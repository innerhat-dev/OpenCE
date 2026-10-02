# Native audio, video and Mac window controls

Open **Settings → Game Settings** from the main menu, or **Game Settings**
from Pause in multiplayer, campaign or cooperative play. **Profile Settings**
continues to open the original player-profile editor. Keyboard and mouse
preferences remain in `config.toml`.

The main Settings chooser uses the original Multiplayer menu's left-hand list
and right-hand picture/description panel. Profile Settings shows the original
Spartan artwork; Game Settings shows the controller artwork. Moving between
the rows updates the preview, with the original fonts, blue highlights and
button legend retained.

Game Settings uses the same two-column chooser for Audio and Video, with the
original controller-calibration and TV/Xbox illustrations. Its Audio and Video
pages clone the original Advanced Controls editor: blue option rows, separate
labels and values, the original arrow graphics, contextual help, and the native
Accept/Cancel legend. There are no replacement fonts or new artwork.

Campaign and multiplayer maps do not contain the main-menu editor artwork.
Their in-game settings use the resident pause artwork: original 202×27 buttons,
original bitmap fonts and text baseline, and the blue frame with its native
Select/Back legend. Taller option pages extend the middle of the frame while
preserving its corners and footer divider. Split-screen pages fit within their
local viewport; focused help appears beneath the frame in full-screen layouts.

Audio and Video preferences belong to the local installation. They are not
part of a player profile, map or network gametype. PB Options remain saved
gametype options with host authority. Timer cue groups, volume, position and
size are local preferences; the host still controls whether the timer and
timer audio are enabled.

## Audio

| Menu control | Config key | Meaning |
| --- | --- | --- |
| Master volume | `audio.volume` | All output, including timer announcements |
| Music volume | `audio.music_volume` | The engine's music sound class |
| Effects volume | `audio.effects_volume` | Effects and ambience, including the multiplayer announcer |
| Dialogue volume | `audio.dialogue_volume` | Unit dialogue and the three scripted dialogue classes |
| Timer Audio → Volume | `audio.timer_volume` | Optional PB timer recordings |
| Timer Audio → Countdown | `audio.timer_countdown` | Spoken warnings and ten-to-one countdown; default On |
| Timer Audio → Beeps | `audio.timer_beeps` | Common timer beeps; default On |
| Timer Audio → Minute Announcements | `audio.timer_minutes` | Elapsed minute calls; default On |
| Timer Audio → Item Cues | `audio.timer_items` | Deterministic map rocket/powerup wave reminders; default Off |
| Menu music | `audio.menu_music` | Main-menu title music on/off |

Timer Audio is a child page of Audio. Its Accept retains changes in the parent
draft; its Cancel restores the values present when entering that child page.
Accept on Audio writes the complete audio draft. Cancel on Audio discards all
pending child changes. The footer explains that the host must enable Timer Sounds.

Volumes range from 0 to 100 percent. Left/right or clicking either arrow changes
the selection; compact pause controls also respond to either side of their row.
An untouched value from the config, such as 15 percent,
is preserved exactly. The first volume edit moves to the next or previous
10-percent step. Master zero mutes the output; the startup-only `audio.enabled`
device switch remains a file setting.

In the main-menu editors, press **A** or **Start**, or click **Accept** in the
button legend, to save the page and apply it to the running game. In the compact
pause editors, select the **Accept** row. **B**, Back or Escape discards the draft.
Existing music fades, sound-class script gains and
dialogue ducking still apply; user volumes multiply those gains. Master and
timer changes reach the mixer under its lock, including a timer clip already
playing. Changing Menu Music during a match affects the next main-menu visit.

## Video

Video contains **Fullscreen**, **VSync**, **Smooth Motion**, **Timer Position**
and **Timer Size**. Smooth Motion enables render interpolation while simulation remains
30 Hz. Switching interpolation resets its old snapshots before rendering with
the new setting.

Timer Position is Top Center, Bottom Center or Bottom Right
(`display.timer_position`, default 0). Timer Size is 50–100%
(`display.timer_scale`, default 1); editing moves in 5% steps and untouched
fractional values remain exact. Both apply to each local viewport using the
stock HUD font, colors and shadow. They only appear when the host enables Match Timer.

Fullscreen shares the existing native Mac preference in `macos-settings.json`.
VSync and Smooth Motion use `display.vsync` and `display.interpolation` in
`config.toml`. Settings apply on Accept without restarting. Rendering resolution,
aspect selection, Direct Camera and high-resolution HUD behavior are unchanged.

## Mac input and window behavior

- Escape opens Pause during gameplay and releases the cursor. Within menus it
  goes back; inside the developer console it closes the console.
- F and Backspace retain Halo's B button behavior. Escape is consumed by the
  native behavior even when an older config includes it in the B binding.
- F12 remains the mouse release/recapture shortcut. Menus keep the cursor free.
- Resume captures after Pause closes. Clicking released gameplay also captures,
  and that first click is consumed so it cannot fire a weapon.
- Changing focus, opening native panels and choosing Show Game leave the cursor
  free. Releasing clears held and queued gameplay input.
- The game window retains the native resizable frame, with the title and
  traffic-light buttons hidden. Its top strip can be dragged while the cursor
  is free. Control-Command-F and the View menu still change fullscreen;
  Command-Q quits normally.

Multiplayer networking continues while the local cursor is released.
Campaign and co-op settings inherit the original pause menu's pause flag, so
opening Audio, Video or nested Timer Audio keeps game time and game audio paused.
Closing the menu releases that pause. Multiplayer settings retain the original
unpaused behavior.

## Persistence and verification

The shared settings boundary validates changed rows, preserves unrelated TOML
text, and replaces the config atomically. A failed save keeps the menu open.
Fullscreen and TOML preferences use separate stores; if either backend also
refuses restoration after an error, the menu reloads current values and reports
that restoration was incomplete.

Focused tests cover mixed numeric/boolean persistence and injected file errors,
live sound gains, current timer clips, menu Accept/Back and registration
lifecycle, input transitions, video application, and the shared save boundary.
The installed Mac build passed 35 focused tests and a two-peer Chill Out smoke
test covering all PB option combinations. Isolated UI checks exercised main-menu
and campaign settings, audio Accept/Cancel, live menu music, fullscreen, resizing,
Escape/Pause and Resume. A main-menu-to-campaign stale-string regression found
during verification is fixed and covered by map-transition fixtures. Audio gain
behavior is verified by mixer tests; subjective listening and physical-controller
split-screen play were not assessed. Local evidence is in
`build/native-settings/ui-check/validation.json` and
`build/native-settings/multiplayer-check/validation.json`.

The Settings chooser revision passed 10 focused menu, persistence and runtime-tag
tests. Live checks confirmed both pictures and descriptions, keyboard focus,
mouse activation of each destination, and Back navigation. Evidence is in
`build/native-settings/chooser-check/validation.json`.

The Game Settings chooser and Audio/Video editor revision passed 12 focused
menu, runtime-tag and Mac input tests. Live checks confirmed the original artwork,
option backgrounds and arrows, focus-dependent help, mouse changes in both
directions, and Accept/Cancel persistence for audio and video. Checks used a
separate save directory; the normal user's preferences were preserved. Evidence
is in `build/native-settings/native-pages-check/validation.json`.

The timer-preference extension passed native main-menu and in-game checks:
Timer Audio child Accept and parent Cancel, parent Accept persistence, independent
preferences on two peers, unchanged fractional values, and a live bottom-right
75% timer. Main-menu PB sound rules also saved and reopened correctly; mouse
arrow hitboxes now include the original arrow artwork for all six PB rows.
See [the first-three integration record](pb-first-three.md) for the 51 focused
tests, peer checks, exact build hashes and current limitations.

The subsequent in-game menu repair restores complete rounded selector outlines,
centers text on the authored 202×27 button background, and retains the original
frame corners, divider and button legend. Compact labels leave padding inside
the curved ends; help lines are checked against the actual bitmap font widths.
The campaign/co-op list moves up three pixels so its added Game Settings row
clears the original footer, while the mission-objective panel stays unchanged.
The main-menu layouts and gameplay rules are unchanged by this repair.

The repair passed 25 focused tests, including real-font help widths, native
menu input/persistence, campaign pause-counter lifecycle, and frame geometry/UV
checks under ASan/UBSan. Live Prisoner checks confirmed complete selector
outlines and padding on PB Options, Audio and Timer Audio, a clean settings
chooser, and a host-applied setting reaching both peers. Live A10 checks
confirmed the campaign's last selector clears the divider and the original
mission-objective panel remains intact. Video and nested Timer Audio held game
time at tick 494 across separate 0.6-second samples; closing the menus resumed
time (1038 to 1056 over 0.6 seconds).

The installed, signature-verified guest is
`46f1ec75a3b8a5c12a68d85f8b79b10102b9ccb27995cd83e1e932c62068f5b7`.
The normal Applications app was observed running that guest with its normal
data/save paths. The final campaign check used that build; the multiplayer
visual/synchronization check used `ec85a5ae55d5506b217b11c884f425e8b19ab7889f2cb54bff07b869a96ef93a`,
before the isolated campaign-pause-flag correction. Split-screen geometry and
co-op pause flags are covered by fixtures, not a physical-controller session.
Evidence is in `build/native-settings/pause-fidelity-polish-final/`,
`build/native-settings/pause-fidelity-campaign-pause-fixed/`, and
`build/native-settings/pause-fidelity-pause-fixed-tests.log`.

The test window was deliberately launched at 640×480. Normal launches use the
display's aspect at startup, with 480-line rendering. The current renderer retains
that startup aspect when the window is resized; dynamic aspect changes remain a
separate renderer improvement.
