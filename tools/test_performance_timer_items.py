"""Compile the production item-wave classifier against deterministic map tags.

The fixture uses production tag layouts and game-type matching. Object creation,
random selection, and pickup inspection are deliberately unavailable.
"""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from tools.test_performance_variants import block

ROOT = Path(__file__).resolve().parents[1]

FIXTURE = r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <stdint.h>
typedef int boolean;
typedef float real;
typedef struct {real x,y,z;} real_point3d;
#define TRUE 1
#define FALSE 0
#define NONE (-1)
#define NUMBEROF(a) (sizeof(a)/sizeof(*(a)))
#define TEST_FLAG(value,bit) (((value)&(1UL<<(bit)))!=0)
#define TICKS_PER_SECOND 30
#define MAXIMUM_SCENARIO_NETGAME_EQUIPMENT_PER_SCENARIO 200
#define ITEM_COLLECTION_DEFINITION_TAG 1
enum {_object_type_weapon=2,_object_type_equipment=3,_object_type_scenery=6};
struct tag_reference {long index;};
struct tag_block {long count; void *address;};
#define TAG_BLOCK_GET_ELEMENT(b,i,t) ((t *)(b)->address+(i))
/* PRODUCTION DECLARATIONS */
struct object_definition {struct {short type;} object;};
struct equipment_definition {struct {short powerup_type;} equipment;};
struct scenario {struct tag_block netgame_equipment;};
static struct scenario scenario;
static struct scenario_netgame_equipment equipment[240];
static struct item_collection_definition collections[16];
static struct item_permutation_definition permutations[16][8];
static struct object_definition definitions[8];
static struct equipment_definition powerups[8];
static long remap[8],weapon_list[8];
static boolean running=TRUE;
static struct {short type;} engine,*game_engine=&engine;
static struct game_variant {struct {unsigned long flags;} universal_variant;} variant;
static struct scenario *global_scenario_get(void) {return &scenario;}
static boolean game_engine_running(void) {return running;}
static struct game_variant *game_engine_get_variant(void) {return &variant;}
static long game_engine_remap_weapon(long tag) {
    if(tag==NONE) return NONE;
    assert(tag>=0 && tag<8); return remap[tag];
}
static struct object_definition *object_definition_get(long tag) {assert(tag>=0 && tag<8); return &definitions[tag];}
static struct equipment_definition *equipment_definition_get(long tag) {assert(tag>=0 && tag<8); return &powerups[tag];}
static long weapon_definition_index_to_list_index(long tag) {assert(tag>=0 && tag<8); return weapon_list[tag];}
static void *tag_get(long group,long tag) {assert(group==1 && tag>=0 && tag<16); return &collections[tag];}
/* PRODUCTION GAME TYPE MATCH */
/* PRODUCTION */
static void setup(void) {
    memset(equipment,0,sizeof(equipment)); memset(collections,0,sizeof(collections));
    memset(permutations,0,sizeof(permutations)); memset(definitions,0,sizeof(definitions));
    memset(powerups,0,sizeof(powerups)); running=TRUE; engine.type=game_engine_slayer; variant.universal_variant.flags=0;
    scenario.netgame_equipment=(struct tag_block){1,equipment};
    for(unsigned i=0;i<NUMBEROF(equipment);i++) {
        equipment[i].item_collection.index=0;
        equipment[i].game_type[0]=game_engine_slayer;
    }
    for(unsigned i=0;i<NUMBEROF(collections);i++) {
        collections[i].permutations=(struct tag_block){1,permutations[i]};
        permutations[i][0].weight=1;
    }
    for(unsigned i=0;i<NUMBEROF(definitions);i++) {remap[i]=i; weapon_list[i]=NONE;}
    definitions[0].object.type=definitions[3].object.type=definitions[5].object.type=_object_type_weapon;
    weapon_list[0]=weapon_list[5]=7; weapon_list[3]=1;
    definitions[1].object.type=definitions[2].object.type=definitions[4].object.type=_object_type_equipment;
    powerups[1].equipment.powerup_type=_equipment_powerup_active_camouflage;
    powerups[2].equipment.powerup_type=_equipment_powerup_overshield;
    powerups[4].equipment.powerup_type=_equipment_powerup_health;
    definitions[6].object.type=_object_type_scenery;
    powerups[6].equipment.powerup_type=_equipment_powerup_overshield;
    remap[7]=NONE;
}
static void categories_and_variant(void) {
    const unsigned expected[]={1,2,4,0,0,1,0,0};
    setup();
    for(unsigned i=0;i<NUMBEROF(expected);i++) {
        permutations[0][0].item.index=i;
        performance_timer_items_initialize();
        assert(performance_timer_items_due(899,900)==expected[i]);
    }
    permutations[0][0].item.index=NONE;
    performance_timer_items_initialize(); assert(!performance_timer_items_due(899,900));
    permutations[0][0].item.index=0; remap[0]=3; /* Rockets replaced by pistols. */
    performance_timer_items_initialize(); assert(!performance_timer_items_due(899,900));
    permutations[0][0].item.index=3; remap[3]=5; /* Pistol collection replaced by rockets. */
    performance_timer_items_initialize(); assert(performance_timer_items_due(899,900)==1);
    running=FALSE; performance_timer_items_initialize(); assert(!performance_timer_items_due(899,900));
    running=TRUE; permutations[0][0].item.index=1; variant.universal_variant.flags=1UL<<_game_variant_always_invisible_bit;
    performance_timer_items_initialize(); assert(!performance_timer_items_due(899,900));
    permutations[0][0].item.index=2;
    performance_timer_items_initialize(); assert(performance_timer_items_due(899,900)==4);
    variant.universal_variant.flags=1UL<<_game_variant_no_shields_bit;
    performance_timer_items_initialize(); assert(!performance_timer_items_due(899,900));
    permutations[0][0].item.index=1;
    performance_timer_items_initialize(); assert(performance_timer_items_due(899,900)==2);
}
static void collection_predictability(void) {
    setup(); collections[0].permutations.count=2;
    permutations[0][1].item.index=1; permutations[0][1].weight=1;
    performance_timer_items_initialize(); assert(!performance_timer_items_due(899,900));
    permutations[0][1].item.index=3; /* Mixed supported and unsupported also excluded. */
    performance_timer_items_initialize(); assert(!performance_timer_items_due(899,900));
    permutations[0][1].item.index=5; /* Distinct tags in the same category are predictable. */
    performance_timer_items_initialize(); assert(performance_timer_items_due(899,900)==1);
    permutations[0][1].item.index=1; permutations[0][1].weight=0;
    performance_timer_items_initialize(); assert(performance_timer_items_due(899,900)==1);
    permutations[0][0].weight=0;
    performance_timer_items_initialize(); assert(!performance_timer_items_due(899,900));
    permutations[0][0].weight=0.4f; permutations[0][1].item.index=0; permutations[0][1].weight=0.4f;
    performance_timer_items_initialize(); assert(!performance_timer_items_due(899,900)); /* Game total truncates per entry. */
    collections[0].permutations.count=0;
    performance_timer_items_initialize(); assert(!performance_timer_items_due(899,900));
    equipment[0].item_collection.index=NONE;
    performance_timer_items_initialize(); assert(!performance_timer_items_due(899,900));
}
static void periods_and_history(void) {
    setup(); scenario.netgame_equipment.count=4;
    for(unsigned i=0;i<4;i++) equipment[i].item_collection.index=i;
    permutations[0][0].item.index=0; collections[0].spawn_time=120;
    permutations[1][0].item.index=1; collections[1].spawn_time=60;
    permutations[2][0].item.index=2; /* Zero seconds falls back to 30. */
    permutations[3][0].item.index=5; equipment[3].spawn_time=120;
    collections[3].spawn_time=45; /* Scenario interval takes precedence. */
    performance_timer_items_initialize();
    assert(!performance_timer_items_due(0,1));
    assert(performance_timer_items_due(899,900)==4);
    assert(performance_timer_items_due(1799,1800)==6);
    assert(performance_timer_items_due(3599,3600)==7); /* Duplicate rockets coalesce. */
    assert(performance_timer_items_due(3580,3610)==7);
    assert(!performance_timer_items_due(-1,3600));
    assert(!performance_timer_items_due(3600,3600));
    assert(!performance_timer_items_due(3601,3600));
    assert(!performance_timer_items_due(3569,3600));
    assert(!performance_timer_items_due(0,NONE));
    equipment[0].spawn_time=15;
    performance_timer_items_initialize(); assert(performance_timer_items_due(449,450)==1);
    equipment[0].spawn_time=-1;
    performance_timer_items_initialize(); assert(!performance_timer_items_due(449,450));
    scenario.netgame_equipment.count=0;
    performance_timer_items_initialize(); assert(!performance_timer_items_due(3599,3600));
}
static void game_types_capacity_and_read_only(void) {
    setup(); equipment[0].game_type[0]=game_engine_ctf;
    performance_timer_items_initialize(); assert(!performance_timer_items_due(899,900));
    equipment[0].game_type[1]=game_engine_slayer;
    performance_timer_items_initialize(); assert(performance_timer_items_due(899,900)==1);
    equipment[0].game_type[0]=_game_engine_all_normal; equipment[0].game_type[1]=0;
    performance_timer_items_initialize(); assert(performance_timer_items_due(899,900)==1);
    engine.type=game_engine_ctf;
    performance_timer_items_initialize(); assert(!performance_timer_items_due(899,900));
    equipment[0].game_type[0]=_game_engine_all;
    performance_timer_items_initialize(); assert(performance_timer_items_due(899,900)==1);
    memset(equipment[0].game_type,0,sizeof(equipment[0].game_type));
    performance_timer_items_initialize(); assert(!performance_timer_items_due(899,900));
    setup(); scenario.netgame_equipment.count=240;
    equipment[200].item_collection.index=1; permutations[1][0].item.index=1;
    struct scenario_netgame_equipment before[240]; memcpy(before,equipment,sizeof(before));
    struct item_collection_definition before_collections[16]; memcpy(before_collections,collections,sizeof(collections));
    struct item_permutation_definition before_permutations[16][8]; memcpy(before_permutations,permutations,sizeof(permutations));
    performance_timer_items_initialize();
    assert(performance_item_wave_count==200);
    assert(performance_timer_items_due(899,900)==1); /* Record 201 never read. */
    assert(!memcmp(before,equipment,sizeof(before)));
    assert(!memcmp(before_collections,collections,sizeof(collections)));
    assert(!memcmp(before_permutations,permutations,sizeof(permutations)));
}
int main(void) {
    categories_and_variant(); collection_predictability(); periods_and_history(); game_types_capacity_and_read_only();
    puts("Production item classification, timing, variant remap, filtering and read-only tags passed");
}
'''


class PerformanceTimerItems(unittest.TestCase):
    def test_production_item_classification(self):
        production = (ROOT / "port/linux/game/performance_timer_items.c").read_text()
        production = re.sub(r'^#include[^\n]*\n', '', production, flags=re.M)
        scenario = (ROOT / "source/scenario/scenario_definitions.h").read_text()
        items = (ROOT / "source/items/item_definitions.h").read_text()
        powerups = (ROOT / "source/items/equipment_definitions.h").read_text()
        engine = (ROOT / "source/game/game_engine.c").read_text()
        engine_header = (ROOT / "source/game/game_engine.h").read_text()
        declarations = "\n".join((
            block(engine_header, "enum game_engine_type\n") + ";",
            block(engine_header[engine_header.rfind("enum\n", 0, engine_header.index("_game_variant_no_shields_bit")):], "enum\n") + ";",
            block(engine[engine.rfind("enum\n", 0, engine.index("_game_engine_all =")):], "enum\n") + ";",
            block(powerups, "enum equipment_powerup_type\n") + ";",
            block(scenario, "struct scenario_netgame_equipment\n") + ";",
            block(items, "struct item_permutation_definition\n") + ";",
            block(items, "struct item_collection_definition\n") + ";",
        ))
        fixture = FIXTURE.replace("/* PRODUCTION DECLARATIONS */", declarations)
        fixture = fixture.replace("/* PRODUCTION GAME TYPE MATCH */", block(engine, "boolean match_game_type(\n"))
        fixture = fixture.replace("/* PRODUCTION */", production)
        with tempfile.TemporaryDirectory(prefix="halo-timer-items-") as folder:
            source, binary = Path(folder) / "fixture.c", Path(folder) / "fixture"
            source.write_text(fixture)
            compiled = subprocess.run(["clang", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                                       str(source), "-o", str(binary)], text=True, capture_output=True)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            result = subprocess.run([str(binary)], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
