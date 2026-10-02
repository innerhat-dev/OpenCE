"""Compile production equip, switch and animation sound hooks with controlled assets.

The fixture links the real provenance module. It compares native Normal/Silent
against the hooks-disabled path for voice creation, RNG and weapon state. Asset
animation/audio APIs are fixtures; this is not a runtime listening test.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.test_performance_variants import block

ROOT = Path(__file__).resolve().parents[1]


def definition(source, signature):
    return block(source[source.rindex(signature):], signature)


def enum_containing(source, value):
    start = source.rfind("\nenum", 0, source.index(value)) + 1
    return block(source[start:], "enum") + ";"


FIXTURE = r'''
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "performance_sound.h"
typedef int boolean;
typedef float real;
#define TRUE 1
#define FALSE 0
#define NONE (-1)
#define TAG_BLOCK_GET_ELEMENT(b,i,t) ((t *)element(b,i,sizeof(t)))
/* ENUMS */
enum { _director_perspective_first_person=0, _unit_base_weapon_none=0 };
struct tag_reference { long index; };
struct tag_block { int count; void *data; };
struct animation_state { short index, frame_index; };
struct animation { short sound_index; };
struct animation_graph_animation_index { short animation_index; };
struct animation_graph_sound_reference { struct tag_reference sound; };
struct animation_graph_first_person_weapon_animations { struct tag_block animations; };
struct animation_graph_weapon_class { const char *hand_marker_name, *grip_marker_name; };
struct animation_graph_unit_seat { struct tag_block weapon_classes; };
struct animation_graph { struct tag_block first_person_weapon_animations, animations, sound_references, unit_seats; };
struct weapon_datum { long definition_index; struct { int state, state_timer, control_flags; long overheated_effect_index; int rounds; } weapon; };
struct weapon_definition { struct { struct tag_reference ready_effect; struct { struct tag_reference first_person_animations; } interface_definition; } weapon; };
struct unit_definition { struct { struct tag_reference animation_graph; } object; };
struct unit_datum { long definition_index; struct {
    int current_weapon_index, desired_weapon_index;
    long weapon_last_used_at_game_time[2];
    struct { short seat_index, weapon_index, action; struct animation_state action_animation, base_animation, soft_ping_animation, overlay_action_animation; } animation;
} unit; };
struct first_person_weapon { long weapon_index, current_sound_index; short state, current_sound_state; struct animation_state state_animation; };
static struct unit_datum unit;
static struct unit_definition unit_definition;
static struct weapon_datum weapons[2];
static struct weapon_definition weapon_definitions[2];
static struct first_person_weapon fp;
static struct animation_graph graph;
static struct animation_graph_first_person_weapon_animations fp_animations;
static struct animation_graph_animation_index animation_indices[40];
static struct animation animations[40];
static struct animation_graph_sound_reference references[1];
static struct animation_graph_unit_seat seat;
static struct animation_graph_weapon_class weapon_class;
static const void *global_origin3d, *global_forward3d;
static unsigned silence, gameplay_rng=0x13579bdf, local_rng=0x2468ace0;
static int voices, reset_calls, effect_calls, detached, attached, unzoomed, deleted_effects;
static int local_player=0, perspective=0, trigger_frame=3, final_frame=5, pal_advance=1;
static float scale_sum;
static unsigned expected_role;
static long last_sound;
static void *element(const struct tag_block *b,int i,size_t size) { assert(i>=0 && i<b->count); return (char *)b->data+size*i; }
static struct weapon_datum *weapon_get(long i) { assert(i>=0 && i<2); return &weapons[i]; }
static struct weapon_datum *weapon_try_and_get(long i) { return i>=0 && i<2 ? &weapons[i]:NULL; }
static struct weapon_definition *weapon_definition_get(long i) { assert(i>=0 && i<2); return &weapon_definitions[i]; }
static struct unit_datum *unit_get(long i) { assert(i==10); return &unit; }
static struct unit_definition *unit_definition_get(long i) { assert(i==20); return &unit_definition; }
static struct animation_graph *animation_graph_definition_get(long i) { assert(i==30); return &graph; }
static struct animation_graph_animation_index *animation_graph_animation_index_get(struct tag_block *b) { return b->data; }
static long object_impulse_sound_new(long object,long sound,short node,const void *position,const void *forward,float scale) {
    (void)node; (void)position; (void)forward; assert(object==0 || object==1 || object==10); assert(sound==99);
    local_rng=local_rng*1664525u+1013904223u;
    last_sound=0x10000+(++voices); assert(voices<512); scale_sum+=scale;
    performance_sound_capture(_performance_sound_voice,last_sound);
#ifdef HALO_PORT_MAXIMUM_NETWORK_PLAYERS
    assert(performance_sound_current()==expected_role);
    assert(performance_sound_role(_performance_sound_voice,last_sound)==expected_role);
    assert(performance_sound_gain(last_sound,silence)==((expected_role & silence)?0.0f:1.0f));
#else
    assert(performance_sound_current()==0 && performance_sound_gain(last_sound,silence)==1.0f);
#endif
    return last_sound;
}
static void weapon_reset(long i) { assert(weapon_get(i)->weapon.rounds==17); reset_calls++; }
static boolean weapon_set_state(long i,int state,boolean immediate) { (void)immediate; weapon_get(i)->weapon.state=state; return TRUE; }
static boolean weapon_busy(long i) { (void)i; return FALSE; }
static void effect_delete(long i) { assert(i==44); deleted_effects++; }
static long weapon_effect_new(long i,long effect,real scale,real error) {
    assert(effect==77 && scale==0.0f && error==0.0f); effect_calls++;
    /* The real effect subsystem separately tests immediate/deferred inheritance. */
    unsigned saved_expected=expected_role; expected_role=_performance_sound_weapon_ready;
    object_impulse_sound_new(i,99,NONE,global_origin3d,global_forward3d,scale);
    expected_role=saved_expected; return 42;
}
static short weapon_get_first_person_animation_time(long i,short magazine,short animation,short frame) {
    (void)i; assert(magazine==0 && animation==_first_person_weapon_animation_ready && frame==NONE); return 35;
}
static short first_person_weapon_index_from_weapon_index(long i) { (void)i; return (short)local_player; }
static short director_get_perspective(short i) { assert(i==0); return (short)perspective; }
static int pal_tags_first_person_advance(short i,long graph_index,short animation,short frame) {
    (void)animation; (void)frame; assert(i==0 && graph_index==30); return pal_advance;
}
static short advance(struct animation_state *animation,long *sound) {
    *sound=animation->frame_index==trigger_frame ? 99:NONE;
    short result=animation->frame_index==final_frame ? _animation_will_restart_on_next_frame:_animation_no_key_frame;
    animation->frame_index++; return result;
}
static short animation_update_render_only(long i,struct animation_state *animation,long *sound) { assert(i==30); return advance(animation,sound); }
static short animation_update_internal(int gameplay,long i,struct animation_state *animation,long *sound) { assert(gameplay==1 && i==30); return advance(animation,sound); }
static void first_person_weapon_next_state(short i) { assert(i==0); fp.state=_first_person_weapon_state_idle; }
/* STATE MAPPINGS */
static void first_person_weapon_message(short i,short message) { if(i!=NONE) fp.state=(short)first_person_weapon_state_from_weapon_message(message); }
/* REMOTE SOUND */
/* MESSAGE */
/* WEAPON READY */
/* WEAPON PUT AWAY */
static long unit_get_desired_weapon_index(long i) { assert(i==10); return unit.unit.desired_weapon_index; }
static long unit_get_current_weapon_index(long i) { assert(i==10); return unit.unit.current_weapon_index; }
static void object_detach(long i) { assert(i==0 || i==1); detached++; }
static void object_disconnect_from_map(long i) { (void)i; }
static void object_activate(long i) { (void)i; }
static void object_set_visibility(long i,boolean visible) { (void)i; (void)visible; }
static void item_in_unit_inventory(long i,long owner) { (void)i; assert(owner==10); }
static const char *unit_get_seat_label(long i) { (void)i; return "stand"; }
static const char *weapon_get_label(long i) { (void)i; return "pistol"; }
static const char *base_weapon_label_get(int i) { (void)i; return "unarmed"; }
static void unit_set_or_test_seat_and_weapon_label(long i,const char *a,const char *b,boolean set) { (void)i; (void)a; (void)b; assert(set); }
static void object_reconnect_to_map(long i,void *p) { (void)i; assert(!p); }
static void object_attach_to_marker(long owner,const char *a,long i,const char *b) { (void)a; (void)b; assert(owner==10 && (i==0 || i==1)); attached++; }
static long game_time_get(void) { return 1234; }
static void unit_unzoom(long i) { assert(i==10); unzoomed++; }
/* UNIT READY */
/* UNIT ANIMATION */
static void local_animation_update(void) {
    short local_player_index=0;
    struct first_person_weapon *first_person_weapon=&fp;
    struct weapon_definition *weapon_definition=&weapon_definitions[0];
    long sound_definition_index;
    short animation_update_result;
#ifdef HALO_PORT_MAXIMUM_NETWORK_PLAYERS
    unsigned animation_sound_role;
#endif
/* LOCAL SOUND FRAME */
}
static void setup(void) {
    graph.first_person_weapon_animations=(struct tag_block){1,&fp_animations};
    graph.animations=(struct tag_block){40,animations}; graph.sound_references=(struct tag_block){1,references};
    graph.unit_seats=(struct tag_block){1,&seat}; seat.weapon_classes=(struct tag_block){1,&weapon_class};
    fp_animations.animations=(struct tag_block){40,animation_indices}; references[0].sound.index=99;
    for(int i=0;i<40;i++) { animation_indices[i].animation_index=(short)i; animations[i].sound_index=0; }
    for(int i=0;i<2;i++) { weapons[i].definition_index=i; weapons[i].weapon.rounds=17;
        weapons[i].weapon.overheated_effect_index=NONE; weapon_definitions[i].weapon.ready_effect.index=77;
        weapon_definitions[i].weapon.interface_definition.first_person_animations.index=30; }
    unit.definition_index=20; unit_definition.object.animation_graph.index=30;
    fp.weapon_index=0; fp.current_sound_index=NONE;
}
static void check_local(short state,unsigned role,int frame,boolean audible,boolean finish) {
    expected_role=role; fp.state=state; fp.state_animation.frame_index=(short)frame;
    trigger_frame=frame; final_frame=finish ? frame:frame+2;
    int before=voices; local_animation_update();
    assert(voices==before+(audible?1:0));
    assert(fp.state_animation.frame_index==frame+(pal_advance?1:0));
    assert(fp.state==((finish && pal_advance)?_first_person_weapon_state_idle:state));
    if(audible) assert(fp.current_sound_state==fp.state);
    assert(performance_sound_current()==_performance_sound_normal);
}
int main(int argc,char **argv) {
    assert(argc==2); silence=(unsigned)atoi(argv[1]); setup();
    /* Initial equip and respawn converge on the same production unit/weapon path. */
    for(int respawn=0;respawn<2;respawn++) {
        unit.unit.current_weapon_index=NONE; unit.unit.desired_weapon_index=0;
        int before=voices; unit_ready_desired_weapon(10,TRUE);
        assert(voices==before+1 && unit.unit.current_weapon_index==0);
        assert(weapons[0].weapon.state==_weapon_state_ready && weapons[0].weapon.state_timer==35);
        assert(unit.unit.weapon_last_used_at_game_time[0]==1234 && fp.state==_first_person_weapon_state_ready);
        check_local(_first_person_weapon_state_ready,_performance_sound_weapon_ready,3,TRUE,FALSE);
    }
    /* Real switch and put-away behavior keep ammo, reset, visibility and attach work. */
    unit.unit.desired_weapon_index=1; weapons[0].weapon.overheated_effect_index=44;
    unit_ready_desired_weapon(10,FALSE);
    assert(unit.unit.current_weapon_index==1 && detached==1 && attached==3 && unzoomed==3 && deleted_effects==1);
    assert(weapons[0].weapon.control_flags==0 && weapons[0].weapon.overheated_effect_index==NONE);
    assert(weapons[1].weapon.state_timer==35 && reset_calls==4 && effect_calls==3);
    assert(weapons[0].weapon.rounds==17 && weapons[1].weapon.rounds==17);
    check_local(_first_person_weapon_state_ready,_performance_sound_weapon_ready,0,TRUE,FALSE);
    check_local(_first_person_weapon_state_ready,_performance_sound_weapon_ready,5,TRUE,TRUE);
    check_local(_first_person_weapon_state_put_away,_performance_sound_weapon_ready,7,TRUE,TRUE);
    check_local(_first_person_weapon_state_primary_fire,_performance_sound_normal,2,TRUE,FALSE);
    check_local(_first_person_weapon_state_reload_while_full,_performance_sound_normal,4,TRUE,TRUE);
    check_local(_first_person_weapon_state_throw_grenade,_performance_sound_normal,1,TRUE,FALSE);
    check_local(_first_person_weapon_state_posing,_performance_sound_normal,1,TRUE,FALSE);
    perspective=1; check_local(_first_person_weapon_state_ready,_performance_sound_weapon_ready,0,FALSE,FALSE);
    perspective=0; pal_advance=0; check_local(_first_person_weapon_state_ready,_performance_sound_weapon_ready,2,FALSE,FALSE); pal_advance=1;
    /* Remote messages deliberately share the same sound tag for every event. */
    local_player=NONE;
    expected_role=_performance_sound_weapon_ready;
    unit.unit.current_weapon_index=NONE; unit.unit.desired_weapon_index=0;
    int remote_before=voices; unit_ready_desired_weapon(10,TRUE);
    assert(voices==remote_before+2 && weapons[0].weapon.state_timer==35);
    unit.unit.desired_weapon_index=1; remote_before=voices; unit_ready_desired_weapon(10,FALSE);
    assert(voices==remote_before+3 && weapons[1].weapon.state_timer==35);
    assert(weapons[0].weapon.rounds==17 && weapons[1].weapon.rounds==17);
    short messages[]={_first_person_weapon_message_ready,_first_person_weapon_message_put_away,
        _first_person_weapon_message_primary_fire,_first_person_weapon_message_reload_while_empty,
        _first_person_weapon_message_reload_while_full,_first_person_weapon_message_throw_grenade};
    for(unsigned i=0;i<sizeof(messages)/sizeof(*messages);i++) {
        expected_role=i<2 ? _performance_sound_weapon_ready:_performance_sound_normal;
        int before=voices; first_person_weapon_message_from_weapon(0,messages[i]);
        assert(voices==before+1 && performance_sound_current()==_performance_sound_normal);
    }
    /* Absent references remain silent; Normal must not synthesize a click. */
    int before=voices; references[0].sound.index=NONE;
    first_person_weapon_message_from_weapon(0,_first_person_weapon_message_ready);
    assert(voices==before); references[0].sound.index=99;
    /* Third-person ready/put-away action frames, including delayed/final frames. */
    struct animation_state *layers[]={&unit.unit.animation.action_animation,&unit.unit.animation.base_animation,
        &unit.unit.animation.soft_ping_animation,&unit.unit.animation.overlay_action_animation};
    for(int action=0;action<=9;action++) for(unsigned layer=0;layer<4;layer++) {
        unit.unit.animation.action=(short)action; layers[layer]->frame_index=5; trigger_frame=final_frame=5;
        expected_role=layer==0 && (action==3 || action==4) ? _performance_sound_weapon_ready:_performance_sound_normal;
        before=voices; assert(unit_animation_update(10,30,layers[layer])==_animation_will_restart_on_next_frame);
        assert(voices==before+1 && layers[layer]->frame_index==6 && unit.unit.animation.action==action);
        assert(performance_sound_current()==_performance_sound_normal);
    }
    /* No sound-frame creates no voice, and provenance nesting is balanced. */
    unit.unit.animation.action=3; unit.unit.animation.action_animation.frame_index=1; before=voices;
    assert(unit_animation_update(10,30,&unit.unit.animation.action_animation)==_animation_no_key_frame && voices==before);
#ifdef HALO_PORT_MAXIMUM_NETWORK_PLAYERS
    unsigned previous=performance_sound_push(_performance_sound_movement);
#endif
    expected_role=_performance_sound_weapon_ready; weapon_play_first_person_weapon_sound(0,_first_person_weapon_message_ready);
#ifdef HALO_PORT_MAXIMUM_NETWORK_PLAYERS
    assert(performance_sound_current()==_performance_sound_movement); performance_sound_pop(previous);
#endif
    assert(gameplay_rng==0x13579bdf && performance_sound_current()==0);
    printf("%d %u %u %.1f %d %d %d %d\n",voices,gameplay_rng,local_rng,scale_sum,
        reset_calls,effect_calls,weapons[0].weapon.rounds,weapons[1].weapon.rounds);
    return 0;
}
'''


class WeaponSoundEventTests(unittest.TestCase):
    def test_production_weapon_and_animation_events(self):
        weapons = (ROOT / "source/items/weapons.c").read_text()
        header = (ROOT / "source/items/weapons.h").read_text()
        first_person = (ROOT / "source/interface/first_person_weapons.c").read_text()
        units = (ROOT / "source/units/units.c").read_text()
        enums = [enum_containing(header, value) for value in (
            "_weapon_state_idle", "_first_person_weapon_message_primary_fire", "_first_person_weapon_animation_idle")]
        enums += [enum_containing(first_person, value) for value in (
            "_first_person_weapon_state_idle", "_animation_no_key_frame")]
        local = definition(first_person, "static void first_person_weapon_update(\n")
        local = local[local.index("\t\t/* port: a PAL map's"):local.index("\n\t\tmoving=")]
        replacements = {
            "/* ENUMS */": "\n".join(enums),
            "/* STATE MAPPINGS */": "\n".join(definition(first_person, signature) for signature in (
                "static long first_person_weapon_state_from_weapon_message(\n",
                "static long first_person_animation_type_from_weapon_state(\n")),
            "/* REMOTE SOUND */": definition(first_person, "static void weapon_play_first_person_weapon_sound(\n"),
            "/* MESSAGE */": definition(first_person, "void first_person_weapon_message_from_weapon(\n"),
            "/* WEAPON READY */": definition(weapons, "void weapon_ready(\n"),
            "/* WEAPON PUT AWAY */": definition(weapons, "boolean weapon_put_away(\n"),
            "/* UNIT READY */": definition(units, "static void unit_ready_desired_weapon(\n"),
            "/* UNIT ANIMATION */": definition(units, "static short unit_animation_update(\n"),
            "/* LOCAL SOUND FRAME */": local,
        }
        fixture = FIXTURE
        for marker, source in replacements.items():
            fixture = fixture.replace(marker, source)
        with tempfile.TemporaryDirectory(prefix="halo-weapon-sound-events-") as directory:
            path = Path(directory)
            source = path / "events.c"
            source.write_text(fixture)
            outputs = []
            for native in (False, True):
                executable = path / ("native" if native else "baseline")
                subprocess.run(["clang", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-Wno-unused-variable",
                    *(["-DHALO_PORT_MAXIMUM_NETWORK_PLAYERS=16"] if native else []),
                    f"-I{ROOT / 'port/linux/game'}", "-iquote", str(ROOT / 'port/linux/include'),
                    str(source), str(ROOT / "port/linux/game/performance_sound.c"), "-o", str(executable)], check=True)
                for silence in (0, 2):
                    result = subprocess.run([str(executable), str(silence)], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    outputs.append(result.stdout)
            self.assertEqual(len(set(outputs)), 1, outputs)


if __name__ == "__main__":
    unittest.main()
