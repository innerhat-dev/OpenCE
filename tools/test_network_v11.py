"""Exercise production v11 settings layout, reassembly and admission boundaries.

The guest's long and wchar are 32/16 bits. Fixtures substitute fixed-width
types for host execution; socket transport and full game loading need runtime
validation separately. The fork's gameplay rules are intentionally unchanged.
"""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from tools.test_network_pings import block

ROOT = Path(__file__).resolve().parents[1]

PREFIX = r'''
#include <assert.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "halo_port_limits.h"
#include "networking/network_performance_protocol.h"
typedef unsigned char byte, boolean;
typedef unsigned short word;
typedef float real;
#define TRUE 1
#define FALSE 0
#define NONE (-1)
#define FLAG(bit) (1U<<(bit))
#define TEST_FLAG(value,bit) ((value)&FLAG(bit))
#define csmemset memset
#define csmemcpy memcpy
#define csstrcmp strcmp
#define csprintf(destination,...) snprintf(destination,sizeof(destination),__VA_ARGS__)
#define VALID_INDEX(i,n) ((i)>=0 && (i)<(n))
#define MAXIMUM_ODDBALLS 16
#define MAXIMUM_NETWORK_MACHINE_COUNT 128
#define MAXIMUM_NUMBER_OF_PLAYERS 128
#define NUMBER_OF_GAME_DIFFICULTY_LEVELS 4
#define HALO_PORT_MAXIMUM_NETWORK_PLAYERS 128
#define _error_network_failed_to_join_game 7
#define match_assert(file,line,condition) assert(condition)
#define network_event(...) ((void)0)
enum { _game_variant_draw_object_in_motion_sensor_bit=0, _game_variant_infinite_grenades_bit=2 };
/* DECLARATIONS */
#include "game/game_variant_options.h"
struct network_player { byte wire[32]; };
/* RECORD */
struct network_game_client { struct network_game game; };
struct network_game_server { struct network_game game; };
static struct network_game_client client;
static struct network_game_server *active_server;
static boolean network_game_client_original_rules_host;
static struct network_game network_game_client_settings_staging;
static int32_t network_game_client_settings_staging_size;
static unsigned precaches, dialogs, applied, errors;
static char shown[600];
static int network_game_client_map_name_is_valid(const char *name, unsigned size) {
    return name[0] && memchr(name,0,size)!=NULL;
}
static int network_game_is_splitscreen_local(void) { return 0; }
static int cache_files_map_plays_multiplayer(const char *map,char *build) {
    (void)map; (void)build; return 1;
}
static void cache_files_show_multiplayer_unavailable(const char *map,const char *build) {
    (void)map; (void)build; assert(0);
}
static void main_set_multiplayer_map_name(const char *map) { (void)map; precaches++; }
static struct network_game_server *global_network_game_server_get(void) { return active_server; }
static struct network_game *network_game_server_get_game(struct network_game_server *s) { return &s->game; }
static unsigned performance_variant_get_flags(const struct game_variant *v) { return v->flags; }
static void performance_options_apply_host_flags(unsigned flags) { (void)flags; applied++; }
static void platform_show_message(const char *title,const char *message) {
    (void)title; snprintf(shown,sizeof(shown),"%s",message); dialogs++;
}
static void display_error_when_main_menu_loaded(unsigned error) {
    assert(error==7); errors++;
}
/* FUNCTIONS */
'''

HARNESS = r'''
static struct network_game defaults(void) {
    struct network_game game={0};
    strcpy(game.map.name,"chillout"); game.machine_count=2; game.player_count=2;
    game.difficulty=1; game.variant.universal_variant.vehicle_set=2;
    game_variant_options_default(&game.variant,&game.variant_options);
    return game;
}
static void reset(void) {
    memset(&client,0,sizeof(client)); network_game_client_original_rules_host=0;
    precaches=dialogs=applied=errors=0; active_server=NULL;
    network_game_client_settings_staging_size=0;
}
static void wire(void) {
    assert(HALO_PORT_NETWORK_VERSION==11);
    assert(sizeof(struct network_game)==13120);
    assert(offsetof(struct network_game,variant_options)==HALO_PORT_NETWORK_GAME_VARIANT_OPTIONS_OFFSET);
    assert(offsetof(struct network_game,local_data)==HALO_PORT_NETWORK_GAME_LOCAL_DATA_OFFSET);
    assert(sizeof(struct game_variant_options)==28);
    assert(offsetof(struct game_variant_options,radar_players)==9);
    assert(offsetof(struct game_variant_options,loadout)==24);
    assert((NETWORK_PERFORMANCE_ADVERTISED_FLAG & HALO_PORT_ADVERTISED_IN_PROGRESS_FLAG)==0);
    assert(network_performance_advertised_version(0,11)==11);
    assert(network_performance_advertised_version(1,11)==0x800B);
    assert(network_performance_version_compatible(0x800B,4,11));
    assert(!network_performance_version_compatible(0x800B,2,11));
    assert(!network_performance_version_compatible(0x800A,4,11));
    assert(!network_performance_version_compatible(10,4,11));
    byte encoded[16]; unsigned flags;
    network_performance_encode(encoded,NETWORK_PERFORMANCE_SETTINGS,31);
    assert(network_performance_decode(encoded,16,NETWORK_PERFORMANCE_SETTINGS,&flags) && flags==31);
}
static void options(void) {
    struct network_game game=defaults();
    const byte expected[28]={0,0,0,0,0,0,0,0,0,2,2,2,0,0,0,0,0,0,0,0,0,0,0,0,0,2,3,0};
    assert(!memcmp(expected,&game.variant_options,28));
    assert(!game_variant_options_unsupported(&game.variant,&game.variant_options));
    for(unsigned field=0;field<28;field++) {
        struct game_variant_options changed=game.variant_options;
        ((byte *)&changed)[field]++;
        /* Inactive counts, category weapons and padding are semantically ignored. */
        assert((game_variant_options_unsupported(&game.variant,&changed)!=NULL)==
            (field<12 || field==24));
    }
    game.variant.universal_variant.flags=1;
    game_variant_options_default(&game.variant,&game.variant_options);
    assert(game.variant_options.radar_players==0);
    for(int set=0;set<=10;set++) {
        game.variant.universal_variant.weapon_set=set;
        assert(!game_variant_options_unsupported(&game.variant,&game.variant_options));
    }
    game.variant.universal_variant.weapon_set=11;
    assert(strstr(game_variant_options_unsupported(&game.variant,&game.variant_options),"weapon set"));
}
static void admission(void) {
    struct network_game game=defaults(); reset();
    client.game.local_data.game_objects_loaded=1;
    assert(network_game_client_game_settings_updated(&client,&game));
    assert(precaches==1 && applied==1 && client.game.local_data.game_objects_loaded==1);
    struct network_game before=client.game;
    strcpy(game.map.name,"bloodgulch"); game.variant_options.time_limit=10;
    assert(!network_game_client_game_settings_updated(&client,&game));
    assert(precaches==1 && applied==1 && dialogs==1 && errors==1);
    assert(strstr(shown,"time limit") && !memcmp(&before,&client.game,sizeof(before)));
    game=defaults(); game.player_count=5; game.variant.universal_variant.flags=4;
    assert(!network_game_client_game_settings_updated(&client,&game));
    assert(strstr(shown,"infinite grenades"));
    network_game_client_original_rules_host=1;
    assert(network_game_client_game_settings_updated(&client,&game));
}
static int send_record(struct network_game *game) {
    int result=1;
    for(unsigned offset=0;offset<sizeof(*game);offset+=HALO_PORT_NETWORK_GAME_SETTINGS_FRAGMENT_SIZE) {
        struct message_server_game_settings_update piece={0};
        piece.total_size=sizeof(*game); piece.offset=offset;
        piece.length=sizeof(*game)-offset;
        if(piece.length>sizeof(piece.data)) piece.length=sizeof(piece.data);
        memcpy(piece.data,(byte *)game+offset,piece.length);
        result=network_game_client_receive_game_settings_piece(&client,&piece);
        if(offset+piece.length<sizeof(*game)) assert(!applied && !precaches);
    }
    return result;
}
static void fragments(void) {
    struct network_game game=defaults(); reset();
    assert(send_record(&game) && applied==1 && precaches==1);
    reset(); game.variant_options.loadout=1;
    assert(!send_record(&game) && !applied && !precaches && dialogs==1);
    reset(); struct message_server_game_settings_update piece={0};
    piece.total_size=13092; piece.length=1;
    assert(!network_game_client_receive_game_settings_piece(&client,&piece));
    piece.total_size=sizeof(game); piece.offset=1;
    assert(network_game_client_receive_game_settings_piece(&client,&piece));
    assert(!applied && !precaches && !network_game_client_settings_staging_size);
    piece.offset=sizeof(game)-1; piece.length=2;
    assert(!network_game_client_receive_game_settings_piece(&client,&piece));
}
int main(int argc,char **argv) {
    assert(argc==2);
    if(!strcmp(argv[1],"wire")) wire();
    else if(!strcmp(argv[1],"options")) options();
    else if(!strcmp(argv[1],"admission")) admission();
    else if(!strcmp(argv[1],"fragments")) fragments();
    else assert(0);
    return 0;
}
'''


class NetworkV11Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix="halo-v11-")
        cls.addClassCleanup(cls.directory.cleanup)
        engine = (ROOT / "source/game/game_engine.h").read_text()
        names = ("universal_variant", "ctf_variant", "slayer_variant", "king_variant", "oddball_variant", "race_variant")
        declarations = "\n".join(block(engine, f"struct {name}\n") + ";" for name in names)
        declarations += "\n" + block(engine, "union game_engine_variant\n") + ";"
        declarations += "\n" + block(engine, "struct game_variant\n") + ";"
        manager = (ROOT / "source/networking/network_game_manager.h").read_text()
        record = "\n".join(block(manager, f"struct {name}\n") + ";" for name in (
            "network_machine", "network_game_map", "network_game_local_data", "network_game"))
        client = (ROOT / "source/networking/network_client_manager.c").read_text()
        handler = (ROOT / "source/networking/network_client_message_handler.c").read_text()
        record += "\n" + block(handler, "struct message_server_game_settings_update\n") + ";"
        functions = block(client, "boolean network_game_client_game_settings_updated(\n")
        functions += "\n" + block(handler, "static boolean network_game_client_receive_game_settings_piece(\n")
        source = PREFIX.replace("/* DECLARATIONS */", declarations).replace("/* RECORD */", record)
        source = source.replace("/* FUNCTIONS */", functions) + HARNESS
        source = re.sub(r"\blong\b", "int32_t", source).replace("unsigned int32_t", "uint32_t")
        source = source.replace("wchar_t", "uint16_t")
        path = Path(cls.directory.name) / "v11.c"
        path.write_text(source)
        cls.executable = path.with_suffix("")
        result = subprocess.run([
            "clang", "-std=c11", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined",
            "-I", str(ROOT / "source"), "-iquote", str(ROOT / "port/linux/include"),
            str(path), "-o", str(cls.executable),
        ], capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise AssertionError(result.stderr)

    def run_case(self, case):
        result = subprocess.run([str(self.executable), case], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_wire_layout_and_pb_namespace(self):
        self.run_case("wire")

    def test_original_defaults_and_active_option_boundaries(self):
        self.run_case("options")

    def test_reject_before_precache_and_live_state_change(self):
        self.run_case("admission")

    def test_fragment_reassembly_and_mixed_version_rejection(self):
        self.run_case("fragments")


if __name__ == "__main__":
    unittest.main()
