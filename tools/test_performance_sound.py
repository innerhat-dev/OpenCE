"""Exercise per-event provenance and the production channel-to-PCM gain path."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.test_performance_variants import block

ROOT = Path(__file__).resolve().parents[1]
GAME = ROOT / "port/linux/game"


def compile_run(source, arguments=()):
    with tempfile.TemporaryDirectory(prefix="halo-event-audio-") as temporary:
        directory = Path(temporary)
        (directory / "test.c").write_text(source)
        subprocess.run(["clang", "-std=c11", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
                        "-Wno-unused-function", "-Wno-unused-variable", "-fsanitize=address,undefined",
                        "-I", str(GAME), "-iquote", str(ROOT / "port/linux/include"),
                        str(directory / "test.c"), str(GAME / "performance_sound.c"),
                        "-o", str(directory / "test")], check=True)
        return subprocess.run([str(directory / "test"), *map(str, arguments)], check=True,
                              capture_output=True, text=True).stdout


PREFIX = r'''
#include <assert.h>
#include <float.h>
#include <math.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "performance_sound.h"
typedef float real;
typedef int boolean, BOOL, HRESULT;
typedef long LONG;
typedef unsigned long DWORD, ULONG;
typedef unsigned char byte;
typedef unsigned short word;
typedef void *LPVOID;
typedef void (*LPFNXMEDIAOBJECTCALLBACK)(void);
typedef struct { int placeholder; } IDirectSoundStream;
typedef struct sdl_stream *LPDIRECTSOUNDSTREAM;
typedef struct { int placeholder; } XMEDIAPACKET;
typedef struct { real x,y,z; } real_point3d;
typedef struct { real i,j,k; } real_vector3d;
#define HALO_PORT_MAXIMUM_NETWORK_PLAYERS 16
#define TRUE 1
#define FALSE 0
#define NONE (-1)
#define OUTPUT_RATE 48000
#define OUTPUT_CHANNELS 2
#define MAXIMUM_STREAM_PACKETS 64
#define DS3DMODE_DISABLE 2
#define DSBVOLUME_MIN (-10000)
#define DS3D_DEFERRED 1
#define DS3D_IMMEDIATE 0
#define FLAG(n) (1u << (n))
#define TEST_FLAG(f,n) (((unsigned)(f) & FLAG(n)) != 0)
#define SET_FLAG(f,n,v) ((f) = (v) ? ((f) | FLAG(n)) : ((f) & ~FLAG(n)))
#define MAX(a,b) ((a)>(b)?(a):(b))
#define MIN(a,b) ((a)<(b)?(a):(b))
#define PIN(v,a,b) MIN(MAX(v,a),b)
#define match_assert(file,line,condition) assert(condition)
#define match_vassert(file,line,condition,message) assert(condition)
#define TAG_BLOCK_GET_ELEMENT(b,i,t) (&((t *)(b)->address)[i])
struct tag_block { int count; void *address; };
enum { _sound_channel_3d_bit=0, _sound_channel_44k_bit=1 };
'''


def function(source, signature):
    return block(source[source.rindex(signature):], signature)


def channel_fixture():
    manager = (ROOT / "source/sound/sound_manager.c").read_text()
    dsound = (ROOT / "source/sound/sound_dsound_xbox.c").read_text()
    mixer = (ROOT / "port/linux/src/dsound_sdl.c").read_text()
    variant = (ROOT / "source/game/performance_variant.h").read_text()
    declarations = "\n".join(block(text, signature) + ";" for text, signature in (
        (variant, "enum\n{"),
        (manager, "struct platform_sound_channel_properties\n{"),
        (mixer, "struct voice_packet\n{"),
        (mixer, "struct sdl_stream\n{"),
        (dsound, "struct sound_channel\n{")))
    source = PREFIX + declarations + r'''
struct sound_permutation { real gain; };
struct sound_pitch_range { real playback_rate; struct tag_block permutations; };
struct sound_definition { short sound_class; real zero_gain_modifier,one_gain_modifier,gain_modifier;
 real inner_cone_angle,outer_cone_angle,outer_cone_gain; struct tag_block pitch_ranges; };
struct sound_datum { long definition_index; struct { real scale,gain; } source; real pitch;
 short playing_channel_index,pitch_range_index,permutation_index; };
struct sound_channel_datum { long sound_index; struct sound_permutation *playing_permutation; };
static struct sound_permutation permutation={0.8f};
static struct sound_pitch_range pitch_range={1.0f,{1,&permutation}};
static struct sound_definition definition={0,0.75f,1.25f,0.9f,0,0,1,{1,&pitch_range}};
static struct sound_datum voice={77,{0.5f,0.5f},1.0f,NONE,0,0};
static struct sound_channel_datum engine_channel={0x10001,&permutation};
static struct sound_channel dsound_channel;
static struct sdl_stream stream;
static struct sdl_stream *streams=&stream;
static pthread_mutex_t mixer_lock=PTHREAD_MUTEX_INITIALIZER;
static unsigned long selected_flags;
static unsigned queued,updated,volumes;
static float master_volume=1.0f,category_gain=0.75f;
static unsigned input_channels=1,input_rate=22050;
static struct { int initialized; float pause_gain; } dsound_globals={1,1};
static void update(short channel) { assert(channel==0); ++updated; }
static struct { void (*channel_update)(short); } platform_definition={update};
static struct { void *unused; __typeof__(platform_definition) *platform_definition; } sound_manager_globals={0,&platform_definition};
static struct sound_datum *sound_get(long index) { assert(index==engine_channel.sound_index); return &voice; }
static struct sound_definition *sound_definition_get(long index) { assert(index==77); return &definition; }
static unsigned long performance_options_get_flags(void) { return selected_flags; }
static real sound_manager_master_gain(short sound_class) { (void)sound_class; return category_gain; }
static real sound_definition_get_minimum_distance(long index) { assert(index==77); return 3.0f; }
static struct { real wet_gain; } sound_class={0.5f};
static __typeof__(sound_class) *sound_class_get(short index) { (void)index; return &sound_class; }
static boolean realcmp_epsilon(real a,real b,real epsilon) { return fabsf(a-b)<=epsilon; }
static void dsound_error(HRESULT result,const char *text) { (void)result; (void)text; assert(0); }
static unsigned long sound_samples_per_second(int rate) { return rate?44100:22050; }
static long dsound_frequency_from_pitch(unsigned long rate,float pitch) { return (long)(rate*pitch); }
static long dsound_angle_from_angle(float angle) { return (long)angle; }
static void dsound_channel_set_I3DL2_properties(short index) { (void)index; }
static HRESULT IDirectSoundStream_SetFrequency(LPDIRECTSOUNDSTREAM s,long frequency) { s->frequency=frequency; return 0; }
#define IDirectSoundStream_SetMaxDistance(...) 0
#define IDirectSoundStream_SetMinDistance(...) 0
#define IDirectSoundStream_SetConeAngles(...) 0
#define IDirectSoundStream_SetConeOutsideVolume(...) 0
static void spatialize(const struct sdl_stream *s,float *left,float *right) { (void)s; *left=*right=1.0f; }
'''
    source += function(mixer, "static float gain_from_millibels(") + "\n"
    source += r'''
static HRESULT IDirectSoundStream_SetVolume(LPDIRECTSOUNDSTREAM s,long volume) {
 ++volumes; s->volume=gain_from_millibels(volume); return 0;
}
#define channel_get(index) (&dsound_channel)
'''
    source += function(dsound, "static long dsound_volume_from_gain(\n\treal gain,") + "\n"
    source += function(dsound, "static void dsound_channel_set_properties(\n\tshort channel_index,") + "\n"
    source += r'''
#undef channel_get
#define channel_get(index) (&engine_channel)
static void channel_set_properties_hardware(short index,const struct platform_sound_channel_properties *p,boolean only) {
 dsound_channel_set_properties(index,p,only);
}
static int sound_cache_sound_loaded(struct sound_permutation *p) { assert(p==&permutation); return 1; }
static void channel_queue_sound(short index,struct sound_permutation *p) { assert(index==0 && p==&permutation); ++queued; }
'''
    source += function(manager, "static real sound_scale_value(\n\treal base,") + "\n"
    source += function(manager, "static void update_channel_for_impulse_sound(\n\tshort channel_index,") + "\n"
    for signature in ("static void voice_gains(", "static float packet_sample(", "static void mix_voice(",
                      "static void mix("):
        source += function(mixer, signature) + "\n"
    source += r'''
static void prepare_stream(short *samples,unsigned long frames) {
 memset(&stream,0,sizeof(stream)); stream.channels=input_channels; stream.sample_rate=input_rate;
 stream.mix_left=stream.mix_right=1; stream.packet_count=1;
 stream.packets[0].samples=samples; stream.packets[0].frames=frames;
 memset(&dsound_channel,0,sizeof(dsound_channel)); dsound_channel.stream=&stream; dsound_channel.gain=-1;
 dsound_channel.type_flags=input_rate==44100?FLAG(_sound_channel_44k_bit):0;
 voice.playing_channel_index=NONE;
}
int main(int argc,char **argv) {
 short samples[131072]; for(unsigned i=0;i<8192;i++) samples[i]=(short)(sin((double)i/17)*12000);
 unsigned frames=8192;
 float normal[2048]={0},silent[2048]={0},control[2048]={0};
 for(unsigned role=0;role<3;role++) {
  performance_sound_record(_performance_sound_voice,engine_channel.sound_index,role);
  for(unsigned flags=0;flags<=24;flags+=8) {
   prepare_stream(samples,frames); selected_flags=flags; unsigned before=queued;
   update_channel_for_impulse_sound(0,0.8f); assert(queued==before+1);
   unsigned muted=(role==1 && (flags&8)) || (role==2 && (flags&16));
   assert((stream.volume==0)==!!muted);
   float output[2048]={0}; mix_voice(&stream,output,1024);
   float peak=0;for(unsigned i=0;i<2048;i++) peak=MAX(peak,fabsf(output[i]));
   assert(muted ? peak==0 : peak>0);
   assert(fabs(stream.cursor-1024.0*22050/OUTPUT_RATE)<0.001 && updated>0);
   if(role==1 && flags==0) memcpy(normal,output,sizeof(normal));
   if(role==1 && flags==8) memcpy(silent,output,sizeof(silent));
   if(role==0 && flags==24) memcpy(control,output,sizeof(control));
  }
 }
 assert(!memcmp(normal,control,sizeof(normal))); /* Same shared tag used by ordinary audio. */
 /* Live toggles preserve cursor and the channel: one existing click-free ramp,
    then exact zero, then the original gain is restored without requeueing. */
 performance_sound_record(_performance_sound_voice,engine_channel.sound_index,1);
 selected_flags=0; prepare_stream(samples,frames); update_channel_for_impulse_sound(0,0.8f);
 float output[2048]={0};mix_voice(&stream,output,1024); unsigned before=queued;
 selected_flags=8; update_channel_for_impulse_sound(0,0.8f); assert(queued==before);
 memset(output,0,sizeof(output));mix_voice(&stream,output,1024);
 memset(output,0,sizeof(output));mix_voice(&stream,output,1024);
 for(unsigned i=0;i<2048;i++) assert(output[i]==0);
 assert(fabs(stream.cursor-3072.0*22050/OUTPUT_RATE)<0.001); selected_flags=0;update_channel_for_impulse_sound(0,0.8f);assert(stream.volume>0);
 /* Quiet voices below the old epsilon still cross exact mute boundaries. */
 struct platform_sound_channel_properties properties={0};
 dsound_channel.gain=0.0005f; stream.volume=0.0005f; before=volumes;
 dsound_channel_set_properties(0,&properties,TRUE); assert(volumes==before+1 && stream.volume==0);
 properties.gain=0.0005f; dsound_channel_set_properties(0,&properties,TRUE);assert(stream.volume>0);
 if(argc>2) {
  unsigned export_role=argc>3?(unsigned)atoi(argv[3]):1;
  input_channels=argc>4?(unsigned)atoi(argv[4]):1; input_rate=argc>5?(unsigned)atoi(argv[5]):22050;
  assert(input_channels>=1 && input_channels<=2 && (input_rate==22050 || input_rate==44100));
  FILE *input=fopen(argv[1],"rb"); assert(input);
  frames=(unsigned)fread(samples,sizeof(*samples),131072,input)/input_channels;assert(feof(input));
  fclose(input); assert(frames>0);
  if(argc>11) {
   permutation.gain=(real)atof(argv[6]);definition.gain_modifier=(real)atof(argv[7]);
   definition.zero_gain_modifier=(real)atof(argv[8]);definition.one_gain_modifier=(real)atof(argv[9]);
   definition.sound_class=(short)atoi(argv[10]);voice.source.scale=(real)atof(argv[11]);
  }
  category_gain=voice.source.gain=1.0f;
  char path[4096]; const char *names[]={"normal.f32","silent.f32","shared-control.f32","restored.f32"};
  unsigned output_frames=(unsigned)ceil((double)frames*OUTPUT_RATE/input_rate);
  float *output=calloc(output_frames*2,sizeof(float)); assert(output);
  for(unsigned i=0;i<4;i++) {
   memset(output,0,output_frames*2*sizeof(float));
   performance_sound_record(_performance_sound_voice,engine_channel.sound_index,i==2?0:export_role);
   selected_flags=i?24:0; prepare_stream(samples,frames);
   update_channel_for_impulse_sound(0,1.0f);
   if(i==3) { unsigned queues=queued;selected_flags=0;update_channel_for_impulse_sound(0,1.0f);assert(queued==queues); }
   mix(output,output_frames);
   snprintf(path,sizeof(path),"%s/%s",argv[2],names[i]);FILE *file=fopen(path,"wb");assert(file);
   assert(fwrite(output,sizeof(float),output_frames*2,file)==output_frames*2);fclose(file);
  }
  free(output);
 }
 puts("production event gains, DirectSound exact zero, PCM samples, unchanged shared audio and live ramps passed");
 return 0;
}
'''
    return source


def delayed_fixture():
    effects = (ROOT / "source/effects/effects.c").read_text()
    particles = (ROOT / "source/effects/particles.c").read_text()
    source = PREFIX + r'''
#define NUMBEROF(a) (sizeof(a)/sizeof((a)[0]))
#define profile_enter(...) ((void)0)
#define profile_exit(...) ((void)0)
#define error(...) ((void)0)
enum { _effect_in_duration_bit=0,_effect_loop_bit,_effect_stopping_bit,_effect_stopped_bit,
 _effect_invisible_bit,_effect_delete_on_stop_bit,_effect_nonviolent_bit };
enum { _effect_definition_must_be_deterministic_bit=0,_effect_definition_deleted_when_inactive_bit=1,
 _object_connected_to_map_bit=0,MAXIMUM_EFFECT_EVENTS_PER_UPDATE=8,MAXIMUM_SPLIT_SCREEN_PARTICLE_COUNT=6,
 _effect_particle_count_bit=5,MAXIMUM_PARTICLE_UNRENDERED_FRAME_COUNT=15,TICKS_PER_SECOND=30 };
typedef struct { real red,green,blue; } real_rgb_color;
struct location { int cluster_index; };
struct object_datum { long definition_index; struct { unsigned flags;struct location location;
 real_vector3d translational_velocity;long attachment_indices[2];real_rgb_color outgoing_change_colors[2]; } object; };
struct object_definition { struct { struct tag_block attachments; } object; };
struct effect_datum { struct { word flags; } header;long definition_index,owner_object_index,object_index;
 short local_player_index,scale_a_function_index,scale_b_function_index,change_color_index,event_index;
 struct location location; real_vector3d velocity;real_rgb_color color;real scale_a,scale_b;
 real event_time,event_duration,last_event_fraction;byte particle_counts[32]; };
struct effect_particles_definition { real count_lower_bound,count_upper_bound;unsigned scale_a_flags,scale_b_flags; };
struct effect_event_definition { real delay_lower_bound,delay_upper_bound,duration_lower_bound,duration_upper_bound,skip_fraction;
 struct tag_block particles; };
struct effect_definition { unsigned flags;short loop_start_index,loop_stop_index;struct tag_block events; };
static struct effect_event_definition event={0.25f,0.25f,0.5f,0.5f,0,{0,0}};
static struct effect_definition definition={0,NONE,NONE,{1,&event}};
static struct effect_datum effect_pool[4];
static unsigned effect_count,voice_count,particle_emits,random_calls;
static unsigned long random_seed;
static long effect_data=1,particle_data=2;
static long first_particle=0x10001,last_nested_effect=NONE;
static struct object_datum object;
static struct object_definition object_definition;
static struct effect_datum *effect_get(long index) { assert((index&65535)<4); return &effect_pool[index&65535]; }
static struct effect_datum *effect_try_and_get(long index) { return index==NONE?NULL:effect_get(index); }
static struct effect_definition *effect_definition_get(long index) { (void)index;return &definition; }
static int game_in_editor(void) { return 0; }
static long datum_new(long pool) { assert(pool==effect_data);assert(effect_count<4);return 0x10000+effect_count++; }
static long data_next_index(long pool,long previous) { return pool==particle_data && previous==NONE?first_particle:NONE; }
static void datum_delete(long pool,long index) { (void)pool;(void)index; }
static void effect_delete(long index) { performance_sound_forget(_performance_sound_effect,index); }
static struct object_datum *object_try_and_get(long index) { (void)index;return &object; }
static struct object_datum *object_get(long index) { (void)index;return &object; }
static long object_get_ultimate_parent(long index) { return index; }
static struct object_definition *object_definition_get(long index) { (void)index;return &object_definition; }
static int object_get_function_value(long i,short f,real *value) { (void)i;(void)f;*value=1;return 1; }
static void effect_stop(long index,boolean and_delete) { (void)index;(void)and_delete; }
#define match_assert_valid_real_rgb_color(...) ((void)0)
static boolean scenario_location_potentially_visible(const struct location *l) { return l->cluster_index!=NONE; }
static boolean scenario_location_potentially_visible_local(const struct location *l) { return l->cluster_index!=NONE; }
static unsigned long *effect_get_random_seed(long index) { (void)index;return &random_seed; }
static unsigned long *get_global_local_random_seed_address(void) { return &random_seed; }
static real real_seed_random(unsigned long *seed) { ++random_calls;return (real)++*seed; }
static real real_seed_random_range(unsigned long *seed,real low,real high) { (void)high; ++*seed;++random_calls;return low; }
static real effect_real_random_range(unsigned long *seed,struct effect_datum *e,real low,real high,unsigned a,unsigned b,unsigned k) {
 (void)e;(void)a;(void)b;(void)k;return real_seed_random_range(seed,low,high);
}
static int local_player_count(void) { return 1; }
static void effect_generate_parts(struct effect_datum *e) {
 (void)e;performance_sound_capture_voice(0x10000+voice_count++,77);
}
static void effect_generate_particles(struct effect_datum *e) {
 (void)e;++particle_emits;performance_sound_capture(_performance_sound_particle,first_particle);
}
'''
    for signature in ("static void effect_set_event(\n\tlong effect_index,",
                      "static long effect_allocate(\n\tlong definition_index,",
                      "static void effect_update(\n\tlong effect_index,"):
        source += function(effects, signature) + "\n"
    source += r'''
struct particle_datum { real age,lifespan;long definition_index,last_rendered_frame_index; };
struct particle_definition { short final_sequence_count; };
static struct particle_datum particle={0,10,77,0};
static struct particle_definition particle_definition;
static struct { long frame_index; } render;
static real particles_leftover_ticks;
static long particles_update_ticks,particles_tick_frame_head;
static long particles_tick_frame_indices[MAXIMUM_PARTICLE_UNRENDERED_FRAME_COUNT+1];
static struct particle_datum *particle_get(long index) { assert(index==first_particle);return &particle; }
static struct particle_definition *particle_definition_get(long index) { assert(index==77);return &particle_definition; }
static void particle_die(long index) { (void)index;performance_sound_capture_voice(0x10000+voice_count++,77); }
static boolean particle_update_frame_time(long index,real dt) { (void)index;(void)dt;return TRUE; }
static boolean particle_update_physics(long index,real dt) {
 (void)index;(void)dt;
 last_nested_effect=effect_allocate(77,NONE,FALSE);
 effect_get(last_nested_effect)->object_index=NONE;
 effect_get(last_nested_effect)->location.cluster_index=0;
 return TRUE;
}
'''
    source += function(particles, "void particles_update(\n\treal dt)") + "\n"
    source += r'''
int main(void) {
 for(unsigned role=0;role<3;role++) {
  memset(effect_pool,0,sizeof(effect_pool));effect_count=voice_count=particle_emits=random_calls=0;random_seed=0;
  for(unsigned owner=0;owner<3;owner++) performance_sound_reset(owner);
  unsigned previous=performance_sound_push(role);
  long index=effect_allocate(77,NONE,FALSE);
  effect_get(index)->object_index=NONE;effect_get(index)->location.cluster_index=0;
  effect_update(index,0); /* Same immediate update used by effect_new_* APIs. */
  performance_sound_pop(previous);
  assert(performance_sound_current()==0 && voice_count==0);
  assert(performance_sound_role(_performance_sound_effect,index)==role);
  effect_update(index,0.1f);assert(voice_count==0 && performance_sound_current()==0);
  effect_update(index,0.2f);assert(voice_count==1 && particle_emits==1 && performance_sound_current()==0);
  assert(performance_sound_role(_performance_sound_voice,0x10000)==role);
  assert(performance_sound_role(_performance_sound_particle,first_particle)==role);
  particles_update(1.0f/30);assert(performance_sound_current()==0 && last_nested_effect!=NONE);
  assert(performance_sound_role(_performance_sound_effect,last_nested_effect)==role);
  effect_update(last_nested_effect,0.3f);assert(voice_count==2);
  assert(performance_sound_role(_performance_sound_voice,0x10001)==role);
  performance_sound_capture_voice(0x10002,77);
  assert(performance_sound_gain(0x10002,3)==1); /* Same shared tag outside event chain. */
  assert(performance_sound_gain(0x10001,3)==(role?0:1));
  assert(performance_sound_current()==0 && random_calls==4 && random_seed==4);
 }
 return 0;
}
'''
    return source


class PerformanceSoundTests(unittest.TestCase):
    def test_salted_event_provenance_scope_reset_and_late_restoration(self):
        compile_run(PREFIX + r'''
int main(void) {
 performance_sound_reset(_performance_sound_voice);
 unsigned outer=performance_sound_push(_performance_sound_movement);
 performance_sound_capture(_performance_sound_effect,0x10001);
 unsigned inner=performance_sound_push(_performance_sound_weapon_ready);
 performance_sound_capture_voice(0x10001,77); performance_sound_pop(inner);
 performance_sound_capture(_performance_sound_particle,0x10001);
 performance_sound_pop(outer); assert(performance_sound_current()==0);
 /* A later effect/particle tick inherits its creation role, even after
    the originating scope ended; an identical sound tag stays per-event. */
 outer=performance_sound_push(performance_sound_role(_performance_sound_particle,0x10001));
 performance_sound_capture(_performance_sound_effect,0x10002); performance_sound_pop(outer);
 outer=performance_sound_push(performance_sound_role(_performance_sound_effect,0x10002));
 performance_sound_capture_voice(0x10002,77); performance_sound_pop(outer);
 performance_sound_capture_voice(0x10003,77);
 assert(performance_sound_gain(0x10001,1)==1 && performance_sound_gain(0x10001,2)==0);
 assert(performance_sound_gain(0x10002,1)==0 && performance_sound_gain(0x10002,2)==1);
 assert(performance_sound_gain(0x10003,3)==1);
 assert(performance_sound_gain(0x10002,0)==1); /* Live restoration. */
 assert(performance_sound_role(_performance_sound_effect,0x20001)==0);
 performance_sound_capture(_performance_sound_effect,0x20001);
 assert(performance_sound_role(_performance_sound_effect,0x10001)==0);
 performance_sound_record(_performance_sound_voice,0x20002,2);
 performance_sound_forget(_performance_sound_voice,0x10002);
 assert(performance_sound_gain(0x20002,2)==0); /* Stale deletion cannot erase reused slot. */
 for(unsigned owner=0;owner<3;owner++) {
  performance_sound_record(owner,-1,3); performance_sound_record(owner,0x1ffff,3);
  assert(performance_sound_role(owner,-1)==0 && performance_sound_role(owner,0x1ffff)==0);
  performance_sound_reset(owner); assert(performance_sound_role(owner,0x10001)==0);
 }
 assert(performance_sound_role(99,0x10001)==0);
 return 0;
}
''')

    def test_production_channel_dispatch_and_mixed_pcm(self):
        self.assertIn("passed", compile_run(channel_fixture()))

    def test_production_delayed_effect_and_particle_event_scopes(self):
        compile_run(delayed_fixture())


if __name__ == "__main__":
    unittest.main()
