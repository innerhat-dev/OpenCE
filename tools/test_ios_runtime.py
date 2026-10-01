#!/usr/bin/env python3
"""Check device IR and execute identical signed-image lowering in the Mac arena."""
import os
from pathlib import Path
import subprocess
import sys
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/ios/probe'
LLVM = Path(os.environ.get('HALO_MACOS_LLVM_BIN', '/opt/homebrew/opt/llvm/bin'))
def run(*args):
    subprocess.run([str(a) for a in args], cwd=ROOT, check=True, timeout=60)

def normalized_ir(path, bias):
    text = path.read_text().split('\n', 1)[1]  # ModuleID contains the temporary filename.
    for offset in (0, 0xff0000):
        text = text.replace(str(bias + offset), str(0x400000000 + offset))
    return text

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    objects = []
    for source in ('port/macos/tests/guest_memory.c', 'port/ios/tests/guest_libc.c'):
        base = OUT / Path(source).stem
        device = OUT / (Path(source).stem + '.device')
        run(sys.executable, 'tools/ios_guest_cc.py', '--target=arm64_32-apple-watchos',
            '-mcpu=cortex-a53', '-O2', '-ffreestanding', '-fno-stack-protector', '-fno-unwind-tables',
            '-fno-asynchronous-unwind-tables', '-S', source, '-o', str(device) + '.darwin.s')
        run(sys.executable, 'tools/ios_guest_cc.py', '--mac-check', '--target=arm64_32-apple-watchos',
            '-mcpu=cortex-a53', '-O2', '-ffreestanding', '-fno-stack-protector', '-fno-unwind-tables',
            '-fno-asynchronous-unwind-tables', '-S', source, '-o', str(base) + '.darwin.s')
        if normalized_ir(Path(str(device) + '.darwin.rebased.ll'), 0x400000000) != normalized_ir(Path(str(base) + '.darwin.rebased.ll'), 0x10000000000):
            raise RuntimeError('Mac signed-image lowering differs from device IR beyond the arena address')
        run(sys.executable, 'tools/android_asm_convert.py', str(base) + '.darwin.s', str(base) + '.s')
        run(LLVM / 'clang', '--target=aarch64-linux-android', '-c', str(base) + '.s', '-o', str(base) + '.o')
        objects.append(str(base) + '.o')
    run('build/macos/toolchain/bin/ld.lld', '-m', 'aarch64linux', '-static', '-nostdlib',
        '-Ttext=0x88000000', '-e', 'guest_test', *objects, '-o', OUT / 'guest.elf')
    run(sys.executable, 'tools/ios_embed.py', OUT / 'guest.elf', OUT / 'embed')
    run('clang', '-arch', 'arm64', '-O2', '-DHALO_IOS_MAC_CHECK=1', f'-I{OUT / "embed"}',
        'port/ios/tests/signed_image.c', OUT / 'embed/guest_image.s', '-o', OUT / 'signed_image')
    run('codesign', '--force', '--sign', '-', OUT / 'signed_image')
    run(OUT / 'signed_image')
if __name__ == '__main__':
    main()
