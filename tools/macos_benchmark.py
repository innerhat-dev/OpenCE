#!/usr/bin/env python3
"""Profile acknowledged game workloads using fresh, isolated saves/settings."""
import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import re
import socket
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
LEVELS = ('a10', 'a30', 'b30', 'prisoner', 'chillout')
MULTIPLAYER_LEVELS = ('prisoner', 'chillout')
SCRIPT_ERROR = re.compile(r'overflowed client buffer|not a valid|not found|syntax error|unable to parse|failed to compile', re.I)
FAULT = re.compile(r'ASSERTION FAILED|EXCEPTION halt in|guest abort|SIGSEGV|signal (?:10|11)|GL error', re.I)


def level_path(level):
    return 'levels\\' + ('test\\' if level in MULTIPLAYER_LEVELS else '') + level + '\\' + level


class Console:
    def __init__(self, connection, transcript):
        self.connection, self.transcript = connection, transcript
        connection.settimeout(.1)

    def send(self, expression):
        encoded = expression.encode('ascii')
        # The game's actual buffer holds 128 bytes including its trailing NUL.
        if len(encoded) >= 128 or '\n' in expression or '\r' in expression:
            raise ValueError('Console expressions must fit in 127 ASCII bytes')
        self.transcript.write('\nSEND: ' + expression + '\n')
        self.connection.sendall(encoded + b'\r\n')

    def wait(self, marker, timeout=8):
        received = ''
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                data = self.connection.recv(65536)
            except socket.timeout:
                continue
            if not data:
                raise RuntimeError('Game console disconnected')
            text = data.decode('latin1')
            self.transcript.write(text)
            self.transcript.flush()
            received += text
            if SCRIPT_ERROR.search(received):
                raise RuntimeError('Game rejected the workload; inspect console.log')
            # Input is echoed. Only a complete output line counts as an ACK.
            if marker in [line.strip() for line in received.replace('\r', '').split('\n')[:-1]]:
                return received
        raise TimeoutError('Game did not acknowledge ' + marker)

    def command(self, expression, timeout=8):
        marker = 'bench_' + uuid.uuid4().hex[:12]
        self.send(expression)
        self.send('(print "' + marker + '")')
        return self.wait(marker, timeout)

    def player_ready(self, timeout=30):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            marker = 'ready_' + uuid.uuid4().hex[:12]
            self.send('(if (> (list_count (players)) 0) (print "' + marker + '"))')
            try:
                self.wait(marker, min(2, max(.1, deadline - time.monotonic())))
                return
            except TimeoutError:
                continue
        raise TimeoutError('Map did not produce a player')


def prepare(output, levels, seconds, fullscreen, hidden, console_port, screenshot_every=0):
    output.mkdir(parents=True, exist_ok=False)
    data, saves = output / 'data', output / 'saves'
    (data / 'maps').mkdir(parents=True)
    saves.mkdir()
    for path in (ROOT / 'assets/maps').iterdir():
        if path.is_file():
            (data / 'maps' / path.name).symlink_to(path.resolve())
    for level in ('ui', *levels):
        if not (data / 'maps' / (level + '.map')).exists():
            raise RuntimeError('Missing test map: ' + level)
    variant = 'game_variant slayer\n' if levels[0] in MULTIPLAYER_LEVELS else ''
    (data / 'init.txt').write_text(variant + 'map_name ' + level_path(levels[0]) + '\n')
    (saves / 'config.toml').write_text(f'''[network]
online = false
allow_upnp = false
join_from_clipboard = false
[discord]
application_id = ""
[update]
auto = false
[display]
interpolation = true
vsync = true
[game]
console_log = "all"
[debug]
telnet_console = true
telnet_console_port = {console_port}
hidden_window = {str(hidden).lower()}
gl_debug = true
exit_after = {seconds}.0
''')
    if screenshot_every:
        screenshots = output / 'screenshots'
        screenshots.mkdir()
        with (saves / 'config.toml').open('a') as config:
            config.write('screenshot_every = ' + str(screenshot_every) + '\n')
            config.write('screenshot_directory = ' + json.dumps(str(screenshots)) + '\n')
    # Unrelated launch overrides must not alter this controlled workload.
    environment = {k: v for k, v in os.environ.items() if not k.startswith('HALO_')}
    environment.update(HALO_DATA_ROOT=str(data), HALO_SAVE_ROOT=str(saves),
                       HALO_PERF_LOG=str(output / 'frames.csv'), HALO_VOLUME='0',
                       HALO_WINDOWED='0' if fullscreen else '1')
    if not fullscreen:
        environment['HALO_SCREEN_WIDTH'] = '640'
    return environment


def summarize(path):
    with path.open() as stream:
        frames = list(csv.DictReader(stream))
    active = [r for r in frames if int(r['draws']) > 0]
    if not active:
        raise RuntimeError('No rendered frames were recorded')
    times = sorted(float(r['frame_ms']) for r in active)
    if any(not math.isfinite(value) or value <= 0 for value in times):
        raise RuntimeError('Invalid frame timings')
    percentile = lambda q: times[min(len(times) - 1, int((len(times) - 1) * q))]
    return {'rendered_frames': len(active), 'median_frame_ms': percentile(.5),
            'p95_frame_ms': percentile(.95), 'p99_frame_ms': percentile(.99),
            'max_footprint_mb': max(float(r['footprint_mb']) for r in frames),
            'mean_upload_bytes_per_frame': sum(int(r['upload_bytes']) for r in active) / len(active),
            'mean_driver_draw_ms': sum(float(r['draw_ms']) for r in active) / len(active)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--level', choices=LEVELS, default='a30')
    parser.add_argument('--levels', help='Comma-separated map sequence, repeated throughout the run')
    parser.add_argument('--cycle-seconds', type=float, default=90)
    parser.add_argument('--seconds', type=int, default=70)
    parser.add_argument('--effects', action='store_true')
    parser.add_argument('--interval', type=float, default=2)
    parser.add_argument('--checkpoints', action='store_true', help='Verify a safe campaign save and revert in each map')
    parser.add_argument('--fullscreen', action='store_true')
    parser.add_argument('--hidden', action='store_true')
    parser.add_argument('--screenshot-every', type=int, default=0, help='Capture every N frames for visual checks (0 disables)')
    parser.add_argument('--guest', type=Path, default=ROOT / 'build/macos/halo_guest.elf')
    parser.add_argument('--host', type=Path, default=ROOT / 'build/macos/halo')
    args = parser.parse_args()
    levels = args.levels.split(',') if args.levels else [args.level]
    if any(level not in LEVELS for level in levels) or args.seconds < 30 or args.interval < .05 or args.cycle_seconds < 30 or args.screenshot_every < 0:
        parser.error('Use known maps, at least 30 seconds per run/map, and a positive effect interval')
    if args.checkpoints and any(level in MULTIPLAYER_LEVELS for level in levels):
        parser.error('Checkpoint tests require campaign maps')
    output = args.output.resolve()
    if output.exists():
        parser.error('Use a new output directory to preserve previous evidence')
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1', 0))
        port = reservation.getsockname()[1]
    environment = prepare(output, levels, args.seconds, args.fullscreen, args.hidden, port, args.screenshot_every)
    record = {'levels': levels, 'seconds': args.seconds, 'effects_requested': args.effects,
              'effect_interval_seconds': args.interval, 'cycle_seconds': args.cycle_seconds,
              'effect_commands_acknowledged': 0, 'map_changes_acknowledged': 0,
              'checkpoint_reverts_verified': 0, 'passed': False,
              'guest_sha256': hashlib.sha256(args.guest.read_bytes()).hexdigest()}
    process = None
    connection = None
    started = time.monotonic()
    try:
        with (output / 'game.log').open('w') as log, (output / 'console.log').open('w') as transcript:
            process = subprocess.Popen([args.host.resolve(), args.guest.resolve()], env=environment,
                                       cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
            deadline = started + min(60, args.seconds - 10)
            while time.monotonic() < deadline and process.poll() is None:
                try:
                    connection = socket.create_connection(('127.0.0.1', port), .5)
                    break
                except OSError:
                    time.sleep(.1)
            if not connection:
                raise RuntimeError('Game console did not start')
            console = Console(connection, transcript)
            console.player_ready()
            console.command('(set cheat_deathless_player true)')
            if len(levels) > 1 or args.checkpoints:
                console.command('(set debug_game_save true)')
            next_effect, next_map = started + 20, started + args.cycle_seconds
            checkpoint_at = started + 15 if args.checkpoints else float('inf')
            map_index = 0
            while process.poll() is None and time.monotonic() < started + args.seconds + 30:
                now = time.monotonic()
                if now >= next_map and len(levels) > 1 and now < started + args.seconds - 15:
                    map_index = (map_index + 1) % len(levels)
                    variant = 'slayer' if levels[map_index] in MULTIPLAYER_LEVELS else ''
                    console.command('(game_variant "' + variant + '")')
                    console.send('map_name ' + level_path(levels[map_index]))
                    console.wait('loaded map ' + level_path(levels[map_index]), timeout=45)
                    console.player_ready()
                    record['map_changes_acknowledged'] += 1
                    next_map += args.cycle_seconds
                    checkpoint_at = time.monotonic() + 10 if args.checkpoints else float('inf')
                    next_effect = time.monotonic() + 5
                if now >= checkpoint_at:
                    console.command('(set debug_game_save true)')
                    console.send('(game_save)')
                    console.wait('checkpoint save completed', timeout=12)
                    console.send('(game_revert)')
                    console.wait('checkpoint revert completed', timeout=12)
                    console.player_ready()
                    record['checkpoint_reverts_verified'] += 1
                    checkpoint_at = float('inf')
                if args.effects and now >= next_effect and now < started + args.seconds - 3:
                    console.command('(effect_new_on_object_marker "weapons\\frag grenade\\effects\\explosion" (list_get (players) 0) "")')
                    record['effect_commands_acknowledged'] += 1
                    next_effect = time.monotonic() + args.interval
                time.sleep(.05)
            process.wait(timeout=5)
        record['exit_code'] = process.returncode
        record['elapsed_seconds'] = time.monotonic() - started
        record['metrics'] = summarize(output / 'frames.csv')
        diagnostics = (output / 'game.log').read_text(errors='replace')
        if (output / 'data/debug.txt').exists():
            diagnostics += (output / 'data/debug.txt').read_text(errors='replace')
        if process.returncode or FAULT.search(diagnostics):
            raise RuntimeError('Game failed or reported a rendering/runtime fault')
        if record['elapsed_seconds'] < args.seconds - 3:
            raise RuntimeError('Game exited before the requested duration')
        if args.effects and not record['effect_commands_acknowledged']:
            raise RuntimeError('No stress effects were acknowledged')
        if args.checkpoints and not record['checkpoint_reverts_verified']:
            raise RuntimeError('No checkpoint revert was verified')
        expected_changes = max(0, math.ceil((args.seconds - 15) / args.cycle_seconds) - 1) if len(levels) > 1 else 0
        if record['map_changes_acknowledged'] < expected_changes:
            raise RuntimeError('The requested map-change workload did not complete')
        record['passed'] = True
    except (OSError, RuntimeError, TimeoutError, ValueError, subprocess.TimeoutExpired) as error:
        record['error'] = str(error)
    finally:
        if connection:
            connection.close()
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        record['elapsed_seconds'] = time.monotonic() - started
        if process:
            record['exit_code'] = process.returncode
        (output / 'validation.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, indent=2), flush=True)
    if not record['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
