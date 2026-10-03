# PB Options

PB Options provides explicitly selected multiplayer practice aids: an
elapsed match timer, spawn markers, timer announcements, and optional silent
movement or weapon equip sounds. All modifications are **off by default**.
The host selects the options for the whole match.

## Game type editor and pause menu

In **Multiplayer → Edit Gametypes → select a game type**, **PB Options** appears
below **Indicator Options**. The submenu is titled **Performance Options**.
Its native game widgets use the existing menu fonts, navigation and help text.
Choose a preset or change the options individually. Game-type selection cards
show **PB options active** whenever the saved variant enables any option.

| Preset | Match Timer | Spawn Markers | Timer Sounds | Movement / Weapon Sounds |
| --- | --- | --- | --- | --- |
| Stock | Off | Off | Off | Normal / Normal |
| Practice | On | On | On | Normal / Normal |
| Custom | Individually selected | Individually selected | Individually selected | Individually selected |

The preset is a convenience over the option bits. Reopening the page shows
Stock when all modifications are off, Practice when just the original three
aids are on, and Custom for any other selection. There is no separate saved
preset identifier. Selecting either Silent rule therefore shows Custom.

Changes on this page are staged. **Accept** puts them into the game type being
edited; finish the existing **Save Changes** flow to persist that variant.
The existing variant copy, rename and save-as paths retain the options. Editing
a saved variant does not immediately change a running match.

During multiplayer play, open the native pause menu and select **PB Options**.
The host can stage a preset or individual changes and choose **Apply** to update
the session. Leaving without Apply discards that panel's draft. Joining players
see the host's current choices with the controls disabled. Session changes do
not write the saved game type back to disk; use Edit Gametypes to save a
preset for later.

The editor and pause pages are native game widgets registered in the loaded
cache's runtime UI table. Retail map files are not rewritten. PB Options uses
these menu entries; there is no separate overlay or Y-button shortcut.

## Match timer

The timer displays elapsed match time as `MM:SS` using the game's HUD font and
color. Under **Game Settings → Video**, choose Top Center (default), Bottom
Center or Bottom Right, and a size from 50% to 100% (default 100%). Placement is
relative to each local player's viewport, including split-screen. It is hidden during cinematics
and the postgame display. Enabling it partway through a match shows the time
already elapsed rather than starting a new clock.

The host uses its simulation tick count. A joining client uses the latest
received host tick, including after a late join; it does not substitute its
local clock before synchronization or during packet loss. A client without a
host tick yet does not show the timer. The display can therefore briefly hold
its last value while host updates are delayed.

The simulation remains **30 Hz**. This option adds a display; it does not change
tick rate, rendering rate, match duration, scoring, weapon behavior or player
movement. It does not execute the source maps' timer scripts or item timers.

## Timer sounds

**Timer Sounds** is independent of the visible clock. It uses the same host
simulation clock and the common NHE talking-timer schedule: beeps at `:20`,
`:30`, `:40` and the next `:00`; spoken warnings at `:30.5` and `:40.5`; the
countdown from ten at `:50` through one at `:59`; then the minute at `:00.5`.
The source recording sequence repeats after thirty minutes.

**Game Settings → Audio → Timer Audio** supplies separate local Countdown,
Beeps, Minute Announcements and Item Cues toggles, plus Timer Volume. These
preferences never enable audio when the host's Timer Sounds rule is Off.
Countdown, beeps and minute calls default On; Item Cues default Off.

Item Cues announces scheduled rocket, active-camouflage and overshield waves.
The runtime reads the map's actual spawn periods, game-type filters and active
weapon/powerup remaps. It skips mixed random collections. These are schedule
reminders, not pickup tracking or a promise of successful object allocation.
Simultaneous item names play once each between common timer calls, using the
recordings' exact duration; a reminder that cannot fit within six seconds is
dropped. A missing optional item recording is skipped. No scripts, gameplay
random values or new gameplay objects are involved.

Joining, enabling the option, clock reversal and long update gaps do not replay
old announcements. Changing local cue groups also clears pending calls without
backfilling. Repeated host ticks do not repeat cues. Turning the option
off or leaving the map stops an active announcement. Playback uses the existing
audio mixer, output device, audio-enabled setting and master volume.

The recordings are a separate local pack at `sounds/performance/` beneath the
existing game data root. They work with stock maps without changing map files
or checksums. The importer [`import_performance_audio.py`](../tools/import_performance_audio.py)
converts already extracted, user-owned NHE sound tags into bounded PCM WAVs and
writes source/output hashes. It preserves existing destination files and does
not download assets. The recordings themselves are not committed to this repo.
The local installation includes the pack. A host without the required recordings
cannot enable Timer Sounds; a peer without them omits timer-audio support while
retaining the other capabilities. The debug console reports whether the
recordings are installed.

## Movement and weapon sounds

**Movement Sounds: Normal / Silent** controls footsteps, shuffling, sliding,
jump and landing sound events. **Weapon Sounds: Normal / Silent** controls
equip, ready and switch sounds, including put-away when authored by the map.
Both are saved game-type rules and host-controlled live settings. Normal is
the default. These rules do not alter weapon draw time, firing, reloads, ammo,
movement physics or simulation rate.

The implementation tracks the event that created each sound, including delayed
effects, particles, first-person animation frames and third-person ready or
put-away actions. It does not infer a role from a filename or a broad sound
class. A shared tag used for firing or reloading therefore keeps that occurrence
audible. Silent changes the final impulse gain while preserving sound creation,
effect visuals, random-number consumption, weapon state and fire-ready timing.
Normal restores the original gain, including for a still-playing sound.

The affected stock weapon inventory is assault rifle, pistol, shotgun, plasma
rifle, plasma pistol, rocket launcher, sniper rifle, needler, flamethrower,
oddball and flag. Map-authored ready and put-away sounds on custom weapons use
the same event policy; absent recordings remain absent. Verification evidence
and remaining gates are recorded in [the first-three delivery log](pb-first-three.md).

## Spawn markers and supported maps

The original scenery-marker audits and runtime checks cover these converted
Xbox v5 caches:

| Map | Cache name | Reviewed marker placements |
| --- | --- | --- |
| NHE Prisoner | `h1pb_prisoner` | 24 |
| Downrush | `downrush` | 19 |

The engine evaluates marker eligibility per placement. A supported marker must
have a scenario object name beginning with `spawn_marker`, refer consistently
to a scenery placement and its palette, and use the reviewed
`scenery\spawn_marker_nhe\spawn_marker_nhe` tag. That tag must be a static scenery
model with no physics, collision model, animation graph, creation effect,
attachments, widgets, runtime functions or active function modes. A similar
name alone is insufficient.

For maps without eligible NHE scenery, including retail Chill Out, the engine
draws green arrows from the map's existing player-start positions and facing
directions. It filters starts using the game's normal game-type matching and
renders only the active BSP. Arrow geometry is part of the engine code; no
per-map metadata pack, replacement map or object tag is needed. It uses the
existing depth-tested drawing path and creates no gameplay objects.
These arrows are hidden while native menus are open to keep menu text clear.

The imported maps retain their initial training-object cleanup. After map
scripts run, each peer creates eligible missing markers locally when the host
enables the option. Scenery is not part of the distributed object transport.
Marker creation preserves the gameplay random seed, and the created objects
are non-colliding and immune to damage. Disabling the option deletes only
objects owned by this feature, checked by full datum identifier, definition
and name. It does not adopt or delete unrelated scenery, and it never restores
the source maps' `randoms` training objects.

These results apply to the converted v5 maps. PB Options does not add support
for the original PC v7 caches, import the Performance Build engine, or enable
additional Performance Build game mechanics.

## Saved variant format

[`performance_variant.h`](../source/game/performance_variant.h) encodes the
options in six existing padding bytes of `universal_variant`. The variant
remains 104 bytes and uses the existing signed save format and editor dirty
comparison. The extension is part of normal whole-variant copies and network
settings; no application environment variable or separate preferences file is
introduced.

| Field | Enabled extension value |
| --- | --- |
| `pad0`, `pad1`, `pad2` | ASCII `P`, `F`, `O` |
| `pad4` | Format version `1` |
| `pad5` | Flags: timer `1`, spawn markers `2`, timer sounds `4`, silent movement `8`, silent weapons `16` |
| `pad6` | Flags XOR `0xA5` |

Stock/off writes all six bytes as zero. Old padding, an unknown format version,
unknown flag bits or a damaged check byte decode as all options off. The check
byte detects malformed extension data; the existing save signature mechanism
still handles the saved variant. `game_variant.flags` is not repurposed.

## Host authority and v11 compatibility

The client's reliable connection announces supported subsets before its normal
join request: the original timer/marker mask, the timer-audio generation, then
the complete capability set. Earlier PB hosts retain the newest subset they
understand. An unextended v11 host ignores those unknown data messages.
The updated host keeps capabilities per connection slot and clears them when
the slot is removed or reused.

All options off preserves stock v11 session admission in either direction for
original-rule games. When any option is enabled, the host advertises extension
version `0x800B` alongside capability flag `0x04`. A stock v11 client displays its existing
update-required explanation. The host also checks capability at admission, so
a stale advertisement or direct join cannot bypass the requirement.

The v11 settings record adds 28 bytes; v10 and PB-v10 (`0x800A`) must update.
Capability flag `0x02` is now upstream's in-progress flag, so PB uses `0x04`.
The reliable option messages and saved variants are unchanged. Unsupported active
PC options and mixed five-plus-player infinite-grenade rules are refused; see the
[current protocol review](upstream-review-2026-10-03.md). The v10 runtime evidence
below remains historical evidence, not a v11 cross-platform test.

Enabling an option, selecting an enabled saved variant, and starting the match
check the connected peers. An unsupported existing peer causes the host's
change to be refused with an explanation. Joining clients cannot change the
host's option state.

The normal reliable settings record carries the variant before begin-game,
both for lobby starts and late joins. Live host changes use a separate reliable
control, also sent to clients that are loading. Clients accept it only from the
established host's reliable stream; UDP controls do not change options. Local
host state remains authoritative across lobby transitions, and leaving a
client session clears the effective options.

## Debug controls and device settings

Press **F2** for the existing developer console. `pb` shows settings and help;
`pb stock` disables all options and `pb practice` enables all three. Use
`pb timer on`, `pb markers off`, or `pb audio toggle` for individual controls.
Those accept `on`, `off` or `toggle`. Use `pb movement silent` or
`pb weapons normal` for sound rules; these accept `normal`, `silent` or `toggle`.
Tab completion is available. Host authority
and peer capability checks are identical to the pause menu. These are session
changes; save a game type in Edit Gametypes for future matches.

The diagnostic `performance_options [0..31]` is available, with flags timer `1`,
markers `2`, audio `4`, silent movement `8` and silent weapons `16`. Status also
reports per-map sound provenance, muted dispatch counts, timer cue preferences
and successful cue dispatch counts; these are diagnostic
counters and do not by themselves prove the audible output.

**Settings** on the main menu opens **Profile Settings** (the original
profile picker) and **Game Settings**, with native Audio and Video pages.
Audio includes master, music, effects and dialogue volumes, Menu Music, and a
Timer Audio submenu. Video includes Fullscreen, VSync, Smooth Motion, Timer
Position and Timer Size. Accept saves and applies the parent page; Cancel
discards its draft. Accept inside Timer Audio keeps its changes in the Audio
draft; Audio Accept persists them, while parent Cancel discards them. The pages preserve unrelated
configuration and report save failures. See
[`native-settings.md`](native-settings.md) for controls and persistence details.

## Validation and limits

Recorded October 2, 2026. The runtime checks used real native Mac processes with
isolated saves, the opt-in local console, and encrypted invite connections on
one Mac. Each test kept at most two game instances active; the late-join test
replaced its temporary second peer after the match started.

| Check | Evidence |
| --- | --- |
| Installed native editor: PB row, fitted text, Stock/Practice, Cancel, Accept, Save Changes and reopen; valid flags on disk | [`native-ui-check/validation.json`](../build/performance-options/native-ui-check/validation.json) |
| Expanded installed UI: both Settings branches, Music Cancel/Accept and config preservation, card status, independent Timer Sounds and saved flags `7` | [`expanded-ui-check/validation.json`](../build/performance-options/expanded-ui-check/validation.json) |
| Retail Chill Out: all eight option combinations synchronized; 25 Slayer markers on both peers, arrows visually confirmed, client mutation refused; three-minute runtime with audio enabled | [`stock-audio-smoke/validation.json`](../build/performance-options/stock-audio-smoke/validation.json) |
| Native pause submenu: fitted heading/rows/footer; Apply disabled the timer on both peers (`7 → 6`); F2 `pb timer on` restored the clock and reported installed recordings | [`stock-pause-diagnostic/ui-validation.json`](../build/performance-options/stock-pause-diagnostic/ui-validation.json), [`runtime report`](../build/performance-options/stock-pause-diagnostic/validation.json) |
| NHE Prisoner: 24 markers on both peers; all timer/marker combinations; client mutation refused | [`prisoner-smoke-2/validation.json`](../build/performance-options/prisoner-smoke-2/validation.json) |
| Downrush: actual in-progress join at host tick 175; timer sampled at 188 on both peers; 19 markers; live `3 → 1 → 2 → 0 → 3 → 0` updates; client mutation refused | [`downrush-latejoin-3/validation.json`](../build/performance-options/downrush-latejoin-3/validation.json) |
| Updated host with options off admits stock v10; enabling is refused and the session continues | [`compatibility-v10-1/stock_session/validation.json`](../build/performance-options/compatibility-v10-1/stock_session/validation.json) |
| Enabled updated host rejects stock v10 with an update explanation; updated client joins a stock v10 host | [`compatibility-v10-2/validation.json`](../build/performance-options/compatibility-v10-2/validation.json) |

The passing reports contain no runtime faults. These are local generated
artifacts, not files required by a checkout or shipped with the game. They record
the guest hashes actually tested: Prisoner used `0fa61f1afafb…`; the later
Downrush and compatibility checks used `dcdb2abc05ce…`. The saved unextended v10
guest used `6f525b592908…`. Expanded UI and retail Chill Out checks used
`131ff620b6b8…`. The Chill Out run enabled the mixer with muted master output;
it verifies runtime behavior but is not an audible listening check.
The pause/F2 check used `d7d2e98ad8fd…` with a temporary menu-event trace;
that trace was removed after confirming the native event path. A stale UI
capture affected an earlier manual attempt, so the successful check used a
fresh capture session. The final source also hides stock spawn arrows while
menus are open, covered by the runtime fixture, and preserves the invoking
controller for split-screen PB menus, covered by the pause fixture.

[`test_performance_variants.py`](../tools/test_performance_variants.py) exercises
the format, malformed extensions, editor dirty detection and variant save/copy
flows using production functions with storage/signature fixtures.
[`performance_network.c`](../port/macos/tests/performance_network.c) covers wire
validation and admission/version combinations. The runtime runners are
[`macos_performance_smoke.py`](../tools/macos_performance_smoke.py) and
[`macos_performance_compatibility.py`](../tools/macos_performance_compatibility.py).
Run multiplayer runners sequentially because the game uses fixed ports.

Focused production-code fixtures cover native UI construction and tag lifetime,
all eight saved option combinations, host and audio-pack capability gates,
the announcement schedule and mixer controls, stock-map spawn filtering and
geometry, console commands, and TOML write failure/comment preservation.
The importer tests compare decoding with the game's Xbox ADPCM algorithm and
reject malformed sound tags and existing output files.

These results do not establish Windows-binary interoperability, two physical
machines or networks, Internet/NAT coverage beyond the same-Mac invite path,
long-session stability, physical-controller navigation or reference-Xbox
fidelity. Network runtime reports exercise options through the native diagnostic
command. The separate editor and pause checks use keyboard navigation in the
installed app and isolated saves; pause Apply was additionally checked on both
peers through their read-only diagnostic status.
