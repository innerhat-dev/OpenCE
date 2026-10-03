"""Synthetic map fixtures test delivery identity, bounds and source preservation."""
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from tools import map_catalog


def synthetic_map(path, *, name=None, version=5, build="01.10.12.2276", kind=1,
                  declared=4096, tag_offset=2048, tag_bytes=2048):
    data = bytearray(4096)
    data[:4] = b"daeh"
    struct.pack_into("<II", data, 4, version, declared)
    struct.pack_into("<II", data, 16, tag_offset, tag_bytes)
    name = name if name is not None else path.stem
    data[32:32 + len(name)] = name.encode()
    data[64:64 + len(build)] = build.encode()
    struct.pack_into("<H", data, 96, kind)
    data[2044:2048] = b"toof"
    path.write_bytes(data)
    return bytes(data)


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "Downrush.map"
        self.bytes = synthetic_map(self.source)
        self.output = self.root / "output"

    def test_exact_native_catalog_objects_and_unchanged_source(self):
        result = map_catalog.prepare_catalog([self.source], self.output, ["DOWNRUSH"])
        checksum = hashlib.sha256(self.bytes).hexdigest()
        key = f"maps/sha256/{checksum}/downrush.map"
        self.assertEqual(result, {"schema_version": 1, "profile": "stock-xbox-ntsc", "maps": [{
            "id": "downrush", "sha256": checksum, "file_bytes": len(self.bytes), "cache_version": 5,
            "cache_build": "01.10.12.2276", "scenario_type": 1, "object_key": key, "prefetch": True}]})
        self.assertEqual(json.loads((self.output / "catalog.json").read_text()), result)
        self.assertEqual((self.output / key).read_bytes(), self.bytes)
        self.assertEqual(self.source.read_bytes(), self.bytes)

    def test_compressed_transfer_can_be_smaller_than_declared_cache(self):
        synthetic_map(self.source, declared=1 << 20, tag_offset=500000, tag_bytes=300000)
        result = map_catalog.prepare_catalog([self.source], self.output)
        self.assertEqual(result["maps"][0]["file_bytes"], 4096)

    def test_transfer_cap_and_exact_cache_tag_limits(self):
        synthetic_map(self.source, declared=128 << 20, tag_offset=100 << 20, tag_bytes=22 << 20)
        self.assertEqual(map_catalog.validate_map(self.source)["tag_bytes"], 22 << 20)
        with self.source.open("r+b") as stream:
            stream.truncate((128 << 20) + 1)
        with self.assertRaisesRegex(ValueError, "transfer size"):
            map_catalog.prepare_catalog([self.source], self.output)
        self.assertFalse(self.output.exists())

    def test_wrong_cache_identity_format_region_type_or_bounds_fail(self):
        cases = ({"name": "other"}, {"name": "../escape"}, {"version": 7}, {"build": "01.01.14.2342"},
                 {"kind": 0}, {"declared": 134217729}, {"declared": 2047}, {"tag_offset": 2047},
                 {"tag_offset": 4090, "tag_bytes": 10}, {"declared": 134217728, "tag_bytes": 23068673})
        for values in cases:
            with self.subTest(values=values):
                synthetic_map(self.source, **values)
                with self.assertRaises(ValueError):
                    map_catalog.prepare_catalog([self.source], self.output)
                self.assertFalse(self.output.exists())

    def test_reserved_names_case_collisions_and_unknown_prefetch_fail(self):
        for name in ("ui", "A10", "BloodGulch"):
            source = self.root / (name + ".map")
            synthetic_map(source)
            with self.subTest(name=name), self.assertRaises(ValueError):
                map_catalog.prepare_catalog([source], self.output)
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            map_catalog.prepare_catalog([self.source, self.source], self.output)
        other_folder = self.root / "other"
        other_folder.mkdir()
        other = other_folder / "downrush.MAP"
        synthetic_map(other)
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            map_catalog.prepare_catalog([self.source, other], self.output)
        with self.assertRaisesRegex(ValueError, "Prefetch"):
            map_catalog.prepare_catalog([self.source], self.output, ["missing"])

    def test_existing_output_and_racing_empty_directory_are_preserved(self):
        self.output.mkdir()
        with self.assertRaises(FileExistsError):
            map_catalog.prepare_catalog([self.source], self.output)
        staged = self.root / "staged"
        staged.mkdir()
        (staged / "marker").write_text("candidate")
        with self.assertRaises(OSError):
            map_catalog.publish_directory(staged, self.output)
        self.assertEqual(list(self.output.iterdir()), [])
        self.assertTrue((staged / "marker").exists())

    def test_copy_failure_and_changed_source_clean_staging(self):
        with patch.object(map_catalog.shutil, "copyfile", side_effect=OSError("disk full")):
            with self.assertRaisesRegex(OSError, "disk full"):
                map_catalog.prepare_catalog([self.source], self.output)
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.root.glob(".output-*.partial")), [])
        self.assertEqual(self.source.read_bytes(), self.bytes)
        original_copy = map_catalog.shutil.copyfile
        def corrupt_copy(source, destination):
            original_copy(source, destination)
            with destination.open("ab") as stream:
                stream.write(b"changed")
        with patch.object(map_catalog.shutil, "copyfile", side_effect=corrupt_copy):
            with self.assertRaisesRegex(ValueError, "source changed"):
                map_catalog.prepare_catalog([self.source], self.output)
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.root.glob(".output-*.partial")), [])
        self.assertEqual(self.source.read_bytes(), self.bytes)


if __name__ == "__main__":
    unittest.main()
