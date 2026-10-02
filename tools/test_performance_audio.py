"""Validate owned-tag import, strict WAV loading, and the production mixer path."""
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

from tools import import_performance_audio as importer
from tools.test_performance_variants import block

ROOT = Path(__file__).resolve().parents[1]


def sound_tag(channels=2, samples=None):
    samples = samples if samples is not None else bytes(36 * channels)
    result = bytearray(424 + len(samples))
    result[36:40] = b"snd!"
    result[60:64] = b"blam"
    struct.pack_into(">I", result, 44, 64)
    struct.pack_into(">H", result, 56, 4)
    struct.pack_into(">H", result, 64 + 6, 1)
    struct.pack_into(">HH", result, 64 + 108, channels - 1, 1)
    struct.pack_into(">I", result, 64 + 152, 1)
    struct.pack_into(">H", result, 228 + 44, 1)
    struct.pack_into(">I", result, 228 + 60, 1)
    struct.pack_into(">HH", result, 300 + 40, 1, 65535)
    struct.pack_into(">I", result, 300 + 64, len(samples))
    result[424:] = samples
    return result


PREFIX = r'''
#include <assert.h>
#include <math.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef int BOOL;
#define TRUE 1
#define FALSE 0
#define WAVE_FORMAT_PCM 1
#define DS_OK 0
#define S_OK 0
#define DS3DMODE_DISABLE 2
typedef struct { int placeholder; } IDirectSoundStream;
typedef IDirectSoundStream *LPDIRECTSOUNDSTREAM;
typedef struct { unsigned short wFormatTag,nChannels; unsigned long nSamplesPerSec,nAvgBytesPerSec;
 unsigned short nBlockAlign,wBitsPerSample,cbSize; } WAVEFORMATEX;
typedef struct { WAVEFORMATEX *lpwfxFormat; unsigned dwMaxAttachedPackets; } DSSTREAMDESC;
typedef struct { void *pvBuffer; unsigned long dwMaxSize; } XMEDIAPACKET;
struct sdl_stream { IDirectSoundStream object; float volume,mix_left,mix_right; BOOL has_3d; unsigned mode; unsigned packet_count,packet_head; struct { BOOL finished; } packets[1]; };
static pthread_mutex_t mixer_lock=PTHREAD_MUTEX_INITIALIZER;
static int enabled=1,created,played,released,start_count;
static unsigned long played_bytes;
static float master_volume=0.4f, configured_master=0.4f, configured_timer=1.0f;
static const char *root;
static const char *platform_data_root(void) { return root; }
static int config_boolean(const char *key) { assert(!strcmp(key,"audio.enabled")); return enabled; }
static double config_real(const char *key) {
 if(!strcmp(key,"audio.volume")) return configured_master;
 assert(!strcmp(key,"audio.timer_volume")); return configured_timer;
}
static void audio_start(void) { ++start_count; }
static struct sdl_stream *stream_from_interface(void *stream) { return stream; }
static unsigned stream_release(IDirectSoundStream *stream) { ++released; free(stream); return 0; }
static int IDirectSound_CreateSoundStream(void *sound,const DSSTREAMDESC *description,LPDIRECTSOUNDSTREAM *result,void *outer) {
 (void)sound; (void)outer; assert(description->dwMaxAttachedPackets==1);
 assert(description->lpwfxFormat->wFormatTag==1 && description->lpwfxFormat->wBitsPerSample==16);
 struct sdl_stream *s=calloc(1,sizeof(*s)); assert(s); s->mix_left=s->mix_right=1.0f;
 *result=&s->object; ++created; return 0;
}
static int stream_process(IDirectSoundStream *stream,const XMEDIAPACKET *packet,void *output) {
 (void)stream; (void)output; assert(packet->pvBuffer && packet->dwMaxSize); ++played; played_bytes=packet->dwMaxSize; return 0;
}
static void spatialize(const struct sdl_stream *stream,float *left,float *right) { (void)stream; *left=*right=1.0f; }
/* PRODUCTION VOICE GAIN AND AUDIO PACK IMPLEMENTATION */
'''

HARNESS = r'''
int main(int argc,char **argv) {
 assert(argc==2); root=argv[1];
 assert(!halo_performance_audio_play("../unrelated",1.0f) && !performance_audio_loaded);
 assert(halo_performance_audio_available());
 assert(halo_performance_audio_duration_ticks("timerbeep")==1);
 assert(halo_performance_audio_duration_ticks("rocket")==0);
 assert(halo_performance_audio_duration_ticks(NULL)==0);
 assert(halo_performance_audio_duration_ticks("../unrelated")==0);
 assert(performance_audio_clips[0].sample_rate==22050 && performance_audio_clips[0].channels==1);
 assert(!halo_performance_audio_busy());
 assert(halo_performance_audio_play("timerbeep",0.5f) && played==1 && created==1 && played_bytes==128);
 struct sdl_stream *active=stream_from_interface(performance_audio_stream);
 active->packet_count=1; assert(halo_performance_audio_busy());
 active->packets[0].finished=1; assert(!halo_performance_audio_busy());
 active->packets[0].finished=0; active->packet_count=0; assert(!halo_performance_audio_busy());
 float left=0,right=0; voice_gains(stream_from_interface(performance_audio_stream),&left,&right);
 assert(fabsf(left-0.2f)<0.0001f && fabsf(right-0.2f)<0.0001f); /* Existing master volume. */
 configured_master=0.8f; configured_timer=0.25f; halo_audio_apply_settings();
 voice_gains(stream_from_interface(performance_audio_stream),&left,&right);
 assert(fabsf(left-0.1f)<0.0001f && fabsf(right-0.1f)<0.0001f);
 halo_audio_apply_settings(); /* Reapplying never compounds the previous gain. */
 voice_gains(stream_from_interface(performance_audio_stream),&left,&right); assert(fabsf(left-0.1f)<0.0001f);
 configured_master=0.0f; halo_audio_apply_settings();
 voice_gains(stream_from_interface(performance_audio_stream),&left,&right); assert(left==0 && right==0);
 configured_master=0.8f; configured_timer=0.0f; halo_audio_apply_settings();
 voice_gains(stream_from_interface(performance_audio_stream),&left,&right); assert(left==0 && right==0);
 configured_timer=1.0f; halo_audio_apply_settings();
 voice_gains(stream_from_interface(performance_audio_stream),&left,&right); assert(fabsf(left-0.4f)<0.0001f);
 assert(!halo_performance_audio_play("timerbeep",NAN) && played==1);
 assert(!halo_performance_audio_play("timerbeep",-1.0f));
 assert(!halo_performance_audio_play("timerbeep",1.1f));
 assert(!halo_performance_audio_play("timerbeep",0.0f));
 enabled=0; assert(!halo_performance_audio_play("1_minute",1.0f) && played==1); enabled=1;
 configured_timer=0.25f;
 assert(halo_performance_audio_play("1_minute",1.0f) && played==2 && released==1);
 voice_gains(stream_from_interface(performance_audio_stream),&left,&right); assert(fabsf(left-0.2f)<0.0001f);
 configured_timer=NAN; configured_master=2.0f; halo_audio_apply_settings();
 voice_gains(stream_from_interface(performance_audio_stream),&left,&right); assert(left==0 && master_volume==1.0f);
 configured_timer=2.0f; configured_master=-1.0f; halo_audio_apply_settings();
 assert(stream_from_interface(performance_audio_stream)->volume==1.0f && master_volume==0.0f);
 halo_performance_audio_stop(); assert(!performance_audio_stream && released==2);
 halo_performance_audio_stop(); assert(released==2);
 /* A malformed optional file must never enter the mixer. */
 assert(!performance_audio_clips[43].samples && !halo_performance_audio_play("rocket",1.0f));
 for(unsigned i=0;i<sizeof(performance_audio_clips)/sizeof(performance_audio_clips[0]);i++) free(performance_audio_clips[i].samples);
 return 0;
}
'''


class PerformanceAudioTest(unittest.TestCase):
    def test_tag_decoder_rejects_unknown_layouts_and_truncation(self):
        rate, channels, pcm = importer.decode_sound_tag(sound_tag())
        self.assertEqual((rate, channels, len(pcm)), (44100, 2, 256))
        for offset, value in ((36, b"bad!"), (56, b"\x00\x03"), (64 + 152, b"\x00\x00\x00\x02"), (300 + 40, b"\x00\x00")):
            damaged = sound_tag()
            damaged[offset:offset + len(value)] = value
            with self.assertRaises(ValueError):
                importer.decode_sound_tag(damaged)
        with self.assertRaises(ValueError):
            importer.decode_sound_tag(sound_tag()[:-1])
        with self.assertRaises(ValueError):
            importer.decode_xbox_adpcm(bytes([0, 0, 255, 0]) + bytes(32), 1)

    def test_import_preserves_existing_files_before_writing(self):
        with tempfile.TemporaryDirectory(prefix="halo-audio-import-") as temporary:
            directory = Path(temporary)
            (directory / "1.wav").write_bytes(b"existing")
            with self.assertRaises(ValueError):
                importer.write_pack({"2.wav": b"new", "1.wav": b"different"}, directory)
            self.assertFalse((directory / "2.wav").exists())
            self.assertEqual((directory / "1.wav").read_bytes(), b"existing")
            self.assertEqual(importer.write_pack({"2.wav": b"new", "1.wav": b"existing"}, directory), (1, 1))

    def test_decoder_matches_production_mixer(self):
        source = (ROOT / "port/linux/src/dsound_sdl.c").read_text()
        definitions = source[source.index("static const int ima_index_table"):source.index("static short *decode_pcm")]
        cases = []
        for channels in (1, 2):
            payload = bytearray()
            for block_index in range(3):
                for channel in range(channels):
                    payload.extend(struct.pack("<hBB", 2000 - channel * 6000, 20 + channel * 30, 0))
                payload.extend(bytes((index * 17 + block_index) & 255 for index in range(32 * channels)))
            expected = importer.decode_xbox_adpcm(payload, channels)
            cases.append("{ unsigned char input[]={%s}; unsigned char expected[]={%s}; unsigned long frames; short *result=decode_adpcm(input,sizeof(input),%d,&frames); assert(frames==192 && !memcmp(result,expected,sizeof(expected))); free(result); }" % (
                ",".join(map(str, payload)), ",".join(map(str, expected)), channels))
        fixture = "#include <assert.h>\n#include <stdlib.h>\n#include <string.h>\n#define XBOX_ADPCM_BLOCK_BYTES 36\n#define XBOX_ADPCM_BLOCK_SAMPLES 64\n" + definitions
        fixture += "int main(void){" + "".join(cases) + "return 0;}"
        self.compile_and_run(fixture)

    def test_strict_loader_and_existing_mixer_controls(self):
        source = (ROOT / "port/linux/src/dsound_sdl.c").read_text()
        gains = block(source, "static void voice_gains(")
        fixture = PREFIX + block(source, "static float audio_setting_volume(") + gains + (ROOT / "port/linux/src/performance_audio.inc").read_text() + HARNESS
        with tempfile.TemporaryDirectory(prefix="halo-audio-pack-") as temporary:
            root = Path(temporary)
            directory = root / "sounds/performance"
            directory.mkdir(parents=True)
            for cue in importer.CUES[:43]:
                (directory / f"{cue}.wav").write_bytes(importer.canonical_wav(22050, 1, bytes(128)))
            # This looks like a WAV but claims a payload beyond the bound.
            damaged = bytearray(importer.canonical_wav(22050, 1, bytes(128)))
            struct.pack_into("<I", damaged, 40, 0xFFFFFFFF)
            (directory / "rocket.wav").write_bytes(damaged)
            self.compile_and_run(fixture, str(root))

    def compile_and_run(self, fixture, *arguments):
        with tempfile.TemporaryDirectory(prefix="halo-audio-test-") as temporary:
            source = Path(temporary) / "test.c"
            binary = Path(temporary) / "test"
            source.write_text(fixture)
            subprocess.run(["clang", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pthread", "-iquote", str(ROOT / "port/linux/include"), str(source), "-o", str(binary)], check=True)
            subprocess.run([str(binary), *arguments], check=True)


if __name__ == "__main__":
    unittest.main()
