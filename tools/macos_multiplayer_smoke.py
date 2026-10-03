#!/usr/bin/env python3
"""Run two real Mac game instances through LAN or an encrypted invite.

Uses isolated saves and the upstream scripted network test. This checks a
single Mac; an internet/NAT test still needs a second physical network.
"""
import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build/macos"


def prepare(folder, role, mode, seconds, host_address, client_address, variants, score,
            map_name="bloodgulch", map_source=None, reference_profile=False, screenshot_every=0):
    saves = folder / "saves"
    saves.mkdir(parents=True, exist_ok=True)
    data = folder / "data"
    data.mkdir()
    (data / "maps").mkdir()
    for path in (ROOT / "assets/maps").iterdir():
        if path.is_file():
            (data / "maps" / path.name).symlink_to(path.resolve())
    if map_source:
        target = data / "maps" / (map_name + ".map")
        if target.exists():
            raise ValueError("A custom map must have its own filename; do not replace a stock map")
        target.symlink_to(map_source)
    # Use configured addresses only: Linux's arbitrary 127.x loopback
    # aliases fail on Darwin. Invite mode supports LAN plus 127.0.0.1.
    address = host_address if role == "host" else client_address
    other_address = client_address if role == "host" else host_address
    broadcast = other_address if mode == "lan" else address
    config = f'''[network]
address = "{address}"
broadcast = "{broadcast}"
online = {str(mode == "invite").lower()}
allow_upnp = false
join_from_clipboard = false

[discord]
application_id = ""

[debug]
hidden_window = true
network_test = "{'host:' + map_name + ':' + variants if role == 'host' else 'join'}"
network_test_start = 20.0
network_test_score = {score}
network_test_shoot = 3.0
network_test_kill = 12.0
test_input = "bot:{17 if role == 'host' else 42}"
exit_after = {seconds}.0
'''
    if screenshot_every:
        frames = folder / "frames"
        frames.mkdir()
        config += 'screenshot_directory = ' + json.dumps(str(frames)) + '\n'
        config += 'screenshot_every = ' + str(screenshot_every) + '\n'
    if reference_profile:
        config += '\n[display]\ninterpolation = false\ndirect_camera = false\nhigh_res_hud = false\n'
    (saves / "config.toml").write_text(config)
    # All are existing runtime overrides. Personal saves and settings are unused.
    environment = dict(os.environ, HALO_DATA_ROOT=str(data),
                       HALO_SAVE_ROOT=str(saves), HALO_WINDOWED="1", HALO_SCREEN_WIDTH="640",
                       HALO_WINDOW_SCALE="1", HALO_VOLUME="0", HALO_NO_AUDIO="1")
    return environment


def read_log(folder):
    # GUI launches keep native/guest stderr in their isolated save directory.
    return ''.join(path.read_text(errors="replace") for path in
                   (folder / "game.log", folder / "saves/halo.log") if path.exists())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("lan", "invite"), default="invite")
    parser.add_argument("--seconds", type=int, default=65)
    parser.add_argument("--variants", default="slayer",
                        help="Comma-separated upstream variants; multiple entries test consecutive matches")
    parser.add_argument("--score", type=int, default=0,
                        help="Score to win; use a small score for consecutive matches (0 keeps the default)")
    parser.add_argument("--map", default="bloodgulch", help="Stock or custom cache name (without .map)")
    parser.add_argument("--map-source", type=Path, help="Converted v5 cache; linked into isolated test data")
    parser.add_argument("--reference-profile", action="store_true", help="Original HUD, camera and 30 FPS presentation")
    parser.add_argument("--screenshot-every", type=int, default=0, help="Capture a frame every N simulation ticks")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--guest", type=Path, default=BUILD / "halo_guest.elf")
    parser.add_argument("--executable", type=Path, default=BUILD / "halo",
                        help="Native executable, including one inside a candidate app bundle")
    parser.add_argument("--native-menu", action="store_true",
                        help="Use the app bundle's guest and native menus (requires --executable inside the app)")
    parser.add_argument("--download-client", action="store_true",
                        help="Give only the host --map-source; opt the isolated native client into configured HTTPS downloads")
    parser.add_argument("--host-address", help="A configured local IPv4 address, other than 127.0.0.1")
    parser.add_argument("--client-address", help="Another configured local IPv4 address")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_ -]{1,31}", args.map) or args.screenshot_every < 0:
        parser.error("Use a safe cache name of at most 31 characters and a nonnegative screenshot interval")
    map_source = args.map_source.resolve(strict=True) if args.map_source else None
    if map_source:
        from community_maps import cache_header
        header = cache_header(map_source)
        if header['version'] != 5 or header['type'] != 1 or header['name'] != args.map:
            parser.error("--map-source must be an Xbox v5 multiplayer cache matching --map")
        if (ROOT / "assets/maps" / map_source.name).exists():
            parser.error("The custom map filename collides with a stock map")
    if args.native_menu and args.executable.parent.name != 'MacOS':
        parser.error('--native-menu requires an executable inside the candidate app bundle')
    if args.download_client and (not args.native_menu or not map_source):
        parser.error('--download-client requires --native-menu and an explicit --map-source')
    if args.score < 0 or not re.fullmatch(r"[a-zA-Z0-9_ -]+(?:,[a-zA-Z0-9_ -]+)*", args.variants):
        parser.error("Use non-empty variant names and a nonnegative score")
    host_address = args.host_address
    if not host_address:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as route:
            # UDP connect selects a local route without transmitting packets.
            route.connect(("192.0.2.1", 9))
            host_address = route.getsockname()[0]
    if host_address == "127.0.0.1":
        raise SystemExit("This test requires a LAN IPv4 address and loopback.")
    client_address = args.client_address
    if not client_address and args.mode == "lan":
        # Halo uses 127.0.0.1 for its own host. A direct LAN test needs
        # another configured non-loopback address; a VPN interface also
        # works. Do not add system interface aliases just for this test.
        interfaces = subprocess.check_output(["ifconfig"], text=True)
        candidates = re.findall(r"\binet (\d+\.\d+\.\d+\.\d+)\b", interfaces)
        client_address = next((a for a in candidates if a != host_address and
                               not ipaddress.IPv4Address(a).is_loopback), None)
        if not client_address:
            raise SystemExit("LAN mode needs a second configured IPv4 address; use invite mode otherwise.")
    client_address = str(ipaddress.IPv4Address(client_address or "127.0.0.1"))
    host_address = str(ipaddress.IPv4Address(host_address))
    if client_address == host_address or (args.mode == "lan" and
                                         ipaddress.IPv4Address(client_address).is_loopback):
        raise SystemExit("LAN mode needs two distinct configured non-loopback IPv4 addresses.")
    out = args.output.resolve()
    if out.exists():
        raise SystemExit("Use a new output directory to preserve previous evidence.")
    out.mkdir(parents=True)
    processes, streams, folders = {}, [], {}
    started = time.monotonic()
    try:
        for role in ("host", "client"):
            folder = out / role
            folders[role] = folder
            environment = prepare(folder, role, args.mode, args.seconds, host_address, client_address,
                                  args.variants, args.score, args.map,
                                  None if args.download_client and role == "client" else map_source,
                                  args.reference_profile, args.screenshot_every)
            if args.download_client and role == "client":
                (folder / "saves/macos-settings.json").write_text(json.dumps({"community_downloads": True}))
            command = [str(args.executable.resolve())]
            if not args.native_menu:
                command.append(str(args.guest.resolve()))
            if role == "client" and args.mode == "invite":
                deadline = time.monotonic() + 40
                invite = None
                while time.monotonic() < deadline:
                    match = re.search(r"halo://join/[0-9a-fA-F]{64}(?![0-9a-fA-F])", read_log(folders["host"]))
                    if match:
                        invite = match[0]
                        break
                    if processes["host"].poll() is not None:
                        break
                    time.sleep(.2)
                if not invite:
                    raise RuntimeError("Host did not produce an invite; inspect host/game.log")
                command.append(invite)
                print("Host generated invite; launching the joining game", flush=True)
            stream = (folder / "game.log").open("w")
            streams.append(stream)
            processes[role] = subprocess.Popen(command, cwd=ROOT, env=environment,
                                               stdout=stream, stderr=subprocess.STDOUT)
            print(f"Started {role} ({args.mode})", flush=True)
        deadline = started + args.seconds + 60
        while any(p.poll() is None for p in processes.values()) and time.monotonic() < deadline:
            time.sleep(.2)
        codes = {role: process.poll() for role, process in processes.items()}
        logs = {role: read_log(folder) for role, folder in folders.items()}
        diagnostics = {role: log + (folders[role] / "data/debug.txt").read_text(errors="replace")
                       if (folders[role] / "data/debug.txt").exists() else log
                       for role, log in logs.items()}
        ticks = {role: re.findall(r"network test: tick[^\n]+", log) for role, log in logs.items()}
        checks = {
            "clean_exit": all(code == 0 for code in codes.values()),
            "both_simulated_multiple_players": all(any(len(set(re.findall(r"player (\d+):", t))) >= 2
                                                       for t in lines) for lines in ticks.values()),
            "client_received_updates": any(re.search(r"received [1-9]\d*", t) for t in ticks["client"]),
            "host_received_client_updates": any(re.search(r"received [1-9]\d*", t) for t in ticks["host"]),
            "no_assertion_or_fault": all(not re.search(r"ASSERTION FAILED|EXCEPTION halt in|guest abort|SIGSEGV|signal 11|signal 10",
                                                        log, re.I) for log in diagnostics.values()),
        }
        if args.mode == "invite":
            checks["encrypted_peer_connected"] = all("Internet play: connected to" in log for log in logs.values())
        if args.download_client:
            managed = folders["client"] / "saves/Community Maps/maps" / (args.map.lower() + ".map")
            checks["client_started_without_custom_map"] = not (folders["client"] / "data/maps" / (args.map + ".map")).exists()
            checks["client_download_matches_host"] = False
            if managed.is_file():
                with managed.open("rb") as downloaded, map_source.open("rb") as original:
                    checks["client_download_matches_host"] = hashlib.file_digest(downloaded, "sha256").digest() == hashlib.file_digest(original, "sha256").digest()
        expected_matches = len(args.variants.split(","))
        if expected_matches > 1:
            checks["host_created_all_matches"] = len(re.findall(r"network test: game \d+,", logs["host"])) >= expected_matches
            restarts = {}
            for role, lines in ticks.items():
                times = [int(re.search(r"tick (\d+)", line)[1]) for line in lines]
                restarts[role] = sum(current < previous for previous, current in zip(times, times[1:]))
            checks["both_played_consecutive_matches"] = all(count >= expected_matches - 1 for count in restarts.values())
        result = {"mode": args.mode, "scope": "two real instances on one Mac",
                  "map": args.map, "map_sha256": hashlib.sha256(map_source.read_bytes()).hexdigest() if map_source else None,
                  "reference_profile": args.reference_profile,
                  "native_menu": args.native_menu,
                  "download_client": args.download_client,
                  "variants": args.variants, "score_to_win": args.score,
                  "exit_codes": codes, "logged_ticks": {k: len(v) for k, v in ticks.items()},
                  "checks": checks, "passed": all(checks.values())}
        (out / "validation.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2), flush=True)
        if not result["passed"]:
            raise SystemExit(1)
    finally:
        for process in processes.values():
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        for stream in streams:
            stream.close()


if __name__ == "__main__":
    main()
