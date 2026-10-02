/* The menus edit a local draft. This is their shared save/apply boundary. */
#include "device_settings.h"
#include "port_config.h"
#include "native_video.h"
#include "native_audio.h"
#include <math.h>
#include <stddef.h>

/* Main menu music is controlled on the game thread, never the mixer thread. */
void ui_apply_main_menu_music_setting(void);

static const char *const setting_names[NUMBER_OF_DEVICE_SETTINGS] =
{
    "audio.volume", "audio.music_volume", "audio.effects_volume",
    "audio.dialogue_volume", "audio.timer_volume", "audio.menu_music",
    NULL, "display.vsync", "display.interpolation",
    "audio.timer_countdown", "audio.timer_beeps", "audio.timer_minutes", "audio.timer_items",
    "display.timer_position", "display.timer_scale"
};

double device_settings_get(short setting)
{
    double value;
    if (setting < 0 || setting >= NUMBER_OF_DEVICE_SETTINGS) return 0.0;
    if (setting == _device_setting_fullscreen) return halo_video_fullscreen_get() != 0;
    if (setting == _device_setting_timer_position)
    {
        long position = config_integer(setting_names[setting]);
        return position >= 0 && position <= 2 ? position : 0;
    }
    if (setting == _device_setting_timer_scale)
    {
        value = config_real(setting_names[setting]);
        return !isfinite(value) ? 1.0 : value < 0.5 ? 0.5 : value > 1.0 ? 1.0 : value;
    }
    if (setting >= _device_setting_menu_music) return config_boolean(setting_names[setting]) != 0;
    value = config_real(setting_names[setting]);
    /* Keep malformed file values out of slider indices. */
    return !(value >= 0.0) ? 0.0 : value > 1.0 ? 1.0 : value;
}

int device_settings_apply(unsigned long changed_mask,
    const double values[NUMBER_OF_DEVICE_SETTINGS])
{
    const char *names[NUMBER_OF_DEVICE_SETTINGS];
    double updates[NUMBER_OF_DEVICE_SETTINGS], previous[NUMBER_OF_DEVICE_SETTINGS];
    double old_fullscreen = 0.0;
    unsigned count = 0;
    unsigned long effective = 0;
    int setting, fullscreen_changed = 0;

    if (changed_mask & ~((1UL << NUMBER_OF_DEVICE_SETTINGS) - 1)) return 0;
    if (!changed_mask) return 1;
    if (!values) return 0;
    for (setting = 0; setting < NUMBER_OF_DEVICE_SETTINGS; setting++)
    {
        double old;
        if (!(changed_mask & (1UL << setting))) continue;
        if (!isfinite(values[setting])) return 0;
        if (setting == _device_setting_timer_position)
        {
            if (values[setting] < 0.0 || values[setting] > 2.0 || values[setting] != (int)values[setting]) return 0;
        }
        else if (setting == _device_setting_timer_scale)
        {
            if (values[setting] < 0.5 || values[setting] > 1.0) return 0;
        }
        else if (values[setting] < 0.0 || values[setting] > 1.0 ||
            (setting >= _device_setting_menu_music && values[setting] != 0.0 && values[setting] != 1.0)) return 0;
        old = device_settings_get((short)setting);
        if (old == values[setting]) continue;
        effective |= 1UL << setting;
        if (setting == _device_setting_fullscreen) old_fullscreen = old;
        else
        {
            names[count] = setting_names[setting];
            updates[count] = values[setting];
            previous[count++] = old;
        }
    }
    if (!effective) return 1;

    /* Fullscreen belongs to native Mac preferences. Apply it first so a
     * rejected mode switch cannot leave the TOML draft partly accepted. */
    if (effective & (1UL << _device_setting_fullscreen))
    {
        if (!halo_video_fullscreen_set(values[_device_setting_fullscreen] != 0.0)) return 0;
        fullscreen_changed = 1;
    }
    if (count && !config_write_numbers(names, updates, count))
    {
        if (fullscreen_changed && !halo_video_fullscreen_set(old_fullscreen != 0.0)) return -1;
        return 0;
    }
    if ((effective & ((1UL << _device_setting_vsync) | (1UL << _device_setting_interpolation))) &&
        !halo_video_apply_settings())
    {
        /* Restore the accepted preference if the display backend refuses it. */
        int restored = !count || config_write_numbers(names, previous, count);
        int video_restored = halo_video_apply_settings();
        int fullscreen_restored = !fullscreen_changed || halo_video_fullscreen_set(old_fullscreen != 0.0);
        if (!restored)
        {
            /* A second storage failure can leave the accepted file in place.
             * Keep audio aligned with that file and report the partial result. */
            if (effective & ((1UL << _device_setting_menu_music) - 1)) halo_audio_apply_settings();
            if (effective & (1UL << _device_setting_menu_music)) ui_apply_main_menu_music_setting();
        }
        return restored && video_restored && fullscreen_restored ? 0 : -1;
    }
    if (effective & ((1UL << _device_setting_menu_music) - 1)) halo_audio_apply_settings();
    if (effective & (1UL << _device_setting_menu_music))
        ui_apply_main_menu_music_setting();
    return 1;
}
