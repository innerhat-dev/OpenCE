"""Stage two explicitly supplied, reviewed Invader helpers for a local prototype.

No downloads, compilation, shell commands or execution of supplied helpers occur.
The source manifest supplies provenance, never executable paths or new trust
anchors. Pins come from checked-in configuration. This is not a fresh-CI build
recipe or a completed public corresponding-source distribution.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PINS = ROOT / "port/macos/content-tools.json"
MAX_BINARY_BYTES = 64 * 1024 * 1024
MAX_NOTICE_BYTES = 16 * 1024 * 1024


def _read_regular(path, limit):
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise RuntimeError("Content tool input must be a bounded regular file: " + path.name)
        data = stream.read(limit + 1)
        if len(data) != info.st_size or len(data) > limit:
            raise RuntimeError("Content tool input changed while reading: " + path.name)
    return data


def _inside(directory, relative):
    path = directory / relative
    if not path.resolve().is_relative_to(directory):
        raise RuntimeError("Content tool source escapes its supplied directory")
    return path


def _capture(*arguments):
    return subprocess.check_output(list(map(str, arguments)), text=True,
                                   stderr=subprocess.PIPE).strip()


def _inspect(binary):
    if _capture("/usr/bin/lipo", "-archs", binary).split() != ["arm64"]:
        raise RuntimeError("Content tools must contain exactly the reviewed arm64 architecture")
    lines = _capture("/usr/bin/otool", "-L", binary).splitlines()
    libraries = []
    for line in lines[1:]:
        match = re.fullmatch(r"\s+(.+?) \(compatibility version [^)]+\)", line)
        if not match:
            raise RuntimeError("Could not validate content tool runtime libraries")
        library = match[1]
        if (not library.startswith(("/usr/lib/", "/System/Library/"))
                or os.path.normpath(library) != library):
            raise RuntimeError("Content tools may link only macOS system libraries")
        libraries.append(library)
    if not libraries:
        raise RuntimeError("Content tool runtime libraries are missing")
    return libraries


def _notices(directory, manifest, pins):
    notices = {}
    for name, relative in pins["notices"].items():
        notices[name] = _read_regular(_inside(directory, relative), MAX_NOTICE_BYTES)
    for name, (relative, marker) in pins["header_notices"].items():
        text = _read_regular(_inside(directory, relative), MAX_NOTICE_BYTES).decode("utf-8")
        offset = text.rfind(marker)
        if offset < 0 or not text[offset:].rstrip().endswith("*/"):
            raise RuntimeError("Embedded content tool license is missing: " + name)
        notices[name] = text[offset:].encode("utf-8")
    # Rust's statically linked standard library includes third-party notices.
    # Only known documentation files are read; this path never executes a tool.
    rust_bin = Path(manifest.get("rust_toolchain", ""))
    if (rust_bin.name != "bin" or rust_bin.parent.name !=
            pins["rust_version"] + "-aarch64-apple-darwin"):
        raise RuntimeError("Content tools need the reviewed Rust standard-library notices")
    rust_docs = rust_bin.parent / "share/doc/rust"
    notices["Rust-COPYRIGHT-library.html"] = _read_regular(
        rust_docs / "COPYRIGHT-library.html", MAX_NOTICE_BYTES)
    for name in pins["rust_notices"]:
        notices["Rust-" + name] = _read_regular(rust_docs / "licenses" / name, MAX_NOTICE_BYTES)
    registry = _inside(directory, pins["cargo_registry"])
    for crate in pins["cargo_crates"]:
        source = _inside(directory, pins["cargo_registry"] + "/" + crate)
        licenses = sorted(path for path in source.iterdir()
                          if path.name.startswith(("LICENSE", "UNLICENSE", "COPYING")))
        if not licenses or not source.resolve().is_relative_to(registry.resolve()):
            raise RuntimeError("Rust crate notices are missing: " + crate)
        for path in licenses:
            notices[crate + "-" + path.name] = _read_regular(path, MAX_NOTICE_BYTES)
    # Preserve the actual small build-system customization, without machine paths.
    notices["invader-dependencies.cmake"] = _read_regular(
        _inside(directory, pins["source_patch"]), MAX_NOTICE_BYTES)
    notices["README.txt"] = (
        "Invader and RIAT: GPL-3.0-only. See the included full license and notices.\n"
        "These are reviewed prebuilt helpers for an explicit local prototype.\n"
        "Source revisions are recorded in ContentTools.json. The patched\n"
        "dependencies.cmake is included here. A pinned fresh-CI build recipe and\n"
        "complete public corresponding-source delivery remain unfinished.\n"
        "The macOS minimum version must include both bundled helper binaries.\n"
        "Runtime reconstruction uses only invader-extract and invader-build;\n"
        "the source package must already contain reviewed compatibility repairs.\n"
    ).encode("utf-8")
    return notices


def stage_content_tools(app, toolchain_directory, sign_identity="-", release=False):
    """Return staged binary Paths for the caller's minimum-macOS calculation.

    The caller supplies a private, unsigned app staging tree. Existing helper or
    provenance destinations are refused. On failure all additions are removed.
    Sign the enclosing app only after this function returns successfully.
    """
    pins = json.loads(PINS.read_text())
    directory = Path(toolchain_directory).resolve(strict=True)
    manifest = json.loads(_read_regular(directory / "source-manifest.json", MAX_NOTICE_BYTES))
    for key in ("invader_repository", "invader_commit", "riat_commit", "architecture"):
        if manifest.get(key) != pins[key]:
            raise RuntimeError("Content tool source manifest differs from the reviewed " + key)
    if release and not sign_identity.startswith("Developer ID Application:"):
        raise RuntimeError("Release content tools need an explicit Developer ID Application identity")
    if release and not pins.get("fresh_ci_ready"):
        raise RuntimeError("Community helpers are local-prototype only; pinned CI and corresponding-source delivery are unfinished")
    contents = Path(app) / "Contents"
    resources = contents / "Resources"
    if (Path(app).is_symlink() or contents.is_symlink() or resources.is_symlink()
            or not contents.is_dir() or not resources.is_dir()):
        raise RuntimeError("Stage content tools only into a prepared private app bundle")
    targets = (contents / "Helpers", resources / "Licenses/Invader", resources / "ContentTools.json")
    if any(os.path.lexists(path) for path in targets):
        raise FileExistsError("Content tools or their provenance already exist in this app")
    inputs = {}
    for name, expected in pins["binaries"].items():
        if manifest.get("binaries", {}).get(name, {}).get("sha256") != expected:
            raise RuntimeError("Content tool manifest contains an unreviewed binary: " + name)
        path = _inside(directory, "build/invader-" + name)
        data = _read_regular(path, MAX_BINARY_BYTES)
        if hashlib.sha256(data).hexdigest() != expected:
            raise RuntimeError("Content tool binary differs from its checked-in pin: " + name)
        inputs[name] = (data, _inspect(path))
    notices = _notices(directory, manifest, pins)
    published = []
    try:
        with tempfile.TemporaryDirectory(prefix=".content-tools-", dir=contents) as temporary:
            staging = Path(temporary)
            helpers, licenses = staging / "Helpers", staging / "Invader"
            helpers.mkdir()
            licenses.mkdir()
            binary_records = {}
            for name, (data, libraries) in inputs.items():
                binary = helpers / ("invader-" + name)
                binary.write_bytes(data)
                binary.chmod(0o755)
                signing = ["/usr/bin/codesign", "--force", "--sign", sign_identity]
                if release:
                    signing += ["--options", "runtime", "--timestamp"]
                subprocess.run([*signing, str(binary)], check=True, capture_output=True)
                subprocess.run(["/usr/bin/codesign", "--verify", "--strict", str(binary)],
                               check=True, capture_output=True)
                binary_records[name] = {"source_sha256": pins["binaries"][name],
                                        "bundled_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
                                        "architecture": "arm64", "system_libraries": libraries}
            for name, data in notices.items():
                (licenses / name).write_bytes(data)
            provenance = {key: pins[key] for key in (
                "schema", "architecture", "invader_repository", "invader_commit",
                "riat_repository", "riat_commit", "rust_version", "fresh_ci_ready")}
            provenance["binaries"] = binary_records
            provenance["notices_sha256"] = {name: hashlib.sha256(data).hexdigest()
                                           for name, data in sorted(notices.items())}
            record = staging / "ContentTools.json"
            record.write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n")
            targets[1].parent.mkdir(exist_ok=True)
            if targets[1].parent.is_symlink():
                raise RuntimeError("Content tool license destination must be a real directory")
            for source, target in zip((helpers, licenses, record), targets):
                if source.is_dir():
                    # mkdir and each link are exclusive, including raced targets.
                    # This caller-owned app remains private until fully signed.
                    target.mkdir()
                    published.append(target)
                    for child in source.iterdir():
                        os.link(child, target / child.name)
                else:
                    os.link(source, target)
                    published.append(target)
    except BaseException:
        for target in reversed(published):
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
        raise
    return [targets[0] / ("invader-" + name) for name in pins["binaries"]]


def audit_content_tools(app):
    """Verify optional helpers and their exact bundled provenance/notices."""
    pins = json.loads(PINS.read_text())
    contents = Path(app) / "Contents"
    record = json.loads(_read_regular(contents / "Resources/ContentTools.json", 1024 * 1024))
    keys = ("schema", "architecture", "invader_repository", "invader_commit", "riat_repository",
            "riat_commit", "rust_version", "fresh_ci_ready")
    if (not isinstance(record, dict) or any(record.get(key) != pins[key] for key in keys)
            or not isinstance(record.get("binaries"), dict)
            or set(record["binaries"]) != set(pins["binaries"])):
        raise RuntimeError("Bundled community tool provenance does not match reviewed pins")
    for name, expected in pins["binaries"].items():
        item = record["binaries"][name]
        binary = contents / "Helpers" / ("invader-" + name)
        if (not isinstance(item, dict) or item.get("source_sha256") != expected
                or item.get("architecture") != "arm64"
                or hashlib.sha256(_read_regular(binary, MAX_BINARY_BYTES)).hexdigest() != item.get("bundled_sha256")
                or _inspect(binary) != item.get("system_libraries")):
            raise RuntimeError("Bundled community helper differs from its provenance: " + name)
    notices = record.get("notices_sha256")
    required = set(pins["notices"]) | set(pins["header_notices"]) | {
        "Rust-" + name for name in pins["rust_notices"]} | {
        "Rust-COPYRIGHT-library.html", "README.txt", "invader-dependencies.cmake"}
    licenses = contents / "Resources/Licenses/Invader"
    if (not isinstance(notices, dict) or not required.issubset(notices)
            or licenses.is_symlink() or not licenses.is_dir()
            or {path.name for path in licenses.iterdir()} != set(notices)
            or any(not any(name.startswith(crate + "-") for name in notices) for crate in pins["cargo_crates"])):
        raise RuntimeError("Bundled community helper notices are incomplete")
    for name, expected in notices.items():
        if (not isinstance(name, str) or Path(name).name != name
                or hashlib.sha256(_read_regular(licenses / name, MAX_NOTICE_BYTES)).hexdigest() != expected):
            raise RuntimeError("Bundled community helper notice differs from its provenance")
    return True
