#!/usr/bin/env python3
"""Run two real Mac game instances through LAN or an encrypted invite.

Uses isolated saves and the upstream scripted network test. This checks a
single Mac; an internet/NAT test still needs a second physical network.
"""
import argparse
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build/macos"


def prepare(folder, role, mode, seconds, host_address):
    saves = folder / "saves"
    saves.mkdir(parents=True, exist_ok=True)
    data = folder / "data"
    data.mkdir()
    (data / "maps").symlink_to(ROOT / "assets/maps", target_is_directory=True)
    # Darwin binds only configured loopback addresses. Use its actual LAN
    # address and 127.0.0.1; Linux's arbitrary 127.x aliases fail on Mac.
    address = host_address if role == "host" else "127.0.0.1"
    broadcast = host_address if mode == "lan" else address
    config = f'''[network]
address = "{address}"
broadcast = "{broadcast}"
netcode = "distributed"
online = {str(mode == "invite").lower()}
allow_upnp = false
join_from_clipboard = false

[debug]
network_test = "{'host:bloodgulch' if role == 'host' else 'join'}"
network_test_start = 20.0
network_test_shoot = 3.0
network_test_kill = 12.0
test_input = "bot:{17 if role == 'host' else 42}"
exit_after = {seconds}.0
'''
    (saves / "config.toml").write_text(config)
    # All are existing runtime overrides. Personal saves and settings are unused.
    environment = dict(os.environ, HALO_DATA_ROOT=str(data),
                       HALO_SAVE_ROOT=str(saves), HALO_WINDOWED="1", HALO_SCREEN_WIDTH="640",
                       HALO_WINDOW_SCALE="1", HALO_VOLUME="0", HALO_NO_AUDIO="1")
    return environment


def read_log(folder):
    return (folder / "game.log").read_text(errors="replace")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("lan", "invite"), default="invite")
    parser.add_argument("--seconds", type=int, default=65)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--guest", type=Path, default=BUILD / "halo_guest.elf")
    parser.add_argument("--host-address", help="A configured local IPv4 address, other than 127.0.0.1")
    args = parser.parse_args()
    host_address = args.host_address
    if not host_address:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as route:
            # UDP connect selects a local route without transmitting packets.
            route.connect(("192.0.2.1", 9))
            host_address = route.getsockname()[0]
    if host_address == "127.0.0.1":
        raise SystemExit("This test requires a LAN IPv4 address and loopback.")
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
            environment = prepare(folder, role, args.mode, args.seconds, host_address)
            command = [str(BUILD / "halo"), str(args.guest.resolve())]
            if role == "client" and args.mode == "invite":
                deadline = time.monotonic() + 40
                invite = None
                while time.monotonic() < deadline:
                    match = re.search(r"halo://join/[0-9a-fA-F]{44}", read_log(folders["host"]))
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
        result = {"mode": args.mode, "scope": "two real instances on one Mac",
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
