#!/usr/bin/env python3
"""Stage a local Mac pilot using original data, reviewed v5 imports and separate saves."""
import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import subprocess

if __package__:
    from .community_maps import ROOT, NTSC_BUILD, MAX_CACHE_BYTES, TAG_ARENA_BYTES, cache_header, digest, output_directory
    from .macos_build import APP_BUILD, APP_VERSION, package_into
else:
    from community_maps import ROOT, NTSC_BUILD, MAX_CACHE_BYTES, TAG_ARENA_BYTES, cache_header, digest, output_directory
    from macos_build import APP_BUILD, APP_VERSION, package_into


def validate_stock_inputs(imports, caches):
    """Keep candidate stock data consistent with the caches used for extraction."""
    inputs = imports.get("stock", {}).get("inputs", {})
    if not {"ui", "a10", "bloodgulch"}.issubset(inputs):
        raise ValueError("The import manifest must record its original stock cache inputs")
    for name, expected in inputs.items():
        candidate = caches.get((name + ".map").casefold())
        if candidate is None or candidate[1]["sha256"] != expected.get("sha256"):
            raise ValueError("Stock cache differs from the import build manifest: " + name)


def write_launcher(path, data, saves, parent_levels=1):
    parent = ":h" * parent_levels
    path.write_text('''#!/bin/zsh
set -e
pilot_dir=${0:A''' + parent + '''}
export HALO_DATA_ROOT="$pilot_dir/''' + data + '''"
export HALO_SAVE_ROOT="$pilot_dir/''' + saves + '''"
export HALO_WINDOWED=1
export HALO_SCREEN_WIDTH=640
exec "$pilot_dir/Halo Xbox Map Pilot.app/Contents/MacOS/halo"
''')
    path.chmod(0o755)


def write_practice_launchers(out, imports, caches, configuration):
    """Give every imported map a human-controlled, offline, one-player launch."""
    launchers = out / "Practice Maps"
    launchers.mkdir()
    offline = '''
[network]
online = false
allow_upnp = false
join_from_clipboard = false
[discord]
application_id = ""
[update]
auto = false
[debug]
network_test = ""
test_input = ""
exit_after = 0.0
'''
    result = {}
    for record in imports["maps"]:
        name = record["id"]
        practice = out / "practice" / name
        maps, saves = practice / "data/maps", practice / "saves"
        maps.mkdir(parents=True)
        saves.mkdir()
        # A real maps directory is needed by the native game-data picker.
        for source, _ in caches.values():
            (maps / source.name).symlink_to(source)
        (practice / "data/init.txt").write_text("game_variant slayer\nmap_name " + name + "\n")
        (saves / "config.toml").write_text(configuration + offline)
        launcher = launchers / (name + ".command")
        write_launcher(launcher, "practice/" + name + "/data", "practice/" + name + "/saves", 2)
        result[name] = str(launcher)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--imports", type=Path, required=True, help="Import output containing build.json")
    parser.add_argument("--stock-maps", type=Path, default=ROOT / "assets/maps")
    parser.add_argument("--output", type=Path, required=True, help="Fresh child directory under build/")
    parser.add_argument("--high-refresh", action="store_true",
                        help="Enable interpolated rendering at the display refresh rate; simulation stays 30 Hz")
    parser.add_argument("--practice-launchers", action="store_true",
                        help="Also create offline, one-player launchers for each imported map")
    args = parser.parse_args()
    imports = json.loads((args.imports / "build.json").read_text())
    if imports["profile"] != "stock-xbox-ntsc" or not imports["maps"]:
        raise ValueError("Use a reviewed stock-Xbox NTSC import")
    caches = {}
    for source in sorted(args.stock_maps.resolve(strict=True).glob("*.map")):
        h = cache_header(source)
        if h["version"] != 5 or h["build"] != NTSC_BUILD:
            raise ValueError("The stock data must be one original Xbox NTSC 2276 set")
        if source.name.casefold() in caches:
            raise ValueError("Stock filenames differ only in capitalization")
        caches[source.name.casefold()] = (source, h)
    if not {"ui.map", "a10.map", "bloodgulch.map"}.issubset(caches):
        raise ValueError("The pilot requires the stock menu, opening campaign and Blood Gulch")
    validate_stock_inputs(imports, caches)
    for record in imports["maps"]:
        source = Path(record["output"]).resolve(strict=True)
        h = cache_header(source)
        if (h["version"] != 5 or h["type"] != 1 or h["build"] != NTSC_BUILD or
                h["sha256"] != record["sha256"] or h["name"] != record["id"] or
                h["declared_bytes"] > MAX_CACHE_BYTES or h["tag_bytes"] > TAG_ARENA_BYTES):
            raise ValueError("Imported cache differs from its v5 NTSC build manifest")
        if source.name.casefold() in caches:
            raise ValueError("A community map would replace a stock map")
        caches[source.name.casefold()] = (source, h)
    out = output_directory(args.output)
    maps = out / "data/maps"
    maps.mkdir(parents=True)
    for source, _ in caches.values():
        (maps / source.name).symlink_to(source)
    saves = out / "saves"
    saves.mkdir()
    profile = ROOT / "port/macos/profiles/xbox-ntsc.toml"
    configuration = profile.read_text()
    if args.high_refresh:
        configuration = configuration.replace("interpolation = false", "interpolation = true")
        configuration = "# High-refresh play profile; the simulation remains 30 Hz.\n" + configuration
    (saves / "config.toml").write_text(configuration)
    app = out / "Halo Xbox Map Pilot.app"
    package_into(app, out / "data", sign_identity="-", release=False,
                 version=APP_VERSION, build=APP_BUILD)
    # Isolate every candidate from the installed app and earlier pilot bundles.
    info_path = app / "Contents/Info.plist"
    with info_path.open("rb") as stream:
        info = plistlib.load(stream)
    bundle_id = "com.pfista.halo.community-map-pilot.c" + hashlib.sha256(str(out).encode()).hexdigest()[:12]
    info.update(CFBundleIdentifier=bundle_id,
                CFBundleName="Halo Xbox Map Pilot", CFBundleDisplayName="Halo Xbox Map Pilot")
    with info_path.open("wb") as stream:
        plistlib.dump(info, stream)
    subprocess.run(["codesign", "--force", "--sign", "-", "--entitlements",
                    str(ROOT / "port/macos/host.entitlements"), str(app)], check=True)
    subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app)], check=True)
    launcher = out / "Play Xbox Map Pilot.command"
    write_launcher(launcher, "data", "saves")
    practice = write_practice_launchers(out, imports, caches, configuration) if args.practice_launchers else {}
    record = {"scope": "local experimental pilot; not installed or published",
              "launcher": str(launcher), "app": str(app),
              "bundle_identifier": bundle_id,
              "reference_profile_sha256": digest(profile),
              "launch_profile_sha256": digest(saves / "config.toml"),
              "high_refresh": args.high_refresh,
              "practice_launchers": practice,
              "guest_sha256": digest(app / "Contents/Resources/halo_guest.elf"),
              "host_sha256": digest(app / "Contents/MacOS/halo"),
              "maps": {name: h for name, (_, h) in caches.items()},
              "community_maps": [m["id"] for m in imports["maps"]]}
    (out / "candidate.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps({"launcher": str(launcher), "community_maps": record["community_maps"]}, indent=2))


if __name__ == "__main__":
    main()
