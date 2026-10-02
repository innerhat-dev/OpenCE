"""Exercise the actual optional-practice runtime against a deterministic game fixture.

This covers authority-state consumption, marker ownership and deferred deletion,
map replacement, gameplay RNG preservation, and use of the host game clock.
It does not claim to validate graphics, sockets or the compiled map tags.
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
#include <strings.h>
#include <stdlib.h>
#include <math.h>
#include "performance_timer_schedule.h"
#include "performance_audio.h"
typedef int boolean;
typedef unsigned char byte;
typedef float real;
typedef struct { float x, y, z; } real_point3d;
typedef struct { short x0, y0, x1, y1; } rectangle2d;
typedef struct { float a, r, g, b; } real_argb_color;
#define TRUE 1
#define FALSE 0
#define NONE (-1)
#define NUMBEROF(a) (sizeof(a) / sizeof(*(a)))
#define VALID_INDEX(i,n) ((i) >= 0 && (i) < (n))
#define MIN(a,b) ((a) < (b) ? (a) : (b))
#define TEST_FLAG(v,b) (((v) & (1u << (b))) != 0)
#define SET_FLAG(v,b,on) ((v) = (on) ? (v) | (1u << (b)) : (v) & ~(1u << (b)))
#define _stricmp strcasecmp
#define TICKS_PER_SECOND 30
#define MAXIMUM_OBJECT_NAMES_PER_SCENARIO 512
/* PRODUCTION DECLARATIONS */
enum { _object_type_scenery = 6, _object_function_none = 0,
       _object_no_collisions_bit = 0, _object_cannot_take_damage_bit = 1,
       _object_header_being_deleted_bit = 2, _object_invisible_bit = 3 };
struct tag_block { long count; void *data; };
struct tag_reference { long index; };
struct object_definition { struct {
    short type;
    struct tag_reference model, animation_graph, collision_model, physics, creation_effect;
    struct tag_block attachments, widgets, functions;
    short function_modes[4];
} object; };
struct scenario_object_name { char name[32]; short runtime_object_type, runtime_scenario_datum_index; };
struct scenario_object_datum { short name_index, palette_entry_index; };
struct scenario_object_palette_entry { struct tag_reference reference; };
struct scenario { struct tag_block object_names, scenery_palette, scenery, players; };
struct object_datum { long definition_index; struct {
    short type, name_index; unsigned flags, damage_flags;
} object; };
struct object_header_datum { unsigned flags; };
struct game_variant { unsigned flags; };
static struct game_variant variant;
static struct scenario scenario;
static struct scenario_object_name names[5];
static struct scenario_object_datum placements[5];
static struct scenario_object_palette_entry palette[2];
static struct object_definition definitions[2];
static const char *tag_names[2];
static struct object_datum objects[16];
static struct object_header_datum headers[16];
static long object_ids[16], name_objects[5];
static int next_id = 1, creates, deletes, in_game = 1, engine_running = 1, initialized = 1;
static int client, cinematic, postgame, draw_count, menu_active;
static int audio_plays, audio_stops, audio_mixer_busy, line_count, active_bsp;
static struct {long type;} engine={game_engine_slayer},*game_engine=&engine;
static char audio_cue[64];
static struct {long tick; char cue[64];} audio_history[512];
static unsigned timer_preferences=7,item_due_mask;
static long item_due_tick=NONE,item_duration=20;
static int item_initializations;
static real_point3d line_from[64], line_to[64];
static struct player_starting_location starts[600];
static long local_ticks, host_ticks = NONE;
static unsigned long rng = 1234;
static char drawn_text[32];
static struct { struct { rectangle2d window_bounds; } camera; } render;
static void *tag_block_get_element_with_size(const struct tag_block *block, long i, long size) {
    assert(VALID_INDEX(i, block->count)); return (char *)block->data + size * i;
}
#define TAG_BLOCK_GET_ELEMENT(b,i,t) ((t *)tag_block_get_element_with_size(b,i,sizeof(t)))
static const char *tag_get_name(long i) { assert(VALID_INDEX(i,2)); return tag_names[i]; }
static struct object_definition *object_definition_get(long i) { assert(VALID_INDEX(i,2)); return &definitions[i]; }
static struct scenario *global_scenario_get(void) { return &scenario; }
static struct tag_block *scenario_get_object_type_scenario_datums(struct scenario *s, short type, long *size) {
    assert(type == _object_type_scenery); *size = sizeof(*placements); return &s->scenery;
}
static boolean game_engine_running(void) { return engine_running; }
static short global_structure_bsp_index_get(void) { return active_bsp; }
/* PRODUCTION GAME TYPE MATCH */
static boolean game_in_progress(void) { return in_game; }
static boolean ui_widgets_active(void) { return menu_active; }
static boolean game_time_initialized(void) { return initialized; }
static struct game_variant *game_engine_get_variant(void) { return &variant; }
static unsigned performance_variant_get_flags(const struct game_variant *v) { return v->flags; }
static struct object_datum *object_try_and_get(long id) {
    for (int i = 0; i < 16; i++) if (object_ids[i] == id && id != NONE) return &objects[i];
    return NULL;
}
static struct object_header_datum *object_header_get(long id) {
    struct object_datum *o = object_try_and_get(id); assert(o); return &headers[o - objects];
}
static long object_index_from_name_index(short name) { assert(VALID_INDEX(name,5)); return name_objects[name]; }
static long object_new_by_name(short name) {
    assert(name_objects[name] == NONE);
    for (int i = 0; i < 16; i++) if (object_ids[i] == NONE) {
        object_ids[i] = next_id++; name_objects[name] = object_ids[i];
        objects[i].definition_index = palette[placements[name].palette_entry_index].reference.index;
        objects[i].object.type = _object_type_scenery; objects[i].object.name_index = name;
        objects[i].object.flags = objects[i].object.damage_flags = headers[i].flags = 0;
        rng = rng * 1664525 + 1013904223; creates++; return object_ids[i];
    }
    return NONE;
}
static void object_delete(long id) {
    struct object_header_datum *h = object_header_get(id);
    assert(!TEST_FLAG(h->flags, _object_header_being_deleted_bit));
    SET_FLAG(h->flags, _object_header_being_deleted_bit, TRUE); deletes++;
}
static void finish_deletes(void) {
    for (int i = 0; i < 16; i++) if (object_ids[i] != NONE && TEST_FLAG(headers[i].flags, _object_header_being_deleted_bit)) {
        name_objects[objects[i].object.name_index] = NONE; object_ids[i] = NONE;
    }
}
static unsigned long get_random_seed(void) { return rng; }
static void set_random_seed(unsigned long seed) { rng = seed; }
static boolean network_game_distributed_client(void) { return client; }
static long distributed_latest_host_time(void) { return host_ticks; }
static long game_time_get(void) { return local_ticks; }
static boolean cinematic_in_progress(void) { return cinematic; }
static boolean game_engine_showing_postgame(void) { return postgame; }
int halo_performance_audio_play(const char *cue,float volume) {
    assert(volume == 1.0f && audio_plays<(int)NUMBEROF(audio_history));
    audio_history[audio_plays].tick=client ? host_ticks:local_ticks;
    snprintf(audio_history[audio_plays].cue,sizeof(audio_history[audio_plays].cue),"%s",cue);
    audio_plays++; snprintf(audio_cue,sizeof(audio_cue),"%s",cue);
    return 1;
}
void halo_performance_audio_stop(void) { audio_stops++; audio_mixer_busy=0; }
int halo_performance_audio_busy(void) { return audio_mixer_busy; }
long halo_performance_audio_duration_ticks(const char *cue) {
    if(!strcmp(cue,"rocket") || !strcmp(cue,"camo") || !strcmp(cue,"overshield")) return item_duration;
    return !strcmp(cue,"timerbeep") ? 8:16;
}
static int config_boolean(const char *name) {
    static const char *const names[]={"audio.timer_countdown","audio.timer_beeps","audio.timer_minutes","audio.timer_items"};
    for(unsigned i=0;i<NUMBEROF(names);i++) if(!strcmp(name,names[i])) return (timer_preferences>>i)&1;
    assert(0); return 0;
}
void performance_timer_items_initialize(void) { item_initializations++; }
unsigned performance_timer_items_due(long previous,long current) {
    if(previous<0 || current<=previous || current-previous>30) return 0;
    return previous<item_due_tick && current>=item_due_tick ? item_due_mask:0;
}
static float cosine(float angle) { return cosf(angle); }
static float sine(float angle) { return sinf(angle); }
static void rasterizer_debug_line(const real_point3d *from,const real_point3d *to,const real_argb_color *color) {
    assert(isfinite(from->x) && isfinite(from->y) && isfinite(from->z));
    assert(isfinite(to->x) && isfinite(to->y) && isfinite(to->z));
    assert(color->a == 1.0f && color->g == 1.0f);
    if(line_count < 64) { line_from[line_count]=*from; line_to[line_count]=*to; }
    line_count++;
}
long performance_options_timer_ticks(void);
void performance_timer_render(long ticks) {
    if(ticks<0) return;
    long seconds=ticks/30;
    snprintf(drawn_text,sizeof(drawn_text),"%02ld:%02ld",seconds/60,seconds%60); draw_count++;
}
/* PRODUCTION */
/* EXTENDED CHECKS */
static void setup(void) {
    scenario.object_names = (struct tag_block){5, names};
    scenario.scenery = (struct tag_block){5, placements};
    scenario.scenery_palette = (struct tag_block){2, palette};
    for (int i = 0; i < 5; i++) {
        snprintf(names[i].name, sizeof(names[i].name), "spawn_marker%d", i);
        names[i].runtime_object_type = _object_type_scenery; names[i].runtime_scenario_datum_index = i;
        placements[i] = (struct scenario_object_datum){i, 0}; name_objects[i] = NONE;
    }
    for (int i = 0; i < 16; i++) object_ids[i] = NONE;
    palette[0].reference.index = 0; palette[1].reference.index = 1;
    tag_names[0] = "scenery\\spawn_marker_nhe\\spawn_marker_nhe";
    tag_names[1] = "scenery\\randoms\\prisoner_randoms";
    definitions[0].object.type = _object_type_scenery;
    definitions[0].object.model.index = 3;
    definitions[0].object.animation_graph.index = definitions[0].object.collision_model.index = NONE;
    definitions[0].object.physics.index = definitions[0].object.creation_effect.index = NONE;
    strcpy(names[2].name, "randoms"); /* Never recreate random-training objects. */
    placements[3].palette_entry_index = 1; /* Correct prefix, wrong tag. */
    names[4].runtime_object_type = 2; /* Correct prefix, wrong object type. */
    render.camera.window_bounds = (rectangle2d){0,0,640,480};
}
int main(void) {
    setup(); assert(performance_options_get_flags() == 0);
    performance_options_initialize_for_new_map();
    assert(performance_options_markers_supported_count() == 2);
    performance_options_update(); assert(creates == 0 && deletes == 0);
    /* Existing startup scenery is left alone, even on toggle off. */
    long startup = object_new_by_name(0); unsigned long seed = rng;
    performance_options_apply_host_flags(2); performance_options_update();
    assert(creates == 2 && rng == seed && performance_options_markers_visible_count() == 1);
    long owned = name_objects[1]; struct object_datum *o = object_try_and_get(owned);
    assert(TEST_FLAG(o->object.flags, _object_no_collisions_bit));
    assert(TEST_FLAG(o->object.damage_flags, _object_cannot_take_damage_bit));
    performance_options_update(); assert(creates == 2);
    performance_options_apply_host_flags(0); performance_options_update();
    assert(deletes == 1 && name_objects[0] == startup && performance_options_markers_visible_count() == 0);
    /* A rapid off/on before deferred deletion must not create a duplicate. */
    performance_options_apply_host_flags(2); performance_options_update(); assert(creates == 2);
    finish_deletes(); performance_options_update(); assert(creates == 3);
    /* Startup cleanup after option activation is recovered on the next tick. */
    object_delete(startup); performance_options_update(); assert(creates == 3);
    finish_deletes(); performance_options_update();
    assert(creates == 4 && performance_options_markers_visible_count() == 2 && rng == seed);
    /* A script replaces one owned marker: the toggle never deletes its replacement. */
    object_delete(name_objects[1]); finish_deletes(); long replacement = object_new_by_name(1);
    performance_options_apply_host_flags(0); performance_options_update();
    assert(!TEST_FLAG(object_header_get(replacement)->flags, _object_header_being_deleted_bit));
    finish_deletes();
    performance_options_apply_host_flags(0x82); assert(performance_options_get_flags() == 0);
    /* Reload discards old ownership and re-reads the authoritative variant. */
    performance_options_dispose_from_old_map(); assert(performance_options_markers_supported_count() == 0);
    variant.flags = 3; performance_options_initialize_for_new_map();
    assert(performance_options_get_flags() == 3 && performance_options_markers_visible_count() == 0);
    performance_options_apply_host_flags(0); performance_options_update();
    assert(!TEST_FLAG(object_header_get(replacement)->flags, _object_header_being_deleted_bit));
    /* Unsafe map content cannot be turned into an effect or collision source. */
    definitions[0].object.creation_effect.index = 7;
    performance_options_initialize_for_new_map(); assert(performance_options_markers_supported_count() == 0);
    definitions[0].object.creation_effect.index = NONE; definitions[0].object.function_modes[0] = 5;
    performance_options_initialize_for_new_map(); assert(performance_options_markers_supported_count() == 0);
    definitions[0].object.function_modes[0] = 0; engine_running = 0;
    performance_options_initialize_for_new_map(); assert(performance_options_get_flags() == 0);
    assert(performance_options_timer_ticks() == NONE); engine_running = 1;
    local_ticks = 1859; assert(performance_options_timer_ticks() == 1859);
    client = 1; host_ticks = 1800; local_ticks = 99000;
    assert(performance_options_timer_ticks() == 1800);
    performance_options_apply_host_flags(1); performance_options_render();
    assert(draw_count == 1 && !strcmp(drawn_text, "01:00"));
    host_ticks = NONE; performance_options_render(); assert(draw_count == 1);
    host_ticks = 3600; cinematic = 1; performance_options_render(); assert(draw_count == 1);
    cinematic = 0; postgame = 1; performance_options_render(); assert(draw_count == 1);
    postgame = 0; performance_options_apply_host_flags(0); performance_options_render(); assert(draw_count == 1);
    initialized = 0; assert(performance_options_timer_ticks() == NONE);
    initialized = 1;
    test_spawn_fallback();
    test_timer_schedule();
    test_timer_audio_lifecycle();
    test_timer_preferences_and_queue();
    puts("Marker ownership, stock spawns, RNG, reload, tag safety, host timer and timer audio passed");
}
'''


EXTENDED_CHECKS = r'''
static void test_spawn_fallback(void) {
    int before_creates=creates, before_deletes=deletes, before_draw=draw_count;
    unsigned long seed=rng;
    performance_options_dispose_from_old_map();
    scenario.object_names.count=0;
    scenario.players=(struct tag_block){7,starts};
    for(int i=0;i<7;i++) {
        starts[i].position=(real_point3d){10+30*i,20+30*i,30+30*i};
        starts[i].structure_bsp_reference_index=0;
    }
    starts[0].game_types[0]=game_engine_slayer;
    starts[0].structure_bsp_reference_index=NONE;
    starts[1].game_types[0]=_game_engine_all; starts[1].facing=1.57079632679f;
    starts[2].game_types[0]=game_engine_slayer; starts[2].structure_bsp_reference_index=1;
    starts[3].game_types[0]=game_engine_ctf;
    starts[4].game_types[0]=_game_engine_all_normal;
    starts[5].game_types[0]=_game_engine_all_non_team;
    starts[5].structure_bsp_reference_index=NONE;
    /* The zero-filled last start is not a multiplayer spawn. The production
     * match_game_type function handles literal and wildcard game types. */
    variant.flags=0; game_engine->type=game_engine_slayer; active_bsp=0;
    performance_options_initialize_for_new_map();
    assert(performance_options_markers_supported_count()==5);
    assert(performance_options_markers_visible_count()==0);
    line_count=0; performance_options_render(); assert(line_count==0);
    performance_options_apply_host_flags(2); performance_options_update();
    assert(performance_options_markers_visible_count()==4);
    performance_options_render(); assert(line_count==40 && draw_count==before_draw);
    /* Geometry follows the scenario position and facing; it is independent
     * of timer HUD, and only current-BSP starts are submitted to rendering. */
    assert(fabsf(line_from[0].x-10)<.0001f && fabsf(line_from[0].z-30.08f)<.0001f);
    assert(fabsf(line_to[8].z-30.78f)<.0001f);
    assert(fabsf(line_to[9].x-10.35f)<.0001f && fabsf(line_to[9].y-20)<.0001f);
    assert(fabsf(line_to[19].x-40)<.0001f && fabsf(line_to[19].y-50.35f)<.0001f);
    active_bsp=1; line_count=0;
    assert(performance_options_markers_visible_count()==3);
    performance_options_render(); assert(line_count==30);
    menu_active=1; performance_options_render(); assert(line_count==30); menu_active=0;
    cinematic=1; performance_options_render(); assert(line_count==30); cinematic=0;
    postgame=1; performance_options_render(); assert(line_count==30); postgame=0;
    in_game=0; performance_options_render(); assert(line_count==30); in_game=1;
    performance_options_apply_host_flags(0); performance_options_update();
    performance_options_render(); assert(line_count==30 && performance_options_markers_visible_count()==0);
    assert(creates==before_creates && deletes==before_deletes && rng==seed);
    /* Reviewed map marker objects take precedence over fallback glyphs. */
    scenario.object_names.count=5; variant.flags=2;
    performance_options_initialize_for_new_map();
    assert(performance_options_markers_supported_count()==2);
    line_count=0; performance_options_render(); assert(line_count==0);
    /* A new variant re-evaluates the actual map spawn game-type filters. */
    scenario.object_names.count=0; game_engine->type=game_engine_ctf; active_bsp=0;
    performance_options_initialize_for_new_map();
    assert(performance_options_markers_supported_count()==2);
    assert(performance_options_markers_visible_count()==2);
    line_count=0; performance_options_render(); assert(line_count==20);
    /* Bound the local registry even when a map has more spawn records. */
    memset(starts,0,sizeof(starts));
    for(unsigned i=0;i<NUMBEROF(starts);i++) {
        starts[i].game_types[0]=_game_engine_all;
        starts[i].structure_bsp_reference_index=NONE;
    }
    scenario.players.count=NUMBEROF(starts);
    performance_options_initialize_for_new_map();
    assert(performance_options_markers_supported_count()==512);
    line_count=0; performance_options_render(); assert(line_count==5120);
    performance_options_dispose_from_old_map();
    assert(performance_options_markers_supported_count()==0);
    assert(creates==before_creates && deletes==before_deletes && rng==seed);
    scenario.players.count=0; variant.flags=0;
    performance_options_initialize_for_new_map();
}

static void test_timer_schedule(void) {
    /* Golden timestamps from the NHE common timer: all cues in two minutes,
     * including the half-second offsets for spoken warnings and minutes. */
    static const struct {long tick; const char *cue;} expected[]={
        {600,"timerbeep"},{900,"timerbeep"},{915,"30_seconds_left"},
        {1200,"timerbeep"},{1215,"20_seconds"},
        {1500,"10"},{1530,"9"},{1560,"8"},{1590,"7"},{1620,"6"},
        {1650,"5"},{1680,"4"},{1710,"3"},{1740,"2"},{1770,"1"},
        {1800,"timerbeep"},{1815,"1_minute"},
        {2400,"timerbeep"},{2700,"timerbeep"},{2715,"30_seconds_left"},
        {3000,"timerbeep"},{3015,"20_seconds"},
        {3300,"10"},{3330,"9"},{3360,"8"},{3390,"7"},{3420,"6"},
        {3450,"5"},{3480,"4"},{3510,"3"},{3540,"2"},{3570,"1"},
        {3600,"timerbeep"},{3615,"2_minutes"}
    };
    unsigned next=0;
    for(long tick=0;tick<=3615;tick++) {
        const char *cue=performance_timer_cue(tick-1,tick);
        if(next<NUMBEROF(expected) && expected[next].tick==tick) {
            assert(cue && !strcmp(cue,expected[next].cue)); next++;
        } else assert(!cue);
    }
    assert(next==NUMBEROF(expected));
    assert(!performance_timer_cue(-1,1800)); /* joining or enabling: no backfill */
    assert(!performance_timer_cue(1800,1800)); /* repeated host snapshot */
    assert(!performance_timer_cue(1815,1800)); /* rewind */
    assert(!performance_timer_cue(1799,1830)); /* over one-second gap */
    assert(!performance_timer_cue(1799,NONE));
    assert(!strcmp(performance_timer_cue(590,620),"timerbeep"));
    assert(!strcmp(performance_timer_cue(890,920),"30_seconds_left"));
    assert(!strcmp(performance_timer_cue(1790,1820),"1_minute"));
    assert(!strcmp(performance_timer_cue(54014,54015),"30_minutes"));
    assert(!strcmp(performance_timer_cue(55814,55815),"1_minute"));
}

static void test_timer_audio_lifecycle(void) {
    int before_draw=draw_count, before_stop=audio_stops;
    performance_options_dispose_from_old_map();
    assert(audio_stops==before_stop+1);
    variant.flags=0; performance_options_initialize_for_new_map();
    client=1; local_ticks=99000; host_ticks=599;
    audio_plays=0; performance_options_apply_host_flags(4);
    performance_options_update(); assert(audio_plays==0); /* establish host clock */
    host_ticks=600; performance_options_update();
    assert(audio_plays==1 && !strcmp(audio_cue,"timerbeep"));
    performance_options_render(); assert(draw_count==before_draw); /* audio without HUD */
    performance_options_update(); assert(audio_plays==1); /* no repeat */
    host_ticks=599; performance_options_update(); assert(audio_plays==1); /* rewind baseline */
    host_ticks=900; performance_options_update(); assert(audio_plays==1); /* no lag backfill */
    host_ticks=915; performance_options_update();
    assert(audio_plays==2 && !strcmp(audio_cue,"30_seconds_left"));
    host_ticks=1200; performance_options_update(); assert(audio_plays==2);
    /* Changing only HUD visibility does not reset the audio clock. */
    performance_options_apply_host_flags(5); host_ticks=1215; performance_options_update();
    assert(audio_plays==3 && !strcmp(audio_cue,"20_seconds"));
    performance_options_render(); assert(draw_count==before_draw+1);
    performance_options_apply_host_flags(4); host_ticks=1499; performance_options_update();
    assert(audio_plays==3);
    host_ticks=1500; performance_options_update(); assert(audio_plays==4 && !strcmp(audio_cue,"10"));
    before_stop=audio_stops; performance_options_apply_host_flags(0);
    assert(audio_stops==before_stop+1);
    host_ticks=1530; performance_options_apply_host_flags(4); performance_options_update();
    assert(audio_plays==4); /* enabling on a due cue skips it */
    host_ticks=1560; performance_options_update(); assert(audio_plays==5 && !strcmp(audio_cue,"8"));
    before_stop=audio_stops; cinematic=1; performance_options_update();
    assert(audio_stops==before_stop+1); cinematic=0;
    host_ticks=1590; performance_options_update(); assert(audio_plays==5);
    host_ticks=1620; performance_options_update(); assert(audio_plays==6 && !strcmp(audio_cue,"6"));
    before_stop=audio_stops; postgame=1; performance_options_update();
    assert(audio_stops==before_stop+1); postgame=0;
    host_ticks=1650; performance_options_update(); assert(audio_plays==6);
    host_ticks=NONE; performance_options_update(); assert(audio_plays==6);
    host_ticks=1680; performance_options_update(); assert(audio_plays==6);
    host_ticks=1710; performance_options_update(); assert(audio_plays==7 && !strcmp(audio_cue,"3"));
    before_stop=audio_stops; performance_options_dispose_from_old_map();
    assert(audio_stops==before_stop+1 && performance_options_get_flags()==0);
    variant.flags=4; performance_options_initialize_for_new_map();
    host_ticks=1740; performance_options_update(); assert(audio_plays==7);
    /* A locally hosted match uses its simulation clock for the same cues. */
    client=0; local_ticks=1769; performance_options_update();
    local_ticks=1770; performance_options_update(); assert(audio_plays==8 && !strcmp(audio_cue,"1"));
    performance_options_apply_host_flags(0);
}

static void timer_test_begin(unsigned preferences,long baseline,unsigned due,long due_tick) {
    performance_options_dispose_from_old_map();
    timer_preferences=preferences; item_due_mask=due; item_due_tick=due_tick;
    item_duration=20; audio_plays=0; client=1; host_ticks=baseline;
    variant.flags=4; performance_options_initialize_for_new_map();
    performance_options_update(); assert(!audio_plays);
}
static void timer_test_through(long last) {
    while(host_ticks<last) { host_ticks++; performance_options_update(); }
}
static void test_timer_preferences_and_queue(void) {
    /* Each common group is independently selectable; disabling an unrelated
     * group must not suppress a cue that shares the same one-second window. */
    for(unsigned mask=0;mask<8;mask++) {
        assert((performance_timer_cue_masked(1499,1500,mask)!=NULL)==!!(mask&1));
        assert((performance_timer_cue_masked(599,600,mask)!=NULL)==!!(mask&2));
        assert((performance_timer_cue_masked(1814,1815,mask)!=NULL)==!!(mask&4));
        const char *cue=performance_timer_cue_masked(890,920,mask);
        if(mask&1) assert(cue && !strcmp(cue,"30_seconds_left"));
        else if(mask&2) assert(cue && !strcmp(cue,"timerbeep"));
        else assert(!cue);
        timer_test_begin(mask,0,7,1800);
        timer_test_through(1820);
        int countdown=0,beeps=0,minutes=0;
        for(int i=0;i<audio_plays;i++) {
            if(!strcmp(audio_history[i].cue,"timerbeep")) beeps++;
            else if(!strcmp(audio_history[i].cue,"1_minute")) minutes++;
            else countdown++;
        }
        assert(countdown==((mask&1) ? 12:0));
        assert(beeps==((mask&2) ? 4:0));
        assert(minutes==((mask&4) ? 1:0));
    }
    /* Preferences alone cannot authorize timer sound playback. */
    timer_test_begin(15,1799,7,1800); performance_options_apply_host_flags(0);
    timer_test_through(1830); assert(!audio_plays);
    performance_options_apply_host_flags(4); performance_options_update();
    assert(!audio_plays); /* no backlog on re-enable */

    /* Simultaneous item categories queue once. The 1800 beep and 1815 minute
     * announcement take their original slots; names wait for exact durations. */
    timer_test_begin(15,1799,7,1800); timer_test_through(1800);
    assert(audio_plays==1 && !strcmp(audio_cue,"timerbeep"));
    for(int i=0;i<5;i++) performance_options_update();
    timer_test_through(1814); assert(audio_plays==1);
    timer_test_through(1815); assert(audio_plays==2 && !strcmp(audio_cue,"1_minute"));
    timer_test_through(1830); assert(audio_plays==2);
    timer_test_through(1831); assert(audio_plays==3 && !strcmp(audio_cue,"rocket"));
    timer_test_through(1851); assert(audio_plays==4 && !strcmp(audio_cue,"camo"));
    timer_test_through(1871); assert(audio_plays==5 && !strcmp(audio_cue,"overshield"));
    timer_test_through(2000); assert(audio_plays==5);
    for(int i=1;i<audio_plays;i++) {
        assert(audio_history[i].tick>=audio_history[i-1].tick+
            halo_performance_audio_duration_ticks(audio_history[i-1].cue));
    }
    /* With all common groups off, names can use the due tick immediately. */
    timer_test_begin(8,1799,7,1800); timer_test_through(1840);
    assert(audio_plays==3 && audio_history[0].tick==1800 && audio_history[1].tick==1820 && audio_history[2].tick==1840);

    /* A valid short host-time jump can outrun wall-clock playback. The
     * elapsed simulation duration alone cannot release the next item. */
    timer_test_begin(15,1799,7,1800); timer_test_through(1815);
    assert(audio_plays==2 && !strcmp(audio_cue,"1_minute"));
    audio_mixer_busy=1; host_ticks+=20; performance_options_update();
    assert(host_ticks==1835 && host_ticks>=performance_audio_busy_until);
    assert(audio_plays==2 && performance_item_pending[0]==1800);
    performance_options_update(); assert(audio_plays==2); /* Same host snapshot, clip still playing. */
    audio_mixer_busy=0; host_ticks++; performance_options_update();
    assert(audio_plays==3 && !strcmp(audio_cue,"rocket") && audio_history[2].tick==1836);
    audio_mixer_busy=1; host_ticks+=20; performance_options_update();
    assert(host_ticks==performance_audio_busy_until && audio_plays==3);
    assert(performance_item_pending[1]==1800);
    audio_mixer_busy=0; performance_options_update();
    assert(audio_plays==4 && !strcmp(audio_cue,"camo") && audio_history[3].tick==1856);

    /* Never play a stale reminder, a missing clip, or a clip that would run
     * across the next enabled countdown. */
    timer_test_begin(15,1499,1,1500); item_duration=2000;
    timer_test_through(1681);
    assert(performance_item_pending[0]==NONE);
    for(int i=0;i<audio_plays;i++) assert(strcmp(audio_history[i].cue,"rocket"));
    timer_test_begin(8,1799,7,1800); item_duration=0; timer_test_through(2000);
    assert(!audio_plays);
    for(int i=0;i<3;i++) assert(performance_item_pending[i]==NONE);

    /* A preference change, a rewind, and a long synchronization gap discard
     * pending names and establish a fresh clock without replaying old cues. */
    for(int reset=0;reset<3;reset++) {
        timer_test_begin(15,1799,7,1800); timer_test_through(1800);
        assert(performance_item_pending[0]==1800);
        int stopped=audio_stops;
        if(reset==0) { timer_preferences=7; host_ticks=1801; }
        else if(reset==1) host_ticks=1798;
        else host_ticks=1900;
        performance_options_update(); assert(audio_stops==stopped+1);
        for(int i=0;i<3;i++) assert(performance_item_pending[i]==NONE);
        assert(audio_plays==1);
    }
    /* Enabling countdown at a due timestamp does not announce its past cue. */
    timer_test_begin(0,1499,0,NONE); timer_preferences=1; host_ticks=1500;
    performance_options_update(); assert(!audio_plays);
    timer_test_through(1530); assert(audio_plays==1 && !strcmp(audio_cue,"9"));
    performance_options_dispose_from_old_map();
    assert(item_initializations>0);
}
'''


class PerformanceRuntime(unittest.TestCase):
    def test_runtime_lifecycle_and_host_clock(self):
        source = (ROOT / "port/linux/game/performance_options.c").read_text()
        source = re.sub(r'^#include[^\n]*\n', '', source, flags=re.M)
        engine = (ROOT / "source/game/game_engine.c").read_text()
        engine_header = (ROOT / "source/game/game_engine.h").read_text()
        scenarios = (ROOT / "source/scenario/scenario_definitions.h").read_text()
        variants = (ROOT / "source/game/performance_variant.h").read_text()
        options = (ROOT / "port/linux/game/performance_options.h").read_text()
        declarations = "\n".join((
            block(engine_header, "enum game_engine_type\n") + ";",
            block(engine[engine.rfind("enum\n", 0, engine.index("_game_engine_all =")):], "enum\n") + ";",
            block(variants, "enum\n") + ";",
            block(scenarios, "struct player_starting_location\n") + ";",
            block(options, "struct performance_timer_statistics\n") + ";",
        ))
        fixture = FIXTURE.replace("/* PRODUCTION DECLARATIONS */", declarations)
        fixture = fixture.replace("/* PRODUCTION GAME TYPE MATCH */", block(engine, "boolean match_game_type(\n"))
        fixture = fixture.replace("/* PRODUCTION */", source).replace("/* EXTENDED CHECKS */", EXTENDED_CHECKS)
        with tempfile.TemporaryDirectory() as directory:
            probe = Path(directory) / "runtime.c"
            binary = Path(directory) / "runtime"
            probe.write_text(fixture)
            compiled = subprocess.run(["clang", "-std=c11", "-O2", "-Wall", "-Werror",
                                       "-I", str(ROOT / "port/linux/game"),
                                       "-iquote", str(ROOT / "port/linux/include"),
                                       str(probe), "-o", str(binary)], text=True, capture_output=True)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            ran = subprocess.run([str(binary)], text=True, capture_output=True)
            self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)


if __name__ == "__main__":
    unittest.main()
