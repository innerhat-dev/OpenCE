"""Exercise optional practice flags through the existing game-variant save flow.

The format helpers are compiled directly. Variant declarations, cleanup, editor
dirty comparison and playlist read/write functions come from production source.
The fixture replaces file/thread APIs and the Xbox content-signature provider;
it checks bytes and control flow, not real platform storage or XDK signatures.
The guest's 32-bit longs and 16-bit wchar_t are made explicit on the test host.
"""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def block(source, signature):
    start = source.index(signature)
    opening = source.index("{", start)
    depth = 0
    tokens = r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[{}]'
    for match in re.finditer(tokens, source[opening:], re.S):
        if match[0] == "{":
            depth += 1
        elif match[0] == "}":
            depth -= 1
            if not depth:
                return source[start:opening + match.end()]
    raise ValueError(f"Unclosed C block: {signature}")


PREFIX = r'''
#include <assert.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint8_t byte, boolean;
typedef uint16_t word, game_wchar_t;
typedef float real;
#define TRUE 1
#define FALSE 0
#define NONE (-1)
#define __stdcall
#define csmemcpy memcpy
#define csmemcmp memcmp
#define csmemset memset
#define NUMBEROF(a) (sizeof(a) / sizeof((a)[0]))
#define FLAG(n) (UINT32_C(1) << (n))
#define TEST_FLAG(f,n) (((uint32_t)(f) & FLAG(n)) != 0)
#define SET_FLAG(f,n,v) ((f) = (v) ? ((f) | FLAG(n)) : ((f) & ~FLAG(n)))
#define MAX(a,b) ((a) > (b) ? (a) : (b))
#define MIN(a,b) ((a) < (b) ? (a) : (b))
#define PIN(v,a,b) MIN(MAX(v,a),b)
#define FLOOR(v,a) MAX(v,a)
#define match_assert(file,line,condition) assert(condition)
#define match_vassert(file,line,condition,message) assert(condition)
#define error(...) ((void)0)
enum { game_engine_ctf=1, game_engine_slayer, game_engine_oddball, game_engine_king, game_engine_race };
enum { NUMBER_OF_GAME_ENGINE_WEAPON_SETS=16, NUMBER_OF_GAME_ENGINE_VEHICLE_SETS=8, MAXIMUM_ODDBALLS=16 };
enum { SAVED_GAME_FILE_BLOCK_SIZE=512, PLAYLIST_PROFILE_CHECKSUM_DATA_SIZE=104, MAXIMUM_GAME_VARIANT_NAME_LENGTH=12 };
enum { _saved_game_file_index_valid_bit=31, _saved_game_file_index_read_only_bit=30,
       _saved_game_file_type_player_profile=0, _saved_game_file_type_game_variant=1,
       _variant_is_system_default_bit=0, _permission_read_bit=0 };
/* VARIANT DECLARATIONS */
#define __GAME_ENGINE_H
#include "game/performance_variant.h"
struct file_reference { unsigned index; };
struct thread_reference { unsigned complete; };
typedef struct _XCALCSIG_SIGNATURE { byte value[20]; } XCALCSIG_SIGNATURE;
/* PLAYLIST DECLARATIONS */
static struct playlist_profile_runtime_globals_prefix playlist_profile_globals;
static byte disk[3][SAVED_GAME_FILE_BLOCK_SIZE];
static unsigned selected_file, checksum_calls, write_calls;
static game_wchar_t display_name[12] = {'s','a','v','e','d',0};
static void saved_game_file_generate_checksum(const void *data, unsigned length, XCALCSIG_SIGNATURE *out) {
    const byte *bytes = data; uint32_t hash = 2166136261u;
    assert(length == sizeof(struct game_variant)); checksum_calls++;
    for (unsigned i = 0; i < length; i++) hash = (hash ^ bytes[i]) * 16777619u;
    for (unsigned i = 0; i < sizeof(out->value); i++) out->value[i] = (byte)(hash >> ((i % 4) * 8));
}
static boolean saved_game_files_take_mutex(void) { return TRUE; }
static void saved_game_files_release_mutex(void) {}
static boolean saved_game_file_open(struct file_reference *file, int32_t index) {
    file->index = (unsigned)index & 3; assert(file->index < 3); return TRUE;
}
static boolean saved_game_file_close(struct file_reference *file, int32_t index) { (void)file; (void)index; return TRUE; }
static boolean file_reference_create_from_path(struct file_reference *file, char *path, boolean directory) {
    (void)path; (void)directory; file->index = selected_file; return TRUE;
}
static boolean file_open(struct file_reference *file, unsigned flags) { (void)file; (void)flags; return TRUE; }
static void file_close(struct file_reference *file) { (void)file; }
static boolean file_set_position(struct file_reference *file, int32_t position) { (void)file; assert(position == 0); return TRUE; }
static boolean file_write(struct file_reference *file, unsigned size, const void *data) {
    assert(size == sizeof(disk[0])); memcpy(disk[file->index], data, size); write_calls++; return TRUE;
}
static boolean file_read(struct file_reference *file, unsigned size, void *data) {
    assert(size == sizeof(disk[0])); memcpy(data, disk[file->index], size); return TRUE;
}
static boolean synchronize_metadata_display_name_with_profile_name(int32_t index, game_wchar_t *name) { (void)index; (void)name; return TRUE; }
static void delete_enumerated_saved_game_file(int32_t index) { (void)index; assert(0); }
static game_wchar_t *saved_game_file_get_display_name(int32_t index) { (void)index; return display_name; }
static void ustrncpy(game_wchar_t *dst, const game_wchar_t *src, unsigned count) {
    unsigned i = 0; for (; i < count && src[i]; i++) dst[i] = src[i]; for (; i < count; i++) dst[i] = 0;
}
static boolean thread_has_exited(struct thread_reference *thread) { return thread->complete; }
static void dispose_thread(struct thread_reference *thread) { (void)thread; }
static void create_thread(unsigned stack, uint32_t (*proc)(void *), void *input, struct thread_reference **out) {
    static struct thread_reference complete = {1}; (void)stack; proc(input); *out = &complete;
}
static struct game_variant *build_game_variant_slayer(struct game_variant *variant) {
    memset(variant, 0, sizeof(*variant)); variant->game_engine_index = game_engine_slayer;
    variant->universal_variant.health = 1.0f; return variant;
}
static void game_engine_playlist_next(int32_t a, int32_t b, int32_t c) { (void)a; (void)b; (void)c; }
static void playlist_profile_write(int32_t, struct game_variant *);
/* Minimal editor context; the production dirty comparison accesses only these. */
struct player_profile { word flags; byte unused[46]; };
union edit_data { struct player_profile player; struct game_variant variant; };
static struct { int32_t edit_profile_index; struct { union edit_data current, original; } edit_profile; } player_ui_globals;
static int32_t saved_game_file_get_type(int32_t index) { (void)index; return _saved_game_file_type_game_variant; }
static boolean player_profile_get(int32_t index, struct player_profile *profile) { (void)index; (void)profile; assert(0); return FALSE; }
static void player_profile_save(int32_t index, struct player_profile *profile) { (void)index; (void)profile; assert(0); }
static boolean saved_game_file_get_path_to_enclosing_directory(int32_t index, char *path) { (void)index; (void)path; return FALSE; }
static void saved_game_file_remember_last_used_multiplayer_variant_directory(char *path) { (void)path; assert(0); }
static int32_t playlist_profile_new(short player, game_wchar_t *name) { (void)player; (void)name; return (int32_t)FLAG(_saved_game_file_index_valid_bit) | 2; }
static int ustrncmp(const game_wchar_t *left, const game_wchar_t *right, unsigned count) {
    for (unsigned i=0;i<count;i++) { if (left[i]!=right[i]) return left[i]<right[i] ? -1 : 1; if (!left[i]) return 0; } return 0;
}
struct widget_instance { struct widget_instance *parent; short type; struct { short selected_index; } data3C; };
struct event_record { short type; };
static struct game_variant *player_ui_get_edit_playlist_profile(void) {
    return player_ui_globals.edit_profile_index==NONE ? NULL : &player_ui_globals.edit_profile.current.variant;
}
/* PRODUCTION FUNCTIONS */
'''


HARNESS = r'''
static void format_and_default(void) {
    const unsigned offsets[] = {29,30,31,41,42,43};
    struct game_variant legacy, edited;
    memset(&legacy, 0, sizeof(legacy));
    assert(sizeof(legacy) == 104 && offsetof(struct game_variant, flags) == 100);
    assert(offsetof(struct game_variant, universal_variant.pad0) == offsets[0]);
    assert(offsetof(struct game_variant, universal_variant.pad1) == offsets[1]);
    assert(offsetof(struct game_variant, universal_variant.pad2) == offsets[2]);
    assert(offsetof(struct game_variant, universal_variant.pad4) == offsets[3]);
    assert(offsetof(struct game_variant, universal_variant.pad5) == offsets[4]);
    assert(offsetof(struct game_variant, universal_variant.pad6) == offsets[5]);
    assert(_performance_option_match_timer == 1 && _performance_option_spawn_markers == 2 &&
        _performance_option_timer_audio == 4 && _performance_option_silent_movement == 8 &&
        _performance_option_silent_weapon_ready == 16 && PERFORMANCE_PRACTICE_FLAGS == 7 && PERFORMANCE_OPTIONS_MASK == 31);
    assert(performance_variant_get_flags(NULL) == 0);
    performance_variant_set_flags(NULL, 3);
    edited = legacy; performance_variant_set_flags(&edited, 0);
    assert(!memcmp(&legacy, &edited, sizeof(legacy)));
    for (unsigned flags = 1; flags <= 31; flags++) {
        memset(&legacy, 0x5a, sizeof(legacy)); edited = legacy;
        performance_variant_set_flags(&edited, flags);
        assert(performance_variant_get_flags(&edited) == flags);
        for (unsigned i = 0; i < sizeof(edited); i++) {
            boolean extension = FALSE;
            for (unsigned n = 0; n < NUMBEROF(offsets); n++) if (i == offsets[n]) extension = TRUE;
            if (!extension) assert(((byte *)&legacy)[i] == ((byte *)&edited)[i]);
        }
        assert(edited.universal_variant.pad0 == 'P' && edited.universal_variant.pad1 == 'F');
        assert(edited.universal_variant.pad2 == 'O' && edited.universal_variant.pad4 == 1);
        assert(edited.universal_variant.pad5 == flags && edited.universal_variant.pad6 == (flags ^ 0xA5));
        for (unsigned n = 0; n < NUMBEROF(offsets); n++) {
            for (unsigned bit = 0; bit < 8; bit++) {
                struct game_variant damaged = edited;
                ((byte *)&damaged)[offsets[n]] ^= 1u << bit;
                assert(performance_variant_get_flags(&damaged) == 0);
            }
        }
    }
    edited.universal_variant.pad4 = 2; assert(performance_variant_get_flags(&edited) == 0);
    performance_variant_set_flags(&edited, 3);
    edited.universal_variant.pad5 = 32; edited.universal_variant.pad6 = 32 ^ 0xA5;
    assert(performance_variant_get_flags(&edited) == 0);
    performance_variant_set_flags(&edited, 32); assert(performance_variant_get_flags(&edited) == 0);
    for (unsigned n = 0; n < NUMBEROF(offsets); n++) assert(((byte *)&edited)[offsets[n]] == 0);
    for (unsigned padding = 0; padding < 256; padding++) {
        memset(&legacy, padding, sizeof(legacy)); edited = legacy;
        assert(performance_variant_get_flags(&legacy) == 0);
        assert(!memcmp(&edited, &legacy, sizeof(legacy)));
    }
}

static void persistence(void) {
    struct game_variant original, loaded, copy;
    const int32_t profile0 = (int32_t)FLAG(_saved_game_file_index_valid_bit);
    for (unsigned flags = 0; flags <= 31; flags++) {
        build_game_variant_slayer(&original);
        original.human_readable_game_description[0] = 'A';
        original.universal_variant.score_to_win = 25;
        performance_variant_set_flags(&original, flags);
        playlist_profile_save(profile0, &original);
        memset(&loaded, 0xcc, sizeof(loaded));
        assert(playlist_profile_get(profile0, &loaded));
        assert(!memcmp(&original, &loaded, sizeof(original)));
        assert(performance_variant_get_flags(&loaded) == flags);
        selected_file = 0; assert(playlist_profile_get_from_path("fixture", &loaded));
        assert(!memcmp(&original, &loaded, sizeof(original)));
        /* Copy, rename, save-as, reload; saving another type cannot change it. */
        copy = loaded; copy.human_readable_game_description[0] = 'B';
        playlist_profile_save(profile0 | 1, &copy);
        selected_file = 1; assert(playlist_profile_get_from_path("copy", &loaded));
        assert(!memcmp(&copy, &loaded, sizeof(copy)));
        assert(performance_variant_get_flags(&loaded) == flags);
        performance_variant_set_flags(&loaded, flags ^ 31);
        playlist_profile_save(profile0 | 2, &loaded);
        assert(playlist_profile_get(profile0 | 1, &loaded));
        assert(performance_variant_get_flags(&loaded) == flags);
    }
    /* A damaged checksum falls back to a stock variant through indexed reads. */
    disk[0][42] ^= 1;
    assert(playlist_profile_get(profile0, &loaded));
    assert(performance_variant_get_flags(&loaded) == 0);
    selected_file = 0; assert(!playlist_profile_get_from_path("damaged", &loaded));
    /* Even a valid save signature cannot turn an unknown extension on. */
    disk[1][41] = 2;
    saved_game_file_generate_checksum(disk[1], 104, (XCALCSIG_SIGNATURE *)(disk[1] + 104));
    assert(playlist_profile_get(profile0 | 1, &loaded));
    assert(performance_variant_get_flags(&loaded) == 0);
    assert(write_calls == 96 && checksum_calls > write_calls);
}

static void editor_dirty(void) {
    player_ui_globals.edit_profile_index = 0;
    build_game_variant_slayer(&player_ui_globals.edit_profile.original.variant);
    player_ui_globals.edit_profile.current = player_ui_globals.edit_profile.original;
    assert(!player_ui_edit_profile_is_dirty());
    performance_variant_set_flags(&player_ui_globals.edit_profile.current.variant, 3);
    assert(player_ui_edit_profile_is_dirty());
    performance_variant_set_flags(&player_ui_globals.edit_profile.current.variant, 0);
    assert(!player_ui_edit_profile_is_dirty());
    player_ui_globals.edit_profile.current.variant.flags = 0xabcd;
    assert(!player_ui_edit_profile_is_dirty());
}

static void editor_save_and_cancel(void) {
    struct game_variant original, loaded;
    const int32_t profile=(int32_t)FLAG(_saved_game_file_index_valid_bit);
    build_game_variant_slayer(&original);
    playlist_profile_save(profile,&original);
    player_ui_begin_editing_profile(profile);
    performance_variant_set_flags(&player_ui_globals.edit_profile.current.variant,7);
    assert(player_ui_edit_profile_is_dirty());
    player_ui_end_editing_profile();
    assert(player_ui_globals.edit_profile_index==NONE);
    assert(playlist_profile_get(profile,&loaded) && performance_variant_get_flags(&loaded)==0);
    player_ui_begin_editing_profile(profile);
    assert(performance_variant_get_flags(&player_ui_globals.edit_profile.current.variant)==0);
    performance_variant_set_flags(&player_ui_globals.edit_profile.current.variant,4);
    assert(player_ui_save_profile() && player_ui_globals.edit_profile_index==NONE);
    assert(playlist_profile_get(profile,&loaded) && performance_variant_get_flags(&loaded)==4);
    /* The default-type rename/save-as path must retain the new flags too. */
    player_ui_begin_editing_profile(profile | FLAG(_saved_game_file_index_read_only_bit));
    performance_variant_set_flags(&player_ui_globals.edit_profile.current.variant,7);
    player_ui_globals.edit_profile.current.variant.human_readable_game_description[0]='C';
    assert(player_ui_save_profile());
    assert(playlist_profile_get(profile | 2,&loaded) && performance_variant_get_flags(&loaded)==7);
    assert(loaded.human_readable_game_description[0]=='C');
    assert(playlist_profile_get(profile,&loaded) && performance_variant_get_flags(&loaded)==4);
}

static void selecting_game_engine(void) {
    const int engines[]={game_engine_ctf,game_engine_king,game_engine_slayer,game_engine_oddball,game_engine_race};
    const int32_t profile=(int32_t)FLAG(_saved_game_file_index_valid_bit);
    struct widget_instance list={0}, item={0};
    struct event_record event={0};
    boolean deleted=FALSE;
    struct game_variant original,loaded;
    list.type=3; item.parent=&list;
    for (unsigned flags=0;flags<=31;flags++) {
        build_game_variant_slayer(&original);
        playlist_profile_save(profile,&original);
        player_ui_begin_editing_profile(profile);
        performance_variant_set_flags(player_ui_get_edit_playlist_profile(),flags);
        /* The Step 1 choices reset only mode-specific rules, including when
         * revisiting a prior mode; every practice choice must survive. */
        for (unsigned selection=0;selection<sizeof(engines)/sizeof(engines[0]);selection++) {
            list.data3C.selected_index=(short)selection;
            assert(playlist_profile_set_game_engine(&item,&event,&deleted));
            assert(player_ui_get_edit_playlist_profile()->game_engine_index==engines[selection]);
            assert(performance_variant_get_flags(player_ui_get_edit_playlist_profile())==flags);
        }
        assert(player_ui_save_profile());
        assert(playlist_profile_get(profile,&loaded));
        assert(loaded.game_engine_index==game_engine_race && performance_variant_get_flags(&loaded)==flags);
    }
}

int main(void) { format_and_default(); persistence(); editor_dirty(); editor_save_and_cancel(); selecting_game_engine(); return 0; }
'''


class PerformanceVariantsTest(unittest.TestCase):
    def test_real_variant_and_playlist_flow(self):
        engine = (ROOT / "source/game/game_engine.h").read_text()
        playlist = (ROOT / "source/saved games/playlist_profile.c").read_text()
        playlist_private = playlist[playlist.index("/* ---------- private code */"):]
        declarations = "\n".join(block(engine, signature) + ";" for signature in (
            "struct universal_variant\n", "struct ctf_variant\n", "struct slayer_variant\n",
            "struct king_variant\n", "struct oddball_variant\n", "struct race_variant\n",
            "union game_engine_variant\n", "struct game_variant\n"))
        playlist_declarations = "\n".join(block(playlist, signature) + ";" for signature in (
            "struct playlist_profile_write_request\n", "struct playlist_profile_runtime_globals_prefix\n"))
        functions = [block((ROOT / "source/game/game_engine.c").read_text(), "void game_engine_variant_cleanup(\n")]
        functions += [block(playlist_private, name) for name in (
            "static boolean playlist_profile_read(\n",
            "static unsigned long __stdcall playlist_profile_write_thread_proc(\n",
            "static void playlist_profile_write(\n")]
        functions += [block(playlist, name) for name in (
            "boolean playlist_profile_get_from_path(\n", "boolean playlist_profile_get(\n", "void playlist_profile_save(\n")]
        player_ui = (ROOT / "source/interface/player_ui.c").read_text()
        functions += [block(player_ui[player_ui.index("/* ---------- private code */"):], "static void clear_profile_edit_data(\n")]
        functions += [block(player_ui, name) for name in (
            "boolean player_ui_edit_profile_is_dirty(\n", "void player_ui_begin_editing_profile(\n",
            "void player_ui_end_editing_profile(\n", "boolean player_ui_save_profile(\n")]
        handlers = (ROOT / "source/interface/ui_widget_event_handler_functions.c").read_text()
        functions += [block(handlers[handlers.index("/* ---------- private code */"):], "static boolean playlist_profile_set_game_engine(\n")]
        generated = PREFIX.replace("/* VARIANT DECLARATIONS */", declarations)
        generated = generated.replace("/* PLAYLIST DECLARATIONS */", playlist_declarations)
        generated = generated.replace("/* PRODUCTION FUNCTIONS */", "\n".join(functions))
        generated = re.sub(r"\bunsigned long\b", "uint32_t", generated)
        generated = re.sub(r"\blong\b", "int32_t", generated)
        generated = re.sub(r"\bwchar_t\b", "game_wchar_t", generated) + HARNESS
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "variants.c"
            executable = Path(directory) / "variants"
            fixture.write_text(generated)
            subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter",
                            "-I", str(ROOT / "source"), str(fixture), "-o", str(executable)], check=True)
            subprocess.run([str(executable)], check=True)


if __name__ == "__main__":
    unittest.main()
