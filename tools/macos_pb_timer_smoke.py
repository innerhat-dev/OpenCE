#!/usr/bin/env python3
"""Check local timer preferences and the shared audio gate in two real Mac peers.

Uses stock Prisoner (rockets at 120s, camo/overshield at 60s), a user-installed
recording pack, and isolated saves. Host items-only and client common-only
preferences must produce different successful dispatch counters in one match.
The client joins after 65s; flags 5 run through 125s, then flags 1 through 185s.
Run sequentially with other multiplayer runners because game ports are fixed.
Never builds, installs, publishes, or reads/writes personal save directories.
"""
import argparse
import hashlib
import ipaddress
import json
import re
import socket
import subprocess
import time
import tomllib
import wave
from pathlib import Path

from import_performance_audio import CUES
from macos_benchmark import Console
from macos_multiplayer_smoke import ROOT, BUILD, prepare
from macos_pb_sound_smoke import SoundPeerPair
from macos_performance_compatibility import redact
from macos_performance_smoke import STATUS, free_port, wait_for

TIMER = re.compile(r'^PB timer: prefs=(\d+) countdown=(\d+) beeps=(\d+) minutes=(\d+) items=(\d+) last=([^\s]+)\s*$', re.M)
ITEMS = re.compile(r'^PB timer items: rocket=(\d+) camo=(\d+) overshield=(\d+)\s*$', re.M)
JOINED = re.compile(r'(?:joined|joins) the game in progress at game tick #(\d+)')
LATE_JOIN_SECONDS, ACTIVE_SECONDS, GATED_SECONDS = 65, 125, 185


def parse_status(text):
    status, timer, items = STATUS.findall(text), TIMER.findall(text), ITEMS.findall(text)
    if not status or not timer or not items:
        raise ValueError('A complete options, timer, and per-item statistics response is required')
    flags, ticks, visible, supported = map(int, status[-1])
    prefs, countdown, beeps, minutes, item_count = map(int, timer[-1][:5])
    return dict(flags=flags, ticks=ticks, visible=visible, supported=supported, prefs=prefs,
                cues=dict(countdown=countdown, beeps=beeps, minutes=minutes, items=item_count),
                items=dict(zip(('rocket', 'camo', 'overshield'), map(int, items[-1]))), last=timer[-1][5])


def active_checks(snapshots):
    host, client = snapshots['host'], snapshots['client']
    return dict(shared_flags_enabled=host['flags'] == client['flags'] == 5,
                local_preferences_differ=host['prefs'] == 8 and client['prefs'] == 7,
                host_common_cues_disabled=all(host['cues'][key] == 0 for key in ('countdown', 'beeps', 'minutes')),
                host_all_item_categories_dispatched=all(value > 0 for value in host['items'].values()),
                host_item_total_matches_categories=host['cues']['items'] == sum(host['items'].values()),
                client_all_common_categories_dispatched=all(client['cues'][key] > 0 for key in ('countdown', 'beeps', 'minutes')),
                client_item_cues_disabled=client['cues']['items'] == 0 and not any(client['items'].values()),
                both_clocks_reached_125_seconds=all(value['ticks'] >= ACTIVE_SECONDS * 30 for value in snapshots.values()))


def gated_checks(before, after):
    checks = {}
    for role in ('host', 'client'):
        checks[role + '_shared_audio_gate_off'] = before[role]['flags'] == after[role]['flags'] == 1
        checks[role + '_local_preferences_unchanged'] = before[role]['prefs'] == after[role]['prefs'] == (8 if role == 'host' else 7)
        checks[role + '_no_new_cues'] = before[role]['cues'] == after[role]['cues'] and before[role]['items'] == after[role]['items']
        checks[role + '_clock_passed_new_cue_opportunities'] = after[role]['ticks'] >= GATED_SECONDS * 30 and before[role]['ticks'] < 150 * 30
    return checks


class TimerPeerPair(SoundPeerPair):
    def launch(self, role, legacy=False, invite=None):
        if legacy:
            raise ValueError('Timer preferences require the current guest on both peers')
        folder = self.folder / role
        self.folders[role] = folder
        port = free_port()
        environment = prepare(folder, role, 'invite', 280 + self.args.hold_seconds,
                              self.args.host_address, '127.0.0.1', 'slayer', 100, self.args.map, None, True)
        (folder / 'data/sounds').symlink_to(self.args.sounds)
        environment.pop('HALO_NO_AUDIO', None)
        config_path = folder / 'saves/config.toml'
        config = config_path.read_text().replace('network_test_start = 20.0', 'network_test_start = 25.0')
        config = config.replace('network_test_shoot = 3.0', 'network_test_shoot = 0.0')
        config = config.replace('network_test_kill = 12.0', 'network_test_kill = 0.0')
        config = config.replace('[debug]\n', f'[debug]\ntelnet_console = true\ntelnet_console_port = {port}\n')
        if role == 'host' and self.args.hold_seconds:
            config = config.replace('hidden_window = true', 'hidden_window = false')
        config = config.replace('[display]\n', '[display]\ntimer_position = 0\ntimer_scale = 1.0\n')
        common, items = ('false', 'true') if role == 'host' else ('true', 'false')
        config += ('\n[game]\nconsole_log = "all"\n[update]\nauto = false\n'
                   '\n[audio]\nenabled = true\nvolume = 0.0\ntimer_volume = 1.0\n'
                   f'timer_countdown = {common}\ntimer_beeps = {common}\ntimer_minutes = {common}\ntimer_items = {items}\n'
                   'timer_smoke_marker = "isolated timer smoke" # preserve unknown setting\n')
        config_path.write_text(config)
        command = [str(self.args.executable), str(self.args.guest)]
        if invite:
            command.append(invite)
        log = (folder / 'game.log').open('w')
        self.streams.append(log)
        self.processes[role] = subprocess.Popen(command, cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT)

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
        print(self.args.map + ': started ' + role + (' items-only' if role == 'host' else ' common-only'), flush=True)

    def status(self, role):
        return parse_status(self.native_command(role))

    def reap_bootstrap(self):
        self.consoles.pop('bootstrap').connection.close()
        process = self.processes.pop('bootstrap')
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        self.result['peers']['bootstrap']['exit_code'] = process.returncode

    def until(self, seconds):
        last_print = -1
        snapshot = None
        deadline = time.monotonic() + seconds + 60
        while time.monotonic() < deadline:
            snapshot = self.status('host')
            elapsed = snapshot['ticks'] // 30
            if elapsed >= seconds:
                return snapshot
            if elapsed >= 0 and elapsed // 15 != last_print:
                print(self.args.map + ': match ' + str(elapsed) + 's; waiting for ' + str(seconds) + 's', flush=True)
                last_print = elapsed // 15
            time.sleep(.5)
        raise TimeoutError('Match clock did not reach ' + str(seconds) + 's; last status ' + str(snapshot))

    def persisted_preferences(self, role):
        config_path = self.folders[role] / 'saves/config.toml'
        config = tomllib.loads(config_path.read_text())
        common = role == 'client'
        return (all(config['audio'][key] is common for key in ('timer_countdown', 'timer_beeps', 'timer_minutes'))
                and config['audio']['timer_items'] is (not common)
                and config['audio']['timer_volume'] == 1.0
                and config['audio']['timer_smoke_marker'] == 'isolated timer smoke'
                and config['display']['timer_position'] == 0 and config['display']['timer_scale'] == 1.0)


def require(checks, label):
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise AssertionError(label + ': ' + ', '.join(failures))


def run(args, output):
    result = dict(scope='Two actual peers on one Mac with isolated preferences; successful dispatch evidence, not a listening or physical-network test.',
                  map=args.map, map_sha256=hashlib.sha256((ROOT / 'assets/maps' / (args.map + '.map')).read_bytes()).hexdigest(),
                  guest_sha256=hashlib.sha256(args.guest.read_bytes()).hexdigest(), native_sha256=hashlib.sha256(args.executable.read_bytes()).hexdigest(),
                  audio_enabled=True, final_master_volume=0, late_join_seconds=LATE_JOIN_SECONDS,
                  active_until_seconds=ACTIVE_SECONDS, gated_until_seconds=GATED_SECONDS, checks={}, phases=[], peers={})
    pair = TimerPeerPair(output, args, result)
    checks = result['checks']
    try:
        pair.launch('host')
        invite = pair.invite()
        initial = pair.status('host')
        checks['host_rules_default_off'] = initial['flags'] == 0
        pair.native_command('host', 5)
        # Network play requires two peers to start. Reap the bootstrap before
        # replacing it so both clients never contend for fixed loopback ports.
        pair.launch('bootstrap', invite=invite)
        before_join = pair.until(LATE_JOIN_SECONDS)
        checks['host_enabled_before_late_join'] = before_join['flags'] == 5
        checks['host_reads_items_only_preferences'] = before_join['prefs'] == 8
        result['bootstrap_status'] = pair.status('bootstrap')
        pair.reap_bootstrap()
        checks['bootstrap_reaped_before_replacement'] = 'bootstrap' not in pair.processes
        pair.launch('client', invite=invite)
        result['initial_network_ticks'] = pair.both_playing()
        joined = pair.synchronized(5)
        result['late_join'] = dict(before=before_join, after=joined)
        checks['client_joined_existing_match_clock'] = joined['client']['ticks'] >= LATE_JOIN_SECONDS * 30
        joined_log = JOINED.search(pair.log('client'))
        checks['client_reported_join_in_progress'] = bool(joined_log and int(joined_log[1]) >= LATE_JOIN_SECONDS * 30)
        checks['late_join_observed_before_next_minute'] = joined['client']['ticks'] < 115 * 30
        checks['late_join_did_not_replay_previous_minute'] = joined['client']['cues']['minutes'] == 0
        checks['client_reads_common_only_preferences'] = joined['client']['prefs'] == 7
        checks['client_cannot_change_shared_gate'] = 'performance options change refused:' in pair.native_command('client', 1)
        require(checks, 'Initial and late-join checks failed')
        pair.until(ACTIVE_SECONDS)
        active = pair.synchronized(5)
        phase = dict(name='local_preferences', status=active, checks=active_checks(active))
        result['phases'].append(phase)
        require(phase['checks'], 'Active timer checks failed')
        pair.native_command('host', 1)
        disabled = pair.synchronized(1)
        print(args.map + ': shared Timer Sounds off; crossing more common and powerup cue opportunities', flush=True)
        pair.until(GATED_SECONDS)
        after = pair.synchronized(1)
        phase = dict(name='shared_audio_gate', before=disabled, after=after, checks=gated_checks(disabled, after))
        result['phases'].append(phase)
        require(phase['checks'], 'Shared timer gate checks failed')
        checks['both_continue_network_updates'] = bool(pair.both_playing(after=result['initial_network_ticks']))
        for role in ('host', 'client'):
            checks[role + '_isolated_preferences_retained'] = pair.persisted_preferences(role)
        checks['both_phases_passed'] = all(all(phase['checks'].values()) for phase in result['phases'])
        require(checks, 'Final timer checks failed')
        if args.hold_seconds:
            pair.native_command('host', 5)
            pair.synchronized(5)
            (output / 'session.json').write_text(json.dumps(result['peers'], indent=2) + '\n')
            (output / 'validation.json').write_text(json.dumps(result, indent=2) + '\n')
            print('Holding isolated peers for ' + str(args.hold_seconds) + 's; ' + str(output / 'session.json'), flush=True)
            deadline = time.monotonic() + args.hold_seconds
            while time.monotonic() < deadline:
                pair.assert_alive()
                time.sleep(.5)
    except BaseException as error:
        result['error'] = redact(str(error))
        raise
    finally:
        pair.close()
        result['passed'] = 'error' not in result and len(result['phases']) == 2 and bool(checks) and all(checks.values())
        (output / 'validation.json').write_text(json.dumps(result, indent=2) + '\n')
    require(checks, 'Timer smoke cleanup checks failed')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--map', choices=('prisoner',), default='prisoner', help='Audited map with all three deterministic item categories')
    parser.add_argument('--guest', type=Path, default=BUILD / 'halo_guest.elf')
    parser.add_argument('--executable', type=Path, default=BUILD / 'halo')
    parser.add_argument('--sounds', type=Path, default=ROOT / 'assets/sounds', help='Existing user-local sounds directory containing performance/*.wav')
    parser.add_argument('--host-address')
    parser.add_argument('--hold-seconds', type=int, default=0, help='Keep isolated peers alive after checks, with a visible host (0..3600)')
    args = parser.parse_args()
    if not 0 <= args.hold_seconds <= 3600:
        parser.error('--hold-seconds must be between 0 and 3600')
    for field in ('guest', 'executable', 'sounds'):
        setattr(args, field, getattr(args, field).resolve(strict=True))
    for cue in CUES:
        with wave.open(str(args.sounds / 'performance' / (cue + '.wav')), 'rb') as audio:
            if audio.getnframes() == 0:
                parser.error('Timer recording pack contains an empty cue: ' + cue)
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
    print(args.map + ': local timer preferences, late join and shared gate PASS; ' + str(output / 'validation.json'), flush=True)


if __name__ == '__main__':
    main()
