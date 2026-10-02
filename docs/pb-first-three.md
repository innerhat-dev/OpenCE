# First three Performance Build ports

Scope: the first three ranked deliveries in
[`pb-feature-inventory-and-porting-priorities.md`](../../h1-competitive-macos/docs/pb-feature-inventory-and-porting-priorities.md),
requested October 2, 2026. These are timer refinements, movement-sound controls,
and weapon equip/switch sound controls. The existing timer, spawn markers and
timer audio are the starting point, not three substitutes for that scope.

## Confirmed scope

The user confirmed that movement and weapon sounds are saved, host-controlled
match rules, selectable before and during a match. Both default to Normal.
Movement Silent covers footstep, shuffle, slide, jump and landing events.
Weapon Silent covers existing equip, ready and switch sounds, including a
put-away sound when the map supplies one; it does not restore absent recordings.
The existing Practice preset remains timer, markers and timer audio (flags 7).
Either new Silent rule makes the selection Custom.

The user also confirmed that timer cue preferences are local to this Mac and
saved under Game Settings → Audio. The existing host-selected Timer Sounds
rule still determines whether the match permits timer audio.

The unchanged variant ABI stores the new rules as bits 8 and 16. Capability
announcements preserve compatibility with peers supporting masks 3 and 7; an
older peer cannot join or enable a rule it does not implement.

The timer scope includes all requested refinements: independent Countdown,
Beeps, Minute Announcements and Item Cues toggles, plus local Timer Position
and Timer Size. The first three cue groups default On, item cues default Off,
and presentation defaults to Top Center at 100%. Timer Audio is a child of
Audio; position and size are under Video.

Item reminders announce deterministic rocket, camo and overshield spawn waves
from the loaded map and active variant. They are reminders of the schedule,
not a guarantee that an uncollected item is available. Mixed random collections
are omitted, and no source-map scripts or gameplay RNG are executed.

Original sounds remain the baseline. Sound controls must preserve firing,
reload and impact audio, weapon animation and fire-ready timing, ammunition,
and the 30 Hz simulation. Native pages reuse existing game widgets, fonts,
artwork, contextual help and Accept/Cancel conventions.

## Current evidence

The base implementation is documented in [performance-options.md](performance-options.md)
and [native-settings.md](native-settings.md). New source-level fixtures verify
all 32 shared option combinations, the unchanged 104-byte save ABI, capability
checks against the previous mask-7 build, native parent/child drafts, local
preference persistence, event provenance, and timer scheduling/rendering.

Two real Mac peers passed the five-phase Normal / Silent Movement / Silent
Weapons / Both Silent / Normal Restored matrix on Blood Gulch and Downrush.
Both peers produced movement, ready and unrelated voices throughout; only the
selected event roles accumulated mute counts. Existing ammo consumption,
firing and repeated respawns continued. Reports:
`build/pb-first-three/sound-runtime-bloodgulch-desktop-20261002/validation.json`
and `build/pb-first-three/sound-runtime-downrush-desktop-20261002/validation.json`.

The 76-case PCM sample matrix covers stock Prisoner and converted Downrush,
Octagon and PB Prisoner. Selected movement/ready samples become exact silence;
normal, restored and shared-tag unrelated-event samples are byte-identical.
This exercises the production decoder/gain/mixer functions with owned samples;
it is not an in-game audio recording or a subjective listening test. Evidence:
`build/pb-first-three/audio-sample-matrix/manifest.json`.

Real previous-generation peer checks passed admission and live-change refusal
for unsupported rules, as well as an updated client joining an earlier host:
`build/pb-first-three/earlier-peer-check/live_gate/validation.json` and
`build/pb-first-three/earlier-peer-check-final/validation.json`.

The five-cache item audit is reproducible with `tools/audit_performance_items.py`:
`build/pb-first-three/item-schedule-audit.json`. Blood Gulch rockets use 90s;
its 180s shield/invisibility collection is random and receives no specific
callout. Downrush CTF camo uses 120s. Converted Race schedules use 30s. Octagon
has no normal-weapon-set power-item waves. The runtime uses these authored
periods and actual variant remaps, with no map-name lookup table.

## Completion evidence

| Delivery | Required evidence |
| --- | --- |
| Timer controls | Selected controls persist and apply through native menus; elapsed host time, late joins, live changes and each local viewport remain correct; no repeated or historical cues; all-off behavior preserved. |
| Movement sounds | Footstep, jump and landing on/off comparisons on stock and representative imported maps; other sound categories preserved; agreed persistence and multiplayer authority; restoration after map/mode changes. |
| Equip/switch sounds | Explicit affected weapon/event list; first equip, ordinary switch and respawn comparisons; draw animation, fire-ready timing and ammunition unchanged; agreed persistence and multiplayer authority. |
| Native menus | Original layouts and help conventions; keyboard/mouse selection; Accept, Cancel, save and reopen; main-menu and in-game access where appropriate to the agreed scope. |
| Installed app | Successful build, signature and BuildInfo verification, installation preserving saves/config, and a fresh launch from Applications. |

Tests must exercise production classification and sound paths. Captured output
can prove sample-level suppression/preservation; subjective listening is a
separate check and must not be claimed from log messages alone.

## Integration verification

The final focused suite passed 51 unique tests (48 in
`build/pb-first-three/final-focused-tests.log`, plus the runtime lifecycle test
after the mixer-completion regression was added, and a saved-log regression
for the timer runner's late-join message, plus the new PB mouse regression).
The final menu fix passed 11 focused checks in
`build/pb-first-three/final-mouse-tests.log`. Item playback waits for both
its reserved schedule interval and actual mixer completion. Queued item cues
therefore cannot replace an unfinished recording after a short host-clock jump.

The final timer build passed the real-peer Prisoner check in
`build/pb-first-three/timer-runtime-prisoner-20261002/validation.json`.
The host selected item cues only; the client selected countdown, beep and minute
cues only. A fresh late join produced no historical minute announcement. By
125 seconds the host had played five item reminders (one rocket, two camo, two
overshield), while the client had played 12 countdown, four beep and one minute
cue. Disabling Timer Sounds on the host stopped both peers' counters through
185 seconds. All 31 checks passed; output volume was zero for this instrumented
test, so it establishes scheduling and authority rather than subjective sound.

Visible in-game checks confirmed the seven PB rows, live application of both
Silent rules to both peers, Cancel restoration, local Timer Audio child/parent
draft behavior, and a smaller bottom-right timer after Video Accept. Evidence:
`build/pb-first-three/native-pause-check-final/ui-validation.json`,
`ui-persistence.json` and `ui-silent-rules.json`. The peer harness passed after
the UI changes with both peers at flags 29 and the same simulation tick.

Main-menu checks verified Timer Audio keyboard Accept/Start navigation, exact
preservation of untouched 62.5% values, Video Cancel, and both sound rules saved
and reopened as Silent. The isolated save contained the valid flags-31 extension.
A final mouse check found PB arrow artwork outside its hit rectangle; the
existing native-arrow hit expansion now also covers all six PB spinners.
Both sound-rule arrows changed their values in the rebuilt app, and Cancel
restored the saved selection. The regression exercises all 12 arrows and fails
when only that fix is removed. Evidence:
`build/pb-first-three/native-ui-check/validation.json`.

The installed guest is
`21dc8918243e2e88748a7fd6937bec1303cff2481bdf68be7c6f305ac2ac4a50`.
The build completed with `--install`; the installed app passed
`codesign --verify --deep --strict`, and its BuildInfo records the same guest.
Build output is `build/pb-first-three/final-mouse-build.log`. A fresh Finder
launch of `/Applications/Halo CE Universal.app` reached the original main menu;
the normal save log confirms this final guest and the normal data/save paths.
The timer and pause reports used guest
`29dad4090f332a7f8cfe417d179fb62c65cb52449a0cd1a1d8165a2daedc673b`;
the only subsequent production change was the PB editor mouse hitbox fix.
The sound-rule runtime reports above used the earlier integration guest
`223d026ef314b682b39f5a827fd114c4c92e58499d8551724f7f6637af008389`;
its event classification and shared-rule implementation are unchanged in the
final timer build. This is a local build from working-tree changes, not a
published release or a pushed commit.
