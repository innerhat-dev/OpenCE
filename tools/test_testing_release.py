"""Synthetic CI fixtures exercise selection, integrity and publication guards."""

import base64
import copy
import hashlib
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from tools import ci_build, testing_release as release


SHA = "a" * 40
TAG = "test-v0.3.0-net11"


class FixtureAPI:
    def __init__(self, root):
        self.sha = SHA
        self.claimed = False
        self.runs, self.artifacts, self.archives = {}, {}, {}
        for run_id, (workflow, outputs) in enumerate(release.WORKFLOWS.items(), 1):
            run = {"id": run_id, "head_sha": SHA, "head_branch": "main", "status": "completed",
                   "conclusion": "success", "event": "push", "path": ".github/workflows/" + workflow,
                   "repository": {"id": 42, "full_name": release.REPOSITORY},
                   "head_repository": {"id": 42, "full_name": release.REPOSITORY},
                   "created_at": "2026-10-03T00:00:00Z"}
            self.runs[workflow] = run
            for name in outputs:
                artifact_id = len(self.artifacts) + 10
                path = root / f"{artifact_id}.zip"
                if workflow == "macos-dmg.yml":
                    data = b"synthetic disk image"
                    files = {release.DMG: data, "README.txt": "Apple Silicon, macOS 26",
                             "BuildInfo.txt": "Source: " + SHA + "\n",
                             "SHA256SUMS": hashlib.sha256(data).hexdigest() + "  " + release.DMG + "\n"}
                elif "windows" in name:
                    files = {"halo.exe": b"synthetic exe", "SDL3.dll": b"synthetic dll"}
                elif "linux" in name:
                    files = {"halo": b"synthetic binary"}
                else:
                    files = {"app-release.apk": b"synthetic apk"}
                with zipfile.ZipFile(path, "w") as archive:
                    for filename, data in files.items():
                        archive.writestr(filename, data)
                artifact = {"id": artifact_id, "name": name, "expired": False,
                            "expires_at": "2099-01-01T00:00:00Z", "size_in_bytes": path.stat().st_size,
                            "digest": "sha256:" + release.digest(path),
                            "workflow_run": {"id": run_id, "head_sha": SHA, "head_branch": "main",
                                             "repository_id": 42, "head_repository_id": 42}}
                self.artifacts[name] = artifact
                self.archives[artifact_id] = path

    def get(self, path, *, missing_ok=False):
        if path == "git/ref/heads/main":
            return {"object": {"sha": self.sha}}
        if path.startswith(("git/ref/tags/", "releases/tags/")):
            return {"id": 1} if self.claimed else None
        if path.startswith("contents/"):
            return {"content": base64.b64encode(b"#define HALO_PORT_NETWORK_VERSION 11\n").decode()}
        if path.startswith("actions/workflows/"):
            return {"workflow_runs": [copy.deepcopy(self.runs[path.split("/")[2]])]}
        if path.startswith("actions/runs/"):
            if "/artifacts?" in path:
                name = path.split("name=")[1].split("&")[0]
                return {"artifacts": [copy.deepcopy(self.artifacts[name])] if name in self.artifacts else []}
            return copy.deepcopy(next(run for run in self.runs.values() if run["id"] == int(path.split("/")[2])))
        if path.startswith("actions/artifacts/"):
            return copy.deepcopy(next(a for a in self.artifacts.values() if a["id"] == int(path.split("/")[2])))
        raise AssertionError("Unexpected API request: " + path)

    def download(self, artifact_id, destination):
        shutil.copyfile(self.archives[artifact_id], destination)


class TestingReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.api = FixtureAPI(self.root)
        self.directory = self.root / "candidate"

    def prepare(self):
        return release.prepare(self.api, release.REPOSITORY, SHA, TAG, self.directory)

    def test_same_source_candidate_has_protocol_and_verifies(self):
        record = self.prepare()
        self.assertEqual(record["network_protocol"], 11)
        self.assertEqual(len(record["artifacts"]), 4)
        self.assertEqual(release.verify_candidate(self.api, release.REPOSITORY, SHA, TAG, self.directory), record)
        self.assertEqual({p.name for p in self.directory.iterdir()}, release.ASSETS | {"release-notes.md"})

    def test_runs_from_other_source_branch_repository_or_event_are_rejected(self):
        run = self.api.runs["build.yml"]
        for field, value in (("head_sha", "b" * 40), ("head_branch", "other"), ("conclusion", "failure"),
                             ("event", "pull_request"), ("head_repository", {"full_name": "someone/fork"})):
            with self.subTest(field=field):
                changed = dict(run, **{field: value})
                with self.assertRaises(RuntimeError):
                    release.validate_run(changed, "build.yml", SHA)

    def test_missing_expired_and_wrong_source_artifacts_fail(self):
        del self.api.artifacts["halo-linux-release"]
        with self.assertRaisesRegex(RuntimeError, "Expected one"):
            self.prepare()
        artifact = self.api.artifacts["halo-windows-release"]
        for changes in ({"expired": True}, {"expires_at": "2000-01-01T00:00:00Z"},
                        {"workflow_run": {"id": 999}}, {"digest": ""}):
            with self.subTest(changes=changes), self.assertRaises(RuntimeError):
                release.validate_artifact(dict(artifact, **changes), artifact["name"], self.api.runs["build.yml"], SHA)

    def test_downloaded_archive_hash_is_checked(self):
        self.api.artifacts["halo-macos-arm64-dmg"]["digest"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(RuntimeError, "checksum"):
            self.prepare()

    def test_mac_buildinfo_and_disk_image_hash_are_checked(self):
        for filename, value, expected in (("BuildInfo.txt", "Source: wrong\n", "BuildInfo"),
                                          ("SHA256SUMS", "wrong\n", "checksum")):
            with self.subTest(filename=filename):
                archive_path = self.root / (filename + ".zip")
                with zipfile.ZipFile(self.api.archives[10]) as original, zipfile.ZipFile(archive_path, "w") as output:
                    for name in original.namelist():
                        output.writestr(name, value if name == filename else original.read(name))
                destination = self.root / filename
                destination.mkdir()
                with self.assertRaisesRegex(RuntimeError, expected):
                    release.collect_mac(archive_path, destination, SHA)

    def test_restricted_and_escaping_archive_entries_are_rejected(self):
        for name in ("../escape", "/absolute", "maps/ui.map", "disc.ISO", "signing.p12"):
            with self.subTest(name=name):
                path = self.root / "unsafe.zip"
                with zipfile.ZipFile(path, "w") as archive:
                    archive.writestr(name, "synthetic")
                with self.assertRaises(RuntimeError):
                    release.validate_zip(path)

    def test_publication_recheck_refuses_advanced_main_claimed_tag_or_changed_asset(self):
        self.prepare()
        self.api.sha = "b" * 40
        with self.assertRaisesRegex(RuntimeError, "latest main"):
            release.verify_candidate(self.api, release.REPOSITORY, SHA, TAG, self.directory)
        self.api.sha, self.api.claimed = SHA, True
        with self.assertRaisesRegex(RuntimeError, "already exists"):
            release.verify_candidate(self.api, release.REPOSITORY, SHA, TAG, self.directory)
        self.api.claimed = False
        (self.directory / release.DMG).write_bytes(b"changed")
        with self.assertRaisesRegex(RuntimeError, "asset changed"):
            release.verify_candidate(self.api, release.REPOSITORY, SHA, TAG, self.directory)

    def test_fork_ci_cannot_offer_upstream_updates(self):
        environment = {"GITHUB_REPOSITORY": release.REPOSITORY, "GITHUB_REF": "refs/heads/main",
                       "GITHUB_RUN_NUMBER": "70", "HALO_BUILD_NUMBER": "999"}
        self.assertEqual(ci_build.update_build_number(environment), "0")
        environment["GITHUB_REPOSITORY"] = "cybersecurity/halo-ce-universal"
        self.assertEqual(ci_build.update_build_number(environment), "70")
        environment["GITHUB_REF"] = "refs/heads/feature"
        self.assertEqual(ci_build.update_build_number(environment), "0")

    def test_fork_android_apks_increment_install_code_without_enabling_updater(self):
        (self.root / ci_build.APKS["release"]).parent.mkdir(parents=True)
        (self.root / ci_build.APKS["release"]).write_bytes(b"fixture APK")
        for dependency in ("extract-xiso", "miniupnpc"):
            license = self.root / "port/third_party" / dependency / "LICENSE.TXT"
            if dependency == "miniupnpc":
                license = license.with_name("LICENSE")
            license.parent.mkdir(parents=True)
            license.write_text("fixture license")
        for number in ("70", "71"):
            commands = []
            def capture(command, cwd=None):
                commands.append((command, os.environ["HALO_BUILD_NUMBER"]))
            environment = {"GITHUB_REPOSITORY": release.REPOSITORY, "GITHUB_REF": "refs/heads/main",
                           "GITHUB_RUN_NUMBER": number, "HALO_BUILD_NUMBER": "999"}
            with self.subTest(number=number), patch.dict(os.environ, environment, clear=True), \
                    patch.object(ci_build, "ROOT", self.root), patch.object(ci_build, "run", capture), \
                    patch("sys.argv", ["ci_build.py", "android", "release"]):
                self.assertEqual(ci_build.main(), 0)
            gradle, updater_number = commands[-1]
            self.assertIn("-PhaloInstallBuildNumber=" + number, gradle)
            self.assertIn("assembleRelease", gradle)
            self.assertTrue(all(update == "0" for _, update in commands))
            self.assertEqual(updater_number, "0")
        for invalid in ("", "-1", "abc", "2100000001", "²"):
            with self.subTest(invalid=invalid):
                self.assertEqual(ci_build.android_install_build_number({"GITHUB_RUN_NUMBER": invalid}), "0")


if __name__ == "__main__":
    unittest.main()
