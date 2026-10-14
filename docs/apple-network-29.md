# Apple protocol 29 integration — 2026-10-14

Reviewed OpenCommunityEdition/OpenCE `b1ef7f7e..8102e711` (four substantive
commits plus merge #353). Last reviewed revision: `8102e711`; selected runtime
baseline: `3e0ba551114819a4a0f648e829208f5d754b742b`. This extends the selective
[protocol-28 integration](apple-network-28.md), not a wholesale upstream merge.
`innerhat/main` remains at `036b9fe6`.

| Upstream commit | Decision and effect |
| --- | --- |
| `52e33a391ef8cdc004bfcf8deb9d4713a2c04f12` | Adopt map-transfer trust/connection limits, bounded geometry and sound input, peer-address retirement, and decoder relocation with its license. Keep the fork's deleted web build/license scripts deleted. Other platform build references follow the decoder relocation. |
| `6d64abdb42fa848b193d2de584978a153389f26d` | Adopt download-restart bitmap bounds and cleanup, stalled-transfer accounting, malformed-map/tag checks, bounded diagnostic strings and Vorbis floor lookup. No new gameplay rule, artwork or sound replacement. |
| `37ded3287c7a74b91791b63e774922e21e86cc70` | Adopt upstream test-harness portability fixes. No runtime effect. |
| `3e0ba551114819a4a0f648e829208f5d754b742b` | Adopt protocol 29: keep map names readable and identify the host's version by its content hash in the game record. Select/download that version, preserve another local version, and restore old hash-suffixed names when unambiguous. Resolve documentation conflicts without restoring unrelated cinematic behavior claims. |
| `8102e711` | Reviewed merge: no independent runtime change beyond the four commits above. |

Cherry-picks retain upstream authors and origin hashes. The map-sharing and
version-selection source files and the wire manifest match upstream exactly.
Apple's population sorting, broker installation, per-container invite paths,
Metal/MetalFX settings, dynamic guest memory, ISO importer, controller routing,
landscape UI and suppressed scenario-song text remain. The broker list is
unchanged. Version-28 games are intentionally incompatible with this build.

## Validation

- The source-derived wire manifest matches version 29.
- Native Mac supplemental harness/cache tests: 203 passed, four skips. One
  geometry overflow negative control cannot detect its injected fault under
  LP64 (the upstream harness requires `-m32`, unavailable on Apple Silicon).
  `tools/test_ios_geometry.py` therefore runs that production function with
  the actual ILP32 ARM compiler and signed-image runtime: correct code passes,
  deliberately removing the overflow guard fails. This is not described as
  an all-green native 32-bit harness run.
- Browser ranking and menu checks: 11 passed plus three subtests.
- Full iOS simulator and unsigned device guest/host builds passed, including
  the relocated decoder and its bundled license.
- Simulator runtime used the production public directory, selected HALO
  UNIVERSAL on Wizard, joined, and received replicated gameplay state. Test
  shooting was off; no physical phone was installed/launched for this update.
  This establishes a short v29 interoperability check, not full-match,
  Custom Edition download or physical-device performance acceptance.
