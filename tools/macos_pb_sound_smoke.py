#!/usr/bin/env python3
"""Validate host-controlled sound rules with two real isolated Mac game peers.

Run sequentially with other multiplayer tests: Halo uses fixed game ports.
Audio is enabled with zero final master gain. Event allocation and pre-mixer
mute counters remain live; the production PCM fixture verifies actual silence.
This runner never builds, installs, modifies personal saves, or publishes.
"""
import argparse
import hashlib
import ipaddress
import json
import re
import socket
import subprocess
import time
from pathlib import Path

from macos_benchmark import Console
from macos_multiplayer_smoke import ROOT, BUILD, prepare
from macos_performance_compatibility import PeerPair, redact
from macos_performance_smoke import STATUS, free_port, wait_for

VOICES = re.compile(
    r'^PB sound voices: normal=(\d+) movement=(\d+) ready=(\d+) \| muted: movement=(\d+) ready=(\d+)\s*$', re.M)
DETAIL = re.compile(
    r'^PB sound effects=(\d+) particles=(\d+) last_voice=([0-9a-f]+) last_tag=([0-9a-f]+) last_role=(\d+)\s*$', re.M)
TICK_LINE = re.compile(r'network test: tick (\d+)[^\n]*')
PLAYER = re.compile(r'player (\d+): (.*?)(?= player \d+:| \||$)')
AMMO = re.compile(r'(?:^| )([0-9a-f]+):(\d+)(?= |$)')
PHASES = (('normal_initial', 0), ('movement_silent', 8), ('ready_silent', 16),
          ('both_silent', 24), ('normal_restored', 0))


def parse_status(text):
    status, voices, detail = STATUS.findall(text), VOICES.findall(text), DETAIL.findall(text)
    if not status or not voices or not detail:
        raise ValueError('A complete options and sound-statistics response is required')
    flags, ticks, visible, supported = map(int, status[-1])
    normal, movement, ready, movement_muted, ready_muted = map(int, voices[-1])
    effects, particles, last_voice, last_tag, last_role = detail[-1]
    return dict(flags=flags, ticks=ticks, visible=visible, supported=supported,
                voices=dict(normal=normal, movement=movement, ready=ready),
                muted=dict(movement=movement_muted, ready=ready_muted),
                effects=int(effects), particles=int(particles), last_voice=last_voice,
                last_tag=last_tag, last_role=int(last_role))


def counter_delta(before, after):
    result = {key: {role: after[key][role] - value for role, value in before[key].items()}
              for key in ('voices', 'muted')}
    if any(value < 0 for group in result.values() for value in group.values()):
        raise ValueError('Sound statistics reset during a phase; the game/map changed')
    return result


def phase_checks(before, after, flags):
    delta = counter_delta(before, after)
    checks = dict(flags_preserved=before['flags'] == after['flags'] == flags,
                  match_clock_advances=after['ticks'] > before['ticks'],
                  normal_voices_created=delta['voices']['normal'] > 0,
                  movement_voices_created=delta['voices']['movement'] > 0,
                  ready_voices_created=delta['voices']['ready'] > 0,
                  movement_mute_correct=(delta['muted']['movement'] > 0 if flags & 8 else delta['muted']['movement'] == 0),
                  ready_mute_correct=(delta['muted']['ready'] > 0 if flags & 16 else delta['muted']['ready'] == 0))
    return delta, checks


def network_samples(text, after_tick=-1):
    samples = {}
    for match in TICK_LINE.finditer(text):
        tick = int(match[1])
        if tick <= after_tick:
            continue
        line = match[0]
        players = []
        for player in PLAYER.finditer(line):
            details = player[2]
            players.append(dict(index=int(player[1]), dead=details.startswith('dead'),
                                weapons={tag: int(rounds) for tag, rounds in AMMO.findall(details)}))
        samples[tick] = dict(tick=tick, players=players, line=redact(line))
    return list(samples.values())


class SoundPeerPair(PeerPair):
    def launch(self, role, legacy=False, invite=None):
        assert not legacy
        folder = self.folder / role
        self.folders[role] = folder
        port = free_port()
        lifetime = 130 + int(self.args.phase_seconds * len(PHASES))
        environment = prepare(folder, role, 'invite', lifetime, self.args.host_address,
                              '127.0.0.1', 'slayer', 100, self.args.map, self.args.map_source, True)
        (folder / 'data/sounds').symlink_to((ROOT / 'assets/sounds').resolve(strict=True))
        # These existing overrides are already used by the standard smoke test.
        # Master 0 mutes final PCM without skipping the engine's sound pipeline.
        environment.pop('HALO_NO_AUDIO', None)
        config_path = folder / 'saves/config.toml'
        config = config_path.read_text().replace('network_test_start = 20.0', 'network_test_start = 25.0')
        config = config.replace('test_input = "bot:', 'test_input = "sound:')
        config = config.replace('[debug]\n', f'[debug]\ntelnet_console = true\ntelnet_console_port = {port}\n')
        config += ('\n[game]\nconsole_log = "all"\n[update]\nauto = false\n'
                   '\n[audio]\nenabled = true\nvolume = 0.0\n')
        config_path.write_text(config)
        command = [str(self.args.executable), str(self.args.guest)]
        if invite:
            command.append(invite)
        log = (folder / 'game.log').open('w')
        self.streams.append(log)
        self.processes[role] = subprocess.Popen(command, cwd=ROOT, env=environment,
                                               stdout=log, stderr=subprocess.STDOUT)

        def connect():
            self.assert_alive()
            try:
                return socket.create_connection(('127.0.0.1', port), timeout=.2)
            except OSError:
                return None

        connection = wait_for(connect, role + ' console did not open')
        self.sockets.append(connection)
        transcript = (folder / 'console.log').open('w')
        self.streams.append(transcript)
        self.consoles[role] = Console(connection, transcript)
        self.result['peers'][role] = dict(folder=str(folder), pid=self.processes[role].pid, console_port=port)
        print(self.args.map + ': started ' + role, flush=True)

    def native_command(self, role, flags=None):
        console = self.consoles[role]
        console.send('performance_options' + ('' if flags is None else ' ' + str(flags)))
        text, deadline = '', time.monotonic() + 10
        while time.monotonic() < deadline:
            self.assert_alive()
            try:
                chunk = console.connection.recv(65536)
            except socket.timeout:
                continue
            if not chunk:
                raise RuntimeError(role + ' console disconnected')
            chunk = chunk.decode('latin1')
            console.transcript.write(chunk)
            console.transcript.flush()
            text += chunk
            complete = '\n'.join(text.replace('\r', '').split('\n')[:-1])
            # Wait through the final sound line, rather than leaving a partial
            # previous status in the socket for the next phase's baseline.
            if DETAIL.search(complete) or 'performance options change refused:' in complete:
                return complete
        raise TimeoutError(role + ' did not return complete native sound statistics')

    def status(self, role):
        return parse_status(self.native_command(role))

    def synchronized(self, flags):
        snapshots = {}

        def ready():
            for role in ('host', 'client'):
                snapshots[role] = self.status(role)
            return (all(value['flags'] == flags and value['ticks'] >= 0 for value in snapshots.values())
                    and abs(snapshots['host']['ticks'] - snapshots['client']['ticks']) <= 30)

        wait_for(ready, 'Both peers did not synchronize flags ' + str(flags), 15)
        return dict(snapshots)


def run(args, output):
    map_path = args.map_source or ROOT / 'assets/maps' / (args.map + '.map')
    result = dict(scope='Two actual game instances on one Mac, isolated saves; no physical-network or listening claim.',
                  map=args.map, map_source=str(map_path), map_sha256=hashlib.sha256(map_path.read_bytes()).hexdigest(),
                  guest_sha256=hashlib.sha256(args.guest.read_bytes()).hexdigest(),
                  native_sha256=hashlib.sha256(args.executable.read_bytes()).hexdigest(),
                  audio_enabled=True, final_master_volume=0, phase_seconds=args.phase_seconds,
                  input='sound:<seed>: ordinary move/fire/jump/grenade + Y every 11s + X every 13s',
                  network_test_shoot_seconds=3, network_test_kill_seconds=12, checks={}, phases=[], peers={})
    pair = SoundPeerPair(output, args, result)
    try:
        pair.launch('host')
        invite = pair.invite()
        result['checks']['host_defaults_normal'] = pair.status('host')['flags'] == 0
        pair.launch('client', invite=invite)
        result['initial_ticks'] = pair.both_playing()
        initial = pair.synchronized(0)
        result['checks']['both_default_normal'] = all(value['flags'] == 0 for value in initial.values())
        response = pair.native_command('client', 24)
        result['checks']['client_cannot_change_host_rules'] = 'performance options change refused:' in response
        pair.synchronized(0)
        for name, flags in PHASES:
            response = pair.native_command('host', flags)
            if 'change refused:' in response:
                raise AssertionError('Host could not set flags ' + str(flags))
            before = pair.synchronized(flags)
            phase = dict(name=name, flags=flags, before=before, peers={})
            result['phases'].append(phase)
            print(args.map + ': ' + name + ' flags=' + str(flags), flush=True)
            started = time.monotonic()
            while time.monotonic() - started < args.phase_seconds:
                pair.assert_alive()
                time.sleep(.2)
            after = pair.synchronized(flags)
            phase['elapsed_seconds'] = round(time.monotonic() - started, 3)
            phase['after'] = after
            for role in ('host', 'client'):
                delta, checks = phase_checks(before[role], after[role], flags)
                samples = network_samples(pair.log(role), before[role]['ticks'])
                checks['network_tick_and_ammo_evidence'] = bool(samples) and any(
                    player['weapons'] for sample in samples for player in sample['players'])
                phase['peers'][role] = dict(delta=delta, checks=checks, network_samples=samples)
            phase['passed'] = all(all(peer['checks'].values()) for peer in phase['peers'].values())
            (output / 'validation.json').write_text(json.dumps(result, indent=2) + '\n')
            if not phase['passed']:
                failures = [role + ':' + check for role, peer in phase['peers'].items()
                            for check, passed in peer['checks'].items() if not passed]
                raise AssertionError(name + ' failed: ' + ', '.join(failures))
        result['checks']['all_phases_passed'] = all(phase['passed'] for phase in result['phases'])
        result['checks']['normal_restored_on_both_peers'] = all(value['flags'] == 0 for value in after.values())
        for role in ('host', 'client'):
            text = pair.log(role)
            samples = network_samples(text)
            ammo = {}
            for sample in samples:
                for player in sample['players']:
                    for tag, rounds in player['weapons'].items():
                        ammo.setdefault((player['index'], tag), set()).add(rounds)
            result['checks'][role + '_ammo_changes_observed'] = any(len(values) > 1 for values in ammo.values())
            dead, respawned = set(), set()
            for sample in samples:
                for player in sample['players']:
                    if player['dead']:
                        dead.add(player['index'])
                    elif player['index'] in dead and player['weapons']:
                        respawned.add(player['index'])
            result['checks'][role + '_death_and_respawn_observed'] = bool(respawned)
        result['checks']['host_kill_scenario_executed'] = 'network test: the first player kills the last' in pair.log('host')
    except BaseException as error:
        result['error'] = redact(str(error))
        raise
    finally:
        pair.close()
        result['passed'] = ('error' not in result and len(result['phases']) == len(PHASES)
                            and bool(result['checks']) and all(result['checks'].values()))
        (output / 'validation.json').write_text(json.dumps(result, indent=2) + '\n')
    if not result['passed']:
        raise AssertionError('Sound smoke checks failed; inspect validation.json')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--map', required=True)
    parser.add_argument('--map-source', type=Path)
    parser.add_argument('--phase-seconds', type=float, default=15.0)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--guest', type=Path, default=BUILD / 'halo_guest.elf')
    parser.add_argument('--executable', type=Path, default=BUILD / 'halo')
    parser.add_argument('--host-address')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_ -]{1,31}', args.map) or not 15 <= args.phase_seconds <= 60:
        parser.error('Provide a safe map name and a phase duration from 15 to 60 seconds')
    from community_maps import cache_header
    stock = ROOT / 'assets/maps' / (args.map + '.map')
    source = (args.map_source or stock).resolve(strict=True)
    header = cache_header(source)
    if header['version'] != 5 or header['type'] != 1 or header['name'] != args.map:
        parser.error('Expected an Xbox v5 multiplayer map matching --map')
    args.map_source = None if stock.exists() and source == stock.resolve() else source
    if not (ROOT / 'assets/sounds').is_dir():
        parser.error('The existing local sounds directory is required')
    for field in ('guest', 'executable'):
        setattr(args, field, getattr(args, field).resolve(strict=True))
    if not args.host_address:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as route:
            route.connect(('192.0.2.1', 9))
            args.host_address = route.getsockname()[0]
    args.host_address = str(ipaddress.IPv4Address(args.host_address))
    if ipaddress.IPv4Address(args.host_address).is_loopback:
        parser.error('A configured LAN IPv4 address and loopback are required')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    run(args, output)
    print(args.map + ': actual sound-rule pipeline PASS; ' + str(output / 'validation.json'), flush=True)


if __name__ == '__main__':
    main()
