# Publishing the testing map catalog

`tools/map-publisher.json` pins the nonsecret account, `halo` bucket, public origin,
and `catalogs/testing/current.json` destination. The current pilot allowlist contains
only **Downrush**. Expand that list only after approving the next maps for public
distribution. Never publish an XISO, retail maps, or the UI cache with this tool.

Prepare the explicit rebuilt Xbox v5 NTSC 2276 multiplayer map first:

```sh
python3 tools/map_catalog.py --map /absolute/path/Downrush.map \
  --prefetch downrush --output build/community-maps/new-catalog-candidate
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
