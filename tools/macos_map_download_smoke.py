#!/usr/bin/env python3
"""Opt-in live acceptance check for the production Mac map downloader.

Runs the checked-in HTTPS endpoint, preserves a fresh isolated library and JSON
evidence, and verifies network-disabled reuse. Never reads/writes user settings
or uploads content. This verifies download/storage only, not gameplay or rights.

Example:
    python3 tools/macos_map_download_smoke.py --data-root /path/to/NTSC/data
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCES = [ROOT / "port/macos/tests/map_download_smoke.m", ROOT / "port/macos/native/HaloMapDownloads.m"]
CONFIG = ROOT / "port/macos/map-downloads.json"


def sha256(path: Path) -> str:
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def write_json(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8") as file:
        json.dump(value, file, indent=2, sort_keys=True)
        file.write("\n")


def ntsc_fixture(root: Path) -> None:
    """Authored profile-header fixture, with no original retail bytes."""
    maps = root / "maps"
    maps.mkdir(parents=True)
    header = bytearray(2048)
    header[:4] = b"daeh"
    struct.pack_into("<II", header, 4, 5, 2048)
    header[32:34] = b"ui"
    header[64:78] = b"01.10.12.2276\0"
    header[2044:] = b"toof"
    (maps / "ui.map").write_bytes(header)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    data = parser.add_mutually_exclusive_group(required=True)
    data.add_argument("--data-root", type=Path, help="Selected extracted original Xbox NTSC 2276 data root containing maps/ui.map")
    data.add_argument("--fixture-ntsc-ui", action="store_true", help="Use an authored profile-header fixture; does not verify original data or gameplay")
    parser.add_argument("--map", default="downrush", dest="map_id", help="Canonical lowercase approved community-map ID (default downrush)")
    parser.add_argument("--output", type=Path, help="New directory to preserve; existing paths are refused")
    parser.add_argument("--timeout", type=int, default=600, help="Live READY deadline in seconds, 1..600 (offline deadline up to 15 seconds)")
    parser.add_argument("--config", type=Path, default=CONFIG, help="Downloader configuration; default is checked-in public R2 settings")
    args = parser.parse_args()
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        parser.error("This native acceptance probe requires an Apple Silicon Mac.")
    if not re.fullmatch(r"[a-z0-9_ -]{1,31}", args.map_id):
        parser.error("--map must be a safe canonical lowercase map ID.")
    if not 1 <= args.timeout <= 600:
        parser.error("--timeout must be between 1 and 600 seconds.")
    config = args.config.expanduser().resolve()
    if not config.is_file():
        parser.error("Downloader configuration does not exist.")
    data_root = args.data_root.expanduser().resolve() if args.data_root else None
    if data_root and not data_root.is_dir():
        parser.error("--data-root must be an existing directory.")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    output = (args.output.expanduser() if args.output else ROOT / "build/macos/tests/map-download-smoke" / stamp).absolute()
    if os.path.lexists(output):
        parser.error(f"Refusing existing output path: {output}")
    output.mkdir(parents=True, exist_ok=False)
    output = output.resolve()
    support = output / "support"
    support.mkdir()
    if args.fixture_ntsc_ui:
        data_root = output / "synthetic-data"
        ntsc_fixture(data_root)
    probe = output / "native-probe"
    native_report = output / "native-report.json"
    compile_command = [
        "clang", "-arch", "arm64", "-mmacosx-version-min=14.0", "-fobjc-arc", "-fblocks",
        "-O2", "-Wall", "-Wextra", "-Wno-deprecated-declarations", "-I", str(ROOT / "port/macos/native"),
        *(str(path) for path in SOURCES), "-framework", "Foundation", "-o", str(probe),
    ]
    probe_command = [str(probe), str(config), str(data_root), str(support), args.map_id, str(native_report), str(args.timeout)]
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=True).stdout.strip()
    provenance = {
        "schema_version": 1, "started_at": datetime.now(timezone.utc).isoformat(), "git_revision": revision,
        "platform": platform.platform(), "map_id": args.map_id, "output_directory": str(output),
        "data_root": str(data_root), "data_source": "synthetic NTSC ui.map profile header" if args.fixture_ntsc_ui else "user-provided existing data root",
        "config_path": str(config), "config_sha256": sha256(config),
        "source_sha256": {str(path.relative_to(ROOT)): sha256(path) for path in SOURCES + [Path(__file__).resolve()]},
        "compile_command": compile_command, "probe_command": probe_command,
        "scope": "Real native HTTPS map delivery, full-file/header verification, guest hook READY, isolated disk-only reuse; no gameplay validation or uploads",
        "user_preferences_modified": False,
    }
    write_json(output / "provenance.json", provenance)
    print(f"Preserving smoke results in {output}", flush=True)
    status = {"schema_version": 1, "success": False, "provenance": "provenance.json", "native_report": "native-report.json"}
    try:
        with (output / "compile.log").open("x", encoding="utf-8") as log:
            subprocess.run(compile_command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)
        with (output / "download.log").open("x", encoding="utf-8") as log:
            result = subprocess.run(probe_command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                timeout=args.timeout + 35, check=False)
        status["probe_exit_code"] = result.returncode
        if native_report.is_file():
            native = json.loads(native_report.read_text(encoding="utf-8"))
            status["success"] = result.returncode == 0 and native.get("success") is True
            status["result"] = native
        else:
            status["error"] = "The native probe exited without a report; inspect download.log."
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        status["error"] = str(error)
    status["finished_at"] = datetime.now(timezone.utc).isoformat()
    write_json(output / "status.json", status)
    print(f"{'PASS' if status['success'] else 'FAIL'}: {output / 'status.json'}", flush=True)
    if not status["success"]:
        print(status.get("error") or status.get("result", {}).get("error", "Inspect preserved logs."), file=sys.stderr)
    return 0 if status["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
