/*
PORT_CONFIG.C

The native ports' settings (port_config.h), parsed with tomlc17
(port/third_party/tomlc17). Every setting is in the table below with its
type, default, the HALO_* environment variable that overrides it and the
comment written into a new file. The file is read once, on the first
question; unknown keys and values of the wrong type are reported in the log
and the defaults used instead. Missing defaults and explicitly saved settings
preserve the player's other values, edits and comments.
*/

#include "platform.h"
#include "port_config.h"
#include "tomlc17.h"

#include <SDL3/SDL.h>
#include <ctype.h>
#include <limits.h>
#include <math.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifndef _WIN32
#include <sys/stat.h>
#include <unistd.h>
#endif

/* ---------- the settings */

enum config_type
{
	_config_boolean,
	_config_integer,
	_config_real,
	_config_string,
};

/* how the setting's environment variable sets it */
enum config_environment
{
	/* the variable's text is the value ("0", "false", "no" and "off" are
	false for a boolean) */
	_environment_value,
	/* the variable being set at all makes it true */
	_environment_set_is_true,
	/* the variable being set at all makes it false */
	_environment_set_is_false,
};

/* the builds a setting means something in, and is written for */
enum
{
	_platform_desktop = 1,
	_platform_android = 2,
	_platform_all = _platform_desktop | _platform_android,
};

struct config_setting
{
	const char *name;
	enum config_type type;
	/* as it is written in the file */
	const char *default_value;
	const char *environment;
	enum config_environment environment_style;
	unsigned platforms;
	const char *comment;
};

static const struct config_setting config_settings[] =
{
	{ "display.fullscreen", _config_boolean, "true", "HALO_FULLSCREEN", _environment_value, _platform_desktop,
		"Start fullscreen, drawing at the display's resolution and shape; false\n"
		"starts in a window, which draws the Xbox's 640x480. F11 switches." },
	{ "display.window_scale", _config_integer, "2", "HALO_WINDOW_SCALE", _environment_value, _platform_desktop,
		"The window's size as a multiple of 640x480 (it can be resized)." },
	{ "display.screen_width", _config_integer, "0", "HALO_SCREEN_WIDTH", _environment_value, _platform_android,
		"Columns of the 480-line picture: 0 for the display's shape, 640 for the\n"
		"Xbox's 4:3." },
	{ "display.vsync", _config_boolean, "true", "HALO_NO_VSYNC", _environment_set_is_false, _platform_all,
		"Wait for the display between frames; false draws as fast as possible." },
	/* Original Xbox presentation is the fork's baseline; enhancements are opt-in. */
	{ "display.max_fps", _config_integer, "0", "HALO_MAX_FPS", _environment_value, _platform_desktop,
		"With vsync off, the most frames a second: 0 for twice the display's\n"
		"refresh rate, -1 for no limit (which can hang some Intel graphics)." },
	{ "display.interpolation", _config_boolean, "false", "HALO_INTERPOLATION", _environment_value, _platform_all,
		"Draw a frame for every display refresh, blending between the game's 30\n"
		"ticks a second; false keeps the original 30 frames a second." },
	{ "display.timer_position", _config_integer, "0", NULL, _environment_value, _platform_all,
		"PB timer position: 0 is top center, 1 bottom center, 2 bottom right." },
	{ "display.timer_scale", _config_real, "1.0", NULL, _environment_value, _platform_all,
		"PB timer size, 0.5 to 1.0. These preferences do not enable the timer." },
	{ "display.direct_camera", _config_boolean, "false", "HALO_DIRECT_CAMERA", _environment_value, _platform_desktop,
		"In first person, point the view where the player aims now instead of\n"
		"where the last tick left it: the view turns the frame the mouse moves,\n"
		"not up to two ticks (66 ms) later." },
	{ "display.high_res_hud", _config_boolean, "false", "HALO_HIGH_RES_HUD", _environment_value, _platform_all,
		"Draw the HUD (meters, counters, panels, motion sensor, reticles,\n"
		"waypoints, scopes) from the high-res assets (8x the maps' bitmaps);\n"
		"false draws the maps' own bitmaps." },

	{ "audio.enabled", _config_boolean, "true", "HALO_NO_AUDIO", _environment_set_is_false, _platform_all,
		"Play sound." },
	{ "audio.volume", _config_real, "1.0", "HALO_VOLUME", _environment_value, _platform_all,
		"The volume of everything, 0.0 to 1.0." },
	{ "audio.music_volume", _config_real, "1.0", NULL, _environment_value, _platform_all,
		"Music volume, 0.0 to 1.0, in addition to the master volume." },
	{ "audio.effects_volume", _config_real, "1.0", NULL, _environment_value, _platform_all,
		"Sound effects and multiplayer announcer volume, 0.0 to 1.0." },
	{ "audio.dialogue_volume", _config_real, "1.0", NULL, _environment_value, _platform_all,
		"Unit and scripted dialogue volume, 0.0 to 1.0." },
	{ "audio.timer_volume", _config_real, "1.0", NULL, _environment_value, _platform_all,
		"Optional Performance Build timer recordings volume, 0.0 to 1.0." },
	{ "audio.timer_countdown", _config_boolean, "true", NULL, _environment_value, _platform_all,
		"Play countdown announcements when the host enables PB Timer Sounds." },
	{ "audio.timer_beeps", _config_boolean, "true", NULL, _environment_value, _platform_all,
		"Play countdown beeps when the host enables PB Timer Sounds." },
	{ "audio.timer_minutes", _config_boolean, "true", NULL, _environment_value, _platform_all,
		"Announce elapsed minutes when the host enables PB Timer Sounds." },
	{ "audio.timer_items", _config_boolean, "false", NULL, _environment_value, _platform_all,
		"Announce scheduled rockets and powerups on supported maps when the\n"
		"host enables PB Timer Sounds. Off preserves the existing timer audio." },
	{ "audio.menu_music", _config_boolean, "true", NULL, _environment_value, _platform_all,
		"Play the main menu title music. False keeps menu effects and gameplay\n"
		"audio enabled. In-game audio settings apply immediately when accepted." },

	{ "input.mouse_sensitivity", _config_real, "1.0", "HALO_MOUSE_SENSITIVITY", _environment_value, _platform_desktop,
		"How far the view turns for the mouse's movement." },
	{ "input.invert_mouse", _config_boolean, "false", "HALO_MOUSE_INVERT", _environment_set_is_true, _platform_desktop,
		"Moving the mouse forward looks down." },
	{ "input.mouse_aim_assist", _config_boolean, "false", "HALO_MOUSE_AIM_ASSIST", _environment_value, _platform_desktop,
		"Magnetism while aiming with the mouse, as with a controller: the view\n"
		"slowed and dragged along by a target. The last of the mouse and the\n"
		"right stick to move decides. The bullets' autoaim (bent toward the\n"
		"target) stays either way." },

	/* Bindings are config-only: they do not need application environment variables. */
#if defined(HALO_MACOS) && !defined(HALO_IOS)
#define BINDING(name, mac, other, comment) { "bindings." #name, _config_string, "\"" mac "\"", NULL, _environment_value, _platform_all, comment },
#else
#define BINDING(name, mac, other, comment) { "bindings." #name, _config_string, "\"" other "\"", NULL, _environment_value, _platform_all, comment },
#endif
#include "input_bindings.def"
#undef BINDING

	{ "game.console_log", _config_string, "\"important\"", NULL, _environment_value, _platform_all,
		"What the game's console shows on screen of what it logs: \"important\"\n"
		"(bans, players dropped for cheating, what refuses a command, and the\n"
		"asserts that stop the game), \"all\" (every line, the game's own\n"
		"chatter too), or \"none\" (the asserts that stop the game only). What\n"
		"a command prints shows whatever this is, and debug.txt has every line." },

	{ "game.language", _config_string, "\"\"", "HALO_LANGUAGE", _environment_value, _platform_all,
		"The language the game asks the Xbox for: \"ja\", \"de\", \"fr\", \"es\" or \"it\";\n"
		"empty for English. The game data decides what is translated." },

	{ "paths.data", _config_string, "\"\"", "HALO_DATA_ROOT", _environment_value, _platform_desktop,
		"The folder holding the game data's maps folder; empty looks in the\n"
		"working directory and its assets folder. Windows paths are easiest in\n"
		"single quotes: 'C:\\Games\\Halo'." },
	{ "paths.saves", _config_string, "\"\"", "HALO_SAVE_ROOT", _environment_value, _platform_desktop,
		"Where saved games and profiles go; empty for the usual place\n"
		"(~/.local/share/halo-og, or %APPDATA%\\Halo OG on Windows).\n"
		"Legacy default saves are copied without replacing existing files;\n"
		"if migration fails, the game reports it and keeps the legacy folder." },

	{ "network.address", _config_string, "\"\"", "HALO_NET_ADDRESS", _environment_value, _platform_all,
		"This machine's IPv4 address for system link, for a machine on several\n"
		"networks; empty chooses one." },
	{ "network.broadcast", _config_string, "\"\"", "HALO_NET_BROADCAST", _environment_value, _platform_all,
		"Comma-separated IPv4 addresses system link sends its announcements to\n"
		"instead of the local network's broadcast address (for VPNs); empty for\n"
		"the local network." },
	{ "network.online", _config_boolean, "true", "HALO_NET_ONLINE", _environment_value, _platform_all,
		"Internet play: hosting makes an invite link (logged, and put on the\n"
		"clipboard) that lets whoever has it join over the internet; opening a\n"
		"link (or copying one before switching to the game) joins. Only people\n"
		"with the invite can join. Off keeps system link to the local network." },
	{ "network.join_from_clipboard", _config_boolean, "true", "HALO_NET_JOIN_FROM_CLIPBOARD", _environment_value,
		_platform_all,
		"Join the game of an invite link found on the clipboard when the game\n"
		"comes to the front." },
	{ "network.tunnel_port", _config_integer, "0", "HALO_NET_TUNNEL_PORT", _environment_value, _platform_all,
		"The UDP port internet play uses; 0 picks one. A fixed one can be\n"
		"forwarded on the router, for networks whose NAT stops connections." },
	{ "network.allow_upnp", _config_boolean, "true", "HALO_NET_ALLOW_UPNP", _environment_value, _platform_all,
		"Let internet play ask the router (UPnP) to forward its port, for\n"
		"networks whose NAT stops connections: when a player joins this\n"
		"machine's game, and when joining a game takes too long. False never\n"
		"asks." },
	{ "network.signalling_brokers", _config_string,
		"\"broker.emqx.io:1883,broker.hivemq.com:1883,test.mosquitto.org:1883\"",
		"HALO_NET_BROKERS", _environment_value, _platform_all,
		"Public MQTT brokers through which the machines of an invite find each\n"
		"other (its messages are encrypted); comma-separated host:port." },
	{ "network.stun_servers", _config_string, "\"stun.l.google.com:19302,stun.cloudflare.com:3478\"",
		"HALO_NET_STUN", _environment_value, _platform_all,
		"Public STUN servers that tell this machine its internet address;\n"
		"comma-separated host:port." },
	{ "discord.application_id", _config_string, "\"1553978809840050229\"", "HALO_DISCORD_APPLICATION",
		_environment_value, _platform_desktop,
		"The Discord application internet play invites go through while the\n"
		"Discord desktop client runs; empty for none." },

	{ "update.auto", _config_boolean, "true", "HALO_UPDATE_AUTO", _environment_value, _platform_all,
		"Look for a new version when the game starts, and offer to update to it;\n"
		"false never looks (the game's \"Do not ask again\" writes false here)." },

	{ "debug.network_test", _config_string, "\"\"", "HALO_NETWORK_TEST", _environment_value, _platform_all,
		"Automated system link sessions for testing (port/linux/game/network_test.c):\n"
		"\"host:<map>\" hosts a game on that map, \"join\" joins the first game found;\n"
		"empty for none." },
	{ "debug.network_test_start", _config_real, "15.0", "HALO_NETWORK_TEST_START", _environment_value, _platform_all,
		"Seconds after hosting that an automated test game starts." },
	{ "debug.network_test_kill", _config_real, "0.0", "HALO_NETWORK_TEST_KILL", _environment_value, _platform_all,
		"Every this many seconds an automated test host kills its last player; 0 never." },
	{ "debug.network_test_score", _config_integer, "0", "HALO_NETWORK_TEST_SCORE", _environment_value, _platform_all,
		"The score an automated test host's game type plays to (a short game, to\n"
		"test the next); 0 the game type's own." },
	{ "debug.network_test_shoot", _config_real, "0.0", "HALO_NETWORK_TEST_SHOOT", _environment_value, _platform_all,
		"Every this many seconds each automated test player hits the next with\n"
		"their weapon, within its reach (the host brings far players near the\n"
		"first a second before); 0 never." },
	{ "debug.network_test_vehicle", _config_real, "0.0", "HALO_NETWORK_TEST_VEHICLE", _environment_value, _platform_all,
		"This many seconds into an automated test game the host seats its last\n"
		"player as a vehicle's driver (and out 15 seconds on); 0 never." },
	{ "debug.network_test_pickup", _config_real, "0.0", "HALO_NETWORK_TEST_PICKUP", _environment_value, _platform_all,
		"This many seconds into an automated test game the host stands its last\n"
		"player on a weapon, which a joining player then picks up; 0 never." },
	{ "debug.network_test_pickup_weapon", _config_string, "\"\"", "HALO_NETWORK_TEST_PICKUP_WEAPON", _environment_value,
		_platform_all,
		"The weapon network_test_pickup stands the player on: the first whose tag\n"
		"name has this in it (\"sniper\", say); empty any." },
	{ "debug.telnet_console", _config_boolean, "false", "HALO_TELNET_CONSOLE", _environment_set_is_true, _platform_all,
		"Listen on 127.0.0.1 (port telnet_console_port) for a script console that\n"
		"runs what it is sent as the game's console does, with no password; false\n"
		"none." },
	{ "debug.telnet_console_port", _config_integer, "2323", NULL, _environment_value,
		_platform_all,
		"The port of the script console (telnet_console); the Xbox's was 23, which\n"
		"only the administrator can listen on." },
	{ "debug.network_latency", _config_real, "0.0", "HALO_NETWORK_LATENCY", _environment_value, _platform_all,
		"Milliseconds everything received is held back (a round trip between two\n"
		"machines of twice it), to test the netcode as over the internet; 0 none." },
	{ "debug.network_loss", _config_real, "0.0", "HALO_NETWORK_LOSS", _environment_value, _platform_all,
		"Percent of datagrams received that are dropped, for the same; 0 none." },
	{ "debug.test_input", _config_string, "\"\"", "HALO_TEST_INPUT", _environment_value, _platform_all,
		"\"bot:<seed>\" plays controller 1 with a scripted pattern (automated\n"
		"network tests); \"look:<seed>\" stands still, only turning and looking\n"
		"up and down; empty for none." },
	{ "debug.update_answer", _config_string, "\"\"", "HALO_UPDATE_ANSWER", _environment_value, _platform_desktop,
		"The answer to the new version question, for automated tests: \"yes\",\n"
		"\"no\" or \"never\" (do not ask again, confirmed); empty asks." },
	{ "debug.exit_after", _config_real, "0.0", "HALO_EXIT_AFTER", _environment_value, _platform_all,
		"Quit this many seconds after the window opens; 0 never." },
	{ "debug.hidden_window", _config_boolean, "false", "HALO_HIDDEN_WINDOW", _environment_set_is_true, _platform_desktop,
		"Keep the window hidden (and never fullscreen)." },
	{ "debug.null_renderer", _config_boolean, "false", "HALO_NULL_RENDERER", _environment_set_is_true, _platform_all,
		"Run without a window, drawing nothing." },
	{ "debug.gl_debug", _config_boolean, "false", "HALO_GL_DEBUG", _environment_set_is_true, _platform_all,
		"Report OpenGL errors in the log." },
	{ "debug.gpu_stats", _config_boolean, "false", "HALO_GPU_STATS", _environment_set_is_true, _platform_all,
		"Log the renderer's draw counts once a second." },
	{ "debug.gpu_trace_frame", _config_integer, "-1", "HALO_GPU_TRACE", _environment_value, _platform_all,
		"Log every draw of this frame; -1 none." },
	{ "debug.gpu_trace_constants", _config_boolean, "false", "HALO_GPU_TRACE_CONSTANTS", _environment_set_is_true, _platform_all,
		"With gpu_trace_frame, also the vertex shader constants." },
	{ "debug.gpu_skip_vertex_shaders", _config_string, "\"\"", "HALO_GPU_SKIP_VS", _environment_value, _platform_all,
		"Comma-separated ids of vertex shaders not to draw with." },
	{ "debug.gpu_dump_shaders", _config_string, "\"\"", "HALO_GPU_DUMP_SHADERS", _environment_value, _platform_all,
		"A folder to write the generated GLSL to; empty none." },
	{ "debug.gpu_debug_expression", _config_string, "\"\"", "HALO_GPU_DEBUG_EXPR", _environment_value, _platform_all,
		"A GLSL expression every pixel shader shows instead of its result." },
	{ "debug.gpu_debug_texture0", _config_boolean, "false", "HALO_GPU_DEBUG_T0", _environment_set_is_true, _platform_all,
		"Pixel shaders show their first texture." },
	{ "debug.gpu_debug_flat", _config_boolean, "false", "HALO_GPU_DEBUG_FLAT", _environment_set_is_true, _platform_all,
		"Pixel shaders show their vertex colour." },
	{ "debug.screenshot_directory", _config_string, "\"\"", "HALO_SCREENSHOT_DIR", _environment_value, _platform_all,
		"A folder to save frames to (with screenshot_every); empty none." },
	{ "debug.screenshot_every", _config_integer, "0", "HALO_SCREENSHOT_EVERY", _environment_value, _platform_all,
		"Save every this many frames to screenshot_directory; 0 none." },
	{ "debug.texture_dump_directory", _config_string, "\"\"", "HALO_TEXTURE_DUMP", _environment_value, _platform_all,
		"A folder to write every texture to as it is uploaded; empty none." },
	{ "debug.texture_log", _config_boolean, "false", "HALO_TEXTURE_LOG", _environment_set_is_true, _platform_all,
		"Log texture uploads." },
	{ "debug.texture_no_cache", _config_boolean, "false", "HALO_TEXTURE_NO_CACHE", _environment_set_is_true, _platform_all,
		"Upload textures again every time they are used." },
	{ "debug.sample_seconds", _config_real, "0.0", "HALO_SAMPLE", _environment_value, _platform_android,
		"Log where every game thread is this often, in seconds (read by the\n"
		"app, port/android/host/host_debug.c); 0 never." },
};

#define NUMBER_OF_CONFIG_SETTINGS (sizeof(config_settings) / sizeof(config_settings[0]))

#if defined(HALO_MACOS) && !defined(HALO_IOS)
#define CONFIG_PLATFORM _platform_desktop
#elif defined(HALO_ANDROID)
#define CONFIG_PLATFORM _platform_android
#else
#define CONFIG_PLATFORM _platform_desktop
#endif

struct config_value
{
	int boolean;
	long integer;
	double real;
	char *string;
};

static struct config_value config_values[NUMBER_OF_CONFIG_SETTINGS];
static int config_loaded = 0;
static volatile unsigned long config_change_count;
static pthread_mutex_t config_lock = PTHREAD_MUTEX_INITIALIZER;

/* ---------- the file */

static void config_path(char *path, size_t size)
{
#ifdef HALO_MACOS
	/* Apple app bundles are read-only on iOS. Keep settings with the saves
	in the writable Application Support directory selected by the host. */
	const char *root = getenv("HALO_SAVE_ROOT");

	snprintf(path, size, "%s/config.toml", root && *root ? root : ".");
#elif defined(HALO_ANDROID)
	/* the data folder, which the app names (port/android/host/host_main.c) */
	const char *root = getenv("HALO_DATA_ROOT");

	snprintf(path, size, "%s/config.toml", root && *root ? root : ".");
#else
	/* the executable's folder, with its separator */
	const char *base = SDL_GetBasePath();

	snprintf(path, size, "%sconfig.toml", base ? base : "");
#endif
}

/* the whole file, NUL terminated, or NULL; free() it */
static char *config_read_file(const char *path, size_t *size)
{
#ifdef HALO_ANDROID
	FILE *file = fopen(path, "rb");
	char *text = NULL;
	long length;

	if (!file)
		return NULL;
	if (fseek(file, 0, SEEK_END) == 0 && (length = ftell(file)) >= 0 && fseek(file, 0, SEEK_SET) == 0)
	{
		text = malloc((size_t)length + 1);
		if (text && fread(text, 1, (size_t)length, file) == (size_t)length)
		{
			text[length] = 0;
			*size = (size_t)length;
		}
		else
		{
			free(text);
			text = NULL;
		}
	}
	fclose(file);
	return text;
#else
	/* SDL's, for UTF-8 paths on Windows */
	void *data = SDL_LoadFile(path, size);
	char *text;

	if (!data)
		return NULL;
	text = malloc(*size + 1);
	if (text)
	{
		memcpy(text, data, *size);
		text[*size] = 0;
	}
	SDL_free(data);
	return text;
#endif
}

static int config_write_file(const char *path, const char *text)
{
#ifdef HALO_ANDROID
	FILE *file = fopen(path, "wb");
	int written;

	if (!file)
		return 0;
	written = fwrite(text, 1, strlen(text), file) == strlen(text);
	return fclose(file) == 0 && written;
#else
	return SDL_SaveFile(path, text, strlen(text));
#endif
}

struct config_text
{
	char *buffer;
	size_t length, capacity;
};

static void config_append(struct config_text *text, const char *string)
{
	size_t length = strlen(string);

	if (text->length + length + 1 > text->capacity)
	{
		size_t capacity = (text->capacity ? text->capacity : 4096) * 2 + length;
		char *buffer = realloc(text->buffer, capacity);

		if (!buffer)
			return;
		text->buffer = buffer;
		text->capacity = capacity;
	}
	memcpy(text->buffer + text->length, string, length + 1);
	text->length += length;
}

/* the first length characters of text, as a string of their own */
static char *config_copy(const char *text, size_t length)
{
	char *copy = malloc(length + 1);

	if (copy)
	{
		memcpy(copy, text, length);
		copy[length] = 0;
	}
	return copy;
}

/* one setting as the file holds it: its comment, and its key at the
default */
static void config_append_setting(struct config_text *text, const struct config_setting *setting)
{
	const char *dot = strchr(setting->name, '.');
	const char *line;
	char buffer[256];

	config_append(text, "\n");
	for (line = setting->comment; *line;)
	{
		size_t length = strcspn(line, "\n");

		snprintf(buffer, sizeof(buffer), "# %.*s\n", (int)length, line);
		config_append(text, buffer);
		line += length;
		if (*line)
			line++;
	}
#ifndef HALO_ANDROID
	/* (Android apps have no environment to set) */
	if (setting->environment)
	{
		switch (setting->environment_style)
		{
		case _environment_value:
			snprintf(buffer, sizeof(buffer), "# (for one run: %s=<value>)\n", setting->environment);
			break;
		case _environment_set_is_true:
			snprintf(buffer, sizeof(buffer), "# (for one run: %s=1 makes it true)\n", setting->environment);
			break;
		case _environment_set_is_false:
			snprintf(buffer, sizeof(buffer), "# (for one run: %s=1 makes it false)\n", setting->environment);
			break;
		}
		config_append(text, buffer);
	}
#endif
	snprintf(buffer, sizeof(buffer), "%s = %s\n", dot + 1, setting->default_value);
	config_append(text, buffer);
}

/* the file with every setting of this build at its default */
static char *config_default_text(void)
{
	struct config_text text = { NULL, 0, 0 };
	char section[32] = "";
	size_t index;

#ifdef HALO_ANDROID
	config_append(&text,
		"# Halo settings\n"
		"#\n"
		"# The game writes this file with the defaults when it is missing: delete\n"
		"# it to go back to them.\n");
#else
	config_append(&text,
		"# Halo settings\n"
		"#\n"
		"# The game writes this file with the defaults when it is missing: delete\n"
		"# it to go back to them. Each setting can also be set for one run with\n"
		"# the environment variable named with it, which wins over this file.\n");
#endif
	for (index = 0; index < NUMBER_OF_CONFIG_SETTINGS; index++)
	{
		const struct config_setting *setting = &config_settings[index];
		const char *dot = strchr(setting->name, '.');
		char buffer[64];

		if (!(setting->platforms & CONFIG_PLATFORM) || !dot)
			continue;
		if (strncmp(section, setting->name, (size_t)(dot - setting->name)) ||
			section[dot - setting->name] != 0)
		{
			snprintf(section, sizeof(section), "%.*s", (int)(dot - setting->name), setting->name);
			snprintf(buffer, sizeof(buffer), "\n[%s]\n", section);
			config_append(&text, buffer);
		}
		config_append_setting(&text, setting);
	}
	return text.buffer;
}

/* the settings of this build that text (the file, parsed as table) lacks,
added to it in their sections, keeping the rest as it is: a newer version's
settings appear in an older file. Returns the new text, or NULL if nothing
was missing */
static char *config_add_missing(const char *text, toml_datum_t table)
{
	char *result = NULL;
	size_t index;

	for (index = 0; index < NUMBER_OF_CONFIG_SETTINGS; index++)
	{
		const struct config_setting *setting = &config_settings[index];
		const char *dot = strchr(setting->name, '.');
		const char *current = result ? result : text;
		struct config_text block = { NULL, 0, 0 };
		struct config_text updated = { NULL, 0, 0 };
		char header[40];
		const char *line;
		const char *insert = NULL;

		if (!(setting->platforms & CONFIG_PLATFORM) || !dot || toml_seek(table, setting->name).type != TOML_UNKNOWN)
			continue;
		snprintf(header, sizeof(header), "[%.*s]", (int)(dot - setting->name), setting->name);
		/* the end of the section's last line that is not blank */
		for (line = current; *line; )
		{
			const char *start = line;
			size_t length = strcspn(line, "\n");

			while (*start == ' ' || *start == '\t')
				start++;
			if (insert && *start == '[')
				break;
			if (!insert && !strncmp(start, header, strlen(header)))
				insert = line + length;
			else if (insert && start < line + length && *start != '\r')
				insert = line + length;
			line += length;
			if (*line)
				line++;
		}
		if (insert)
		{
			if (*insert)
				insert++;
			config_append_setting(&block, setting);
		}
		else
		{
			/* no such section: a new one at the end */
			insert = current + strlen(current);
			config_append(&block, current[0] && insert[-1] != '\n' ? "\n\n" : "\n");
			config_append(&block, header);
			config_append(&block, "\n");
			config_append_setting(&block, setting);
		}
		if (!block.buffer)
			continue;
		{
			char *before = config_copy(current, (size_t)(insert - current));

			if (before)
				config_append(&updated, before);
			free(before);
		}
		if (insert > current && insert[-1] != '\n')
			config_append(&updated, "\n");
		config_append(&updated, block.buffer);
		config_append(&updated, insert);
		free(block.buffer);
		if (updated.buffer)
		{
			free(result);
			result = updated.buffer;
			platform_log("settings: added %s (new in this version) at its default", setting->name);
		}
	}
	return result;
}

/* ---------- values */

static int config_text_is_false(const char *text)
{
	char lower[8];
	size_t index;

	for (index = 0; index + 1 < sizeof(lower) && text[index]; index++)
		lower[index] = (char)tolower((unsigned char)text[index]);
	lower[index] = 0;
	return !strcmp(lower, "0") || !strcmp(lower, "false") || !strcmp(lower, "no") || !strcmp(lower, "off");
}

static void config_set_from_text(struct config_value *value, enum config_type type, const char *text)
{
	switch (type)
	{
	case _config_boolean:
		value->boolean = !config_text_is_false(text);
		break;
	case _config_integer:
		value->integer = strtol(text, NULL, 10);
		break;
	case _config_real:
		value->real = strtod(text, NULL);
		break;
	case _config_string:
		free(value->string);
		value->string = strdup(text);
		break;
	}
}

/* the value in the file, if it is there and of the setting's type */
static void config_set_from_file(struct config_value *value, const struct config_setting *setting,
	toml_datum_t table)
{
	toml_datum_t datum = toml_seek(table, setting->name);
	int wrong_type = 0;

	if (datum.type == TOML_UNKNOWN)
		return;
	switch (setting->type)
	{
	case _config_boolean:
		if (datum.type == TOML_BOOLEAN)
			value->boolean = datum.u.boolean;
		else
			wrong_type = 1;
		break;
	case _config_integer:
		if (datum.type == TOML_INT64)
			value->integer = (long)datum.u.int64;
		else
			wrong_type = 1;
		break;
	case _config_real:
		if (datum.type == TOML_FP64)
			value->real = datum.u.fp64;
		else if (datum.type == TOML_INT64)
			value->real = (double)datum.u.int64;
		else
			wrong_type = 1;
		break;
	case _config_string:
		if (datum.type == TOML_STRING)
		{
			free(value->string);
			value->string = strdup(datum.u.s);
		}
		else
		{
			wrong_type = 1;
		}
		break;
	}
	if (wrong_type)
	{
		static const char *const expected[] = { "true or false", "a whole number", "a number", "a quoted string" };

		platform_log("config.toml line %d: %s should be %s; using %s", datum.lineno, setting->name,
			expected[setting->type], setting->default_value);
	}
}

static long config_setting_index(const char *name)
{
	size_t index;

	for (index = 0; index < NUMBER_OF_CONFIG_SETTINGS; index++)
	{
		if (!strcmp(config_settings[index].name, name))
			return (long)index;
	}
	return -1;
}

/* keys in the file that are no setting, likely misspelt */
static void config_report_unknown_keys(toml_datum_t table)
{
	int section_index;

	for (section_index = 0; section_index < table.u.tab.size; section_index++)
	{
		toml_datum_t section = table.u.tab.value[section_index];
		int key_index;

		if (section.type != TOML_TABLE)
		{
			platform_log("config.toml line %d: unknown setting %s", section.lineno, table.u.tab.key[section_index]);
			continue;
		}
		for (key_index = 0; key_index < section.u.tab.size; key_index++)
		{
			char name[128];

			snprintf(name, sizeof(name), "%s.%s", table.u.tab.key[section_index], section.u.tab.key[key_index]);
			if (config_setting_index(name) < 0)
				platform_log("config.toml line %d: unknown setting %s", section.u.tab.value[key_index].lineno, name);
		}
	}
}

static void config_load(int complete_file)
{
	char path[1024];
	size_t size = 0;
	char *text;
	size_t index;

	for (index = 0; index < NUMBER_OF_CONFIG_SETTINGS; index++)
	{
		const char *default_value = config_settings[index].default_value;

		if (config_settings[index].type == _config_string)
		{
			/* written as a TOML basic string without escapes */
			size_t length = strlen(default_value);

			config_values[index].string = length >= 2 ? config_copy(default_value + 1, length - 2) : strdup("");
		}
		else
		{
			config_set_from_text(&config_values[index], config_settings[index].type, default_value);
		}
	}

	config_path(path, sizeof(path));
	text = config_read_file(path, &size);
	if (text)
	{
		toml_result_t result = toml_parse(text, (int)size);

		if (result.ok)
		{
			char *completed;

			for (index = 0; index < NUMBER_OF_CONFIG_SETTINGS; index++)
				config_set_from_file(&config_values[index], &config_settings[index], result.toptab);
			config_report_unknown_keys(result.toptab);
			platform_log("settings: %s", path);
			completed = complete_file ? config_add_missing(text, result.toptab) : NULL;
			if (completed && !config_write_file(path, completed))
				platform_log("settings: cannot write %s", path);
			free(completed);
		}
		else
		{
			platform_log("config.toml: %s; using the defaults", result.errmsg);
		}
		toml_free(result);
		free(text);
	}
	else if (complete_file)
	{
		char *defaults = config_default_text();

		if (defaults && config_write_file(path, defaults))
			platform_log("settings: wrote the defaults to %s", path);
		else
			platform_log("settings: cannot write %s; using the defaults", path);
		free(defaults);
	}

	for (index = 0; index < NUMBER_OF_CONFIG_SETTINGS; index++)
	{
		const struct config_setting *setting = &config_settings[index];
		const char *environment = setting->environment ? getenv(setting->environment) : NULL;

		if (!environment)
			continue;
		switch (setting->environment_style)
		{
		case _environment_value:
			config_set_from_text(&config_values[index], setting->type, environment);
			break;
		case _environment_set_is_true:
			config_values[index].boolean = 1;
			break;
		case _environment_set_is_false:
			config_values[index].boolean = 0;
			break;
		}
	}
}

static struct config_value config_value(const char *name, enum config_type type)
{
	struct config_value result = { 0, 0, 0.0, "" };
	long index = config_setting_index(name);

	pthread_mutex_lock(&config_lock);
	if (!config_loaded)
	{
		config_load(1);
		config_loaded = 1;
	}
	if (index >= 0 && config_settings[index].type == type)
		result = config_values[index];
	else
		platform_log("settings: no %s setting %s", type == _config_string ? "string" : "such", name);
	pthread_mutex_unlock(&config_lock);
	/* Scalar reads are copied while locked, so saves cannot race the mixer
	or other native callers. Strings are immutable after the initial load. */
	return result;
}

/* ---------- writing a setting */

/* Source locations come from the parsed TOML, so comments, quoted keys and
inline tables are preserved rather than recognized by a line-shaped guess. */
static const char *config_source_line(const char *text, int number)
{
	if (number < 1)
		return NULL;
	while (--number)
	{
		text = strchr(text, '\n');
		if (!text)
			return NULL;
		text++;
	}
	return text;
}

static char *config_replace_text(const char *text, size_t size, size_t offset, size_t length, const char *replacement)
{
	size_t added = strlen(replacement);
	char *updated;

	if (offset > size || length > size - offset || added > SIZE_MAX - size - 1)
		return NULL;
	updated = malloc(size - length + added + 1);
	if (!updated)
		return NULL;
	memcpy(updated, text, offset);
	memcpy(updated + offset, replacement, added);
	memcpy(updated + offset + added, text + offset + length, size - offset - length);
	updated[size - length + added] = 0;
	return updated;
}

/* Replace the complete file only after its temporary sibling has been written
and closed successfully. A failed write must leave the original file intact. */
static int config_write_file_atomic(const char *path, const char *text)
{
	char temporary[1100];
	int succeeded = 0;
#ifdef _WIN32
	SDL_IOStream *file;
	size_t size = strlen(text);

	snprintf(temporary, sizeof(temporary), "%s.%llu.tmp", path,
		(unsigned long long)SDL_GetPerformanceCounter());
	file = SDL_IOFromFile(temporary, "wbx");
	if (!file)
		return 0;
	succeeded = SDL_WriteIO(file, text, size) == size;
	if (!SDL_CloseIO(file))
		succeeded = 0;
	if (succeeded)
		succeeded = SDL_RenamePath(temporary, path);
	if (!succeeded)
		SDL_RemovePath(temporary);
#else
	struct stat attributes;
	FILE *file;
	int descriptor;

	/* Respect a deliberately read-only config, even though replacing a file
	would otherwise require only write access to its parent directory. */
	if (stat(path, &attributes) || !S_ISREG(attributes.st_mode) || access(path, W_OK))
		return 0;
	snprintf(temporary, sizeof(temporary), "%s.XXXXXX", path);
	descriptor = mkstemp(temporary);
	if (descriptor < 0)
		return 0;
	file = fdopen(descriptor, "wb");
	if (file)
	{
		size_t size = strlen(text);

		succeeded = !fchmod(descriptor, attributes.st_mode & 0777) &&
			fwrite(text, 1, size, file) == size && !fflush(file) && !fsync(descriptor);
		if (fclose(file))
			succeeded = 0;
	}
	else
		close(descriptor);
	if (succeeded)
		succeeded = !rename(temporary, path);
	if (!succeeded)
		unlink(temporary);
#endif
	return succeeded;
}

static int config_number_matches(toml_datum_t datum, enum config_type type, double value)
{
	switch (type)
	{
	case _config_boolean:
		return datum.type == TOML_BOOLEAN && datum.u.boolean == (value != 0.0);
	case _config_integer:
		return datum.type == TOML_INT64 && datum.u.int64 == (long)value;
	case _config_real:
		return (datum.type == TOML_FP64 && datum.u.fp64 == value) ||
			(datum.type == TOML_INT64 && (double)datum.u.int64 == value);
	default:
		return 0;
	}
}

/* Source locations come from TOML, including dotted/quoted keys and inline
 tables. Only the value token is replaced; all surrounding text is retained. */
static char *config_edit_number(const char *text, size_t size, const struct config_setting *setting, double value)
{
	const char *name = setting->name, *dot = strchr(name, '.');
	char section[64], addition[256], number[64];
	char *updated = NULL;
	toml_result_t parsed = toml_parse(text, (int)size);
	toml_datum_t datum;

	if (!parsed.ok || !dot || (size_t)(dot - name) >= sizeof(section))
		goto done;
	if (setting->type == _config_boolean)
		snprintf(number, sizeof(number), "%s", value ? "true" : "false");
	else if (setting->type == _config_integer)
		snprintf(number, sizeof(number), "%ld", (long)value);
	else
	{
		snprintf(number, sizeof(number), "%.17g", value);
		if (!strpbrk(number, ".eE"))
			strcat(number, ".0");
	}
	datum = toml_seek(parsed.toptab, name);
	if ((setting->type == _config_boolean && datum.type == TOML_BOOLEAN) ||
		(setting->type == _config_integer && datum.type == TOML_INT64) ||
		(setting->type == _config_real && (datum.type == TOML_FP64 || datum.type == TOML_INT64)))
	{
		const char *line = config_source_line(text, datum.lineno);

		if (line && datum.colno > 0 && (size_t)(datum.colno - 1) < strcspn(line, "\r\n"))
		{
			const char *token = line + datum.colno - 1;
			size_t length = strcspn(token, " \t\r\n,#}]");

			if (length)
				updated = config_replace_text(text, size, (size_t)(token - text), length, number);
		}
	}
	else if (datum.type == TOML_UNKNOWN)
	{
		toml_datum_t table;
		const char *line;

		snprintf(section, sizeof(section), "%.*s", (int)(dot - name), name);
		table = toml_get(parsed.toptab, section);
		line = config_source_line(text, table.lineno);
		if (line)
			while (*line == ' ' || *line == '\t') line++;
		if (table.type == TOML_UNKNOWN)
		{
			snprintf(addition, sizeof(addition), "%s[%s]\n%s = %s\n",
				size && text[size - 1] != '\n' ? "\n" : "", section, dot + 1, number);
			updated = config_replace_text(text, size, size, 0, addition);
		}
		else if (table.type == TOML_TABLE && line && *line == '[' && line[1] != '[')
		{
			const char *end = strchr(line, '\n');
			size_t offset = end ? (size_t)(end + 1 - text) : size;

			snprintf(addition, sizeof(addition), "%s%s = %s\n", end ? "" : "\n", dot + 1, number);
			updated = config_replace_text(text, size, offset, 0, addition);
		}
		else if (table.type == TOML_TABLE)
		{
			/* Dotted-key tables can be extended at top level. Inline tables
			are closed; the final parse rejects extending them. */
			snprintf(addition, sizeof(addition), "%s = %s\n", name, number);
			updated = config_replace_text(text, size, 0, 0, addition);
		}
	}
 done:
	toml_free(parsed);
	return updated;
}

int config_write_numbers(const char *const *names, const double *values, unsigned count)
{
	long indices[NUMBER_OF_CONFIG_SETTINGS];
	char path[1024], *text = NULL;
	size_t size = 0;
	unsigned item;
	int succeeded = 0;

	if (count > NUMBER_OF_CONFIG_SETTINGS || (count && (!names || !values)))
		return 0;
	if (!count)
		return 1;
	for (item = 0; item < count; item++)
	{
		long index = names[item] ? config_setting_index(names[item]) : -1;
		double value = values[item];
		unsigned previous;

		if (index < 0 || !isfinite(value) || config_settings[index].type == _config_string)
			return 0;
		if (config_settings[index].type == _config_boolean && value != 0.0 && value != 1.0)
			return 0;
		if (config_settings[index].type == _config_integer &&
			(value < (double)LONG_MIN || value >= -(double)LONG_MIN || (double)(long)value != value))
			return 0;
		for (previous = 0; previous < item; previous++)
			if (indices[previous] == index)
				return 0;
		indices[item] = index;
	}
	pthread_mutex_lock(&config_lock);
	if (!config_loaded)
	{
		/* A save as the first config operation must not rewrite missing
		defaults before the requested batch has been validated and committed. */
		config_load(0);
		config_loaded = 1;
	}
	config_path(path, sizeof(path));
	text = config_read_file(path, &size);
	if (!text || size > INT_MAX)
		goto done;
	for (item = 0; item < count; item++)
	{
		char *updated = config_edit_number(text, size, &config_settings[indices[item]], values[item]);

		if (!updated)
			goto done;
		free(text);
		text = updated;
		size = strlen(text);
		if (size > INT_MAX)
			goto done;
	}
	{
		toml_result_t check = toml_parse(text, (int)size);
		int valid = check.ok;

		for (item = 0; valid && item < count; item++)
			valid = config_number_matches(toml_seek(check.toptab, names[item]),
				config_settings[indices[item]].type, values[item]);
		toml_free(check);
		if (valid)
			succeeded = config_write_file_atomic(path, text);
	}
	if (succeeded)
	{
		for (item = 0; item < count; item++)
		{
			struct config_value *saved = &config_values[indices[item]];

			switch (config_settings[indices[item]].type)
			{
			case _config_boolean: saved->boolean = values[item] != 0.0; break;
			case _config_integer: saved->integer = (long)values[item]; break;
			case _config_real: saved->real = values[item]; break;
			default: break;
			}
		}
		config_change_count++;
	}
 done:
	pthread_mutex_unlock(&config_lock);
	free(text);
	return succeeded;
}

int config_write_boolean(const char *name, int value)
{
	long index = name ? config_setting_index(name) : -1;
	double number = value != 0;

	if (index < 0 || config_settings[index].type != _config_boolean)
		return 0;
	return config_write_numbers(&name, &number, 1);
}


/* the line's key, if it is "key = ..." (after spaces) */
static int config_line_key(const char *line, const char *end, const char *key)
{
	size_t length = strlen(key);

	while (line < end && (*line == ' ' || *line == '\t'))
		line++;
	if ((size_t)(end - line) <= length || strncmp(line, key, length) != 0)
		return 0;
	line += length;
	while (line < end && (*line == ' ' || *line == '\t'))
		line++;
	return line < end && *line == '=';
}

static int config_line_section(const char *line, const char *end, char *section, size_t size)
{
	const char *close;

	while (line < end && (*line == ' ' || *line == '\t'))
		line++;
	if (line >= end || *line != '[')
		return 0;
	close = memchr(line, ']', (size_t)(end - line));
	if (!close || (size_t)(close - line - 1) >= size)
		return 0;
	memcpy(section, line + 1, (size_t)(close - line - 1));
	section[close - line - 1] = 0;
	return 1;
}

int config_write(const char *name, const char *value)
{
	const char *dot = strchr(name, '.');
	long index = config_setting_index(name);
	char section[64], key[64], wanted[80], current[64] = "", line_text[600], path[1024];
	struct config_text out = { 0 };
	size_t size = 0;
	char *file_text;
	const char *line;
	int written = 0, in_section = 0, succeeded;

	if (index < 0 || !dot || (size_t)(dot - name) >= sizeof(section) || strlen(value) > 256)
		return 0;
	config_value(name, config_settings[index].type);
	pthread_mutex_lock(&config_lock);
	config_set_from_text(&config_values[index], config_settings[index].type, value);
	snprintf(section, sizeof(section), "%.*s", (int)(dot - name), name);
	snprintf(key, sizeof(key), "%s", dot + 1);
	switch (config_settings[index].type)
	{
	case _config_boolean:
		snprintf(line_text, sizeof(line_text), "%s = %s\n", key, config_values[index].boolean ? "true" : "false");
		break;
	case _config_integer:
		snprintf(line_text, sizeof(line_text), "%s = %ld\n", key, config_values[index].integer);
		break;
	case _config_real:
		snprintf(line_text, sizeof(line_text), "%s = %.15g", key, config_values[index].real);
		if (!strpbrk(line_text + strlen(key) + 3, ".en"))
			strcat(line_text, ".0");
		strcat(line_text, "\n");
		break;
	case _config_string:
	{
		char *end = line_text + snprintf(line_text, sizeof(line_text), "%s = \"", key);
		const char *character;

		for (character = config_values[index].string; *character; character++)
		{
			if (*character == '"' || *character == '\\')
				*end++ = '\\';
			*end++ = *character;
		}
		strcpy(end, "\"\n");
		break;
	}
	}
	snprintf(wanted, sizeof(wanted), "%s", section);
	config_path(path, sizeof(path));
	file_text = config_read_file(path, &size);
	for (line = file_text ? file_text : ""; *line;)
	{
		const char *end = line + strcspn(line, "\n");
		const char *next = *end ? end + 1 : end;

		if (config_line_section(line, end, current, sizeof(current)))
		{
			if (in_section && !written)
			{
				config_append(&out, line_text);
				written = 1;
			}
			in_section = !strcmp(current, wanted);
		}
		else if (in_section && !written && config_line_key(line, end, key))
		{
			config_append(&out, line_text);
			written = 1;
			line = next;
			continue;
		}
		{
			char *copy = config_copy(line, (size_t)(next - line));

			if (copy)
			{
				config_append(&out, copy);
				free(copy);
			}
		}
		line = next;
	}
	if (!written)
	{
		if (out.length && out.buffer[out.length - 1] != '\n')
			config_append(&out, "\n");
		if (!in_section)
		{
			char header[80];

			snprintf(header, sizeof(header), "\n[%s]\n", section);
			config_append(&out, header);
		}
		config_append(&out, line_text);
	}
	succeeded = out.buffer && config_write_file(path, out.buffer);
	config_change_count++;
	pthread_mutex_unlock(&config_lock);
	free(out.buffer);
	free(file_text);
	return succeeded;
}

int config_text(const char *name, char *text, size_t size)
{
	long index = config_setting_index(name);
	struct config_value value;

	if (index < 0)
		return 0;
	value = config_value(name, config_settings[index].type);
	switch (config_settings[index].type)
	{
	case _config_boolean:
		snprintf(text, size, "%s", value.boolean ? "true" : "false");
		break;
	case _config_integer:
		snprintf(text, size, "%ld", value.integer);
		break;
	case _config_real:
		snprintf(text, size, "%.15g", value.real);
		break;
	case _config_string:
		snprintf(text, size, "%s", value.string ? value.string : "");
		break;
	}
	return 1;
}

void config_folder(char *path, size_t size)
{
	char file[1024];
	char *separator;

	config_path(file, sizeof(file));
	separator = strrchr(file, '/');
#ifndef HALO_ANDROID
	if (!separator || (strrchr(file, '\\') && strrchr(file, '\\') > separator))
		separator = strrchr(file, '\\');
#endif
	if (separator)
		separator[1] = 0;
	else
		file[0] = 0;
	snprintf(path, size, "%s", file);
}

unsigned long config_changes(void)
{
	return config_change_count;
}

int config_default(const char *name, char *text, size_t size)
{
	long index = config_setting_index(name);
	const char *value;
	size_t length;

	if (index < 0)
		return 0;
	value = config_settings[index].default_value;
	length = strlen(value);
	if (config_settings[index].type == _config_string && length >= 2 && value[0] == '"')
	{
		value++;
		length -= 2;
	}
	snprintf(text, size, "%.*s", (int)length, value);
	return 1;
}

/* ---------- public code */

int config_boolean(const char *name)
{
	return config_value(name, _config_boolean).boolean;
}

long config_integer(const char *name)
{
	return config_value(name, _config_integer).integer;
}

double config_real(const char *name)
{
	return config_value(name, _config_real).real;
}

const char *config_string(const char *name)
{
	const char *string = config_value(name, _config_string).string;

	return string ? string : "";
}
