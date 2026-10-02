"""Exercise bundle cleanup in temporary folders, without macOS side effects."""
from contextlib import redirect_stdout
import io
from pathlib import Path
import plistlib
import tempfile
import unittest
from unittest.mock import patch

from tools import macos_build


BUNDLE_ID = "local.halo.ce-universal"


def make_app(path, identifier=BUNDLE_ID, marker=b"fixture"):
    contents = path / "Contents"
    contents.mkdir(parents=True)
    (contents / "Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": identifier}))
    (contents / "payload").write_bytes(marker)
    return path


class MacOSInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="halo-installer-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.build = self.root / "build"
        self.macos = self.build / "macos"
        self.applications = self.root / "Applications"
        self.addCleanup(patch.stopall)
        patch.object(macos_build, "ROOT", self.root).start()
        patch.object(macos_build, "BUILD", self.macos).start()
        self.commands = patch.object(macos_build, "run").start()
        self.unregister = patch.object(macos_build.subprocess, "run").start()

    def install(self, source):
        with redirect_stdout(io.StringIO()):
            return macos_build.install_app(source, self.applications)

    def test_archives_renamed_same_id_apps_across_generated_builds(self):
        source = make_app(self.macos / "Halo CE Universal.app", marker=b"current")
        pilot = make_app(self.build / "community-maps/pilot/Halo Xbox Map Pilot.app", marker=b"pilot")
        other_pilot = make_app(self.macos / "checks/Halo Xbox Map Pilot.app", marker=b"other pilot")
        source_helper = make_app(source / "Contents/Helpers/Helper.app", marker=b"nested helper")
        unrelated = make_app(self.build / "tests/Halo Custom.app", "local.halo.test")
        unrelated_helper = make_app(unrelated / "Contents/Helpers/Helper.app")
        installed = self.install(source)

        self.assertEqual(installed, self.applications / source.name)
        self.assertEqual((installed / "Contents/payload").read_bytes(), b"current")
        self.assertTrue((installed / source_helper.relative_to(source)).is_dir())
        self.assertTrue(unrelated.is_dir())
        self.assertTrue(unrelated_helper.is_dir())
        generations = list((self.macos / "app-backups.noindex").iterdir())
        self.assertEqual(len(generations), 1)
        for original, marker in ((source, b"current"), (pilot, b"pilot"), (other_pilot, b"other pilot")):
            archived = generations[0] / original.relative_to(self.build)
            archived = archived.with_name(archived.name + ".backup")
            self.assertFalse(original.exists())
            self.assertEqual((archived / "Contents/payload").read_bytes(), marker)
        archived_source = generations[0] / "macos/Halo CE Universal.app.backup"
        self.assertTrue((archived_source / source_helper.relative_to(source)).is_dir())
        self.assertEqual({Path(call.args[0][2]) for call in self.unregister.call_args_list},
                         {source, pilot, other_pilot})
        self.assertEqual([call.args[0] for call in self.commands.call_args_list],
                         ["codesign", Path("/System/Library/Frameworks/CoreServices.framework/Frameworks/"
                                           "LaunchServices.framework/Support/lsregister"), "mdimport"])
        self.assertEqual(self.commands.call_args_list[-2].args[1:], ("-f", installed))

    def test_preserves_archives_packages_and_external_symlinks_on_repeat_install(self):
        source = make_app(self.macos / "Halo CE Universal.app")
        archived = [
            make_app(self.build / "app-backups.noindex/old/Pilot.app"),
            make_app(self.macos / "app-backups.noindex/old/Pilot.app"),
            make_app(self.build / "old/Pilot.app.backup/Contents/Helpers/Helper.app"),
        ]
        external = make_app(self.root / "external/Halo.app")
        (self.build / "Alias.app").symlink_to(external, target_is_directory=True)
        (self.build / "linked-folder").symlink_to(external.parent, target_is_directory=True)
        self.install(source)
        first_archive = next((self.macos / "app-backups.noindex").glob("*/macos/Halo CE Universal.app.backup"))
        nested = make_app(first_archive / "Contents/Helpers/Helper.app")
        source = make_app(source, marker=b"second")
        self.unregister.reset_mock()
        installed = self.install(source)

        self.assertEqual((installed / "Contents/payload").read_bytes(), b"second")
        for preserved in [*archived, first_archive, nested, external]:
            self.assertTrue(preserved.is_dir(), preserved)
        self.assertTrue((self.build / "Alias.app").is_symlink())
        self.assertTrue((self.build / "linked-folder").is_symlink())
        self.assertEqual({Path(call.args[0][2]) for call in self.unregister.call_args_list},
                         {installed, source})
        previous = list(self.applications.glob(".halo-previous-*/Halo CE Universal.app.backup"))
        self.assertEqual(len(previous), 1)
        self.assertEqual((previous[0] / "Contents/payload").read_bytes(), b"fixture")

    def test_incomplete_or_invalid_bundles_do_not_block_installation(self):
        source = make_app(self.macos / "Halo CE Universal.app")
        missing = self.build / "Missing.app"
        missing.mkdir()
        malformed = make_app(self.build / "Malformed.app")
        (malformed / "Contents/Info.plist").write_bytes(b"not a plist")
        incomplete_xml = make_app(self.build / "IncompleteXML.app")
        (incomplete_xml / "Contents/Info.plist").write_bytes(b'<?xml version="1.0"?><plist><dict>')
        wrong_type = make_app(self.build / "Array.app")
        (wrong_type / "Contents/Info.plist").write_bytes(plistlib.dumps([BUNDLE_ID]))
        self.install(source)
        for untouched in (missing, malformed, incomplete_xml, wrong_type):
            self.assertTrue(untouched.is_dir())
        self.assertEqual(len(self.unregister.call_args_list), 1)


if __name__ == "__main__":
    unittest.main()
