#!/usr/bin/env python3
"""Smoke each built community map in a fresh offline native Mac process.

This checks loading, player creation and rendered frames, not map fidelity,
every spawn, long play or multiplayer. It never changes an installed app or
terminates a process it did not launch. Hidden windows still require GPU access.
"""
import argparse
import csv
import json
import math
import os
from pathlib import Path
import re
import socket
import subprocess
import time

if __package__:
    from .community_maps import ROOT, NTSC_BUILD, MAX_CACHE_BYTES, TAG_ARENA_BYTES, NAME, cache_header, digest, output_directory
    from .macos_benchmark import Console, FAULT
else:
    from community_maps import ROOT, NTSC_BUILD, MAX_CACHE_BYTES, TAG_ARENA_BYTES, NAME, cache_header, digest, output_directory
    from macos_benchmark import Console, FAULT


def validate_import(record):
    name = record["id"]
    if not NAME.fullmatch(name):
        raise ValueError("Invalid map ID")
    source = Path(record["output"]).resolve(strict=True)
    header = cache_header(source)
    if (header["name"] != name or header["version"] != 5 or header["type"] != 1 or
            header["build"] != NTSC_BUILD or header["sha256"] != record["sha256"] or
            header["declared_bytes"] > MAX_CACHE_BYTES or header["tag_bytes"] > TAG_ARENA_BYTES):
        raise ValueError("Map differs from its v5 NTSC import manifest")
    return source


def stock_inputs(path, imports):
    stock = {}
    for source in sorted(path.resolve(strict=True).glob("*.map")):
        header = cache_header(source)
        if header["version"] != 5 or header["build"] != NTSC_BUILD:
            raise ValueError("Stock maps must be original Xbox NTSC 2276 caches")
        key = source.name.casefold()
        if key in stock:
            raise ValueError("Stock map filenames collide")
        stock[key] = (source.resolve(), header)
    expected = imports.get("stock", {}).get("inputs", {})
    if not {"ui", "a10", "bloodgulch"}.issubset(expected):
        raise ValueError("Import manifest must identify the original stock inputs")
    for name, header in expected.items():
        actual = stock.get((name + ".map").casefold())
        if actual is None or actual[1]["sha256"] != header["sha256"]:
            raise ValueError("Stock data differs from the import inputs: " + name)
    return stock


def read_frames(path):
    if not path.exists():
        return []
    with path.open() as stream:
        return list(csv.DictReader(stream))


def frame_summary(path, after_frame):
    active = [row for row in read_frames(path)
              if int(row["frame"]) > after_frame and int(row["draws"]) > 0]
    if len(active) < 30:
        raise ValueError("Fewer than 30 rendered frames after player creation")
    times = sorted(float(row["frame_ms"]) for row in active)
    if any(not math.isfinite(value) or value <= 0 for value in times):
        raise ValueError("Invalid frame timings")
    percentile = lambda q: times[int((len(times) - 1) * q)]
    return {"rendered_frames_after_player_ready": len(active),
            "median_frame_ms": percentile(.5), "p95_frame_ms": percentile(.95),
            "observed_mean_fps": 1000 * len(times) / sum(times),
            "max_footprint_mb": max(float(row["footprint_mb"]) for row in active)}


def prepare(folder, source, stock, port, args):
    maps, saves = folder / "data/maps", folder / "saves"
    maps.mkdir(parents=True)
    saves.mkdir()
    if source.name.casefold() in stock:
        raise ValueError("Community map would replace a stock map")
    for stock_source, _ in stock.values():
        (maps / stock_source.name).symlink_to(stock_source)
    (maps / source.name).symlink_to(source)
    (folder / "data/init.txt").write_text('game_variant slayer\nmap_name "' + source.stem + '"\n')
    screenshots = folder / "screenshots"
    if args.screenshot_every:
        screenshots.mkdir()
    (saves / "config.toml").write_text(f'''[network]
online = false
allow_upnp = false
join_from_clipboard = false
[discord]
application_id = ""
[update]
auto = false
[audio]
enabled = false
[display]
fullscreen = false
interpolation = true
vsync = true
direct_camera = false
high_res_hud = false
[game]
console_log = "all"
[debug]
telnet_console = true
telnet_console_port = {port}
hidden_window = {str(not args.visible).lower()}
gl_debug = true
exit_after = {float(args.seconds)}
test_input = {json.dumps("look:0" if args.look else "")}
screenshot_every = {args.screenshot_every}
screenshot_directory = {json.dumps(str(screenshots) if args.screenshot_every else "")}
''')
    environment = {key: value for key, value in os.environ.items() if not key.startswith("HALO_")}
    environment.update(HALO_DATA_ROOT=str(folder / "data"), HALO_SAVE_ROOT=str(saves),
                       HALO_PERF_LOG=str(folder / "frames.csv"), HALO_WINDOWED="1",
                       HALO_SCREEN_WIDTH="640")
    return environment


def smoke(record, folder, stock, args):
    result = {"id": record["id"], "map_sha256": record["sha256"], "passed": False,
              "player_spawn_acknowledged": False, "seconds_requested": args.seconds,
              "hidden_window": not args.visible, "test_input": "look:0" if args.look else ""}
    process = connection = None
    started = time.monotonic()
    folder.mkdir()
    try:
        source = validate_import(record)
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        environment = prepare(folder, source, stock, port, args)
        with (folder / "game.log").open("w") as log, (folder / "console.log").open("w") as transcript:
            started = time.monotonic()
            process = subprocess.Popen([args.host, args.guest], env=environment, cwd=ROOT,
                                       stdout=log, stderr=subprocess.STDOUT)
            deadline = started + min(args.load_timeout, args.seconds - 4)
            while time.monotonic() < deadline and process.poll() is None:
                try:
                    connection = socket.create_connection(("127.0.0.1", port), .25)
                    break
                except OSError:
                    time.sleep(.1)
            if connection is None:
                raise RuntimeError("Game console did not start")
            console = Console(connection, transcript)
            console.player_ready(timeout=max(.1, deadline - time.monotonic()))
            result["player_spawn_acknowledged"] = True
            console.send('(if (= (list_count (players)) 1) (print "smoke_exactly_one_player"))')
            console.wait("smoke_exactly_one_player", timeout=2)
            result["player_count"] = 1
            result["player_ready_seconds"] = time.monotonic() - started
            current = read_frames(folder / "frames.csv")
            after_frame = int(current[-1]["frame"]) if current else -1
            result["player_ready_frame"] = after_frame
            process.wait(timeout=max(1, args.seconds + 15 - (time.monotonic() - started)))
        result["metrics"] = frame_summary(folder / "frames.csv", after_frame)
        if process.returncode:
            raise RuntimeError("Game exited with code " + str(process.returncode))
        if time.monotonic() - started < args.seconds - 3:
            raise RuntimeError("Game exited before the requested duration")
        result["passed"] = True
    except (OSError, ValueError, RuntimeError, TimeoutError, subprocess.TimeoutExpired) as error:
        result["error"] = str(error)
    finally:
        if connection:
            connection.close()
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        result["elapsed_seconds"] = time.monotonic() - started
        result["exit_code"] = process.returncode if process else None
        diagnostics = "\n".join(path.read_text(errors="replace") for path in
                                (folder / "game.log", folder / "data/debug.txt", folder / "saves/halo.log")
                                if path.exists())
        result["runtime_faults"] = sorted(set(FAULT.findall(diagnostics)))
        if result["runtime_faults"]:
            result["passed"] = False
            result.setdefault("error", "Game reported a rendering/runtime fault")
        # Preserve relevant map-loading lines without treating ordinary warnings
        # as a failure or claiming that drawing alone proves visual correctness.
        result["map_load_log"] = [line for line in diagnostics.splitlines()
                                  if re.search(r"loaded map|loading map|precaching of map|init: map_name|failed.*map", line, re.I)][-12:]
        result["target_map_precache_logged"] = ("starting precaching of map '" + record["id"] + "'") in diagnostics
        if not result["target_map_precache_logged"]:
            result["passed"] = False
            result.setdefault("error", "Expected map was not logged as loading")
        result["warnings"] = sorted(set(line for line in diagnostics.splitlines()
                                        if re.search(r"warning|unsupported|race flag", line, re.I)))
        (folder / "validation.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--imports", type=Path, required=True, help="build.json, or its parent import directory")
    parser.add_argument("--output", type=Path, required=True, help="Fresh child directory under build/")
    parser.add_argument("--stock-maps", type=Path, default=ROOT / "assets/maps")
    parser.add_argument("--host", type=Path, default=ROOT / "build/macos/halo")
    parser.add_argument("--guest", type=Path, default=ROOT / "build/macos/halo_guest.elf")
    parser.add_argument("--map", action="append", dest="maps", help="Limit to selected built map IDs; repeatable")
    parser.add_argument("--seconds", type=int, default=20, help="Autoexit after window creation (minimum 12)")
    parser.add_argument("--load-timeout", type=float, default=15)
    parser.add_argument("--visible", action="store_true", help="Show windows; hidden by default")
    parser.add_argument("--look", action="store_true", help="Turn camera without walking or firing")
    parser.add_argument("--screenshot-every", type=int, default=0)
    args = parser.parse_args()
    if args.seconds < 12 or args.load_timeout <= 0 or args.screenshot_every < 0:
        parser.error("Use at least 12 seconds, a positive load timeout and nonnegative screenshot interval")
    manifest_path = args.imports / "build.json" if args.imports.is_dir() else args.imports
    imports = json.loads(manifest_path.read_text())
    if imports.get("profile") != "stock-xbox-ntsc" or not imports.get("maps"):
        parser.error("Use a nonempty stock-Xbox NTSC import manifest")
    selected = set(args.maps) if args.maps else {record["id"] for record in imports["maps"]}
    records = [record for record in imports["maps"] if record["id"] in selected]
    if selected != {record["id"] for record in records}:
        parser.error("A selected map is absent from the import manifest")
    names = [record["id"] for record in records]
    if any(not NAME.fullmatch(name) for name in names) or len({name.casefold() for name in names}) != len(names):
        parser.error("Import map IDs must be safe and unique")
    args.host = args.host.resolve(strict=True)
    args.guest = args.guest.resolve(strict=True)
    stock = stock_inputs(args.stock_maps, imports)
    output = output_directory(args.output)
    result = {"scope": "isolated offline map-load/player/render smoke; not fidelity or multiplayer certification",
              "imports": str(manifest_path.resolve()), "imports_sha256": digest(manifest_path),
              "host_sha256": digest(args.host), "guest_sha256": digest(args.guest),
              "tool_sha256": digest(Path(__file__)), "maps": [], "passed": False}
    for record in records:
        item = smoke(record, output / record["id"], stock, args)
        result["maps"].append(item)
        (output / "validation.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps({"id": item["id"], "passed": item["passed"],
                          "error": item.get("error"), "metrics": item.get("metrics")}), flush=True)
    result["passed"] = all(item["passed"] for item in result["maps"])
    result["passed_count"] = sum(item["passed"] for item in result["maps"])
    result["failed_count"] = len(result["maps"]) - result["passed_count"]
    (output / "validation.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"output": str(output), "passed": result["passed"],
                      "passed_count": result["passed_count"], "failed_count": result["failed_count"]}), flush=True)
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
