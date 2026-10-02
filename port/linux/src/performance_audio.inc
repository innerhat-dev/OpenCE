/* Included by dsound_sdl.c after its stream implementation. Keeping these
 * optional recordings in the existing mixer preserves the user's audio toggle,
 * master volume, output device and guest/host audio-thread handoff. */
#include "performance_audio.h"
#include <stdio.h>

enum
{
	PERFORMANCE_AUDIO_REQUIRED_CLIPS = 43,
	PERFORMANCE_AUDIO_MAXIMUM_BYTES = 1024 * 1024,
};

static const char *const performance_audio_cues[] =
{
	"timerbeep",
	"1_minute", "2_minutes", "3_minutes", "4_minutes", "5_minutes",
	"6_minutes", "7_minutes", "8_minutes", "9_minutes", "10_minutes",
	"11_minutes", "12_minutes", "13_minutes", "14_minutes", "15_minutes",
	"16_minutes", "17_minutes", "18_minutes", "19_minutes", "20_minutes",
	"21_minutes", "22_minutes", "23_minutes", "24_minutes", "25_minutes",
	"26_minutes", "27_minutes", "28_minutes", "29_minutes", "30_minutes",
	"30_seconds_left", "20_seconds",
	"10", "9", "8", "7", "6", "5", "4", "3", "2", "1",
	/* Item calls are separate from the general minute/countdown schedule. */
	"rocket", "camo", "overshield",
};

struct performance_audio_clip
{
	unsigned char *samples;
	unsigned long bytes;
	unsigned long sample_rate;
	unsigned short channels;
};
static struct performance_audio_clip performance_audio_clips[
	sizeof(performance_audio_cues) / sizeof(performance_audio_cues[0])];
static BOOL performance_audio_loaded;
static BOOL performance_audio_complete;
static LPDIRECTSOUNDSTREAM performance_audio_stream;
static float performance_audio_requested_volume;

void halo_audio_apply_settings(void)
{
	/* Read config before taking the mixer lock: the audio callback never needs
	to acquire the config lock, and its next buffer uses these new gains. */
	float master = audio_setting_volume("audio.volume");
	float timer = audio_setting_volume("audio.timer_volume");

	pthread_mutex_lock(&mixer_lock);
	master_volume = master;
	if (performance_audio_stream)
		stream_from_interface(performance_audio_stream)->volume = performance_audio_requested_volume * timer;
	pthread_mutex_unlock(&mixer_lock);
}

static unsigned long performance_audio_u32(const unsigned char *value)
{
	return (unsigned long)value[0] | ((unsigned long)value[1] << 8) |
		((unsigned long)value[2] << 16) | ((unsigned long)value[3] << 24);
}

static unsigned short performance_audio_u16(const unsigned char *value)
{
	return (unsigned short)((unsigned short)value[0] | ((unsigned short)value[1] << 8));
}

/* The importer writes canonical 44-byte PCM WAV headers. Refuse other WAV
 * layouts rather than introducing runtime compressed-audio parsers. */
static int performance_audio_load_clip(unsigned long index)
{
	struct performance_audio_clip *clip = &performance_audio_clips[index];
	unsigned char header[44];
	unsigned long bytes, rate, channels, align;
	char path[4096];
	FILE *file;
	int path_length;
	const char *root = platform_data_root();
	if (!root || !root[0])
		return 0;
	path_length = snprintf(path, sizeof(path), "%s/sounds/performance/%s.wav", root, performance_audio_cues[index]);
	if (path_length < 0 || (unsigned long)path_length >= sizeof(path))
		return 0;
	file = fopen(path, "rb");
	if (!file)
		return 0;
	if (fread(header, 1, sizeof(header), file) != sizeof(header) ||
		memcmp(header, "RIFF", 4) || memcmp(header + 8, "WAVEfmt ", 8) ||
		performance_audio_u32(header + 16) != 16 ||
		performance_audio_u16(header + 20) != WAVE_FORMAT_PCM ||
		performance_audio_u16(header + 34) != 16 || memcmp(header + 36, "data", 4))
		goto invalid;
	channels = performance_audio_u16(header + 22);
	rate = performance_audio_u32(header + 24);
	align = performance_audio_u16(header + 32);
	bytes = performance_audio_u32(header + 40);
	if ((channels != 1 && channels != 2) || (rate != 22050 && rate != 44100) ||
		align != channels * 2 || performance_audio_u32(header + 28) != rate * align ||
		!bytes || bytes > PERFORMANCE_AUDIO_MAXIMUM_BYTES || bytes % align ||
		bytes > rate * align * 4 || performance_audio_u32(header + 4) != bytes + 36)
		goto invalid;
	clip->samples = malloc(bytes);
	if (!clip->samples)
		goto invalid;
	if (fread(clip->samples, 1, bytes, file) != bytes || fgetc(file) != EOF)
	{
		free(clip->samples);
		clip->samples = NULL;
		goto invalid;
	}
	fclose(file);
	clip->bytes = bytes;
	clip->sample_rate = rate;
	clip->channels = (unsigned short)channels;
	return 1;

invalid:
	fclose(file);
	return 0;
}

int halo_performance_audio_available(void)
{
	unsigned long index;
	if (!performance_audio_loaded)
	{
		performance_audio_loaded = TRUE;
		performance_audio_complete = TRUE;
		for (index = 0; index < sizeof(performance_audio_cues) / sizeof(performance_audio_cues[0]); index++)
		{
			if (!performance_audio_load_clip(index) && index < PERFORMANCE_AUDIO_REQUIRED_CLIPS)
				performance_audio_complete = FALSE;
		}
	}
	return performance_audio_complete != FALSE;
}

long halo_performance_audio_duration_ticks(const char *cue)
{
	unsigned long index;
	if (!cue || !halo_performance_audio_available()) return 0;
	for (index = 0; index < sizeof(performance_audio_cues) / sizeof(performance_audio_cues[0]); index++)
	{
		struct performance_audio_clip const *clip = &performance_audio_clips[index];
		if (!strcmp(cue, performance_audio_cues[index]) && clip->samples)
		{
			unsigned long bytes_per_second = clip->sample_rate * clip->channels * 2;
			return (long)((clip->bytes * 30 + bytes_per_second - 1) / bytes_per_second);
		}
	}
	return 0;
}

int halo_performance_audio_busy(void)
{
	int busy = 0;
	pthread_mutex_lock(&mixer_lock);
	if (performance_audio_stream)
	{
		struct sdl_stream *stream = stream_from_interface(performance_audio_stream);
		busy = stream->packet_count && !stream->packets[stream->packet_head].finished;
	}
	pthread_mutex_unlock(&mixer_lock);
	return busy;
}

void halo_performance_audio_stop(void)
{
	if (performance_audio_stream)
	{
		stream_release(performance_audio_stream);
		performance_audio_stream = NULL;
	}
}

int halo_performance_audio_play(const char *cue, float volume)
{
	unsigned long index;
	struct performance_audio_clip *clip;
	struct sdl_stream *stream;
	WAVEFORMATEX format;
	DSSTREAMDESC description;
	XMEDIAPACKET packet;
	float timer_volume;
	if (!cue || !(volume >= 0.0f && volume <= 1.0f) || volume == 0.0f ||
		!config_boolean("audio.enabled"))
		return 0;
	for (index = 0; index < sizeof(performance_audio_cues) / sizeof(performance_audio_cues[0]); index++)
		if (!strcmp(cue, performance_audio_cues[index]))
			break;
	if (index == sizeof(performance_audio_cues) / sizeof(performance_audio_cues[0]) ||
		!halo_performance_audio_available())
		return 0;
	clip = &performance_audio_clips[index];
	if (!clip->samples)
		return 0;
	halo_performance_audio_stop();
	memset(&format, 0, sizeof(format));
	format.wFormatTag = WAVE_FORMAT_PCM;
	format.nChannels = clip->channels;
	format.nSamplesPerSec = clip->sample_rate;
	format.wBitsPerSample = 16;
	format.nBlockAlign = clip->channels * 2;
	format.nAvgBytesPerSec = clip->sample_rate * format.nBlockAlign;
	memset(&description, 0, sizeof(description));
	description.lpwfxFormat = &format;
	description.dwMaxAttachedPackets = 1;
	audio_start();
	if (IDirectSound_CreateSoundStream(NULL, &description, &performance_audio_stream, NULL) != DS_OK)
		return 0;
	stream = stream_from_interface(performance_audio_stream);
	timer_volume = audio_setting_volume("audio.timer_volume");
	pthread_mutex_lock(&mixer_lock);
	performance_audio_requested_volume = volume;
	stream->volume = volume * timer_volume;
	pthread_mutex_unlock(&mixer_lock);
	memset(&packet, 0, sizeof(packet));
	packet.pvBuffer = clip->samples;
	packet.dwMaxSize = clip->bytes;
	if (stream_process(performance_audio_stream, &packet, NULL) != S_OK)
	{
		halo_performance_audio_stop();
		return 0;
	}
	return 1;
}
