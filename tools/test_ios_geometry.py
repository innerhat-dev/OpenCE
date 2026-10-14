#!/usr/bin/env python3
"""Execute the production geometry overflow check and its negative control as ILP32 ARM code.
Requires tools/ios_build.py --plugin-only and pytest for the upstream test fixture.
"""
import sys, subprocess, os
from pathlib import Path
root=Path(__file__).resolve().parents[1];os.chdir(root);sys.path.insert(0,str(root/'tools'))
from harness import function,constant
from harness.tests.test_geometry_bytes import NEGATIVE_CONTROLS
llvm=Path(os.environ.get('HALO_MACOS_LLVM_BIN','/opt/homebrew/opt/llvm@22/bin'));os.environ['HALO_MACOS_LLVM_BIN']=str(llvm)
out=root/'build/ios/v29-geometry';out.mkdir(parents=True,exist_ok=True)
source=(root/'port/linux/game/custom_edition_geometry.c').read_text();code=function(source,'geometry_bytes_add')
def run(*args):subprocess.run([str(a) for a in args],check=True,stdout=subprocess.DEVNULL)
for faulty in [False,True]:
 body=code
 if faulty:
  fault,case=NEGATIVE_CONTROLS['no-count-check'];body=body.replace(*fault)
 probe=out/('fault.c' if faulty else 'correct.c')
 probe.write_text('''typedef unsigned short word; typedef int boolean;
#define TRUE 1
#define FALSE 0
#define MAXIMUM_GEOMETRY_BYTES 0x8000000
_Static_assert(sizeof(unsigned long)==4,"ILP32 required");
'''+body+'''
unsigned geometry_test(unsigned unused) {
 unsigned long bytes=0;
 if(geometry_bytes_add(&bytes,0x08000001UL,32,0)) return 107;
 if(geometry_bytes_add(&bytes,0,32,0x80000001UL)) return 108;
 if(bytes) return 109;
 if(!geometry_bytes_add(&bytes,MAXIMUM_GEOMETRY_BYTES/32,32,0)) return 110;
 if(geometry_bytes_add(&bytes,0,32,1)) return 111;
 return 93;
}
''')
 asm=probe.with_suffix('.darwin.s');elfasm=probe.with_suffix('.s');obj=probe.with_suffix('.o')
 run(sys.executable,'tools/ios_guest_cc.py','--target=arm64_32-apple-watchos','-mcpu=cortex-a53','-O2','-ffreestanding','-fno-stack-protector','-S',probe,'-o',asm)
 run(sys.executable,'tools/android_asm_convert.py',asm,elfasm)
 run(llvm/'clang','--target=aarch64-linux-android','-c',elfasm,'-o',obj)
 run('build/macos/toolchain/bin/ld.lld','-m','aarch64linux','-static','-nostdlib','-Ttext=0x88000000','-e','geometry_test',obj,'-o',out/'guest.elf')
 run(sys.executable,'tools/ios_embed.py',out/'guest.elf',out/'embed')
 run('clang','-arch','arm64','-O2','-DTEST_IMPORT_TABLE=0x88000000',f'-I{out}/embed','port/ios/tests/signed_image.c',out/'embed/guest_image.s','-o',out/'probe')
 run('codesign','--force','--sign','-',out/'probe')
 result=subprocess.run([str(out/'probe')],capture_output=True,text=True)
 assert result.returncode==(1 if faulty else 0),result.stdout+result.stderr
 print(('Negative control rejected' if faulty else 'Production ILP32 overflow checks passed')+': '+result.stdout.strip())
