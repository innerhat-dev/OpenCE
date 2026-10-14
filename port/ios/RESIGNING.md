# Install the unsigned IPA with your own Apple account

Use an Apple Silicon Mac with Xcode 26+ and Python 3. This runtime requires
iOS/iPadOS 26+. Build 17 and newer choose their guest arena dynamically and
do not request Extended Virtual Addressing or Increased Memory Limit. Start with a device IPA
provided by the builder, or build one using [the iOS build instructions](README.md)
and `tools/ios_package.py`. Download the unsigned device IPA and re-signing kit from the
[PR #1 testing release](https://github.com/AttilaTheFun/halo-ce-universal/releases/tag/apple-ios-pr1-20261014-v29). The release is built from
`apple/ios-installer`, not the private branding branch. GitHub Actions does not
yet publish an unsigned IPA automatically. A simulator app cannot run on an iPhone.

The script signs locally using a certificate/private key already in your
Keychain and a provisioning profile issued for your account. It does not
sign in to Apple, create certificates, register devices, or bypass provisioning.
You do not need to send your device ID to this project's maintainer when
you use your own account.

## Set up signing once

1. Add your Apple account in **Xcode → Settings → Accounts**. Connect your
   iPhone, trust the Mac, and enable Developer Mode if requested.
2. If you do not already have a suitable iOS development profile, create a
   temporary iOS App project in Xcode. Select your team, enable automatic
   signing, and set a unique bundle identifier such as `com.yourname.haloce`.
   Build/run that temporary app on your phone so Xcode creates the identity
   and a profile covering the device. Then delete the temporary app from
   the phone before installing Halo with the same identifier.
3. Locate the temporary app's build product using **Products → Show in
   Finder**, then **Show Package Contents**. Copy its
   `embedded.mobileprovision` somewhere convenient. Alternatively, use an
   existing development or Ad Hoc `.mobileprovision` downloaded from Apple.
4. List available identities:

   ```sh
   security find-identity -v -p codesigning
   ```

   Use the matching **Apple Development** identity (or **Apple Distribution**
   identity for an Ad Hoc profile). Its private key must be in your Keychain,
   and its certificate must be included in the profile. An App Store profile
   cannot install this build directly on a phone.

## Sign and install

Extract `OpenCE-iOS-resigning-kit.zip` and run the command below from its
folder. Alternatively, check out `apple/ios-installer` from
`AttilaTheFun/halo-ce-universal` and run it from the repository root:

```sh
./tools/ios_resign.sh ~/Downloads/OpenCE-iOS-PR1-unsigned.ipa \
  --identity 'Apple Development: Your Name (IDENTITY_ID)' \
  --profile ~/Downloads/embedded.mobileprovision \
  --bundle-id com.yourname.haloce \
  --device YOUR_DEVICE_UDID \
  --output ~/Downloads/Halo-signed.ipa
```

The exact identity name or its SHA-1 fingerprint is accepted. `--device`
is optional but recommended: it verifies that the supplied UDID is covered.
Use `xcrun devicectl list devices` or Xcode's Devices and Simulators window
to identify your phone. The output must not already exist.

The script checks profile expiry, platform, bundle ID, device and signing
certificate; updates the bundle ID; signs ANGLE/SDL frameworks and the app
inside-out; generates DER entitlements; verifies signatures; and writes a
new IPA plus a SHA-256 checksum. It never changes the downloaded IPA.
The shell entry point uses the adjacent `ios_resign.py`, so keep both files.

Install `Halo-signed.ipa` with Apple Configurator, or extract and install
the app with Xcode's command-line device tools:

```sh
mkdir -p ~/Downloads/Halo-signed-extracted
ditto -x -k ~/Downloads/Halo-signed.ipa ~/Downloads/Halo-signed-extracted
xcrun devicectl device install app --device YOUR_DEVICE_UDID \
  ~/Downloads/Halo-signed-extracted/Payload/Halo.app
xcrun devicectl device process launch --device YOUR_DEVICE_UDID com.yourname.haloce
```

On first launch, choose your own supported original Xbox Halo ISO/XISO.
No game image or maps are included in the IPA. Keep the same account and
bundle ID for updates to retain imported data. Renew the provisioning
profile and re-sign before it expires; a free Personal Team's validity and
device limits differ from paid developer membership. Back up saves before
uninstalling. Do not upload your signed IPA/profile or private key to this
repository; they contain your signing/device information.

## AltStore / similar sideloaders

Build 17 and newer no longer require a special memory entitlement. Free-account
AltStore/SideStore and LiveContainer installation still need testing; removing
this requirement is not proof of compatibility with every signing service.
The tested signing workflow uses a locally held Apple development identity.

The unsigned IPA has no embedded profile or code signature. The kit's
`Required-entitlements.plist` is empty for build 17 onward. Older IPAs (up to
build 16) still require Extended Virtual Addressing: a new signing kit cannot
change their compiled memory layout. The script checks IPA metadata and retains
the requirement for those older builds. This is not an AltStore PAL listing.

## LiveContainer and memory reservation errors

Builds up to 16 reserved a fixed arena at 448 GiB and required Extended Virtual
Addressing. An iPhone 17 Pro Max / iOS 26.0 LiveContainer report failed there.
[LiveContainer does not apply guest entitlements to its host](https://github.com/LiveContainer/LiveContainer#limitations).

Build 17 replaces that fixed address with an OS-selected, 4-GiB-aligned region.
Compiler pointer translation, GL arguments, import stubs and host services all
use its runtime address. Executable code remains in the signed app image; no
JIT or writable executable memory is introduced. See the
[memory-layout validation record](../../docs/apple-ios-dynamic-arena.md).

A sufficiently large aligned region must still be available in the process.
If reservation fails inside LiveContainer, try a fresh launch or standalone
installation and share `Documents/save/halo.log` (not signing credentials).
The preflight runs before ISO import; its scrollable error screen provides
**Copy details** and **Close**. Existing imports and saves are preserved.

## Build it yourself

```sh
git clone --branch apple/ios-installer https://github.com/AttilaTheFun/halo-ce-universal.git
cd halo-ce-universal
```

Follow [the build instructions](README.md#build), supplying your own team and
unique bundle ID. No special memory capability is required by the current source.

The public IPA is checked by re-signing it locally and verifying the nested
framework and app signatures. This does not establish
compatibility with every device or signing service.

Apple references: [signing setup](https://developer.apple.com/documentation/xcode/running-your-app-on-simulated-or-physical-devices),
[provisioning profiles](https://developer.apple.com/documentation/technotes/tn3125-inside-code-signing-provisioning-profiles),
and [nested signatures and DER entitlements](https://developer.apple.com/documentation/xcode/using-the-latest-code-signature-format).
