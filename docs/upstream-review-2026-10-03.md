# Selective upstream review: protocol version 11

Reviewed October 3, 2026 from this fork's `main` at `6c1f1ae8`, through
upstream `23b542601f2ca505c7a0143703e92fbda6075e18`. The previous reviewed-through
revision was `d1c7243cb20eab4488efa1266e259b1f4d5240f6`.

The last full upstream integration remains `c55e4e2b` / Apple merge
`aabe44417431c36e46aaa385a69a89a3c9d685c0`; selective v10 integration was
`ea4dec3c28fcb4975ad36718c344bf5205b4c5eb`. This v11 addition is a focused
selective port, with no upstream merge. Local integration commit:
`694cc79d48654d862d3ecda51e71ea559f93bd2d`.
The [fidelity policy](xbox-fidelity.md) remains in force.

## Protocol and compatibility boundary

Upstream's `network_distributed.c` and `.h` have **no changes** across these seven
commits. Version 11 adds the PC gametype-options record to the game settings;
it does not introduce a new prediction, hit-reporting or transport algorithm.
The complete 28-byte options record is inserted after `number_of_games_played`
and before `local_data`. A 128-player/128-machine settings record is now 13,120
bytes, still carried by four reliable fragments. Map identity is still its
existing name/version record; PC menu map indices are not part of the new wire
format and are not required to play the same map across platforms.

This fork sends upstream's original-rule option defaults whenever its selected
variant or playlist stage changes: no additional time limit, friendly fire on,
no betrayal penalty or vehicle respawn override, no automatic team balancing,
category loadout, and the variant's radar/vehicle sets. It reads the complete
record but refuses active PC options it does not implement before changing the
client's game record or precaching a map. The refusal names the unsupported
option and asks the host to select original Xbox options. Every complete settings
update takes that path, including lobby changes, later matches and late joins.
Inactive per-vehicle counts, primary/secondary weapons and padding are accepted;
they do not affect category loadouts or non-custom vehicle sets. Extended PC
weapon-set values 11–13 are refused.

The upstream in-progress advertisement bit `0x02` is sent for loading, play and
postgame. This formerly overlapped the fork's PB capability bit, so the latter
is now `0x04`. PB sessions with any option enabled advertise `0x800B`, while
options-off sessions advertise stock v11. The existing reliable HPFO messages,
variant extension, host authority and capability-mask `0x1F` combinations are preserved.
Older v10 and PB-v10 sessions (`0x800A`) are incompatible with the longer settings
record and must update. Unextended v11 clients can join options-off original-rule
games; enabling PB options still requires supporting peers.

Upstream keyboard input also sends action-only bit 15. This fork recognizes,
latches and removes that bit before passing control flags to units, so an upstream
player's action key does not unexpectedly reload when this fork is the host.
The fork's local keyboard/controller mapping is preserved. No replacement menus,
fonts, scoreboard, aim-assist policy or local controls configuration is imported.

Upstream `23b54260` changes infinite grenades with five or more players. This fork
keeps its existing Xbox cutoff. Received settings from an unextended upstream
host with that combination are refused. A fork host checks peer capability at
start, variant changes and each player addition (including late additions),
refusing a mixed-build game that would cross the five-player boundary with
Infinite Grenades selected. Fork-only games continue using the existing rule.
Cross-build testing should leave Infinite Grenades off for five or more players.

## Per-commit decisions

All seven new actual diffs and their relevant dependencies were inspected. This
table records reviewed-through separately from integrated behavior.

| Upstream commit | Actual change | Decision and reason | Validation / integration status |
| --- | --- | --- | --- |
| [`80d30410c8db28f4008b92f4e012a1b046ece14e`](https://github.com/cybersecurity/halo-ce-universal/commit/80d30410c8db28f4008b92f4e012a1b046ece14e) | Desktop Mesa Intel workaround: configurable GPU memory barrier every three draws, detected from renderer name; adds a GL entry point and configuration/environment setting. | **Defer.** Useful platform-specific stability candidate, independent of v11. Apple's GLES path compiles it out; a Linux GPU comparison and a separately authorized configuration choice are needed. | Actual draw/config/GL diff reviewed; not integrated. |
| [`c9ee319ab5f2964a32372fffdc7756111e39727d`](https://github.com/cybersecurity/halo-ce-universal/commit/c9ee319ab5f2964a32372fffdc7756111e39727d) | Large PC-menu replacement, XML/parser/assets/build dependencies, runtime settings/input bindings, gametype editor/save extension, new game-rule implementations, and v11 settings/advertisement/input changes. | **Partially adopt.** Port the entire v11 wire record, original-rule defaults, in-progress metadata, and received action-only input prerequisite. Refuse unsupported active settings. Exclude PC menus, added engine modes, settings/bindings, save extension, XML/Expat/assets and renderer/audio rewiring. | Focused working-tree port; tests below. Existing native Mac menus and PB save/network behavior preserved. The port does not claim every upstream PC mode is supported. |
| [`2b0103a0ef2f46f3713d7e045436c5283668f9a6`](https://github.com/cybersecurity/halo-ce-universal/commit/2b0103a0ef2f46f3713d7e045436c5283668f9a6) | Adds Slayer kills-to-win 75/100/150/200/250/500 to the Xbox-style editor and spinner descriptions/layout. | **Exclude.** Independent gametype-editor expansion; no new network field or simulation implementation. | Actual widget/event/data-input diff reviewed; not integrated. Existing generic score field is retained. |
| [`383355381c3f92ae8ce6c9c79cbe84924856aa2f`](https://github.com/cybersecurity/halo-ce-universal/commit/383355381c3f92ae8ce6c9c79cbe84924856aa2f) | Adds those score choices to the new PC menu XML/generator/editor. | **Exclude.** Depends on excluded PC-menu replacement and is unnecessary for the v11 record. | Actual strings/generator/menu-function diff reviewed; not integrated. |
| [`e8e0c2215ab6871bbe6f855f67b3459d94817b35`](https://github.com/cybersecurity/halo-ce-universal/commit/e8e0c2215ab6871bbe6f855f67b3459d94817b35) | Windows game compiler searches `port/linux/include` with `-iquote`, finding PC menu/keyboard headers without treating neighboring C runtime wrappers as system headers. | **Defer.** Fixes the excluded menu/bindings dependency. The selected v11 input bit is defined in the already-included `source/units/units.h`; this port adds no bare Linux-port header includes to game units. | Four-line actual build diff reviewed; not required or integrated. Windows/Linux execution remains a separate validation gate. |
| [`62b630a2610e7c0df88ffa43d6f03914cb35345e`](https://github.com/cybersecurity/halo-ce-universal/commit/62b630a2610e7c0df88ffa43d6f03914cb35345e) | Removes fuel-rod/flamethrower custom-loadout menu choices, sanitizes old PC options and further remaps unfinished gravity-rifle/flamethrower weapons to rockets. | **Exclude.** Independent weapon/loadout policy. Custom loadouts are refused here; the fork's weapon-remapping behavior and saved variant format stay intact. | Actual menu/engine/header/save/generator diff reviewed; not integrated. Shared map content still needs compatible object/tag assumptions. |
| [`23b542601f2ca505c7a0143703e92fbda6075e18`](https://github.com/cybersecurity/halo-ce-universal/commit/23b542601f2ca505c7a0143703e92fbda6075e18) | Allows infinite grenades at every player count, and completes unarmed-melee damage fallback and host hit-validation tracking for custom no-weapon loadouts. | **Exclude.** Changes existing Xbox rules. No-weapon loadouts are unsupported; mixed five-plus-player infinite-grenade sessions are gated instead of changing the baseline. | Actual engine/units/network-damage diff reviewed; not integrated. Client and host admission gates are tested. |

The October 1–2 presentation, scoreboard, label and moderation exclusions remain
as recorded in [the v10 review](upstream-review-2026-10-02.md). No earlier excluded
commit is a prerequisite for the selected v11 record or input handling.

## Validation and limits

`python3 -m unittest tools.test_network_v11 tools.test_network_pings
tools.test_performance_network tools.test_performance_variants`: **11 tests passed**.
The new production-source harness runs with AddressSanitizer/UndefinedBehaviorSanitizer
and checks exact guest-layout offsets/size, original defaults, every options-byte
boundary, inactive fields, PB namespace separation, old-version refusal, complete
fragment reassembly, bad-size/order/bounds handling, and refusal before precache
or live state mutation. Existing ping codec/role/staleness tests and PB host
capability/assets/saved-selection checks passed; host grenade-rule thresholds
are covered by the PB authority fixture. `git diff --check` passed.

The native ARM64 guest and Mac app built successfully, and the installed app
passed strict signature verification. Standalone runtime probes passed for
rebasing, allocation, clocks, synchronization, audio and network transports.
Two real instances on one Mac completed two consecutive Slayer matches over
the encrypted invite transport, with bidirectional updates and no assertions
or faults (`consecutive-v11-final/validation.json` in the ignored local review
output). Both used the original reference profile and separate data/save roots.
This verifies fork-to-fork protocol 11 on one Mac. Actual upstream-v11
interoperability, Windows/Linux/Android devices, Internet loss/jitter timing and
controller gameplay still require separate runtime evidence.
The pre-existing fidelity reports remain unchanged and document already-present
input-timing differences from the Xbox reference; this patch does not establish
retail parity or undo those historical differences. No matchmaking service,
account system or peer-to-peer map transfer is added by this protocol update.
