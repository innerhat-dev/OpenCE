#!/usr/bin/env python3
"""Check practice-option interoperability with the saved unextended v10 guest.

Runs each pair sequentially with isolated saves and the stock Blood Gulch map.
Halo's fixed game ports mean this must not overlap another multiplayer runner.
Only the opt-in consoles use ephemeral ports. Invite tokens stay in local logs
and are never printed or copied into the validation report.
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

from macos_benchmark import Console, FAULT
from macos_multiplayer_smoke import ROOT, BUILD, prepare, read_log
from macos_performance_smoke import STATUS, free_port, wait_for

INVITE = re.compile(r'halo://join/[0-9a-fA-F]{64}(?![0-9a-fA-F])')
CASES = ('stock_session', 'enabled_session', 'legacy_host')


def redact(text):
    return INVITE.sub('halo://join/[redacted]', text)


def multiplayer_tick(log):
    for line in reversed(re.findall(r'network test: tick[^\n]+', log)):
        if len(set(re.findall(r'player (\d+):', line))) >= 2 and re.search(r'received [1-9]\d*', line):
            return int(re.search(r'tick (\d+)', line)[1])
    return None


class PeerPair:
    def __init__(self, folder, args, result):
        self.folder, self.args, self.result = folder, args, result
        self.processes, self.folders, self.consoles = {}, {}, {}
        self.streams, self.sockets = [], []

    def launch(self, role, legacy=False, invite=None):
        folder = self.folder / role
        self.folders[role] = folder
        port = free_port()
        environment = prepare(folder, role, 'invite', 180, self.args.host_address,
                              '127.0.0.1', 'slayer', 0, 'bloodgulch', None, True)
        if getattr(self.args, 'timer_pack', False):
            sounds = (ROOT / 'assets/sounds').resolve(strict=True)
            if not (sounds / 'performance').is_dir():
                raise ValueError('This case requires the complete timer recording pack')
            (folder / 'data/sounds').symlink_to(sounds)
            environment.pop('HALO_NO_AUDIO', None)
        config_path = folder / 'saves/config.toml'
        config = config_path.read_text().replace('network_test_start = 20.0', 'network_test_start = 25.0')
        config = config.replace('network_test_shoot = 3.0', 'network_test_shoot = 0.0')
        config = config.replace('network_test_kill = 12.0', 'network_test_kill = 0.0')
        config = config.replace('[debug]\n', f'[debug]\ntelnet_console = true\ntelnet_console_port = {port}\n')
        config += '\n[game]\nconsole_log = "all"\n[update]\nauto = false\n'
        config_path.write_text(config)
        guest = self.args.legacy_guest if legacy else self.args.guest
        command = [str(self.args.executable), str(guest)]
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
        print(self.folder.name + ': started ' + ('earlier ' if legacy else 'updated ') + role, flush=True)

    def assert_alive(self):
        for role, process in self.processes.items():
            if process.poll() is not None:
                raise RuntimeError(role + ' exited unexpectedly with code ' + str(process.returncode))

    def log(self, role):
        self.assert_alive()
        text = read_log(self.folders[role])
        debug = self.folders[role] / 'data/debug.txt'
        if debug.exists():
            text += debug.read_text(errors='replace')
        return text

    def invite(self):
        wait_for(lambda: 'network test: game 1, slayer' in self.log('host'), 'Host lobby setup failed')
        return wait_for(lambda: INVITE.search(self.log('host')), 'Host did not create an invite')[0]

    def native_command(self, role, flags=None):
        # Joining clients deliberately reject HS scripts, including an ACK
        # `(print ...)`. This native helper has its own complete response line.
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
            if STATUS.search(complete) or 'performance options change refused:' in complete:
                return complete
        raise TimeoutError(role + ' did not acknowledge native options command')

    def status(self, role):
        matches = STATUS.findall(self.native_command(role))
        if not matches:
            raise RuntimeError(role + ' did not return a complete options status')
        flags, ticks, visible, supported = map(int, matches[-1])
        return dict(flags=flags, ticks=ticks, visible=visible, supported=supported)

    def both_playing(self, after=None):
        snapshots = {}

        def ready():
            for role in ('host', 'client'):
                tick = multiplayer_tick(self.log(role))
                if tick is None or (after and tick <= after[role]):
                    return False
                snapshots[role] = tick
            return dict(snapshots)

        return wait_for(ready, 'Both versions did not exchange updates with two players', 85 if after is None else 12)

    def close(self):
        for connection in self.sockets:
            connection.close()
        for process in self.processes.values():
            if process.poll() is None:
                process.terminate()
        for process in self.processes.values():
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        for stream in self.streams:
            stream.close()
        faults = {}
        for role, folder in self.folders.items():
            diagnostic = read_log(folder)
            debug = folder / 'data/debug.txt'
            if debug.exists():
                diagnostic += debug.read_text(errors='replace')
            faults[role] = FAULT.findall(diagnostic)
        self.result['faults'] = faults
        self.result['checks']['no_runtime_faults'] = not any(faults.values())


def run_case(name, args, output):
    result = {'case': name, 'checks': {}}
    pair = PeerPair(output / name, args, result)
    checks = result['checks']
    try:
        pair.launch('host', legacy=name == 'legacy_host')
        invite = pair.invite()
        if name == 'enabled_session':
            pair.native_command('host', 3)
            checks['host_enabled_before_join'] = pair.status('host')['flags'] == 3
            if not checks['host_enabled_before_join']:
                raise AssertionError('Updated host did not enable options before legacy join')
            pair.launch('client', legacy=True, invite=invite)
            wait_for(lambda: 'not joining a host of network version 32778' in pair.log('client'),
                     'Stock-v10 client did not reject the enabled session', 50)
            client_log = pair.log('client')
            checks['stock_client_rejected_extension_version'] = True
            checks['client_explained_update_required'] = (
                'newer version of the network code' in client_log and 'Update the game to join this host.' in client_log)
            checks['stock_client_never_entered_match'] = not re.search(r'network test: tick', client_log)
            checks['host_remains_enabled'] = pair.status('host')['flags'] == 3
        else:
            pair.launch('client', legacy=name == 'stock_session', invite=invite)
            initial = pair.both_playing()
            checks['both_versions_exchange_updates'] = True
            if name == 'stock_session':
                checks['host_defaults_off'] = pair.status('host')['flags'] == 0
                refusal = pair.native_command('host', 3)
                checks['host_enable_refused_with_legacy_peer'] = 'performance options change refused:' in refusal
                checks['host_stays_off_after_refusal'] = pair.status('host')['flags'] == 0
                checks['host_explained_unsupported_peer'] = 'A connected player does not support these practice options.' in pair.log('host')
                pair.both_playing(after=initial)
                checks['stock_session_continues_after_refusal'] = True
            else:
                checks['updated_client_uses_stock_flags'] = pair.status('client')['flags'] == 0
                checks['legacy_host_accepted_capability_before_join'] = True
            result['ticks'] = initial
    except BaseException as error:
        result['error'] = redact(str(error))
        raise
    finally:
        pair.close()
        result['passed'] = 'error' not in result and bool(checks) and all(checks.values())
        (output / name / 'validation.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--guest', type=Path, default=BUILD / 'halo_guest.elf')
    parser.add_argument('--legacy-guest', type=Path, default=ROOT / 'build/performance-options/baseline-v10/halo_guest.elf')
    parser.add_argument('--executable', type=Path, default=BUILD / 'halo')
    parser.add_argument('--host-address')
    parser.add_argument('--cases', nargs='+', choices=CASES, default=list(CASES))
    args = parser.parse_args()
    for field in ('guest', 'legacy_guest', 'executable'):
        setattr(args, field, getattr(args, field).resolve(strict=True))
    if not args.host_address:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as route:
            route.connect(('192.0.2.1', 9))
            args.host_address = route.getsockname()[0]
    args.host_address = str(ipaddress.IPv4Address(args.host_address))
    if ipaddress.IPv4Address(args.host_address).is_loopback:
        parser.error('A configured LAN IPv4 address and loopback are required')
    if len(set(args.cases)) != len(args.cases):
        parser.error('Specify each case at most once')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    result = {'scope': 'two real instances on one Mac, sequential pairs', 'map': 'bloodgulch',
              'guest_sha256': hashlib.sha256(args.guest.read_bytes()).hexdigest(),
              'legacy_guest_sha256': hashlib.sha256(args.legacy_guest.read_bytes()).hexdigest(),
              'native_sha256': hashlib.sha256(args.executable.read_bytes()).hexdigest(), 'cases': []}
    try:
        for name in args.cases:
            case = run_case(name, args, output)
            result['cases'].append(case)
            if not case['passed']:
                raise AssertionError(name + ' failed; inspect its validation.json')
            print(name + ': PASS', flush=True)
        result['passed'] = True
    except BaseException as error:
        result['passed'] = False
        result['error'] = redact(str(error))
        raise
    finally:
        (output / 'validation.json').write_text(json.dumps(result, indent=2) + '\n')
    print('Performance options stock-v10 compatibility: PASS', flush=True)


if __name__ == '__main__':
    main()
