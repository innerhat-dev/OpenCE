#!/usr/bin/env python3
"""Exercise host-selected practice aids with two isolated native Mac instances.

Uses a stock map or the user's converted v5 map and the existing opt-in loopback
console; never touches personal saves. This checks one Mac, not physical-network
parity. Optional audio uses the existing repo-local sounds, with output muted.
"""
import argparse
import hashlib
import json
import re
import socket
import subprocess
import time
from pathlib import Path

from macos_benchmark import Console, FAULT
from macos_multiplayer_smoke import ROOT, BUILD, prepare, read_log

STATUS = re.compile(r'^performance options: flags=(\d+) ticks=(-?\d+) markers=(\d+)/(\d+)\s*$', re.M)


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def wait_for(predicate, description, timeout=40):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        result = predicate()
        if result:
            return result
        time.sleep(.1)
    raise TimeoutError(description)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--map', required=True)
    parser.add_argument('--map-source', type=Path,
                        help='Converted v5 cache; omit for a map already in assets/maps')
    parser.add_argument('--markers', type=int, required=True)
    parser.add_argument('--flags', type=int, choices=range(32), default=3,
                        help='Requested bits: timer=1, markers=2, audio=4, silent movement=8, silent weapons=16')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--late-join', action='store_true')
    parser.add_argument('--hold-seconds', type=int, default=0,
                        help='Keep both peers alive with the requested flags after checks (0..3600)')
    parser.add_argument('--visible-host', action='store_true',
                        help='Show the isolated host window; the other peer stays hidden')
    parser.add_argument('--host-app', type=Path,
                        help='Run the host from this app bundle with native menus; guest must match build/macos')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_ -]{1,31}', args.map) or args.markers < 1:
        parser.error('Provide a safe map name and its expected positive marker count')
    if not 0 <= args.hold_seconds <= 3600:
        parser.error('--hold-seconds must be between 0 and 3600')
    from community_maps import cache_header
    stock = ROOT / 'assets/maps' / (args.map + '.map')
    map_path = (args.map_source or stock).resolve(strict=True)
    source = None if stock.exists() and map_path == stock.resolve() else map_path
    header = cache_header(map_path)
    if header['version'] != 5 or header['type'] != 1 or header['name'] != args.map:
        parser.error('Expected an Xbox v5 multiplayer map matching --map')
    sounds = ROOT / 'assets/sounds'
    if args.flags & 4 and not (sounds / 'performance').is_dir():
        parser.error('Audio flags require the existing assets/sounds/performance recording pack')
    host_executable = None
    guest_hash = hashlib.sha256((BUILD / 'halo_guest.elf').read_bytes()).hexdigest()
    if args.host_app:
        args.host_app = args.host_app.resolve(strict=True)
        host_executable = args.host_app / 'Contents/MacOS/halo'
        host_guest = args.host_app / 'Contents/Resources/halo_guest.elf'
        if not host_executable.is_file() or not host_guest.is_file():
            parser.error('--host-app must be a complete Halo app bundle')
        if hashlib.sha256(host_guest.read_bytes()).hexdigest() != guest_hash:
            parser.error('App host and build/macos client guests differ; build/install the same revision first')
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.connect(('192.0.2.1', 9))
        host_address = sock.getsockname()[0]
    if host_address == '127.0.0.1':
        raise RuntimeError('A LAN address and loopback are required')
    processes, streams, sockets, consoles, folders = {}, [], [], {}, {}
    result = {'map': args.map, 'map_source': str(map_path), 'late_join': args.late_join,
              'requested_flags': args.flags, 'hold_seconds': args.hold_seconds,
              'host_app': str(args.host_app) if args.host_app else None,
              'audio_pack': str(sounds.resolve()) if sounds.is_dir() else None,
              'audio_output_muted': True, 'peers': {}, 'checks': [],
              'guest_sha256': guest_hash}

    def launch(role, invite=None):
        folder = out / role
        folders[role] = folder
        port = free_port()
        env = prepare(folder, 'host' if role == 'host' else 'client', 'invite', 240 + args.hold_seconds,
                      host_address, '127.0.0.1',
                      'slayer', 0, args.map, source, True, 180)
        if sounds.is_dir():
            (folder / 'data/sounds').symlink_to(sounds.resolve(), target_is_directory=True)
        if args.flags & 4:
            # Existing overrides only: run the mixer at zero master volume so
            # the scheduled cue path executes without background test audio.
            env.pop('HALO_NO_AUDIO', None)
        config_path = folder / 'saves/config.toml'
        config = config_path.read_text().replace('network_test_start = 20.0', 'network_test_start = 25.0')
        config = config.replace('network_test_shoot = 3.0', 'network_test_shoot = 0.0')
        config = config.replace('network_test_kill = 12.0', 'network_test_kill = 0.0')
        if args.visible_host:
            # Scripted controller input replaces real keys. Leave both players
            # stationary for native-menu checks and make the host controllable.
            config = config.replace('test_input = "bot:17"', 'test_input = ""')
            config = config.replace('test_input = "bot:42"', 'test_input = ""')
        if role == 'host' and args.visible_host:
            config = config.replace('hidden_window = true', 'hidden_window = false')
        config = config.replace('[debug]\n', f'[debug]\ntelnet_console = true\ntelnet_console_port = {port}\n')
        config += '\n[game]\nconsole_log = "all"\n[update]\nauto = false\n'
        if args.flags & 4:
            config += '\n[audio]\nenabled = true\nvolume = 0.0\n'
        config_path.write_text(config)
        command = ([str(host_executable)] if role == 'host' and host_executable else
                   [str(BUILD / 'halo'), str(BUILD / 'halo_guest.elf')])
        if invite:
            command.append(invite)
        log = (folder / 'game.log').open('w')
        streams.append(log)
        processes[role] = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        result['peers'][role] = {'pid': processes[role].pid, 'console_port': port,
                                 'folder': str(folder), 'visible': role == 'host' and args.visible_host}
        def connect():
            if processes[role].poll() is not None:
                raise RuntimeError(role + ' exited during startup')
            try:
                return socket.create_connection(('127.0.0.1', port), timeout=.2)
            except OSError:
                return None
        connection = wait_for(connect, role + ' console did not open')
        sockets.append(connection)
        transcript = (folder / 'console.log').open('w')
        streams.append(transcript)
        consoles[role] = Console(connection, transcript)
        print('Started %s PID %d, console %d' % (role, processes[role].pid, port), flush=True)

    def diagnostics(role):
        text = read_log(folders[role])
        debug = folders[role] / 'data/debug.txt'
        if debug.exists():
            text += debug.read_text(errors='replace')
        return text

    def stop(role):
        consoles[role].connection.close()
        process = processes[role]
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()

    def native_command(role, value=None):
        console = consoles[role]
        console.send('performance_options' + ('' if value is None else ' ' + str(value)))
        text = ''
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
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
        raise TimeoutError(role + ' did not acknowledge native command')

    def status(role):
        text = native_command(role)
        matches = STATUS.findall(text.replace('\r', ''))
        if not matches:
            raise RuntimeError(role + ' did not return a complete performance status')
        flags, ticks, visible, supported = map(int, matches[-1])
        return dict(flags=flags, ticks=ticks, visible=visible, supported=supported)

    def check_flags(flags):
        expected = args.markers if flags & 2 else 0
        snapshots = {}
        for role in ('host', 'client'):
            def ready():
                entry = status(role)
                snapshots[role] = entry
                return entry['flags'] == flags and entry['visible'] == expected and entry['supported'] == args.markers
            wait_for(ready, role + ' did not apply flags ' + str(flags), 15)
        result['checks'].append({'flags': flags, 'peers': snapshots})
        print('Both peers: flags=%d, markers=%d/%d' % (flags, expected, args.markers), flush=True)
        return snapshots

    try:
        launch('host')
        wait_for(lambda: 'network test: game 1, slayer' in read_log(folders['host']), 'Host lobby setup failed')
        default = status('host')
        if default['flags'] != 0:
            raise AssertionError('New host did not default to stock')
        response = native_command('host', args.flags)
        if 'change refused' in response or status('host')['flags'] != args.flags:
            raise AssertionError('Host could not enable requested pregame options: ' + response.strip())
        invite = wait_for(lambda: re.search(r'halo://join/[0-9a-fA-F]{64}(?![0-9a-fA-F])', read_log(folders['host'])),
                          'Host did not create invite')[0]
        if args.late_join:
            # Network play requires two machines/players to start. Start with a
            # temporary second peer, then replace it once the game is running;
            # reaping its process frees the loopback address and ports. Launch
            # the replacement immediately: waiting for the departed player's
            # network timeout would leave the host alone and end the match.
            launch('bootstrap', invite)
            wait_for(lambda: status('host')['ticks'] > 90 and status('bootstrap')['ticks'] > 90,
                     'Initial pair did not start the match', 85)
            result['bootstrap'] = {'host': status('host'), 'peer': status('bootstrap')}
            stop('bootstrap')
            result['bootstrap_process_reaped'] = processes['bootstrap'].poll() is not None
            result['host_ticks_before_late_join'] = status('host')['ticks']
        launch('client', invite)
        wait_for(lambda: status('host')['ticks'] >= 0 and status('client')['ticks'] >= 0,
                 'Both peers did not load the match', 85)
        if args.late_join:
            late = wait_for(lambda: re.search(r'joins the game in progress at game tick #(\d+)',
                                             diagnostics('host')),
                            'Client did not use the in-progress join path')
            result['late_join_host_tick'] = int(late[1])
            if result['late_join_host_tick'] <= 90:
                raise AssertionError('Late join did not occur after the match was running')
        snapshots = check_flags(args.flags)
        if abs(snapshots['host']['ticks'] - snapshots['client']['ticks']) > 30:
            raise AssertionError('Client timer differs by more than one second')
        response = native_command('client', 0)
        if ('change refused' not in response or status('host')['flags'] != args.flags or
                status('client')['flags'] != args.flags):
            raise AssertionError('Joining client changed host settings')
        result['client_change_refused'] = True
        # Test each selected bit combination. For the default flags=3 this is
        # exactly the original sequence: 1, 2, 0, 3, 0.
        toggles = [flags for flags in range(1, args.flags) if not flags & ~args.flags]
        toggles += [0, args.flags, 0] if args.flags else [0]
        for flags in toggles:
            native_command('host', flags)
            check_flags(flags)
        if args.hold_seconds:
            native_command('host', args.flags)
            result['hold_start'] = check_flags(args.flags)
            (out / 'session.json').write_text(json.dumps(result, indent=2) + '\n')
            # The game permits one console connection. Release ours while
            # a UI observer checks the held peers, then reconnect for the
            # final consistency check. Observers should close their sockets.
            for role in ('host', 'client'):
                consoles[role].connection.close()
            print('Holding verified peers for %d seconds; %s' %
                  (args.hold_seconds, out / 'session.json'), flush=True)
            deadline = time.monotonic() + args.hold_seconds
            while time.monotonic() < deadline:
                # A local UI observer can finish a long hold as soon as its
                # checks are complete, without killing the test processes.
                if (out / 'finish-hold').exists():
                    break
                for role in ('host', 'client'):
                    if processes[role].poll() is not None:
                        raise RuntimeError(role + ' exited during the requested hold')
                time.sleep(min(1, max(0, deadline - time.monotonic())))
            for role in ('host', 'client'):
                connection = socket.create_connection(('127.0.0.1', result['peers'][role]['console_port']), timeout=2)
                sockets.append(connection)
                consoles[role] = Console(connection, consoles[role].transcript)
            # A native UI observer may have deliberately changed host options
            # during the hold; verify those final settings reached both peers.
            result['hold_end'] = check_flags(status('host')['flags'])
        result['passed'] = True
    except BaseException as error:
        result['passed'] = False
        result['error'] = str(error)
        raise
    finally:
        for sock in sockets:
            sock.close()
        for process in processes.values():
            if process.poll() is None:
                process.terminate()
        for process in processes.values():
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        for stream in streams:
            stream.close()
        faults = {role: FAULT.findall(diagnostics(role)) for role in folders}
        result['faults'] = faults
        if any(faults.values()):
            result['passed'] = False
        (out / 'validation.json').write_text(json.dumps(result, indent=2) + '\n')
    if not result['passed']:
        raise RuntimeError('Runtime fault: inspect validation.json')
    print('Performance options multiplayer smoke: PASS', flush=True)


if __name__ == '__main__':
    main()
