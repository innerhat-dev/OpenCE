#!/usr/bin/env python3
"""Collect CI outputs read-only; publish only with the explicit publish command.

The manual testing-release workflow separates these commands into jobs with
read-only and write tokens. No rebuild, signing identity or game data is used.
"""

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import tempfile
from urllib.parse import quote, urlencode
import zipfile


REPOSITORY = "pfista/halo-ce-universal"
DMG = "Halo-CE-Universal-macos-arm64.dmg"
WORKFLOWS = {
    "macos-dmg.yml": {"halo-macos-arm64-dmg": DMG},
    "build.yml": {f"halo-{platform}-release": f"halo-{platform}-release.zip"
                  for platform in ("windows", "linux", "android")},
}
MAC_FILES = {DMG, "README.txt", "BuildInfo.txt", "SHA256SUMS"}
ASSETS = {DMG, "macos-README.txt", "macos-BuildInfo.txt", "SHA256SUMS",
          "provenance.json", *(f"halo-{p}-release.zip" for p in ("windows", "linux", "android"))}


class GitHub:
    def __init__(self, repository):
        self.prefix = f"repos/{repository}/"

    def get(self, path, *, missing_ok=False):
        result = subprocess.run(["gh", "api", self.prefix + path],
                                capture_output=True, text=True)
        if result.returncode:
            if missing_ok and "(HTTP 404)" in result.stderr:
                return None
            raise RuntimeError(f"GitHub read failed for {path}: {result.stderr.strip()}")
        return json.loads(result.stdout)

    def download(self, artifact_id, destination):
        with destination.open("xb") as output:
            result = subprocess.run(["gh", "api", self.prefix + f"actions/artifacts/{artifact_id}/zip"],
                                    stdout=output, stderr=subprocess.PIPE, text=False)
        if result.returncode:
            raise RuntimeError(f"Artifact {artifact_id} download failed")


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def validate_inputs(repository, sha, tag):
    if repository != REPOSITORY:
        raise RuntimeError("Testing publication is limited to " + REPOSITORY)
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise RuntimeError("Use a full source commit SHA")
    if not re.fullmatch(r"test-[A-Za-z0-9][A-Za-z0-9._-]{0,79}", tag) or ".." in tag or tag.endswith("."):
        raise RuntimeError("Use a new test- tag with letters, digits, dots, underscores or hyphens")


def check_main_and_tag(api, sha, tag):
    if api.get("git/ref/heads/main")["object"]["sha"] != sha:
        raise RuntimeError("The selected source is no longer latest main; wait for its builds and dispatch again")
    for path in ("git/ref/tags/" + quote(tag, safe=""), "releases/tags/" + quote(tag, safe="")):
        if api.get(path, missing_ok=True) is not None:
            raise RuntimeError("The requested tag or release already exists; choose a new testing tag")


def source_protocol(api, sha):
    source = api.get("contents/port/linux/include/halo_port_limits.h?ref=" + sha)
    text = base64.b64decode(source["content"]).decode()
    match = re.search(r"^#define HALO_PORT_NETWORK_VERSION (\d+)$", text, re.MULTILINE)
    if not match:
        raise RuntimeError("Selected source has no recognizable network protocol version")
    return int(match[1])


def validate_run(run, workflow, sha):
    if (run.get("head_sha") != sha or run.get("head_branch") != "main"
            or run.get("status") != "completed" or run.get("conclusion") != "success"
            or run.get("event") not in {"push", "workflow_dispatch"}
            or run.get("path", "").split("@")[0] != ".github/workflows/" + workflow
            or run.get("repository", {}).get("full_name") != REPOSITORY
            or run.get("head_repository", {}).get("full_name") != REPOSITORY):
        raise RuntimeError("Build run does not belong to successful same-source main CI")


def select_run(api, workflow, sha):
    query = urlencode({"branch": "main", "head_sha": sha, "status": "success", "per_page": 100})
    runs = api.get(f"actions/workflows/{workflow}/runs?{query}")["workflow_runs"]
    valid = []
    for run in runs:
        try:
            validate_run(run, workflow, sha)
        except RuntimeError:
            continue
        valid.append(run)
    if not valid:
        raise RuntimeError(f"No successful {workflow} run for latest main {sha}")
    return max(valid, key=lambda run: (run["created_at"], run["id"]))


def validate_artifact(artifact, name, run, sha):
    origin = artifact.get("workflow_run", {})
    expiry = datetime.fromisoformat(artifact["expires_at"].replace("Z", "+00:00"))
    if (artifact.get("name") != name or artifact.get("expired") is not False
            or expiry <= datetime.now(timezone.utc) or artifact.get("size_in_bytes", 0) <= 0
            or origin.get("id") != run["id"] or origin.get("head_branch") != "main"
            or origin.get("head_sha") != sha
            or origin.get("repository_id") != run["repository"]["id"]
            or origin.get("head_repository_id") != run["repository"]["id"]
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", artifact.get("digest", ""))):
        raise RuntimeError(f"Missing, expired or wrong-source artifact: {name}")


def select_artifact(api, name, run, sha):
    # Query by exact name; duplicates are an error instead of an ambiguous choice.
    query = urlencode({"name": name, "per_page": 100})
    found = api.get(f"actions/runs/{run['id']}/artifacts?{query}")["artifacts"]
    if len(found) != 1:
        raise RuntimeError(f"Expected one {name} artifact in run {run['id']}")
    validate_artifact(found[0], name, run, sha)
    return found[0]


def validate_zip(path):
    with zipfile.ZipFile(path) as archive:
        names = set()
        for item in archive.infolist():
            name = PurePosixPath(item.filename)
            mode = item.external_attr >> 16
            if (not item.filename or item.filename in names or name.is_absolute()
                    or ".." in name.parts or "\\" in item.filename or ":" in item.filename
                    or stat.S_ISLNK(mode)
                    or name.suffix.lower() in {".map", ".iso", ".xiso", ".xbe", ".p12", ".pfx", ".pem"}):
                raise RuntimeError("Unsafe or restricted file in build archive: " + item.filename)
            names.add(item.filename)
        if not names or archive.testzip() is not None:
            raise RuntimeError("Empty or corrupt build archive")
    return names


def collect_mac(archive_path, directory, sha):
    if validate_zip(archive_path) != MAC_FILES:
        raise RuntimeError("Unexpected files in macOS DMG artifact")
    with zipfile.ZipFile(archive_path) as archive:
        build_info = archive.read("BuildInfo.txt").decode()
        if f"Source: {sha}\n" not in build_info:
            raise RuntimeError("The packaged Mac BuildInfo source does not match CI")
        for source, target in ((DMG, DMG), ("README.txt", "macos-README.txt"),
                               ("BuildInfo.txt", "macos-BuildInfo.txt")):
            with archive.open(source) as input_file, (directory / target).open("xb") as output:
                shutil.copyfileobj(input_file, output)
        if archive.read("SHA256SUMS").decode().strip() != f"{digest(directory / DMG)}  {DMG}":
            raise RuntimeError("The packaged DMG does not match its CI checksum")


def check_platform_archive(path, name):
    names = validate_zip(path)
    required = {"halo-windows-release": {"halo.exe", "SDL3.dll"},
                "halo-linux-release": {"halo"}}
    if not required.get(name, set()).issubset(names):
        raise RuntimeError("Incomplete platform artifact: " + name)
    if name == "halo-android-release" and not any(file.endswith(".apk") for file in names):
        raise RuntimeError("Android artifact has no APK")


def release_notes(record):
    url = "https://github.com/" + record["repository"]
    return (f"Testing build `{record['tag']}` from [{record['sha']}]({url}/commit/{record['sha']}).\n\n"
            f"Network protocol: **{record['network_protocol']}**.\n\n"
            "Mac, Windows, Linux and Android assets use the same source revision. "
            "Supply your own original Xbox Halo game data. No maps or disc images are included.\n\n"
            "The Apple Silicon DMG is ad-hoc signed and unnotarized; automatic updates are disabled. "
            "See macos-README.txt for the required macOS version and first-launch instructions. "
            "Linux requires the 32-bit runtime dependencies documented in port/linux/README.md.\n\n"
            "Check SHA256SUMS before installing. provenance.json records workflow runs, artifact IDs "
            "and hashes. These are test builds; cross-platform play has not been established by CI.\n")


def prepare(api, repository, sha, tag, directory):
    check_main_and_tag(api, sha, tag)
    if directory.exists():
        raise RuntimeError("Candidate directory already exists; choose a fresh path")
    selected = []
    for workflow, outputs in WORKFLOWS.items():
        run = select_run(api, workflow, sha)
        for name, output in outputs.items():
            artifact = select_artifact(api, name, run, sha)
            selected.append((workflow, run, artifact, output))
    directory.mkdir(parents=True)
    record = {"repository": repository, "sha": sha, "tag": tag,
              "network_protocol": source_protocol(api, sha), "artifacts": [], "files": {}}
    with tempfile.TemporaryDirectory(prefix="halo-testing-release-") as temporary:
        for workflow, run, artifact, output in selected:
            archive = Path(temporary) / f"{artifact['id']}.zip"
            api.download(artifact["id"], archive)
            if "sha256:" + digest(archive) != artifact["digest"]:
                raise RuntimeError("Downloaded artifact checksum does not match GitHub")
            if workflow == "macos-dmg.yml":
                collect_mac(archive, directory, sha)
            else:
                check_platform_archive(archive, artifact["name"])
                shutil.copyfile(archive, directory / output)
            record["artifacts"].append({"workflow": workflow, "run_id": run["id"],
                "artifact_id": artifact["id"], "name": artifact["name"], "digest": artifact["digest"]})
    record["files"] = {path.name: digest(path) for path in sorted(directory.iterdir())}
    (directory / "provenance.json").write_text(json.dumps(record, indent=2) + "\n")
    (directory / "SHA256SUMS").write_text("".join(
        f"{digest(path)}  {path.name}\n" for path in sorted(directory.iterdir()) if path.name != "SHA256SUMS"))
    (directory / "release-notes.md").write_text(release_notes(record))
    return record


def verify_candidate(api, repository, sha, tag, directory):
    check_main_and_tag(api, sha, tag)
    record = json.loads((directory / "provenance.json").read_text())
    if (record.get("repository"), record.get("sha"), record.get("tag")) != (repository, sha, tag):
        raise RuntimeError("Prepared source or testing tag changed")
    if record.get("network_protocol") != source_protocol(api, sha):
        raise RuntimeError("Prepared network protocol does not match selected source")
    if {path.name for path in directory.iterdir()} != ASSETS | {"release-notes.md"}:
        raise RuntimeError("Prepared asset list changed")
    expected_files = ASSETS - {"provenance.json", "SHA256SUMS"}
    if set(record["files"]) != expected_files:
        raise RuntimeError("Prepared file provenance is incomplete")
    for name, checksum in record["files"].items():
        if digest(directory / name) != checksum:
            raise RuntimeError("Prepared asset changed: " + name)
    expected_sums = "".join(f"{digest(directory / name)}  {name}\n" for name in sorted(ASSETS - {"SHA256SUMS"}))
    if (directory / "SHA256SUMS").read_text() != expected_sums:
        raise RuntimeError("Prepared checksums changed")
    if (directory / "release-notes.md").read_text() != release_notes(record):
        raise RuntimeError("Prepared release notes changed")
    expected = {(workflow, name) for workflow, outputs in WORKFLOWS.items() for name in outputs}
    if len(record["artifacts"]) != len(expected) or {
            (item["workflow"], item["name"]) for item in record["artifacts"]} != expected:
        raise RuntimeError("Prepared artifact provenance is incomplete")
    for item in record["artifacts"]:
        run = api.get(f"actions/runs/{item['run_id']}")
        validate_run(run, item["workflow"], sha)
        artifact = api.get(f"actions/artifacts/{item['artifact_id']}")
        validate_artifact(artifact, item["name"], run, sha)
        if artifact["digest"] != item["digest"]:
            raise RuntimeError("GitHub artifact checksum changed")
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "verify", "publish"))
    parser.add_argument("--repository", default=REPOSITORY)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    validate_inputs(args.repository, args.sha, args.tag)
    api = GitHub(args.repository)
    if args.command == "prepare":
        prepare(api, args.repository, args.sha, args.tag, args.directory)
        print("Prepared read-only candidate: " + str(args.directory))
    else:
        verify_candidate(api, args.repository, args.sha, args.tag, args.directory)
        if args.command == "publish":
            # Creating the ref fails if another caller claimed the tag since
            # verification. Never reuse or move an existing tag.
            subprocess.run(["gh", "api", f"repos/{args.repository}/git/refs", "--method", "POST", "--input", "-"],
                input=json.dumps({"ref": "refs/tags/" + args.tag, "sha": args.sha}), text=True, check=True,
                stdout=subprocess.DEVNULL)
            subprocess.run(["gh", "release", "create", args.tag, "--repo", args.repository,
                "--verify-tag", "--prerelease", "--latest=false",
                "--title", "Testing " + args.tag, "--notes-file", str(args.directory / "release-notes.md"),
                *(str(args.directory / name) for name in sorted(ASSETS))], check=True)
            print(f"DMG: https://github.com/{args.repository}/releases/download/{args.tag}/{DMG}")
        else:
            print("Verified candidate; nothing published")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, KeyError, ValueError, OSError, zipfile.BadZipFile, subprocess.CalledProcessError) as error:
        raise SystemExit("Testing release failed: " + str(error))
