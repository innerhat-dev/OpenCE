"""Tests for explicit reviewed-helper staging; no Invader programs execute."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools import macos_content_tools as tools


class ContentToolsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.app = self.root / "Candidate.app"
        (self.app / "Contents/Resources").mkdir(parents=True)
        self.toolchain = self.root / "toolchain"
        (self.toolchain / "build").mkdir(parents=True)
        self.pins = json.loads(tools.PINS.read_text())
        self.pins["binaries"] = {}
        for name in ("extract", "build"):
            data = ("reviewed fixture " + name).encode()
            (self.toolchain / "build" / ("invader-" + name)).write_bytes(data)
            self.pins["binaries"][name] = hashlib.sha256(data).hexdigest()
        for path in self.pins["notices"].values():
            self.source_file(path, b"Fixture license and copyright notice\n")
        for path, marker in self.pins["header_notices"].values():
            self.source_file(path, ("unshipped header code\n" + marker + "\nlicense */\n").encode())
        self.source_file(self.pins["source_patch"], b"# fixture patched source\n")
        for crate in self.pins["cargo_crates"]:
            self.source_file(self.pins["cargo_registry"] + "/" + crate + "/LICENSE-MIT",
                             b"Fixture crate copyright\n")
        rust = self.root / (self.pins["rust_version"] + "-aarch64-apple-darwin")
        docs = rust / "share/doc/rust"
        (docs / "licenses").mkdir(parents=True)
        (docs / "COPYRIGHT-library.html").write_text("Fixture Rust copyright\n")
        for name in self.pins["rust_notices"]:
            (docs / "licenses" / name).write_text("Fixture Rust license\n")
        self.manifest = {key: self.pins[key] for key in (
            "invader_repository", "invader_commit", "riat_commit", "architecture")}
        self.manifest["rust_toolchain"] = str(rust / "bin")
        self.manifest["binaries"] = {name: {"sha256": digest, "path": "/untrusted/never-executed"}
                                     for name, digest in self.pins["binaries"].items()}
        self.write_manifest()
        self.pins_path = self.root / "pins.json"
        self.pins_path.write_text(json.dumps(self.pins))
        self.addCleanup(patch.stopall)
        patch.object(tools, "PINS", self.pins_path).start()
        self.commands = []
        self.capture = patch.object(tools, "_capture", side_effect=self.inspect).start()
        self.run = patch.object(tools.subprocess, "run", side_effect=self.sign).start()

    def source_file(self, path, data):
        target = self.toolchain / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return target

    def write_manifest(self):
        (self.toolchain / "source-manifest.json").write_text(json.dumps(self.manifest))

    def inspect(self, *command):
        self.commands.append(command)
        if command[0] == "/usr/bin/lipo":
            return "arm64"
        return str(command[-1]) + ":\n\t/usr/lib/libSystem.B.dylib (compatibility version 1.0.0, current version 1.0.0)"

    def sign(self, command, **kwargs):
        self.commands.append(tuple(command))
        if "--sign" in command:
            binary = Path(command[-1])
            binary.write_bytes(binary.read_bytes() + b" fixture signature")
        return subprocess.CompletedProcess(command, 0)

    def stage(self, **kwargs):
        return tools.stage_content_tools(self.app, self.toolchain, **kwargs)

    def test_two_helpers_sign_and_provenance_omit_machine_paths(self):
        binaries = self.stage()
        self.assertEqual([path.name for path in binaries], ["invader-extract", "invader-build"])
        self.assertTrue(all(path.stat().st_mode & 0o111 for path in binaries))
        provenance = (self.app / "Contents/Resources/ContentTools.json").read_text()
        self.assertNotIn(str(self.root), provenance)
        self.assertNotIn("/untrusted", provenance)
        self.assertFalse(json.loads(provenance)["fresh_ci_ready"])
        for name, record in json.loads(provenance)["binaries"].items():
            self.assertEqual(record["source_sha256"], self.pins["binaries"][name])
            binary = self.app / "Contents/Helpers" / ("invader-" + name)
            self.assertEqual(record["bundled_sha256"], hashlib.sha256(binary.read_bytes()).hexdigest())
        self.assertEqual({command[0] for command in self.commands},
                         {"/usr/bin/lipo", "/usr/bin/otool", "/usr/bin/codesign"})
        notice = self.app / "Contents/Resources/Licenses/Invader/bcdec.txt"
        self.assertNotIn("unshipped header code", notice.read_text())
        self.assertFalse(any(self.app.joinpath("Contents").glob(".content-tools-*")))

    def test_manifest_cannot_introduce_an_unreviewed_hash(self):
        self.manifest["binaries"]["extract"]["sha256"] = "0" * 64
        self.write_manifest()
        with self.assertRaisesRegex(RuntimeError, "unreviewed binary"):
            self.stage()
        self.assertFalse(self.commands)

    def test_binary_bytes_must_match_checked_in_pin(self):
        (self.toolchain / "build/invader-extract").write_bytes(b"different bytes")
        with self.assertRaisesRegex(RuntimeError, "checked-in pin"):
            self.stage()
        self.assertFalse(self.commands)

    def test_wrong_source_revision_refused(self):
        self.manifest["riat_commit"] = "0" * 40
        self.write_manifest()
        with self.assertRaisesRegex(RuntimeError, "riat_commit"):
            self.stage()
        self.assertFalse(self.commands)

    def test_non_arm64_refused_before_signing(self):
        self.capture.side_effect = lambda *command: "x86_64"
        with self.assertRaisesRegex(RuntimeError, "arm64"):
            self.stage()
        self.run.assert_not_called()

    def test_non_system_library_and_system_path_traversal_refused(self):
        for library in ("@rpath/unreviewed.dylib", "/opt/homebrew/lib/libz.dylib", "/usr/lib/../../tmp/tool.dylib"):
            with self.subTest(library=library):
                self.capture.side_effect = lambda *c: ("arm64" if c[0].endswith("lipo") else
                    "tool:\n\t" + library + " (compatibility version 1.0.0, current version 1.0.0)")
                with self.assertRaisesRegex(RuntimeError, "system libraries"):
                    self.stage()
        self.run.assert_not_called()

    def test_input_binary_symlink_is_refused(self):
        source = self.toolchain / "build/invader-extract"
        data = source.read_bytes()
        source.unlink()
        outside = self.root / "outside"
        outside.write_bytes(data)
        source.symlink_to(outside)
        with self.assertRaisesRegex(RuntimeError, "escapes"):
            self.stage()
        self.run.assert_not_called()

    def test_missing_notice_aborts_before_any_signing(self):
        (self.toolchain / self.pins["notices"]["GPL-3.0.txt"]).unlink()
        with self.assertRaises(FileNotFoundError):
            self.stage()
        self.run.assert_not_called()
        self.assertFalse((self.app / "Contents/Helpers").exists())

    def test_existing_destination_never_overwritten(self):
        existing = self.app / "Contents/Helpers"
        existing.mkdir()
        (existing / "prior").write_bytes(b"keep")
        with self.assertRaises(FileExistsError):
            self.stage()
        self.assertEqual((existing / "prior").read_bytes(), b"keep")
        self.assertFalse(self.commands)

    def test_failed_signature_leaves_no_published_additions(self):
        self.run.side_effect = subprocess.CalledProcessError(1, ["codesign"])
        with self.assertRaises(subprocess.CalledProcessError):
            self.stage()
        self.assertFalse((self.app / "Contents/Helpers").exists())
        self.assertFalse((self.app / "Contents/Resources/ContentTools.json").exists())
        self.assertFalse(any(self.app.joinpath("Contents").glob(".content-tools-*")))

    def test_raced_provenance_is_preserved_and_owned_helpers_cleaned(self):
        link = tools.os.link
        provenance = self.app / "Contents/Resources/ContentTools.json"

        def raced_link(source, destination):
            if destination == provenance:
                provenance.write_bytes(b"racing unrelated bytes")
            return link(source, destination)

        with patch.object(tools.os, "link", side_effect=raced_link):
            with self.assertRaises(FileExistsError):
                self.stage()
        self.assertEqual(provenance.read_bytes(), b"racing unrelated bytes")
        self.assertFalse((self.app / "Contents/Helpers").exists())
        self.assertFalse((self.app / "Contents/Resources/Licenses/Invader").exists())

    def test_partial_helper_publication_failure_cleans_only_owned_destinations(self):
        with patch.object(tools.os, "link", side_effect=OSError("fixture disk error")):
            with self.assertRaises(OSError):
                self.stage()
        self.assertFalse((self.app / "Contents/Helpers").exists())
        self.assertFalse((self.app / "Contents/Resources/ContentTools.json").exists())

    def test_linked_resources_cannot_write_outside_private_app(self):
        resources = self.app / "Contents/Resources"
        resources.rmdir()
        outside = self.root / "outside-resources"
        outside.mkdir()
        resources.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError, "private app"):
            self.stage()
        self.assertFalse(list(outside.iterdir()))
        self.assertFalse(self.commands)

    def test_release_signs_each_helper_with_runtime_and_timestamp(self):
        self.pins["fresh_ci_ready"] = True
        self.pins_path.write_text(json.dumps(self.pins))
        self.stage(sign_identity="Developer ID Application: Fixture", release=True)
        signing = [command for command in self.commands if "--sign" in command]
        self.assertEqual(len(signing), 2)
        for command in signing:
            self.assertIn("runtime", command)
            self.assertIn("--timestamp", command)
        verified = [command for command in self.commands if "--verify" in command]
        self.assertEqual(len(verified), 2)

    def test_release_refuses_adhoc_identity(self):
        with self.assertRaisesRegex(RuntimeError, "Developer ID"):
            self.stage(release=True)
        self.assertFalse(self.commands)

    def test_release_refuses_unfinished_prototype_even_with_signing_identity(self):
        with self.assertRaisesRegex(RuntimeError, "local-prototype only"):
            self.stage(sign_identity="Developer ID Application: Fixture", release=True)
        self.assertFalse(self.commands)

    def test_bundle_audit_verifies_binaries_provenance_and_required_notices(self):
        self.stage()
        self.assertTrue(tools.audit_content_tools(self.app))
        record_path = self.app / "Contents/Resources/ContentTools.json"
        original_record = record_path.read_bytes()
        for mutation in ("source-pin", "missing-notice", "bundled-helper", "notice-bytes"):
            with self.subTest(mutation=mutation):
                changed = json.loads(original_record)
                victim, original = None, None
                if mutation == "source-pin":
                    changed["binaries"]["build"]["source_sha256"] = "0" * 64
                elif mutation == "missing-notice":
                    del changed["notices_sha256"]["GPL-3.0.txt"]
                else:
                    relative = "Helpers/invader-build" if mutation == "bundled-helper" else "Resources/Licenses/Invader/GPL-3.0.txt"
                    victim = self.app / "Contents" / relative
                    original = victim.read_bytes()
                    victim.write_bytes(original + b"unexpected bytes")
                record_path.write_text(json.dumps(changed))
                try:
                    with self.assertRaises(RuntimeError):
                        tools.audit_content_tools(self.app)
                finally:
                    if victim:
                        victim.write_bytes(original)
                    record_path.write_bytes(original_record)
        self.assertTrue(tools.audit_content_tools(self.app))


if __name__ == "__main__":
    unittest.main()
