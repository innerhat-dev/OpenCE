"""Exercise production discovery with synthetic caches and a minimal file API."""
import ctypes
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools import community_maps
from tools import community_map_candidate

ROOT = Path(__file__).resolve().parents[1]
STOCK = ("beavercreek", "sidewinder", "damnation", "ratrace", "prisoner", "hangemhigh",
         "chillout", "carousel", "boardingaction", "bloodgulch", "wizard", "putput", "longest")


def header(name="downrush", version=5, kind=1, length=1024 * 1024, build="01.10.12.2276"):
    result = bytearray(2048)
    result[:4] = b"daeh"
    struct.pack_into("<II", result, 4, version, length)
    result[32:32 + len(name)] = name.encode("ascii")
    result[64:64 + len(build)] = build.encode("ascii")
    struct.pack_into("<H", result, 96, kind)
    result[-4:] = b"toof"
    return result


XTL = r'''
#include <stdio.h>
typedef void *HANDLE;
typedef struct { unsigned long dwFileAttributes; char cFileName[260]; } WIN32_FIND_DATAA;
#define INVALID_HANDLE_VALUE ((HANDLE)-1)
#define GENERIC_READ 1
#define OPEN_EXISTING 1
#define FILE_ATTRIBUTE_DIRECTORY 16
HANDLE CreateFileA(const char *, int, int, void *, int, int, void *);
int ReadFile(HANDLE, void *, unsigned long, unsigned long *, void *);
int CloseHandle(HANDLE);
HANDLE FindFirstFileA(const char *, WIN32_FIND_DATAA *);
int FindNextFileA(HANDLE, WIN32_FIND_DATAA *);
'''

HARNESS = r'''
#include <dirent.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include "xtl.h"
static char directory[256];
void set_directory(const char *p) { snprintf(directory, sizeof(directory), "%s/", p); }
const char *cache_files_map_directory(void) { return directory; }
const char *cache_files_build_region(const char *build) {
    return !strcmp(build, "01.10.12.2276") || !strcmp(build, "01.01.14.2342") ? "region" : NULL;
}
struct handle { int kind; FILE *file; DIR *dir; };
HANDLE CreateFileA(const char *name, int access, int share, void *security, int creation, int flags, void *template) {
    struct handle *h = calloc(1, sizeof(*h)); h->kind = 1; h->file = fopen(name, "rb");
    if (!h->file) { free(h); return INVALID_HANDLE_VALUE; } return h;
}
int ReadFile(HANDLE handle, void *data, unsigned long size, unsigned long *read, void *overlapped) {
    struct handle *h = handle; *read = fread(data, 1, size, h->file); return !ferror(h->file);
}
int CloseHandle(HANDLE handle) {
    struct handle *h = handle; if (h->kind == 1) fclose(h->file); else closedir(h->dir); free(h); return 1;
}
int FindNextFileA(HANDLE handle, WIN32_FIND_DATAA *out) {
    struct handle *h = handle; struct dirent *entry;
    while ((entry = readdir(h->dir))) {
        if (entry->d_name[0] == '.') continue;
        char path[512]; struct stat info; snprintf(path, sizeof(path), "%s%s", directory, entry->d_name);
        if (stat(path, &info)) continue;
        out->dwFileAttributes = S_ISDIR(info.st_mode) ? FILE_ATTRIBUTE_DIRECTORY : 0;
        snprintf(out->cFileName, sizeof(out->cFileName), "%s", entry->d_name); return 1;
    } return 0;
}
HANDLE FindFirstFileA(const char *pattern, WIN32_FIND_DATAA *out) {
    struct handle *h = calloc(1, sizeof(*h)); h->dir = opendir(directory);
    if (!h->dir || !FindNextFileA(h, out)) {
        if (h->dir) closedir(h->dir); free(h); return INVALID_HANDLE_VALUE;
    } return h;
}
'''


class NativeMapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="halo-v5-maps-")
        cls.folder = Path(cls.temp.name)
        (cls.folder / "cache").mkdir()
        (cls.folder / "cseries.h").write_text('''#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#define TRUE 1
#define FALSE 0
#define NUMBEROF(a) (sizeof(a)/sizeof((a)[0]))
#define _stricmp strcasecmp
#define _strnicmp strncasecmp
''')
        (cls.folder / "cache/cache_files.h").write_text("const char *cache_files_map_directory(void);\nconst char *cache_files_build_region(const char *);\n")
        (cls.folder / "xtl.h").write_text(XTL)
        (cls.folder / "harness.c").write_text(HARNESS)
        library = cls.folder / "maps.dylib"
        subprocess.run(["clang", "-shared", "-fPIC", "-Wall", "-Wextra", "-Wno-unused-parameter",
                        "-I", str(cls.folder), "-iquote", str(ROOT / "port/linux/include"),
                        "-include", str(ROOT / "port/linux/include/halo_port_capacity.h"),
                        str(ROOT / "port/linux/game/custom_maps.c"), str(cls.folder / "harness.c"),
                        "-o", str(library)], check=True, capture_output=True)
        cls.lib = ctypes.CDLL(str(library))
        cls.lib.native_map_header_valid.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        cls.lib.native_map_header_valid.restype = ctypes.c_int
        cls.lib.native_multiplayer_map_list.argtypes = [ctypes.POINTER(ctypes.c_char_p), ctypes.c_short, ctypes.POINTER(ctypes.c_short)]
        cls.lib.native_multiplayer_map_list.restype = ctypes.POINTER(ctypes.c_char_p)
        cls.lib.set_directory.argtypes = [ctypes.c_char_p]

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def valid(self, data, filename="downrush.map"):
        return bool(self.lib.native_map_header_valid(ctypes.create_string_buffer(bytes(data)), filename.encode()))

    def test_header_acceptance_and_capacity(self):
        self.assertTrue(self.valid(header()))
        self.assertTrue(self.valid(header(build="01.01.14.2342")))
        self.assertTrue(self.valid(header(length=128 * 1024 * 1024)))
        self.assertFalse(self.valid(header(length=128 * 1024 * 1024 + 1)))
        self.assertFalse(self.valid(header(length=2047)))
        self.assertTrue(self.valid(header(), "DOWNRUSH.MAP"))

    def test_reject_wrong_format_type_identity_or_build(self):
        for data in (header(version=7), header(kind=0), header(kind=2), header(build="Unknown"),
                     header(name="../downrush"), header(name="")):
            with self.subTest(data=data[4:12]): self.assertFalse(self.valid(data))
        self.assertFalse(self.valid(header(), "alias.map"))
        for offset in (32, 64):
            data = header(); data[offset:offset + 32] = b"x" * 32
            self.assertFalse(self.valid(data))
        data = header(); data[-4:] = b"xxxx"
        self.assertFalse(self.valid(data))

    def test_discovery_preserves_stock_order_and_skips_invalid_inputs(self):
        maps = self.folder / "maps"
        maps.mkdir()
        cases = {"downrush.map": header(), "atlas.map": header("atlas"),
                 "h1pb_chillout.map": header("h1pb_chillout"), "chillout.map": header("chillout"),
                 "pc.map": header("pc", version=7), "campaign.map": header("campaign", kind=0),
                 "bad.map": b"short", "alias.map": header("different")}
        for name, data in cases.items(): (maps / name).write_bytes(data)
        (maps / "directory.map").mkdir()
        self.lib.set_directory(str(maps).encode())
        stock = (ctypes.c_char_p * len(STOCK))(*[f"levels\\test\\{s}\\{s}".encode() for s in STOCK])
        count = ctypes.c_short()
        result = self.lib.native_multiplayer_map_list(stock, len(STOCK), ctypes.byref(count))
        self.assertEqual(count.value, 16)
        self.assertEqual([result[i] for i in range(13)], list(stock))
        self.assertEqual([result[i] for i in range(13, count.value)], [b"atlas", b"downrush", b"h1pb_chillout"])


class ImportBoundaryTests(unittest.TestCase):
    def test_pc_shader_conversion_preserves_sources_and_rejects_ambiguous_targets(self):
        with tempfile.TemporaryDirectory() as directory:
            tags = Path(directory)
            source = tags / "sky.shader_transparent_chicago_extended"
            target = tags / "sky.shader_transparent_chicago"
            source.write_bytes(b"authored PC shader")
            test = self
            class ShaderTool:
                def count(self, root, tag, field):
                    test.assertEqual(root, tags)
                    test.assertEqual(tag, source.name)
                    test.assertIn(field, ("maps_4_stage", "maps_2_stage"))
                    return 2
                def run(self, name, *args):
                    if name == "convert":
                        target.write_bytes(b"converted Xbox shader")
                    elif name == "refactor":
                        test.assertIn("no-move", args)
                    else:
                        test.fail("Unexpected shader operation")
            result = community_maps.convert_extended_shaders(ShaderTool(), tags)
            self.assertEqual(result, [{"source_tag": source.name, "converted_tag": target.name,
                "sha256_before": community_maps.digest(source), "sha256_after": community_maps.digest(target),
                "four_stage_layers": 2, "two_stage_fallback_layers": 2}])
            self.assertEqual(source.read_bytes(), b"authored PC shader")
            with self.assertRaisesRegex(ValueError, "overwrite"):
                community_maps.convert_extended_shaders(ShaderTool(), tags)
            target.unlink()
            with patch.object(ShaderTool, "count", return_value=0):
                with self.assertRaisesRegex(ValueError, "layer count"):
                    community_maps.convert_extended_shaders(ShaderTool(), tags)
            self.assertFalse(target.exists())

    def test_map_geometry_cannot_be_silently_replaced_by_stock_lookup(self):
        with tempfile.TemporaryDirectory() as directory:
            stock, tags = Path(directory) / "stock", Path(directory) / "tags"
            names = ("levels/test/pilot/pilot.bitmap", "shared/geometry.scenario_structure_bsp",
                     "weapons/pistol/pistol.weapon")
            for root in (stock, tags):
                for name in names:
                    target = root / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(b"tag")
            with self.assertRaisesRegex(ValueError, "pilot.bitmap.*geometry.scenario_structure_bsp"):
                community_maps.validate_map_content_priority(stock, tags, "levels/test/pilot/pilot",
                                                              "levels/test/pilot/pilot.scenario")
            for name in names[:2]:
                (stock / name).unlink()
            # Core gameplay dependencies retain the original stock priority.
            community_maps.validate_map_content_priority(stock, tags, "levels/test/pilot/pilot",
                                                         "levels/test/pilot/pilot.scenario")

    def test_alias_rebuilds_copied_scenario_without_selecting_stock_scenario(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package, stock, output = root / "package", root / "stock", root / "output"
            source_tag = "levels/test/chillout/chillout.scenario"
            source = package / "tags" / source_tag
            source.parent.mkdir(parents=True)
            source.write_bytes(b"community scenario with optional script")
            stock_source = stock / source_tag
            stock_source.parent.mkdir(parents=True)
            stock_source.write_bytes(b"original stock scenario")
            spec = {"id": "h1pb_chillout", "display_name": "H1PB Chill Out",
                    "scenario": source_tag.removesuffix(".scenario"),
                    "scenario_sha256": community_maps.digest(source),
                    "optional_scripts": ["timer"], "cleanup_prefixes": []}
            alias = "levels/test/chillout/h1pb_chillout.scenario"
            test = self
            class BuildTool:
                def count(self, tags, tag, field):
                    test.assertEqual(tag, alias)
                    return 1 if field == "scripts" else 0
                def get(self, tags, tag, field):
                    test.assertEqual((tag, field), (alias, "scripts[0].name"))
                    return "timer"
                def run(self, name, *args):
                    if name == "dependency":
                        expected = source_tag if args[2] == package / "tags" else alias
                        test.assertEqual(args[-1], expected)
                        return ""
                    if name == "edit":
                        test.assertEqual(args[-1], alias)
                        (Path(args[1]) / alias).write_bytes(b"community scenario without optional script")
                    if name == "build":
                        test.assertEqual(args[-1], alias.removesuffix(".scenario"))
                        test.assertEqual(args[args.index("-t") + 1], stock)
                        copied = output / spec["id"] / "tags"
                        test.assertEqual((copied / alias).read_bytes(), b"community scenario without optional script")
                        test.assertEqual((copied / source_tag).read_bytes(), source.read_bytes())
                        maps = Path(args[args.index("-m") + 1])
                        (maps / "h1pb_chillout.map").write_bytes(header("h1pb_chillout"))
                    return ""
            result = community_maps.build_map(BuildTool(), spec, package, stock, output)
            self.assertEqual(result["name"], "h1pb_chillout")
            self.assertEqual(result["compiled_scenario"], alias.removesuffix(".scenario"))
            self.assertEqual(community_maps.digest(source), spec["scenario_sha256"])
            self.assertEqual(stock_source.read_bytes(), b"original stock scenario")
            manifest = json.loads((output / spec["id"] / "manifest.json").read_text())
            self.assertEqual(manifest["source_tags"], {source_tag: spec["scenario_sha256"]})
            with self.assertRaisesRegex(ValueError, "stock data"):
                community_maps.build_map(BuildTool(), dict(spec, id="chillout"), package, stock, output)

    def test_batch_continues_after_rejected_map_and_records_outcomes(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            specs = {name: {"id": name, "scenario": "levels/test/" + name}
                     for name in ("first", "rejected", "last")}
            result = {"profile": "stock-xbox-ntsc", "stock": {"inputs": {"source": "hash"}}}
            calls = []
            def build(tool, spec, package, stock, folder):
                calls.append(spec["id"])
                saved = json.loads((output / "build.json").read_text())
                self.assertEqual(saved["map_status"][spec["id"]], "building")
                if spec["id"] == "rejected":
                    raise ValueError("Unreviewed script/AI behavior")
                return {"id": spec["id"], "output": spec["id"] + ".map"}
            with patch.object(community_maps, "build_map", side_effect=build):
                failures = community_maps.build_maps(None, specs,
                    ["first", "rejected", "last", "first"], output, output, output, result)
            self.assertEqual(failures, 1)
            self.assertEqual(calls, ["first", "rejected", "last"])
            self.assertEqual([item["id"] for item in result["maps"]], ["first", "last"])
            self.assertEqual(result["failures"], [{"id": "rejected", "scenario": "levels/test/rejected",
                                                   "error": "Unreviewed script/AI behavior", "status": "failed"}])
            self.assertEqual(result["status"], "completed with failures")
            self.assertEqual(json.loads((output / "build.json").read_text()), result)
            self.assertFalse((output / "build.json.tmp").exists())
            self.assertEqual(result["stock"], {"inputs": {"source": "hash"}})

    def test_candidate_rejects_changed_stock_with_matching_build_header(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            caches, inputs = {}, {}
            for name, kind in (("ui", 2), ("a10", 0), ("bloodgulch", 1)):
                source = root / (name + ".map")
                source.write_bytes(header(name, kind=kind))
                info = community_maps.cache_header(source)
                caches[source.name] = (source, info)
                inputs[name] = info
            imports = {"stock": {"inputs": inputs}}
            community_map_candidate.validate_stock_inputs(imports, caches)
            source = root / "bloodgulch.map"
            source.write_bytes(source.read_bytes() + b"changed cache contents")
            caches[source.name] = (source, community_maps.cache_header(source))
            with self.assertRaisesRegex(ValueError, "bloodgulch"):
                community_map_candidate.validate_stock_inputs(imports, caches)
            with self.assertRaisesRegex(ValueError, "record"):
                community_map_candidate.validate_stock_inputs({}, caches)

    def test_substitutions_follow_converted_reachable_model_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stock, tags = root / "stock", root / "tags"
            stock.mkdir(); tags.mkdir()
            for name in ("player.model", "unused.weapon"):
                (stock / name).write_bytes(b"stock")
                (tags / name).write_bytes(b"package")
            (tags / "player.gbxmodel").write_bytes(b"pre-conversion")
            (tags / "community.model").write_bytes(b"custom")
            test = self
            class DependencyTool:
                def run(self, *args):
                    test.assertEqual(args, ("dependency", "-r", "-t", stock,
                                            "-t", tags, "pilot.scenario"))
                    return "player.model\ncommunity.model"
            result = community_maps.resolved_stock_substitutions(DependencyTool(), stock, tags, "pilot.scenario")
            self.assertEqual(result, {"player.model": community_maps.digest(stock / "player.model")})

    def test_tag_paths_cannot_escape_input_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "tags"; root.mkdir()
            (root / "safe.scenario").write_bytes(b"data")
            self.assertEqual(community_maps.safe_tag(root, "safe.scenario"), (root / "safe.scenario").resolve())
            for value in ("../tags/safe.scenario", str(root / "safe.scenario"), "missing.scenario"):
                with self.subTest(value=value), self.assertRaises((ValueError, OSError)):
                    community_maps.safe_tag(root, value)

    def test_inventory_namespaces_stock_collisions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); package = root / "package"; stock = root / "stock"
            (package / "maps").mkdir(parents=True); (package / "tags").mkdir(); stock.mkdir()
            (stock / "chillout.map").write_bytes(header("chillout"))
            (package / "maps/chillout.map").write_bytes(header("chillout", version=7))
            result = community_maps.inventory(package, stock)
            self.assertEqual(result["maps"][0]["import_id"], "h1pb_chillout")
            self.assertTrue(result["maps"][0]["stock_filename_collision"])
            self.assertEqual(community_maps.cache_header(stock / "chillout.map")["version"], 5)


if __name__ == "__main__":
    unittest.main()
