# Mac menu, local data and releases

The native AppKit menu runs in the game's process. Its monochrome helmet opens
Settings, changes fullscreen immediately, selects game data, opens saves and
controls, checks updates, and quits through the normal game exit path. Settings
is also available with Command-comma; Control-Command-F toggles fullscreen.
Release the captured mouse with F12 to reach the menu bar. The existing Dock
icon is retained; `port/macos/Helmet.svg` generates a vector template PDF.

## Independently supplied data

After the initial game build and public dependency setup, build without a local
checkout path:

```sh
python3 tools/macos_build.py --host-only --no-data-path
python3 tools/macos_release.py local-dmg
```

The resulting `build/macos/Halo-0.3.0-local.dmg` is a local test artifact. It has
no notarization ticket and is not a verified public release. It includes an
Applications shortcut and the app, without maps, ISOs or a local checkout path.

The end user needs no Homebrew, XDK or build tools. SDL3, ANGLE, Sparkle and the
compiled engine are bundled. First launch accepts the user's locally obtained
original Xbox Halo XISO/ISO, or extracted game folder (its `maps` subfolder also
works). Nothing is downloaded or uploaded by this selection. Disc imports copy
maps to a fresh directory in:

```text
~/Library/Application Support/Halo CE Universal/Game Data/<import-id>/maps/
```

Header checks require a supported Xbox release, including `ui.map` and `a10.map`.
PC/Custom Edition/MCC maps and mixed releases are rejected. This checks the
format, not completeness of every level: use a complete set from one disc.
Failed imports preserve the previous selection and data. Successful imports
retain earlier imports rather than deleting the person's files.

`macos-settings.json` in the existing Application Support directory records the
data/source-image paths and fullscreen preference. Saves, profiles, cache and
`config.toml` stay in their established locations outside the signed app.
Settings, file-picker sheets and disc imports return control to SDL while the
game is running, so the simulation and networking continue. First-launch data
selection can wait before the engine starts. Data changes apply on the next launch.
Advanced Settings opens `config.toml` in TextEdit; restart to apply control edits.

Existing `HALO_DATA_ROOT`, `HALO_SAVE_ROOT` and `HALO_WINDOWED` development
overrides remain available. Passing an explicit guest image bypasses the native
chooser and preserves the command-line test runner behavior.

## Sparkle configuration

Sparkle 2.10.0 is pinned by checksum in `port/macos/dependencies.json`. It starts
only with a valid HTTPS feed and 32-byte public Ed25519 key. Standard Sparkle
UI handles update consent and downloads. Scheduled reminders wait in the menu
while playing; installations requiring a relaunch wait for clean game exit.
Local builds omit the feed and disable update controls.

Hosting is intentionally unconfigured. The non-secret checked-in file
`port/macos/release-config.json` currently has null values for:

| Field | Purpose |
| --- | --- |
| `feed_url` | Public HTTPS appcast XML |
| `public_update_key` | Halo's public Sparkle Ed25519 key |
| `download_base_url` | Public HTTPS base for versioned DMGs |
| `s3_bucket` | S3 or Cloudflare R2 bucket |
| `s3_endpoint_url` | S3-compatible HTTPS API endpoint, if needed |
| `s3_profile` | Existing AWS CLI profile name, if needed |

The S3-compatible publisher requires the feed beneath the download base.
Another service can host the same DMG/XML over public HTTPS. No new application
environment variables or committed credentials are needed.

After choosing hosting and reviewing distribution rights, create Halo's separate
Sparkle key in the login Keychain:

```sh
python3 tools/macos_release.py setup-updates
```

Commit only its public key. Keep the private key in Keychain and back it up via
the established 1Password workflow. Use the 1Password MCP server when preparing
developer environments. Signing/notary use existing Keychain identities and
profiles; storage uses an existing AWS profile. No keys or cloud resources have
been created for this task.

From a clean, committed tree, prepare a release with an explicit identity:

```sh
python3 tools/macos_release.py build --version 0.3.0 --build-number 8 \
  --sign-identity 'Developer ID Application: YOUR NAME (TEAMID)' \
  --notary-profile YOUR_EXISTING_KEYCHAIN_PROFILE
```

The tool rebuilds a fresh app, signs nested helpers/libraries and the app with
hardened runtime, audits resources, notarizes/staples the app, creates an
Applications-link DMG, notarizes/staples it, and Sparkle-signs it. The custom
guest loader needs unsigned executable-memory permission, declared in
`port/macos/host.entitlements`. Developer ID launch/notarization remain untested
until a real release is prepared.

The app and feed report the minimum OS required by their bundled Mach-O code.
The current Homebrew SDL3 requires macOS 26.0; this build is Apple Silicon.
Older targets need a compatible SDL3 build selected with the existing
`HALO_MACOS_SDL_PREFIX` option, followed by validation on those Macs.

The audit rejects disc images/maps, XBE/debug/SDK inputs, private signing inputs,
external symlinks and unexpected resources. It establishes a packaging boundary,
not redistribution rights for compiled code or artwork. Public dependency
licenses are included. This product includes software developed by in
<in@fishtank.com>.

For an approved release and configured hosting:

```sh
python3 tools/macos_release.py publish build/macos/releases/8
```

The publisher re-verifies checksum, certificate signature, stapled ticket and
Sparkle signature, uploads an immutable versioned DMG, reads the public download
back and checks its hash, then updates the feed last and verifies the live XML.
`release.json` records source revision, signatures, hashes, URLs and notarization
submissions. Nothing has been published for this task.

## Apple signing risk

Developer ID distribution still carries contractual third-party IP requirements.
Notarization checks security; it is not App Review or legal clearance. Omitting
maps/discs/SDK helps but does not settle the reconstructed engine or Halo/Master
Chief branding rights. The project's license cannot grant third-party rights.

Apple reserves certificate revocation. Its guidance says every app signed with
a revoked Developer ID certificate can stop installing or launching. Reusing
TrackTimer's certificate therefore couples the projects. A separate certificate
reduces certificate-level coupling, but does not guarantee isolation from
developer-team/account enforcement. Resolve engine and branding rights before
public signing.

- [Apple Developer Program agreement](https://developer.apple.com/support/terms/apple-developer-program-license-agreement/)
- [Apple Developer ID guidance](https://developer.apple.com/help/account/certificates/create-developer-id-certificates/)
- [Apple notarization documentation](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution)
- [Sparkle documentation](https://sparkle-project.org/documentation/)

## Validation

```sh
python3 tools/test_macos_menu.py
python3 tools/test_macos_menu.py --check-ui
HALO_MACOS_LLVM_BIN=/opt/homebrew/opt/llvm@22/bin python3 tools/test_macos_runtime.py
```

Menu tests use authored synthetic XDVDFS/map headers. No copyrighted test data
is checked in. `port/macos/tests/menu_ui.m` exercises the real settings/menu and
SDL window bridge in a separate test app without running a game.
