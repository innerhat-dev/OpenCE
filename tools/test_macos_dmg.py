"""Packaging failure boundaries, without mounting disks or driving Finder."""
from pathlib import Path
import shutil
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from tools.macos_dmg import create_dmg


class InstallerBoundary(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.app = self.root / "Halo OG.app"
        self.app.mkdir()
        (self.app / "engine").write_bytes(b"verified source")
        self.output = self.root / "Halo-OG.dmg"

    def package_with(self, builder):
        with patch.dict("sys.modules", {"dmgbuild": SimpleNamespace(build_dmg=builder)}), \
                patch("tools.macos_dmg.subprocess.run"):
            create_dmg(self.app, self.output)

    def test_existing_output_is_preserved(self):
        self.output.write_bytes(b"existing installer")
        with self.assertRaisesRegex(RuntimeError, "already exists"):
            create_dmg(self.app, self.output)
        self.assertEqual(self.output.read_bytes(), b"existing installer")

    def test_raced_output_is_preserved(self):
        def builder(filename, volume, settings):
            Path(filename).write_bytes(b"new installer")
            self.output.write_bytes(b"other installer")
        with self.assertRaises(FileExistsError):
            self.package_with(builder)
        self.assertEqual(self.output.read_bytes(), b"other installer")

    def test_incomplete_app_copy_cannot_finish(self):
        def builder(filename, volume, settings):
            mount = self.root / "mount"
            (mount / self.app.name).mkdir(parents=True)
            settings["create_hook"](str(mount), settings)
            self.fail("An incomplete app was accepted")
        with self.assertRaisesRegex(RuntimeError, "differs"):
            self.package_with(builder)
        self.assertFalse(self.output.exists())

    def test_signature_failure_cannot_finish(self):
        import subprocess
        def builder(filename, volume, settings):
            mount = self.root / "mount"
            shutil.copytree(self.app, mount / self.app.name)
            settings["create_hook"](str(mount), settings)
            self.fail("An invalid signature was accepted")
        def run(command, **kwargs):
            if command[0] == "codesign":
                raise subprocess.CalledProcessError(1, command)
        with patch.dict("sys.modules", {"dmgbuild": SimpleNamespace(build_dmg=builder)}), \
                patch("tools.macos_dmg.subprocess.run", side_effect=run), \
                self.assertRaises(subprocess.CalledProcessError):
            create_dmg(self.app, self.output)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
