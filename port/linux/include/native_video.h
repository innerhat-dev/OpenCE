/* Live presentation controls. Call on the game's main/render thread. */
#ifndef HALO_NATIVE_VIDEO_H
#define HALO_NATIVE_VIDEO_H

int halo_video_fullscreen_get(void);
/* Change the native window and persist its Mac preference; 0 on failure. */
int halo_video_fullscreen_set(int enabled);
/* Apply saved VSync/Smooth Motion settings; 0 if the display rejected VSync. */
int halo_video_apply_settings(void);

/* Explicit Resume captures after the current menu closes; opening/focusing
   a native panel or game window never counts as Resume. */
void platform_mouse_release_gameplay(void);
void platform_mouse_resume_gameplay(void);

#endif
