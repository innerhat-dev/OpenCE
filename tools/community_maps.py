#!/usr/bin/env python3
"""Inventory community caches or build reviewed map imports with stock NTSC tags.

Only explicitly selected, locally built Invader tools execute. Package files
are data inputs; its executables, startup files and build scripts are unused.
All generated tags, caches and reports stay in a fresh ignored build directory.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "port/maps/jukkis-beta3.json"
NTSC_BUILD = "01.10.12.2276"
MAX_CACHE_BYTES = 128 * 1024 * 1024
TAG_ARENA_BYTES = 22 * 1024 * 1024
NAME = re.compile(r"[A-Za-z0-9_ -]{1,31}\Z")
SCENARIO = re.compile(r"[A-Za-z0-9_ /-]+\Z")


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def cache_header(path):
    with Path(path).open("rb") as stream:
        data = stream.read(2048)
    if len(data) != 2048 or data[:4] != b"daeh" or data[-4:] != b"toof":
        raise ValueError(f"Invalid cache header: {path}")
    def string(offset):
        value = data[offset:offset + 32]
        if b"\0" not in value:
            raise ValueError(f"Unterminated cache string: {path}")
        return value.split(b"\0", 1)[0].decode("ascii")
    name = string(32)
    if not NAME.fullmatch(name) or name.casefold() != Path(path).stem.casefold():
        raise ValueError(f"Cache name does not match its safe filename: {path}")
    return {"name": name, "version": struct.unpack_from("<I", data, 4)[0],
            "declared_bytes": struct.unpack_from("<I", data, 8)[0],
            "tag_bytes": struct.unpack_from("<I", data, 20)[0],
            "build": string(64), "type": struct.unpack_from("<H", data, 96)[0],
            "file_bytes": Path(path).stat().st_size, "sha256": digest(path)}


def output_directory(path):
    path = path.resolve()
    if not path.is_relative_to((ROOT / "build").resolve()) or path == ROOT / "build":
        raise ValueError("Use a new child directory under this repo's ignored build/")
    path.mkdir(parents=True, exist_ok=False)
    return path


def safe_tag(root, relative):
    relative = relative.replace("\\", "/")
    if Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError(f"Unsafe source tag path: {relative}")
    path = (root / relative).resolve(strict=True)
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError(f"Tag dependency escapes the source tree: {relative}")
    return path


def inventory(package, stock_maps):
    stock = {p.stem.casefold(): cache_header(p) for p in sorted(stock_maps.glob("*.map"))}
    scenarios = {}
    tags = package / "tags"
    for p in sorted(tags.rglob("*.scenario")):
        scenarios.setdefault(p.stem.casefold(), []).append(p.relative_to(tags).with_suffix("").as_posix())
    maps = []
    for p in sorted((package / "maps").glob("*.map")):
        header = cache_header(p)
        name = header["name"]
        collision = name.casefold() in stock
        maps.append({"source": p.name, **header, "stock_filename_collision": collision,
                     "import_id": "h1pb_" + name if collision else name,
                     "source_scenarios": scenarios.get(name.casefold(), []),
                     "status": "not converted"})
    if not maps:
        raise ValueError("The package has no maps/*.map files")
    return {"package": json.loads(POLICY.read_text())["package"],
            "stock_maps": stock, "maps": maps, "map_count": len(maps),
            "source_only": True, "downloaded_executables_run": False}


class Invader:
    def __init__(self, binary, manifest, logs):
        self.binary = binary.resolve(strict=True)
        self.logs = logs
        self.sequence = 0
        self.provenance = {}
        pinned = json.loads(manifest.read_text())
        if pinned["invader_commit"] != json.loads(POLICY.read_text())["invader_commit"]:
            raise ValueError("Invader source revision differs from the reviewed import toolchain")
        for name in ("extract", "dependency", "convert", "refactor", "edit", "bludgeon", "build"):
            p = self.binary / ("invader-" + name)
            actual = digest(p)
            if actual != pinned["binaries"][name]["sha256"]:
                raise ValueError("Invader binary differs from its source manifest: " + name)
            self.provenance[name] = actual
        self.commit = pinned["invader_commit"]

    def run(self, tool, *args):
        self.sequence += 1
        command = [str(self.binary / ("invader-" + tool)), *map(str, args)]
        result = subprocess.run(command, capture_output=True, text=True)
        log = self.logs / f"{self.sequence:04d}-{tool}.log"
        log.write_text(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError(f"invader-{tool} failed ({result.returncode}); see {log}")
        return result.stdout.strip()

    def get(self, tags, tag, field):
        return self.run("edit", "-t", tags, "-G", field, tag)

    def count(self, tags, tag, field):
        return int(self.run("edit", "-t", tags, "-C", field, tag))


def prepare_stock(tool, maps, destination):
    destination.mkdir()
    inputs = {}
    # Blood Gulch supplies the multiplayer globals/player/weapons first;
    # campaign and UI data then fill in missing pause/menu dependencies.
    for name in ("bloodgulch", "a10", "ui"):
        source = maps / (name + ".map")
        h = cache_header(source)
        if h["version"] != 5 or h["build"] != NTSC_BUILD:
            raise ValueError("Use one original Xbox USA NTSC 2276 data set")
        inputs[name] = h
        tool.run("extract", "-t", destination, source)
    patches = []
    for p in sorted(destination.rglob("*.weapon")):
        tag = p.relative_to(destination).as_posix()
        value = tool.get(destination, tag, "actor_firing_parameters")
        if value and not value.startswith("."):
            before = digest(p)
            tool.run("edit", "-t", destination, "-S", "actor_firing_parameters", "", tag)
            patches.append({"tag": tag, "field": "actor_firing_parameters", "before": value,
                            "after": "no AI firing dependency", "sha256_before": before,
                            "sha256_after": digest(p)})
    # Source rebuilding validates fields the retail cache leaves unused.
    # Keep these narrowly identified visual metadata repairs auditable.
    flare = "vehicles/scorpion/headlights scorpion.lens_flare"
    index = tool.get(destination, flare, "reflections[0].bitmap_index")
    if index != "2":
        raise ValueError("Unexpected stock Scorpion flare metadata; review instead of applying the 2276 repair")
    before = digest(destination / flare)
    tool.run("edit", "-t", destination, "-S", "reflections[0].bitmap_index", "0", flare)
    patches.append({"tag": flare, "field": "reflections[0].bitmap_index", "before": 2,
                    "after": 0, "sha256_before": before, "sha256_after": digest(destination / flare)})
    effects = {p.relative_to(destination).as_posix(): digest(p) for p in destination.rglob("*.effect")}
    tool.run("bludgeon", "-t", destination, "-T", "invalid-indices", "-b", "*.effect")
    repaired = [name for name, sha in effects.items() if digest(destination / name) != sha]
    if repaired != ["vehicles/scorpion/secondary fire bullet.effect"]:
        raise ValueError(f"Unexpected stock effect repairs require review: {repaired}")
    for name in repaired:
        patches.append({"tag": name, "repair": "invalid local effect location index",
                        "sha256_before": effects[name], "sha256_after": digest(destination / name)})
    return {"inputs": inputs, "compatibility_patches": patches,
            "scope": "multiplayer maps without combat AI; player weapon fields are unchanged"}


def resolved_stock_substitutions(tool, stock, tags, scenario_tag):
    """Record reachable copied tags overridden by the compiler's stock-first lookup."""
    dependencies = [scenario_tag, *tool.run("dependency", "-r", "-t", stock,
                                            "-t", tags, scenario_tag).splitlines()]
    substitutions = {}
    for relative in dict.fromkeys(p.strip().replace("\\", "/") for p in dependencies):
        if (stock / relative).is_file() and (tags / relative).is_file():
            substitutions[relative] = digest(safe_tag(stock, relative))
    return substitutions


def validate_map_content_priority(stock, tags, scenario, source_tag):
    """Do not silently replace authored level content through stock-first lookup."""
    level = Path(scenario).parent
    collisions = []
    for path in sorted(tags.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(tags)
        # An aliased source scenario remains only as a provenance copy; the
        # compiled scenario's identity is checked separately before copying.
        if relative.as_posix() == source_tag and relative != Path(scenario + ".scenario"):
            continue
        if (relative.is_relative_to(level) or path.suffix == ".scenario_structure_bsp") and (stock / relative).is_file():
            collisions.append(relative.as_posix())
    if collisions:
        raise ValueError("Stock lookup would replace authored map content; review a scoped override: " +
                         ", ".join(collisions))


def convert_extended_shaders(tool, tags):
    """Convert copied PC-only Chicago shaders using their authored four-stage path."""
    source_group = "shader_transparent_chicago_extended"
    target_group = "shader_transparent_chicago"
    conversions = []
    for source in sorted(tags.rglob("*." + source_group)):
        tag = source.relative_to(tags).as_posix()
        target = source.with_suffix("." + target_group)
        if target.exists():
            raise ValueError("Chicago shader conversion would overwrite an existing tag: " + tag)
        layers = tool.count(tags, tag, "maps_4_stage")
        if not 1 <= layers <= 4:
            raise ValueError("Review unsupported Chicago shader four-stage layer count: " + tag)
        conversions.append({"source_tag": tag, "converted_tag": target.relative_to(tags).as_posix(),
                            "sha256_before": digest(source), "four_stage_layers": layers,
                            "two_stage_fallback_layers": tool.count(tags, tag, "maps_2_stage")})
    if conversions:
        tool.run("convert", "-t", tags, "-g", source_group, target_group, "-b", "*." + source_group)
        tool.run("refactor", "-t", tags, "-M", "no-move", "-g", source_group, target_group)
        for record in conversions:
            record["sha256_after"] = digest(tags / record["converted_tag"])
    return conversions


def build_map(tool, spec, package, stock, output):
    import_id = spec["id"]
    if not NAME.fullmatch(import_id):
        raise ValueError("Invalid import map ID")
    scenario = spec["scenario"]
    if (not SCENARIO.fullmatch(scenario) or Path(scenario).is_absolute() or
            ".." in scenario.split("/") or Path(scenario).as_posix() != scenario):
        raise ValueError("Invalid source scenario path")
    compiled_scenario = str(Path(scenario).with_name(import_id))
    source_tag, tag = scenario + ".scenario", compiled_scenario + ".scenario"
    # Stock-first dependency lookup must never substitute a retail scenario for
    # the imported map. Compile collision maps under a separate scenario identity.
    if (stock / tag).exists():
        raise ValueError("The import scenario would resolve to stock data; use a separate map ID")
    folder = output / import_id
    tags, data, maps = folder / "tags", folder / "data", folder / "maps"
    for path in (tags, data, maps): path.mkdir(parents=True)
    source_tags = package / "tags"
    if digest(safe_tag(source_tags, source_tag)) != spec["scenario_sha256"]:
        raise ValueError("Scenario differs from the reviewed script policy: " + spec["id"])
    source_list = [source_tag, *tool.run("dependency", "-r", "-t", source_tags, source_tag).splitlines()]
    provenance = {}
    for relative in dict.fromkeys(p.strip().replace("\\", "/") for p in source_list):
        source = safe_tag(source_tags, relative)
        provenance[relative] = digest(source)
        target = tags / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    if tag != source_tag:
        if (tags / tag).exists():
            raise ValueError("The import scenario alias conflicts with a source dependency")
        shutil.copyfile(tags / source_tag, tags / tag)
    names = [tool.get(tags, tag, f"scripts[{i}].name") for i in range(tool.count(tags, tag, "scripts"))]
    unknown = set(names) - set(spec["optional_scripts"])
    if unknown or tool.count(tags, tag, "encounters"):
        raise ValueError(f"Unreviewed script/AI behavior in {spec['id']}: {sorted(unknown)}")
    # Read-only generated arrays are changed only in the copied scenario.
    tool.run("edit", "-t", tags, "-n", "-E", "scripts[*]", "-E", "globals[*]", "-E", "source_files[*]", tag)
    cleanup = spec.get("cleanup_prefixes", [])
    if cleanup:
        if any(not re.fullmatch(r"[A-Za-z0-9_]+", p) for p in cleanup):
            raise ValueError("Invalid cleanup object prefix")
        script = data / Path(scenario).parent / "scripts/community_cleanup.hsc"
        script.parent.mkdir(parents=True)
        script.write_text("(script startup community_map_cleanup\n" +
                          "".join(f'    (object_destroy_containing "{p}")\n' for p in cleanup) + ")\n")
    models = sum(1 for _ in tags.rglob("*.gbxmodel"))
    tool.run("convert", "-t", tags, "-g", "gbxmodel", "model", "-b", "*.gbxmodel")
    tool.run("refactor", "-t", tags, "-M", "no-move", "-g", "gbxmodel", "model")
    shaders = convert_extended_shaders(tool, tags)
    validate_map_content_priority(stock, tags, compiled_scenario, source_tag)
    substitutions = resolved_stock_substitutions(tool, stock, tags, tag)
    tool.run("build", "-g", "xbox-ntsc", "-t", stock, "-t", tags,
             "-m", maps, "-d", data, "-S", "data", "-E", compiled_scenario)
    cache = maps / (import_id + ".map")
    h = cache_header(cache)
    if h["name"] != import_id or h["version"] != 5 or h["build"] != NTSC_BUILD or h["type"] != 1:
        raise ValueError("The generated map is not Xbox NTSC v5 multiplayer data")
    if h["declared_bytes"] > MAX_CACHE_BYTES or h["tag_bytes"] > TAG_ARENA_BYTES:
        raise ValueError("The generated map exceeds the native cache or original tag-arena capacity")
    if any(digest(safe_tag(source_tags, p)) != sha for p, sha in provenance.items()):
        raise RuntimeError("A source tag changed during import")
    manifest = {"id": spec["id"], "display_name": spec["display_name"], "scenario": scenario,
                "compiled_scenario": compiled_scenario,
                "output": str(cache), **h, "profile": "stock-xbox-ntsc",
                "source_tags": provenance, "stock_substitutions": substitutions,
                "models_converted": models, "removed_optional_scripts": names,
                "chicago_shader_conversions": shaders,
                "retained_cleanup_prefixes": cleanup, "source_files_unchanged": True,
                "status": "built; runtime and fidelity validation pending"}
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return {k: v for k, v in manifest.items() if k not in ("source_tags", "stock_substitutions")}


def build_maps(tool, specs, selected, package, stock, output, result):
    """Keep successful imports usable while recording failures and interruption state."""
    selected = list(dict.fromkeys(selected))
    result.update(selected_maps=selected, maps=[], failures=[], status="building",
                  map_status={name: "pending" for name in selected})
    def save():
        # A terminated process must not leave a half-written manifest behind.
        pending = output / "build.json.tmp"
        pending.write_text(json.dumps(result, indent=2) + "\n")
        pending.replace(output / "build.json")
    save()
    for name in selected:
        print("Building " + name, flush=True)
        result["map_status"][name] = "building"
        save()
        try:
            record = build_map(tool, specs[name], package, stock, output)
        except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
            result["failures"].append({"id": name, "scenario": specs[name]["scenario"],
                                       "error": str(error), "status": "failed"})
            result["map_status"][name] = "failed"
            print(f"Failed {name}: {error}", file=sys.stderr, flush=True)
        else:
            result["maps"].append(record)
            result["map_status"][name] = "built; runtime validation pending"
        save()
    result["status"] = "completed with failures" if result["failures"] else "built; runtime validation pending"
    save()
    return len(result["failures"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("inventory", "build"))
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--stock-maps", type=Path, default=ROOT / "assets/maps")
    parser.add_argument("--output", type=Path, required=True)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--map", action="append", dest="maps", help="Reviewed map ID; repeat for a cohort")
    selection.add_argument("--all", action="store_true", help="Build every map in the reviewed import policy")
    parser.add_argument("--invader-bin", type=Path)
    parser.add_argument("--invader-manifest", type=Path)
    args = parser.parse_args()
    package, stock_maps = args.package.resolve(strict=True), args.stock_maps.resolve(strict=True)
    policy = json.loads(POLICY.read_text())
    specs = {s["id"]: s for s in policy["maps"]}
    if len({name.casefold() for name in specs}) != len(policy["maps"]):
        parser.error("The import policy has duplicate map IDs")
    selected = list(specs) if args.all else args.maps or ["downrush"]
    if args.command == "build" and (not args.invader_bin or not args.invader_manifest or set(selected) - specs.keys()):
        parser.error("build needs the reviewed Invader binaries/manifest and supported map IDs")
    out = output_directory(args.output)
    record = inventory(package, stock_maps)
    record["import_tool_sha256"] = digest(Path(__file__))
    record["import_policy_sha256"] = digest(POLICY)
    record["engine_revision"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    record["source_diff_sha256"] = hashlib.sha256(subprocess.check_output(["git", "diff"], cwd=ROOT)).hexdigest()
    (out / "inventory.json").write_text(json.dumps(record, indent=2) + "\n")
    if args.command == "build":
        logs = out / "logs"
        logs.mkdir()
        tool = Invader(args.invader_bin, args.invader_manifest, logs)
        result = {"engine_revision": record["engine_revision"], "profile": policy["profile"],
                  "import_tool_sha256": record["import_tool_sha256"],
                  "import_policy_sha256": record["import_policy_sha256"],
                  "invader_commit": tool.commit, "tool_sha256": tool.provenance,
                  "stock": prepare_stock(tool, stock_maps, out / "stock-tags"), "maps": []}
        failures = build_maps(tool, specs, selected, package, out / "stock-tags", out, result)
        print(json.dumps({"output": str(out), "maps": result["maps"],
                          "failures": result["failures"]}, indent=2))
        return 1 if failures else 0
    else:
        print(json.dumps({"output": str(out), "maps": record["map_count"],
                          "stock_filename_collisions": [m["name"] for m in record["maps"] if m["stock_filename_collision"]]}, indent=2))


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print("Community map import failed: " + str(error), file=sys.stderr)
        sys.exit(1)
