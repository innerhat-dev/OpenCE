#!/usr/bin/env python3
"""Exercise new sound-rule capability gates against the saved three-option guest.

Uses isolated profiles and two real processes on one Mac. It does not establish
two-machine networking or audible behavior. Do not overlap multiplayer runners.
"""
import argparse
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import socket

from macos_performance_compatibility import PeerPair, ROOT, BUILD, redact, wait_for

CASES = ('live_gate', 'join_gate', 'earlier_host')


def run_case(name, args, output):
    result = {'case': name, 'checks': {}}
    pair = PeerPair(output / name, args, result)
    checks = result['checks']
    try:
        pair.launch('host', legacy=name == 'earlier_host')
        invite = pair.invite()
        if name == 'join_gate':
            pair.native_command('host', 24)
            checks['silent_rules_enabled_before_join'] = pair.status('host')['flags'] == 24
            if not checks['silent_rules_enabled_before_join']:
                raise AssertionError('Host did not enable sound rules')
            pair.launch('client', legacy=True, invite=invite)
            wait_for(lambda: 'refusing client: this match enables practice options' in pair.log('host'),
                     'Host did not reject unsupported sound rules', 50)
            wait_for(lambda: 'unable to join game: reason= #0/rejection_code_version_too_old' in pair.log('client'),
                     'Earlier client did not receive the version rejection', 15)
            checks['server_rejected_earlier_peer_capability'] = True
            checks['earlier_client_received_version_too_old'] = True
            checks['earlier_client_never_entered_match'] = not re.search(r'network test: tick', pair.log('client'))
            checks['host_remains_enabled'] = pair.status('host')['flags'] == 24
        else:
            # Both versions know flags7. The new client's ordered 3/7/31
            # announcements must allow the earlier host to retain mask7.
            pair.native_command('host', 7)
            checks['existing_practice_enabled'] = pair.status('host')['flags'] == 7
            if not checks['existing_practice_enabled']:
                raise AssertionError('Host needs the complete timer pack')
            pair.launch('client', legacy=name == 'live_gate', invite=invite)
            initial = pair.both_playing()
            wait_for(lambda: pair.status('client')['flags'] == 7, 'Client did not receive existing rules')
            checks['both_versions_play_existing_practice'] = True
            if name == 'live_gate':
                for flags in (8, 16, 31):
                    refusal = pair.native_command('host', flags)
                    checks[f'flags_{flags}_refused'] = 'performance options change refused:' in refusal
                    checks[f'flags_{flags}_unchanged'] = (
                        pair.status('host')['flags'] == 7 and pair.status('client')['flags'] == 7)
                pair.native_command('host', 0)
                wait_for(lambda: pair.status('client')['flags'] == 0, 'Stock restoration did not reach client')
                checks['stock_restored_for_both_versions'] = pair.status('host')['flags'] == 0
            else:
                checks['earlier_host_accepted_new_client_capability'] = True
                pair.native_command('host', 3)
                wait_for(lambda: pair.status('client')['flags'] == 3, 'Earlier host live settings did not arrive')
                checks['earlier_host_live_settings_received'] = True
            pair.both_playing(after=initial)
            checks['session_continues'] = True
            result['initial_ticks'] = initial
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
    parser.add_argument('--legacy-guest', type=Path,
                        default=ROOT / 'build/pb-first-three/legacy-peer/halo_guest.elf')
    parser.add_argument('--executable', type=Path, default=BUILD / 'halo')
    parser.add_argument('--host-address')
    parser.add_argument('--cases', nargs='+', choices=CASES, default=list(CASES))
    args = parser.parse_args()
    args.timer_pack = True
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
    result = {'scope': 'two real instances on one Mac, sequential pairs',
              'map': 'bloodgulch', 'earlier_supported_flags': 7,
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
    print('Sound rule compatibility with earlier PB guest: PASS', flush=True)


if __name__ == '__main__':
    main()
