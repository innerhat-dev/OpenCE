# Community map source review

The JukkisP H1 Performance Build 2.0 Public Beta 3 package contains 40 map caches
and 40 corresponding source scenarios. All 40 scenarios are reviewed for the
`stock-xbox-ntsc` import profile in
[`port/maps/jukkis-beta3.json`](../port/maps/jukkis-beta3.json). This extends the
initial Downrush, Atlas and Octagon pilot to the other 37 maps.

## Evidence and method

The review used the locally source-built Invader toolchain at commit
`7d25a855f5ef9e4ab8407abf490b21f8780abf27`. The `invader-edit` and
`invader-recover` binary hashes were checked against the recorded toolchain
manifest before reading the source tags. Downloaded executables were not run.

For every scenario, the review recorded its source path and SHA-256, the original
cache SHA-256, compiled script names, recovered source-file hashes, object names,
and scenario/AI/device counts. Recovered script declarations exactly matched the
compiled script names. Script bodies were compared as whitespace-normalized
variants, then the distinct bodies and differences were read. The decision was
based on their operations, not just their names.

Each checked-in map entry pins the complete source scenario with
`scenario_sha256` and enumerates its exact `optional_scripts` and
`cleanup_prefixes`. The importer rejects a changed scenario or an unexpected
script. Those hashes tie this review to these particular source files; a newer
package requires another review. The original three entries retain the same
hashes and script decisions.

Local detailed evidence is in the ignored directory
`build/community-maps/full-collection-review-20261002/`: `source-review.json`,
`script-variants.json`, recovered scripts, and the review scripts/logs. Proprietary
map assets and lengthy recovered source are not checked into this repository.

## Script decisions

All recovered scenario scripts implement optional NHE host setup, training aids,
timer presentation or extra garbage collection. No required authored traversal,
door, teleporter or objective script was found.

| Category | Reviewed behavior | Stock-Xbox import decision |
| --- | --- | --- |
| `player_count`, `host_setup` | Detect NHE mode through named vehicles; optionally move a neutral host into a vehicle, pause input for a countdown, fade the screen and show training aids | Remove |
| `activate_*waypoint*`, `deactivate_*waypoint*` | Show or hide training HUD pointers | Remove |
| `beep_every_ten_sec`, `announce_min`, `show_min`, `combined_tens`, `timer_tens`, `timer_minutes`, `nhe_combined_timer` | Audio/HUD clocks and powerup announcements; no actual equipment spawning or relocation | Remove |
| Octagon `octa_garbage_cleanup` | Extra garbage collection every 150 ticks | Remove |
| Initial `spawn_marker` and `randoms` cleanup within host setup | Remove training objects that the source only recreates for training mode | Retain as a small separate startup script |

Thirty-seven maps share the same normalized full `host_setup` body. Outbound
adds countdown titles, while the two Octagons have smaller NHE-only variants.
Birdhouse/Patrace, Hang Em High/Hangman, Weld, Temple, Wizard and Outbound vary
the powerup announcement schedule or waypoint locations. Outbound uses team
waypoint functions; Temple and Wizard include extra powerup pointers; Weld has a
separate camo pointer cleanup. These variants do not implement map traversal.

Octagon B has neither training-object cleanup calls nor matching object names,
so its cleanup list is empty. Cleanup expressions for the other maps match the
reviewed source behavior. Other authored objects, including doors, Weld's
`bounce` object and Patrace's turret objects, are outside those expressions.

All 40 scenarios have zero AI encounters, child scenarios, command lists, AI
script references and AI conversations. This review found no required authored
script to preserve alongside the cleanup script.

## Stock map names and authored devices

Four package cache names collide with retail maps. They must be imported under
independent names so the stock versions remain available:

| Package map | Import ID |
| --- | --- |
| `chillout` | `h1pb_chillout` |
| `hangemhigh` | `h1pb_hangemhigh` |
| `prisoner` | `h1pb_prisoner` |
| `wizard` | `h1pb_wizard` |

Some maps contain authored device machines despite having no required gameplay
scripts. Birdhouse has one outer-door machine; Temple has three machines with
A10 device references; Weld has two fan/light machines with custom references;
Wizard has four light machines. Preserve their scenario instances and device
dependencies. Their behavior is driven by tags and engine logic rather than the
removed NHE scripts. Stock-first dependency resolution can substitute a baseline
stock device tag, so doors, lights and fans require observation during playtests.

## Validation limits

This source review authorizes attempted content conversion. It does not prove
that a cache compiles, loads, preserves lighting or works in every game mode.
Generated caches still need the importer's V5 NTSC header, size and tag-arena
checks, followed by runtime validation. Movement, authored devices, item
placements, audio, controller play, long sessions and multiplayer behavior are
separate checks. Importing this content does not authorize competitive rule,
weapon or presentation modifications in the original-Xbox engine baseline.
