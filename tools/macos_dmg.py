"""Create and audit the drag-to-Applications Finder layout without UI scripting."""
from pathlib import Path
import hashlib
import os
import stat
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
WINDOW_SIZE = (680, 440)
ICON_POSITIONS = {"Halo OG.app": (160, 220), "Applications": (520, 220)}


def bundle_manifest(app):
    """Record every bundle file, directory mode and internal symlink target."""
    app = Path(app)
    result = {}
    for path in sorted(app.rglob("*")):
        name = path.relative_to(app).as_posix()
        if path.is_symlink():
            result[name] = {"symlink": os.readlink(path)}
        elif path.is_dir():
            result[name] = {"directory_mode": stat.S_IMODE(path.stat().st_mode)}
        elif path.is_file():
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            result[name] = {"mode": stat.S_IMODE(path.stat().st_mode), "sha256": digest}
        else:
            raise RuntimeError("Unexpected bundle entry: " + name)
    return result


def create_dmg(app, destination):
    app, destination = Path(app).resolve(), Path(destination).resolve()
    if destination.exists():
        raise RuntimeError("Disk image output already exists; choose a new filename")
    if app.name != "Halo OG.app" or not app.is_dir():
        raise RuntimeError("Package an existing Halo OG.app bundle")
    try:
        import dmgbuild
    except ImportError as error:
        raise RuntimeError("Install the build dependencies: python3 -m pip install -r tools/macos-dmg-requirements.txt") from error
    destination.parent.mkdir(parents=True, exist_ok=True)
    original = bundle_manifest(app)

    def verify_copy(mount, settings):
        copied = Path(mount) / app.name
        if bundle_manifest(copied) != original:
            raise RuntimeError("The installer app differs from its source bundle")
        subprocess.run(["codesign", "--verify", "--deep", "--strict", str(copied)], check=True)

    # dmgbuild converts with overwrite enabled. Keep that inside a private
    # directory, then expose the complete output with an exclusive hard link.
    with tempfile.TemporaryDirectory(prefix=".halo-og-installer-", dir=destination.parent) as temporary:
        layout = Path(temporary)
        for scale, name in ((1, "background.png"), (2, "background@2x.png")):
            subprocess.run([
                "swift", "-module-cache-path", str(ROOT / "build/macos/installer-module-cache"),
                str(ROOT / "port/macos/installer/render_background.swift"),
                str(ROOT / "port/macos/installer/background.svg"),
                str(layout / name), str(scale),
            ], cwd=ROOT, check=True)
        image = layout / "installer.dmg"
        dmgbuild.build_dmg(str(image), "Halo OG", settings={
            "format": "UDZO", "filesystem": "HFS+",
            "files": [str(app)], "symlinks": {"Applications": "/Applications"},
            "background": str(layout / "background.png"),
            "window_rect": ((100, 100), WINDOW_SIZE),
            "default_view": "icon-view", "icon_locations": ICON_POSITIONS,
            "icon_size": 96, "text_size": 14, "label_pos": "bottom",
            "arrange_by": "none", "show_icon_preview": False,
            "show_status_bar": False, "show_tab_view": False,
            "show_toolbar": False, "show_pathbar": False, "show_sidebar": False,
            # Setting a bundle's FinderInfo to hide .app breaks strict signing.
            # Finder uses the bundle display name without modifying the app.
            "create_hook": verify_copy,
        })
        os.link(image, destination)


def audit_dmg_layout(volume):
    """Validate the mounted image's actual Finder metadata and install target."""
    from ds_store import DSStore
    volume = Path(volume)
    if not (volume / "Halo OG.app").is_dir():
        raise RuntimeError("Installer app is missing")
    shortcut = volume / "Applications"
    if not shortcut.is_symlink() or os.readlink(shortcut) != "/Applications":
        raise RuntimeError("Installer shortcut must point to /Applications")
    background = volume / ".background.tiff"
    if not background.is_file() or background.stat().st_size == 0:
        raise RuntimeError("Installer Retina background is missing")
    with DSStore.open(str(volume / ".DS_Store"), "r") as store:
        records = {(entry.filename, entry.code): entry.value for entry in store}
    for name, position in ICON_POSITIONS.items():
        if tuple(records.get((name, b"Iloc"), ()))[:2] != position:
            raise RuntimeError("Incorrect installer icon position: " + name)
    window = records.get((".", b"bwsp"), {})
    if window.get("WindowBounds") != "{{100, 100}, {680, 440}}" or any(
            window.get(key) for key in ("ShowToolbar", "ShowSidebar", "ShowStatusBar", "ShowPathbar")):
        raise RuntimeError("Incorrect installer window layout")
    view = records.get((".", b"icvp"), {})
    if (view.get("iconSize") != 96 or view.get("textSize") != 14
            or view.get("backgroundType") != 2 or not view.get("backgroundImageAlias")
            or records.get((".", b"icvl")) != b"icnv"):
        raise RuntimeError("Incorrect installer background or icon view")
    print("Verified Finder installer: Retina background, positioned icons, Applications shortcut")
    return True
