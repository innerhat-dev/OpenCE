# Building Halo OG

Players can use the [testing packages](../README.md#download) without developer
tools. Native ports use the checked-in [Xbox SDK declarations](../port/include/xdk/README.md);
the private Xbox SDK and original executable are not needed to compile them.
Supply your own original Xbox game data to play. Maps, disc images, signing
identities, provisioning profiles, and built apps are excluded from Git.

```sh
git clone https://github.com/pfista/halo-og.git
cd halo-og
```

## Choose a platform

| Platform | Build instructions |
| --- | --- |
| Apple Silicon Mac | [Apple dependencies](apple-build.md), then [Mac build](../port/macos/README.md#build): `python3 tools/macos_build.py` |
| iPhone development | [Apple dependencies](apple-build.md) and [Xcode/device signing](../port/ios/README.md#build); use your own Apple team and app identifier |
| Windows | [Windows tools/build](../port/windows/README.md#requirements); build on Windows |
| Linux | [Linux tools/build](../port/linux/README.md#requirements) |
| Android | [Android tools/APK](../port/android/README.md#requirements) |

For Windows/Linux, install Python, Ninja, and the platform's compiler/runtime
dependencies, then configure and select the target:

```sh
python configure.py --release --portable
ninja windows   # on Windows
# or: ninja linux
```

Android uses `python configure.py`, then `ninja android_apk` with its documented
toolchain. Without an explicit target, Ninja builds the default configured
platform. `tools/ci_build.py` follows the CI platform build; for example,
`python tools/ci_build.py linux release`.

The Mac renderer uses ANGLE's Metal backend. Apple guest compilation has its
own pinned toolchain; follow [Apple setup](apple-build.md).

## Build options

Pass these to `configure.py` for the generic native builds:

| Option | Purpose |
| --- | --- |
| No release flag | Debug build; failed assertions stop the game. |
| `--release` | Release build without assertion checks. |
| `--portable` | Avoid host-specific CPU instructions in Windows/Linux packages. Use for distribution. |
| `--lto=thin`, `--lto=off` | Reduce link-time optimization and link time. |
| `--pgo=off` | Disable profile-guided optimization. |
| `--pgo=train` | Record an optimization profile with game data installed. |

Without `--portable`, Windows/Linux builds use the build machine's instructions
(`-march=native`) and may fail on another computer. Apple scripts have their
own options; use `python3 tools/macos_build.py --help` and the Mac guide.

## Optimization profiles

The generic builds use `pgo/halo_linux.profdata` for Linux/Android and
`pgo/halo_windows.profdata` for Windows. These profiles need clang 22 or later;
an older clang does not use them.

To record a replacement profile, preserve any current profile you need, remove
the target profile, run `python configure.py --pgo=train`, then `ninja linux`
or `ninja windows`. With original game data under `assets/`, training visits
the main menu and the opening minute of each campaign level for about fifteen
minutes. This measures optimization workloads; it does not certify fidelity.

## Validation and contribution

Follow [AGENTS.md](../AGENTS.md) and the [Xbox fidelity policy](xbox-fidelity.md).
Keep original presentation/rules as the baseline, preserve the 30 Hz simulation,
and review upstream changes individually. Matching the original build-2342 Xbox
executable is distinct from validating a native ARM/x86 port.

[Community maps](community-maps.md) documents rebuilding source tags into Xbox
v5 NTSC caches. [Release/data instructions](macos-menu-and-releases.md) cover
asset-free packaging and opt-in managed downloads. Cross-platform gameplay,
physical controllers, campaign coverage, and reference-Xbox comparisons need
explicit runtime evidence beyond successful compilation.
