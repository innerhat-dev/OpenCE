# Build on Apple Silicon

Start here for both macOS and iPhone. All commands run on an Apple Silicon Mac
from the repository root unless stated otherwise. The Mac game runs natively;
the iPhone build also uses native ARM code and ANGLE's Metal renderer.

To run the Mac app without compiling, download the
[macOS DMG artifact](../port/macos/README.md#download). It bundles the runtime
dependencies; only your own original Xbox game data is needed separately.

## 1. Clone and install public dependencies

```sh
git clone https://github.com/pfista/halo-ce-universal.git
cd halo-ce-universal
```

Install Xcode Command Line Tools for a Mac-only build, or full Xcode 26 or later
for iPhone. Open Xcode once to accept its license and install the iOS platform
support. For simulator testing, also install an iOS 26+ simulator runtime in
Xcode's Settings → Components. Physical-device builds do not need a simulator.

Using [Homebrew](https://brew.sh/):

```sh
brew install python cmake llvm@22 lld@22 sdl3 ninja
export HALO_MACOS_LLVM_BIN="$(brew --prefix llvm@22)/bin"
export PATH="$(brew --prefix lld@22)/bin:$PATH"

# For iPhone builds; adjust if Xcode is installed elsewhere:
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer

python3 tools/macos_setup.py
```

The compiler adapter requires **LLVM 22** (tested with 22.1.8), not Apple clang
or a newer LLVM major. [Homebrew's LLVM 22 formula](https://formulae.brew.sh/formula/llvm@22)
provides that version; LLD is a separate formula. Keep the exports in the shell
used for later builds. Do not put LLVM's entire `bin` directory ahead of the
system compiler: the host builds with Apple's clang, while
`HALO_MACOS_LLVM_BIN` selects the game compiler. Python 3.10+ and CMake 3.28+
are required.

Already have LLVM 22 at `/opt/homebrew/opt/llvm`? Use that keg for
`HALO_MACOS_LLVM_BIN` instead. Setup accepts an ELF-capable `ld.lld` on `PATH`;
if unavailable, installing `uv` enables its local Zig/LLD fallback. Ninja can
come from Homebrew or that fallback environment.

Setup downloads only public dependencies. ANGLE and Khronos headers have pinned
URLs and SHA-256 checksums in [dependencies.json](../port/macos/dependencies.json).
The build also fetches SDL3 3.4.16 and musl 1.2.5. No Android NDK is required.

## 2. Supply game data to play

Mac and iPhone native builds use the declarations in
[port/include/xdk](../port/include/xdk/README.md). They do not require the
private Xbox SDK, `xbox/include`, or `cachebeta.exe`. The Mac app can be compiled
and packaged without game data using `python3 tools/macos_build.py --no-data-path`;
first launch then asks for the user's disc image or extracted maps folder.

To play, supply **original Xbox Halo: Combat Evolved maps** extracted from your
retail disc image. These are not included or downloaded by the build scripts.
Supported Xbox version-5 headers are PAL `01.01.14.2342` and USA
`01.10.12.2276`. Use one complete set; do not mix regions or builds. Halo PC,
Custom Edition, Anniversary and MCC maps are not substitutes.

The checkout should look like this:

```text
halo-ce-universal/
  assets/
    maps/
      ui.map
      a10.map
      a30.map
      ...                  # all remaining campaign and multiplayer maps
```

To extract an existing XISO, one option is the open-source
[XboxDev/extract-xiso utility](https://github.com/XboxDev/extract-xiso#building).
Build it under the ignored build directory, then copy only the maps into place:

```sh
git clone https://github.com/XboxDev/extract-xiso.git build/tools/extract-xiso
cmake -S build/tools/extract-xiso -B build/tools/extract-xiso/build
cmake --build build/tools/extract-xiso/build
build/tools/extract-xiso/build/extract-xiso \
  -x -d build/game-extracted "/path/to/your/Halo.xiso.iso"
mkdir -p assets
cp -R build/game-extracted/maps assets/
```

Use the actual paths and filename case from your extraction. If you already
have an extracted `maps/` folder, copy it directly; extraction is unnecessary.
Keep the disc image outside the repository. Supply the full set to play the full
campaign. The Mac data importer validates supported map headers when selecting
a disc image or game folder. The older SDK-oriented `macos_preflight.py` check
is not a prerequisite for these native builds.

## 3. Build and play

- [macOS: compile, launch, controls and performance](../port/macos/README.md#build).
  No Apple development account or special entitlement is needed.
- [iPhone: compile, sign and install](../port/ios/README.md#build).
  Use your own paid Apple development team, a unique bundle identifier and a
  phone in Developer Mode. A Personal Team could not provision the required
  Extended Virtual Addressing entitlement in testing.
- [iOS simulator](../port/ios/README.md#simulator): useful for menu and touch
  checks without device signing; it does not establish device performance.

The tested devices are an M5 Mac on macOS 26.5.1 and an iPhone 17 Pro Max on
iOS 26.6.2. The current bundled SDL3 requires macOS 26.0, which packaging
enforces in the app's minimum version; the iPhone build targets iOS 26+.
Other OS/device combinations have not been exhaustively tested.

## Development workflow

[Apple regression checks](apple-regression-checks.md) covers source-only CI,
native menu responsiveness and local gameplay/renderer validation.

Use `main` in [pfista/halo-ce-universal](https://github.com/pfista/halo-ce-universal)
as the working branch. `origin` points to that fork; `upstream` points to
[cybersecurity/halo-ce-universal](https://github.com/cybersecurity/halo-ce-universal).
For a fresh clone, add the upstream remote:

```sh
git remote add upstream https://github.com/cybersecurity/halo-ce-universal.git
git fetch upstream
```

This is an independent fork with an [original-Xbox fidelity policy](xbox-fidelity.md).
Keep the last integrated baseline recorded while staying current with useful core
improvements through selective review. During upstream-update work, inspect every
new commit's actual diff and behavioral effects. Prioritize verified matching-
decompilation progress, performance, stability and platform fixes. Consider netcode
and potential matchmaking improvements individually, with timing and fairness
validation. Preserve original Xbox NTSC gameplay and presentation; high-refresh
rendering can coexist with the original 30 Hz simulation.

Do not merge upstream `main` wholesale. Select or cherry-pick accepted changes and
split mixed commits to exclude unrelated modifications. Renaming/rebranding,
replacement fonts/artwork/HUD, overhead player labels and changes to gameplay rules
are excluded by default unless the user requests them separately. Record each
commit's hash, category, decision, reason, validation and integration status in the
update's review ledger, including rejected, deferred and already-equivalent
changes. Record how far upstream was reviewed separately from how far it was
integrated. See the fidelity policy for the detailed review criteria.

When a contribution is ready, prepare a focused branch against
`upstream/main` and open a pull request into that repository. CI still checks
fork pushes; automatic releases and Discord build notifications run only in
the upstream repository.

## Source and build artifacts

`assets/`, `xbox/`, `original/` and `build/` are ignored, along with disc images,
map files, SDK archives, Apple signing material and generated Xcode projects.
Generated game binaries stay under `build/` and must not be committed. The
[macOS DMG workflow](https://github.com/pfista/halo-ce-universal/actions/workflows/macos-dmg.yml)
builds a separate downloadable artifact from the committed source and public
dependencies, with no game data or private SDK inputs. It audits the bundle
before packaging and retains the DMG artifact for 14 days. This CI download is
separate from the Developer ID and Sparkle release process.

Device signing settings belong in your local Xcode account and ignored build
directory. Pass your team ID and bundle identifier on the command line; do not
hardcode your team, certificate name, device IDs or provisioning profile into
source files. The checked-in entitlement file contains only a capability flag,
not an identity or secret.

iPhone apps bundle your maps by default. `--no-bundle-maps` leaves them out,
but does not turn a locally built app into an approved redistributable package.
Keep compiled apps, logs and provisioning profiles local. When contributing
source, inspect `git diff --cached --name-only` and `git diff --cached` before
committing; ignore rules cannot prevent an explicit `git add -f`.
