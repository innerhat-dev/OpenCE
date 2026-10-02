# Community maps on the Xbox-derived Mac engine

All **40 maps** from JukkisP's **H1 Performance Build 2.0 Public Beta 3** now
compile as Xbox NTSC **v5** content for this fork, extending the initial
Downrush, Octagon and Atlas pilot. The engine remains the Xbox-derived macOS
port. Compilation and local staging do not establish acceptance of every map,
game mode or authored effect.

Follow the [Xbox fidelity policy](xbox-fidelity.md) and the
[implementation plan](competitive-maps-plan.md). The
[source review](community-map-source-review.md) records the scope of the
40-map script and scenario decisions. These are local experimental imports,
with remaining gameplay and controller validation described below.

## Try the local collection

The staged candidate is under
`build/community-maps/full-collection-candidate-20261002/`. Run
`Play Xbox Map Pilot.command` from that directory. It launches
`Halo Xbox Map Pilot.app` with separate data and saves, a 4:3 window, the original
map HUD artwork, and high-refresh interpolated rendering with VSync. The
simulation remains **30 Hz**; rendering can follow a 120 Hz display. The direct
camera remains disabled in this profile. It does not replace the installed game.
Keep its source map folders in place: the candidate uses symlinks to local stock
and generated maps.

For a one-player session, open a map's `.command` file inside `Practice Maps/`,
for example `Practice Maps/downrush.command`. Each launcher starts that map in
offline Slayer with human input, its own saves, no bot and no automatic exit.
It does not require a second local player. The ordinary multiplayer menus remain
available through the main launcher; the split-screen lobby requires two local
players to start.

The 40 custom maps append to the original maps in the multiplayer selector and
use the generic question-mark thumbnail. Four package variants have `h1pb_`
names to keep their retail counterparts intact. The initial three-map selector
was inspected visually. Downrush was selected and launched into
Slayer through the original System Link menus, with a second scripted local
client joining the invite. Full-collection manual-menu coverage and physical
controller navigation remain separate acceptance checks.

## Runtime support for compatible v5 maps

Native map discovery is independent of Jukkis' package. Place a compatible v5
multiplayer cache in the active data root's `maps/` directory, alongside the
stock maps, then restart the game. The map list is collected once per process.
Use the existing external-data arrangement described in the
[Mac instructions](../port/macos/README.md); keep stock caches intact.

Discovery retains the original 13 map entries and order, then appends custom
maps sorted by name. The list is bounded at 128 entries total. A custom cache
must have a valid v5 multiplayer header, a recognized regional build string,
and a header name matching its filename without `.map`, ignoring case. Names
are 1–31 ASCII letters, numbers, spaces, underscores or hyphens. Stock-name
duplicates are skipped. Custom network identifiers use the cache basename,
allowing source scenarios in directories other than the stock `levels/test/`.

The native multiplayer disk-cache allowance is 128 MiB; the Xbox tag arena
remains 22 MiB. Non-native Xbox limits are unchanged. Passing discovery checks
does not certify every tag, script or game mode in an arbitrary map. The import
builder targets the USA NTSC data build `01.10.12.2276` specifically. Renaming a
v7 cache or changing its version field is not conversion.

## Reproduce the imports

Run these commands from the repository root. Each output must be a **new child
directory under `build/`**; the tools refuse to overwrite an existing output.
The package supplies `maps/` and `tags/`. Original Xbox NTSC caches are supplied
separately through `assets/maps` by default, or `--stock-maps`.

Inventory all package caches without running its executables:

```sh
python3 tools/community_maps.py inventory \
  --package '/Users/pfista/Downloads/H1 Performance Build 2.0 Beta 3' \
  --output build/community-maps/inventory-new
```

Build all 40 reviewed maps with the locally built Invader toolchain:

```sh
python3 tools/community_maps.py build \
  --package '/Users/pfista/Downloads/H1 Performance Build 2.0 Beta 3' \
  --invader-bin ../research/downrush-conversion-2026-09-30/toolchain/build \
  --invader-manifest ../research/downrush-conversion-2026-09-30/toolchain/source-manifest.json \
  --all \
  --output build/community-maps/full-collection-new
```

The importer checks the Invader revision and every executable hash against the
source manifest. The reviewed revision is
`7d25a855f5ef9e4ab8407abf490b21f8780abf27`.
[jukkis-beta3.json](../port/maps/jukkis-beta3.json) pins the source scenarios and
allowed scripts. New scenario content or unreviewed scripts require review
before this policy can be extended. Use repeated `--map` options for a smaller
cohort, such as `--map downrush --map octagon --map atlas`; omitting both `--all`
and `--map` selects Downrush. Batch builds record per-map successes and failures
in `build.json` and continue building the rest of the selected cohort after a
map fails. Inspect those results before staging a collection.

After building the native app using the [Mac build instructions](apple-build.md),
stage a separate playable candidate:

```sh
python3 tools/community_map_candidate.py \
  --imports build/community-maps/full-collection-new \
  --high-refresh --practice-launchers \
  --output build/community-maps/full-collection-candidate-new
```

The candidate builder verifies the imported cache hashes and NTSC headers,
and requires its stock extraction inputs to match the import manifest's hashes,
rejects stock-name collisions, packages and locally signs the Mac app, and
copies the [Xbox reference profile](../port/macos/profiles/xbox-ntsc.toml) into
its own save directory. `--high-refresh` enables interpolation in that copy;
without it the reference profile renders at 30 FPS. `--practice-launchers` adds
the independent offline launchers. `candidate.json` records those options,
launch profiles, app, guest and map hashes.
This is a local staging operation, not an installer or a published release.

## Import policy and recorded changes

The tool copies the source dependency closure, extracts stock dependencies from
Blood Gulch first, and fills missing dependencies from `a10` and `ui`. Stock
dependencies take precedence over corresponding package tags, restoring the
baseline player, weapon, sound, HUD and global dependencies where available.
Map-specific content remains in the copied source tree. Gearbox model tags are
converted to Xbox model tags and references are rewritten before compilation.

All reviewed optional scenario scripts, globals and source files are removed
from the copy. This removes the package's timer, announcement, host-setup and
waypoint behavior. Where the source uses training objects, a single startup
script destroys objects with the reviewed `spawn_marker` and `randoms` prefixes.
Octagon B has no such cleanup in its source and needs no replacement script.
The original package files are unchanged. Combat-AI encounters are rejected for
this import profile; all 40 reviewed scenarios have none.

Weld also requires converting its PC-only
`headlongset_sky.shader_transparent_chicago_extended` to Xbox-supported
`shader_transparent_chicago`. Invader preserves the authored four-stage path
(two layers in this tag) and the importer rewrites its references in copied
tags. The conversion is recorded with source/output hashes and layer counts;
it does not change the renderer or game rules. Sky appearance still needs visual
comparison.

Recompiling extracted stock tags also requires explicit compatibility repairs:

- Clear unused AI firing references in the Ghost gun, Scorpion cannon and
  Warthog gun weapon tags. Player weapon fields are retained; this import is
  scoped to multiplayer without combat AI.
- Change the Scorpion headlight flare's invalid bitmap index from 2 to 0.
- Repair the invalid local effect-location index in the Scorpion secondary-fire
  bullet effect. The importer rejects unexpected effect repairs.

These repairs are recorded with before/after hashes in `build.json`. They are
not evidence that every imported asset is byte-identical to retail data; their
visual behavior still needs comparison. Each map's `manifest.json` records
source hashes, stock substitutions, removed scripts, model/shader conversions,
compiled scenario identity and the output cache hash. Compiler output is
retained in `logs/`.

The converted stock-name variants use `h1pb_chillout`, `h1pb_hangemhigh`,
`h1pb_prisoner` and `h1pb_wizard`. Their scenario identities, cache headers,
filenames and network identifiers use these aliases; this is not a filename-only
rename. The importer also rejects stock dependency lookup that would replace
authored level content. Generated maps and extracted original-game tags remain
local build outputs.

## Validation recorded on October 1, 2026

The UTC-dated evidence folders use `20261002`.

### Full collection

`build/community-maps/full-collection-combined-20261002/build.json` combines
the 39 successful initial imports from `full-collection-import-20261002/` with
the repaired Weld import from `full-collection-weld-repair-20261002/`. All 40
have V5 NTSC multiplayer headers, matching names and recorded output hashes.
Declared uncompressed caches range from 36.08 MiB (Octagon B) to 58.15 MiB
(Weld), below the 128 MiB native allowance. The largest header tag-data figure
is 7.27 MiB (Fallout); the compiler also checks BSP allocations against the
22 MiB tag arena.

The compiled-cache audit at
`build/community-maps/full-collection-20261002/weapon-audit/results.json`
covers all 40 maps. Pistol/AR ready-effect, spread/error and fire-rate fields,
plus selected player/global movement and biped fields, match compiled stock
Blood Gulch in 1,240 comparisons. All five extracted tags per map also match
stock extraction byte-for-byte: pistol, AR, globals, multiplayer cyborg biped
and pistol ready effect (200 tag-hash comparisons). This is a targeted
compiled-data check, not proof of audible sound or complete engine fidelity.

Compiler warnings remain visible in the source build logs. In particular,
**Octagon B has no blue CTF spawns**, so it must not be advertised as accepted
for CTF. Several maps have fewer than 16 spawns for individual modes; logs also
include unused palettes, legacy tag metadata and rendering warnings. Preserve
the authored placements while recording supported modes; a successful build
does not resolve those warnings or establish all-mode support.

All **40 maps passed isolated offline one-player Slayer load/render smoke
tests**, with a logged target-map load, acknowledged player spawn, rendered
frames after the spawn and a clean exit without a recorded runtime fault.
Groups `full-collection-smoke-a-20261002/`, `-b-`, and `-c-` covered 10, 15 and
14 maps with 15-second process limits; `full-collection-smoke-weld-20261002/`
covered Weld with a 20-second limit. Playable time starts after loading and is
shorter than those limits. These hidden-window runs used scripted look input;
their frame statistics do not establish 120 FPS performance on every map.

`build/community-maps/full-collection-20261002/validation.json` combines the
four reports and verifies their map IDs and cache hashes against the combined
import and staged candidate. Guest hashes also match. Packaging changes the
host's library paths and signature, so packaged and smoke-host hashes are
recorded separately. The final targeted unit suite passed **29 tests**, recorded
in the same directory's `unit-tests-final.log`.

`source-preservation.json` rechecks the complete before/after inventory: all
3,633 files under package `tags/`, all 44 files under package `maps/` (40 map
caches and four shader-data files), and all 24 stock caches retain their hashes.
No files were added or removed in those recorded source sets.

Runtime/compiler warnings still require mode-specific acceptance; some maps
also report missing Race flags. These short smoke runs do not certify all game
modes, authored effects, controller feel or retail fidelity. The earlier
two-process network coverage below applies to the three pilot maps, not all 40.

### Initial three-map pilot

The reviewed pilot output is
`build/community-maps/stock-pilot-audited-20261002/`. Its map hashes match the
earlier `stock-pilot-20261002/` files used by the earlier pilot candidate.

| Map | Declared uncompressed cache | Header tag data | Result |
| --- | ---: | ---: | --- |
| Downrush | 50.99 MiB | 6.81 MiB | v5 NTSC; repeat build identical; network smoke passed |
| Octagon | 36.99 MiB | 6.61 MiB | v5 NTSC; repeat build identical; network smoke passed |
| Atlas | 46.05 MiB | 6.74 MiB | v5 NTSC; repeat build identical; network smoke passed |

The header tag-data figures exclude some BSP allocations; the Invader build
also enforces the original tag-arena limit. A fresh build under
`stock-pilot-repro-20261002/` produced the same SHA-256 for each map.
The audited rebuild also matches, with corrected reporting of post-conversion
stock model overrides: 1,148 substitutions for Downrush, 700 for Octagon and
1,139 for Atlas. Input metadata and hash consistency do not independently prove
retail authenticity; the user-supplied stock data remains the comparison input.

Evidence under `build/community-maps/pilot-20261002/` includes:

- `source-preservation.json`: all inspected package tags and all 24 stock
  caches retained their original hashes.
- `weapon-audit-02/results.json`: the compiled pistol and assault-rifle tags
  match the stock ready-effect, minimum-error, error-angle and maximum-rate-of-
  fire fields for all three maps. This is a targeted audit, not a complete
  weapon or sound comparison.
- `network-downrush-02/validation.json`, `network-octagon-01/validation.json`,
  `network-atlas-01/validation.json` and `network-bloodgulch-01/validation.json`:
  four 70-second Slayer invite tests with two real processes on one Mac. Both
  peers simulated multiple players and exchanged gameplay updates over the
  encrypted connection; both exited successfully without assertions or faults.
- `import-audited-validation.json`: corrected import manifests reproduce all
  three caches, and the earlier pilot candidate's stock and custom-map hashes agree.
- `unit-tests-final.log`: 25 map-discovery, import/candidate, Mac-preflight and input/configuration
  tests passed. The native Mac build and strict local signature verification
  also passed.
- `controller-inventory.json`: no physical gamepad was connected. Controller
  feel has not been validated.
- `menu-network-final/`: Downrush selected, hosted and started through the
  normal System Link menus using keyboard input, with a second local client.
  `menu-downrush-gameplay.png` records the rendered game and original HUD.

The network runner can repeat a pilot test with isolated data and saves:

```sh
python3 tools/macos_multiplayer_smoke.py \
  --mode invite --seconds 70 --map downrush \
  --map-source build/community-maps/stock-pilot-20261002/downrush/maps/downrush.map \
  --reference-profile --screenshot-every 180 \
  --output build/community-maps/network-downrush-new
```

### Two copies on the same Mac

The local pair at `build/community-maps/local-system-link-20261002/` opens two
normal game menus, each with separate saves and all 40 community maps. Use
`Play Two Instances.command` so the local connection helper starts first.
Create a System Link game in one window, then focus the other window and open
its System Link browser. The existing clipboard invite feature connects the
two copies; choose the hosted game normally. No map is selected automatically.

This setup uses the existing encrypted invite transport with a broker bound
only to `127.0.0.1:18883`, empty STUN settings and UPnP disabled. Direct discovery
between this Mac's Wi-Fi and Tailscale addresses did not work, so this local
pair uses Wi-Fi plus loopback. The addresses in each saved config are specific
to this Mac's current network configuration. This is a local test arrangement,
not verification of discovery across two physical computers.

`local-broker-network-20261002-a/validation.json` records a 50-second Birdhouse
Slayer test with two real game processes using this helper: both simulated two
players, exchanged gameplay updates, connected over the encrypted transport,
and exited without assertions or faults.

Both copies set `audio.volume = 0.1` and `audio.menu_music = false`. The new
config-only music preference suppresses the title track while retaining menu
effects and gameplay audio. It defaults to true for other installs and takes
effect on restart. Native compilation, eight input/config tests and focused
menu-music start/stop checks passed. These copies use the rebuilt guest recorded
in their `session.json`; the earlier collection smoke evidence records its own
guest separately.

Remaining acceptance work includes full-collection manual-menu coverage,
a physical Xbox controller, audible weapon-ready cues, reference Xbox comparisons,
authored devices, sky/lighting comparisons, collision/spawn/item coverage,
each map's supported game modes, longer sessions and map transitions. Networking
still needs expanded map coverage, two physical Macs, different networks,
latency/loss tests and map/rules-mismatch handling. None of the smoke tests
certifies retail fidelity, competitive balance, completed matchmaking or
compatibility with physical Xbox consoles.
