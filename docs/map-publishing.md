# Publishing the testing map catalog

`tools/map-publisher.json` pins the nonsecret account, `halo` bucket, public origin,
and `catalogs/testing/current.json` destination. The current allowlist contains
**40 approved community caches**, including PB community variants. These rebuilt
maps include normal embedded Halo dependencies; the user approved that scope.
Expand the list only after approving additional maps for public distribution.
Never publish an XISO, original stock/campaign map files, or `ui.map` with this tool.

Prepare the complete catalog from the reviewed full-collection manifest. Each
map is selected explicitly; no directory-wide upload is performed:

```sh
python3 - <<'PY'
import json
import subprocess
from pathlib import Path

manifest = json.loads(Path(
    "build/community-maps/full-collection-combined-20261002/build.json"
).read_text())
assert len(manifest["maps"]) == 40
command = ["python3", "tools/map_catalog.py", "--output",
           "build/community-maps/new-catalog-candidate"]
for entry in sorted(manifest["maps"], key=lambda entry: entry["id"]):
    command += ["--map", entry["output"], "--prefetch", entry["id"]]
subprocess.run(command, check=True)
PY
python3 tools/publish_map_catalog.py \
  --prepared build/community-maps/new-catalog-candidate
```

The second command performs local validation only. It checks the exact manifest
schema, native cache format and limits, identity, SHA-256 and transfer size. The
directory must contain exactly `catalog.json` and the declared content-addressed
map objects, with no symlinks or extra files. It reads no credentials and sends no
network requests until `--publish` is explicitly supplied.

For an authorized upload, use the existing `CLOUDFLARE_API_TOKEN` from the established
1Password environment, an existing 1Password-mounted file, or a hidden terminal
prompt. Do not put the token in a command argument or create a checked-in env file.
The publisher reads a single literal `CLOUDFLARE_API_TOKEN=...` assignment from a mounted file;
it does not source or execute that file. No new game environment variable is used.

```sh
python3 tools/publish_map_catalog.py \
  --prepared build/community-maps/new-catalog-candidate \
  --credential-file /absolute/path/to/existing/1password-mounted.env --publish
```

Omit `--credential-file` to use an already populated `CLOUDFLARE_API_TOKEN`, or enter the token
at the hidden prompt when running in a terminal. The older publisher-only `CFTOKEN`
name remains an optional alias; the standard name takes precedence. The helper verifies the account
token, derives its S3 access key ID and secret in memory, and uses the R2 S3 API;
the credential needs object read/write access to `halo`, not bucket administration.
Cloudflare documents [token derivation](https://developers.cloudflare.com/r2/api/tokens/)
and [R2 S3 conditional writes](https://developers.cloudflare.com/r2/api/s3/api/).

Publication proceeds in this order:

1. Inspect the current catalog and capture its ETag, or record that it is absent.
2. Read each immutable object. Accept it only if its size and SHA-256 match the
   prepared bytes. Create an absent object with signed `If-None-Match: *`; never
   replace different bytes. A racing creation must pass the same byte check.
   If an immutable upload response is lost, accept the object only after exact
   private readback and the public verification in step 3. A definite missing
   object (HTTP 404) on private readback permits up to three total create-only
   upload attempts; other failed verification stops publication. Catalog writes
   remain conditional and are never blindly retried.
3. Download every map through the public HTTPS origin and verify exact size and
   SHA-256 before writing the catalog.
4. Publish the catalog with `If-Match` on the captured ETag, or `If-None-Match: *`
   if it was absent. Refuse a competing catalog change and ask the operator to
   validate and retry.
5. Verify the exact catalog bytes through both R2 and its canonical public URL.

Immutable maps use a one-year immutable cache policy; the mutable testing catalog
uses `Cache-Control: no-cache`. Requests refuse redirects and do not send upload
credentials to the public domain. Logs contain safe progress, sizes and hashes;
remote error bodies and raw library errors are suppressed.

A failure before step 4 leaves the current catalog intact, though verified
immutable objects may already have been created. A public catalog verification
failure after step 4 can mean the catalog is already published but a CDN still
serves older bytes; inspect that state before retrying. The tool does not delete
objects or attempt an automatic rollback. Running it again is safe for identical
immutable map bytes. Successful local validation or offline tests do not establish
that an upload or public distribution has occurred.

Run the offline regression tests with:

```sh
python3 -m unittest tools.test_publish_map_catalog tools.test_map_catalog
```

On October 3, 2026 the full collection was uploaded and the public catalog plus
all **40 immutable objects** were verified against their exact local sizes and
SHA-256 hashes. The objects total **904,589,312 bytes (862.68 MiB)** and all catalog
entries set `prefetch: true`. The catalog is available at
[the testing endpoint](https://dl.oghalo.com/catalogs/testing/current.json).
Its verified SHA-256 is
`84219567075381233f391f85562c57fc6bfebba4902dc1ee3add407855d17668`.

The final bucket inventory contains exactly **41 objects**: the 40 declared
community map objects and `catalogs/testing/current.json`, with no extra keys.
There are no standalone original disc, stock/campaign map, or UI files. The
maps contain the normal embedded Halo dependencies approved for this collection.
The safe local publication record, including before/after keys and byte counts,
is `build/community-maps/r2-full-collection-publication-2026-10-03.json`.
An independent read of the canonical public catalog matched the prepared bytes.

The exact prepared tree is
`build/community-maps/r2-full-collection-candidate-2026-10-03/`: only `catalog.json`
and its 40 declared content-addressed `.map` files, with no extras or symlinks.
Every map's bytes match its conversion manifest, the combined full-collection
build manifest, and the earlier successful local load/render smoke record.
Weld uses its validated repaired cache; Downrush retains the pilot's published
hash. No object is an original disc, stock/campaign map file, or UI cache.
This establishes byte delivery, not multiplayer or every-mode acceptance for
all 40 maps. See [conversion evidence](community-maps.md) and
[player setup](playtesting.md#community-maps).

Full-collection native acceptance used the unchanged production Mac downloader
from release commit `41c4aa82` in a fresh isolated support directory. Real
NSURLSession transfers automatically installed all 40 maps in an observed
**68.70 seconds**, without harness `requestMap` calls before installation.
Every file matched its catalog size/SHA-256, passed native cache validation,
and reported READY through the guest hook. A second downloads-disabled manager
verified all 40 files unchanged and READY, with **zero network attempts**. User
settings were untouched. An authored NTSC `ui.map` profile header gated this
probe; it checks the download service rather than original game data or gameplay.
The local `status.json`, `native-report.json`, and source provenance are under
`build/macos/netcode-v11-review-2026-10-03/r2-all-maps-harness/live-20261003T210600.329392Z/`.

Earlier that day the Downrush pilot was uploaded and both its immutable object
and public catalog were verified against the prepared bytes. The production
native downloader fetched all 26,480,640 bytes, validated SHA-256
`3282e580e782f939ae00c63f01971238eb0f85db19a2467efe42b5cb5600d126`, and reached
READY. A second downloads-disabled manager reused those bytes with zero network
requests. Evidence is in the ignored local review output under
`build/macos/netcode-v11-review-2026-10-03/r2-native-download/`.

The publisher identifies itself as `Halo-OG-map-publisher/1`.
The selected public endpoint returned HTTP 403 for Python's default user agent;
the descriptive publisher identity and the native NSURLSession client both
received the exact approved bytes without changing Cloudflare access rules.
The upload credential is concealed in the `oghalo.com` 1Password environment.

The real game smoke test then launched a host with Downrush and a native client
without that map. The client downloaded matching bytes into its isolated
managed library and both completed two consecutive Slayer matches over protocol
11, with bidirectional updates and no assertions or faults. Evidence is in
`build/macos/netcode-v11-review-2026-10-03/r2-client-multiplayer/validation.json`.
This is two instances on one Mac; cross-platform device play remains unverified.
