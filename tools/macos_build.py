#!/usr/bin/env python3
"""Build the native Apple Silicon host, rebased game, and local .app bundle."""
import argparse
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import plistlib
import shlex
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.linux_build import MINIUPNPC_DEFINES, MINIUPNPC_DIR, miniupnpc_sources
BUILD = ROOT / "build/macos"
LLVM = Path(os.environ.get("HALO_MACOS_LLVM_BIN", "/opt/homebrew/opt/llvm/bin"))
SDL = Path(os.environ.get("HALO_MACOS_SDL_PREFIX", "/opt/homebrew/opt/sdl3"))
ANGLE = Path(os.environ.get("HALO_MACOS_ANGLE_DIR", str(BUILD / "angle/dist")))
GL = BUILD / "toolchain/gl"
APP_ICON = "AppIcon.icns"
APP_VERSION = "0.3.0"
APP_BUILD = "6"


def run(*args):
    subprocess.run([str(arg) for arg in args], cwd=ROOT, check=True)


def require(path):
    if not path.exists():
        raise RuntimeError(f"Missing build dependency: {path}. See port/macos/README.md.")
    return path


def build_plugin():
    BUILD.mkdir(parents=True, exist_ok=True)
    require(LLVM / "llvm-config")
    flags = shlex.split(subprocess.check_output(
        [LLVM / "llvm-config", "--cxxflags", "--ldflags", "--libs", "core", "passes"], text=True))
    run(LLVM / "clang++", "-shared", "-fPIC", "port/macos/compiler/guest_rebase.cpp",
        "-o", BUILD / "guest_rebase.dylib", *flags)


def build_host():
    obj_dir = BUILD / "host-obj"
    obj_dir.mkdir(parents=True, exist_ok=True)
    frameworks = [ANGLE / f"{name}.xcframework/macos-arm64" for name in ("EGL", "GLESv2")]
    for name, directory in zip(("libEGL", "libGLESv2"), frameworks):
        require(directory / f"{name}.framework" / name)
    # EGL's loader also uses this name beside the EGL binary.
    companion = frameworks[0] / "libEGL.framework/libGLESv2.dylib"
    if companion.is_symlink():
        companion.unlink()
    if not companion.exists():
        companion.symlink_to(frameworks[1] / "libGLESv2.framework/libGLESv2")
    flags = ["-arch", "arm64", "-O2", "-g", "-DHALO_MACOS=1", "-D_DARWIN_C_SOURCE",
             "-Wall", "-Wextra", "-Wno-unused-function", "-Wno-unused-parameter",
             "-I.", "-Iport/macos/host", "-Iport/android/include", "-Iport/linux/src",
             f"-I{SDL / 'include'}", f"-I{GL}",
             f"-I{MINIUPNPC_DIR / 'include'}", f"-I{MINIUPNPC_DIR / 'src'}", *MINIUPNPC_DEFINES]
    sources = sorted((ROOT / "port/macos/host").glob("*.c"))
    sources += miniupnpc_sources()
    sources += [BUILD / "host/host_import_table.c", ROOT / "port/macos/host/entry.s"]
    objects = []
    for source in sources:
        obj = obj_dir / (source.name + ".o")
        run("clang", *flags, "-c", source, "-o", obj)
        objects.append(obj)
    run("clang", *objects, f"-L{SDL / 'lib'}", "-lSDL3",
        *(f"-F{directory}" for directory in frameworks),
        "-framework", "libEGL", "-framework", "libGLESv2",
        *(f"-Wl,-rpath,{directory}" for directory in frameworks), "-o", BUILD / "halo")


def package_icon(resources):
    source = require(ROOT / "port/ios/Assets.xcassets/AppIcon.appiconset/AppIcon.png")
    with tempfile.TemporaryDirectory(prefix="halo-macos-icon-") as temporary:
        iconset = Path(temporary) / "AppIcon.iconset"
        iconset.mkdir()
        for size in (16, 32, 128, 256, 512):
            for scale in (1, 2):
                pixels = size * scale
                suffix = "@2x" if scale == 2 else ""
                target = iconset / f"icon_{size}x{size}{suffix}.png"
                subprocess.run(["/usr/bin/sips", "-z", str(pixels), str(pixels),
                                str(source), "--out", str(target)],
                               check=True, stdout=subprocess.DEVNULL)
        run("/usr/bin/iconutil", "--convert", "icns", "--output",
            resources / APP_ICON, iconset)


def package(data_root):
    app = BUILD / "Halo CE Universal.app"
    contents = app / "Contents"
    macos = contents / "MacOS"
    frameworks = contents / "Frameworks"
    resources = contents / "Resources"
    for directory in (macos, frameworks, resources):
        directory.mkdir(parents=True, exist_ok=True)
    executable = macos / "halo"
    # Keep a running copy's executable inode intact during a local rebuild.
    if executable.exists():
        executable.unlink()
    shutil.copy2(BUILD / "halo", executable)
    shutil.copy2(BUILD / "halo_guest.elf", resources / "halo_guest.elf")
    sdl = frameworks / "libSDL3.0.dylib"
    if sdl.exists():
        sdl.unlink()
    shutil.copy2(require(SDL / "lib/libSDL3.0.dylib"), sdl)
    run("install_name_tool", "-change", str(SDL / "lib/libSDL3.0.dylib"),
        "@rpath/libSDL3.0.dylib", executable)
    run("install_name_tool", "-id", "@rpath/libSDL3.0.dylib", sdl)
    for name in ("EGL", "GLESv2"):
        directory = ANGLE / f"{name}.xcframework/macos-arm64"
        source = directory / f"lib{name}.framework"
        old_framework = frameworks / source.name
        if old_framework.exists():
            shutil.rmtree(old_framework)
        target = frameworks / f"lib{name}.dylib"
        if target.exists():
            target.unlink()
        shutil.copy2(source / f"lib{name}", target)
        target.chmod(0o755)
        run("install_name_tool", "-change", f"@rpath/lib{name}.framework/lib{name}",
            f"@rpath/lib{name}.dylib", executable)
        run("install_name_tool", "-id", f"@rpath/lib{name}.dylib", target)
        run("install_name_tool", "-delete_rpath", str(directory), executable)
    run("install_name_tool", "-add_rpath", "@executable_path/../Frameworks", executable)
    # Store the independently supplied data location as a configuration file;
    # external symlinks would invalidate a strictly signed app bundle.
    data_link = resources / "GameData"
    if data_link.is_symlink():
        data_link.unlink()
    (resources / "GameDataPath.txt").write_text(str(require(data_root.resolve())) + "\n")
    package_icon(resources)
    info = {
        "CFBundleExecutable": "halo", "CFBundleIdentifier": "local.halo.ce-universal",
        "CFBundleName": "Halo CE Universal", "CFBundleDisplayName": "Halo CE Universal",
        "CFBundleIconFile": APP_ICON,
        "CFBundlePackageType": "APPL", "CFBundleShortVersionString": APP_VERSION,
        "CFBundleVersion": APP_BUILD, "LSMinimumSystemVersion": "14.0",
        "CFBundleURLTypes": [{"CFBundleURLName": "Halo multiplayer invite",
                              # Match the shared discord.application_id default.
                              "CFBundleURLSchemes": ["halo", "discord-1553978809840050229"],
                              "CFBundleTypeRole": "Viewer"}],
        "NSLocalNetworkUsageDescription": "Connect to players hosting Halo multiplayer games.",
        "NSHighResolutionCapable": True,
        "NSHumanReadableCopyright": "Local experimental Apple Silicon port",
    }
    with (contents / "Info.plist").open("wb") as stream:
        plistlib.dump(info, stream)
    try:
        revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                           text=True, stderr=subprocess.DEVNULL).strip()
        if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip():
            revision += " (local changes)"
    except (OSError, subprocess.CalledProcessError):
        revision = "unknown"
    guest_hash = hashlib.sha256((resources / "halo_guest.elf").read_bytes()).hexdigest()
    (resources / "BuildInfo.txt").write_text(
        f"Halo CE Universal {APP_VERSION} (build {APP_BUILD})\n"
        f"Source: {revision}\nGuest SHA-256: {guest_hash}\n")
    licenses = resources / "Licenses"
    licenses.mkdir(exist_ok=True)
    for source, name in (
        (ROOT / "LICENSE.md", "Project.txt"),
        (ROOT / "libs/d3d8/LICENSE.GPL-3.0", "D3D8-GPL-3.0.txt"),
        (ROOT / "port/macos/licenses/ANGLE.txt", "ANGLE.txt"),
        (SDL / "share/licenses/SDL3/LICENSE.txt", "SDL3.txt"),
        (ROOT / "build/android/third_party/musl-1.2.5/COPYRIGHT", "musl.txt"),
        (ROOT / "port/third_party/kcp/LICENSE", "KCP.txt"),
        (ROOT / "port/third_party/miniupnpc/LICENSE", "miniupnpc.txt"),
    ):
        if source.exists():
            shutil.copy2(source, licenses / name)
    # Local ad-hoc signing requires neither an account nor an entitlement.
    for binary in (sdl, frameworks / "libGLESv2.dylib", frameworks / "libEGL.dylib"):
        run("codesign", "--force", "--sign", "-", binary)
    run("codesign", "--force", "--sign", "-", app)
    run("codesign", "--verify", "--deep", "--strict", app)
    print(f"Built {app}")


def install_app(app, applications):
    """Stage and verify a complete app before replacing an installed copy."""
    app = require(app.resolve())
    applications = applications.expanduser().resolve()
    applications.mkdir(parents=True, exist_ok=True)
    destination = applications / app.name
    register = Path("/System/Library/Frameworks/CoreServices.framework/Frameworks/"
                    "LaunchServices.framework/Support/lsregister")

    def unregister(bundle):
        # An already-unregistered bundle returns an error. Archive it anyway;
        # the installed app's final registration below must succeed.
        subprocess.run([str(register), "-u", str(bundle)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)

    with tempfile.TemporaryDirectory(prefix=".halo-install-", dir=applications) as temporary:
        staged = Path(temporary) / app.name
        shutil.copytree(app, staged, symlinks=True)
        run("codesign", "--verify", "--deep", "--strict", staged)
        previous = None
        if destination.exists():
            with (destination / "Contents/Info.plist").open("rb") as stream:
                installed = plistlib.load(stream)
            if installed.get("CFBundleIdentifier") != "local.halo.ce-universal":
                raise RuntimeError(f"Another application already exists at {destination}")
            previous = Path(tempfile.mkdtemp(prefix=".halo-previous-", dir=applications))
            unregister(destination)
            destination.rename(previous / (app.name + ".backup"))
        try:
            staged.rename(destination)
        except OSError:
            if previous:
                (previous / (app.name + ".backup")).rename(destination)
                previous.rmdir()
                run(register, "-f", destination)
            raise
    # Older installers kept launchable apps in these folders. macOS follows
    # their file identities when the installed copy is renamed to a backup.
    for prior in applications.glob(".halo-previous-*/" + app.name):
        with (prior / "Contents/Info.plist").open("rb") as stream:
            info = plistlib.load(stream)
        if info.get("CFBundleIdentifier") == "local.halo.ce-universal":
            unregister(prior)
            prior.rename(prior.with_name(prior.name + ".backup"))
    # Spotlight can rediscover unregistered development bundles, and launching
    # by name can then choose one of them instead of the installed version.
    # Preserve generated copies outside its index with a non-app extension.
    development_apps = list(BUILD.rglob("Halo CE Universal.app"))
    backup_root = BUILD / "app-backups.noindex" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    for development_app in development_apps:
        if development_app.resolve() == destination:
            continue
        info_path = development_app / "Contents/Info.plist"
        if not info_path.is_file():
            continue
        with info_path.open("rb") as stream:
            info = plistlib.load(stream)
        if info.get("CFBundleIdentifier") != "local.halo.ce-universal":
            continue
        unregister(development_app)
        backup = backup_root / development_app.relative_to(BUILD)
        backup = backup.with_name(backup.name + ".backup")
        backup.parent.mkdir(parents=True, exist_ok=True)
        development_app.rename(backup)
    os.utime(destination, None)
    run(register, "-f", destination)
    run("mdimport", "-i", destination)
    print(f"Installed {destination}")
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plugin-only", action="store_true")
    parser.add_argument("--host-only", action="store_true")
    parser.add_argument("--data-root", type=Path, default=ROOT / "assets")
    parser.add_argument("--install", nargs="?", const=Path("/Applications"), type=Path,
                        metavar="DIRECTORY", help="Install in /Applications, or the given directory, for Spotlight")
    parser.add_argument("--jobs", type=int, default=min(os.cpu_count() or 4, 6))
    args = parser.parse_args()
    os.chdir(ROOT)
    if args.plugin_only:
        build_plugin()
        return
    if not args.host_only:
        llvm_bin = BUILD / "toolchain/bin"
        require(llvm_bin / "llvm-ar")
        require(llvm_bin / "ld.lld")
        require(GL / "GLES3/gl32.h")
        run(sys.executable, "configure.py", "--macos", "--android-guest-llvm-bin", llvm_bin,
            "--android-guest-gl-include", GL, "--pgo", "off")
        ninja = shutil.which("ninja") or str(BUILD / "toolchain/venv/bin/ninja")
        run(ninja, "-j", args.jobs, "macos_guest")
    build_host()
    package(args.data_root)
    if args.install:
        install_app(BUILD / "Halo CE Universal.app", args.install)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.CalledProcessError) as error:
        print(f"macOS build failed: {error}", file=sys.stderr)
        sys.exit(1)
