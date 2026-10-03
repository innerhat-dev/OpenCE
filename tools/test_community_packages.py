"""Isolated fixtures for community-package integrity and publication boundaries.

These tests never build or install an app, read user preferences, or contact a
network service. Tag bytes are synthetic; the separate Downrush acceptance run
must prove the real pinned Invader reconstruction hash.
"""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools import community_packages as packages
from tools.community_maps import NTSC_BUILD, POLICY
from tools.test_map_catalog import synthetic_map


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_files(root, files):
    root.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def tree_bytes(root):
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in root.rglob("*") if p.is_file()}


class CommunityPackageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="halo-community-package-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.original = self.root / "original-stock-tags"
        self.patched = self.root / "patched-stock-tags"
        self.tags = self.root / "prepared-tags"
        self.data = self.root / "prepared-data"
        self.maps = self.root / "stock-maps"
        self.expected = self.root / "downrush.map"
        self.package = self.root / "downrush.hogpkg"
        self.destination = self.root / "materialized"
        self.unchanged = "weapons/pistol/pistol.weapon"
        self.modified = "weapons/rifle/rifle.weapon"
        self.override = "globals/globals.globals"
        self.original_bytes = {
            self.unchanged: b"UNCHANGED-ORIGINAL-ASSET\0" * 20,
            self.modified: b"ORIGINAL-RIFLE-ASSET\0" * 20,
            self.override: b"ORIGINAL-GLOBALS-ASSET\0" * 20,
        }
        self.tag_bytes = {
            self.unchanged: self.original_bytes[self.unchanged],
            self.modified: self.original_bytes[self.modified][:-1] + b"!",
            "levels/test/downrush/downrush.scenario": b"COMMUNITY-SCENARIO\0" * 20,
            "custom/texture.bitmap": b"COMMUNITY-BITMAP\0" * 20,
        }
        self.patched_bytes = dict(self.original_bytes)
        self.patched_bytes[self.override] = b"COMPATIBILITY-GLOBALS\0" * 20
        self.data_bytes = {"levels/test/downrush/scripts/cleanup.hsc": b"(script startup cleanup)\n"}
        write_files(self.original, self.original_bytes)
        write_files(self.patched, self.patched_bytes)
        write_files(self.tags, self.tag_bytes)
        write_files(self.data, self.data_bytes)
        self.maps.mkdir()
        for name, kind in (("bloodgulch", 1), ("a10", 0), ("ui", 2)):
            synthetic_map(self.maps / (name + ".map"), kind=kind)
        self.expected_bytes = synthetic_map(self.expected)
        self.toolchain = self.root / "invader-toolchain.json"
        self.toolchain.write_text(json.dumps({
            "invader_commit": json.loads(POLICY.read_text())["invader_commit"],
            "binaries": {
                "extract": {"sha256": sha(b"fake-extract")},
                "build": {"sha256": sha(b"fake-build")},
            },
        }))
        self.sources_before = self.source_snapshot()

    def source_snapshot(self):
        return {name: tree_bytes(path) for name, path in (
            ("original", self.original), ("patched", self.patched),
            ("tags", self.tags), ("data", self.data), ("maps", self.maps))}

    def prepare(self):
        return packages.prepare_package(
            prepared_tags=self.tags, prepared_data=self.data,
            original_stock_tags=self.original, patched_stock_tags=self.patched,
            stock_maps=self.maps, expected_map=self.expected,
            scenario="levels/test/downrush/downrush",
            toolchain_manifest=self.toolchain, destination=self.package)

    def payload(self):
        raw = self.package.read_bytes()
        _, length = packages.HEADER.unpack_from(raw)
        return raw[packages.HEADER.size + length:]

    def forged(self, manifest, payload=None, name="forged.hogpkg", encoded=None):
        encoded = encoded if encoded is not None else json.dumps(manifest).encode()
        payload = self.payload() if payload is None else payload
        path = self.root / name
        path.write_bytes(packages.HEADER.pack(packages.MAGIC, len(encoded)) + encoded + payload)
        return path

    def assert_rejected_without_materialization(self, manifest, *, payload=None):
        forged = self.forged(manifest, payload=payload)
        with self.assertRaises(packages.PackageError):
            packages.materialize_package(package=forged,
                                         original_stock_tags=self.original,
                                         destination=self.destination)
        self.assertFalse(self.destination.exists())
        self.assertEqual(self.source_snapshot(), self.sources_before)

    def test_whole_unchanged_assets_only_and_exact_materialization(self):
        manifest = self.prepare()
        records = {(entry["tree"], entry["path"]): entry for entry in manifest["files"]}
        unchanged = records[("tags", self.unchanged)]
        self.assertEqual((unchanged["kind"], unchanged["classification"]),
                         ("stock-reference", "unchanged-stock"))
        self.assertEqual(unchanged["sha256"], sha(self.original_bytes[self.unchanged]))
        modified = records[("tags", self.modified)]
        self.assertEqual((modified["kind"], modified["classification"]),
                         ("literal", "modified-or-different-stock"))
        self.assertEqual(modified["size"], len(self.tag_bytes[self.modified]))
        self.assertEqual(self.payload()[modified["offset"]:modified["offset"] + modified["size"]],
                         self.tag_bytes[self.modified])
        override = records[("stock-overrides", self.override)]
        self.assertEqual((override["kind"], override["classification"]),
                         ("literal", "compatibility-modified-stock"))
        self.assertEqual(override["original_sha256"], sha(self.original_bytes[self.override]))
        self.assertEqual(override["size"], len(self.patched_bytes[self.override]))
        self.assertNotIn(self.original_bytes[self.unchanged], self.payload())
        self.assertEqual(packages.read_package(self.package), manifest)
        result = packages.materialize_package(package=self.package,
                                             original_stock_tags=self.original,
                                             destination=self.destination)
        self.assertEqual(result, manifest)
        self.assertEqual(tree_bytes(self.destination / "tags"), self.tag_bytes)
        self.assertEqual(tree_bytes(self.destination / "data"), self.data_bytes)
        self.assertEqual(tree_bytes(self.destination / "stock"), self.patched_bytes)
        self.assertEqual(self.source_snapshot(), self.sources_before)
        self.assertEqual(self.expected.read_bytes(), self.expected_bytes)

    def test_reconstruction_identity_pins_complete_stock_maps(self):
        manifest = self.prepare()
        self.assertEqual((manifest["profile"], manifest["cache_build"]),
                         ("stock-xbox-ntsc", NTSC_BUILD))
        self.assertEqual(manifest["output"]["sha256"], sha(self.expected_bytes))
        self.assertEqual(manifest["output"]["size"], len(self.expected_bytes))
        self.assertEqual([item["name"] for item in manifest["stock_inputs"]],
                         ["bloodgulch", "a10", "ui"])
        for item in manifest["stock_inputs"]:
            raw = (self.maps / (item["name"] + ".map")).read_bytes()
            self.assertEqual((item["size"], item["sha256"]), (len(raw), sha(raw)))

    def test_compressed_cache_declared_length_can_exceed_transfer_length(self):
        # The transport identity is independent of decompressed cache bounds.
        raw = synthetic_map(self.expected, declared=65536, tag_offset=49152, tag_bytes=4096)
        manifest = self.prepare()
        self.assertEqual(manifest["output"], {"size": len(raw), "sha256": sha(raw),
                                             "declared_bytes": 65536, "tag_bytes": 4096})
        self.assertEqual(self.expected.read_bytes(), raw)

    def test_container_truncation_magic_json_and_trailing_bytes_rejected(self):
        self.prepare()
        raw = self.package.read_bytes()
        for data in (raw[:7], raw[:packages.HEADER.size - 1],
                     b"BADMAGIC" + raw[8:], raw[:-1], raw + b"extra",
                     packages.HEADER.pack(packages.MAGIC, packages.MAX_MANIFEST_BYTES + 1),
                     packages.HEADER.pack(packages.MAGIC, 1) + b"{"):
            with self.subTest(size=len(data)):
                path = self.root / "invalid.hogpkg"
                path.write_bytes(data)
                with self.assertRaises(packages.PackageError):
                    packages.read_package(path)

    def test_profile_output_hash_and_literal_corruption_rejected(self):
        valid = self.prepare()
        changes = (("profile", "foreign-profile"), ("cache_build", "01.01.14.2342"),
                   ("version", 2), ("id", "../downrush"),
                   ("scenario", "../external/scenario"),
                   ("invader_commit", "0" * 40))
        for key, value in changes:
            with self.subTest(key=key):
                forged = copy.deepcopy(valid)
                forged[key] = value
                self.assert_rejected_without_materialization(forged)
        for value in ("bad", "G" * 64):
            with self.subTest(hash=value):
                forged = copy.deepcopy(valid)
                forged["output"]["sha256"] = value
                self.assert_rejected_without_materialization(forged)
        payload = bytearray(self.payload())
        payload[-1] ^= 1
        self.assert_rejected_without_materialization(valid, payload=bytes(payload))

    def test_paths_cannot_escape_or_alias_materialization_roots(self):
        valid = self.prepare()
        for key in ("path", "stock_path"):
            for unsafe in ("../outside", "/absolute", "C:/outside", "safe/../../outside",
                           "safe\\..\\outside", "./alias", "safe//alias", "safe/./alias"):
                with self.subTest(key=key, path=unsafe):
                    forged = copy.deepcopy(valid)
                    entry = next(item for item in forged["files"]
                                 if key == "path" or item["kind"] == "stock-reference")
                    entry[key] = unsafe
                    self.assert_rejected_without_materialization(forged)
        for change in ("case", "duplicate"):
            forged = copy.deepcopy(valid)
            entry = copy.deepcopy(forged["files"][0])
            if change == "case":
                entry["path"] = entry["path"].upper()
            forged["files"].append(entry)
            with self.subTest(alias=change):
                self.assert_rejected_without_materialization(forged)
        self.assertFalse((self.root / "outside").exists())

    def test_manifest_lengths_offsets_and_cache_limits_rejected(self):
        valid = self.prepare()
        cases = (("payload_bytes", -1), ("payload_bytes", True),
                 ("payload_bytes", 256 * 1024 * 1024 + 1))
        for key, value in cases:
            forged = copy.deepcopy(valid)
            forged[key] = value
            with self.subTest(field=key, value=value):
                self.assert_rejected_without_materialization(forged)
        for field, value in (("size", -1), ("size", True), ("size", 128 * 1024 * 1024 + 1),
                             ("declared_bytes", 128 * 1024 * 1024 + 1),
                             ("tag_bytes", 22 * 1024 * 1024 + 1)):
            forged = copy.deepcopy(valid)
            forged["output"][field] = value
            with self.subTest(output=field, value=value):
                self.assert_rejected_without_materialization(forged)
        for field, value in (("size", -1), ("size", True), ("size", 128 * 1024 * 1024 + 1),
                             ("offset", -1), ("offset", True), ("offset", len(self.payload()) + 1)):
            forged = copy.deepcopy(valid)
            entry = next(item for item in forged["files"] if item["kind"] == "literal")
            entry[field] = value
            with self.subTest(file=field, value=value):
                self.assert_rejected_without_materialization(forged)
        with patch.object(packages, "MAX_FILES", len(valid["files"]) - 1):
            self.assert_rejected_without_materialization(valid)

    def test_missing_or_changed_stock_refuses_before_any_writes(self):
        self.prepare()
        for path in (self.unchanged, self.override):
            source = self.original / path
            before = source.read_bytes()
            with self.subTest(path=path, reason="missing"):
                source.unlink()
                with self.assertRaises(packages.PackageError):
                    packages.materialize_package(package=self.package,
                                                 original_stock_tags=self.original,
                                                 destination=self.destination)
                self.assertFalse(self.destination.exists())
                source.write_bytes(before)
            with self.subTest(path=path, reason="modified"):
                source.write_bytes(before[:-1] + b"?")
                with self.assertRaises(packages.PackageError):
                    packages.materialize_package(package=self.package,
                                                 original_stock_tags=self.original,
                                                 destination=self.destination)
                self.assertFalse(self.destination.exists())
                source.write_bytes(before)
        self.assertEqual(self.source_snapshot(), self.sources_before)

    def test_existing_destinations_and_dangling_symlinks_preserved(self):
        self.prepare()
        saved_package = self.package.read_bytes()
        with self.assertRaises((packages.PackageError, FileExistsError)):
            self.prepare()
        self.assertEqual(self.package.read_bytes(), saved_package)
        for destination_kind in ("empty", "user-files", "symlink"):
            with self.subTest(kind=destination_kind):
                if destination_kind == "symlink":
                    self.destination.symlink_to(self.root / "absent-target")
                else:
                    self.destination.mkdir()
                    if destination_kind == "user-files":
                        (self.destination / "save.bin").write_bytes(b"USER-SAVE")
                with self.assertRaises((packages.PackageError, FileExistsError)):
                    packages.materialize_package(package=self.package,
                                                 original_stock_tags=self.original,
                                                 destination=self.destination)
                if destination_kind == "user-files":
                    self.assertEqual((self.destination / "save.bin").read_bytes(), b"USER-SAVE")
                if self.destination.is_symlink():
                    self.assertEqual(self.destination.readlink(), self.root / "absent-target")
                    self.destination.unlink()
                else:
                    shutil.rmtree(self.destination)
        self.assertEqual(self.source_snapshot(), self.sources_before)

    def test_source_symlinks_cannot_import_external_files(self):
        external = self.root / "external.bin"
        external.write_bytes(b"PRIVATE-EXTERNAL-DATA")
        for source_root in (self.tags, self.data, self.original, self.patched):
            for directory in (False, True):
                with self.subTest(root=source_root.name, directory=directory):
                    link = source_root / "unsafe-link"
                    link.symlink_to(external.parent if directory else external,
                                    target_is_directory=directory)
                    with self.assertRaises(packages.PackageError):
                        self.prepare()
                    self.assertFalse(self.package.exists())
                    link.unlink()
        self.assertEqual(external.read_bytes(), b"PRIVATE-EXTERNAL-DATA")
        self.assertEqual(self.source_snapshot(), self.sources_before)

    def test_wrong_stock_region_type_and_modified_expected_cache_refused(self):
        for name, values in (("ui", {"build": "01.01.14.2342", "kind": 2}),
                             ("a10", {"kind": 1}), ("bloodgulch", {"version": 7})):
            source = self.maps / (name + ".map")
            before = source.read_bytes()
            with self.subTest(name=name):
                synthetic_map(source, **values)
                with self.assertRaises(packages.PackageError):
                    self.prepare()
                self.assertFalse(self.package.exists())
                source.write_bytes(before)
        for values in ({"version": 7}, {"kind": 0}, {"name": "other"},
                       {"declared": 128 * 1024 * 1024 + 1},
                       {"tag_bytes": 22 * 1024 * 1024 + 1},
                       {"tag_offset": 2047},
                       {"tag_offset": 4090, "tag_bytes": 10}):
            with self.subTest(expected=values):
                synthetic_map(self.expected, **values)
                with self.assertRaises(packages.PackageError):
                    self.prepare()
                self.assertFalse(self.package.exists())
        self.expected.write_bytes(self.expected_bytes)
        self.assertEqual(self.source_snapshot(), self.sources_before)

    def test_duplicate_json_keys_overlapping_ranges_and_prefix_collisions_refused(self):
        valid = self.prepare()
        encoded = json.dumps(valid).encode()
        # An escaped spelling is the same decoded key and must also fail.
        duplicate = b'{"\\u0069d":"other",' + encoded[1:]
        with self.assertRaises(packages.PackageError):
            packages.read_package(self.forged(valid, encoded=duplicate))
        for change in ("overlap", "gap", "prefix", "directory-case", "reference-class"):
            forged = copy.deepcopy(valid)
            if change in ("overlap", "gap"):
                literal = next(item for item in forged["files"] if item["kind"] == "literal")
                literal["offset"] += -1 if change == "overlap" else 1
            elif change == "prefix":
                entry = copy.deepcopy(forged["files"][0])
                entry["path"] = entry["path"].split("/")[0]
                forged["files"].append(entry)
            elif change == "directory-case":
                entry = copy.deepcopy(next(item for item in forged["files"] if item["kind"] == "stock-reference"))
                parts = entry["path"].split("/")
                parts[0] = parts[0].upper()
                parts[-1] = "distinct.weapon"
                entry["path"] = "/".join(parts)
                forged["files"].append(entry)
            else:
                entry = next(item for item in forged["files"] if item["kind"] == "stock-reference")
                entry["classification"] = "modified-or-different-stock"
            with self.subTest(change=change):
                self.assert_rejected_without_materialization(forged)

    def test_write_failures_and_corrupted_copies_remove_only_owned_staging(self):
        with patch.object(packages.shutil, "copyfileobj", side_effect=OSError("disk full")):
            with self.assertRaisesRegex(OSError, "disk full"):
                self.prepare()
        self.assertFalse(self.package.exists())
        self.assertEqual(list(self.root.glob(".community-package-*")), [])
        self.prepare()
        original_copy = packages.shutil.copyfile
        def corrupt_copy(source, destination):
            original_copy(source, destination)
            with Path(destination).open("ab") as stream:
                stream.write(b"unexpected")
        for effect in (OSError("disk full"), corrupt_copy):
            with self.subTest(effect=str(effect)):
                with patch.object(packages.shutil, "copyfile", side_effect=effect):
                    with self.assertRaises((OSError, packages.PackageError)):
                        packages.materialize_package(package=self.package,
                                                     original_stock_tags=self.original,
                                                     destination=self.destination)
                self.assertFalse(self.destination.exists())
        self.assertEqual(self.source_snapshot(), self.sources_before)

    def test_package_publication_race_preserves_winning_file(self):
        publish = packages._publish_file
        def racing_publish(source, destination):
            Path(destination).write_bytes(b"EXISTING-USER-PACKAGE")
            return publish(source, destination)
        with patch.object(packages, "_publish_file", side_effect=racing_publish):
            with self.assertRaises(packages.PackageError):
                self.prepare()
        self.assertEqual(self.package.read_bytes(), b"EXISTING-USER-PACKAGE")
        self.assertEqual(list(self.root.glob(".community-package-*")), [])
        self.assertEqual(self.source_snapshot(), self.sources_before)

    def test_reconstruction_publishes_only_the_exact_expected_cache(self):
        manifest = self.prepare()
        tool_bin = self.root / "tools"
        write_files(tool_bin, {"invader-extract": b"fake-extract",
                               "invader-build": b"fake-build"})
        rebuilt = self.root / "rebuilt"
        calls = []
        corrupt = True
        def run(args, **kwargs):
            calls.append((Path(args[0]).name, list(args[1:]), kwargs))
            if Path(args[0]).name == "invader-extract":
                write_files(Path(args[args.index("-t") + 1]), self.original_bytes)
            else:
                target = Path(args[args.index("-m") + 1]) / "downrush.map"
                output = bytearray(self.expected_bytes)
                if corrupt:
                    output[3000] ^= 1
                target.write_bytes(output)
            return subprocess.CompletedProcess(args, 0, "", "")
        with patch.object(packages.subprocess, "run", side_effect=run):
            with self.assertRaisesRegex(packages.PackageError, "exact bytes"):
                packages.reconstruct_package(package=self.package, stock_maps=self.maps,
                    tool_bin=tool_bin, toolchain_manifest=self.toolchain, destination=rebuilt)
            self.assertFalse(rebuilt.exists())
            corrupt = False
            report = packages.reconstruct_package(package=self.package, stock_maps=self.maps,
                tool_bin=tool_bin, toolchain_manifest=self.toolchain, destination=rebuilt)
        self.assertEqual(report["status"], "exact-reconstruction")
        self.assertEqual(report["map"], manifest["output"])
        self.assertEqual((rebuilt / "maps/downrush.map").read_bytes(), self.expected_bytes)
        self.assertFalse((rebuilt / ".assembled").exists())
        self.assertFalse((rebuilt / ".original-stock").exists())
        self.assertEqual([name for name, _, _ in calls], ["invader-extract"] * 3 + ["invader-build"] +
                         ["invader-extract"] * 3 + ["invader-build"])
        build_args = calls[-1][1]
        self.assertEqual(build_args[0:2], ["-g", "xbox-ntsc"])
        self.assertEqual(build_args[-4:], ["-S", "data", "-E", "levels/test/downrush/downrush"])
        self.assertTrue(all(kwargs["timeout"] == 180 for _, _, kwargs in calls))
        self.assertEqual(self.source_snapshot(), self.sources_before)

    def test_reconstruction_rejects_changed_stock_and_tool_before_execution(self):
        self.prepare()
        tool_bin = self.root / "tools"
        write_files(tool_bin, {"invader-extract": b"fake-extract",
                               "invader-build": b"fake-build"})
        rebuilt = self.root / "rebuilt"
        stock = self.maps / "bloodgulch.map"
        stock_bytes = stock.read_bytes()
        build = tool_bin / "invader-build"
        with patch("tools.community_maps.subprocess.run",
                   side_effect=AssertionError("unverified tools must never execute")):
            for changed in ("stock", "tool", "toolchain"):
                with self.subTest(changed=changed):
                    original_manifest = self.toolchain.read_bytes()
                    if changed == "stock":
                        stock.write_bytes(stock_bytes[:-1] + b"?")
                    elif changed == "tool":
                        build.write_bytes(b"replacement-tool")
                    else:
                        altered = json.loads(original_manifest)
                        altered["binaries"]["build"]["sha256"] = sha(b"replacement-tool")
                        self.toolchain.write_text(json.dumps(altered))
                    with self.assertRaises(packages.PackageError):
                        packages.reconstruct_package(
                            package=self.package, stock_maps=self.maps, tool_bin=tool_bin,
                            toolchain_manifest=self.toolchain, destination=rebuilt)
                    self.assertFalse(rebuilt.exists())
                    stock.write_bytes(stock_bytes)
                    build.write_bytes(b"fake-build")
                    self.toolchain.write_bytes(original_manifest)
        self.assertEqual(self.source_snapshot(), self.sources_before)


if __name__ == "__main__":
    unittest.main()
