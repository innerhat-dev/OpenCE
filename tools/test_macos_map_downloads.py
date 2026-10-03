#!/usr/bin/env python3
"""Compile and run the native downloader against synthetic in-process HTTPS fixtures."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    output = ROOT / "build/macos/tests/map-downloads"
    output.mkdir(parents=True, exist_ok=True)
    executable = output / "map-downloads"
    subprocess.run([
        "clang", "-arch", "arm64", "-mmacosx-version-min=14.0", "-fobjc-arc", "-fblocks",
        "-O2", "-Wall", "-Wextra", "-Wno-deprecated-declarations", "-Iport/macos/native",
        "port/macos/tests/map_downloads.m", "port/macos/native/HaloMapDownloads.m",
        "-framework", "Foundation", "-o", executable,
    ], cwd=ROOT, check=True)
    with tempfile.TemporaryDirectory(prefix="fixtures-", dir=output) as fixtures:
        subprocess.run([executable, fixtures, ROOT / "port/macos/map-downloads.json"], check=True, timeout=30)


if __name__ == "__main__":
    main()
