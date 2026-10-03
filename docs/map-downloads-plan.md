# Managed game data and community-map downloads

Updated October 3, 2026. The source investigation started from `main` at
`6c1f1ae8`. The 40-map R2 collection's public bytes were verified on October 3;
all 40 also passed native automatic downloads and offline reuse. The Downrush
pilot passed same-Mac multiplayer checks. Cross-platform device acceptance
remains a separate check.

## Implemented in this change

The Mac app can manage a copy of selected extracted maps and download approved
community maps while it runs. The checked-in download configuration points at
`https://dl.oghalo.com/catalogs/testing/current.json`; downloads remain off until
the player opts in. Selected original disc/map files stay local. Endpoint
configuration and local tests alone do not establish live catalog/map publication
or download success.

| Flow | Behavior |
| --- | --- |
| Choose Disc Image | Existing ISO/XISO import extracts maps into a fresh Application Support import ID. Leaves the original image and earlier imports in place. |
| Choose Maps Folder | Offers **Copy and Manage**, **Use This Folder**, or **Cancel**. Managed copying streams only regular `.map` files from known map directories, verifies copied SHA-256 bytes, validates the resulting maps, and changes the saved selection only on success. Linked developer data can still be used in place. |
| Runtime import | Copy/extraction runs off the game thread. Existing simulation/network activity continues; changing the selected stock-data root applies next launch. |
| Community download consent | Separate native Settings checkbox explains HTTPS catalog downloads and disk storage. Preference defaults off and survives app updates. |
| Launch download | When enabled/configured, validates cached catalog/installed files and fetches the current catalog asynchronously. Only catalog entries with `prefetch: true` download proactively. Other approved maps download when requested by a missing-map join. |
| Missing approved map | Readiness stays pending while HTTP download, verification and engine precache run. Native Settings shows progress/failure and offers **Check Maps / Retry** and **Cancel Downloads**. Unknown/stock map names do not become arbitrary download URLs. |
| Completed map | Installs a whole, verified map atomically into the managed library. The loader uses existing user data first, then a read-only managed map overlay for entries whose cached native state is READY. Reopening map selection rescans available maps. |
| Downloads disabled | Stops network requests; already-installed, catalog-verified maps remain usable. A current incompatible stock-data profile disables this collection's overlay and download requests. |

The native UI/settings shipped with the app are distinct from `ui.map`.
Original stock `ui.map`, campaign maps, multiplayer stock caches and disc
images remain user-imported data. No import/join operation uploads user data.

## Storage and integration points

The canonical macOS location is outside the app bundle:

```text
~/Library/Application Support/Halo OG/
  macos-settings.json            data/source-image paths, display/download consent
  config.toml                    existing advanced game settings
  <existing saves/profiles/cache/logs>
  Game Data/<import-id>/
    maps/                        copied or disc-extracted original map files
    maps_<language>/             copied when present in selected extracted data
    import.json                  copied-folder provenance, byte counts, hashes
  Community Maps/
    catalog.json                 last accepted catalog and configured source URL
    maps/<map-id>.map             verified complete community caches
    Downloads/<hash>-<UUID>.partial
```

On first launch the app copies the legacy `Halo CE Universal` Application
Support tree into `Halo OG`, including settings, profiles, saves and maps.
Original files and existing destination files are preserved. Managed selections
are repointed only after their copied targets are complete. A copy failure
stops launch with an error so an empty new directory cannot hide prior settings.
Explicit development save-root overrides are outside this migration.

The source folder and prior successful imports are preserved. Copy failure,
validation failure or cancellation before copying leaves the prior selection
unchanged. Original ISO bytes are not archived automatically. Existing
`HALO_DATA_ROOT`, `HALO_SAVE_ROOT`, CLI test behavior and save locations remain
compatible; no new application environment variable is introduced.

Incomplete downloads are never exposed as maps. Publication uses an exclusive
hard link followed by removal of the staging file, so a destination that appears
mid-download cannot be overwritten. Same-name/different-byte files produce a
visible collision error and are left intact. A retry starts a fresh transfer;
resumable range transfers and automatic deletion of stale interrupted-process
partials are not implemented. There is no automatic deletion of original maps.

Native implementation: `port/macos/native/HaloPreferences.*`,
`HaloMapDownloads.*` and `host_menu.m`. The host-only C hooks are:

```c
int halo_map_download_directory(char *out, size_t capacity);
int halo_map_download_request(const char *map_name);
// UNAVAILABLE=0, READY=1, PENDING=2, FAILED=-1
```

The request hook consults short-lived locked state and schedules work without
file reads, hashing or HTTP waits on the guest/tick thread. The directory hook
includes `/maps`; importing/loading any overlay entry additionally requires
READY, so an arbitrary local file or an unverified cached file cannot activate
itself. Initial catalog checks report PENDING; catalog/download failures report
FAILED with native retry/cancel controls. A catalog refresh clears stale READY
state when files disappear or catalog revisions change.

Engine integration uses `native_map_get_path` / `native_map_download_pending`
with a read-only `M:` namespace. Discovery, multiplayer build checks and disk
precache use the same map resolver. User stock/custom files retain priority.
The selector retains the stock 13 maps/order, appends safe custom names sorted
by name, and keeps the existing 128-entry limit.

The native downloader uses `NSURLSession`; SHA-256 uses macOS CommonCrypto.
Downloads/copying continue off the game thread, preserving the 30 Hz simulation.
The other native platforms do not acquire new Mac host symbols. Their existing
save defaults are `%APPDATA%/Halo OG` on Windows and `$XDG_DATA_HOME/halo-og`
or `~/.local/share/halo-og` on Linux, with non-destructive legacy copying.
Native Windows/Linux HTTP downloaders
are later work; they need the same content policy and final map bytes.

## Configure the publisher endpoint

`port/macos/map-downloads.json` is packaged as a non-secret app resource. Set
`catalog_url`, `objects_base_url` and exact HTTPS `allowed_origins`; keep the
profile/build and bounds checked in. The current collection contains 40 approved
caches totaling 904,589,312 bytes (862.68 MiB), all with `prefetch: true`.
Neither R2 upload credentials nor catalog
signing secrets belong in the client. An illustrative catalog entry is:

```json
{
  "schema_version": 1,
  "profile": "stock-xbox-ntsc",
  "maps": [
    {
      "id": "downrush",
      "sha256": "<64 lowercase hex characters>",
      "file_bytes": 12345,
      "cache_version": 5,
      "cache_build": "01.10.12.2276",
      "scenario_type": 1,
      "object_key": "maps/sha256/<hash>/downrush.map",
      "prefetch": false
    }
  ]
}
```

Placeholders are invalid publication values. The object key must exactly match
the canonical lowercase map ID/hash. Managed filenames and overlay lookups use
that exact lowercase spelling; user data keeps its case-insensitive lookup.
Relative paths, traversal, stock/campaign/UI names, duplicate
names ignoring case, invalid hash/size fields and unsupported builds are
rejected. URL redirects are restricted to the configured HTTPS origin list.
The catalog is bounded at 1 MiB/115 custom maps and each transfer/cache at
128 MiB by the shipped settings; lower configured limits are enforced.

A complete map must match its catalog byte count and full SHA-256. Native
verification also checks v5 header/footer, matching safe cache name, multiplayer
scenario type, NTSC build `01.10.12.2276`, declared cache bounds, the original
22 MiB tag arena and tag ranges within declared cache bytes. Compressed v5 files
can have a transfer length different from their declared decompressed length.
The player must select original NTSC 2276 data for this catalog; PAL/other
releases retain their data and do not silently use this collection.

This is publisher allowlisting through a configured TLS endpoint plus full map
hash verification. Detached catalog signatures/publisher-key pinning are not
implemented yet. The catalog publisher is trusted to select the content; a
hash does not establish authorship, gameplay correctness or permission to
redistribute it. The client never downloads a map from a host-supplied URL.

Build final Xbox v5 maps in the controlled publisher workflow using
`tools/community_maps.py` and the pinned source/toolchain provenance. Do not
rename PC v7 maps or edit their version field as conversion. Generated maps
are local output rather than bundled DMG data. The approved 40-map collection
retains its exact validated output hashes, including repaired Weld. Full-collection
load/render smoke tests do not establish every map/mode/network combination's
acceptance. See [community maps](community-maps.md).

`tools/map_catalog.py` prepares a fresh local catalog/object tree from explicitly
selected rebuilt maps and verifies copied objects; it performs no uploads:

```sh
python3 tools/map_catalog.py \
  --map /path/to/rebuilt/downrush.map \
  --prefetch downrush \
  --output build/community-maps/r2-candidate-new
```

It writes `catalog.json` and `maps/sha256/<hash>/<map-id>.map`, rejects stock,
unsafe/duplicate/wrong-format/over-limit maps, and refuses an existing output
directory. The actual prepared collection is in the ignored local
`build/community-maps/r2-full-collection-candidate-2026-10-03/` tree. Preparing
maps alone is not proof of hosting or permission to publish; the upload
allowlist remains a separate reviewable decision.

## R2 delivery

Use a dedicated bucket and an owned HTTPS custom domain for approved public
content. R2 buckets start private; `r2.dev` is rate-limited development hosting.
A custom domain enables Cloudflare caching/access controls, and public buckets
do not offer root directory enumeration. Publish the catalog explicitly and
configure caching for `.map` objects rather than relying on extension defaults.
[R2 public buckets](https://developers.cloudflare.com/r2/buckets/public-buckets/)
and [Cache Rules settings](https://developers.cloudflare.com/cache/how-to/cache-rules/settings/)
describe these behaviors.

```text
catalogs/testing/current.json
maps/sha256/<sha256>/<map-id>.map
```

Upload immutable objects first, verify an HTTP download against the local
size/hash, then publish the catalog. Use long cache lifetimes for hash-addressed
objects and a short cache/revalidation policy for the mutable catalog. Release
catalogs should carry a reviewable exact object/hash allowlist and author/license
provenance. Only separately approved community content is eligible for upload;
conversion does not confer redistribution rights. The user approved working
community maps, including their normal embedded Halo dependencies and PB variants.
Original disc images, stock/campaign cache files and `ui.map` are excluded.
Native settings ship with the app; an additional approved
UI/settings pack would need separate opt-in/content compatibility work.

For private testers, a Worker bound to a private bucket or a trusted service
issuing expiring presigned GET URLs is an alternative. Presigned URLs are bearer
credentials and work on the S3 endpoint, not a custom domain; the current
immutable object-key downloader would need an authenticated-delivery adapter.
[R2 presigned URLs](https://developers.cloudflare.com/r2/api/s3/presigned-urls/)
documents that constraint. Do not embed an R2 access key in the app.

For later resumable downloads, test the endpoint's range/length/revision behavior
before enabling resume. R2 Workers support ranged reads but their conditional
API excludes `If-Range`, requiring explicit equivalent logic when proxying.
[R2 Workers API](https://developers.cloudflare.com/r2/api/workers/workers-api-reference/)
explains the API. HTTP ETags are not the content authority: multipart ETags are
not full-file SHA-256 hashes.
[R2 uploads](https://developers.cloudflare.com/r2/objects/upload-objects/)
describes their format.

The public collection uses bucket `halo`, domain `dl.oghalo.com`, and the
concealed publisher credential in the `oghalo.com` 1Password environment.
All 40 approved objects and the public catalog were verified against their
prepared hashes. The final bucket inventory has exactly 40 community objects
plus the catalog, with no standalone original disc, stock/campaign map or UI
files. Downrush additionally passed native/game acceptance.
See [the publisher workflow and evidence](map-publishing.md). R2 Object Read &
Write can be limited to chosen buckets; bucket/domain administration needs
separate permissions. Obtain developer credentials through the established
1Password MCP environment mechanism and never print, commit or bundle secrets.
[R2 authentication](https://developers.cloudflare.com/r2/api/tokens/)
describes those scopes. Additional map uploads still require an explicit
publisher allowlist expansion and acceptance checks.

## Verification and next stages

`python3 tools/test_macos_map_downloads.py` runs the actual native NSURLSession
service against synthetic HTTPS responses supplied by an in-process
NSURLProtocol fixture. It covers consent/no requests, asynchronous pending to
verified publication, invalid catalogs/headers/hash/length/symlinks, tighter
capacity limits, collisions, offline cached reuse with downloads disabled,
revalidation after deletion/catalog removal, retry, cancellation, HTTP catalog
failure, PAL gating and uppercase folder/UI names. It uses no game assets,
credentials or external network.

The unchanged release Mac downloader also prefetched all 40 live R2 maps into
a fresh isolated library in an observed 68.70 seconds. All passed exact
size/SHA-256, native validation and guest READY checks; a downloads-disabled
second manager reused every file unchanged with zero network attempts. User
settings were untouched. This probe used an authored NTSC profile header and
verified transport/cache behavior, not original data or gameplay. See the
[full-collection native evidence](map-publishing.md).

For an explicit live acceptance check after publication, run
`python3 tools/macos_map_download_smoke.py --data-root /path/to/NTSC/data --timeout 120`.
It uses the production NSURLSession service and checked-in public endpoint,
downloads `downrush` into a fresh isolated support directory, checks full
size/SHA/header and guest-facing READY, then verifies unchanged cached bytes
with a second downloads-disabled manager whose network requests are rejected
and counted. It preserves logs and provenance/status JSON under
`build/macos/tests/map-download-smoke/`; no user settings are modified. The
explicit `--fixture-ntsc-ui` option uses an authored profile header and does
not validate original retail data or gameplay. This command does not upload.

`python3 tools/test_macos_menu.py --preferences` covers persistent consent,
copy/source preservation, copied-byte identity, invalid-copy rollback,
uppercase paths, keeping linked external developer data available, existing
disc import and release boundaries. The native menu-loop test separately
checks settings/file sheets/import while SDL and loopback packets continue.
Synthetic fixtures prove control flow and rejection behavior, not live R2
throughput or cross-platform map play.

Next steps are:

1. Check full-collection background downloads and offline reuse on fresh tester
   profiles; verify retry and native missing-map joins beyond the Downrush pilot.
   No player should need development tools or a source checkout.
2. Test stock and community host/client pairs across the target native platforms
   using matching protocol/content profiles. HTTP download support for other
   platforms remains a separate implementation; they can use matching manually
   installed map files meanwhile.
3. Add exact session map identity: current host/readiness messages name a map,
   not its complete SHA-256. Existing engine checksum/build handling is kept,
   but it does not prove arbitrary hosts use the catalog's exact bytes. A new
   content-ID capability/wire change must be reviewed/versioned independently
   of netcode 11 compatibility. Do not claim unmodified v11 peers understand
   an added hash field.
4. Add publisher catalog signatures, validated resume, storage cleanup, and
   more detailed download/library controls after broader playtesting.
5. Evaluate peer-to-peer delivery using the same approved content identity and
   final verification. Treat peers as transport only; require separate upload
   consent, serve only authorized community objects, cap transfer bandwidth and
   retain R2 fallback. Do not fill the gameplay reliable stream with map bytes.
