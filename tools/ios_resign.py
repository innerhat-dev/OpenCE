#!/usr/bin/env python3
"""Re-sign a Halo device IPA; never downloads credentials or registers devices."""
import argparse
import datetime
import hashlib
import plistlib
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath


def run(*args):
    subprocess.run(list(map(str, args)), check=True)


def permits(pattern, value):
    return pattern == value or (pattern.endswith('*') and value.startswith(pattern[:-1]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ipa', type=Path)
    parser.add_argument('--profile', required=True, type=Path, help='Your .mobileprovision file')
    parser.add_argument('--identity', required=True, help='Exact keychain identity name or SHA-1 fingerprint')
    parser.add_argument('--bundle-id', required=True, help='App identifier covered by your profile')
    parser.add_argument('--output', required=True, type=Path, help='New signed IPA (must not exist)')
    parser.add_argument('--device', help='Check that this device UDID is included in the profile')
    args = parser.parse_args()
    if sys.platform != 'darwin':
        parser.error('Requires macOS, Xcode command-line tools and Python 3.')
    if args.output.exists() or args.output.resolve() == args.ipa.resolve():
        parser.error('Output must be a new file; the input IPA is never modified.')
    if not re.fullmatch(r'[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+', args.bundle_id):
        parser.error('Invalid bundle identifier.')
    profile = plistlib.loads(subprocess.check_output(['security', 'cms', '-D', '-i', str(args.profile)]))
    if profile['ExpirationDate'] <= datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None):
        parser.error('Provisioning profile has expired.')
    if 'iOS' not in profile.get('Platform', []):
        parser.error('An iOS provisioning profile is required.')
    devices = profile.get('ProvisionedDevices', [])
    if not devices:
        parser.error('Use a development or Ad Hoc profile containing registered devices, not an App Store profile.')
    if args.device and args.device.lower() not in [d.lower() for d in devices]:
        parser.error('The requested device is not registered in this profile.')
    allowed = profile['Entitlements']
    prefix, _ = allowed['application-identifier'].split('.', 1)
    app_id = prefix + '.' + args.bundle_id
    if not permits(allowed['application-identifier'], app_id):
        parser.error('Bundle identifier is not covered by the provisioning profile.')
    team = allowed['com.apple.developer.team-identifier']
    if team not in profile['TeamIdentifier']:
        parser.error('Profile team identifiers do not match.')
    identities = subprocess.check_output(['security', 'find-identity', '-v', '-p', 'codesigning'], text=True)
    matches = [(digest, name) for digest, name in re.findall(r'\) ([A-Fa-f0-9]{40}) "([^"]+)"[^\n]*', identities)
               if args.identity.upper() == digest.upper() or args.identity == name]
    certs = {hashlib.sha1(cert).hexdigest().upper() for cert in profile['DeveloperCertificates']}
    matches = [(digest, name) for digest, name in matches if digest.upper() in certs]
    if len(matches) != 1:
        parser.error('Select one installed signing identity whose certificate is included in the profile. '
                     'Use security find-identity -v -p codesigning to list identities.')
    identity = matches[0][0]
    # Grant only required capabilities, not every entitlement in the profile.
    entitlements = {'application-identifier': app_id,
                    'com.apple.developer.team-identifier': team,
                    'get-task-allow': bool(allowed.get('get-task-allow', False))}
    if any(permits(pattern, app_id) for pattern in allowed.get('keychain-access-groups', [])):
        entitlements['keychain-access-groups'] = [app_id]
    with tempfile.TemporaryDirectory(prefix='halo-resign-') as temporary:
        stage = Path(temporary)
        with zipfile.ZipFile(args.ipa) as archive:
            for entry in archive.infolist():
                path = PurePosixPath(entry.filename)
                mode = entry.external_attr >> 16
                if (path.is_absolute() or '..' in path.parts or '\\' in entry.filename
                        or not path.parts or path.parts[0] != 'Payload'
                        or stat.S_ISLNK(mode)):
                    parser.error('Expected a Halo IPA containing only Payload, without unsafe paths or symlinks.')
            archive.extractall(stage)
        apps = list((stage/'Payload').glob('*.app'))
        if len(apps) != 1:
            parser.error('Expected exactly one application in Payload.')
        app = apps[0]
        info_path = app/'Info.plist'
        info = plistlib.loads(info_path.read_bytes())
        # Older IPAs still hardcode the extended-VA arena. Missing metadata
        # must retain their entitlement requirement when using a newer kit.
        if info.get('HaloRequiresExtendedVirtualAddressing', True) is not False:
            capability = 'com.apple.developer.kernel.extended-virtual-addressing'
            if not allowed.get(capability):
                parser.error('This older IPA requires Extended Virtual Addressing. Download build 17 or newer.')
            entitlements[capability] = True
        if (info.get('CFBundleExecutable') not in ('Halo', 'HaloCE')
                or info.get('CFBundleSupportedPlatforms') != ['iPhoneOS']
                or not (app/info['CFBundleExecutable']).is_file()):
            parser.error('Expected a HaloCE iPhone/iPad device build.')
        if any(app.rglob('*.appex')) or any(app.rglob('*.app')):
            parser.error('Nested apps/extensions require separate profiles and are unsupported.')
        for signature in app.rglob('_CodeSignature'):
            shutil.rmtree(signature)
        info['CFBundleIdentifier'] = args.bundle_id
        info_path.write_bytes(plistlib.dumps(info))
        shutil.copyfile(args.profile, app/'embedded.mobileprovision')
        entitlement_path = stage/'entitlements.plist'
        entitlement_path.write_bytes(plistlib.dumps(entitlements))
        # ZIP extraction does not preserve executable mode. Restore bundle
        # executables before signing, including SDL and ANGLE frameworks.
        nested = list(app.rglob('*.framework')) + list(app.rglob('*.dylib'))
        for target in sorted(nested, key=lambda p: len(p.parts), reverse=True):
            if target.suffix == '.framework':
                framework = plistlib.loads((target/'Info.plist').read_bytes())
                executable = target/framework['CFBundleExecutable']
            else:
                executable = target
            executable.chmod(0o755)
            run('codesign', '--force', '--sign', identity, '--timestamp=none', target)
        (app/info['CFBundleExecutable']).chmod(0o755)
        run('codesign', '--force', '--sign', identity, '--timestamp=none',
            '--generate-entitlement-der', '--entitlements', entitlement_path, app)
        run('codesign', '--verify', '--deep', '--strict', app)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(args.output, 'x', zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(app.rglob('*')):
                if path.is_file():
                    archive.write(path, path.relative_to(stage))
        digest = hashlib.sha256(args.output.read_bytes()).hexdigest()
        args.output.with_suffix(args.output.suffix+'.sha256').write_text(f'{digest}  {args.output.name}\n')
    print(f'Signed IPA: {args.output}\nBundle ID: {args.bundle_id}\nProfile expires: {profile["ExpirationDate"]} UTC')
    print('Install with Apple Configurator, or extract the IPA and use xcrun devicectl device install app.')
    print('Keep your signing account and bundle ID unchanged when updating to preserve imported game data.')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, subprocess.CalledProcessError) as error:
        sys.exit(f'Re-signing failed: {error}')
