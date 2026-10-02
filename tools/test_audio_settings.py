"""Exercise real TOML batch persistence and the engine's live category gains."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib
import unittest

from tools.test_input_bindings import PREFIX, PORT, ROOT, SDL
from tools.test_performance_variants import block


CONFIG_HARNESS = r'''
#include <assert.h>
#include <errno.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
#include <SDL3/SDL.h>
#include "port_config.h"
#undef fsync
#undef rename
#undef fwrite
#undef fclose
static int failure_mode;
int config_test_fsync(int fd) { if(failure_mode==1) { errno=ENOSPC; return -1; } return fsync(fd); }
int config_test_rename(const char *from,const char *to) { if(failure_mode==2) { errno=EACCES; return -1; } return rename(from,to); }
size_t config_test_fwrite(const void *data,size_t size,size_t count,FILE *file) {
    return fwrite(data,size,failure_mode==3 ? count/2:count,file);
}
int config_test_fclose(FILE *file) { int result=fclose(file); return failure_mode==4 ? EOF:result; }
void platform_log(const char *format,...) { (void)format; }
#ifndef HALO_ANDROID
const char *SDL_GetBasePath(void) {
    static char path[1024]; snprintf(path,sizeof(path),"%s/",getenv("HALO_SAVE_ROOT")); return path;
}
void *SDL_LoadFile(const char *path,size_t *size) {
    FILE *file=fopen(path,"rb"); if(!file) return NULL;
    assert(!fseek(file,0,SEEK_END)); long length=ftell(file); assert(length>=0); rewind(file);
    void *data=malloc((size_t)length+1); assert(data);
    assert(fread(data,1,(size_t)length,file)==(size_t)length); fclose(file); *size=(size_t)length; return data;
}
bool SDL_SaveFile(const char *path,const void *data,size_t size) {
    FILE *file=fopen(path,"wb"); if(!file) return false;
    bool written=fwrite(data,1,size,file)==size; return fclose(file)==0 && written;
}
void SDL_free(void *data) { free(data); }
#endif
int main(int argc,char **argv) {
    assert(argc>=3 && (argc-3)%2==0);
    if(strcmp(argv[2],"cold")) {
        assert(config_real("audio.music_volume")==1.0 && config_real("audio.effects_volume")==1.0);
        assert(config_real("audio.dialogue_volume")==1.0 && config_real("audio.timer_volume")==1.0);
        assert(config_boolean("audio.timer_countdown") && config_boolean("audio.timer_beeps") && config_boolean("audio.timer_minutes"));
        assert(!config_boolean("audio.timer_items") && config_integer("display.timer_position")==0 && config_real("display.timer_scale")==1.0);
    }
    char path[1024]; snprintf(path,sizeof(path),"%s/config.toml",getenv("HALO_SAVE_ROOT"));
    FILE *input=fopen(argv[1],"rb"),*output=fopen(path,"wb"); assert(input && output);
    for(int c;(c=fgetc(input))!=EOF;) assert(fputc(c,output)!=EOF);
    assert(!fclose(input) && !fclose(output));
    const char *names[32]; double values[32]; unsigned count=(unsigned)(argc-3)/2; assert(count<32);
    for(unsigned i=0;i<count;i++) { names[i]=argv[3+i*2]; values[i]=strtod(argv[4+i*2],NULL); }
    if(!strcmp(argv[2],"readonly")) assert(!chmod(path,0400));
    failure_mode=atoi(argv[2]);
    int result=config_write_numbers(names,values,count);
    failure_mode=0;
    printf("%d %d %.17g %.17g %.17g %.17g %.17g %ld %d %d %d %d %ld %.17g\n",result,config_boolean("audio.menu_music"),
        config_real("audio.volume"),config_real("audio.music_volume"),config_real("audio.effects_volume"),
        config_real("audio.dialogue_volume"),config_real("audio.timer_volume"),config_integer("display.window_scale"),
        config_boolean("audio.timer_countdown"),config_boolean("audio.timer_beeps"),config_boolean("audio.timer_minutes"),
        config_boolean("audio.timer_items"),config_integer("display.timer_position"),config_real("display.timer_scale"));
    assert(!chmod(path,0600)); return 0;
}
'''


@unittest.skipUnless(shutil.which("clang") and (SDL / "include/SDL3/SDL.h").exists(), "clang and SDL3 headers required")
class ConfigBatchPersistenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="halo-audio-config-")
        cls.directory = Path(cls.temporary.name)
        (cls.directory / "prefix.h").write_text(PREFIX + r"""
#include <unistd.h>
int config_test_fsync(int);
int config_test_rename(const char *,const char *);
size_t config_test_fwrite(const void *,size_t,size_t,FILE *);
int config_test_fclose(FILE *);
#define fsync config_test_fsync
#define rename config_test_rename
#define fwrite config_test_fwrite
#define fclose config_test_fclose
""")
        (cls.directory / "probe.c").write_text(CONFIG_HARNESS)
        cls.executables = {}
        for target, defines in (("mac", ["-DHALO_ANDROID=1", "-DHALO_MACOS=1"]),
                                ("other", ["-DHALO_ANDROID=1"]), ("desktop", [])):
            executable = cls.directory / target
            subprocess.run(["clang", "-std=gnu11", "-O2", "-Wall", "-Wextra", "-Werror", "-pthread",
                            *defines, "-include", str(cls.directory / "prefix.h"), f"-I{PORT}",
                            f"-I{SDL / 'include'}", f"-I{ROOT / 'port/third_party/tomlc17'}",
                            str(cls.directory / "probe.c"), str(PORT / "port_config.c"),
                            str(ROOT / "port/third_party/tomlc17/tomlc17.c"), "-o", str(executable)], check=True)
            cls.executables[target] = executable

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def save(self, original, changes, *, expected=None, mode="save", success=True):
        for target, executable in self.executables.items():
            with self.subTest(target=target), tempfile.TemporaryDirectory(dir=self.directory) as folder:
                directory = Path(folder)
                fixture = directory / "existing.toml"
                fixture.write_bytes(original.encode())
                environment = {key: value for key, value in os.environ.items() if not key.startswith("HALO_")}
                environment.update(HALO_SAVE_ROOT=folder, HALO_DATA_ROOT=folder)
                arguments = [str(executable), str(fixture), mode]
                arguments += [str(value) for pair in changes for value in pair]
                result = subprocess.run(arguments, env=environment, text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                values = list(map(float, result.stdout.split()))
                self.assertEqual(values[0], int(success))
                loaded = {"audio.menu_music": 1, "audio.volume": 1, "audio.music_volume": 1,
                          "audio.effects_volume": 1, "audio.dialogue_volume": 1, "audio.timer_volume": 1,
                          "display.window_scale": 2, "audio.timer_countdown": 1, "audio.timer_beeps": 1,
                          "audio.timer_minutes": 1, "audio.timer_items": 0, "display.timer_position": 0, "display.timer_scale": 1}
                if success:
                    loaded.update((key, float(value)) for key, value in changes)
                self.assertEqual(values[1:], list(loaded.values()))
                saved = (directory / "config.toml").read_bytes().decode()
                if expected is not None:
                    self.assertEqual(saved, expected)
                if not success:
                    self.assertEqual(saved, original)
                else:
                    parsed = tomllib.loads(saved)
                    for key, value in changes:
                        section, name = key.split(".")
                        self.assertEqual(parsed[section][name], float(value))
                self.assertEqual(sorted(path.name for path in directory.iterdir()), ["config.toml", "existing.toml"])

    def test_mixed_batch_preserves_comments_unknown_keys_and_exact_numeric_tokens(self):
        original = '# custom\n[audio] # audio\nmenu_music = true # keep\nvolume = 1_0e-1\ncustom = "é"\n[display]\nwindow_scale = 0x2 # scale\n'
        expected = original.replace('true # keep', 'false # keep').replace('1_0e-1', '0.125').replace('0x2 # scale', '3 # scale')
        self.save(original, [("audio.menu_music", 0), ("audio.volume", 0.125), ("display.window_scale", 3)], expected=expected)

    def test_quoted_dotted_and_inline_tables_accept_batches(self):
        for original in ('["audio"]\r\n"volume"=1 # v\r\n"menu_music"=true\r\n',
                         'audio.volume=+1.0\naudio.menu_music=true\n',
                         'audio={volume=1, menu_music=true, extra="é, # []"}\n'):
            with self.subTest(original=original):
                self.save(original, [("audio.volume", 0), ("audio.menu_music", 0)])

    def test_missing_numeric_keys_and_sections_added_together(self):
        self.save('# existing comments only', [("audio.volume", 0.5), ("audio.timer_volume", 0.25),
                                              ("audio.menu_music", 0), ("display.window_scale", 3)])
        self.save('audio.volume=1.0\n', [("audio.music_volume", 0.5), ("audio.effects_volume", 0.25),
                                       ("audio.dialogue_volume", 0.75), ("audio.timer_volume", 0)])

    def test_timer_preferences_preserve_existing_values_comments_and_failure_atomicity(self):
        original = '[audio] # existing\nmenu_music=true\ntimer_countdown=true # countdown\ntimer_beeps=true\ntimer_minutes=true\ntimer_items=false\n[display]\ntimer_position=0 # place\ntimer_scale=1.0\ncustom="keep"\n'
        changes = [("audio.timer_countdown", 0), ("audio.timer_beeps", 0), ("audio.timer_minutes", 0),
                   ("audio.timer_items", 1), ("display.timer_position", 2), ("display.timer_scale", 0.625)]
        expected = original.replace('timer_countdown=true', 'timer_countdown=false').replace('timer_beeps=true', 'timer_beeps=false').replace('timer_minutes=true', 'timer_minutes=false').replace('timer_items=false', 'timer_items=true').replace('timer_position=0', 'timer_position=2').replace('timer_scale=1.0', 'timer_scale=0.625')
        self.save(original, changes, expected=expected)
        self.save(original, changes, mode="2", success=False)
        self.save('# preserve unknown\n[custom]\nvalue=42\n', changes)

    def test_last_invalid_value_rolls_back_whole_batch(self):
        original = '[audio]\nmenu_music=true\nvolume=1.0\ntimer_volume="invalid"\n'
        self.save(original, [("audio.menu_music", 0), ("audio.volume", 0.125), ("audio.timer_volume", 0.5)], success=False)
        for original in ('[audio]\nvolume=invalid\n', 'audio={volume=1.0}\n'):
            self.save(original, [("audio.volume", 0.5), ("audio.timer_volume", 0.5)], success=False)

    def test_first_config_operation_saves_without_an_earlier_default_rewrite(self):
        original = '[audio]\nmenu_music=true\nvolume=1.0\ntimer_volume="invalid"\n'
        self.save(original, [("audio.menu_music", 0), ("audio.timer_volume", 0.5)], mode="cold", success=False)
        original = '[audio]\nvolume=1.0 # keep\n'
        self.save(original, [("audio.volume", 0.5)], mode="cold", expected=original.replace("1.0", "0.5"))

    def test_invalid_numeric_requests_and_duplicate_keys_change_nothing(self):
        original = '[audio]\nmenu_music=true\nvolume=1.0\n'
        invalid = [("audio.volume", "nan"), ("audio.volume", "inf"), ("audio.menu_music", 0.5),
                   ("display.window_scale", 2.5), ("display.window_scale", 1e30), ("audio.unknown", 1),
                   ("game.language", 1), ("audio.menu_music", 0)]
        for last in invalid:
            with self.subTest(last=last):
                self.save(original, [("audio.menu_music", 0), last], success=False)

    def test_partial_write_close_sync_rename_and_readonly_failures_preserve_file_and_memory(self):
        original = '# unchanged\n[audio]\nmenu_music=true\nvolume=1.0 # volume\n'
        for mode in ("readonly", "1", "2", "3", "4"):
            with self.subTest(mode=mode):
                self.save(original, [("audio.menu_music", 0), ("audio.volume", 0.125)], mode=mode, success=False)


class LiveEngineCategoryTests(unittest.TestCase):
    def test_categories_multiply_current_script_gains_and_dialogue_ducking(self):
        source = (ROOT / "source/sound/sound_manager.c").read_text()
        signature = "static real sound_manager_master_gain(\n\tshort class_index)\n{"
        gain = block(source, signature)
        fixture = r'''
#include <assert.h>
#include <math.h>
#include <string.h>
#define HALO_PORT_MAXIMUM_NETWORK_PLAYERS 16
typedef float real;
enum { _sound_class_unit_dialog=19, _sound_class_music=32, _sound_class_scripted_dialog_to_player=44,
       _sound_class_scripted_other=45, _sound_class_scripted_dialog_to_other=46, _sound_class_scripted_dialog_force_unspatialized=47 };
static struct { real nondialog_gain; } sound_manager_globals={0.7f};
static real script_gain=0.8f;
static double music=1,effects=1,dialogue=1;
static real sound_class_get_gain(short index) { (void)index; return script_gain; }
static double config_real(const char *name) {
    if(!strcmp(name,"audio.music_volume")) return music;
    if(!strcmp(name,"audio.effects_volume")) return effects;
    assert(!strcmp(name,"audio.dialogue_volume")); return dialogue;
}
''' + gain + r'''
int main(void) {
    for(short index=0;index<=50;index++) {
        int scripted=index==44 || index==46 || index==47;
        float duck=scripted ? 1.0f:sound_manager_globals.nondialog_gain;
        assert(fabsf(sound_manager_master_gain(index)-script_gain*duck)<0.00001f);
    }
    music=0.25; effects=0.5; dialogue=0.75;
    for(short index=0;index<=50;index++) {
        int scripted=index==44 || index==46 || index==47;
        float duck=scripted ? 1.0f:sound_manager_globals.nondialog_gain;
        float user=index==32 ? music:scripted || index==19 ? dialogue:effects;
        assert(fabsf(sound_manager_master_gain(index)-script_gain*duck*user)<0.00001f);
    }
    /* Existing music reflects changes without recreating a channel; script
       fades and non-dialog ducking continue to modify that same final gain. */
    music=0; assert(sound_manager_master_gain(32)==0);
    music=1; script_gain=0.4f; sound_manager_globals.nondialog_gain=0.5f;
    assert(fabsf(sound_manager_master_gain(32)-0.2f)<0.00001f);
    assert(fabsf(sound_manager_master_gain(44)-0.3f)<0.00001f);
    effects=NAN; assert(sound_manager_master_gain(45)==0);
    effects=-1; assert(sound_manager_master_gain(50)==0);
    effects=2; assert(fabsf(sound_manager_master_gain(45)-0.2f)<0.00001f);
    return 0;
}
'''
        with tempfile.TemporaryDirectory(prefix="halo-audio-categories-") as temporary:
            directory = Path(temporary)
            (directory / "test.c").write_text(fixture)
            subprocess.run(["clang", "-std=c11", "-Wall", "-Wextra", "-Werror", str(directory / "test.c"),
                            "-o", str(directory / "test")], check=True)
            subprocess.run([str(directory / "test")], check=True)


class NativeStatHeaderTests(unittest.TestCase):
    def test_platform_layer_keeps_posix_and_msvc_file_declarations(self):
        # Production includes the game's compatibility headers before libc.
        # The ordinary parser fixture intentionally stubs that game ABI, so
        # exercise this include order separately rather than hiding the shim.
        source = r'''
#include <sys/stat.h>
int probe(const char *path,int descriptor) {
    struct stat native;
    struct _stat xbox;
    return stat(path,&native)+_stat(path,&xbox)+fchmod(descriptor,native.st_mode)+!S_ISREG(native.st_mode);
}
'''
        subprocess.run(["clang", "-std=gnu11", "-Wall", "-Wextra", "-Werror", "-fsyntax-only",
                        "-DHALO_LINUX_PLATFORM_LAYER", "-I", str(ROOT / "port/linux/include"),
                        "-x", "c", "-"], input=source, text=True, check=True)


if __name__ == "__main__":
    unittest.main()
