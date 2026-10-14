# iOS normal-address-space arena

The build-16 LiveContainer report failed before gameplay while reserving the
fixed 448-GiB guest-data arena. Increased Memory Limit is a different capability
from Extended Virtual Addressing. Adding entitlements to the guest app cannot
change the LiveContainer host's capabilities.

## Change

Build 17 asks `vm_map` for an available 2304-MiB virtual region aligned to 4 GiB,
with no initial access and a maximum protection of read/write. The host records
that address. The compiler derives the same base from each guest function's
stack pointer; every guest entry already runs on a stack inside this arena.
The generated import trampolines and explicit wide GL arguments use the same
translation. Indirect calls read the signed-code delta from the selected arena.
The game retains its 32-bit layouts and pointer values. macOS retains its fixed
arena and compiler path. No JIT, writable executable pages, overwritten host
mappings, or reserved ABI registers are introduced.

The application no longer requests Extended Virtual Addressing or Increased
Memory Limit. The signing helper recognizes an explicit Info.plist flag; it
still requires Extended Virtual Addressing for old IPAs without that flag.
New code and old guest images must never be mixed: rebuild the full guest.

## Attribution

The comparison was prompted by @UEMxMDE's report on
[innerhat-dev/OpenCE PR #1](https://github.com/innerhat-dev/OpenCE/pull/1#issuecomment-6162542405).
[NicholasDominici/halo-ce-ios, ios-port](https://github.com/NicholasDominici/halo-ce-ios/tree/b8a7266a68467ac2819105d33567e31c7ed321ca)
uses an OS-selected, 4-GiB-aligned arena in `port/ios/host/host_memory.c`.
This informed the allocator approach. Its register-based guest lowering was
not imported; our existing LLVM signed-image pass now derives the base from SP.

## Validation and limits

- The signed-code execution probe runs unchanged machine code in an OS-selected
  arena and at fixed 1-TiB and 2-TiB bases. It exercises globals, stack pointers,
  indirect calls, unaligned loads, variadics, libc operations, atomics, and the
  generated host-import bridge with stack and global pointer arguments.
- Device and simulator compiler IR match (apart from temporary ModuleID).
- The full simulator build starts Metal, resolves all 227 imports and renders
  the main menu with the dynamic allocator (1006 widgets loaded).
- The simulator runs under macOS's address-space rules and selected 448 GiB.
  It cannot validate unentitled physical-iOS allocation or LiveContainer.
  Low fixed-address probes on this Mac correctly failed on occupied mappings.
- Physical iPhone 15 Pro on iOS 27.0.1: installed and launched standalone build
  25 without a debugger; signature verification confirmed neither Extended
  Virtual Addressing nor Increased Memory Limit. The OS selected 448 GiB,
  all 227 imports resolved, Metal/MetalFX initialized and the main menu loaded.
  This establishes startup on that device, not iOS 26 or LiveContainer support.
- Physical gameplay/performance and LiveContainer remain to be tested.
  A normal process must still have a sufficiently large aligned free region;
  this implementation cannot guarantee a suitable hole in every host process.
