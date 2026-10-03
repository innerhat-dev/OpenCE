"""Offline publication tests: immutable bytes, public verification, races and secrets."""
import contextlib
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

from tools import map_catalog
from tools import publish_map_catalog as publisher
from tools.test_map_catalog import synthetic_map


class FakeHTTPS:
    def __init__(self, config):
        self.config = config
        self.objects = {}
        self.requests = []
        self.public_bad = {}
        self.race = None
        self.token_result = {"success": True, "result": {"id": "b" * 32, "status": "active"}}
        self.token_status = 200

    def request(self, method, url, *, headers=None, body=None, limit=16384):
        headers = {key.lower(): value for key, value in (headers or {}).items()}
        self.requests.append((method, url, headers, body))
        parsed = urlsplit(url)
        if parsed.hostname == "api.cloudflare.com":
            return publisher.Response(self.token_status, {}, json.dumps(self.token_result).encode())
        if parsed.hostname.endswith(".r2.cloudflarestorage.com"):
            self_assert = headers.get("authorization", "")
            if not self_assert.startswith("AWS4-HMAC-SHA256 "):
                raise AssertionError("S3 request was not signed")
            key = parsed.path.split("/", 2)[2]
            if method == "PUT":
                if self.race:
                    callback, self.race = self.race, None
                    callback(key, self.objects)
                if "if-none-match" in headers:
                    if headers["if-none-match"] != "*":
                        raise AssertionError("unexpected immutable condition")
                    if key in self.objects:
                        return publisher.Response(412, {}, b"")
                elif "if-match" in headers:
                    if key not in self.objects or headers["if-match"] != self.etag(self.objects[key]):
                        return publisher.Response(412, {}, b"")
                else:
                    raise AssertionError("unconditional object replacement")
                self.objects[key] = body
                return publisher.Response(200, {"etag": self.etag(body)}, b"")
            if key not in self.objects:
                return publisher.Response(404, {}, b"")
            return publisher.Response(200, {"etag": self.etag(self.objects[key])}, self.objects[key])
        if parsed.hostname == urlsplit(self.config["public_base_url"]).hostname:
            if "authorization" in headers:
                raise AssertionError("credential sent to public origin")
            key = parsed.path.lstrip("/")
            if key in self.public_bad:
                return self.public_bad[key]
            return publisher.Response(200 if key in self.objects else 404, {}, self.objects.get(key, b""))
        raise AssertionError("unexpected origin")

    @staticmethod
    def etag(data):
        return '"' + hashlib.md5(data).hexdigest() + '"'


class PublisherTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "Downrush.map"
        self.data = synthetic_map(self.source)
        self.directory = self.root / "prepared"
        map_catalog.prepare_catalog([self.source], self.directory, ["downrush"])
        self.config = publisher.load_config()
        self.prepared = publisher.validate_prepared(self.directory, self.config)
        self.entry = self.prepared.maps[0]
        self.key = self.entry["object_key"]
        self.catalog_key = self.config["catalog_key"]
        self.http = FakeHTTPS(self.config)
        self.r2 = publisher.R2(self.config, "b" * 32, "c" * 64, self.http)
        self.progress = []

    def publish(self):
        publisher.publish(self.prepared, self.config, self.r2, self.http, progress=self.progress.append)

    def writes(self):
        return [item for item in self.http.requests if item[0] == "PUT"]

    def test_new_object_is_conditional_and_public_hash_verified_before_catalog(self):
        self.publish()
        writes = self.writes()
        self.assertEqual(len(writes), 2)
        self.assertTrue(writes[0][1].endswith("/" + self.key))
        self.assertEqual(writes[0][2]["if-none-match"], "*")
        self.assertIn("if-none-match", writes[0][2]["authorization"].split("SignedHeaders=")[1].split(",")[0])
        self.assertEqual(writes[0][2]["x-amz-content-sha256"], self.entry["sha256"])
        self.assertEqual(writes[0][3], self.data)
        self.assertEqual(writes[1][2]["if-none-match"], "*")
        public_map = self.config["public_base_url"] + self.key
        map_index = next(i for i, item in enumerate(self.http.requests) if item[1] == public_map)
        catalog_index = self.http.requests.index(writes[1])
        self.assertLess(map_index, catalog_index)
        self.assertEqual(self.http.objects[self.catalog_key], self.prepared.catalog)
        self.assertIn("Published and verified", self.progress[-1])

    def test_identical_existing_map_is_never_rewritten_and_catalog_uses_etag(self):
        self.http.objects[self.key] = self.data
        old_catalog = b'{"previous":true}\n'
        self.http.objects[self.catalog_key] = old_catalog
        self.publish()
        self.assertEqual(len(self.writes()), 1)
        self.assertEqual(self.writes()[0][2]["if-match"], FakeHTTPS.etag(old_catalog))
        self.assertEqual(self.http.objects[self.key], self.data)
        self.http.requests.clear()
        self.publish()
        self.assertEqual(self.writes(), [])

    def test_different_immutable_bytes_and_public_mismatch_never_advance_catalog(self):
        for public in (False, True):
            with self.subTest(public=public):
                self.http.objects.clear()
                self.http.requests.clear()
                self.http.public_bad.clear()
                self.http.objects[self.catalog_key] = b"previous"
                if public:
                    self.http.objects[self.key] = self.data
                    self.http.public_bad[self.key] = publisher.Response(200, {}, self.data[:-1] + b"X")
                else:
                    self.http.objects[self.key] = self.data[:-1] + b"X"
                with self.assertRaisesRegex(publisher.PublishError, "different bytes"):
                    self.publish()
                self.assertEqual(self.writes(), [])
                self.assertEqual(self.http.objects[self.catalog_key], b"previous")

    def test_racing_immutable_create_only_accepts_exact_same_bytes(self):
        for same in (False, True):
            with self.subTest(same=same):
                self.http.objects.clear()
                self.http.requests.clear()
                raced = self.data if same else self.data[:-1] + b"X"
                self.http.race = lambda key, objects: objects.update({key: raced})
                if same:
                    self.publish()
                    self.assertEqual(self.http.objects[self.catalog_key], self.prepared.catalog)
                else:
                    with self.assertRaisesRegex(publisher.PublishError, "different bytes"):
                        self.publish()
                    self.assertNotIn(self.catalog_key, self.http.objects)
                self.assertEqual(self.http.objects[self.key], raced)

    def test_racing_catalog_writer_is_preserved(self):
        self.http.objects[self.key] = self.data
        self.http.objects[self.catalog_key] = b"old"
        self.http.race = lambda key, objects: objects.update({key: b"competing catalog"})
        with self.assertRaisesRegex(publisher.PublishError, "changed during publication"):
            self.publish()
        self.assertEqual(self.http.objects[self.catalog_key], b"competing catalog")

    def lose_map_put_response(self, after_store=None):
        request = self.http.request
        def lost_response(method, url, **kwargs):
            result = request(method, url, **kwargs)
            if method == "PUT" and url.endswith("/" + self.key):
                if after_store:
                    after_store()
                raise publisher.PublishError("private lost-response fixture marker")
            return result
        return patch.object(self.http, "request", side_effect=lost_response)

    def test_lost_map_put_response_accepts_exact_stored_bytes_without_rewriting(self):
        self.http.objects[self.catalog_key] = b"previous"
        with self.lose_map_put_response():
            self.publish()
        writes = self.writes()
        self.assertEqual(len(writes), 2)
        self.assertEqual(writes[0][2]["if-none-match"], "*")
        self.assertEqual(writes[1][2]["if-match"], FakeHTTPS.etag(b"previous"))
        self.assertEqual(self.http.objects[self.key], self.data)
        self.assertEqual(self.http.objects[self.catalog_key], self.prepared.catalog)
        map_write = self.http.requests.index(writes[0])
        recovered_read, public_read = self.http.requests[map_write + 1:map_write + 3]
        self.assertEqual(recovered_read[0], "GET")
        self.assertTrue(recovered_read[1].endswith("/" + self.key))
        self.assertEqual(public_read[1], self.config["public_base_url"] + self.key)
        self.assertLess(self.http.requests.index(public_read), self.http.requests.index(writes[1]))

    def test_lost_map_put_response_unverified_read_never_advances_catalog(self):
        for failure in ("short", "wrong-hash", "http-error", "read-error"):
            with self.subTest(failure=failure):
                self.http.objects = {self.catalog_key: b"previous"}
                self.http.requests.clear()
                def change_stored_object():
                    if failure == "short":
                        self.http.objects[self.key] = self.data[:-1]
                    elif failure == "wrong-hash":
                        self.http.objects[self.key] = self.data[:-1] + b"X"
                request = self.r2.request
                def failed_read(method, key, **kwargs):
                    if method == "GET" and key == self.key and self.writes():
                        if failure == "http-error":
                            return publisher.Response(503, {}, b"")
                        if failure == "read-error":
                            raise publisher.PublishError("private read-response fixture marker")
                    return request(method, key, **kwargs)
                with self.lose_map_put_response(change_stored_object), patch.object(self.r2, "request", side_effect=failed_read):
                    with self.assertRaisesRegex(publisher.PublishError, "stored bytes could not be verified; catalog was not advanced") as error:
                        self.publish()
                self.assertNotIn("private", str(error.exception))
                self.assertEqual(len(self.writes()), 1)
                self.assertEqual(self.http.objects[self.catalog_key], b"previous")
                self.assertFalse(any(url == self.config["public_base_url"] + self.key for _, url, _, _ in self.http.requests))

    def test_missing_readback_retries_only_conditional_map_put_until_exact_success(self):
        def initially_missing():
            if len(self.writes()) < 3:
                self.http.objects.pop(self.key)
        with self.lose_map_put_response(initially_missing):
            self.publish()
        map_writes = [item for item in self.writes() if item[1].endswith("/" + self.key)]
        self.assertEqual(len(map_writes), 3)
        self.assertTrue(all(item[2]["if-none-match"] == "*" and item[3] == self.data for item in map_writes))
        self.assertEqual(self.http.objects[self.catalog_key], self.prepared.catalog)
        self.assertEqual(self.progress[:2], [
            "Retrying immutable map downrush after missing readback (attempt 2/3)",
            "Retrying immutable map downrush after missing readback (attempt 3/3)"])

    def test_persistently_missing_lost_put_readback_is_bounded_at_three_attempts(self):
        self.http.objects[self.catalog_key] = b"previous"
        with self.lose_map_put_response(lambda: self.http.objects.pop(self.key)):
            with self.assertRaisesRegex(publisher.PublishError, "catalog was not advanced") as error:
                self.publish()
        self.assertEqual(len(self.writes()), 3)
        self.assertTrue(all(item[2]["if-none-match"] == "*" and item[1].endswith("/" + self.key) for item in self.writes()))
        self.assertEqual(len(self.progress), 2)
        self.assertNotIn("private", str(error.exception))
        self.assertEqual(self.http.objects[self.catalog_key], b"previous")

    def test_map_retry_preserves_a_racing_object_and_requires_its_exact_bytes(self):
        for same in (False, True):
            with self.subTest(same=same):
                self.http.objects = {self.catalog_key: b"previous"}
                self.http.requests.clear()
                self.progress.clear()
                raced = self.data if same else self.data[:-1] + b"X"
                request = self.http.request
                def lost_once(method, url, **kwargs):
                    response = request(method, url, **kwargs)
                    if method == "PUT" and url.endswith("/" + self.key) and len(self.writes()) == 1:
                        self.http.objects.pop(self.key)
                        self.http.race = lambda key, objects: objects.update({key: raced})
                        raise publisher.PublishError("private lost-response fixture marker")
                    return response
                with patch.object(self.http, "request", side_effect=lost_once):
                    if same:
                        self.publish()
                    else:
                        with self.assertRaisesRegex(publisher.PublishError, "different bytes"):
                            self.publish()
                map_writes = [item for item in self.writes() if item[1].endswith("/" + self.key)]
                self.assertEqual(len(map_writes), 2)
                self.assertTrue(all(item[2]["if-none-match"] == "*" for item in map_writes))
                self.assertEqual(self.http.objects[self.key], raced)
                self.assertEqual(self.http.objects[self.catalog_key], self.prepared.catalog if same else b"previous")

    def test_lost_map_put_response_still_requires_public_bytes_and_catalog_etag(self):
        for failure in ("public", "catalog-race"):
            with self.subTest(failure=failure):
                self.http.objects = {self.catalog_key: b"previous"}
                self.http.requests.clear()
                self.http.public_bad.clear()
                if failure == "public":
                    self.http.public_bad[self.key] = publisher.Response(200, {}, self.data[:-1] + b"X")
                def race():
                    if failure == "catalog-race":
                        self.http.objects[self.catalog_key] = b"competing catalog"
                with self.lose_map_put_response(race), self.assertRaises(publisher.PublishError):
                    self.publish()
                self.assertEqual(self.http.objects[self.catalog_key], b"previous" if failure == "public" else b"competing catalog")
                self.assertEqual(len(self.writes()), 1 if failure == "public" else 2)

    def test_lost_catalog_put_response_is_never_retried_or_recovered(self):
        request = self.http.request
        def lost_response(method, url, **kwargs):
            result = request(method, url, **kwargs)
            if method == "PUT" and url.endswith("/" + self.catalog_key):
                raise publisher.PublishError("HTTPS request failed; credentials and remote error text were suppressed")
            return result
        with patch.object(self.http, "request", side_effect=lost_response), self.assertRaises(publisher.PublishError):
            self.publish()
        self.assertEqual(len(self.writes()), 2)
        self.assertEqual(self.http.requests[-1], self.writes()[-1])
        self.assertEqual(self.http.objects[self.catalog_key], self.prepared.catalog)

    def test_public_failure_after_catalog_write_reports_partial_publication(self):
        self.http.public_bad[self.catalog_key] = publisher.Response(404, {}, b"")
        with self.assertRaisesRegex(publisher.PublishError, "R2 catalog matches.*public verification failed"):
            self.publish()
        self.assertEqual(self.http.objects[self.catalog_key], self.prepared.catalog)
        self.assertEqual(self.http.objects[self.key], self.data)

    def test_private_read_failure_after_catalog_write_does_not_claim_rollback(self):
        request = self.r2.request
        def unavailable_after_write(method, key, **kwargs):
            if method == "GET" and key == self.catalog_key and key in self.http.objects:
                return publisher.Response(503, {}, b"")
            return request(method, key, **kwargs)
        with patch.object(self.r2, "request", side_effect=unavailable_after_write):
            with self.assertRaisesRegex(publisher.PublishError, "publication may already have completed"):
                self.publish()
        self.assertEqual(self.http.objects[self.catalog_key], self.prepared.catalog)

    def test_prepared_inventory_hash_and_scope_are_checked_before_network(self):
        catalog_path = self.directory / "catalog.json"
        original = catalog_path.read_bytes()
        for mutation in ("extra", "symlink", "hash", "id", "duplicate-key", "unexpected-field", "boolean-size"):
            with self.subTest(mutation=mutation):
                catalog_path.write_bytes(original)
                extra = self.directory / "extra"
                if mutation == "extra":
                    extra.write_text("unlisted")
                elif mutation == "symlink":
                    extra.symlink_to(self.source)
                elif mutation == "duplicate-key":
                    catalog_path.write_bytes(original.replace(b'"schema_version": 1', b'"schema_version": 1, "schema_version": 1'))
                else:
                    catalog = json.loads(original)
                    entry = catalog["maps"][0]
                    if mutation == "hash":
                        (self.directory / self.key).write_bytes(self.data[:-1] + b"X")
                    elif mutation == "id":
                        entry["id"] = "unapproved"
                    elif mutation == "unexpected-field":
                        entry["token"] = "unknown"
                    elif mutation == "boolean-size":
                        entry["file_bytes"] = True
                    catalog_path.write_text(json.dumps(catalog))
                with self.assertRaises(publisher.PublishError):
                    publisher.validate_prepared(self.directory, self.config)
                self.assertEqual(self.http.requests, [])
                if extra.exists() or extra.is_symlink():
                    extra.unlink()
                (self.directory / self.key).write_bytes(self.data)

    def test_changed_local_object_after_validation_cannot_be_uploaded(self):
        (self.directory / self.key).write_bytes(self.data[:-1] + b"X")
        with self.assertRaisesRegex(publisher.PublishError, "changed after validation"):
            self.publish()
        self.assertEqual(self.writes(), [])

    def test_cloudflare_active_token_is_verified_and_secret_derived_in_memory(self):
        token = "example_R2_token_for_offline_test"
        access, secret = publisher.derive_s3_credentials(token, self.config, self.http)
        self.assertEqual(access, "b" * 32)
        self.assertEqual(secret, hashlib.sha256(token.encode()).hexdigest())
        self.assertEqual(self.http.requests[0][1], "https://api.cloudflare.com/client/v4/accounts/" + self.config["account_id"] + "/tokens/verify")
        for value in (["unexpected"], {"success": False}, {"success": True, "result": {"id": "b" * 32, "status": "expired"}}):
            self.http.token_result = value
            with self.subTest(value=value), self.assertRaises(publisher.PublishError):
                publisher.derive_s3_credentials(token, self.config, self.http)

    def test_existing_credential_file_and_hidden_prompt_do_not_execute_shell(self):
        token = "example_R2_token_for_offline_test"
        credential = self.root / "mounted.env"
        credential.write_text("IGNORED=unchanged\nexport CFTOKEN='" + token + "'\n")
        self.assertEqual(publisher.load_token(credential), token)
        credential.write_text("IGNORED=unchanged\nexport CLOUDFLARE_API_TOKEN='" + token + "'\n")
        self.assertEqual(publisher.load_token(credential), token)
        for text in ("CFTOKEN=$(touch danger)\n", "CFTOKEN=\n", "CFTOKEN=" + token + "\nCFTOKEN=" + token):
            credential.write_text(text)
            with self.assertRaises(publisher.PublishError):
                publisher.load_token(credential)
        with patch.dict(os.environ, {"CLOUDFLARE_API_TOKEN": token, "CFTOKEN": "older_alias_token_value"}, clear=True):
            self.assertEqual(publisher.load_token(), token)
        with patch.dict(os.environ, {}, clear=True), patch.object(publisher.sys.stdin, "isatty", return_value=True), patch.object(publisher.getpass, "getpass", return_value=token) as prompt:
            self.assertEqual(publisher.load_token(), token)
            prompt.assert_called_once()

    def test_local_validation_default_reads_no_credentials_and_makes_no_requests(self):
        with patch.object(publisher.sys, "argv", ["publisher", "--prepared", str(self.directory)]), patch.object(publisher, "load_token") as token, patch.object(publisher, "HTTPS") as http, contextlib.redirect_stdout(io.StringIO()) as output:
            publisher.main()
        token.assert_not_called()
        http.assert_not_called()
        self.assertIn("no credentials read or network requests", output.getvalue())

    def test_signature_matches_aws_s3_reference_and_binds_conditional_put(self):
        # AWS's official example: https://docs.aws.amazon.com/AmazonS3/latest/
        # developerguide/sig-v4-header-based-auth.html (Example: GET Object).
        now = datetime(2013, 5, 24, tzinfo=timezone.utc)
        signed = publisher.sign_s3("GET", "https://examplebucket.s3.amazonaws.com/test.txt", None,
                                  {"Range": "bytes=0-9"}, "AKIAIOSFODNN7EXAMPLE",
                                  "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", now=now, region="us-east-1")
        self.assertTrue(signed["authorization"].endswith("Signature=f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41"))
        url = "https://" + self.config["account_id"] + ".r2.cloudflarestorage.com/halo/" + self.key
        first = publisher.sign_s3("PUT", url, self.data, {"If-None-Match": "*"}, "b" * 32, "c" * 64, now=now)
        second = publisher.sign_s3("PUT", url, self.data, {"If-Match": '"other"'}, "b" * 32, "c" * 64, now=now)
        self.assertNotEqual(first["authorization"], second["authorization"])
        self.assertIn("/auto/s3/aws4_request", first["authorization"])

    def test_network_errors_are_redacted_and_redirects_are_refused(self):
        http = publisher.HTTPS()
        with patch.object(http.opener, "open", side_effect=OSError("private token must never appear")) as transport:
            with self.assertRaises(publisher.PublishError) as error:
                http.request("GET", "https://api.cloudflare.com/", headers={"Authorization": "Bearer private_token"})
        self.assertNotIn("private", str(error.exception))
        request = transport.call_args.args[0]
        self.assertEqual(request.get_header("User-agent"), "Halo-OG-map-publisher/1")
        self.assertIsNone(publisher.NoRedirect().redirect_request(None, None, 302, "redirect", {}, "https://other.test/"))
        with self.assertRaises(publisher.PublishError):
            http.request("GET", "http://insecure.test/")

    def test_large_put_timeout_is_bounded_and_error_remains_redacted(self):
        http = publisher.HTTPS()
        with patch.object(http.opener, "open", side_effect=TimeoutError("private lost-response marker")) as transport:
            with self.assertRaises(publisher.PublishError) as error:
                http.request("PUT", "https://example.test/map", headers={"If-None-Match": "*"}, body=b"x" * (1024 * 1024 + 1))
        self.assertNotIn("private", str(error.exception))
        self.assertEqual(transport.call_args.kwargs["timeout"], 60)
        self.assertEqual(transport.call_args.args[0].get_header("If-none-match"), "*")


if __name__ == "__main__":
    unittest.main()
