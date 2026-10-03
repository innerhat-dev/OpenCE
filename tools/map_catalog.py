#!/usr/bin/env python3
"""Prepare a local community-map catalog and immutable object tree. Never upload.

Inputs must already be rebuilt Xbox v5 NTSC multiplayer caches. This checks the
delivery format and hashes; it does not convert maps or certify gameplay parity.
"""
import argparse
import ctypes
import json
import os
from pathlib import Path
import shutil
import struct
import sys
import tempfile

if __package__:
    from .community_maps import cache_header, MAX_CACHE_BYTES, NTSC_BUILD, TAG_ARENA_BYTES
else:
    from community_maps import cache_header, MAX_CACHE_BYTES, NTSC_BUILD, TAG_ARENA_BYTES


RESERVED = set("ui a10 a30 a50 b30 b40 c10 c20 c40 d20 d40 beavercreek sidewinder damnation "
               "ratrace prisoner hangemhigh chillout carousel boardingaction bloodgulch wizard putput longest".split())
MAX_MAPS = 115
MAX_CATALOG_BYTES = 1048576


def validate_map(path):
    path = Path(path)
    if not path.is_file() or path.suffix.casefold() != ".map":
        raise ValueError("Select an existing .map file: " + str(path))
    size = path.stat().st_size
    if size < 2048 or size > MAX_CACHE_BYTES:
        raise ValueError("Map transfer size must be between 2048 bytes and 128 MiB: " + str(path))
    header = cache_header(path)
    with path.open("rb") as stream:
        data = stream.read(2048)
    tag_offset = struct.unpack_from("<I", data, 16)[0]
    if (header["name"].casefold() in RESERVED or header["version"] != 5
            or header["build"] != NTSC_BUILD or header["type"] != 1):
        raise ValueError("Only non-stock Xbox v5 NTSC 2276 multiplayer maps are allowed: " + str(path))
    # Compressed v5 caches declare their decompressed length. Tag bounds belong
    # to that declared cache, not to the smaller transfer file.
    if (not 2048 <= header["declared_bytes"] <= MAX_CACHE_BYTES
            or header["tag_bytes"] > TAG_ARENA_BYTES or tag_offset < 2048
            or tag_offset + header["tag_bytes"] > header["declared_bytes"]):
        raise ValueError("Map cache or tag bounds exceed the native loader limits: " + str(path))
    return header


def publish_directory(staged, output):
    """Atomic directory rename that refuses an existing destination, even empty."""
    if sys.platform == "win32":
        os.rename(staged, output)  # Windows rename never replaces a destination.
        return
    library = ctypes.CDLL(None, use_errno=True)
    if sys.platform == "darwin":
        rename = library.renamex_np
        rename.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        result = rename(os.fsencode(staged), os.fsencode(output), 4)  # RENAME_EXCL
    elif sys.platform.startswith("linux") and hasattr(library, "renameat2"):
        rename = library.renameat2
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        result = rename(-100, os.fsencode(staged), -100, os.fsencode(output), 1)  # AT_FDCWD, RENAME_NOREPLACE
    else:
        raise OSError("This platform cannot atomically publish a new directory without replacing one")
    if result:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), str(output))


def prepare_catalog(maps, output, prefetch=()):
    output = Path(os.path.abspath(output))
    if os.path.lexists(output):
        raise FileExistsError("Output already exists; choose a new directory: " + str(output))
    if not 1 <= len(maps) <= MAX_MAPS:
        raise ValueError("Select between 1 and 115 explicit map files")
    selected = {}
    for path in maps:
        header = validate_map(path)
        key = header["name"].casefold()
        if key in selected:
            raise ValueError("Duplicate map identity, ignoring capitalization: " + header["name"])
        selected[key] = (Path(path), header)
    requested = {name.casefold() for name in prefetch}
    if requested - selected.keys():
        raise ValueError("Prefetch identity was not selected: " + ", ".join(sorted(requested - selected.keys())))
    output.parent.mkdir(parents=True, exist_ok=True)
    staged = Path(tempfile.mkdtemp(prefix="." + output.name + "-", suffix=".partial", dir=output.parent))
    try:
        entries = []
        for key, (source, header) in sorted(selected.items()):
            object_key = f"maps/sha256/{header['sha256']}/{key}.map"
            destination = staged / object_key
            destination.parent.mkdir(parents=True)
            shutil.copyfile(source, destination)
            if validate_map(destination) != header:
                raise ValueError("Map source changed while preparing its object: " + str(source))
            entries.append({"id": key, "sha256": header["sha256"], "file_bytes": header["file_bytes"],
                            "cache_version": 5, "cache_build": NTSC_BUILD, "scenario_type": 1,
                            "object_key": object_key, "prefetch": key in requested})
        catalog = {"schema_version": 1, "profile": "stock-xbox-ntsc", "maps": entries}
        data = (json.dumps(catalog, indent=2) + "\n").encode()
        if len(data) > MAX_CATALOG_BYTES:
            raise ValueError("Catalog exceeds the native downloader's 1 MiB limit")
        (staged / "catalog.json").write_bytes(data)
        publish_directory(staged, output)
        return catalog
    finally:
        if staged.exists():
            shutil.rmtree(staged)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--map", dest="maps", type=Path, action="append", required=True,
                        help="Explicit rebuilt Xbox v5 NTSC multiplayer map; repeat for each file")
    parser.add_argument("--output", type=Path, required=True, help="New local catalog/object directory")
    parser.add_argument("--prefetch", action="append", default=[], metavar="ID",
                        help="Selected map to fetch in the background after launch; repeat as needed")
    args = parser.parse_args()
    try:
        catalog = prepare_catalog(args.maps, args.output, args.prefetch)
    except (ValueError, OSError) as error:
        parser.exit(1, "Catalog preparation failed: " + str(error) + "\n")
    print(f"Prepared {len(catalog['maps'])} maps in {args.output.resolve()}")
    print("No files uploaded. Hosting configuration and upload credentials are still required.")


if __name__ == "__main__":
    main()
