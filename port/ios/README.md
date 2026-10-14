# iPhone and iPad

Native ARM64 iOS/iPadOS 26+ build using innerhat's signed ILP32 runtime and
ANGLE Metal renderer. Both iPhone and iPad are supported by the app bundle.
No game data is packaged: first launch presents **Choose Halo ISO** in Files.
Import validates supported original Xbox PAL/NTSC-US maps, verifies a retained
private image by SHA-256 readback, and atomically publishes the new map cache.
Subsequent launches reuse it. Existing imports/saves from our earlier branch
and existing innerhat `Documents/GameData/maps` installations remain readable
when the same bundle ID and account are used. Different IDs have separate data.

## Download a test IPA

[Download the unsigned IPA and re-signing kit](https://github.com/AttilaTheFun/halo-ce-universal/releases/tag/apple-ios-pr1-20261014-v29) for this PR.
Follow [the re-signing guide](RESIGNING.md). Source builds starting at build 17
no longer require Extended Virtual Addressing. Free-account AltStore and
LiveContainer installation remain unverified; builds up to 16 still require it.
You supply your own game image on first launch. No device ID needs to be sent
to the maintainer when you use your own signing account.

## Build

Follow [Apple build setup](../../docs/apple-build.md). LLVM 22, full Xcode,
CMake and Ninja are required; no private Xbox SDK or game image is needed to
compile. Do not bundle maps in an app distributed to others.

```sh
export HALO_MACOS_LLVM_BIN="$(brew --prefix llvm@22)/bin"
export PATH="$(brew --prefix lld@22)/bin:$PATH"
python3 tools/macos_setup.py
python3 tools/ios_build.py --platform simulator
python3 tools/ios_build.py --platform device --sign \
  --team YOUR_TEAM_ID --bundle-id com.yourname.halo
python3 tools/ios_package.py build/ios/device/Release-iphoneos/Halo.app build/Halo.ipa
```

The repository default identifier remains `local.halo.ce-universal.ios`.
Choose your own identifier for distribution; personal account settings do not
belong in this repository. `--no-bundle-maps` remains accepted for compatibility,
but map bundling has been removed. `--host-only` is suitable only when reusing an
unchanged guest image. Any game/compiler/bridge change requires the normal build.

The runtime reserves an OS-selected aligned virtual arena without Extended
Virtual Addressing or Increased Memory Limit. No JIT entitlement is used. A development
or Ad Hoc profile must cover the installing device. See the [IPA re-signing
guide](RESIGNING.md) for a locally held identity/profile workflow.

## Play and settings

Touch controls hide when a physical controller connects, and return on
disconnect. The primary hardware controller shares player one with the touch
controller; additional controllers retain separate slots. D-pad buttons support
menu navigation. Flashlight and grenade-switch labels match the default game
bindings.

For touch plus a controller as **different players**, shake to open settings,
enable **Touch as a separate player**, then relaunch. Touch remains player one
and stays visible; the first hardware controller becomes player two. Create or
join a multiplayer lobby, choose **Add Player**, and use the additional
controller to select its profile. This also permits the second controller's
profile selection in **Co-op Campaign**. With the option off (the default),
connecting a controller still hides touch controls. Hardware split-screen
play has not yet been verified on a physical device with this revision.

Mac uses its existing keyboard/mouse/controller path without touch.

Shake the phone/tablet for the settings modal. It offers optional MetalFX
spatial upscaling, bounded shader-stall recording and a share sheet for reports.
The graphics settings select Metal (ANGLE) or native OpenGL ES, with a relaunch
to change renderer. The separate WebKit room-code transport remains retired. The in-game browser
uses upstream's current native/browser networking. The default renderer is
Metal and MetalFX remains off unless explicitly enabled.

The ANGLE blob cache is private and bounded to 64 MiB; misses compile normally.
Reports contain shader sources and timing, not maps or saves. First-use GPU
recording adds synchronization overhead. MetalFX benefit depends on hardware
and selected render resolution and is not a guaranteed performance gain.

## Validation

[Migration and validation record](../../docs/apple-ios-migration.md) records
what has been carried over and what still needs device testing. Simulator
results do not prove physical iPhone/iPad memory reservation or GPU performance.
Use your own device through your usual installer; test tooling should not
replace or launch apps on someone else's device.

Simulator builds keep a separate signed image in `build/ios-simulator` and use
the Mac address arena because recent simulators reserve the device arena.
`--host-only` reuses only the image for the requested platform.
