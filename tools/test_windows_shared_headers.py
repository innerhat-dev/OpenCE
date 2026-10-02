"""Compile native bridge headers with the Windows build's generated search path.

The probe targets the actual i686 MSVC ABI and needs no Windows SDK or linker.
A separate preprocessing check uses sentinel SDK headers to verify that angle
includes still resolve through Windows' CRT wrappers, never Linux's wrappers.
"""
import io
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools import windows_build
from tools.ninja_syntax import Writer


ROOT = Path(__file__).resolve().parents[1]
SHARED_HEADERS = (
    "performance_sound.h", "performance_audio.h", "native_audio.h",
    "native_video.h", "native_input_events.h", "halo_port_capacity.h",
)


class RecordingWriter(Writer):
    def __init__(self):
        super().__init__(io.StringIO())
        self.compile_flags = {}

    def build(self, outputs, rule, inputs=None, **kwargs):
        if rule == "windows_cc":
            self.compile_flags[Path(inputs).as_posix()] = kwargs["variables"]["cflags"]
        return super().build(outputs, rule, inputs, **kwargs)


def generated_game_include_flags():
    """Use the real generator, suppressing downloads and wrapper-file writes."""
    writer = RecordingWriter()
    solution = SimpleNamespace(port_lto="off", port_pgo="off", port_portable=True)
    previous = Path.cwd()
    try:
        os.chdir(ROOT)
        with patch.object(windows_build.sys, "platform", "win32"), \
                patch.object(windows_build, "fetch_sdl"), \
                patch.object(windows_build, "inline_export_wrapper", side_effect=lambda source: source):
            windows_build.generate_windows_build(writer, solution)
    finally:
        os.chdir(previous)
    # Both the failed engine unit and the new settings module must receive
    # exactly this search path; future changes to the generator are exercised.
    result = {}
    for source in ("source/effects/effects.c", "port/linux/game/device_settings.c"):
        tokens = shlex.split(writer.compile_flags[source].replace("\\", "/"))
        includes = []
        index = 0
        while index < len(tokens):
            token = tokens[index]
            if token in ("-I", "-iquote", "-isystem"):
                includes.extend((token, tokens[index + 1]))
                index += 1
            elif token.startswith("-I"):
                includes.append(token)
            index += 1
        result[source] = includes
    return result


PROBE = r'''
#include "performance_sound.h"
#include "performance_audio.h"
#include "native_audio.h"
#include "native_video.h"
#include "native_input_events.h"
#include "halo_port_capacity.h"
#include "port_config.h"

typedef char windows_pointer_is_32_bits[sizeof(void *) == 4 ? 1 : -1];
typedef char windows_long_is_32_bits[sizeof(long) == 4 ? 1 : -1];
typedef char windows_wchar_is_16_bits[sizeof(__WCHAR_TYPE__) == 2 ? 1 : -1];
typedef char native_input_event_is_present[HALO_NATIVE_MOUSE_RELEASE != 0 ? 1 : -1];
typedef char native_sound_capacity_is_present[HALO_PORT_MAXIMUM_EFFECTS >= 256 ? 1 : -1];

void native_bridge_declarations(void)
{
    struct performance_sound_statistics statistics;
    unsigned previous = performance_sound_push(_performance_sound_movement);
    performance_sound_capture(_performance_sound_effect, 1);
    performance_sound_pop(previous);
    performance_sound_get_statistics(&statistics);
    halo_performance_audio_available();
    halo_performance_audio_duration_ticks("timerbeep");
    halo_performance_audio_busy();
    halo_performance_audio_play("timerbeep", 1.0f);
    halo_performance_audio_stop();
    halo_audio_apply_settings();
    halo_video_fullscreen_get();
    halo_video_fullscreen_set(1);
    halo_video_apply_settings();
    platform_mouse_release_gameplay();
    platform_mouse_resume_gameplay();
    config_write_boolean("audio.menu_music", 1);
}
'''


class WindowsSharedHeadersTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.clang = shutil.which("clang")
        if not cls.clang:
            raise unittest.SkipTest("clang is required for the Windows ABI header probe")
        cls.include_flags = generated_game_include_flags()

    def test_native_bridges_compile_with_generated_windows_game_paths(self):
        paths = list(self.include_flags.values())
        self.assertEqual(paths[0], paths[1])
        with tempfile.TemporaryDirectory(prefix="halo-windows-headers-") as temporary:
            directory = Path(temporary)
            source = directory / "native_bridges.c"
            source.write_text(PROBE)
            output = directory / "native_bridges.obj"
            subprocess.run([
                self.clang, "--target=i686-pc-windows-msvc", "-std=gnu11",
                "-Wall", "-Wextra", "-Werror", "-nostdinc", *paths[0],
                "-c", str(source), "-o", str(output),
            ], cwd=ROOT, check=True, capture_output=True, text=True)
            # A genuine 32-bit COFF object, not a successful host compilation.
            self.assertEqual(output.read_bytes()[:2], b"\x4c\x01")

    def test_angle_headers_keep_windows_crt_isolation(self):
        headers = ("stdio.h", "stdlib.h", "string.h", "math.h", "limits.h",
                   "stdarg.h", "io.h", "fcntl.h", "direct.h")
        with tempfile.TemporaryDirectory(prefix="halo-windows-crt-") as temporary:
            directory = Path(temporary)
            sdk = directory / "sdk"
            sdk.mkdir()
            for name in headers:
                marker = "HALO_TEST_SDK_" + name.replace(".", "_")
                (sdk / name).write_text(f"#ifndef {marker}\n#define {marker} 1\n#endif\n")
            source = directory / "crt_search.c"
            source.write_text(
                "\n".join(f'#include "{name}"' for name in SHARED_HEADERS) + "\n" +
                "\n".join(f"#include <{name}>" for name in headers) + "\n" +
                "\n".join(f"#ifndef HALO_TEST_SDK_{name.replace('.', '_')}\n"
                          f'#error "Windows SDK fallback missing for {name}"\n#endif' for name in headers))
            result = subprocess.run([
                self.clang, "--target=i686-pc-windows-msvc", "-E", "-nostdinc",
                *next(iter(self.include_flags.values())), "-isystem", str(sdk), str(source),
            ], cwd=ROOT, check=True, capture_output=True, text=True)
            included = result.stdout.replace("\\\\", "/").replace("\\", "/")
            for name in headers:
                self.assertNotIn(f"port/linux/include/{name}", included)
            for name in ("stdio.h", "stdlib.h", "string.h", "math.h", "limits.h"):
                self.assertIn(f"port/windows/include/crt/{name}", included)
            for name in SHARED_HEADERS:
                self.assertIn(f"port/windows/include/{name}", included)


if __name__ == "__main__":
    unittest.main()
