# Local community-map reconstruction prototype

`tools/community_packages.py` prepares a content package and reconstructs a
complete Xbox v5 multiplayer cache from that package plus the player's original
Xbox NTSC `bloodgulch.map`, `a10.map` and `ui.map`. It uses only the reviewed
native `invader-extract` and `invader-build` helpers during reconstruction.
It never runs a package's executables or build scripts.

This is an **unchanged-asset stripping prototype**, not a claim that the remaining
payload has cleared provenance. Only a complete prepared tag whose size, SHA-256
and bytes equal a complete freshly extracted original stock tag is omitted.
Path equality alone is insufficient; an identical tag under a different path
can reference its original source path. A tag differing by even one byte remains
an entire literal asset. Modified-original and unknown assets stay intact,
including existing compatibility repairs. There is no chunk matching or binary
delta. Tags that are functionally similar but serialize differently also remain
literal. The existing hosted complete `.map` collection is unchanged by this
prototype.

## Optional Mac prototype

An explicitly prepared Mac build can include the two reviewed native helpers
with `tools/macos_build.py --content-tools <reviewed-toolchain-directory>`.
That build exposes **Settings → Import Community Package…**. Import runs
extraction and compilation in the background using the active session's
original data, then registers a verified map in
`~/Library/Application Support/Halo OG/Community Maps/maps/`. A local receipt
allows verified maps to be reused after restart without downloading, including
when HTTPS hosting is unconfigured or community downloads are off. Local
receipt identity takes precedence over an HTTP catalog entry with the same ID;
existing differing destination files are preserved for the user to resolve.
The local package choice is separate from consent to network downloads.
Cancellation stops a missing-map wait while keeping verified ready maps usable.

The reviewed helper binaries require **macOS 27.0**. Helper-enabled packaging
includes both binaries in the minimum-OS calculation, source and signed-binary
hash records, and their notices. Default CI packaging does not include these
helpers, and the current published testing DMG does not provide package import.
A pinned fresh-CI helper recipe and complete public corresponding-source
delivery remain unfinished; this opt-in bundle is a local prototype. Packaging
currently refuses `--release` with these helpers until that readiness gate is
completed. The optional helper audit checks the actual bundled binary hashes,
reviewed source pins, system-library dependencies and recorded notice hashes.

Both Python and the production native assembly/receipt APIs recreated Downrush
exactly in isolated tests, as recorded below. The isolated helper-enabled app
also passed signing and bundle audits. Native menu interaction and gameplay in
that prototype app have not been exercised; the installed app and active game
were preserved.

## Format and consumer contract

A `.hogpkg` file contains a 16-byte header (`<8sQ`, little endian), UTF-8 JSON,
then contiguous raw literal bytes. The magic is `HOGPKG1\n`; the unsigned 64-bit
integer gives the JSON byte length. Literal offsets start at the beginning of
the payload, not the file. There is no archive extraction or decompression.

Version 1 accepts exactly these manifest fields:

| Field | Meaning |
| --- | --- |
| `format`, `version` | `halo-og-community-package`, `1` |
| `id`, `scenario` | Safe lowercase community ID and relative compiled scenario ending in that ID |
| `profile`, `cache_build` | `stock-xbox-ntsc`, `01.10.12.2276` |
| `invader_commit` | Reviewed `7d25a855f5ef9e4ab8407abf490b21f8780abf27` revision |
| `tool_sha256` | Exact `extract` and `build` binary hashes; this prototype records Mac binaries |
| `stock_inputs` | Ordered `bloodgulch`, `a10`, `ui` entries: `name`, complete `size`, `sha256`, `type` (1, 0, 2) |
| `output` | Approved complete cache `size`, `sha256`, `declared_bytes`, `tag_bytes` |
| `payload_bytes`, `files` | Exact payload size and asset records |

Stock cache hashes are **per-package exact-base requirements**, not a global
allowlist of all acceptable original game data. The producer records its chosen
NTSC caches, and the consumer requires those exact complete inputs. This
Downrush package is pinned to the three original caches used by its approved
conversion; it does not accept every disc with the same build header.

Every file record has `tree`, `path`, `kind`, `classification`, `size` and
`sha256`. Trees are `tags`, `data` or `stock-overrides`. Literal records add
`offset`. `stock-reference` records add `stock_path`, are allowed only in `tags`,
and have classification `unchanged-stock`. They restore the whole original tag
under the prepared tag's requested path.

Other tag classifications are `modified-or-different-stock` and
`unknown-or-community`; neither proves authorship. Prepared `.hsc` files use
`generated-data`. Stock overrides are complete literals classified
`compatibility-modified-stock`, with an additional `original_sha256` guard for
the unmodified original tag. Overrides replace only the consumer's temporary
extracted copy. The original caches and selected game-data folder remain intact.

Limits are 4 MiB JSON, 20,000 records, 256 MiB for the complete package, 128 MiB
per asset, and 1 GiB of listed expanded assets. The consumer rejects unknown
fields/versions, duplicate JSON keys, unsafe or aliased paths, links, duplicate
or case-colliding names, file/directory conflicts, noncontiguous offsets,
truncation, trailing bytes and bad whole-file hashes. Original stock cache
inputs can exceed the 128 MiB multiplayer cache limit; their complete hashes
and NTSC headers are still required. The final multiplayer cache must satisfy
the 128 MiB declared-cache and 22 MiB tag-arena limits, including its tag range.

The consumer first verifies the package, trusted helper hashes, exact stock
cache inputs, all referenced stock tags and all override bases. It extracts
stock in `bloodgulch → a10 → ui` order, restores prepared tags/data, applies
guarded whole-file stock overrides and builds with stock-first tag priority:

```text
invader-build -g xbox-ntsc -t stock -t tags -m maps -d data -S data -E <scenario>
```

Only a cache matching the approved header, complete size and SHA-256 is usable.
Python reconstruction uses a fresh destination, publishes verified maps last,
and removes its generated destination on failure. It refuses existing
destinations, including dangling symlinks. The native Mac integration uses the
same data contract; consumer Python is not a requirement for that design.

## Producer and local verification

The producer accepts already reviewed converted tags and generated script data.
Its `original_stock_tags` input must be a fresh extraction with the pinned
extractor and the same stock order. `patched_stock_tags` must have the identical
inventory, with only the existing reviewed contents changed. A real
reconstruction from the original caches is the acceptance gate for that
producer-input assumption. See [community-maps.md](community-maps.md) for
central conversion and the pinned toolchain/source-manifest procedure.

```sh
# Fresh, unmodified stock extraction: verify the reviewed Mac helper before running it.
python3 - "$INVADER_BIN" "$INVADER_MANIFEST" \
  build/community-maps/local-package-prototype-20261003/original-stock-tags <<'PY'
import json
from pathlib import Path
import subprocess
import sys
from tools.community_packages import digest

binary = Path(sys.argv[1]).resolve() / "invader-extract"
manifest = json.loads(Path(sys.argv[2]).read_text())
pins = json.loads(Path("port/macos/content-tools.json").read_text())
if (manifest["invader_commit"] != pins["invader_commit"] or
    manifest["binaries"]["extract"]["sha256"] != pins["binaries"]["extract"] or
    digest(binary) != pins["binaries"]["extract"]):
    raise RuntimeError("Extractor differs from the reviewed Mac source and binary pins")
stock = Path(sys.argv[3]).resolve()
stock.mkdir(parents=True, exist_ok=False)
for name in ("bloodgulch", "a10", "ui"):
    subprocess.run([str(binary), "-t", str(stock),
                    str((Path("assets/maps") / (name + ".map")).resolve())], check=True)
PY

python3 tools/community_packages.py prepare \
  --prepared-tags build/community-maps/full-collection-import-20261002/downrush/tags \
  --prepared-data build/community-maps/full-collection-import-20261002/downrush/data \
  --original-stock-tags build/community-maps/local-package-prototype-20261003/original-stock-tags \
  --patched-stock-tags build/community-maps/full-collection-import-20261002/stock-tags \
  --stock-maps assets/maps \
  --expected-map build/community-maps/full-collection-import-20261002/downrush/maps/downrush.map \
  --scenario levels/test/pat_downrush/downrush \
  --toolchain-manifest "$INVADER_MANIFEST" \
  --destination build/community-maps/local-package-prototype-20261003/downrush.hogpkg

python3 tools/community_packages.py reconstruct \
  --package build/community-maps/local-package-prototype-20261003/downrush.hogpkg \
  --stock-maps assets/maps --tool-bin "$INVADER_BIN" \
  --toolchain-manifest "$INVADER_MANIFEST" \
  --destination build/community-maps/local-package-prototype-20261003/reconstructed

python3 tools/community_packages.py inspect \
  build/community-maps/local-package-prototype-20261003/downrush.hogpkg
python3 -m unittest tools.test_community_packages

# Actual native API acceptance, using a separately staged optional-helper app.
python3 tools/macos_map_package_smoke.py \
  --package build/community-maps/local-package-prototype-20261003/downrush.hogpkg \
  --data-root assets \
  --tools-app "build/community-maps/local-package-prototype-20261003/host-build-final/Halo OG.app" \
  --output build/community-maps/local-package-prototype-20261003/native-smoke-new-run
```

`INVADER_BIN` and `INVADER_MANIFEST` above are temporary shell shortcuts to the
reviewed local tools, not application settings. Choose fresh output paths for
every run. `prepare_package`, `read_package`, `materialize_package` (asset-only
fixture seam) and `reconstruct_package` are also callable Python APIs.

The isolated 2026-10-03 Downrush run produced a 69,252,341-byte package, SHA-256
`8652543d972f227d5dd7718bfaae06151290a93b2ffa0daa1fd20ce2dadcd287`.
Its 1,376 entries retain 453 same-path differing tags, 217 unknown/community
tags, five whole modified-stock compatibility tags and one generated script.
Its 700 unchanged-stock references omit 10,498,176 bytes. The raw package is
larger than the compressed compiled map; size reduction is not the acceptance
criterion for this pass.

Using only the pinned extractor and builder, fresh stock extraction plus this
package reproduced the approved Downrush cache exactly: 26,480,640 bytes,
SHA-256 `3282e580e782f939ae00c63f01971238eb0f85db19a2467efe42b5cb5600d126`.
The inspectable manifest, helper logs and reconstruction provenance are under
the ignored `build/community-maps/local-package-prototype-20261003/` directory.

The final native smoke (`native-smoke-final-v2-20261003/status.json`) reconstructed
those exact bytes in an observed **9.26 seconds** and passed 15 native parser,
reuse and helper-mismatch cases. It verified local registration, fresh startup
with hosting unconfigured and HTTP consent off (`PENDING → READY`), exact map
replay without helper execution, uppercase stock paths, tamper rejection and
preservation of conflicting files. Removed local maps produced an explicit
re-import/cancel status with mocked HTTP enabled; cancellation returned
`UNAVAILABLE` to stop waiting without fetching a map. The run made zero real network requests
and one mock catalog request; original caches, package and helpers were
unchanged. The filesystem could not exercise two differently cased stock
filenames because it is case-insensitive; the parser's case-collision fixture
did pass.

The separately staged `host-build-final/Halo OG.app` passed the app signature
and bundle audits for 11 Mach-O objects, with minimum OS 27.0. The game and UI
were not launched by this acceptance check. These results prove the local ARM
Mac data reconstruction and receipt path. Other toolchain/platform variants,
the remaining 39 package conversions, native menu interaction and gameplay need
their own checks; physical cross-platform play is still unverified. The
installed app, active game, original data and user preferences were untouched.
