/* Native audio preferences; independent of map, profile and network state. */
#ifndef HALO_NATIVE_AUDIO_H
#define HALO_NATIVE_AUDIO_H

/* Main/game thread only, after accepting and successfully saving settings.
 * Updates the master and current timer clip under the mixer lock. Engine
 * music/effects/dialogue gains read the saved settings during sound updates. */
void halo_audio_apply_settings(void);

#endif
