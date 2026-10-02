"""Exercise the production menu save boundary with refusing storage/display backends."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

HARNESS = r'''
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
#include "device_settings.h"
static const char *names[] = {"audio.volume", "audio.music_volume", "audio.effects_volume",
    "audio.dialogue_volume", "audio.timer_volume", "audio.menu_music", "display.vsync", "display.interpolation",
    "audio.timer_countdown", "audio.timer_beeps", "audio.timer_minutes", "audio.timer_items",
    "display.timer_position", "display.timer_scale"};
static double saved[14];
static int fullscreen, write_ok, switch_ok, apply_ok, writes, audio_applies, video_applies, switches, starts, stops;
static int write_fail_on, switch_fail_on, apply_fail_on;
static int index_of(const char *name) {
    for (int i=0;i<14;i++) if (!strcmp(names[i],name)) return i;
    assert(!"unknown preference"); return -1;
}
int config_boolean(const char *name) { return saved[index_of(name)] != 0; }
double config_real(const char *name) { return saved[index_of(name)]; }
long config_integer(const char *name) { return (long)saved[index_of(name)]; }
int config_write_numbers(const char *const *keys,const double *values,unsigned count) {
    writes++; if (!write_ok || writes==write_fail_on) return 0;
    for (unsigned i=0;i<count;i++) saved[index_of(keys[i])]=values[i];
    return 1;
}
int halo_video_fullscreen_get(void) { return fullscreen; }
int halo_video_fullscreen_set(int enabled) { switches++; if (!switch_ok || switches==switch_fail_on) return 0; fullscreen=enabled; return 1; }
int halo_video_apply_settings(void) { video_applies++; return apply_ok && video_applies!=apply_fail_on; }
void halo_audio_apply_settings(void) { audio_applies++; }
void ui_apply_main_menu_music_setting(void) { if (saved[5]) starts++; else stops++; }
static void reset(double values[NUMBER_OF_DEVICE_SETTINGS]) {
    for (int i=0;i<14;i++) saved[i]=(i==7 || i==11 || i==12) ? 0.0 : 1.0;
    saved[0]=0.15; fullscreen=1; write_ok=switch_ok=apply_ok=1;
    writes=audio_applies=video_applies=switches=starts=stops=0;
    write_fail_on=switch_fail_on=apply_fail_on=0;
    for(int i=0;i<NUMBER_OF_DEVICE_SETTINGS;i++) values[i]=device_settings_get(i);
}
int main(void) {
    double values[NUMBER_OF_DEVICE_SETTINGS];
    reset(values);
    /* Opening/saving an untouched page preserves an off-step master volume. */
    assert(device_settings_apply(0,NULL));
    assert(device_settings_apply((1UL<<NUMBER_OF_DEVICE_SETTINGS)-1,values));
    assert(writes==0 && audio_applies==0 && switches==0 && saved[0]==0.15);
    values[_device_setting_music_volume]=0.4; values[_device_setting_menu_music]=0;
    assert(device_settings_apply((1UL<<_device_setting_music_volume)|(1UL<<_device_setting_menu_music),values));
    assert(writes==1 && audio_applies==1 && stops==1 && starts==0 && saved[0]==0.15 && saved[1]==0.4);
    assert(video_applies==0 && switches==0);
    reset(values); values[_device_setting_master_volume]=0; write_ok=0;
    assert(!device_settings_apply(1,values)); assert(saved[0]==0.15 && audio_applies==0);
    reset(values); values[0]=NAN; assert(!device_settings_apply(1,values));
    values[0]=1.1; assert(!device_settings_apply(1,values));
    values[0]=-0.1; assert(!device_settings_apply(1,values));
    values[_device_setting_menu_music]=0.5;
    assert(!device_settings_apply(1UL<<_device_setting_menu_music,values));
    assert(!device_settings_apply(1UL<<NUMBER_OF_DEVICE_SETTINGS,values));
    assert(!device_settings_apply(1,NULL)); assert(writes==0 && switches==0);
    reset(values); values[_device_setting_fullscreen]=0;
    assert(device_settings_apply(1UL<<_device_setting_fullscreen,values));
    assert(!fullscreen && switches==1 && writes==0);
    reset(values); values[_device_setting_fullscreen]=0; values[_device_setting_vsync]=0;
    switch_ok=0; assert(!device_settings_apply((1UL<<_device_setting_fullscreen)|(1UL<<_device_setting_vsync),values));
    assert(fullscreen && writes==0 && saved[6]==1);
    reset(values); values[_device_setting_fullscreen]=0; values[_device_setting_vsync]=0; write_ok=0;
    assert(!device_settings_apply((1UL<<_device_setting_fullscreen)|(1UL<<_device_setting_vsync),values));
    assert(fullscreen && switches==2 && saved[6]==1 && video_applies==0);
    reset(values); values[_device_setting_fullscreen]=0; values[_device_setting_vsync]=0; apply_fail_on=1;
    assert(!device_settings_apply((1UL<<_device_setting_fullscreen)|(1UL<<_device_setting_vsync),values));
    assert(fullscreen && saved[6]==1 && writes==2 && switches==2 && video_applies==2);
    reset(values); values[_device_setting_fullscreen]=0; values[_device_setting_vsync]=0;
    write_ok=0; switch_fail_on=2;
    assert(device_settings_apply((1UL<<_device_setting_fullscreen)|(1UL<<_device_setting_vsync),values)==-1);
    assert(!fullscreen && saved[6]==1);
    reset(values); values[_device_setting_vsync]=0; apply_fail_on=1; write_fail_on=2;
    assert(device_settings_apply(1UL<<_device_setting_vsync,values)==-1);
    assert(saved[6]==0); /* Report incomplete rollback, never pretend unchanged. */
    reset(values); values[_device_setting_vsync]=0; apply_ok=0;
    assert(device_settings_apply(1UL<<_device_setting_vsync,values)==-1);
    reset(values); values[_device_setting_interpolation]=1;
    assert(device_settings_apply(1UL<<_device_setting_interpolation,values));
    assert(saved[7]==1 && video_applies==1 && audio_applies==0);
    /* New timer preferences do not enable match rules or reconfigure audio/video backends. */
    reset(values);
    assert(values[_device_setting_timer_countdown]==1 && values[_device_setting_timer_beeps]==1 &&
        values[_device_setting_timer_minutes]==1 && values[_device_setting_timer_items]==0 &&
        values[_device_setting_timer_position]==0 && values[_device_setting_timer_scale]==1);
    values[_device_setting_timer_countdown]=0; values[_device_setting_timer_beeps]=0;
    values[_device_setting_timer_minutes]=0; values[_device_setting_timer_items]=1;
    values[_device_setting_timer_position]=2; values[_device_setting_timer_scale]=0.625;
    assert(device_settings_apply(((1UL<<NUMBER_OF_DEVICE_SETTINGS)-1) & ~((1UL<<9)-1),values));
    assert(writes==1 && !audio_applies && !video_applies && !switches && !starts && !stops);
    assert(saved[8]==0 && saved[9]==0 && saved[10]==0 && saved[11]==1 && saved[12]==2 && saved[13]==0.625);
    reset(values);
    for(int setting=_device_setting_timer_countdown;setting<=_device_setting_timer_items;setting++) {
        values[setting]=0.5; assert(!device_settings_apply(1UL<<setting,values)); values[setting]=0;
    }
    values[_device_setting_timer_position]=1.5; assert(!device_settings_apply(1UL<<_device_setting_timer_position,values));
    values[_device_setting_timer_position]=3; assert(!device_settings_apply(1UL<<_device_setting_timer_position,values));
    values[_device_setting_timer_scale]=0.49; assert(!device_settings_apply(1UL<<_device_setting_timer_scale,values));
    values[_device_setting_timer_scale]=1.01; assert(!device_settings_apply(1UL<<_device_setting_timer_scale,values));
    assert(!writes);
    reset(values); values[_device_setting_vsync]=0; values[_device_setting_timer_position]=2; values[_device_setting_timer_scale]=0.55;
    apply_fail_on=1;
    assert(!device_settings_apply((1UL<<_device_setting_vsync)|(1UL<<_device_setting_timer_position)|(1UL<<_device_setting_timer_scale),values));
    assert(writes==2 && saved[6]==1 && saved[12]==0 && saved[13]==1);
    saved[12]=-1; assert(device_settings_get(_device_setting_timer_position)==0);
    saved[12]=3; assert(device_settings_get(_device_setting_timer_position)==0);
    saved[13]=NAN; assert(device_settings_get(_device_setting_timer_scale)==1);
    saved[13]=0.1; assert(device_settings_get(_device_setting_timer_scale)==0.5);
    saved[13]=2; assert(device_settings_get(_device_setting_timer_scale)==1);
    saved[0]=NAN; assert(device_settings_get(0)==0); saved[0]=-1; assert(device_settings_get(0)==0);
    saved[0]=2; assert(device_settings_get(0)==1);
    puts("device settings save/apply tests passed");
}
'''


class DeviceSettingsTests(unittest.TestCase):
    def test_save_apply_boundary(self):
        with tempfile.TemporaryDirectory(prefix="halo-device-settings-") as folder:
            path = Path(folder)
            (path / "test.c").write_text(HARNESS)
            (path / "port_config.h").write_text(
                "int config_boolean(const char *); double config_real(const char *); long config_integer(const char *);\n"
                "int config_write_numbers(const char *const *, const double *, unsigned);\n")
            (path / "native_audio.h").write_text("void halo_audio_apply_settings(void);\n")
            (path / "native_video.h").write_text(
                "int halo_video_fullscreen_get(void); int halo_video_fullscreen_set(int);\n"
                "int halo_video_apply_settings(void);\n")
            executable = path / "test"
            subprocess.run(["clang", "-std=c99", "-Wall", "-Wextra", "-Werror",
                            "-I", str(path), "-I", str(ROOT / "port/linux/game"),
                            str(path / "test.c"), str(ROOT / "port/linux/game/device_settings.c"),
                            "-o", str(executable)], check=True)
            subprocess.run([str(executable)], check=True)


if __name__ == "__main__":
    unittest.main()
