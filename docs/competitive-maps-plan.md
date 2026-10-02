# Xbox gameplay on macOS and community map imports

Plan prepared October 1, 2026; all 40 package maps now compile as stock-dependency Xbox NTSC v5 imports and pass short offline one-player Slayer load/render smoke tests. Native map discovery, a high-refresh local candidate and offline practice launchers are implemented. The final targeted unit suite passes 29 tests, and source-input hashes remain unchanged. The initial three-map pilot has normal-menu and same-Mac two-instance network evidence; that coverage does not extend automatically to the other maps. Physical-controller, per-mode and reference-Xbox fidelity acceptance remain open. Current implementation and validation are recorded in [community-map support](community-maps.md).

## Direction

Use **`pfista-halo-macos`, based on `cybersecurity/halo-ce-universal`, as the game engine**. First establish an accurate original-Xbox gameplay experience on macOS with an Xbox controller. Then bring in the community maps from **JukkisP's H1 Performance Build 2.0 Public Beta 3**. Add optional competitive features after that foundation works.

The maps are content inputs, not a reason to adopt the H1 Performance Build engine or all of its rules. Retain the separate `h1-competitive-macos` project as a reference and preserve its work. Reuse an individual fix only after checking that it applies to the Xbox-derived engine.

The target is our native macOS engine. Running the converted maps on original Xbox consoles is outside this plan. Windows and Linux support can follow the Mac work.

Our fork follows the [original-Xbox fidelity policy](xbox-fidelity.md). Future upstream decompilation and platform fixes are reviewed individually; presentation or gameplay changes are not adopted automatically. Generic macOS and v5 map support can still be offered as focused upstream contributions. Runtime discovery supports compatible v5 maps in general; Jukkis package conversion stays in separate tooling. Native-only extensions preserve the original Xbox ABI and tag-arena limits and add no package-specific gameplay rules.

The original Xbox Halo: Combat Evolved launched in **2001**; 2003 refers to the PC/Mac era. Use **original Xbox NTSC gameplay** as the initial reference rather than mixing PAL and NTSC behavior. [Halo's twentieth anniversary](https://www.halowaypoint.com/news/celebrating-20-years-of-halo).

## Starting evidence

| Component | What we have established | What still needs verification |
| --- | --- | --- |
| Primary engine | Apple fork at `aabe44417431c36e46aaa385a69a89a3c9d685c0`, derived from cybersecurity's reconstruction of Xbox build **2342**, `cachebeta.exe`. | How closely this native port reproduces retail Xbox gameplay. Source ancestry alone does not establish retail parity. |
| Original data | All **24 local stock maps** have Xbox cache version **5** and build string **`01.10.12.2276`**, the USA NTSC data baseline. | Reference behavior, controller feel, and the remaining campaign coverage. Keep the source build and the map-data build recorded separately. |
| Jukkis package | **40 PC-format v7 maps**, now rebuilt from reviewed source as v5 NTSC imports. The four stock-name variants compile with `h1pb_` aliases. | Rendering, authored devices and supported modes for each converted map. A PC-format cache does not identify the ancestry or rules of the engine that uses it. |
| Downrush feasibility | The early conversion passed a **105.6-second local Slayer test**. The subsequent stock-dependency pilot reproduced Downrush, Octagon and Atlas and passed same-Mac two-process Slayer tests. | Physical-controller play, reference-Xbox comparison, longer sessions and two physical machines. |
| Current networking | The Mac documentation records two native instances on one Mac exchanging gameplay updates, damage, death, and respawn through encrypted invites. | Two physical Macs, different networks, latency behavior, and competitive fairness. This is not completed matchmaking or original-Xbox network compatibility. |

The early Downrush proof retained timer scripts and competitive source assets; it has been superseded for this project by the stock-dependency imports. The supplied Downrush and Octagon caches omit weapon-ready sounds, and the H1 edition has additional engine/rules changes. Those changes must be audited rather than silently imported. The current 40-map compiled-cache audit verifies that the pistol, AR, globals, multiplayer cyborg biped and pistol ready-effect tags match stock Blood Gulch extraction; audible sound and broader fidelity acceptance remain separate.

Evidence: [engine provenance](../README.md), [Mac validation](../port/macos/README.md#validation-and-remaining-work), [network validation](apple-multiplayer.md), [Downrush conversion report](/Users/pfista/src/halo/research/downrush-conversion-2026-09-30/conversion-result.json), [map compatibility inventory](/Users/pfista/src/halo/research/h1pb-assessment-2026-09-30/map-compatibility-results.json), and [weapon-ready asset inspection](/Users/pfista/src/halo/h1-competitive-macos/research/weapon-ready-assets.json).

## 1. Establish the original-game Mac baseline

Pin the engine revision and hashes of the NTSC map set. Record a reference settings profile and a short fidelity report before promoting custom maps into the normal game experience.

- Test a physical Xbox controller: menus, button presets, triggers, sticks, sensitivity, dead zones, aiming, vibration where supported, and reconnection. Automated input tests do not establish controller feel.
- Compare movement, jumping, grenade behavior, melee, aiming/autoaim, pistol spread, damage, reload and weapon-ready timing, item pickups, respawns, and their sounds against a documented Xbox NTSC reference.
- Keep the original **30 Hz simulation**. Evaluate smooth rendering separately; a higher display frame rate must not silently change gameplay timing.
- Keep an original-presentation comparison profile using the maps' HUD art and a 4:3 view. The isolated reference profile disables interpolation and the direct camera. The current play candidate enables interpolated rendering with VSync for high-refresh displays while retaining 30 Hz simulation and original HUD art. A 30 FPS comparison preset is not a normal-play requirement. Audit controller behavior rather than treating either profile as proof of retail parity.
- Exercise stock multiplayer maps, map transitions, a longer gameplay session, and campaign checkpoint/save/reload behavior. Start with representative scenes, then expand coverage and record the gaps.

Use existing configuration facilities for reference settings. Keep original sounds and gameplay behavior as the baseline. Any confirmed port difference should have a reproduction and a narrowly scoped fix.

**Exit condition:** the current Mac app has a documented, reproducible Xbox-controller baseline; tested gameplay matches the selected reference within recorded limits. Outstanding campaign or hardware coverage remains explicit rather than being called complete. Small map-tooling experiments can proceed while this validation is underway, but imported maps do not replace the stock baseline.

## 2. Produce a clean Downrush import, then two more pilot maps

The initial **Downrush**, **Octagon** and **Atlas** cohort is implemented and reproducible. It remains the smaller regression cohort for detailed gameplay and network checks while collection-wide validation continues.

Build each map from copied source tags through a pinned toolchain targeting Xbox NTSC v5. Do not patch a v7 cache's version field. [Invader supports Xbox-targeted builds](https://github.com/SnowyMouse/invader#can-invader-build-create-xbox-maps), but model, HUD, script, and dependency differences still require conversion.

For the initial imports:

- Preserve the authored geometry, collision, lighting, textures, map-specific objects, spawn positions, and item placements.
- Resolve shared player, weapon, physics, sound, HUD, and game-global dependencies against the verified stock NTSC baseline. Keep necessary custom assets, but record their differences.
- Review scripts and tag dependencies before removing optional timers, announcements, training features, or silent weapon switching. Preserve scripts required for the map to function. Build the stock-gameplay variant deliberately rather than assuming that converting the format restores stock behavior.
- Record every compatibility adjustment. Do not rebalance map layouts or item placements as part of format conversion.
- Preserve source downloads, stock maps, and the earlier competitive Downrush candidate. Build into separate output folders with separate test settings and saves.

The early Downrush work established model conversion, reference rewriting and missing Xbox pause-menu dependencies. The current repository-native importer and candidate builder supersede that experiment's scripts and paths; use the commands in [community-map support](community-maps.md) to reproduce the current profile.

The native multiplayer disk-cache allowance is now bounded at **128 MiB**, while the original tag arena stays at **22 MiB**. The current collection's declared uncompressed caches range from **36.08 to 58.15 MiB**. Validate tag/BSP allocations and workload behavior separately; do not increase unrelated limits merely because the target is a Mac.

**Exit condition:** the three pilot maps build reproducibly and run in the current Mac engine with the stock gameplay profile. Check controller play, rendering, collision, spawn/item behavior, weapon-ready audio, pause/resume, and each advertised game mode. Classify warnings and unsupported modes. Loading a map alone is not acceptance.

## 3. Add map selection and import the complete collection

The original guest menu used a fixed **13-entry multiplayer map table**. Native discovery now preserves those entries and appends compatible custom maps to the normal menu. Continue validation of selection, hosting, joining and consistent identifiers/display names. Physical-controller operation remains to be tested.

Keep the original maps intact. The four conflicting variants now use `h1pb_chillout`, `h1pb_hangemhigh`, `h1pb_prisoner` and `h1pb_wizard` for compiled scenario identities, cache headers, filenames and network lookup. Continue validating their selection and joining behavior; aliases alone do not establish game-mode support.

The [reviewed policy](../port/maps/jukkis-beta3.json) and generated build/per-map manifests cover all **40** maps. The [source review](community-map-source-review.md) binds script decisions to exact source scenario hashes. Preserve and expand these records with:

- Stable map identifier, display name, author/credits, source scenario, package version, and input hashes.
- Dependency substitutions, optional competitive content, compatibility patches, and output hash.
- Cache/tag sizes, supported game modes, validation status, and the engine/rules version required to play.

The full conversion is complete: 39 initial imports plus Weld after conversion of its PC-only extended Chicago sky shader to the Xbox-supported form using its authored four-stage layers. That copied-tag repair is recorded with hashes and does not change engine rules; verify the sky visually. The aggregate is `build/community-maps/full-collection-combined-20261002/`, and the local candidate is `build/community-maps/full-collection-candidate-20261002/`.

Reproduce with `tools/community_maps.py build --all` and the documented package/toolchain options, then stage using `tools/community_map_candidate.py --high-refresh --practice-launchers`. The candidate provides normal-menu selection and a `Practice Maps/` launcher for each map, using offline one-player Slayer, separate saves and human input. Rendering follows the display refresh with the original 30 Hz simulation.

All 40 compiled caches pass the targeted stock-data audit: 1,240 field comparisons and 200 extracted-tag hashes match stock Blood Gulch across pistol, AR, globals, multiplayer cyborg biped and pistol ready effect. This does not replace runtime or audible-sound checks. Validate each map's rendering, collision, spawns, authored devices, weapon/item behavior, scripts, audio, and supported modes. **Octagon B has no blue CTF spawns**; do not advertise it as accepted for CTF. Other compiler spawn-count and rendering warnings also need classification. Perform longer sessions on representative complex maps and test transitions between stock maps and community maps.

Keep tooling, manifests, patches, credits, and permitted third-party source assets in the repo. Preserve the existing external-data model for original game assets; generated caches that embed stock game data remain local build/import outputs. Make import repeatable from the user's original data and map-source package.

**Exit condition:** every map has an explicit accepted or blocked status with a reason. Accepted maps are selectable with a controller; stock maps retain their original identities and hashes. The full collection is not marked supported until its individual checks pass.

## 4. Validate community maps online using the existing network stack

Use cybersecurity's native network implementation rather than importing the H1 edition's engine or changing the simulation rate. Start with two real instances on one Mac for fast regressions, then test two physical Macs and different networks.

Check map/rules agreement at join time, map changes, damage, melee, grenades, deaths, respawns, pickups, sound cues, and disconnect/rejoin behavior. Measure behavior under latency and packet loss against the stock-map baseline. Give players a useful error when a map or rules version differs.

**Exit condition:** the pilot maps support documented two-machine sessions without unexplained state differences, crashes, or timing changes. Expand testing to the accepted collection. Matchmaking and broader platform interoperability are subsequent work, not claims established by an invite test.

## 5. Add optional competitive features

Plan an optional in-game settings/debug overlay styled to match original Halo,
using the H1 Performance Build menu as a functional reference. Make it usable
with an Xbox controller and keyboard. Start with existing display and diagnostic
settings, such as interpolation, VSync, direct-camera behavior and FPS display;
reuse the current configuration system and show when a setting needs a restart.
Keep presentation and performance controls distinct from changes to gameplay
rules, preserve the original 30 Hz simulation, and keep the overlay hidden during
normal play unless opened. Implement this after the Mac and map baseline is
validated; this is planned work, not part of the current pilot.

After stock behavior and map support are established, introduce an explicit competitive preset for requested changes such as timers, announcements, and weapon-switch sound removal. Evaluate balancing changes separately with players; they do not become the default merely because they exist in Jukkis' package.

Some features live in map tags/scripts, others in engine code. Use runtime settings where suitable and separately built map variants where necessary. Include the preset and relevant asset hashes in session compatibility checks so every player receives the same rules. Keep the stock profile available.

## Next acceptance work

1. Record the current NTSC baseline and complete the physical-controller/fidelity audit; fix confirmed Mac-port problems in the primary repo.
2. Finish and record per-map runtime, manual-menu, authored-device and supported-mode checks for the 40 compiled imports; preserve explicit limitations where warnings remain.
3. Compare audible weapon-ready cues, movement and core gameplay against the NTSC reference, then test longer sessions and map transitions.
4. Expand the three-map same-Mac network cohort to the collection and test two physical Macs, latency/loss and map/rules mismatches.

Implementation has moved here from the separate **COMPETITIVE** chat. Its H1-engine work is preserved as a reference. Further implementation follows the Xbox-derived Mac engine and the reviewed content imports.
