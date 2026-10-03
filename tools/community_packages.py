#!/usr/bin/env python3
"""Whole-asset community packages and isolated, exact-base Xbox reconstruction.

This prototype omits only complete tags identical to freshly extracted stock
tags. Modified and unknown assets remain literal; it is not a rights audit.
Only locally trusted, hash-pinned invader-extract and invader-build execute.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import struct
import subprocess
import tempfile

MAGIC = b"HOGPKG1\n"
HEADER = struct.Struct("<8sQ")
FORMAT = "halo-og-community-package"
VERSION = 1
INVADER_COMMIT = "7d25a855f5ef9e4ab8407abf490b21f8780abf27"
NTSC_BUILD = "01.10.12.2276"
MAX_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_PACKAGE_BYTES = 256 * 1024 * 1024
MAX_PAYLOAD_BYTES = MAX_PACKAGE_BYTES - HEADER.size
MAX_FILE_BYTES = 128 * 1024 * 1024
MAX_FILES = 20000
MAX_TREE_BYTES = 1024 * 1024 * 1024
MAX_STOCK_BYTES = 512 * 1024 * 1024
MAX_CACHE_BYTES = 128 * 1024 * 1024
MAX_TAG_BYTES = 22 * 1024 * 1024
STOCK_NAMES = ("bloodgulch", "a10", "ui")
STOCK_TYPES = (1, 0, 2)
STOCK_IDS = {"ui", "a10", "a30", "a50", "b30", "b40", "c10", "c20", "c40", "d20", "d40",
             "beavercreek", "bloodgulch", "boardingaction", "carousel", "chillout", "damnation",
             "hangemhigh", "longest", "prisoner", "putput", "ratrace", "sidewinder", "wizard"}
CLASSIFICATIONS = {"unchanged-stock", "modified-or-different-stock", "unknown-or-community",
                   "compatibility-modified-stock", "generated-data"}
ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,30}\Z")
SHA = re.compile(r"[0-9a-f]{64}\Z")


class PackageError(ValueError):
    """Invalid or incompatible data; no final map is published."""


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _integer(value, minimum, maximum, label):
    if type(value) is not int or not minimum <= value <= maximum:
        raise PackageError(f"Invalid {label}")
    return value


def _sha(value):
    if not isinstance(value, str) or not SHA.fullmatch(value):
        raise PackageError("Invalid SHA-256")
    return value


def _path(value):
    if (not isinstance(value, str) or not 1 <= len(value.encode("utf-8")) <= 512 or
            any(ord(c) < 32 or ord(c) > 126 for c in value) or
            "\\" in value or ":" in value or value.startswith("/") or
            any(p in ("", ".", "..") or p.startswith(".") for p in value.split("/")) or
            str(PurePosixPath(value)) != value):
        raise PackageError("Unsafe relative asset path")
    return value


def _regular(path):
    path = Path(path)
    if not stat.S_ISREG(path.lstat().st_mode):
        raise PackageError(f"Expected a regular file: {path}")
    return path


def _tree(root):
    root = Path(root)
    if not stat.S_ISDIR(root.lstat().st_mode):
        raise PackageError("Expected a real asset directory")
    files, seen, total = {}, set(), 0
    for p in sorted(root.rglob("*")):
        mode = p.lstat().st_mode
        relative = _path(p.relative_to(root).as_posix())
        if stat.S_ISDIR(mode):
            continue
        if not stat.S_ISREG(mode):
            raise PackageError("Symlinks and special files are not permitted in asset trees")
        folded = relative.casefold()
        if folded in seen:
            raise PackageError("Case-colliding asset paths")
        seen.add(folded)
        size = _integer(p.stat().st_size, 0, MAX_FILE_BYTES, "asset size")
        total += size
        if total > MAX_TREE_BYTES or len(files) >= MAX_FILES:
            raise PackageError("Asset tree exceeds limits")
        files[relative] = {"path": p, "size": size, "sha256": digest(p)}
    return files


def _cache(path, *, stock=False):
    path = _regular(path)
    size = _integer(path.stat().st_size, 2048, MAX_STOCK_BYTES if stock else MAX_CACHE_BYTES, "cache size")
    with path.open("rb") as stream:
        data = stream.read(2048)
    if data[:4] != b"daeh" or data[-4:] != b"toof" or struct.unpack_from("<I", data, 4)[0] != 5:
        raise PackageError("Expected an Xbox v5 cache")
    def string(offset):
        raw = data[offset:offset + 32]
        if b"\0" not in raw:
            raise PackageError("Unterminated cache header string")
        try:
            return raw.split(b"\0", 1)[0].decode("ascii")
        except UnicodeDecodeError as error:
            raise PackageError("Invalid cache header string") from error
    name, build = string(32), string(64)
    if name.casefold() != path.stem.casefold() or build != NTSC_BUILD:
        raise PackageError("Cache name or original NTSC profile differs")
    declared, tag_bytes = struct.unpack_from("<I", data, 8)[0], struct.unpack_from("<I", data, 20)[0]
    tag_offset = struct.unpack_from("<I", data, 16)[0]
    if not stock and (not 2048 <= declared <= MAX_CACHE_BYTES or tag_bytes > MAX_TAG_BYTES or
                      tag_offset < 2048 or tag_offset + tag_bytes > declared):
        raise PackageError("Cache exceeds Xbox map limits")
    return {"name": name, "size": size, "sha256": digest(path), "type": struct.unpack_from("<H", data, 96)[0],
            "declared_bytes": declared, "tag_bytes": tag_bytes}


def _tools(manifest):
    data = json.loads(_regular(manifest).read_text())
    if data.get("invader_commit") != INVADER_COMMIT:
        raise PackageError("Unsupported Invader revision")
    try:
        hashes = {name: _sha(data["binaries"][name]["sha256"]) for name in ("extract", "build")}
    except (KeyError, TypeError) as error:
        raise PackageError("Missing trusted Invader hashes") from error
    return hashes


def _stock_inputs(maps):
    result = []
    for name, cache_type in zip(STOCK_NAMES, STOCK_TYPES):
        h = _cache(Path(maps) / (name + ".map"), stock=True)
        if h["type"] != cache_type:
            raise PackageError("Stock cache type differs")
        result.append({k: h[k] for k in ("name", "size", "sha256", "type")})
    return result


def _validate_manifest(m):
    required = {"format", "version", "id", "profile", "cache_build", "scenario", "invader_commit",
                "tool_sha256", "stock_inputs", "output", "payload_bytes", "files"}
    if not isinstance(m, dict) or set(m) != required:
        raise PackageError("Unsupported manifest fields")
    if (m["format"] != FORMAT or type(m["version"]) is not int or m["version"] != VERSION or
            m["profile"] != "stock-xbox-ntsc" or m["cache_build"] != NTSC_BUILD or
            m["invader_commit"] != INVADER_COMMIT):
        raise PackageError("Unsupported package version or profile")
    if not isinstance(m["id"], str) or not ID.fullmatch(m["id"]) or m["id"] in STOCK_IDS:
        raise PackageError("Unsafe or stock map identity")
    scenario = _path(m["scenario"])
    if not re.fullmatch(r"[A-Za-z0-9_ /-]+", scenario) or scenario.rsplit("/", 1)[-1] != m["id"]:
        raise PackageError("Scenario must use the community map identity")
    if not isinstance(m["tool_sha256"], dict) or set(m["tool_sha256"]) != {"extract", "build"}:
        raise PackageError("Invalid tool hashes")
    for sha in m["tool_sha256"].values():
        _sha(sha)
    if not isinstance(m["stock_inputs"], list) or len(m["stock_inputs"]) != 3:
        raise PackageError("Missing exact stock extraction inputs")
    for entry, name, cache_type in zip(m["stock_inputs"], STOCK_NAMES, STOCK_TYPES):
        if not isinstance(entry, dict) or set(entry) != {"name", "size", "sha256", "type"}:
            raise PackageError("Invalid stock input fields")
        if entry["name"] != name or type(entry["type"]) is not int or entry["type"] != cache_type:
            raise PackageError("Stock extraction order or type differs")
        _integer(entry["size"], 2048, MAX_STOCK_BYTES, "stock cache size")
        _sha(entry["sha256"])
    output = m["output"]
    if not isinstance(output, dict) or set(output) != {"size", "sha256", "declared_bytes", "tag_bytes"}:
        raise PackageError("Invalid expected cache fields")
    _sha(output["sha256"])
    _integer(output["size"], 2048, MAX_CACHE_BYTES, "expected cache size")
    _integer(output["declared_bytes"], 2048, MAX_CACHE_BYTES, "declared cache size")
    _integer(output["tag_bytes"], 0, MAX_TAG_BYTES, "tag arena size")
    _integer(m["payload_bytes"], 0, MAX_PAYLOAD_BYTES, "payload size")
    if not isinstance(m["files"], list) or not 1 <= len(m["files"]) <= MAX_FILES:
        raise PackageError("Invalid file count")
    seen, directories, offset, expanded, scenario_present = set(), {}, 0, 0, False
    for entry in m["files"]:
        if not isinstance(entry, dict):
            raise PackageError("Invalid asset entry")
        base = {"tree", "path", "kind", "classification", "size", "sha256"}
        tree, kind = entry.get("tree"), entry.get("kind")
        if tree not in ("tags", "data", "stock-overrides") or kind not in ("literal", "stock-reference"):
            raise PackageError("Unsupported asset storage")
        expected = base | ({"offset"} if kind == "literal" else {"stock_path"})
        if tree == "stock-overrides":
            expected.add("original_sha256")
        if (set(entry) != expected or not isinstance(entry["classification"], str) or
                entry["classification"] not in CLASSIFICATIONS):
            raise PackageError("Invalid asset fields or classification")
        path = _path(entry["path"])
        folded = (tree, path.casefold())
        if folded in seen or folded in directories:
            raise PackageError("Duplicate or case-colliding asset path")
        # A directory cannot also be a file, even with alternate casing.
        parts = path.split("/")
        for i in range(1, len(parts)):
            prefix = "/".join(parts[:i])
            key = (tree, prefix.casefold())
            if key in seen or (key in directories and directories[key] != prefix):
                raise PackageError("Asset file/directory collision")
            directories[key] = prefix
        seen.add(folded)
        size = _integer(entry["size"], 0, MAX_FILE_BYTES, "asset size")
        _sha(entry["sha256"])
        expanded += size
        if expanded > MAX_TREE_BYTES:
            raise PackageError("Expanded assets exceed limits")
        if kind == "literal":
            if _integer(entry["offset"], 0, MAX_PAYLOAD_BYTES, "payload offset") != offset:
                raise PackageError("Literal payload must be contiguous and ordered")
            offset += size
            if entry["classification"] == "unchanged-stock":
                raise PackageError("Unchanged stock assets must be references")
        else:
            if tree != "tags" or entry["classification"] != "unchanged-stock":
                raise PackageError("Only unchanged whole stock tags can be referenced")
            _path(entry["stock_path"])
        if tree == "stock-overrides":
            if kind != "literal" or entry["classification"] != "compatibility-modified-stock":
                raise PackageError("Stock repairs must retain entire modified assets")
            _sha(entry["original_sha256"])
            if entry["original_sha256"] == entry["sha256"]:
                raise PackageError("Stock override is unchanged")
        if tree == "data" and (kind != "literal" or entry["classification"] != "generated-data" or
                               not path.endswith(".hsc")):
            raise PackageError("Only prepared script data is supported")
        if tree == "tags" and path == scenario + ".scenario":
            scenario_present = kind == "literal"
        if tree == "stock-overrides" and path == scenario + ".scenario":
            raise PackageError("Stock repairs cannot replace the community scenario")
    if offset != m["payload_bytes"] or not scenario_present:
        raise PackageError("Incomplete payload or missing authored scenario")
    return m


def _unique_json(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise PackageError("Duplicate JSON key")
        result[key] = value
    return result


def read_package(path, verify_payload=True):
    """Validate schema, exact bounds and optionally every complete literal hash."""
    path = _regular(path)
    size = _integer(path.stat().st_size, HEADER.size + 2, MAX_PACKAGE_BYTES, "package size")
    with path.open("rb") as stream:
        magic, length = HEADER.unpack(stream.read(HEADER.size))
        if magic != MAGIC:
            raise PackageError("Invalid package magic")
        _integer(length, 2, MAX_MANIFEST_BYTES, "manifest size")
        if HEADER.size + length > size:
            raise PackageError("Truncated manifest")
        try:
            m = json.loads(stream.read(length).decode("utf-8"), object_pairs_hook=_unique_json)
        except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
            raise PackageError("Invalid manifest JSON") from error
        _validate_manifest(m)
        if HEADER.size + length + m["payload_bytes"] != size:
            raise PackageError("Truncated payload or trailing bytes")
        if verify_payload:
            for entry in m["files"]:
                if entry["kind"] != "literal":
                    continue
                h, remaining = hashlib.sha256(), entry["size"]
                while remaining:
                    chunk = stream.read(min(remaining, 1024 * 1024))
                    if not chunk:
                        raise PackageError("Truncated asset payload")
                    h.update(chunk)
                    remaining -= len(chunk)
                if h.hexdigest() != entry["sha256"]:
                    raise PackageError("Literal asset hash differs")
    return m


def _outside(destination, roots):
    resolved = Path(destination).absolute().resolve()
    for root in roots:
        if resolved.is_relative_to(Path(root).resolve()):
            raise PackageError("Destination would modify an input tree")
    if os.path.lexists(destination):
        raise PackageError("Destination already exists; refusing to overwrite")


def _publish_file(source, destination):
    # link is exclusive; unlike rename it cannot replace a racing destination.
    try:
        os.link(source, destination, follow_symlinks=False)
    except FileExistsError as error:
        raise PackageError("Destination already exists; refusing to overwrite") from error


def prepare_package(*, prepared_tags, prepared_data, original_stock_tags, patched_stock_tags,
                    stock_maps, expected_map, scenario, toolchain_manifest, destination):
    """Package producer-prepared tags; original_stock_tags must be a fresh extraction.

    A later reconstruct against the exact original caches is the acceptance gate
    for this producer-input assumption. No supplied build scripts execute.
    """
    destination = Path(destination)
    _outside(destination, (prepared_tags, prepared_data, original_stock_tags, patched_stock_tags, stock_maps))
    original, patched = _tree(original_stock_tags), _tree(patched_stock_tags)
    if set(original) != set(patched):
        raise PackageError("Prepared stock inventory differs from original extraction")
    prepared, data = _tree(prepared_tags), _tree(prepared_data)
    hashes = _tools(toolchain_manifest)
    h = _cache(expected_map)
    if h["type"] != 1 or not ID.fullmatch(h["name"]) or h["name"] in STOCK_IDS:
        raise PackageError("Expected a distinct community multiplayer map")
    m = {"format": FORMAT, "version": VERSION, "id": h["name"], "profile": "stock-xbox-ntsc",
         "cache_build": NTSC_BUILD, "scenario": scenario, "invader_commit": INVADER_COMMIT,
         "tool_sha256": hashes, "stock_inputs": _stock_inputs(stock_maps),
         "output": {k: h[k] for k in ("size", "sha256", "declared_bytes", "tag_bytes")},
         "payload_bytes": 0, "files": []}
    originals_by_hash = {}
    for relative, item in original.items():
        originals_by_hash.setdefault((item["size"], item["sha256"]), relative)
    literals = []
    def literal(tree, relative, item, classification, **extra):
        entry = {"tree": tree, "path": relative, "kind": "literal", "classification": classification,
                 "size": item["size"], "sha256": item["sha256"], "offset": m["payload_bytes"], **extra}
        m["files"].append(entry)
        literals.append(item)
        m["payload_bytes"] += item["size"]
    for relative, item in prepared.items():
        match = originals_by_hash.get((item["size"], item["sha256"]))
        if match is not None:
            # Whole asset equality; never identify unchanged chunks in a modified tag.
            if item["path"].read_bytes() != original[match]["path"].read_bytes():
                raise PackageError("Whole-asset digest collision")
            m["files"].append({"tree": "tags", "path": relative, "kind": "stock-reference",
                               "classification": "unchanged-stock", "size": item["size"],
                               "sha256": item["sha256"], "stock_path": match})
        else:
            literal("tags", relative, item, "modified-or-different-stock" if relative in original else "unknown-or-community")
    for relative, item in data.items():
        literal("data", relative, item, "generated-data")
    for relative, item in patched.items():
        if item["sha256"] != original[relative]["sha256"]:
            literal("stock-overrides", relative, item, "compatibility-modified-stock",
                    original_sha256=original[relative]["sha256"])
    _validate_manifest(m)
    encoded = json.dumps(m, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    if len(encoded) > MAX_MANIFEST_BYTES or HEADER.size + len(encoded) + m["payload_bytes"] > MAX_PACKAGE_BYTES:
        raise PackageError("Package exceeds limits")
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".community-package-", dir=destination.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(HEADER.pack(MAGIC, len(encoded)))
            stream.write(encoded)
            for item in literals:
                if digest(_regular(item["path"])) != item["sha256"]:
                    raise PackageError("Producer input changed during packaging")
                with item["path"].open("rb") as source:
                    shutil.copyfileobj(source, stream, 1024 * 1024)
            stream.flush()
            os.fsync(stream.fileno())
        read_package(temporary)
        _publish_file(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return m


def _verify_originals(m, original):
    for entry in m["files"]:
        if entry["kind"] == "stock-reference":
            item = original.get(entry["stock_path"])
            if not item or item["sha256"] != entry["sha256"] or item["size"] != entry["size"]:
                raise PackageError("Original whole stock tag differs or is missing")
        if entry["tree"] == "stock-overrides":
            item = original.get(entry["path"])
            if not item or item["sha256"] != entry["original_sha256"]:
                raise PackageError("Stock compatibility repair base differs or is missing")
    if m["scenario"] + ".scenario" in original:
        raise PackageError("Stock-first lookup would replace the community scenario")
    level = m["scenario"].rsplit("/", 1)[0] + "/"
    for entry in m["files"]:
        if entry["tree"] == "tags" and entry["path"] in original and (
                entry["path"].startswith(level) or entry["path"].endswith(".scenario_structure_bsp")):
            raise PackageError("Stock-first lookup would replace authored level content")


def materialize_package(*, package, original_stock_tags, destination):
    """Asset-only seam: exact references, intact literals, guarded stock repairs."""
    package, destination = Path(package), Path(destination)
    _outside(destination, (original_stock_tags,))
    m = read_package(package)
    original = _tree(original_stock_tags)
    _verify_originals(m, original)
    # Validate stock override hierarchy before opening any destination files.
    for entry in m["files"]:
        if entry["tree"] == "stock-overrides":
            for parent in PurePosixPath(entry["path"]).parents:
                if parent.as_posix() in original:
                    raise PackageError("Stock override path collides with a file")
    destination.mkdir(parents=True, exist_ok=False)
    try:
        for tree in ("stock", "tags", "data"):
            (destination / tree).mkdir()
        for relative, item in original.items():
            target = destination / "stock" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(item["path"], target)
            if digest(target) != item["sha256"]:
                raise PackageError("Original tag changed while copying")
        with package.open("rb") as source:
            _, length = HEADER.unpack(source.read(HEADER.size))
            payload_start = HEADER.size + length
            for entry in m["files"]:
                tree = "stock" if entry["tree"] == "stock-overrides" else entry["tree"]
                target = destination / tree / entry["path"]
                target.parent.mkdir(parents=True, exist_ok=True)
                if entry["kind"] == "stock-reference":
                    shutil.copyfile(original[entry["stock_path"]]["path"], target)
                else:
                    source.seek(payload_start + entry["offset"])
                    fd, temporary = tempfile.mkstemp(prefix=".asset-", dir=target.parent)
                    try:
                        with os.fdopen(fd, "wb") as output:
                            remaining = entry["size"]
                            while remaining:
                                chunk = source.read(min(remaining, 1024 * 1024))
                                if not chunk:
                                    raise PackageError("Package changed while materializing")
                                output.write(chunk)
                                remaining -= len(chunk)
                        if digest(temporary) != entry["sha256"]:
                            raise PackageError("Asset changed while materializing")
                        # Only guarded stock repairs replace our temporary copied stock.
                        if entry["tree"] == "stock-overrides":
                            if digest(target) != entry["original_sha256"]:
                                raise PackageError("Stock repair target changed")
                            os.replace(temporary, target)
                        else:
                            _publish_file(temporary, target)
                    finally:
                        Path(temporary).unlink(missing_ok=True)
                if digest(target) != entry["sha256"]:
                    raise PackageError("Materialized whole asset differs")
    except BaseException:
        shutil.rmtree(destination)
        raise
    return m


def reconstruct_package(*, package, stock_maps, tool_bin, toolchain_manifest, destination):
    """Reconstruct in a fresh workspace using only trusted native extract/build."""
    package, stock_maps, tool_bin, destination = map(Path, (package, stock_maps, tool_bin, destination))
    _outside(destination, (stock_maps, tool_bin))
    m = read_package(package)
    if _stock_inputs(stock_maps) != m["stock_inputs"]:
        raise PackageError("Selected original stock cache hashes differ from this exact package base")
    trusted = _tools(toolchain_manifest)
    if trusted != m["tool_sha256"]:
        raise PackageError("Package toolchain differs from trusted source manifest")
    for name, sha in trusted.items():
        if digest(_regular(tool_bin / ("invader-" + name))) != sha:
            raise PackageError("Invader executable differs from trusted manifest")
    destination.mkdir(parents=True, exist_ok=False)
    try:
        logs = destination / "logs"
        logs.mkdir()
        def run(name, *args):
            command = [str((tool_bin / ("invader-" + name)).resolve()), *map(str, args)]
            try:
                result = subprocess.run(command, capture_output=True, text=True, timeout=180)
            except subprocess.TimeoutExpired as error:
                raise PackageError(f"Trusted invader-{name} timed out") from error
            (logs / f"{len(list(logs.iterdir())) + 1:02d}-{name}.log").write_text(result.stdout + result.stderr)
            if result.returncode:
                raise PackageError(f"Trusted invader-{name} failed ({result.returncode}): {result.stderr[-1500:]}")
        extracted = destination / ".original-stock"
        extracted.mkdir()
        for name in STOCK_NAMES:
            run("extract", "-t", extracted, stock_maps / (name + ".map"))
        workspace = destination / ".assembled"
        materialize_package(package=package, original_stock_tags=extracted, destination=workspace)
        maps = workspace / "maps"
        maps.mkdir()
        run("build", "-g", "xbox-ntsc", "-t", workspace / "stock", "-t", workspace / "tags",
            "-m", maps, "-d", workspace / "data", "-S", "data", "-E", m["scenario"])
        cache = maps / (m["id"] + ".map")
        h = _cache(cache)
        if h["type"] != 1 or {k: h[k] for k in m["output"]} != m["output"]:
            raise PackageError("Reconstructed cache differs from approved exact bytes")
        if _stock_inputs(stock_maps) != m["stock_inputs"]:
            raise PackageError("Original stock caches changed during reconstruction")
        report = {"status": "exact-reconstruction", "id": m["id"], "package_sha256": digest(package),
                  "map": m["output"], "profile": m["profile"], "invader_commit": m["invader_commit"],
                  "tool_sha256": trusted, "stock_inputs": m["stock_inputs"],
                  "scope": "Only whole identical stock tags omitted; modified and unknown assets remain literal."}
        # Publish verified maps last, after compiler success and all hash gates.
        for tree in ("stock", "tags", "data", "maps"):
            os.rename(workspace / tree, destination / tree)
        workspace.rmdir()
        shutil.rmtree(extracted)
        (destination / "provenance.json").write_text(json.dumps(report, indent=2) + "\n")
        return report
    except BaseException:
        shutil.rmtree(destination)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    for option in ("prepared-tags", "prepared-data", "original-stock-tags", "patched-stock-tags", "stock-maps",
                   "expected-map", "toolchain-manifest", "destination"):
        prepare.add_argument("--" + option, required=True, type=Path)
    prepare.add_argument("--scenario", required=True)
    inspect = commands.add_parser("inspect")
    inspect.add_argument("package", type=Path)
    reconstruct = commands.add_parser("reconstruct")
    for option in ("package", "stock-maps", "tool-bin", "toolchain-manifest", "destination"):
        reconstruct.add_argument("--" + option, required=True, type=Path)
    args = vars(parser.parse_args())
    command = args.pop("command")
    try:
        result = (prepare_package(**args) if command == "prepare" else
                  reconstruct_package(**args) if command == "reconstruct" else read_package(args["package"]))
    except (PackageError, OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        parser.exit(1, f"community package: {error}\n")
    if command == "inspect":
        print(json.dumps(result, indent=2))
    else:
        print(json.dumps({"status": command, "id": result["id"], "destination": str(args["destination"])}))


if __name__ == "__main__":
    main()
