# Native Apple Silicon build

The experimental native Mac build is playable. On 2026-09-27, the main menu,
campaign loading and gameplay, mouse capture, and audible output were confirmed
on an M5 Mac with 16 GB RAM running macOS 26.5.1. This is the phase-one baseline;
it is not a claim that every campaign level or Mac configuration is verified.

The CPU code runs natively on ARM64. The existing GLES renderer uses ANGLE's
Metal backend. No Windows runtime, Xbox emulator, Apple Developer account,
special entitlement, or security-setting change is required for this local build.

## Download

Sign in to GitHub and open the
[macOS DMG workflow](https://github.com/pfista/halo-ce-universal/actions/workflows/macos-dmg.yml).
Choose a successful run, then download **halo-macos-arm64-dmg** from its
**Artifacts** section. Builds run on code pushes to `main` and can also be
started manually. Artifacts expire after 14 days.

Extract the downloaded ZIP and open `Halo-CE-Universal-macos-arm64.dmg`.
Drag **Halo CE Universal.app** onto the Applications shortcut, then launch it
from Applications. `README.txt` records that build's minimum macOS version and
installation steps. `BuildInfo.txt` records the source revision and guest hash;
`SHA256SUMS` lets you verify the DMG with `shasum -a 256 -c SHA256SUMS` from the
extracted folder.

This build requires **Apple Silicon and macOS 26 or later** with the current
bundled dependencies. No Homebrew, Xbox SDK or build tools are needed. The app
is ad hoc signed and is not notarized by Apple, so macOS may block its first
launch; after attempting to open it, use **System Settings → Privacy & Security
→ Open Anyway** if you choose to run this build. See
[Apple's opening instructions](https://support.apple.com/en-us/102445).

On first launch, select your own original Xbox Halo disc image or extracted
game folder. The download contains no maps or disc images. See
[Mac data import and releases](../../docs/macos-menu-and-releases.md) for details.

## Launch

Open `build/macos/Halo CE Universal.app` in Finder. There is no automatic timeout.
The app includes SDL3, ANGLE, Sparkle, and the compiled game image. It remembers
your chosen local data location. Development builds can fall back to this
checkout's `assets/` directory. The helmet menu icon opens Settings, changes
fullscreen, and selects your own disc image or maps folder. See
[Mac menu and releases](../../docs/macos-menu-and-releases.md) for first launch,
data import and the intentionally unconfigured release hosting.

The app defaults to borderless fullscreen at the desktop's aspect ratio, with
Retina output. The 3D field of view widens; the image is not stretched. Rendering
still uses 480 vertical lines internally, scaled to the display. On the tested
display this is 740x480 into a 3420x2214 drawable. Set `HALO_WINDOWED=1` for a
resizable window or `HALO_SCREEN_WIDTH=640` to restore the original 4:3 view.
`HALO_WINDOW_SCALE` controls the initial size in windowed mode.

New configurations use the maps' original HUD bitmaps, 30 FPS presentation and
the tick-based camera. Existing `config.toml` values remain in effect. The
upstream high-resolution HUD artwork, interpolation and direct camera remain
available as explicit settings. For a separate 4:3 comparison configuration,
use [xbox-ntsc.toml](profiles/xbox-ntsc.toml) and the existing
`HALO_SCREEN_WIDTH=640` override. See the [fidelity policy](../../docs/xbox-fidelity.md).
Text glyphs keep the fonts in the game data and have clear borders to
prevent neighboring characters from bleeding into their edges, and widescreen
menu dimming and flat backgrounds cover the whole display.

Saves, cache files, `config.toml`, and `halo.log` are under:

```text
~/Library/Application Support/Halo CE Universal/
```

Keyboard/mouse controls:

| Control | Action |
| --- | --- |
| W A S D / mouse | Move / aim |
| Left / right mouse button | Fire / grenade |
| Space or Enter | Jump / accept |
| E or R | Action / reload (X) |
| F or Backspace | Melee / back (B) |
| Escape | Pause and release mouse / back in menus |
| Q, Tab or mouse wheel | Change weapon (Y) |
| L | Flashlight |
| X | Change grenade type |
| Shift (either side) | Crouch |
| Control (either side) or middle mouse button | Zoom |
| 1 | Pause (Start) |
| Backtick (`) or F1 | Hold for scoreboard (Back/Select) |
| F2 | Open / close developer console |
| F12 (Fn-F12 on some keyboards) | Release or recapture mouse |

Menus support mouse navigation. The cursor stays free after switching apps or
closing a native panel; choose Resume or click gameplay to capture it. That
first capture click does not fire. Windowed play keeps a resizable native frame
with its title/buttons hidden; drag the top strip while the cursor is released.
See [native settings](../../docs/native-settings.md) for live Audio/Video options
in the main and pause menus.

All keyboard/controller actions and mouse buttons can be changed in the
`[bindings]` section of `~/Library/Application Support/Halo CE Universal/config.toml`.
The first launch adds any missing bindings with their defaults, preserving
existing settings, bindings and comments. Quit Halo, edit the file, and restart
to apply changes. These bindings emit Xbox controller buttons, so an in-game
controller preset can also change what an action does.

For example, these are the Mac defaults for the main keyboard actions:

```toml
[bindings]
x = "E, R"
y = "Q, Tab, Wheel"
zoom = "Ctrl, MouseMiddle"
start = "1"
select = "Grave, F1"
a = "Space, Return, KeypadEnter"
b = "F, Escape, Backspace, MouseX1, ACBack"
crouch = "Shift"
console = "F2"
release_mouse = "F12"
```

Names are case-insensitive. Separate alternative keys/buttons with commas;
for example, `select = "CapsLock, F1"`. `Grave`, `Backtick`, or the literal
backtick names the physical backtick key. `Ctrl`, `Shift`, `Alt`/`Option`, and
`Cmd` match either side; `LeftCtrl` and `RightCtrl` select just one. Letters,
digits, F1-F24, arrows, `Space`, `Return`, `Escape`, `Tab`, `Backspace`,
`CapsLock`, navigation keys and keypad keys are supported. Mouse names are
`MouseLeft`, `MouseRight`, `MouseMiddle`, `MouseX1`, `MouseX2`, and `Wheel`.
Use `""` to unbind an action, and use names such as `Comma` for punctuation.
The `console` and `release_mouse` bindings accept keyboard keys only and take
priority over controller actions. Invalid bindings are logged and use the
default for that action. The remaining movement, D-pad, trigger, flashlight
and grenade bindings are listed with comments in the generated config.

`HALO_DATA_ROOT`, `HALO_SAVE_ROOT`, `HALO_WINDOW_SCALE`, `HALO_VOLUME`, and the
other [shared native settings](../linux/README.md#settings) remain available.
For a command-line run from the repository root:

```sh
build/macos/halo build/macos/halo_guest.elf
```

That development command uses `build/macos/saves/` by default; the app uses the
Mac Application Support location above.

For Mac invite links and Mac-versus-iPhone LAN setup, follow
[Apple multiplayer setup](../../docs/apple-multiplayer.md). Builds must use the
same networking revision and map set. Hosting copies an invite to the clipboard;
opening it, or copying it and switching to Halo, connects the peers so the host
appears in the System Link browser.

With the Discord desktop client running, Halo connects to its local RPC socket
and accepts Discord game invitations. Hosting a System Link game publishes
"Hosting a game" with an invite in Discord. Enable activity sharing in Discord
to make it visible. The installed app handles both `halo://` links and the
upstream Discord application's launch scheme, so an invite can start Halo
when it is closed. Ordinary campaign/client gameplay does not publish activity.
This branch uses multiplayer protocol 9 and 64-digit invite codes; all players
need matching builds. Command-W is ignored while playing, and Command-Q or
the window's close button quits.

## Build

First complete [Apple build setup](../../docs/apple-build.md): clone the fork,
install LLVM 22 and the public dependencies, and place your own game maps
locally. Native builds use the checked-in SDK declarations and do not need the
Xbox SDK. Keep the documented environment exports in the shell used below.
From the repository root:

```sh
python3 tools/macos_build.py
open "build/macos/Halo CE Universal.app"
```

To build and install a single copy in Applications for Spotlight:

```sh
python3 tools/macos_build.py --install
```

To build without local game data, use `--no-data-path --install` instead;
the app will ask for a disc image or game folder on first launch.

Then press Command-Space, type `Halo CE Universal`, and press Return. An
optional directory, such as `--install ~/Applications`, installs for just your
account. Installation verifies the signed bundle before replacing a previous
copy, preserves the previous app in a hidden backup directory, and registers
the new copy with Launch Services and Spotlight. Generated app copies in
`build/macos` are preserved under `build/macos/app-backups.noindex` with a
`.app.backup` extension so Spotlight cannot select an older development build.
Quit an older running copy before launching the installed version: macOS can
reactivate an existing
instance with the same app ID. The startup log now identifies the executable,
app version, source revision and guest hash.

The first build compiles the complete game and downloads public SDL/musl source
dependencies. No development team, provisioning profile or paid account is needed;
the local app is ad-hoc signed automatically. For compiler/runtime checks:

```sh
python3 tools/test_macos_runtime.py
python3 -m unittest tools.test_macos_preflight
python3 -m unittest tools.test_visibility_queries
```

Packaging creates the Mac app icon from the existing
`port/ios/Assets.xcassets/AppIcon.appiconset/AppIcon.png` artwork. The built-in
macOS `sips` tool generates standard and Retina PNG sizes, which packaging embeds
in `AppIcon.icns` before signing. The editable menu icon is `Helmet.svg`.

The shared settings are read from `config.toml` in the save directory, with
`HALO_*` environment overrides still supported. The Mac host keeps its
`HALO_WINDOWED` override and 480-line render scale, with fullscreen also available
in the native menu; the upstream desktop-only
F11/menu-pointer path is not yet bridged through the ARM host.

The default LLVM path is `/opt/homebrew/opt/llvm/bin`. `HALO_MACOS_SDL_PREFIX`
and `HALO_MACOS_ANGLE_DIR` can select other dependency locations. SDL's guest
headers and musl sources are fetched by the shared ARM build graph. Existing
Windows/Linux/Android builds keep their own output directories.

`macos_build.py --host-only` rebuilds and packages just the host. After an initial
configuration, `ninja macos_guest` rebuilds the game. Compiler-pass and wrapper
changes are tracked dependencies. `--data-root /path/to/game` records another
local data directory in the app. The bundle is ad-hoc signed and signature
verification is part of packaging. It is a local build, not a notarized release.

## Memory and host architecture

Extra RAM does not solve the original address problem: the game stores pointers
and `long` in 32 bits, while ordinary ARM Mac executables cannot use its original
low addresses. The LLVM pass preserves those layouts and rebases memory access
and indirect calls into a 4 GB **virtual** arena at `0x10000000000`. This address
is not a physical RAM requirement. Memory is committed only as needed.

The pass uses LLVM address space 272 for 64-bit dereferences, explicitly lowers
varargs and memory intrinsics, preserves opaque GL offsets/handles, and translates
host pointer arguments. The Mac image has a distinct ABI version, so it cannot
be accidentally loaded by the Android host. This is an ABI adapter for the
locally compiled game, not an isolation boundary for arbitrary binaries.

The native host translates Linux/musl file, time, synchronization, memory, and
error interfaces to Darwin. Xbox 4 KB allocations share native 16 KB pages;
protection combines their requirements so freeing one allocation cannot remove
access to its neighbors. Texture write tracking therefore has 16 KB granularity.
Fresh heap mappings are explicitly recreated: Darwin's `MADV_DONTNEED` alone
does not guarantee the zero-filled pages expected by musl.

The Mac renderer streams current geometry by default. The optional cache in
`renderer_config.h` compares current vertex and index pages with a CPU shadow
before reusing the contiguous geometry mirror. This detects reused map memory
and writes missed by page tracking, including changes within one frame. Shadows
are allocated lazily and bounded by the original 128 MB contiguous arena;
frequently rewritten geometry, allocation failures and unsupported ranges use
the existing streaming path. The cache reduced uploads but did not improve
median frame time, so it remains disabled. iOS continues streaming until its
cache is validated on a device. The cache prototype passed Prisoner → Chill Out
→ a10 → b30 → Prisoner; captured Chill Out geometry matched the streamed
reference after a map change.

SDL video stays on the real main thread. Audio mixing runs on a guest-stack
worker, with the results returned to SDL's callback thread before submission.
This avoids a cross-thread stream-lock deadlock. Mouse capture is enabled on
macOS even though the renderer shares the Android GLES compilation path.

The old `--probe` preflight option measures the original low-address Android
assumptions and is expected to fail on an ordinary Mac. It is historical
diagnostic evidence, not a prerequisite for this rebased build.

## Validation and remaining work

Completed:

- Full ARM game and Darwin host compile; strictly verified local app signature.
- SDK hash and all 24 test-disc map payloads validated.
- Native execution probes for 32-bit layouts, globals, stacks, indirect calls,
  Xbox addresses, integer/floating varargs, memory routines, and atomics.
- Regression checks for fresh allocation contents, neighboring 4 KB allocations,
  texture write tracking, futex wakeups, clocks, and the SDL audio handoff.
- Mac invite validation, private atomic delivery, and native SDL URL events
  consumed without passing a 64-bit string pointer to the guest.
- Two real instances on one M5 Max Mac: encrypted invite connection, Blood
  Gulch gameplay, bidirectional updates, damage, death/respawn, and clean exit.
- Real menu rendering, campaign gameplay, mouse capture, sound, and clean timed
  test shutdown; gameplay, audio and input confirmed on the target Mac.

Not yet exhaustively validated: all campaign missions, checkpoint save/reload
outside the tested a30 scene,
controllers, split screen, multiplayer across physical devices/networks,
128-player sessions, other M-series GPUs, and older macOS.
Bink startup videos are skipped by the existing native port. CPU and rendering
correctness still need longer playtesting, especially under memory pressure.

The compiler regression suite includes an unaligned 64-bit read from a guest
stack pointer. ARM64 ILP32 instruction selection could add the arena bias twice
when splitting this load (observed in radar blip drawing). Explicit machine-level
pointer truncation fixes it. The original Xbox stack walker is disabled on Mac
because it cannot safely traverse native Darwin frames during assertion reports.

## Performance investigation (2026-09-27)

A live gameplay session reached 21.1 GB physical footprint: 20.8 GB was graphics
allocations, including 15.9 GB swapped out. The 4 GB guest virtual reservation
was not the source. The renderer now expands misaligned Xbox vertex attributes
only for the vertices in the draw. This avoids ANGLE's conversion of entire
4/16 MB backing buffers for attributes such as SHORT1 at byte 30 of a vertex.
Occlusion queries also use the last completed result instead of spinning on
unfinished Metal work, matching the existing desktop query-buffer behavior.

Historical seventy-second `a30` launch profiles gave these results on the M5
Mac (vsync enabled). Their requested grenade workload was not acknowledged by
the engine, so they are not evidence of grenade stress-test coverage:

| Build/mode | Median frame | 95th percentile | Peak physical footprint |
| --- | --- | --- | --- |
| Before renderer fixes, 4:3 | 16.67 ms | 17.32 ms | 1181 MB |
| After fixes, 4:3 | 16.67 ms | 17.41 ms | 468 MB |
| After fixes, native aspect fullscreen | 16.67 ms | 17.88 ms | 511 MB |

A historical 70-second launch profile requesting an explosion every 0.25 seconds
recorded 16.67 ms median, 17.25 ms p95 and 460 MB peak footprint. That workload
was also unverified. The current benchmark fails when the engine rejects a
command, the console disconnects, the game exits early or rendering faults.

These runs show reduced memory demand, not a measured increase in maximum FPS:
both versions reached the 60 FPS presentation limit. The after runs also captured
periodic screenshots. They do not yet reproduce or rule out the original long
session's 21 GB growth. Campaign screenshots were checked for geometry and HUD
rendering; broader visual and sustained-play comparisons remain necessary.

With other Halo instances closed, reproduce the test using isolated saves:

```sh
python3 tools/macos_benchmark.py --output build/macos/performance/retest --effects --fullscreen
```

`--host` and `--guest` choose a comparison build. `--levels` accepts an ordered
list of campaign or test multiplayer maps; `--cycle-seconds` repeats that list.
`--checkpoints` requests a normal safe save and checks the completed revert
before continuing. Use a30 for this check: the initial a10 cryo scene can refuse
an unsafe save. `--screenshot-every N` captures every N frames. The helper uses
the existing private loopback developer console and creates fresh settings and
saves; its output directory must not already exist. Multiplayer test maps use
Slayer so a player is created. The CSV, console transcript, game log and
`validation.json` record completed work and the actual guest image hash.
Set `HALO_PERF_LOG=/absolute/path/frames.csv` for profiling an ordinary launch.
Driver draw time includes waits (including drawable/vsync waits); it is not a
GPU timestamp measurement. Normal launches do not enable per-draw profiling.

See [Apple regression checks](../../docs/apple-regression-checks.md) for the
source-only CI boundary, local gameplay checks and measured upload comparison.

The [overshield shadow regression](../../docs/overshield-shadow-fix.md) records
the GLES border-sampling correction and its fixed-camera/gameplay evidence.
Run `python3 -m unittest tools.test_texture_border -v` with Metal access for the
offscreen production-shader pixel checks.

## Phase two

Use this ANGLE/Metal build as the reference before changing rendering behavior.
Capture repeatable `a10`, `a30`, and `b30` scenes, recording frame-time percentiles,
GPU time, resident memory, loading time, and shader compilation stalls. Then
prioritize measured bottlenecks: shader/pipeline caching, upload and dirty-region
costs, resolution scaling, frame pacing, and CPU hot paths. Preserve the 30 Hz
simulation and validate interpolation separately.

Direct NV2A-to-Metal shader translation is a later experiment, with visual
comparisons for fog, water, shadows, blending, gamma, and render targets. ANGLE
already uses Metal today; a direct renderer should earn its maintenance cost
through measured performance or compatibility improvements.
