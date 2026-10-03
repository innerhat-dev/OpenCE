# Playtesting Halo OG

Use the same Halo OG testing package as the other players:
**[test-v0.3.0-net11-dmg2](https://github.com/pfista/halo-og/releases/tag/test-v0.3.0-net11-dmg2)**.
If the release is unavailable, the [download table](../README.md#download)
explains matching-commit CI artifacts.
You do not need to compile the game.
This revision adds the Mac installer screen. Its game app and other platform
ZIPs match `test-v0.3.0-net11`, so players using either release can play together.

Bring your own original Xbox Halo: Combat Evolved disc image (`.iso` / `.xiso`)
or extracted game data. Use one complete set. **USA NTSC is recommended**;
the community downloads require NTSC cache build `01.10.12.2276`. PC, Custom
Edition, Anniversary, and MCC data are not substitutes.

## Mac

Requires Apple Silicon and macOS 26 or later. Use the minimum recorded in
`macos-README.txt` / the package's `README.txt` if it changes in a later build.

1. Open `Halo-OG-macos-arm64.dmg` and drag **Halo OG.app** into **Applications**.
2. Open the app. This testing build is ad-hoc signed and unnotarized; if macOS
   blocks it, use **System Settings → Privacy & Security → Open Anyway** for
   this app after attempting to open it. See [Mac installation](../port/macos/README.md#download).
3. Choose your Xbox disc image, or **Choose Maps Folder**. A disc import
   extracts maps without changing the image. For a folder, **Copy and Manage**
   copies the maps into the app's data folder; **Use This Folder** keeps the
   external folder selected. Your originals stay in place.
4. Select/create your profile and try a stock map before joining others.

Use **Halo OG → Settings…** or the menu-bar helmet for fullscreen, map selection,
download status, and **Open Saves Folder**. Data lives in
`~/Library/Application Support/Halo OG/`. First launch copies old
`Halo CE Universal` data where needed, preserving old and existing files. A
copy failure stops launch with an explanation so you can correct it and retry.

**Escape** pauses/releases the mouse; **F12** releases or recaptures it.
**WASD** moves, the mouse aims, and the left mouse button fires. Controls can be
remapped; see [Mac controls](../port/macos/README.md#launch).

## Windows

1. Extract `halo-windows-release.zip` into a writable folder. Keep `halo.exe`
   and `SDL3.dll` together; run the extracted executable, not one inside the ZIP.
2. Open `halo.exe`. If no maps are found, choose your original Xbox disc image
   in the game's import prompt. It extracts `maps` beside the executable.
   An existing complete `maps` folder can also go there.
3. Select/create a profile and try a stock map.

This is a portable 32-bit x86 build for an x86/x86-64 PC with OpenGL 4.5.
An exact Windows runtime minimum has not been established by this playtest.
Settings are in `config.toml` beside the executable; saves default to
`%APPDATA%\Halo OG`. Old `%APPDATA%\halo` saves are copied without overwriting
existing data. See [Windows setup](../port/windows/README.md#start-the-game).

## Linux

1. Extract `halo-linux-release.zip` into a writable folder.
2. Install your distribution's **32-bit** glibc, SDL3, OpenGL/Mesa, and
   PipeWire or PulseAudio client libraries. The executable is 32-bit x86 and
   requires OpenGL 4.5. See [Linux runtime requirements](../port/linux/README.md#requirements)
   for package names; distribution compatibility still needs testing.
3. From the extracted folder, run `./halo`. If necessary, first run
   `chmod +x halo`. Select your original Xbox disc image when prompted, or
   put a complete `maps` folder beside the executable.
4. Select/create a profile and try a stock map.

Settings are in `config.toml` beside the executable. Saves default to
`$XDG_DATA_HOME/halo-og`, usually `~/.local/share/halo-og`. Old `halo-linux`
saves are copied while preserving existing files. See [Linux setup](../port/linux/README.md#start-the-game).

## Android

1. Extract `halo-android-release.zip` and copy `app-release.apk` to the device.
2. Install the APK, allowing installation from that file source if Android asks.
3. Copy your Xbox disc image onto the device, open Halo OG, and use its file
   picker to select the image. Wait for map extraction to finish.
4. Connect a game controller or keyboard. **Android gameplay has no touch
   controls.** Keep the app in the foreground during a match.

Requires ARM64, Android 9/API 28 or later, and OpenGL ES 3. Device gameplay
is a playtest target. If Android reports a signature conflict with an older
installation, back up its maps/saves before removing it—uninstalling can remove
app data. See [Android installation/data](../port/android/README.md#game-data).

## Play together

1. Confirm everyone uses the **same Halo OG release tag/commit**, protocol 11,
   and matching map data. Old protocol-10 builds cannot join. For this first
   test, use a stock map and leave **PB Options → Stock** selected.
2. The host opens **Multiplayer → System Link** and creates a game. Select a
   stock map such as Blood Gulch and a game type such as Slayer.
3. On the same LAN, clients open **Multiplayer → System Link** and select the
   host's game. Allow local-network/firewall access if your operating system
   prompts; isolated guest Wi-Fi may prevent discovery.
4. For an Internet test, the host shares the current `halo://join/…` invite
   copied to its clipboard. The client copies the invite and returns to the
   game, or opens the registered invite link. Once the host appears in System
   Link, select it and join. The host app must remain running.
5. Start the match. Check movement, shooting, damage, deaths/respawns, audio,
   and the scoreboard on both machines. Play a second match without restarting.

Physical cross-platform and Internet/NAT play are still being validated. Report
which pairing/network worked or failed; a successful CI build is not proof of
that pairing. [Invite/network details](../port/linux/README.md#internet-play)
and [Mac networking](../port/macos/README.md#launch) cover troubleshooting.

PB Options are optional. The host chooses them in the game type editor or
multiplayer pause menu; all peers need compatible options support. Timer Sounds
additionally require a separately supplied local audio pack.
[PB Options](performance-options.md) explains these settings.

## Community maps

First verify a stock-map match. The public collection contains **40 approved
community maps** for original Xbox v5 NTSC data, about **863 MiB** in total.
This includes PB community variants with their normal embedded Halo dependencies;
original disc images, stock map files, campaign files, and `ui.map` are excluded.

On **Mac**, open **Halo OG → Settings…**, enable **Download approved community
maps in the background**, and accept the prompt. **Check Maps / Retry** refreshes
the catalog. Missing maps from the collection are queued on launch while the
app runs; joining a host whose approved map is missing also requests it. Watch
the Settings progress/error text. Installed, verified maps work with downloads
disabled and offline.
Reopen map selection after completion; restart if the current session still
holds an older selection. Downloads never replace your original maps.

On **Windows/Linux/Android**, automatic map downloads are not implemented yet.
Download the same approved
[downrush.map](https://dl.oghalo.com/maps/sha256/3282e580e782f939ae00c63f01971238eb0f85db19a2467efe42b5cb5600d126/downrush.map)
and put it into the active game's `maps` folder, keeping the exact filename.
Windows/Linux usually keep this beside the executable; Android keeps it under
`/sdcard/Android/data/com.halo.decomp/files/maps/` (see its data instructions).
Mac can also use this file manually in its selected `maps` folder. Restart
after adding it. Preserve any existing same-name map first; all participants
must use the same bytes. The approved file is 26,480,640 bytes, SHA-256
`3282e580e782f939ae00c63f01971238eb0f85db19a2467efe42b5cb5600d126`.

For another map, open the [public catalog](https://dl.oghalo.com/catalogs/testing/current.json),
find its `id`, and append its `object_key` to `https://dl.oghalo.com/` to download
the approved file. Keep `<id>.map` as its filename and use the catalog's
`file_bytes` and `sha256` to check it. All players need the same map bytes.
Downrush has completed two consecutive multiplayer matches on one Mac; the
other maps have short local load/render checks, with multiplayer/mode testing
still needed. All 40 public downloads have been checked against their hashes.

<details>
<summary>Manual downloads for all 40 community maps</summary>

| Map | Map | Map | Map |
| --- | --- | --- | --- |
| [atlas.map](https://dl.oghalo.com/maps/sha256/7f2bbfc141152896f49b2be03d6412227ce39b63600950766caff5478e6d3513/atlas.map) | [badcreek.map](https://dl.oghalo.com/maps/sha256/42db0b80a833e0d9455a507080bf53024c17c975021824471b14d4d425508826/badcreek.map) | [birdhouse.map](https://dl.oghalo.com/maps/sha256/4804b99739fc9765dfbbb6c9f7fe42c8d74605fb7a72e47e862e3d70cf9520f7/birdhouse.map) | [calam.map](https://dl.oghalo.com/maps/sha256/84aacd00adb92b82ebef92210334ee1b05d55289697c1d1e01b265747f4d8944/calam.map) |
| [chilledout.map](https://dl.oghalo.com/maps/sha256/73d835d11efe24a210699fffc984a195851b79f62feca09c4b3786d0731cd6d6/chilledout.map) | [dammy.map](https://dl.oghalo.com/maps/sha256/df9ac6c0482b8a764f0e257ea94618d7000a85076f0450c7acd51db4db1604ab/dammy.map) | [decidia.map](https://dl.oghalo.com/maps/sha256/57bc9d59dcf3d62321a9cebfb3c9006909cdc059bfd681bf6d19efea38b5f76f/decidia.map) | [dere.map](https://dl.oghalo.com/maps/sha256/cf01b23457c1bc1635b94e8eb480f7a8e006ece7e8c81f0c9d07d65d9bbd4c8e/dere.map) |
| [descent.map](https://dl.oghalo.com/maps/sha256/153dc7596166ca70f02529849c28fbdd1e9efb8af57921d0474a03405e2eafd7/descent.map) | [doubletake.map](https://dl.oghalo.com/maps/sha256/b05085aa00501e7ee8c3cb6db123b8b7cbeef47026daff6e14a2bd0543b15dff/doubletake.map) | [downfall.map](https://dl.oghalo.com/maps/sha256/68e22e10b894d6da8b33a6d13923e04015b02dbf742426d0de654a3b906f9cdf/downfall.map) | [downog.map](https://dl.oghalo.com/maps/sha256/a1763a44b4ef016433bb57fb70a3954ab2828f8a6a7ea37e3401bd850eb78b6f/downog.map) |
| [downrush.map](https://dl.oghalo.com/maps/sha256/3282e580e782f939ae00c63f01971238eb0f85db19a2467efe42b5cb5600d126/downrush.map) | [dread.map](https://dl.oghalo.com/maps/sha256/b2a37d9bee0d757d0f86b1c0835ab75c29d0ede13cbcda1bec9d825e90744777/dread.map) | [dread_new.map](https://dl.oghalo.com/maps/sha256/9e2057f74ff04beed79c3dedcf953e45a8bfa0a73436616e2a69fddc3e502d5e/dread_new.map) | [exhibit.map](https://dl.oghalo.com/maps/sha256/ac49d1c142285622274294cd26fa83386abf6b6087052ccf1f9e95cb3c73496f/exhibit.map) |
| [fallout.map](https://dl.oghalo.com/maps/sha256/f05a258a0e518196c7aa3ade27ffe59d127da0888078c81cd902e71bc394c3b0/fallout.map) | [h1pb_chillout.map](https://dl.oghalo.com/maps/sha256/70a1d647ae4f09904db33103a7383e60e54bd0b23d8fd320008525af24478717/h1pb_chillout.map) | [h1pb_hangemhigh.map](https://dl.oghalo.com/maps/sha256/5699b09143811309de3451f610a1fcefb58860620168186b5789205a2c758fca/h1pb_hangemhigh.map) | [h1pb_prisoner.map](https://dl.oghalo.com/maps/sha256/ed009445753401aefe00a56b963a4911dfb5be4d98f6cdf45bd29296e936965a/h1pb_prisoner.map) |
| [h1pb_wizard.map](https://dl.oghalo.com/maps/sha256/2dfb97492d18278d387008991559c409ce46b48fd08e5bbd4040c1ba0b6debba/h1pb_wizard.map) | [hangman.map](https://dl.oghalo.com/maps/sha256/d41970a9d06e60c8c2678c090deea2d2adcb48166519e1b1c1f460e278ff8674/hangman.map) | [hotbox.map](https://dl.oghalo.com/maps/sha256/e1295796bbc4cd684bc70e75111d53340d77e0f6a3cfe62a07e5911f389be47d/hotbox.map) | [imminent.map](https://dl.oghalo.com/maps/sha256/5855435bbdb4b90dc4c0b894a680a7314561ae18b3c89afbca610b9b7551d8a4/imminent.map) |
| [jaywalk.map](https://dl.oghalo.com/maps/sha256/9703fb1f7d1c2b380399fcc5e0ec4f0a94fc9a43b42014113836d336e43902c5/jaywalk.map) | [longshot.map](https://dl.oghalo.com/maps/sha256/c070c2ee037f89021f9f33ac7badd37fbe15e2b273353f19e699f7145c771aa4/longshot.map) | [octagon.map](https://dl.oghalo.com/maps/sha256/30166bb0bec257fe660af042b2804ae97f7aab8b903dcb005c3f90f661fda9c2/octagon.map) | [octagon_b.map](https://dl.oghalo.com/maps/sha256/56a21aa0737c2eb465efe51b74afeb35116676824db419c66297bc54de9e9ac9/octagon_b.map) |
| [outbound.map](https://dl.oghalo.com/maps/sha256/e37a0d68b9d9be998321740c9ff3a3826d0697b0ace3f5160562ddcd994f904b/outbound.map) | [overflow.map](https://dl.oghalo.com/maps/sha256/c2d44c77cfb680bd14bc2e49000fb938a142ad89ed533524f8665cbef4ea79c0/overflow.map) | [patrace.map](https://dl.oghalo.com/maps/sha256/fc68763f456b41ea8445b6e2a7db2922f4160cd587565b07dd47c3854474c77e/patrace.map) | [redshift.map](https://dl.oghalo.com/maps/sha256/31b3f16fea0cdfab090d13cf8cd2310a9e4021fdf84f4e26f4473c3f7aa76dc2/redshift.map) |
| [salvation.map](https://dl.oghalo.com/maps/sha256/e90eb1e593ba615906485031269db4c9da1aafe59e86c9e4e8a813d244ae0021/salvation.map) | [slammer.map](https://dl.oghalo.com/maps/sha256/d25ad27e7c29a09584cd0be4d29b92054fbb7c83bf77b68c7f5b8f13a73e2caa/slammer.map) | [temple.map](https://dl.oghalo.com/maps/sha256/998a6011946dd3db9ff3fef215bedb331362eb859a190d7057d5b9a1ad1221a3/temple.map) | [tinker.map](https://dl.oghalo.com/maps/sha256/d5d605ad7308b5b82be4d0c3b0dbb4b8a0928a9d8a62bfbf51fe5fec9c991875/tinker.map) |
| [tinkered.map](https://dl.oghalo.com/maps/sha256/6e6ea4b56386d7b0ed805acb74c5eea0e98fc9c6c6070d225c24f10a4b2cd222/tinkered.map) | [weld.map](https://dl.oghalo.com/maps/sha256/25a89672437f81746913cd5848f01b3d7383bc4c0e2945e51a8e05f96d378ca6/weld.map) | [whiskey.map](https://dl.oghalo.com/maps/sha256/19d06ab5f4a2d3dcaaf29f6d0f89ca74eef431c849d7982e6918944a2f368d8d/whiskey.map) | [worthy.map](https://dl.oghalo.com/maps/sha256/df913543827171da86d545aca7c5b6c5d8875a4fa938805b051ea54396cf2316/worthy.map) |

</details>

Original stock maps and `ui.map` remain user-imported. A PC/Custom Edition map
cannot be made compatible by renaming it or changing its version field.
[Map conversion](community-maps.md) explains the supported pipeline.

## Report a problem

Open an [issue in Halo OG](https://github.com/pfista/halo-og/issues/new) with:

- The release tag and commit from `provenance.json` or `BuildInfo.txt`.
- Both devices' OS/CPU/GPU, controller or keyboard/mouse, and which is host.
- LAN or Internet, the map/build, game type, and whether PB Options were enabled.
- What you did, what happened, and whether restarting or a stock map changes it.
- Relevant log lines or a screenshot. Mac logs are `halo.log` in Application
  Support; Windows/Linux logs are `debug.txt` in the active data root; Android
  has `debug.txt` in its app data folder.

Do not attach game data, private invite codes, credentials, or personal saves
to a public issue. Check logs for personal paths before sharing. Keep originals
and backups while testing. See [current validation limits](../README.md#what-has-been-checked).
