#!/usr/bin/env python3
"""Native, offline local-package acceptance probe in a fresh isolated library.

Compiles production Foundation map code, never starts the game or reads user
preferences. Only the explicitly supplied, reviewed bundled helpers execute.
Original maps, package and tool app are read-only inputs. Results are preserved
in a new directory; no hosting credentials, HTTP calls, uploads or installation.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.community_packages import read_package

SOURCES = [ROOT / "port/macos/tests/map_package_smoke.m",
           ROOT / "port/macos/native/HaloMapPackages.m",
           ROOT / "port/macos/native/HaloMapDownloads.m"]


def sha256(path: Path) -> str:
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def write_json(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8") as file:
        json.dump(value, file, indent=2, sort_keys=True)
        file.write("\n")


def package_manifest(path: Path) -> dict:
    return read_package(path)


def parser_cases(manifest: dict, directory: Path) -> list[dict]:
    """Tiny authored payloads exercise the real parser without copying assets."""
    directory.mkdir()
    base = json.loads(json.dumps(manifest))
    payload = b"authored smoke scenario bytes"
    entry = {"tree": "tags", "path": base["scenario"] + ".scenario", "kind": "literal",
             "classification": "unknown-or-community", "size": len(payload),
             "sha256": hashlib.sha256(payload).hexdigest(), "offset": 0}
    base["files"], base["payload_bytes"] = [entry], len(payload)
    cases = []

    def emit(name, value=None, body=payload, *, valid=False, assemble=False, reuse=False, raw=None):
        encoded = json.dumps(value or base, separators=(",", ":")).encode()
        data = raw if raw is not None else struct.pack("<8sQ", b"HOGPKG1\n", len(encoded)) + encoded + body
        path = directory / (name + ".hogpkg")
        path.write_bytes(data)
        cases.append({"name": name, "path": path, "valid": valid,
                      "assemble_rejected": assemble, "reuse_rejected": reuse})

    emit("authored-valid-parser-fixture", valid=True)
    emit("manifest-length-overflow", raw=struct.pack("<8sQ", b"HOGPKG1\n", 2**64-1) + b"{}")
    emit("truncated-literal", body=payload[:-1])
    emit("trailing-literal", body=payload + b"!")
    changed = json.loads(json.dumps(base)); changed["files"][0]["offset"] = 1
    emit("noncontiguous-offset", changed)
    changed = json.loads(json.dumps(base)); changed["files"][0]["sha256"] = "0" * 64
    emit("wrong-literal-hash", changed)
    for name, path in (("parent-traversal", "../escape.scenario"),
                       ("absolute-path", "/escape.scenario"),
                       ("backslash-path", "levels\\escape.scenario"),
                       ("hidden-component", ".hidden/escape.scenario")):
        changed = json.loads(json.dumps(base)); changed["files"][0]["path"] = path
        emit(name, changed)
    changed = json.loads(json.dumps(base))
    duplicate = dict(changed["files"][0]); duplicate["path"] = duplicate["path"].upper(); duplicate["offset"] = len(payload)
    changed["files"].append(duplicate); changed["payload_bytes"] = 2 * len(payload)
    emit("case-colliding-path", changed, body=payload * 2)
    changed = json.loads(json.dumps(base)); changed["tool_sha256"]["build"] = "invalid"
    emit("malformed-tool-hash", changed)
    changed = json.loads(json.dumps(base)); changed["tool_sha256"]["build"] = "0" * 64
    emit("trusted-tool-mismatch", changed, valid=True, assemble=True)
    for key in ("declared_bytes", "tag_bytes"):
        changed = json.loads(json.dumps(base)); changed["output"][key] += 1
        emit("forged-output-" + key, changed, valid=True, assemble=True, reuse=True)
    return cases


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("package", "data-root", "tools-app", "output"):
        parser.add_argument("--" + option, required=True, type=Path)
    parser.add_argument("--timeout", type=int, default=900,
                        help="Native assembly and readiness deadline in seconds (30..1800)")
    args = parser.parse_args()
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        parser.error("This production native probe requires an Apple Silicon Mac")
    if not 30 <= args.timeout <= 1800:
        parser.error("--timeout must be between 30 and 1800 seconds")
    package, data_root, tools_app = (path.expanduser().resolve(strict=True)
                                    for path in (args.package, args.data_root, args.tools_app))
    output = args.output.expanduser().absolute()
    if os.path.lexists(output):
        parser.error("Refusing an existing output path")
    output = output.resolve()
    if any(output.is_relative_to(path) for path in (data_root, tools_app)):
        parser.error("Output must be outside the original data and tool app")
    if not package.is_file() or not data_root.is_dir() or not tools_app.is_dir():
        parser.error("Package, original data directory and tools app must exist")
    manifest = package_manifest(package)
    maps = data_root / "maps"
    inputs = {"package": package,
              "ContentTools.json": tools_app / "Contents/Resources/ContentTools.json"}
    for entry in manifest["stock_inputs"]:
        inputs["stock/" + entry["name"]] = maps / (entry["name"] + ".map")
    for name in ("extract", "build"):
        inputs["helper/" + name] = tools_app / "Contents/Helpers" / ("invader-" + name)
    before = {name: {"path": str(path), "sha256": sha256(path), "file_bytes": path.stat().st_size}
              for name, path in inputs.items()}
    output.mkdir(parents=True, exist_ok=False)
    support = output / "support"
    support.mkdir()
    probe = output / "native-probe"
    report = output / "native-report.json"
    compile_command = ["/usr/bin/clang", "-arch", "arm64", "-mmacosx-version-min=14.0",
        "-fobjc-arc", "-fblocks", "-O2", "-Wall", "-Wextra", "-Wno-deprecated-declarations",
        "-I", str(ROOT / "port/macos/native"), *(str(path) for path in SOURCES),
        "-framework", "Foundation", "-o", str(probe)]
    command = [str(probe), str(package), str(data_root), str(tools_app), str(support), str(report), str(args.timeout)]
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    provenance = {"schema_version": 1, "git_revision": revision,
        "started_at": datetime.now(timezone.utc).isoformat(), "manifest": manifest,
        "package_sha256": before["package"]["sha256"], "inputs_before": before,
        "source_sha256": {str(path.relative_to(ROOT)): sha256(path) for path in SOURCES + [Path(__file__).resolve()]},
        "compile_command": compile_command, "probe_command": command,
        "scope": "Local whole-tag reconstruction, receipt readiness, offline reuse and parser rejection; no gameplay/rights validation",
        "user_preferences_modified": False, "application_installed": False}
    write_json(output / "provenance.json", provenance)
    print("Preserving native package evidence in " + str(output), flush=True)
    status = {"schema_version": 1, "success": False, "parser_cases": []}
    try:
        with (output / "compile.log").open("x") as log:
            subprocess.run(compile_command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)
        with (output / "assembly.log").open("x") as log:
            result = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                    timeout=args.timeout + 45, check=False)
        native = json.loads(report.read_text()) if report.is_file() else {}
        status["native_report"] = native
        status["native_exit_code"] = result.returncode
        cases = parser_cases(manifest, output / "parser-cases")
        for case in cases:
            mode = "--reject-reuse" if case["reuse_rejected"] else "--reject-tools" if case["assemble_rejected"] else "--inspect"
            destination = output / "parser-cases" / (case["name"] + ".json")
            case_command = [str(probe), mode, str(case["path"]), str(data_root), str(tools_app),
                    str(support if case["reuse_rejected"] else output / "parser-cases" / (case["name"] + "-support")), str(destination)]
            with (destination.with_suffix(".log")).open("x") as log:
                result_case = subprocess.run(case_command, stdout=log, stderr=subprocess.STDOUT, timeout=30, check=False)
            evidence = json.loads(destination.read_text()) if destination.is_file() else {}
            expected = case["valid"] and not case["assemble_rejected"]
            passed = evidence.get("accepted") is expected and result_case.returncode == (0 if expected else 1)
            if case["assemble_rejected"]:
                passed = passed and evidence.get("rejected_before_helpers") is True
            status["parser_cases"].append({"name": case["name"], "passed": passed,
                                           "exit_code": result_case.returncode, "report": evidence})
            print("Parser " + case["name"] + ": " + ("PASS" if passed else "FAIL"), flush=True)
        status["success"] = (result.returncode == 0 and native.get("success") is True
                             and all(case["passed"] for case in status["parser_cases"]))
        assembled = Path(native.get("map_path", ""))
        status["assembled_map_preserved_after_parser_cases"] = (assembled.is_file()
            and sha256(assembled) == manifest["output"]["sha256"]
            and assembled.stat().st_size == manifest["output"]["size"])
        status["success"] = status["success"] and status["assembled_map_preserved_after_parser_cases"]
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        status["error"] = str(error)
    finally:
        after = {name: {"path": str(path), "sha256": sha256(path), "file_bytes": path.stat().st_size}
                 for name, path in inputs.items()}
        status["inputs_after"] = after
        status["inputs_unchanged"] = before == after
        status["success"] = status["success"] and status["inputs_unchanged"]
        status["finished_at"] = datetime.now(timezone.utc).isoformat()
        write_json(output / "status.json", status)
    print(("PASS: " if status["success"] else "FAIL: ") + str(output / "status.json"), flush=True)
    if not status["success"]:
        print(status.get("error") or status.get("native_report", {}).get("error", "Inspect preserved logs"), file=sys.stderr)
    return 0 if status["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
