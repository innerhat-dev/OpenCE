"""Run production host authorization and pre-join capabilities with socket stubs."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.test_performance_variants import block

ROOT = Path(__file__).resolve().parents[1]

FIXTURE = r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <wchar.h>
#include "networking/network_performance_protocol.h"
#include "performance_audio.h"
typedef unsigned char boolean;
typedef unsigned char byte;
typedef unsigned short word;
#define HALO_PORT_MAXIMUM_NETWORK_PLAYERS 16
#define MAXIMUM_NETWORK_MACHINE_COUNT 4
#define MAXIMUM_NETWORK_PLAYER_COUNT 16
#define MAXIMUM_MACHINE_NAME_LENGTH 16
#define NETWORK_GAME_NAME_LENGTH 16
#define TRUE 1
#define FALSE 0
#define NONE (-1)
#define VALID_INDEX(i,n) ((i)>=0 && (i)<(n))
#define match_assert(file,line,condition) assert(condition)
#define csmemcpy memcpy
#define csmemset memset
#define TEST_FLAG(value,bit) ((value)&(1U<<(bit)))
enum { _game_variant_draw_object_in_motion_sensor_bit=0, _game_variant_infinite_grenades_bit=2 };
#define network_event(...) ((void)0)
#define error(...) ((void)0)
#define ustrncpy wcsncpy
enum { _performance_option_timer_audio=4, PERFORMANCE_OPTIONS_MASK=31,
       _network_game_server_state_pregame=1, _network_game_server_state_ingame=2, _message_server_begin_game=2 };
struct game_variant { unsigned flags; struct {int teams, flags, vehicle_set, weapon_set;} universal_variant; };
struct network_game_server_client_machine {int machine_index,joined,local;};
#include "game/game_variant_options.h"
struct game_data {
    struct game_variant variant;
    struct game_variant_options variant_options;
    struct {char name[32]; int version;} map;
    wchar_t name[16]; int minimum_players,maximum_players,maximum_teams;
    int players[16],player_count;
};
struct network_game_server {
    struct network_game_server_client_machine client_machines[MAXIMUM_NETWORK_MACHINE_COUNT];
    struct game_data game; int state,sent_start_game_message,next_update_number;
};
struct network_game_client {void *connection;};
struct message_server_begin_game {int unused;};
static struct network_game_server server,*active=&server;
static struct game_variant runtime_variant,playlist_variant;
static byte network_game_server_performance_capabilities[MAXIMUM_NETWORK_MACHINE_COUNT];
static int network_game_server_start_players[16];
static boolean network_game_server_started_with_five_players;
static int recordings=1,apply_calls,override_calls,pregame_sends,setting_sends,start_sends,opened;
static unsigned runtime_flags,capabilities[4],capability_count;
static char shown[512];
int halo_performance_audio_available(void) {return recordings;}
static void platform_show_message(const char *title,const char *message) {
    snprintf(shown,sizeof(shown),"%s: %s",title,message);
}
static int network_game_server_client_machine_is_joined_to_game(struct network_game_server *s,
    struct network_game_server_client_machine *m) {(void)s;return m->joined;}
static int network_game_server_client_machine_is_local(struct network_game_server *s,
    struct network_game_server_client_machine *m) {(void)s;return m->local;}
static struct network_game_server *global_network_game_server_get(void) {return active;}
static struct game_variant *game_engine_get_variant(void) {return &runtime_variant;}
static void performance_variant_set_flags(struct game_variant *v,unsigned flags) {v->flags=flags;}
static unsigned performance_variant_get_flags(const struct game_variant *v) {return v->flags;}
static void game_engine_override_game_variant(struct game_variant *v) {(void)v;override_calls++;}
static void performance_options_apply_host_flags(unsigned flags) {runtime_flags=flags;apply_calls++;}
static int network_game_server_send_game_data_pregame(struct network_game_server *s) {(void)s;pregame_sends++;return TRUE;}
static int network_game_server_send_message_to_client_machine(struct network_game_server *s,
    struct network_game_server_client_machine *m,void *message) {
    unsigned flags=0;(void)s;(void)m;
    assert(network_performance_decode(message,NETWORK_PERFORMANCE_MESSAGE_SIZE,NETWORK_PERFORMANCE_SETTINGS,&flags));
    assert(flags==runtime_flags);setting_sends++;return TRUE;
}
static int game_engine_get_current_stage(struct game_variant *v,char *map) {
    *v=playlist_variant;strcpy(map,"chillout");return TRUE;
}
static void network_game_generate_local_machine_name(wchar_t *name) {wcscpy(name,L"fixture");}
static void network_game_server_open_game(struct network_game_server *s) {(void)s;opened++;}
static int network_game_server_send_game_settings_to_all_machines(struct network_game_server *s,void *g,unsigned size) {
    (void)s;(void)g;(void)size;return TRUE;
}
static void *create_network_game_message(unsigned kind,void *data,unsigned size) {
    static int message;(void)data;(void)size;assert(kind==_message_server_begin_game);return &message;
}
static int network_game_server_send_message_to_all_machines(struct network_game_server *s,void *m) {
    (void)s;(void)m;start_sends++;return TRUE;
}
static int network_game_client_write(void *connection,void *packet,unsigned size,void *address,int reliable) {
    (void)connection;assert(!address && reliable==1 && capability_count<4);
    assert(network_performance_decode(packet,size,NETWORK_PERFORMANCE_CAPABILITY,&capabilities[capability_count++]));
    return TRUE;
}
/* PRODUCTION */
static boolean announce(struct network_game_client *client) {
    /* PRODUCTION ANNOUNCEMENT */
    return TRUE;
}
static void unchanged(unsigned flags,int calls) {
    assert(server.game.variant.flags==flags && runtime_flags==flags && apply_calls==calls);
}
int main(void) {
    server.state=_network_game_server_state_pregame;
    for(int i=0;i<4;i++) server.client_machines[i].machine_index=i;
    server.client_machines[0].joined=server.client_machines[0].local=TRUE;
    server.client_machines[1].joined=TRUE;
    network_game_server_performance_capability(&server.client_machines[1],3);
    recordings=0;
    assert(!performance_options_set_host_flags(4));unchanged(0,0);
    assert(strstr(shown,"timer recordings missing"));
    assert(performance_options_set_host_flags(3));unchanged(3,1);
    assert(!performance_options_set_host_flags(7));unchanged(3,1);
    recordings=1;
    assert(!performance_options_set_host_flags(7));unchanged(3,1);
    assert(strstr(shown,"connected player"));
    network_game_server_performance_capability(&server.client_machines[1],7);
    assert(performance_options_set_host_flags(7));unchanged(7,2);
    assert(pregame_sends==2 && setting_sends==2 && override_calls==2);
    assert(!performance_options_set_host_flags(8));unchanged(7,2);
    active=NULL;assert(!performance_options_set_host_flags(0));unchanged(7,2);active=&server;
    assert(performance_options_set_host_flags(0));unchanged(0,3);
    /* The three-option peer cannot accept either sound rule. Upgraded peers
     * agree live on all combinations; stock restoration remains available. */
    assert(!performance_options_set_host_flags(16));unchanged(0,3);
    network_game_server_performance_capability(&server.client_machines[1],31);
    assert(performance_options_set_host_flags(8));unchanged(8,4);
    assert(performance_options_set_host_flags(16));unchanged(16,5);
    assert(performance_options_set_host_flags(31));unchanged(31,6);
    assert(performance_options_set_host_flags(0));unchanged(0,7);
    assert(!performance_options_set_host_flags(32));unchanged(0,7);
    apply_calls=3;
    /* Saved variant selection cannot bypass the same missing-pack gate. */
    struct game_variant chosen={.flags=7};recordings=0;
    network_game_server_change_game_variant(&server,&chosen);unchanged(0,3);
    recordings=1;network_game_server_change_game_variant(&server,&chosen);unchanged(7,4);
    /* Recheck at start and when the playlist supplies an enabled variant. */
    recordings=0;assert(!network_game_server_start_network_game(&server));
    assert(!server.sent_start_game_message && !start_sends);
    playlist_variant.flags=7;assert(!network_game_server_setup_game_from_playlist(&server));
    assert(!opened && apply_calls==4);
    recordings=1;assert(network_game_server_setup_game_from_playlist(&server));
    assert(opened==1 && apply_calls==5);
    assert(network_game_server_start_network_game(&server));
    assert(server.sent_start_game_message && start_sends==1);
    /* Compile the actual ordered client announcement; missing assets must
     * never advertise audio support to an enabled host. */
    struct network_game_client client={0};
    recordings=0;capability_count=0;assert(announce(&client));
    assert(capability_count==3 && capabilities[0]==3 && capabilities[1]==3 && capabilities[2]==27);
    recordings=1;capability_count=0;assert(announce(&client));
    assert(capability_count==3 && capabilities[0]==3 && capabilities[1]==7 && capabilities[2]==31);
    /* Keep the Xbox grenade cutoff without admitting a mixed-rules match.
     * Four players still interoperate; a fork-only five-player game is safe. */
    server.game.variant.flags=0; server.game.variant.universal_variant.flags=4;
    server.game.player_count=5; server.sent_start_game_message=FALSE;
    network_game_server_performance_capabilities[1]=0;
    assert(!network_game_server_start_network_game(&server));
    assert(strstr(shown,"grenade cutoff") && !server.sent_start_game_message);
    server.game.player_count=4;
    assert(network_game_server_original_grenade_peers_support(&server,&server.game.variant,4));
    assert(!network_game_server_original_grenade_peers_support(&server,&server.game.variant,5));
    network_game_server_performance_capabilities[1]=31;
    assert(network_game_server_original_grenade_peers_support(&server,&server.game.variant,5));
    assert(network_game_server_start_network_game(&server));
    /* A match's Xbox threshold is fixed at start. A newly loading machine
     * must not derive a different threshold from a changed player count. */
    server.state=_network_game_server_state_ingame;
    network_game_server_started_with_five_players=FALSE;
    assert(network_game_server_original_grenade_peers_support(&server,&server.game.variant,4));
    assert(!network_game_server_original_grenade_peers_support(&server,&server.game.variant,5));
    assert(strstr(shown,"newly loading machine"));
    network_game_server_started_with_five_players=TRUE;
    assert(!network_game_server_original_grenade_peers_support(&server,&server.game.variant,4));
    assert(network_game_server_original_grenade_peers_support(&server,&server.game.variant,5));
    network_game_server_performance_capabilities[1]=0;
    assert(!network_game_server_original_grenade_peers_support(&server,&server.game.variant,5));
    server.game.variant.universal_variant.flags=0;
    assert(network_game_server_original_grenade_peers_support(&server,&server.game.variant,4));
    assert(network_game_server_original_grenade_peers_support(&server,&server.game.variant,5));
    puts("performance host authority, assets, saved variants and capabilities: PASS");
    return 0;
}
'''


class PerformanceNetworkTests(unittest.TestCase):
    def test_production_host_gate_and_client_capabilities(self):
        server = (ROOT / "source/networking/network_server_manager.c").read_text()
        functions = "\n".join(block(server, signature) for signature in (
            "void network_game_server_performance_capability(\n",
            "boolean network_game_server_performance_supported(\n",
            "static boolean network_game_server_performance_peers_support(\n",
            "static boolean network_game_server_original_grenade_peers_support(\n",
            "boolean performance_options_set_host_flags(\n",
            "void network_game_server_change_game_variant(\n",
            "boolean network_game_server_start_network_game(\n",
        ))
        private = server[server.index("/* ---------- private code */"):]
        functions += "\n" + block(private, "static boolean network_game_server_setup_game_from_playlist(\n")
        client = (ROOT / "source/networking/network_client_manager.c").read_text()
        start = client.index("word capability[NETWORK_PERFORMANCE_MESSAGE_SIZE / sizeof(word)];")
        end = client.index("csmemset(&join_game_request", start)
        fixture = FIXTURE.replace("/* PRODUCTION */", functions)
        fixture = fixture.replace("/* PRODUCTION ANNOUNCEMENT */", client[start:end])
        with tempfile.TemporaryDirectory(prefix="halo-pb-network-") as temporary:
            source = Path(temporary) / "network.c"
            binary = Path(temporary) / "network"
            source.write_text(fixture)
            subprocess.run([
                "cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-I", str(ROOT / "source"),
                "-iquote", str(ROOT / "port/linux/include"), str(source), "-o", str(binary),
            ], check=True)
            subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    unittest.main()
