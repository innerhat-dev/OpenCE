#!/usr/bin/env python3
"""Publish an explicit prepared map catalog to R2; default is local validation only.

Credentials stay in memory. Use an existing CLOUDFLARE_API_TOKEN, a 1Password-mounted
credential file, or the hidden terminal prompt. No bucket administration is used.
"""
import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import getpass
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import shlex
import stat
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import build_opener, HTTPRedirectHandler, Request

if __package__:
    from .map_catalog import MAX_CATALOG_BYTES, MAX_MAPS, NTSC_BUILD, validate_map
else:
    from map_catalog import MAX_CATALOG_BYTES, MAX_MAPS, NTSC_BUILD, validate_map


DEFAULT_CONFIG = Path(__file__).with_name("map-publisher.json")
ENTRY_FIELDS = {"id", "sha256", "file_bytes", "cache_version", "cache_build",
                "scenario_type", "object_key", "prefetch"}
MAP_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,30}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class PublishError(Exception):
    """An operator-safe error; never include credential or remote response text."""


@dataclass(frozen=True)
class Response:
    status: int
    headers: dict
    body: bytes


@dataclass(frozen=True)
class Prepared:
    directory: Path
    catalog: bytes
    maps: tuple


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise PublishError("JSON contains a duplicate key")
        result[key] = value
    return result


def read_regular(path, limit):
    # Do not follow a selected file symlink, including a replaced file between
    # inventory validation and upload. The exact bytes are hashed again below.
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(descriptor, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise PublishError("Prepared input must contain regular files")
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise PublishError("Input exceeds its permitted byte limit")
    return data


def parse_json(data):
    try:
        return json.loads(data, object_pairs_hook=unique_object)
    except (ValueError, UnicodeError):
        raise PublishError("Input is not valid UTF-8 JSON") from None


def load_config(path=DEFAULT_CONFIG):
    config = parse_json(read_regular(path, 16384))
    fields = {"schema_version", "account_id", "bucket", "public_base_url",
              "catalog_key", "allowed_map_ids"}
    if not isinstance(config, dict) or set(config) != fields or type(config["schema_version"]) is not int or config["schema_version"] != 1:
        raise PublishError("Publisher configuration has an unsupported schema")
    if not isinstance(config["account_id"], str) or not re.fullmatch(r"[0-9a-f]{32}", config["account_id"]):
        raise PublishError("Publisher account ID is invalid")
    if not isinstance(config["bucket"], str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,61}[a-z0-9]", config["bucket"]):
        raise PublishError("Publisher bucket is invalid")
    if not isinstance(config["public_base_url"], str):
        raise PublishError("Publisher public URL is invalid")
    url = urlsplit(config["public_base_url"])
    if (url.scheme != "https" or not url.hostname or url.username or url.password
            or url.port is not None or url.path != "/" or url.query or url.fragment):
        raise PublishError("Publisher public URL must be an HTTPS origin ending in /")
    if config["catalog_key"] != "catalogs/testing/current.json":
        raise PublishError("This publisher is limited to the testing catalog")
    ids = config["allowed_map_ids"]
    if not isinstance(ids, list) or not ids or any(not isinstance(value, str) or not MAP_ID.fullmatch(value) for value in ids) or len(set(ids)) != len(ids):
        raise PublishError("Publisher map allowlist is invalid")
    return config


def validate_prepared(directory, config):
    directory = Path(os.path.abspath(directory))
    if directory.is_symlink() or not directory.is_dir():
        raise PublishError("Select an existing prepared catalog directory")
    data = read_regular(directory / "catalog.json", MAX_CATALOG_BYTES)
    catalog = parse_json(data)
    if (not isinstance(catalog, dict) or set(catalog) != {"schema_version", "profile", "maps"}
            or type(catalog["schema_version"]) is not int or catalog["schema_version"] != 1
            or catalog["profile"] != "stock-xbox-ntsc" or not isinstance(catalog["maps"], list)
            or not 1 <= len(catalog["maps"]) <= MAX_MAPS):
        raise PublishError("Catalog has an unsupported schema or map count")
    ids, expected_files = set(), {"catalog.json"}
    expected_dirs = set()
    for entry in catalog["maps"]:
        if not isinstance(entry, dict) or set(entry) != ENTRY_FIELDS:
            raise PublishError("Catalog map has unexpected fields")
        name, digest = entry["id"], entry["sha256"]
        if (not isinstance(name, str) or not MAP_ID.fullmatch(name) or name in ids
                or name not in config["allowed_map_ids"] or not isinstance(digest, str)
                or not SHA256.fullmatch(digest)):
            raise PublishError("Catalog map identity is duplicate, invalid, or outside the publisher allowlist")
        ids.add(name)
        key = f"maps/sha256/{digest}/{name}.map"
        if (entry["object_key"] != key or type(entry["file_bytes"]) is not int
                or type(entry["cache_version"]) is not int or entry["cache_version"] != 5
                or entry["cache_build"] != NTSC_BUILD or type(entry["scenario_type"]) is not int
                or entry["scenario_type"] != 1 or type(entry["prefetch"]) is not bool):
            raise PublishError("Catalog map metadata or immutable key is invalid")
        expected_files.add(key)
        parent = Path(key).parent
        while str(parent) != ".":
            expected_dirs.add(parent.as_posix())
            parent = parent.parent
    files, directories = set(), set()
    for path in directory.rglob("*"):
        if path.is_symlink():
            raise PublishError("Prepared directory must not contain symlinks")
        key = path.relative_to(directory).as_posix()
        if path.is_dir():
            directories.add(key)
        elif path.is_file():
            files.add(key)
        else:
            raise PublishError("Prepared directory contains a non-regular input")
    if files != expected_files or directories != expected_dirs:
        raise PublishError("Prepared directory must contain exactly catalog.json and its declared map objects")
    for entry in catalog["maps"]:
        try:
            header = validate_map(directory / entry["object_key"])
        except ValueError:
            raise PublishError("Prepared map does not satisfy the native Xbox cache checks") from None
        if (header["name"].casefold() != entry["id"] or header["sha256"] != entry["sha256"]
                or header["file_bytes"] != entry["file_bytes"]):
            raise PublishError("Prepared map does not match the catalog hash, size, or identity")
    return Prepared(directory, data, tuple(catalog["maps"]))


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


class HTTPS:
    def __init__(self):
        self.opener = build_opener(NoRedirect())

    def request(self, method, url, *, headers=None, body=None, limit=16384):
        if urlsplit(url).scheme != "https":
            raise PublishError("Only HTTPS requests are permitted")
        request_headers = {"User-Agent": "Halo-OG-map-publisher/1"}
        request_headers.update(headers or {})
        request = Request(url, data=body, headers=request_headers, method=method)
        try:
            with self.opener.open(request, timeout=60) as response:
                result_headers = {key.lower(): value for key, value in response.headers.items()}
                if result_headers.get("content-encoding", "identity").lower() != "identity":
                    raise PublishError("Remote response unexpectedly changed content encoding")
                data = response.read(limit + 1)
                if len(data) > limit:
                    raise PublishError("Remote response exceeds its expected byte limit")
                return Response(response.status, result_headers, data)
        except HTTPError as error:
            # Error bodies can echo request data. Do not read or display them.
            headers = {key.lower(): value for key, value in error.headers.items()}
            error.close()
            return Response(error.code, headers, b"")
        except (URLError, OSError, ValueError):
            raise PublishError("HTTPS request failed; credentials and remote error text were suppressed") from None


def load_token(credential_file=None):
    if credential_file is not None:
        try:
            content = read_regular(credential_file, 65536).decode("utf-8")
            assignments = {"CLOUDFLARE_API_TOKEN": [], "CFTOKEN": []}
            for line in content.splitlines():
                match = re.match(r"^\s*(?:export\s+)?(CLOUDFLARE_API_TOKEN|CFTOKEN)\s*=", line)
                if match:
                    fields = shlex.split(line.split("=", 1)[1], comments=True)
                    if len(fields) != 1:
                        raise ValueError()
                    assignments[match.group(1)].append(fields[0])
            if any(len(values) > 1 for values in assignments.values()):
                raise ValueError()
            values = assignments["CLOUDFLARE_API_TOKEN"] or assignments["CFTOKEN"]
            token = values[0] if len(values) == 1 else ""
        except (UnicodeError, ValueError):
            raise PublishError("Credential file must contain one literal CLOUDFLARE_API_TOKEN assignment (CFTOKEN alias accepted)") from None
    else:
        token = os.environ.get("CLOUDFLARE_API_TOKEN", "") or os.environ.get("CFTOKEN", "")
        if not token and sys.stdin.isatty():
            token = getpass.getpass("Cloudflare R2 API token (hidden): ")
    if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{20,512}", token):
        raise PublishError("Supply CLOUDFLARE_API_TOKEN through an existing environment, mounted credential file, or terminal prompt")
    return token


def derive_s3_credentials(token, config, http):
    url = "https://api.cloudflare.com/client/v4/accounts/" + config["account_id"] + "/tokens/verify"
    response = http.request("GET", url, headers={"Authorization": "Bearer " + token, "Accept-Encoding": "identity"})
    if response.status != 200:
        raise PublishError(f"Cloudflare token verification failed (HTTP {response.status})")
    verified = parse_json(response.body)
    result = verified.get("result") if isinstance(verified, dict) else None
    if (not isinstance(verified, dict) or verified.get("success") is not True or not isinstance(result, dict) or result.get("status") != "active"
            or not isinstance(result.get("id"), str) or not re.fullmatch(r"[0-9a-f]{32}", result["id"])):
        raise PublishError("Cloudflare did not verify an active account API token")
    return result["id"], hashlib.sha256(token.encode("ascii")).hexdigest()


def sign_s3(method, url, body, headers, access_key, secret_key, *, now=None, region="auto"):
    """Sign only an HTTPS S3 object URL without query parameters or redirects."""
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise PublishError("S3 signing requires an HTTPS object URL without query parameters")
    now = now or datetime.now(timezone.utc)
    timestamp = now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    day = timestamp[:8]
    payload_hash = hashlib.sha256(body or b"").hexdigest()
    signed = {key.lower(): " ".join(value.split()) for key, value in headers.items()}
    signed.update({"host": parsed.netloc, "x-amz-date": timestamp, "x-amz-content-sha256": payload_hash})
    names = ";".join(sorted(signed))
    canonical_headers = "".join(key + ":" + signed[key] + "\n" for key in sorted(signed))
    canonical = "\n".join((method, parsed.path or "/", "", canonical_headers, names, payload_hash))
    scope = day + "/" + region + "/s3/aws4_request"
    to_sign = "\n".join(("AWS4-HMAC-SHA256", timestamp, scope, hashlib.sha256(canonical.encode()).hexdigest()))
    key = ("AWS4" + secret_key).encode()
    for part in (day, region, "s3", "aws4_request"):
        key = hmac.new(key, part.encode(), hashlib.sha256).digest()
    signature = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
    signed["authorization"] = ("AWS4-HMAC-SHA256 Credential=" + access_key + "/" + scope
                                + ", SignedHeaders=" + names + ", Signature=" + signature)
    return signed


class R2:
    def __init__(self, config, access_key, secret_key, http):
        self.config, self.access_key, self.secret_key, self.http = config, access_key, secret_key, http

    def request(self, method, key, *, body=None, headers=None, limit=16384):
        # Keys have already been constrained to catalog or content-addressed map paths.
        url = ("https://" + self.config["account_id"] + ".r2.cloudflarestorage.com/"
               + self.config["bucket"] + "/" + quote(key, safe="/-_.~"))
        values = dict(headers or {})
        values["Accept-Encoding"] = "identity"
        if body is not None:
            values["Content-Length"] = str(len(body))
        signed = sign_s3(method, url, body, values, self.access_key, self.secret_key)
        return self.http.request(method, url, headers=signed, body=body, limit=limit)


def require_exact(response, data, label, *, catalog_pending=True):
    state = "; catalog was not advanced" if catalog_pending else "; catalog publication may already have completed"
    if response.status != 200:
        raise PublishError(f"{label} failed (HTTP {response.status})" + state)
    if len(response.body) != len(data) or hashlib.sha256(response.body).digest() != hashlib.sha256(data).digest():
        raise PublishError(label + " has different bytes" + state)


def publish(prepared, config, r2, http, *, progress=print):
    # Capture the current catalog before changing any object, then condition the
    # final write on that ETag. A competing publisher cannot be silently replaced.
    old = r2.request("GET", config["catalog_key"], limit=MAX_CATALOG_BYTES)
    if old.status == 404:
        condition = {"If-None-Match": "*"}
    elif old.status == 200 and re.fullmatch(r'"[A-Za-z0-9_-]{1,128}"', old.headers.get("etag", "")):
        condition = {"If-Match": old.headers["etag"]}
    else:
        raise PublishError(f"Cannot safely inspect the current catalog (HTTP {old.status})")
    for entry in prepared.maps:
        key = entry["object_key"]
        data = read_regular(prepared.directory / key, entry["file_bytes"])
        if len(data) != entry["file_bytes"] or hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise PublishError("Prepared map changed after validation; catalog was not advanced")
        existing = r2.request("GET", key, limit=len(data))
        if existing.status == 404:
            for attempt in range(1, 4):
                try:
                    result = r2.request("PUT", key, body=data, headers={"If-None-Match": "*",
                                        "Content-Type": "application/octet-stream",
                                        "Cache-Control": "public, max-age=31536000, immutable"})
                except PublishError:
                    # R2 may have stored the object before losing its response.
                    # Retry only after a definite 404, retaining create-only
                    # writes so a racing publisher's object is never replaced.
                    try:
                        existing = r2.request("GET", key, limit=len(data))
                        if existing.status == 404 and attempt < 3:
                            progress(f"Retrying immutable map {entry['id']} after missing readback (attempt {attempt + 1}/3)")
                            continue
                        require_exact(existing, data, "Immutable map " + entry["id"])
                    except PublishError:
                        raise PublishError(f"Immutable map {entry['id']} upload response failed and stored bytes could not be verified; catalog was not advanced") from None
                else:
                    if result.status not in (200, 201, 204, 409, 412):
                        raise PublishError(f"Immutable map upload failed (HTTP {result.status}); catalog was not advanced")
                    # A racing publisher's object is accepted only after exact read.
                    existing = r2.request("GET", key, limit=len(data))
                break
        require_exact(existing, data, "Immutable map " + entry["id"])
        public = http.request("GET", config["public_base_url"] + key,
                              headers={"Accept-Encoding": "identity", "Cache-Control": "no-cache"}, limit=len(data))
        require_exact(public, data, "Public map " + entry["id"])
        progress("Verified public map " + entry["id"] + " (" + str(len(data)) + " bytes, SHA-256 " + entry["sha256"] + ")")
    if old.status != 200 or old.body != prepared.catalog:
        result = r2.request("PUT", config["catalog_key"], body=prepared.catalog,
                            headers={**condition, "Content-Type": "application/json", "Cache-Control": "no-cache"})
        if result.status in (409, 412):
            raise PublishError("Current catalog changed during publication; it was not overwritten. Validate and retry")
        if result.status not in (200, 201, 204):
            raise PublishError(f"Catalog publication failed (HTTP {result.status})")
    private = r2.request("GET", config["catalog_key"], limit=MAX_CATALOG_BYTES)
    require_exact(private, prepared.catalog, "Published catalog", catalog_pending=False)
    public = http.request("GET", config["public_base_url"] + config["catalog_key"],
                          headers={"Accept-Encoding": "identity", "Cache-Control": "no-cache"}, limit=MAX_CATALOG_BYTES)
    # At this point the mutable catalog may already be published. Do not imply a
    # failed public read automatically rolled it back or removed immutable maps.
    if public.status != 200 or public.body != prepared.catalog:
        raise PublishError(f"R2 catalog matches prepared bytes but exact public verification failed (HTTP {public.status}); inspect CDN caching before retrying")
    progress("Published and verified " + config["public_base_url"] + config["catalog_key"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared", type=Path, required=True, help="Explicit directory produced by map_catalog.py")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="Nonsecret publisher configuration")
    parser.add_argument("--credential-file", type=Path, help="Existing mounted file containing a literal CLOUDFLARE_API_TOKEN assignment")
    parser.add_argument("--publish", action="store_true", help="Upload and advance testing/current.json after verification")
    args = parser.parse_args()
    try:
        config = load_config(args.config)
        prepared = validate_prepared(args.prepared, config)
        print("Validated " + str(len(prepared.maps)) + " maps for " + config["bucket"] + "/" + config["catalog_key"])
        if not args.publish:
            print("Local validation only; no credentials read or network requests made. Add --publish to upload.")
            return
        token = load_token(args.credential_file)
        http = HTTPS()
        access, secret = derive_s3_credentials(token, config, http)
        del token
        publish(prepared, config, R2(config, access, secret, http), http)
    except (PublishError, OSError, ValueError):
        # Only our deliberately safe errors are printed. Raw library exceptions
        # and file parsing errors can include credentials or remote request data.
        error = sys.exc_info()[1]
        message = str(error) if isinstance(error, PublishError) else "Local input could not be read or validated"
        parser.exit(1, "Map publication failed: " + message + "\n")


if __name__ == "__main__":
    main()
