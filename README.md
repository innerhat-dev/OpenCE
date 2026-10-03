# Halo OG

Original Xbox **Halo: Combat Evolved**, brought to modern devices through its
decompilation and native ports.

Our goal is to reproduce the Halo 1 experience that OG players know: movement,
weapons, sounds, presentation, and the original 30 Hz simulation. Community maps
and explicitly enabled competitive/practice tools give serious players more
ways to play while keeping OG rules as the default. Faithful reproduction is
the goal; complete retail parity is still being tested.

**[Get running and join the playtest →](docs/playtesting.md)**

![Original Halo main menu running on Apple Silicon](docs/images/main-menu.png)

## Download

Use the **[test-v0.3.0-net11 testing release](https://github.com/pfista/halo-og/releases/tag/test-v0.3.0-net11)**.
Choose your platform:

| Platform | Testing package | Requirements |
| --- | --- | --- |
| Mac | [Halo-OG-macos-arm64.dmg](https://github.com/pfista/halo-og/releases/download/test-v0.3.0-net11/Halo-OG-macos-arm64.dmg) | Apple Silicon, macOS 26+ |
| Windows | [halo-windows-release.zip](https://github.com/pfista/halo-og/releases/download/test-v0.3.0-net11/halo-windows-release.zip) | x86/x86-64 PC, OpenGL 4.5 |
| Linux | [halo-linux-release.zip](https://github.com/pfista/halo-og/releases/download/test-v0.3.0-net11/halo-linux-release.zip) | x86, OpenGL 4.5, [32-bit runtime libraries](port/linux/README.md#requirements) |
| Android | [halo-android-release.zip](https://github.com/pfista/halo-og/releases/download/test-v0.3.0-net11/halo-android-release.zip) | ARM64, Android 9+, OpenGL ES 3; controller or keyboard |

All packages in the release come from the **same source commit**. Use the same
tag when playing together. The release includes `SHA256SUMS`, `provenance.json`,
and Mac installation notes. These are experimental builds.

If the release is not available, sign in to GitHub and use successful runs of
this repository's [macOS DMG workflow](https://github.com/pfista/halo-og/actions/workflows/macos-dmg.yml)
or [Build workflow](https://github.com/pfista/halo-og/actions/workflows/build.yml).
Download the platform's `halo-…-release` artifact, or `halo-macos-arm64-dmg`, and
match the runs' commit SHA. Artifact downloads are ZIPs and expire.

The Mac test build is ad-hoc signed and unnotarized. Install **Halo OG.app** into
Applications; no Homebrew or developer tools are needed. Testing packages have
automatic updates disabled. [Installation steps](docs/playtesting.md) explain
first launch, platform dependencies, and updating.

## Get running

1. Download and install the package for your platform.
2. Supply your own original Xbox Halo disc image (`.iso` / `.xiso`) or complete
   extracted `maps` folder. **USA NTSC data is recommended** and required by the
   current community-map collection. Game data is not bundled; PC, Custom
   Edition, Anniversary, and MCC data are not substitutes.
3. Create/select a profile, try a stock map, then
   [join the multiplayer playtest](docs/playtesting.md#play-together).

Mac first launch imports a disc or offers to manage a copy of your maps.
Data, saves, and settings live in `~/Library/Application Support/Halo OG/`.
Prior `Halo CE Universal` data is copied where needed, preserving the old folder
and existing files. External map folders can remain selected.
[Data management details](docs/macos-menu-and-releases.md#independently-supplied-data).

## Community maps and competitive options

Mac Settings can **download approved community maps in the background** after
you opt in. The Cloudflare R2 pilot currently serves **Downrush**, built for
Xbox v5 NTSC data. Verified downloads remain usable offline. Windows, Linux,
and Android currently install that same map manually;
[community-map setup](docs/playtesting.md#community-maps) includes its download.

**PB Options** offers a match timer, spawn markers, timer announcements, and
optional silent movement/weapon-ready sounds. All modifications default **off**;
the host chooses the match's options. Use **Stock** for original-rule play.
Timer announcements need a separate audio pack, not bundled with these builds.
[PB Options](docs/performance-options.md) explains settings and compatibility.

The current network protocol is **11**; protocol-10 builds need updating.
Enabled PB Options require compatible peers. For the first cross-platform
tests, use matching Halo OG packages with PB Options off.

## What has been checked

Native Mac campaign/input/audio smoke checks and protocol-11 stock multiplayer
have been exercised. A client starting without Downrush downloaded the verified
pilot and completed two consecutive Slayer matches with a host on the **same
physical Mac**; offline reuse also passed. Physical cross-platform devices,
Internet/NAT play, long sessions, full campaign coverage, and reference-Xbox
fidelity remain acceptance work. See the [fidelity policy](docs/xbox-fidelity.md),
[protocol review](docs/upstream-review-2026-10-03.md), and
[map-delivery evidence](docs/map-publishing.md).

## Build and contribute

[Build from source](docs/building.md) · [Apple setup](docs/apple-build.md) ·
[Community-map conversion](docs/community-maps.md) ·
[Report a playtest problem](docs/playtesting.md#report-a-problem)

The experimental [iPhone port](port/ios/README.md) is a developer build with no
installation package in this testing release. Halo OG builds on
[bnunu/halo-1](https://github.com/bnunu/halo-1),
[punpckhdq/halo](https://github.com/punpckhdq/halo), and the platform work in
[cybersecurity/halo-ce-universal](https://github.com/cybersecurity/halo-ce-universal).
We review upstream changes individually and keep optional modifications explicit.
