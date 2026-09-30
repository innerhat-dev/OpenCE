"""Compile the real binding/config code and exercise its Xbox packet and console queue."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]
PORT = ROOT / "port/linux/src"
SDL = Path(os.environ.get("HALO_MACOS_SDL_PREFIX", "/opt/homebrew/opt/sdl3"))

# Only the Xbox declarations and logging are stubbed. Config, TOML parsing,
# controller mapping and SDL keyboard translation use their production code.
PREFIX = r'''
#define __HALO_LINUX_PLATFORM_H
#include <stdint.h>
#include <pthread.h>
#include <stdio.h>
#include <stdarg.h>
typedef int BOOL;
typedef unsigned char BYTE;
typedef char CHAR;
typedef short SHORT;
#define TRUE 1
#define FALSE 0
typedef struct {
    unsigned short wButtons;
    BYTE bAnalogButtons[8];
    SHORT sThumbLX, sThumbLY, sThumbRX, sThumbRY;
} XINPUT_GAMEPAD;
void platform_log(const char *, ...);
'''

HARNESS = r'''
#include <assert.h>
#include <stdlib.h>
#include <string.h>
#include <SDL3/SDL.h>
#include "sdl_platform.h"
#include "input_bindings.h"
#include "port_config.h"
void platform_log(const char *format, ...) {
    va_list args; va_start(args, format); vfprintf(stderr, format, args);
    fputc('\n', stderr); va_end(args);
}
static Uint64 ticks = 100, wheel_press_until_ms;
Uint64 SDL_GetTicks(void) { return ticks; }
#ifndef HALO_ANDROID
const char *SDL_GetBasePath(void) {
    static char path[1024]; snprintf(path, sizeof(path), "%s/", getenv("HALO_SAVE_ROOT")); return path;
}
void *SDL_LoadFile(const char *path, size_t *size) {
    FILE *file = fopen(path, "rb");
    if (!file) return NULL;
    assert(!fseek(file, 0, SEEK_END)); long length = ftell(file); assert(length >= 0);
    rewind(file); void *data = malloc((size_t)length + 1); assert(data);
    assert(fread(data, 1, (size_t)length, file) == (size_t)length); fclose(file);
    *size = (size_t)length; return data;
}
bool SDL_SaveFile(const char *path, const void *data, size_t size) {
    FILE *file = fopen(path, "wb"); if (!file) return false;
    bool written = fwrite(data, 1, size, file) == size; return fclose(file) == 0 && written;
}
void SDL_free(void *data) { free(data); }
#endif
static BYTE analog(BOOL down) { return down ? 0xff : 0; }
#define KEYSTROKE_QUEUE_SIZE 64
static struct platform_keystroke keystroke_queue[KEYSTROKE_QUEUE_SIZE];
static unsigned long keystroke_head, keystroke_count;
static pthread_mutex_t input_lock = PTHREAD_MUTEX_INITIALIZER;
/* PRODUCTION_CODE */

static XINPUT_GAMEPAD press(SDL_Scancode key) {
    struct platform_input_state input = {0};
    XINPUT_GAMEPAD pad = {0};
    input.keys[key] = 1; keyboard_gamepad(&input, &pad); return pad;
}
static void console_event(SDL_Scancode key, BYTE expected) {
    SDL_KeyboardEvent event = {0};
    struct platform_keystroke stroke;
    event.scancode = key; event.key = key == SDL_SCANCODE_GRAVE ? SDLK_GRAVE : SDLK_F2;
    event.down = true; queue_keystroke(&event);
    assert(platform_next_keystroke(&stroke)); assert(stroke.virtual_key == expected);
    event.down = false; queue_keystroke(&event);
    assert(platform_next_keystroke(&stroke)); assert(stroke.virtual_key == expected);
    assert(stroke.flags & 0x40);
}
int main(int argc, char **argv) {
    struct input_binding parsed;
    struct platform_input_state input = {0};
    XINPUT_GAMEPAD pad;
    const char *mode = argc > 1 ? argv[1] : "default";
    if (!strcmp(mode, "parser")) {
        assert(input_binding_parse(" e, Left Ctrl, Right_Shift, `, F24, Keypad9, Mouse Right, Wheel ", &parsed));
        assert(parsed.keys[SDL_SCANCODE_E] && parsed.keys[SDL_SCANCODE_LCTRL]);
        assert(!parsed.keys[SDL_SCANCODE_RCTRL] && parsed.keys[SDL_SCANCODE_RSHIFT]);
        assert(parsed.keys[SDL_SCANCODE_GRAVE] && parsed.keys[SDL_SCANCODE_F24]);
        assert(parsed.keys[SDL_SCANCODE_KP_9] && parsed.mouse_buttons == (1U << SDL_BUTTON_RIGHT) && parsed.wheel);
        assert(input_binding_parse("ctrl, shift, alt, cmd", &parsed));
        assert(parsed.keys[SDL_SCANCODE_RCTRL] && parsed.keys[SDL_SCANCODE_LSHIFT]);
        assert(parsed.keys[SDL_SCANCODE_RALT] && parsed.keys[SDL_SCANCODE_RGUI]);
        assert(input_binding_parse("  ", &parsed) && !parsed.keys[SDL_SCANCODE_E]);
        assert(!input_binding_parse("E, unknown", &parsed) && !parsed.keys[SDL_SCANCODE_E]);
        assert(!input_binding_parse("E,", &parsed));
        assert(!input_binding_parse("F25", &parsed));
        assert(!input_binding_parse("F1junk", &parsed));
        assert(!input_binding_parse("Keypad10", &parsed));
        return 0;
    }
    if (!strcmp(mode, "custom")) {
        assert(press(SDL_SCANCODE_T).bAnalogButtons[XINPUT_GAMEPAD_X] == 255);
        assert(!press(SDL_SCANCODE_E).bAnalogButtons[XINPUT_GAMEPAD_X]);
        assert(press(SDL_SCANCODE_CAPSLOCK).wButtons == XINPUT_GAMEPAD_BACK);
        assert(!press(SDL_SCANCODE_GRAVE).wButtons);
        assert(!press(SDL_SCANCODE_Q).bAnalogButtons[XINPUT_GAMEPAD_Y]);
        assert(press(SDL_SCANCODE_RALT).wButtons == XINPUT_GAMEPAD_LEFT_THUMB);
        assert(!press(SDL_SCANCODE_LSHIFT).wButtons);
        assert(press(SDL_SCANCODE_RCTRL).wButtons == XINPUT_GAMEPAD_RIGHT_THUMB);
        assert(!press(SDL_SCANCODE_LCTRL).wButtons);
        console_event(SDL_SCANCODE_F3, 0xc0);
        console_event(SDL_SCANCODE_GRAVE, 0);
        /* Console binding wins even if the same key is also assigned X. */
        assert(!press(SDL_SCANCODE_F3).bAnalogButtons[XINPUT_GAMEPAD_X]);
        wheel_press_until_ms = 200; pad = (XINPUT_GAMEPAD){0};
        keyboard_gamepad(&input, &pad); assert(!pad.bAnalogButtons[XINPUT_GAMEPAD_Y]);
        assert(input_binding_matches_key(_binding_release_mouse, SDL_SCANCODE_F4));
        assert(!input_binding_matches_key(_binding_release_mouse, SDL_SCANCODE_F12));
        return 0;
    }
    if (!strcmp(mode, "legacy")) {
        assert(press(SDL_SCANCODE_TAB).bAnalogButtons[XINPUT_GAMEPAD_Y] == 255);
        assert(press(SDL_SCANCODE_Q).bAnalogButtons[XINPUT_GAMEPAD_WHITE] == 255);
        assert(press(SDL_SCANCODE_LCTRL).wButtons == XINPUT_GAMEPAD_LEFT_THUMB);
        console_event(SDL_SCANCODE_GRAVE, 0xc0);
        return 0;
    }
    assert(press(SDL_SCANCODE_E).bAnalogButtons[XINPUT_GAMEPAD_X] == 255);
    assert(press(SDL_SCANCODE_Q).bAnalogButtons[XINPUT_GAMEPAD_Y] == 255);
    assert(!press(SDL_SCANCODE_Q).bAnalogButtons[XINPUT_GAMEPAD_WHITE]);
    assert(press(SDL_SCANCODE_TAB).wButtons == XINPUT_GAMEPAD_START);
    assert(!press(SDL_SCANCODE_TAB).bAnalogButtons[XINPUT_GAMEPAD_Y]);
    assert(press(SDL_SCANCODE_GRAVE).wButtons == XINPUT_GAMEPAD_BACK);
    assert(press(SDL_SCANCODE_F1).wButtons == XINPUT_GAMEPAD_BACK);
    assert(press(SDL_SCANCODE_LCTRL).wButtons == XINPUT_GAMEPAD_RIGHT_THUMB);
    assert(press(SDL_SCANCODE_RCTRL).wButtons == XINPUT_GAMEPAD_RIGHT_THUMB);
    assert(press(SDL_SCANCODE_LSHIFT).wButtons == XINPUT_GAMEPAD_LEFT_THUMB);
    assert(press(SDL_SCANCODE_RSHIFT).wButtons == XINPUT_GAMEPAD_LEFT_THUMB);
    assert(press(SDL_SCANCODE_SPACE).bAnalogButtons[XINPUT_GAMEPAD_A] == 255);
    assert(press(SDL_SCANCODE_F).bAnalogButtons[XINPUT_GAMEPAD_B] == 255);
    console_event(SDL_SCANCODE_GRAVE, 0); console_event(SDL_SCANCODE_F2, 0xc0);
    assert(input_binding_matches_key(_binding_release_mouse, SDL_SCANCODE_F12));
    /* Held Select persists until released, then leaves no latched button. */
    input.keys[SDL_SCANCODE_GRAVE] = 1;
    for (int n = 0; n < 3; n++) {
        pad = (XINPUT_GAMEPAD){0}; keyboard_gamepad(&input, &pad);
        assert(pad.wButtons == XINPUT_GAMEPAD_BACK);
    }
    input.keys[SDL_SCANCODE_GRAVE] = 0;
    pad = (XINPUT_GAMEPAD){0}; keyboard_gamepad(&input, &pad); assert(!pad.wButtons);
    input.keys[SDL_SCANCODE_W] = input.keys[SDL_SCANCODE_D] = 1;
    pad = (XINPUT_GAMEPAD){0}; keyboard_gamepad(&input, &pad);
    assert(pad.sThumbLX > 23000 && pad.sThumbLX < 24000 && pad.sThumbLX == pad.sThumbLY);
    input.keys[SDL_SCANCODE_A] = 1;
    pad = (XINPUT_GAMEPAD){0}; keyboard_gamepad(&input, &pad); assert(!pad.sThumbLX);
    memset(&input, 0, sizeof(input)); input.mouse_buttons[SDL_BUTTON_LEFT] = 1;
    pad = (XINPUT_GAMEPAD){0}; keyboard_gamepad(&input, &pad);
    assert(pad.bAnalogButtons[XINPUT_GAMEPAD_RIGHT_TRIGGER] == 255);
    input.mouse_released = true; wheel_press_until_ms = 200;
    pad = (XINPUT_GAMEPAD){0}; keyboard_gamepad(&input, &pad);
    assert(!pad.bAnalogButtons[XINPUT_GAMEPAD_RIGHT_TRIGGER] && !pad.bAnalogButtons[XINPUT_GAMEPAD_Y]);
    input.mouse_released = false;
    pad = (XINPUT_GAMEPAD){0}; keyboard_gamepad(&input, &pad); assert(pad.bAnalogButtons[XINPUT_GAMEPAD_Y] == 255);
    ticks = 201;
    pad = (XINPUT_GAMEPAD){0}; keyboard_gamepad(&input, &pad); assert(!pad.bAnalogButtons[XINPUT_GAMEPAD_Y]);
    return 0;
}
'''


@unittest.skipUnless(shutil.which("clang") and (SDL / "include/SDL3/SDL.h").exists(), "clang and SDL3 headers required")
class InputBindings(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.directory = Path(cls.temporary.name)
        constants = (ROOT / "port/include/xdk/xdk_xbox.h").read_text()
        constants = "\n".join(re.findall(r"^#define XINPUT_GAMEPAD_.*$", constants, re.M))
        (cls.directory / "prefix.h").write_text(PREFIX + constants + "\n")
        xinput = (PORT / "xinput_sdl.c").read_text()
        controller = xinput.split("static void keyboard_gamepad(", 1)[1].split("/* A scroll", 1)[0]
        controller = "static void keyboard_gamepad(" + controller
        platform = (PORT / "sdl_platform.c").read_text()
        translation = platform.split("/* ---------- keyboard translation */", 1)[1].split("/* ---------- internet play", 1)[0]
        (cls.directory / "probe.c").write_text(HARNESS.replace("/* PRODUCTION_CODE */", controller + translation))
        cls.executables = {}
        for target, defines in (("mac", ["-DHALO_ANDROID=1", "-DHALO_MACOS=1"]),
                                ("other", ["-DHALO_ANDROID=1"]), ("desktop", [])):
            executable = cls.directory / target
            command = ["clang", "-std=gnu11", "-O2", "-Wall", "-Wextra", "-Werror", "-pthread",
                       *defines, "-include", str(cls.directory / "prefix.h"),
                       f"-I{PORT}", f"-I{SDL / 'include'}", f"-I{ROOT / 'port/third_party/tomlc17'}",
                       str(cls.directory / "probe.c"), str(PORT / "input_bindings.c"), str(PORT / "port_config.c"),
                       str(ROOT / "port/third_party/tomlc17/tomlc17.c"), "-o", str(executable)]
            compiled = subprocess.run(command, text=True, capture_output=True, timeout=30)
            if compiled.returncode:
                raise AssertionError(compiled.stderr)
            cls.executables[target] = executable

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def run_probe(self, mode="default", config=None, target="mac"):
        with tempfile.TemporaryDirectory(dir=self.directory) as folder:
            folder = Path(folder)
            path = folder / "config.toml"
            if config is not None:
                path.write_text(config)
            environment = {k: v for k, v in os.environ.items() if not k.startswith("HALO_")}
            environment.update(HALO_SAVE_ROOT=str(folder), HALO_DATA_ROOT=str(folder))
            tested = subprocess.run([str(self.executables[target]), mode], env=environment,
                                    text=True, capture_output=True, timeout=5)
            self.assertEqual(tested.returncode, 0, tested.stderr)
            return path.read_text() if path.exists() else "", tested.stderr

    def test_parser_names_and_rejected_partial_bindings(self):
        self.run_probe("parser")

    def test_mac_defaults_packets_holds_console_and_mouse(self):
        config, _ = self.run_probe()
        bindings = tomllib.loads(config)["bindings"]
        self.assertEqual(bindings["select"], "Grave, F1")
        self.assertEqual(bindings["zoom"], "Ctrl, MouseMiddle")

    def test_custom_bindings_disable_old_keys_and_wheel(self):
        self.run_probe("custom", '''[bindings]
x = "T, F3"
y = ""
select = "CapsLock"
crouch = "RightAlt"
zoom = "RightCtrl"
console = "F3"
release_mouse = "F4"
''')

    def test_invalid_values_fall_back_without_partial_bindings(self):
        _, log = self.run_probe(config='''[bindings]
a = "NoSuchKey"
zoom = "Ctrl, NoSuchKey"
start = "BadKey"
crouch = false
console = "MouseLeft"
release_mouse = "Wheel"
''')
        self.assertIn("bindings.zoom: invalid binding", log)
        self.assertIn("bindings.crouch should be a quoted string", log)
        self.assertIn("bindings.console: invalid binding", log)

    def test_existing_config_keeps_comments_and_values(self):
        original = '# My local settings\n[audio]\nvolume = 0.25 # keep\n[bindings]\nx = "E" # mine\n[custom]\nmarker = "preserve"\n'
        config, _ = self.run_probe(config=original)
        self.assertIn('# My local settings', config)
        self.assertIn('volume = 0.25 # keep', config)
        self.assertIn('x = "E" # mine', config)
        parsed = tomllib.loads(config)
        self.assertEqual(parsed["custom"]["marker"], "preserve")
        self.assertEqual(parsed["bindings"]["console"], "F2")

    def test_other_native_ports_keep_their_keyboard_defaults(self):
        config, _ = self.run_probe("legacy", target="other")
        self.assertEqual(tomllib.loads(config)["bindings"]["y"], "Tab, Wheel")

    def test_desktop_config_only_bindings_write_valid_defaults(self):
        config, _ = self.run_probe("legacy", target="desktop")
        self.assertEqual(tomllib.loads(config)["bindings"]["console"], "Grave")


if __name__ == "__main__":
    unittest.main()
