"""Exercise the production Mac SDL event state with authored input events.

No window, game, clipboard, user preferences, or native app is opened.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.test_input_bindings import PREFIX, ROOT, PORT, SDL


HARNESS = r'''
#include <assert.h>
#include <stdlib.h>
#include <string.h>
#include <SDL3/SDL.h>
#include "sdl_platform.h"
#include "input_bindings.h"
#include "native_input_events.h"

static SDL_Window *platform_window = (SDL_Window *)1;
static SDL_ThreadID platform_event_thread = 1;
static struct platform_input_state input_state;
static unsigned char keys_pressed[SDL_SCANCODE_COUNT];
static struct platform_ui_pointer ui_pointer;
static float ui_pointer_wheel;
static pthread_mutex_t input_lock = PTHREAD_MUTEX_INITIALIZER;
#define KEYSTROKE_QUEUE_SIZE 64
static struct platform_keystroke keystroke_queue[KEYSTROKE_QUEUE_SIZE];
static unsigned long keystroke_head, keystroke_count;
static int captured, console_open, capture_fails;
static SDL_Event events[16];
static int event_count, event_next;

void platform_log(const char *format, ...) { (void)format; }
unsigned char console_is_active(void) { return console_open; }
const char *config_string(const char *name) {
#define BINDING(action, mac, other, comment) if (!strcmp(name, "bindings." #action)) return mac;
#include "input_bindings.def"
#undef BINDING
    return "";
}
double config_real(const char *name) { (void)name; return 0; }
Uint64 SDL_GetTicks(void) { return 100; }
SDL_ThreadID SDL_GetCurrentThreadID(void) { return 1; }
const char *SDL_GetError(void) { return "authored failure"; }
bool SDL_SetWindowRelativeMouseMode(SDL_Window *window, bool enabled) {
    (void)window;
    if (enabled && capture_fails) return false;
    captured = enabled;
    return true;
}
bool SDL_GetWindowSize(SDL_Window *window, int *w, int *h) {
    (void)window; *w = 800; *h = 600; return true;
}
void SDL_WarpMouseInWindow(SDL_Window *window, float x, float y) {
    (void)window; (void)x; (void)y;
}
bool SDL_PollEvent(SDL_Event *event) {
    if (event_next == event_count) return false;
    *event = events[event_next++]; return true;
}
SDL_Gamepad *SDL_OpenGamepad(SDL_JoystickID id) { (void)id; return NULL; }
static void platform_show_pending_message(void) {}
static void platform_invite_clipboard(BOOL look) { (void)look; }

/* PRODUCTION_CODE */

static void pump(SDL_Event event) {
    event_next = 0; event_count = 1; events[0] = event;
    platform_pump_events();
}
static void key(SDL_Scancode scancode, int down, int repeat) {
    SDL_Event event = {0}; event.type = down ? SDL_EVENT_KEY_DOWN : SDL_EVENT_KEY_UP;
    event.key.scancode = scancode; event.key.down = down; event.key.repeat = repeat;
    event.key.key = scancode == SDL_SCANCODE_ESCAPE ? SDLK_ESCAPE : SDLK_W;
    pump(event);
}
static struct platform_input_state snapshot(void) {
    struct platform_input_state result; platform_input_read(&result, TRUE); return result;
}
static void click(int down) {
    SDL_Event event = {0}; event.type = down ? SDL_EVENT_MOUSE_BUTTON_DOWN : SDL_EVENT_MOUSE_BUTTON_UP;
    event.button.button = SDL_BUTTON_LEFT; event.button.down = down;
    event.button.x = 321; event.button.y = 234; pump(event);
}
int main(void) {
    struct platform_input_state state;
    struct platform_ui_pointer pointer;
    input_state.focused = TRUE;
    platform_mouse_resume_gameplay(); assert(captured);
    key(SDL_SCANCODE_W, 1, 0); click(1);
    key(SDL_SCANCODE_ESCAPE, 1, 0);
    state = snapshot(); assert(state.pause_pressed && state.mouse_released && !captured);
    assert(!state.keys[SDL_SCANCODE_W] && !state.mouse_buttons[SDL_BUTTON_LEFT]);
    assert(!snapshot().pause_pressed);
    key(SDL_SCANCODE_ESCAPE, 1, 1); assert(!snapshot().pause_pressed);
    key(SDL_SCANCODE_ESCAPE, 0, 0);

    platform_ui_pointer_set_active(TRUE); assert(!captured);
    key(SDL_SCANCODE_ESCAPE, 1, 0);
    state = snapshot(); assert(state.menu_back_pressed && !state.pause_pressed && state.mouse_released);
    key(SDL_SCANCODE_ESCAPE, 0, 0);
    click(1); assert(platform_ui_pointer_read(&pointer));
    assert(pointer.left_clicks == 1 && pointer.click_x == 321 && pointer.click_y == 234);
    assert(!snapshot().mouse_buttons[SDL_BUTTON_LEFT]);
    platform_ui_pointer_set_active(FALSE); assert(!captured);

    /* Focus alone does not resume; the first gameplay click is consumed. */
    SDL_Event focus = {.type = SDL_EVENT_WINDOW_FOCUS_GAINED}; pump(focus); assert(!captured);
    click(1); state = snapshot(); assert(captured && !state.mouse_released);
    assert(!state.mouse_buttons[SDL_BUTTON_LEFT]);
    click(0); click(1); assert(snapshot().mouse_buttons[SDL_BUTTON_LEFT]);
    key(SDL_SCANCODE_W, 1, 0);
    SDL_Event native = {.type = SDL_EVENT_USER}; native.user.code = HALO_NATIVE_MOUSE_RELEASE;
    pump(native); state = snapshot(); assert(!captured && state.mouse_released);
    assert(!state.keys[SDL_SCANCODE_W] && !state.mouse_buttons[SDL_BUTTON_LEFT]);

    /* Explicit Resume is allowed to capture only after its menu closes. */
    platform_ui_pointer_set_active(TRUE); platform_mouse_resume_gameplay(); assert(!captured);
    platform_ui_pointer_set_active(FALSE); assert(captured);
    key(SDL_SCANCODE_W, 1, 1); assert(!snapshot().keys[SDL_SCANCODE_W]);
    key(SDL_SCANCODE_W, 0, 0); key(SDL_SCANCODE_W, 1, 0);
    assert(snapshot().keys[SDL_SCANCODE_W]);
    SDL_Event lost = {.type = SDL_EVENT_WINDOW_FOCUS_LOST}; pump(lost);
    assert(!captured && !snapshot().keys[SDL_SCANCODE_W]);
    pump(focus); assert(!captured);

    /* Escape still opens pause after F12 has already released the cursor. */
    platform_mouse_resume_gameplay(); key(SDL_SCANCODE_F12, 1, 0); assert(!captured);
    key(SDL_SCANCODE_ESCAPE, 1, 0); assert(snapshot().pause_pressed);
    key(SDL_SCANCODE_ESCAPE, 0, 0);
    console_open = 1; key(SDL_SCANCODE_ESCAPE, 1, 0);
    state = snapshot(); assert(!state.pause_pressed && !state.menu_back_pressed);
    struct platform_keystroke stroke;
    assert(platform_next_keystroke(&stroke) && stroke.virtual_key == 0x1b);
    console_open = 0;

    capture_fails = 1; platform_mouse_resume_gameplay();
    assert(snapshot().mouse_released && !captured);
    puts("Mac input transitions passed");
    return 0;
}
'''


class MacInput(unittest.TestCase):
    def test_live_video_reads_and_display_failure(self):
        source = (PORT / "sdl_platform.c").read_text()
        video = "int halo_interpolation_enabled(" + source.split("int halo_interpolation_enabled(", 1)[1].split(
            "#ifndef HALO_ANDROID\n/* whether the window", 1)[0]
        harness = r'''
#include <assert.h>
#include <SDL3/SDL.h>
static SDL_Window *platform_window = (SDL_Window *)1;
static SDL_GLContext platform_gl_context = (SDL_GLContext)1;
static int smooth, vsync = 1, fullscreen, display_fails, last_interval = -1, reset_count;
int config_boolean(const char *name) { return !strcmp(name, "display.vsync") ? vsync : smooth; }
int host_sdl_video_fullscreen(unsigned int window, int enabled) {
    assert(window == 1);
    if (enabled < 0) return fullscreen;
    if (display_fails) return 0;
    fullscreen = enabled; return 1;
}
bool SDL_GL_SetSwapInterval(int interval) {
    if (display_fails) return false;
    last_interval = interval; return true;
}
void render_interpolation_reset(void) { reset_count++; }
/* PRODUCTION_CODE */
int main(void) {
    assert(!halo_interpolation_enabled()); smooth = 1; assert(halo_interpolation_enabled());
    smooth = 0; assert(!halo_interpolation_enabled());
    assert(!halo_video_fullscreen_get()); assert(halo_video_fullscreen_set(1));
    assert(halo_video_fullscreen_get()); assert(halo_video_fullscreen_set(0));
    assert(!halo_video_fullscreen_get());
    assert(halo_video_apply_settings() && last_interval == 1 && reset_count == 1);
    vsync = 0; assert(halo_video_apply_settings() && last_interval == 0 && reset_count == 2);
    display_fails = 1;
    assert(!halo_video_fullscreen_set(1) && !halo_video_fullscreen_get());
    vsync = 1; assert(!halo_video_apply_settings() && last_interval == 0 && reset_count == 2);
    platform_window = NULL; assert(!halo_video_fullscreen_set(1) && !halo_video_fullscreen_get());
    platform_gl_context = NULL; assert(!halo_video_apply_settings());
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "probe.c").write_text(harness.replace("/* PRODUCTION_CODE */", video))
            executable = directory / "probe"
            compiled = subprocess.run(["clang", "-std=gnu11", "-O2", "-Wall", "-Wextra", "-Werror",
                "-Wno-pointer-to-int-cast", "-DHALO_ANDROID=1", "-DHALO_MACOS=1", f"-I{SDL / 'include'}",
                str(directory / "probe.c"), "-o", str(executable)], text=True, capture_output=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            tested = subprocess.run([executable], text=True, capture_output=True, timeout=5)
            self.assertEqual(tested.returncode, 0, tested.stderr)

    def test_real_event_state_and_capture_transitions(self):
        source = (PORT / "sdl_platform.c").read_text()
        controls = source.split("void platform_mouse_capture(", 1)[1].split("/* ---------- keyboard translation */", 1)[0]
        translation = source.split("/* ---------- keyboard translation */", 1)[1].split("/* ---------- internet play", 1)[0]
        events = source.split("void platform_pump_events(", 1)[1]
        production = "void platform_mouse_capture(" + controls + translation + "void platform_pump_events(" + events
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "prefix.h").write_text(PREFIX)
            (directory / "probe.c").write_text(HARNESS.replace("/* PRODUCTION_CODE */", production))
            executable = directory / "probe"
            command = ["clang", "-std=gnu11", "-O2", "-Wall", "-Wextra", "-Werror", "-pthread",
                       "-DHALO_ANDROID=1", "-DHALO_MACOS=1", "-include", str(directory / "prefix.h"),
                       f"-I{PORT}", "-iquote", str(ROOT / "port/linux/include"), f"-I{SDL / 'include'}",
                       str(directory / "probe.c"), str(PORT / "input_bindings.c"), "-o", str(executable)]
            compiled = subprocess.run(command, text=True, capture_output=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            tested = subprocess.run([executable], text=True, capture_output=True, timeout=5)
            self.assertEqual(tested.returncode, 0, tested.stderr)
            self.assertIn("Mac input transitions passed", tested.stdout)


if __name__ == "__main__":
    unittest.main()
