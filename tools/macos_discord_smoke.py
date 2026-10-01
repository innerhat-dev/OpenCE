#!/usr/bin/env python3
"""Deliver a Discord invite through a private mock RPC socket into the real Mac game.

Requires a built Mac game and local maps. Uses isolated saves and loopback
signalling, without contacting the user's Discord client or changing activity.
"""
import argparse
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build/macos"
APPLICATION = "1553978809840050229"
SECRET = "0123456789abcdef0123456789abcdeffedcba9876543210fedcba9876543210"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, default=BUILD / "halo")
    parser.add_argument("--guest", type=Path, default=BUILD / "halo_guest.elf")
    args = parser.parse_args()
    (BUILD / "tests").mkdir(parents=True, exist_ok=True)
    out = Path(tempfile.mkdtemp(prefix="discord-game-", dir=BUILD / "tests"))
    (out / "config.toml").write_text(f'''[network]
online = true
address = "127.0.0.1"
join_from_clipboard = false
allow_upnp = false
signalling_brokers = "127.0.0.1:1"
stun_servers = ""
[discord]
application_id = "{APPLICATION}"
[debug]
hidden_window = true
exit_after = 10.0
''')
    with tempfile.TemporaryDirectory(prefix="halo-rpc-", dir="/tmp") as ipc:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
            server.bind(ipc + "/discord-ipc-0")
            server.listen(1)
            server.settimeout(15)
            environment = dict(os.environ, XDG_RUNTIME_DIR=ipc, HALO_SAVE_ROOT=str(out),
                               HALO_DATA_ROOT=str(ROOT / "assets"), HALO_NO_AUDIO="1",
                               HALO_VOLUME="0", HALO_WINDOWED="1", HALO_SCREEN_WIDTH="640",
                               HALO_WINDOW_SCALE="1")
            with (out / "game.log").open("w") as log:
                process = subprocess.Popen([str(args.executable.resolve()), str(args.guest.resolve()),
                                            f"discord-{APPLICATION}://"], cwd=ROOT,
                                           env=environment, stdout=log, stderr=subprocess.STDOUT)
                try:
                    connection, _ = server.accept()
                    with connection:
                        connection.settimeout(15)

                        def read_exact(size):
                            data = b""
                            while len(data) < size:
                                part = connection.recv(size - len(data))
                                if not part:
                                    raise RuntimeError("Game closed the RPC connection")
                                data += part
                            return data

                        def receive():
                            opcode, length = struct.unpack("<II", read_exact(8))
                            if length > 16384:
                                raise RuntimeError("Unexpected RPC frame size")
                            return opcode, json.loads(read_exact(length))

                        def send(data):
                            body = json.dumps(data).encode()
                            frame = struct.pack("<II", 1, len(body)) + body
                            connection.sendall(frame[:5])
                            connection.sendall(frame[5:])

                        opcode, handshake = receive()
                        assert opcode == 0 and handshake == {"v": 1, "client_id": APPLICATION}
                        send({"cmd": "DISPATCH", "evt": "READY", "data": {}})
                        opcode, subscription = receive()
                        assert opcode == 1 and subscription.get("cmd") == "SUBSCRIBE"
                        assert subscription.get("evt") == "ACTIVITY_JOIN"
                        send({"cmd": "SUBSCRIBE", "evt": None, "nonce": subscription["nonce"],
                              "data": {"evt": "ACTIVITY_JOIN"}})
                        send({"cmd": "DISPATCH", "evt": "ACTIVITY_JOIN", "data": {"secret": SECRET}})
                        opcode, activity = receive()
                        assert opcode == 1 and activity.get("cmd") == "SET_ACTIVITY"
                        assert activity["args"]["pid"] == process.pid
                        assert process.wait(timeout=20) == 0
                finally:
                    if process.poll() is None:
                        process.terminate()
                        process.wait(timeout=5)
    log_text = (out / "game.log").read_text(errors="replace")
    assert "Internet play: connected to Discord" in log_text
    assert "Internet play: accepted a Discord invite" in log_text
    # The longer key hash maps to a locally administered unicast identifier.
    assert "joining 0223456789ab's game" in log_text
    report = {"discord_launch_argument": True, "game_handshake": True,
              "invite_subscription": True, "native_pid": True,
              "invite_dispatched_to_game": True, "clean_exit": True}
    (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print("Real Halo: Discord launch, handshake, subscription and invite delivery passed")
    print("Evidence:", out)


if __name__ == "__main__":
    main()
