# Apple integration onto innerhat/OpenCE

## Bases and attribution

- New base: [innerhat-dev/OpenCE main](https://github.com/innerhat-dev/OpenCE/tree/036b9fe609bdba518711464ce24d2a2d9a3d7caf), `036b9fe609bdba518711464ce24d2a2d9a3d7caf`.
  This fork already has Mac and iOS signed-code runtimes, compiler lowering,
  renderer fixes, native menus, co-op and newer native/browser networking.
- Previous contribution: [AttilaTheFun/halo-ce-universal](https://github.com/AttilaTheFun/halo-ce-universal/commit/6702fb72efd8d97a780939d9b4bc04ab78d05aaf), `6702fb72efd8d97a780939d9b4bc04ab78d05aaf`, formerly PR #64 in OpenCommunityEdition/OpenCE.
- Earlier iOS foundation: [NicholasDominici/halo-ce-ios ios-port](https://github.com/NicholasDominici/halo-ce-ios/tree/3f2c14101d3ae1c7f0c0a11993a43407fadbeb46).
- Earlier browser foundation: [fqlx/halo-ce-universal fqlx/browser-webgl-stream-batching](https://github.com/fqlx/halo-ce-universal/tree/eaa82e6803f3d3e67c91d7f2fa2b15ee04e195f5), upstream PR #12.
- Shared decompilation lineage: OpenCommunityEdition/OpenCE and bnunu/halo-1.

This is a selective port of the earlier Apple additions onto the requested
new base, not a replacement of innerhat's engine with the older PR #12 tree.
The old branch has a local backup and bundle before it is retired.

## Decisions

| Earlier contribution | Decision |
| --- | --- |
| Assembly-rewritten ILP32 runtime, memory and ABI bridges | Superseded by innerhat's LLVM-pass runtime and shared Mac/iOS bridges; retain upstream's Extended Virtual Addressing device requirement. |
| Game/network rejoin, lifecycle, migration and compatibility patches | Retain the newer base's game/network implementation; do not reintroduce protocol-6/11 compatibility or old migration structures. |
| WebKit room-code UI, browser relay, WASM build scaffolding | Retire from this contribution: new base owns browser networking and its protocol. No claim of compatibility with older deployed WASM clients. |
| Missing data importer and distribution separation | Carry over transactional Files ISO/XISO import and private image/map storage; remove default bundling of proprietary maps. |
| Mac disc imports | Retain a SHA-256-verified private ISO/XISO beside extracted maps; store that private image path so later launches and community tooling do not depend on the selected external file. |
| Existing saves/imports | Preserve old branch Documents/save and generation store, plus innerhat's previous extracted-map and save paths. IDs/accounts must remain unchanged for in-place updates. |
| iPad, touch and controller handling | Enable universal device family, bring over touch layout/D-pad/primary-controller routing and landscape handling. Correct the earlier swapped flashlight/grenade labels. |
| Metal / OpenGL switch | Metal remains the default; native OpenGL ES was restored with explicit driver dispatch and EAGL window framebuffer handling. Both are selected in the persisted shake menu. |
| MetalFX and shader diagnostics | Adapt optional MetalFX, bounded ANGLE blob cache and shareable source/timing reports to the upstream context. Separate Mac graphics window; shake modal on iOS. |
| Mac menus, audio during menus, Quit | Retain upstream's native menu/audio integration rather than overwrite it with the older host. |
| Mouse sensitivity | Carry over 1–100, default 20 (0.10 multiplier), preserving existing config units and vertical SAME. Expand matching menu capacities to 128. |
| App icon/splash | Keep upstream artwork and display names; personal distribution branding lives only on the downstream internal branch. |
| IPA packaging/re-signing | Carry over asset exclusion and local signer; adapt to upstream Halo executable and required memory entitlement. |

## Validation

- Native ARM Mac and signed device app compile; simulator builds use a separate
  1-TB guest arena because recent simulators reserve the device's 16-GB range.
  The compiler pass, import trampolines and nested GL pointers all use the same
  platform bias. Device and simulator images have separate build directories.
- Signed-image ABI/runtime probe passes; 16 ISO/XISO safety tests pass under
  ASan/UBSan. A full private retail image was imported in the iPad simulator,
  including verification, private copy and extraction; relaunch uses that copy.
- Mac and iPad simulator reach and render the main menu. The iPad graphics
  modal is visible, and Mac MetalFX creates its scaler and runs to a clean exit.
  Simulator MetalFX is explicitly unavailable, rather than linked against a
  framework that the simulator SDK does not provide.
- Menu XML/capacity validation passes for 100 horizontal and 101 vertical entries.
  Fresh Mac/iOS config generation, TOML parsing, sensitivity save and process
  relaunch pass. Reordered upstream's misplaced display options to prevent
  duplicate `[display]` sections that invalidated generated settings on relaunch.
- The broader input, geometry, presentation, visibility, game-settings and audio
  fixture run has the same 5 failures, 7 errors and 1 skip on pristine
  `036b9fe6` and this branch before the focused config fix. Those outdated fixture
  failures are not claimed as passing or suppressed in CI.
- Device signing uses an explicit distribution identifier supplied at build time,
  with Extended Virtual Addressing. Packaging excludes game images/maps, saves,
  private keys and development configuration. Repository defaults remain unchanged.

Still to validate on physical hardware: iPhone/iPad startup and gameplay with the
new memory layout, controller connect/disconnect, MetalFX quality/performance,
background/resume, and a full online match with a current matching web client.
No physical devices were installed or launched by the test tooling. The draft
status is intentional; compilation and simulator smoke tests do not establish
retail fidelity or network interoperability with older deployed clients.

Mac importer regression checks also delete the original selected ISO and verify
that the retained image, extracted maps and reloaded preferences remain usable.
Failed imports leave the previous selection untouched.

## Current networking

See [protocol 28 and discovery validation](apple-network-28.md).
