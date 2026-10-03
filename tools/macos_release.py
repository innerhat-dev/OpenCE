#!/usr/bin/env python3
"""Build/notarize an asset-free Mac DMG and publish through S3-compatible storage.

Hosting and the public update key are non-secret checked-in configuration.
Signing/notary secrets remain in the login Keychain; storage authentication uses
an existing AWS CLI profile. This tool never creates or reads an env file.
"""
import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import re
import subprocess
import sys
from urllib.parse import urlparse
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.macos_build import APP_NAME, APP_VERSION, update_configuration
from tools.macos_sparkle import setup_sparkle, DIRECTORY as SPARKLE
from tools.macos_dmg import create_dmg
from tools.macos_content_tools import audit_content_tools

CONFIG = ROOT / "port/macos/release-config.json"
APP = ROOT / "build/macos" / (APP_NAME + ".app")
ACCOUNT = "local.halo.ce-universal"
NAMESPACE = "http://www.andymatuschak.org/xml-namespaces/sparkle"
ET.register_namespace("sparkle", NAMESPACE)


def run(*command, capture=False):
    return subprocess.run([str(part) for part in command], cwd=ROOT, check=True, text=True,
                          stdout=subprocess.PIPE if capture else None).stdout


def config():
    return json.loads(CONFIG.read_text())


def https_url(value):
    url = urlparse(value or "")
    if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise RuntimeError("Release URLs must be public HTTPS URLs without credentials, queries or fragments")
    return value.rstrip("/")


def audit_bundle(app):
    """An explicit package boundary, not a license clearance for compiled code."""
    allowed = {"Info.plist", "MacOS", "Frameworks", "Resources", "_CodeSignature", "Helpers"}
    contents = app / "Contents"
    if {path.name for path in contents.iterdir()} - allowed:
        raise RuntimeError("Unexpected top-level content in the app")
    resources = contents / "Resources"
    if {path.name for path in resources.iterdir()} - {"AppIcon.icns", "Helmet.pdf", "halo_guest.elf", "BuildInfo.txt", "Licenses", "map-downloads.json", "ContentTools.json"}:
        raise RuntimeError("Release resources must contain only the compiled engine, icons, build record and licenses")
    helpers = contents / "Helpers"
    provenance = resources / "ContentTools.json"
    if helpers.exists() != provenance.exists():
        raise RuntimeError("Community package helpers require their bundled provenance record")
    if helpers.exists() and (helpers.is_symlink() or not helpers.is_dir() or
                            {path.name for path in helpers.iterdir()} != {"invader-extract", "invader-build"} or
                            any(path.is_symlink() or not path.is_file() for path in helpers.iterdir())):
        raise RuntimeError("Unexpected community package helper")
    if helpers.exists():
        audit_content_tools(app)
    if {path.name for path in (contents / "MacOS").iterdir()} != {"halo"}:
        raise RuntimeError("Release executables must contain only the native host")
    if {path.name for path in (contents / "Frameworks").iterdir()} != {"Sparkle.framework", "libSDL3.0.dylib", "libEGL.dylib", "libGLESv2.dylib"}:
        raise RuntimeError("Unexpected bundled runtime dependency")
    for path in app.rglob("*"):
        if path.suffix.lower() in {".iso", ".xiso", ".map", ".xbe", ".pdb", ".p12", ".mobileprovision"}:
            raise RuntimeError("Restricted or private input in app: " + str(path.relative_to(app)))
        if path.is_symlink() and not path.resolve().is_relative_to(app.resolve()):
            raise RuntimeError("External symlink in the signed app")
    return True


def audit_adhoc_signing(app):
    """Check all bundled code without exposing unexpected signing metadata."""
    with (app / "Contents/Info.plist").open("rb") as stream:
        if plistlib.load(stream)["CFBundleIdentifier"] != ACCOUNT:
            raise RuntimeError("Unexpected app bundle identifier")
    # Inspect every real Mach-O, including nested Sparkle helpers. Vendor
    # capability entitlements remain intact; no signing certificate or team
    # identity is allowed, even on a secondary architecture in a fat binary.
    magic = {bytes.fromhex(value) for value in (
        "feedface", "cefaedfe", "feedfacf", "cffaedfe",
        "cafebabe", "bebafeca", "cafebabf", "bfbafeca",
    )}
    checked = 0
    for path in app.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        with path.open("rb") as stream:
            if stream.read(4) not in magic:
                continue
        architectures = subprocess.check_output(["lipo", "-archs", str(path)], text=True).split()
        if not architectures:
            raise RuntimeError("No Mach-O architectures found: " + str(path.relative_to(app)))
        for architecture in architectures:
            result = subprocess.run(
                ["codesign", "-d", "--verbose=4", "--arch", architecture, str(path)],
                capture_output=True, text=True, check=True)
            fields = result.stderr.splitlines()
            if ("Signature=adhoc" not in fields or "TeamIdentifier=not set" not in fields
                    or any(field.startswith("Authority=") for field in fields)):
                raise RuntimeError("Expected ad-hoc signing without a certificate or team: "
                                   + str(path.relative_to(app)) + " (" + architecture + ")")
        checked += 1
    if not checked:
        raise RuntimeError("No signed Mach-O code found in app")
    print(f"Verified {checked} code objects: ad-hoc signing, no certificate authorities or team identifiers")
    return checked


def appcast(record):
    rss = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = APP_NAME + " Updates"
    entry = ET.SubElement(channel, "item")
    ET.SubElement(entry, "title").text = "Halo " + record["version"]
    ET.SubElement(entry, "{" + NAMESPACE + "}minimumSystemVersion").text = record["minimum_macos"]
    ET.SubElement(entry, "enclosure", {"url": record["url"], "length": str(record["size"]),
        "type": "application/octet-stream", "{" + NAMESPACE + "}version": record["build"],
        "{" + NAMESPACE + "}shortVersionString": record["version"],
        "{" + NAMESPACE + "}edSignature": record["signature"]})
    return ET.tostring(rss, encoding="utf-8", xml_declaration=True)


def notarize(path, profile):
    result = json.loads(run("xcrun", "notarytool", "submit", path, "--keychain-profile", profile,
                            "--wait", "--output-format", "json", capture=True))
    if result.get("status") != "Accepted":
        raise RuntimeError("Apple did not accept notarization; submission " + str(result.get("id")))
    return result["id"]


def local_dmg(args):
    app = args.app.resolve()
    audit_bundle(app)
    run("codesign", "--verify", "--deep", "--strict", app)
    with (app / "Contents/Info.plist").open("rb") as stream:
        info = plistlib.load(stream)
    destination = args.output or ROOT / "build/macos" / ("Halo-OG-" + info["CFBundleShortVersionString"] + "-local.dmg")
    create_dmg(app, destination.resolve())
    print("Local test DMG (not notarized or approved for public distribution): " + str(destination))


def build_release(args):
    settings = config()
    if not update_configuration(settings):
        raise RuntimeError("Choose release hosting and configure Halo's public update key first")
    base = https_url(settings.get("download_base_url"))
    if not re.fullmatch(r"\d+(?:\.\d+){0,2}", args.version) or not re.fullmatch(r"\d+(?:\.\d+)*", args.build_number):
        raise RuntimeError("Use numeric version and build numbers")
    if not args.sign_identity.startswith("Developer ID Application:"):
        raise RuntimeError("Select an explicit Developer ID Application identity")
    if run("git", "status", "--porcelain", capture=True).strip():
        raise RuntimeError("Build public releases from a clean, committed tree")
    destination = ROOT / "build/macos/releases" / args.build_number
    if destination.exists():
        raise RuntimeError("Release output already exists; use a new build number")
    setup_sparkle()
    key = run(SPARKLE / "bin/generate_keys", "--account", ACCOUNT, "-p", capture=True).strip()
    if key != settings["public_update_key"]:
        raise RuntimeError("Halo's Keychain update key does not match the committed public key")
    destination.mkdir(parents=True)
    run(sys.executable, "tools/macos_build.py", "--release", "--no-data-path", "--sign-identity", args.sign_identity,
        "--version", args.version, "--build-number", args.build_number)
    audit_bundle(APP)
    run("codesign", "--verify", "--deep", "--strict", APP)
    with (APP / "Contents/Info.plist").open("rb") as stream:
        minimum_macos = plistlib.load(stream)["LSMinimumSystemVersion"]
    app_zip = destination / "notarize-app.zip"
    run("ditto", "-c", "-k", "--keepParent", APP, app_zip)
    app_notary = notarize(app_zip, args.notary_profile)
    run("xcrun", "stapler", "staple", APP)
    run("spctl", "--assess", "--type", "execute", APP)
    dmg = destination / ("Halo-OG-" + args.version + ".dmg")
    create_dmg(APP, dmg)
    run("codesign", "--sign", args.sign_identity, "--timestamp", dmg)
    dmg_notary = notarize(dmg, args.notary_profile)
    run("xcrun", "stapler", "staple", dmg)
    signature = run(SPARKLE / "bin/sign_update", "--account", ACCOUNT, "-p", dmg, capture=True).strip()
    run(SPARKLE / "bin/sign_update", "--account", ACCOUNT, "--verify", dmg, signature)
    record = {"version": args.version, "build": args.build_number, "filename": dmg.name,
              "size": dmg.stat().st_size, "sha256": hashlib.sha256(dmg.read_bytes()).hexdigest(),
              "signature": signature, "public_update_key": key,
              "url": base + "/mac/" + args.build_number + "/" + dmg.name,
              "feed_url": settings["feed_url"], "source_revision": run("git", "rev-parse", "HEAD", capture=True).strip(),
              "minimum_macos": minimum_macos,
              "notarization": {"app": app_notary, "dmg": dmg_notary}, "distributable": True}
    (destination / "release.json").write_text(json.dumps(record, indent=2) + "\n")
    (destination / "appcast.xml").write_bytes(appcast(record))
    print("Prepared release: " + str(destination))


def publish(args):
    settings = config()
    release = args.directory.resolve()
    record = json.loads((release / "release.json").read_text())
    if not record.get("distributable") or not record.get("notarization", {}).get("dmg"):
        raise RuntimeError("Only verified notarized releases can be published")
    base = https_url(settings.get("download_base_url"))
    feed = https_url(settings.get("feed_url"))
    feed_prefix = base + "/"
    if not feed.startswith(feed_prefix):
        raise RuntimeError("The configured feed must live beneath the download base URL")
    key = "mac/" + record["build"] + "/" + record["filename"]
    if record["url"] != base + "/" + key or record["feed_url"] != settings["feed_url"]:
        raise RuntimeError("Release hosting changed; prepare a matching release")
    if record["public_update_key"] != settings["public_update_key"]:
        raise RuntimeError("Release update key no longer matches the app configuration")
    dmg = release / record["filename"]
    if dmg.parent != release or hashlib.sha256(dmg.read_bytes()).hexdigest() != record["sha256"]:
        raise RuntimeError("The release disk image has changed")
    if dmg.stat().st_size != record["size"]:
        raise RuntimeError("The release disk image length has changed")
    setup_sparkle()
    key_in_keychain = run(SPARKLE / "bin/generate_keys", "--account", ACCOUNT, "-p", capture=True).strip()
    if key_in_keychain != settings["public_update_key"]:
        raise RuntimeError("Halo's Keychain update key no longer matches the release")
    run("codesign", "--verify", "--strict", dmg)
    run("xcrun", "stapler", "validate", dmg)
    run(SPARKLE / "bin/sign_update", "--account", ACCOUNT, "--verify", dmg, record["signature"])
    bucket = settings.get("s3_bucket")
    if not bucket or not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", bucket):
        raise RuntimeError("Configure an S3 or R2 bucket first")
    aws = ["aws"]
    if settings.get("s3_profile"):
        aws += ["--profile", settings["s3_profile"]]
    if settings.get("s3_endpoint_url"):
        aws += ["--endpoint-url", https_url(settings["s3_endpoint_url"])]
    # A versioned archive is immutable. After an ambiguous write, inspect the
    # public object before retrying; never overwrite a different archive.
    try:
        with urllib.request.urlopen(record["url"], timeout=60) as response:
            existing = response.read()
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
        run(*aws, "s3api", "put-object", "--bucket", bucket, "--key", key, "--body", dmg,
            "--content-type", "application/x-apple-diskimage", "--if-none-match", "*")
    else:
        if hashlib.sha256(existing).hexdigest() != record["sha256"]:
            raise RuntimeError("A different disk image already exists at this versioned URL")
    with urllib.request.urlopen(record["url"], timeout=60) as response:
        if hashlib.sha256(response.read()).hexdigest() != record["sha256"]:
            raise RuntimeError("Public download verification failed; feed was not changed")
    (release / "appcast.xml").write_bytes(appcast(record))
    run(*aws, "s3api", "put-object", "--bucket", bucket, "--key", feed[len(feed_prefix):],
        "--body", release / "appcast.xml", "--content-type", "application/xml", "--cache-control", "no-cache")
    with urllib.request.urlopen(feed, timeout=60) as response:
        if response.read() != appcast(record):
            raise RuntimeError("The live feed does not yet match this release")
    print("Published and verified " + record["url"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("setup-updates", help="Create Halo's separate Sparkle key in the login Keychain")
    local = commands.add_parser("local-dmg", help="Package a verified asset-free local app without hosting or Developer ID")
    local.add_argument("--app", type=Path, default=APP, help="Existing signed Halo OG.app to package")
    local.add_argument("--output", type=Path)
    build = commands.add_parser("build")
    build.add_argument("--version", default=APP_VERSION)
    build.add_argument("--build-number", required=True)
    build.add_argument("--sign-identity", required=True)
    build.add_argument("--notary-profile", required=True)
    upload = commands.add_parser("publish")
    upload.add_argument("directory", type=Path)
    args = parser.parse_args()
    if args.command == "setup-updates":
        setup_sparkle()
        run(SPARKLE / "bin/generate_keys", "--account", ACCOUNT)
        print("Commit only the public key to port/macos/release-config.json. Back up the private key in 1Password.")
    elif args.command == "local-dmg":
        local_dmg(args)
    elif args.command == "build":
        build_release(args)
    else:
        publish(args)


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as error:
        print("Release failed: " + str(error), file=sys.stderr)
        sys.exit(1)
