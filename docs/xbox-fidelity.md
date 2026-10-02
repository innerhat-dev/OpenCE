# Original Xbox fidelity

This fork targets original Xbox Halo: Combat Evolved NTSC gameplay on native
macOS, with controller support and separately imported community maps. Matching
decompilation, core performance, stability and platform improvements should stay
current through selective upstream review. Original game presentation and rules
remain the baseline; an upstream change is not accepted merely because it is new.

## Pinned baseline and upstream review

The last integrated upstream revision is `c55e4e2b` (build 64), merged into the
Apple fork as `aabe44417431c36e46aaa385a69a89a3c9d685c0`. Keep that baseline until
a specific later change has been reviewed and validated. This is a record of the
last integration, not a permanent freeze. During upstream-update work, review all
changes since the last recorded review so useful core improvements are not missed.
Fetching upstream does not authorize merging it. Do not merge upstream `main`
wholesale; select focused changes and split mixed commits when necessary.

The last review covered new commits through upstream revision
`f2ba71d9af4c6fc65d7419cc22e8f4899b16da88` on October 1, 2026. The following
additions were inspected and excluded; neither is integrated:

| Upstream change | Category and effect | Decision and reason | Validation / integration status |
| --- | --- | --- | --- |
| [`0182da817285b67eee8264663ca79f7c32d66b5e`](https://github.com/cybersecurity/halo-ce-universal/commit/0182da817285b67eee8264663ca79f7c32d66b5e) | Presentation / branding: high-resolution text and OpenCE titles. | Exclude: keep the game data's bitmap fonts and original menu titles. | Diff reviewed; not integrated; no adoption tests required. |
| [`f2ba71d9af4c6fc65d7419cc22e8f4899b16da88`](https://github.com/cybersecurity/halo-ce-universal/commit/f2ba71d9af4c6fc65d7419cc22e8f4899b16da88) | Presentation / player information: names above players' heads. | Exclude: preserve original target-name/teammate-indicator behavior. | Diff reviewed; not integrated; no adoption tests required. |

Every upstream commit requires inspection of its actual diff and behavioral
effects, including defaults, assets, dependencies and bundled changes. Use the
following policy when deciding what to integrate:

| Change category | Policy |
| --- | --- |
| Matching decompilation / byte accuracy | Prioritize verified corrections toward the stated Xbox reconstruction target; validate their effect on the native port separately. |
| Core performance, stability, platform compatibility and renderer correctness | Prioritize improvements that preserve original gameplay and presentation. Verify that an optimization does not silently change simulation timing or player behavior. |
| Netcode and potential matchmaking | Consider individually for more reliable, fair online play. Review compatibility, latency, authority, timing and fairness effects; eligibility is not automatic acceptance. |
| Renaming or rebranding, including OpenCE names/titles | Exclude from this fork unless the user explicitly requests a separate change. |
| Replacement fonts, artwork or HUD; new overhead player labels | Exclude by default. Preserve original presentation and original target-name/teammate-indicator behavior. |
| Timers, silent weapon switches, balance changes or other rule modifications | Exclude from the baseline unless the user explicitly requests and separately reviews them. |

Renderer correctness fixes can be appropriate: the existing `bfbac357`
glyph-padding fix preserves the original font pixels and prevents adjacent atlas
cells bleeding into enlarged text. A cosmetic replacement bundled with a useful
fix is not a reason to accept the replacement; isolate the fix or defer the commit.
Uncertain fidelity or fairness effects should be recorded and deferred pending
evidence, rather than silently changing the baseline.

Keep an upstream review ledger alongside the relevant update documentation. For
each reviewed commit, record its full hash, category, actual behavioral effect,
decision (adopt, partially adopt, exclude or defer), reason, relevant tests and
integration status (including the local commit when integrated). Include rejected,
deferred and already-equivalent/no-change decisions so later reviews do not mistake
them for omissions. Record the upstream revision reviewed through separately from
the last integrated revision. A matching-build result, native regression result
and untested claim must remain distinguishable.

Generic macOS/v5-map fixes can still be offered upstream as focused contributions,
independently of this fork's presentation choices. This policy does not schedule
automatic fetching, merging or monitoring.

## Defaults and comparison profile

The current implementation creates new `config.toml` files with
`display.high_res_hud = false`,
`display.interpolation = false` and `display.direct_camera = false`. The
simulation stays at 30 Hz. These current defaults are not a permanent requirement
to cap rendering at 30 FPS. High-refresh rendering, including 120 FPS through
interpolation, can be appropriate while preserving the 30 Hz simulation. Review
interpolation and camera behavior for their effect on fidelity and responsiveness.
Existing configurations are preserved; explicitly set these keys to false when
using an older save directory for reference comparisons.

[xbox-ntsc.toml](../port/macos/profiles/xbox-ntsc.toml) supplies an isolated
comparison profile. Launch it with the existing `HALO_SCREEN_WIDTH=640` override
for a 4:3 window. Fullscreen/widescreen and optional rendering settings remain
available, but the reference comparison uses original presentation settings.
Keep this 30 FPS reference preset separate from decisions about normal-play
rendering performance.

Modern native networking and community-map loading are deliberate extensions.
They must preserve the baseline's timing and weapon/player rules. Native map
files may use a bounded 128 MiB disk cache; the original 22 MiB tag arena and
non-native Xbox build limits are retained. Imported map geometry, spawn/item
placements and necessary custom content are reviewed separately from the engine.

## What “100% matching” means here

The decompilation target is Xbox build **2342**, `cachebeta.exe`, SHA-256
`4cc87b45f721270392a96f1674ed2b5cd4a7bb4355faeab4531d1cf1884d9520`.
The local retail data set is USA NTSC cache v5 build **2276**,
`01.10.12.2276`. These are distinct identifiers.

The [bnunu decompilation README](https://github.com/bnunu/halo-1#readme) reported
99.5% byte matching when inspected on October 1, 2026. This is a reported status,
not a matching build verified in this checkout. Track future matching progress
against its stated executable and build configuration. Do not call the ARM Mac
executable byte-identical to an Xbox executable: it uses a different compiler,
instruction set and platform layer, with replacement networking.

A matching Xbox reconstruction and a faithful native port require different
evidence. Native fidelity still needs physical-controller play, reference Xbox
comparisons, campaign/save coverage and multiplayer timing tests. A successful
Mac build, stock-map hash or community-map smoke test does not certify those.
