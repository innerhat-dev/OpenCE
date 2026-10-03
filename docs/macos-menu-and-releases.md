# Halo OG Mac menu, local data and releases

The native AppKit menu runs in the game's process. Its monochrome helmet opens
Settings, changes fullscreen immediately, selects game data, opens saves and
controls, checks updates, and quits through the normal game exit path. Settings
is also available with Command-comma; Control-Command-F toggles fullscreen.
Release the captured mouse with F12 to reach the menu bar. The existing Dock
icon is retained; `port/macos/Helmet.svg` generates a vector template PDF.

## GitHub Actions DMG

The [macOS DMG workflow](https://github.com/pfista/halo-og/actions/workflows/macos-dmg.yml)
builds an Apple Silicon app on code pushes to `main` and manual runs. Sign in to
GitHub, choose a successful run, and download **halo-macos-arm64-dmg** under
**Artifacts**. Artifacts are retained for 14 days and contain:

- `Halo-OG-macos-arm64.dmg`, with `Halo OG.app` and an Applications shortcut.
- `README.txt`, with the build's minimum macOS version and installation steps.
- `BuildInfo.txt`, identifying the source revision and compiled guest hash.
- `SHA256SUMS`, for verifying the DMG after extracting the artifact ZIP.

The current bundled dependencies require macOS 26 or later on Apple Silicon.
Use the minimum macOS version recorded in the artifact's `README.txt` for that
build.
No build tools are needed to run the download. Open the DMG, drag the app into
Applications as **Halo OG.app**, and supply your own original Xbox game data on first launch.
These are ad hoc signed, unnotarized builds; see
[Mac installation](../port/macos/README.md#download) for the first-launch steps.

CI uses public dependencies and the checked-in SDK declarations. It audits the
app to exclude game data, private inputs and local checkout paths, verifies its
signature, and packages the DMG. The artifact does not configure Sparkle updates
or use a Developer ID signing identity. The notarized release process below
remains separate.

CI explicitly uses `--sign-identity -` and imports no developer certificates or
Keychain credentials. Before upload, every bundled Mach-O architecture must have
an ad hoc signature with no certificate authority or team identifier. The app
uses the generic `local.halo.ce-universal` bundle identifier. Third-party helper
identifiers and capability entitlements remain those of the pinned dependency.
The app's displayed name is **Halo OG** and its bundle identifier remains stable.
The canonical data directory is `~/Library/Application Support/Halo OG/`.
Prior files are copied from `~/Library/Application Support/Halo CE Universal/`
without deleting the original files or replacing files already in the new directory.
Existing Halo OG settings take precedence. Copied settings point to copied managed
data when that selection is complete; a conflicting selection continues using
its intact legacy path. External game folders remain selected in place.
If migration cannot complete, the app reports the error and stops launch so it
can retry safely next time.

## Manual testing prerelease

The fork's **Publish testing prerelease** workflow runs only when explicitly
dispatched on `main` with a new `test-...` tag, for example
`test-v0.3.0-net11`. It publishes the latest `main` commit using existing,
successful **Build** and **macOS DMG** workflow outputs from that exact commit.
It does not rebuild, sign with a personal identity, or include game data.

After these changes are committed and pushed, wait for both build workflows to
succeed. In GitHub Actions, choose **Publish testing prerelease → Run workflow**,
select `main`, and enter an unused testing tag. This explicit dispatch publishes
a prerelease; code pushes do not publish. Prepare/collection uses a read-only
token; the separate publication job alone receives `contents: write`.

The helper rejects another source revision, non-main runs, unsuccessful runs,
missing/expired artifacts, changed hashes, unexpected Mac contents, and reused
tags/releases. Before publication it rechecks latest main and build provenance.
If main advances while publication is queued, dispatch again after the new
commit's builds finish. Workflow artifacts must still exist: Mac artifacts last
14 days and other platform artifacts last 3 days. Manually rerun both build
workflows on latest main if needed.

The prerelease includes:

- `Halo-OG-macos-arm64.dmg`, `macos-README.txt` and `macos-BuildInfo.txt`.
- `halo-windows-release.zip`, `halo-linux-release.zip` and `halo-android-release.zip`.
- `SHA256SUMS` and `provenance.json` with source SHA, network protocol, CI run IDs,
  artifact IDs and SHA-256 hashes. Debug builds are omitted.

For a tag such as `test-v0.3.0-net11`, the direct Mac download is:

```text
https://github.com/pfista/halo-og/releases/download/test-v0.3.0-net11/Halo-OG-macos-arm64.dmg
```

The URL becomes usable only after that tag is published. Public release assets
require no GitHub sign-in and are retained until the release is deleted.
Prereleases cannot be GitHub's “Latest” release, so share the tagged URL instead
of `releases/latest/download`. Tags and assets are not overwritten. A failed
publication can leave a new tag or incomplete release; inspect that state and
use a fresh tag for a retry instead of overwriting it.

Testers should use the same tag across platforms. Current source uses protocol
**11**, which cannot join protocol 10 sessions; metadata extracts the actual
protocol from the selected source instead of assuming it from the tag name.
The DMG is Apple Silicon/macOS 26+, ad-hoc signed and unnotarized. Windows builds
are portable x86 executables; Linux builds still need the documented 32-bit
OpenGL/SDL/audio runtime dependencies. Android signing depends on the existing
CI signing configuration. Build success does not establish cross-platform play.
Fork CI builds disable the updater that otherwise targets cybersecurity's
different build; Sparkle also remains disabled in these Mac CI builds.

Read-only local preparation and verification are available without publication:

```sh
python3 tools/testing_release.py prepare --sha FULL_LATEST_MAIN_SHA \
  --tag test-v0.3.0-net11 --directory /tmp/halo-testing-candidate
python3 tools/testing_release.py verify --sha FULL_LATEST_MAIN_SHA \
  --tag test-v0.3.0-net11 --directory /tmp/halo-testing-candidate
```

Use Python 3.11 or later, a fresh directory and the authenticated GitHub CLI. `prepare` downloads the
existing artifacts and writes a candidate; only the explicit `publish` command
creates a tag/release. The workflow uses that command in its publication job.

GitHub documents [artifact download access](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/download-workflow-artifacts),
[artifact metadata and download](https://docs.github.com/en/rest/actions/artifacts),
[workflow source/run filters](https://docs.github.com/en/rest/actions/workflow-runs),
and [prerelease/latest behavior](https://docs.github.com/en/rest/releases/releases).

## Independently supplied data

After the initial game build and public dependency setup, build without a local
checkout path:

```sh
python3 tools/macos_build.py --host-only --no-data-path
python3 -m venv build/macos/dmg-packaging-venv
build/macos/dmg-packaging-venv/bin/python -m pip install -r tools/macos-dmg-requirements.txt
build/macos/dmg-packaging-venv/bin/python tools/macos_release.py local-dmg
```

The resulting `build/macos/Halo-OG-0.3.0-local.dmg` is a local test artifact. It has
no notarization ticket and is not a verified public release. It includes an
Applications shortcut and the app, without maps, ISOs or a local checkout path.
The Finder window has a Retina background, positioned app/folder icons and a
drag arrow. Rendering uses macOS's native SVG support; the Python dependencies
write Finder metadata without scripting Finder and are only used at build time.

To repackage an existing signed app, pass `--app "/path/to/Halo OG.app"` and a
fresh `--output` filename to `local-dmg`. Packaging checks every bundle file,
directory permission and symlink target against the source and verifies the
copied signature. It preserves the app's build information and does not rebuild
the game or change user data. Existing output files are never replaced.

`test-v0.3.0-net11-dmg2` is an installer revision of `test-v0.3.0-net11`.
Its Mac app and other platform ZIPs are identical to that release's
`41c4aa82` game build; these releases can play together. `provenance.json`
records the installer tooling commit separately from the binary source and
original CI artifacts. The original release and its checksums remain available.

The end user needs no Homebrew, XDK or build tools. SDL3, ANGLE, Sparkle and the
compiled engine are bundled. First launch accepts the user's locally obtained
original Xbox Halo XISO/ISO, or extracted game folder (its `maps` subfolder also
works). Nothing is downloaded or uploaded by this selection. Disc imports copy
maps to a fresh directory in:

```text
~/Library/Application Support/Halo OG/Game Data/<import-id>/maps/
```

Header checks require a supported Xbox release, including `ui.map` and `a10.map`.
PC/Custom Edition/MCC maps and mixed releases are rejected. This checks the
format, not completeness of every level: use a complete set from one disc.
Failed imports preserve the previous selection and data. Successful imports
retain earlier imports rather than deleting the person's files.

Extracted-folder selection offers **Copy and Manage**, **Use This Folder**, or
**Cancel**. Managed copies use the same Application Support layout and preserve
the original files. Community downloads have separate opt-in controls and a
verified library under `Community Maps/maps/`; user-supplied files take priority.
See [managed storage and map downloads](map-downloads-plan.md) for the catalog,
missing-map readiness flow and hosting configuration. The selected publisher
is `https://dl.oghalo.com`; downloads default off until the player opts in.

`macos-settings.json` in the Halo OG Application Support directory records the
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
Use the packaging virtual environment prepared above so the Finder metadata
dependencies are available.

```sh
build/macos/dmg-packaging-venv/bin/python tools/macos_release.py build --version 0.3.0 --build-number 8 \
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
