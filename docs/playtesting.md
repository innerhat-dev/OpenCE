# Playtesting Halo OG

Use the same Halo OG testing package as the other players:
**[test-v0.3.0-net11](https://github.com/pfista/halo-og/releases/tag/test-v0.3.0-net11)**.
If the release is unavailable, the [download table](../README.md#download)
explains matching-commit CI artifacts.
You do not need to compile the game.

Bring your own original Xbox Halo: Combat Evolved disc image (`.iso` / `.xiso`)
or extracted game data. Use one complete set. **USA NTSC is recommended**;
the Downrush download requires NTSC cache build `01.10.12.2276`. PC, Custom
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

First verify a stock-map match. The approved public download pilot currently
contains **Downrush** for original Xbox v5 NTSC data.

On **Mac**, open **Halo OG → Settings…**, enable **Download approved community
maps in the background**, and accept the prompt. **Check Maps / Retry** refreshes
the catalog. The current pilot downloads on launch; joining a host whose
approved map is missing also requests it. Watch the Settings progress/error
text. Installed, verified maps work with downloads disabled and offline.
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
