"""Read actual Xbox-cache item schedules without changing tags or map bytes."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

from tools.test_performance_variants import block
from tools.verify_performance_sound_samples import Cache

ROOT = Path(__file__).resolve().parents[1]
GAME_TYPES = {0: "none", 1: "ctf", 2: "slayer", 3: "oddball", 4: "king", 5: "race",
              6: "terminator", 7: "stub", 12: "all", 13: "all_non_ctf", 14: "all_non_ctf_non_race"}


def production_layout():
    """Compile exact production declarations with the cache's explicit ILP32 ABI."""
    declarations = [("source/scenario/scenario_definitions.h", "scenario"),
                    ("source/scenario/scenario_definitions.h", "scenario_netgame_equipment"),
                    ("source/items/item_definitions.h", "item_collection_definition"),
                    ("source/items/item_definitions.h", "item_permutation_definition"),
                    ("source/objects/object_definitions.h", "_object_definition"),
                    ("source/items/item_definitions.h", "_item_definition"),
                    ("source/items/equipment_definitions.h", "_equipment_definition"),
                    ("source/items/equipment_definitions.h", "equipment_definition"),
                    ("source/game/game_globals.h", "game_globals")]
    fields = [("scenario", "netgame_equipment"), ("scenario_netgame_equipment", "game_type"),
              ("scenario_netgame_equipment", "spawn_time"), ("scenario_netgame_equipment", "position"),
              ("scenario_netgame_equipment", "item_collection"), ("item_collection_definition", "spawn_time"),
              ("item_permutation_definition", "weight"), ("item_permutation_definition", "item"),
              ("equipment_definition", "equipment"), ("game_globals", "weapon_list")]
    source = """#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
typedef float real;
typedef uint16_t word;
typedef struct { float x,y,z; } real_point3d;
struct tag_reference { uint32_t group,name,length,index; };
struct tag_block { uint32_t count,address,definition; };
struct tag_data { uint32_t size,flags,offset,address,definition; };
"""
    hashes = {}
    for path, name in declarations:
        contents = (ROOT / path).read_text()
        declaration = block(contents, "struct " + name + "\n{")
        declaration = re.sub(r"\bunsigned long\b", "uint32_t", declaration)
        declaration = re.sub(r"\blong\b", "int32_t", declaration)
        source += declaration + ";\n"
        hashes[path] = hashlib.sha256(contents.encode()).hexdigest()
    source += "int main(void) {\n"
    for name, field in fields:
        source += f'printf("{name}.{field}=%zu\\n",offsetof(struct {name},{field}));\n'
    for name in ("scenario_netgame_equipment", "item_permutation_definition"):
        source += f'printf("{name}.size=%zu\\n",sizeof(struct {name}));\n'
    source += "return 0;}\n"
    with tempfile.TemporaryDirectory(prefix="halo-item-layout-") as temporary:
        folder = Path(temporary)
        (folder / "layout.c").write_text(source)
        subprocess.run(["clang", "-std=c11", "-Wall", "-Wextra", "-Werror", str(folder / "layout.c"),
                        "-o", str(folder / "layout")], check=True)
        output = subprocess.check_output([str(folder / "layout")], text=True)
    return {line.split("=")[0]: int(line.split("=")[1]) for line in output.splitlines()}, hashes


def matches(entries, game_type):
    return any(entry == game_type or entry == 12 or (entry == 13 and game_type != 1) or
               (entry == 14 and game_type not in (1, 5)) for entry in entries)


def inspect(path, layout):
    cache = Cache(path)
    scenarios = [tag for tag in cache.tags.values() if tag["group"] == "scnr"]
    assert len(scenarios) == 1, path
    scenario = scenarios[0]
    globals_tag = cache.by_path[r"globals\globals"]
    weapon_count, weapon_address, _ = cache.unpack("<3I", globals_tag["address"] + layout["game_globals.weapon_list"])
    weapons = []
    for i in range(weapon_count):
        index = cache.unpack("<I", weapon_address + i * 16 + 12)[0]
        tag = cache.tags.get(index)
        weapons.append({"slot": i, "index": index, "path": tag["path"] if tag else None})
    rocket_index = weapons[7]["index"] if weapon_count > 7 else None
    count, address, _ = cache.unpack("<3I", scenario["address"] + layout["scenario.netgame_equipment"])
    assert 0 <= count <= 512
    entries = []
    for index in range(count):
        entry_address = address + index * layout["scenario_netgame_equipment.size"]
        game_types = cache.unpack("<4h", entry_address + layout["scenario_netgame_equipment.game_type"])
        spawn_time = cache.unpack("<h", entry_address + layout["scenario_netgame_equipment.spawn_time"])[0]
        collection_index = cache.unpack("<I", entry_address + layout["scenario_netgame_equipment.item_collection"] + 12)[0]
        collection = cache.tags.get(collection_index)
        permutations = []
        collection_period = None
        if collection:
            assert collection["group"] == "itmc"
            collection_period = cache.unpack("<h", collection["address"] + layout["item_collection_definition.spawn_time"])[0]
            permutation_count, permutation_address, _ = cache.unpack("<3I", collection["address"])
            assert 0 <= permutation_count <= 1024
            for permutation_index in range(permutation_count):
                current = permutation_address + permutation_index * layout["item_permutation_definition.size"]
                item_index = cache.unpack("<I", current + layout["item_permutation_definition.item"] + 12)[0]
                item = cache.tags.get(item_index)
                powerup_type = None
                category = "other"
                if item and item["group"] == "eqip":
                    powerup_type = cache.unpack("<h", item["address"] + layout["equipment_definition.equipment"])[0]
                    category = {2: "overshield", 3: "camouflage"}.get(powerup_type, "other_equipment")
                elif item and item["group"] == "weap":
                    category = "rockets" if item_index == rocket_index else "other_weapon"
                permutations.append({"index": permutation_index,
                                     "weight": cache.unpack("<f", current + layout["item_permutation_definition.weight"])[0],
                                     "item_index": item_index, "path": item["path"] if item else None,
                                     "group": item["group"] if item else None, "powerup_type": powerup_type,
                                     "category_normal_weapon_set": category})
        categories = sorted({p["category_normal_weapon_set"] for p in permutations if p["weight"] > 0})
        entries.append({"index": index, "flags": cache.unpack("<I", entry_address)[0],
                        "game_type_filters": list(game_types),
                        "game_type_filter_names": [GAME_TYPES.get(value, "unknown") for value in game_types],
                        "active_game_types": [GAME_TYPES[g] for g in range(1, 6) if matches(game_types, g)],
                        "scenario_spawn_seconds": spawn_time, "collection_spawn_seconds": collection_period,
                        "effective_spawn_seconds": spawn_time or collection_period or 30,
                        "period_source": "scenario" if spawn_time else "collection" if collection_period else "default_30_seconds",
                        "position": list(cache.unpack("<3f", entry_address + layout["scenario_netgame_equipment.position"])),
                        "collection_index": collection_index, "collection_path": collection["path"] if collection else None,
                        "permutations": permutations, "categories_normal_weapon_set": categories,
                        "unambiguous_category": categories[0] if len(categories) == 1 else None})
    schedules = {}
    for game_type in ("ctf", "slayer", "oddball", "king", "race"):
        schedules[game_type] = {category: sorted({entry["effective_spawn_seconds"] for entry in entries
                               if game_type in entry["active_game_types"] and entry["unambiguous_category"] == category})
                               for category in ("rockets", "overshield", "camouflage")}
    ambiguous = [{"index": entry["index"], "effective_spawn_seconds": entry["effective_spawn_seconds"],
                  "active_game_types": entry["active_game_types"],
                  "possible_categories": entry["categories_normal_weapon_set"]}
                 for entry in entries if len(entry["categories_normal_weapon_set"]) > 1]
    return {"map": str(cache.path), "map_sha256": cache.sha256, "scenario": scenario["path"],
            "netgame_equipment_count": count, "weapon_list": weapons, "schedules_normal_weapon_set": schedules,
            "ambiguous_category_spawns_excluded_from_schedules": ambiguous,
            "category_counts": dict(Counter(entry["unambiguous_category"] or "ambiguous" for entry in entries)),
            "entries": entries}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--map", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    layout, hashes = production_layout()
    report = {"recorded_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "Read-only actual compiled Xbox v5 caches. Periods and categories under the normal weapon set; no runtime spawning, pickup state or RNG was sampled. Remapped variants require separate deterministic category handling.",
              "source_layout_offsets": layout, "source_header_sha256": hashes,
              "period_rule": "scenario spawn_time if nonzero; otherwise collection spawn_time if nonzero; otherwise 30 seconds. Stock spawn checks game_time modulo period.",
              "category_rule": "eqip powerup_type 2=overshield, 3=camouflage; weap index equals globals.weapon_list[7]=rockets. Never classify by path.",
              "maps": [inspect(path, layout) for path in args.map]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    for entry in report["maps"]:
        print(Path(entry["map"]).name, entry["netgame_equipment_count"], entry["schedules_normal_weapon_set"]["slayer"])


if __name__ == "__main__":
    main()
