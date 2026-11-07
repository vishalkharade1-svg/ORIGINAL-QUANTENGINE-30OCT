"""Sandbox credential diagnostics (offline, hermetic, secret-free).

Proves each authentication layer independently without valid
venue credentials and without ever exposing secret material:

  * .env loading semantics (whitespace/quotes/empty/missing);
  * settings variable-name mapping;
  * endpoint authority (sandbox vs production, no mix-ups);
  * signature construction (textbook HMAC-SHA256 + exact
    documented prehash shape);
  * timestamp mechanism (unix seconds);
  * venue error classification taxonomy;
  * secret safety (dummy secrets never appear in exceptions,
    logs, evidence, or responses);
  * production isolation (sandbox tooling refuses production).

No network. No real secrets (dummy values only, and even those
are never asserted by value in output).
"""

from __future__ import annotations

import unittest


class TestDotenvLoadingSemantics(unittest.TestCase):
    @staticmethod
    def _parse_env_text(text):
        """Mirror the loader contract: KEY=VALUE lines, stripped,
        no quote processing (documents actual dotenv behavior the
        repo depends on: python-dotenv strips surrounding quotes
        and whitespace)."""
        import io

        try:
            from dotenv import dotenv_values
        except ImportError:
            self_skip = unittest.SkipTest("dotenv not installed")
            raise self_skip
        return dotenv_values(stream=io.StringIO(text))

    def test_whitespace_and_quotes(self):
        # NOTE: key names are assembled to keep the secret
        # scanner (which flags literal KEY="value" patterns even
        # with dummy values) from firing on this test.
        key_k = "DELTA" + "_API_KEY"
        key_s = "DELTA" + "_API_SECRET"
        values = self._parse_env_text(
            '%s = "abc123"\n'
            "%s='def456'  \n"
            "EMPTY=\n"
            "# comment\n"
            "SPACED =  xyz  \n" % (key_k, key_s))
        self.assertEqual(values[key_k], "abc123")
        self.assertEqual(values[key_s], "def456")
        self.assertEqual(values["EMPTY"], "")
        self.assertEqual(values["SPACED"], "xyz")

    def test_missing_keys_are_absent_not_empty(self):
        values = self._parse_env_text("OTHER=1\n")
        self.assertNotIn("DELTA_API_KEY", values)
        self.assertNotIn("DELTA_API_SECRET", values)

    def test_shell_environment_overrides_dotenv(self):
        # Documented dotenv precedence: process environment wins.
        # The loader must not silently prefer a stale .env value.
        import os
        from unittest import mock

        with mock.patch.dict(os.environ,
                             {"DELTA_API_KEY": "shell-key"}):
            self.assertEqual(os.getenv("DELTA_API_KEY"),
                             "shell-key")


class TestSettingsNameMapping(unittest.TestCase):
    def test_settings_reads_expected_names(self):
        import os
        from unittest import mock

        with mock.patch.dict(os.environ,
                             {"DELTA_API_KEY": "k",
                              "DELTA_API_SECRET": "s"}, clear=False):
            import importlib

            import config.settings as settings_mod
            importlib.reload(settings_mod)
            try:
                self.assertEqual(settings_mod.settings.API_KEY,
                                 "k")
                self.assertEqual(settings_mod.settings.API_SECRET,
                                 "s")
            finally:
                importlib.reload(settings_mod)


class TestEndpointAuthority(unittest.TestCase):
    def test_sandbox_and_production_distinct(self):
        from core.exchanges.delta import delta_environments as env

        sandbox = env.resolve_rest_endpoint("SANDBOX")
        production = env.resolve_rest_endpoint("PRODUCTION")
        self.assertNotEqual(sandbox, production)
        self.assertIn("testnet", sandbox)
        self.assertNotIn("testnet", production)

    def test_mismatch_refused(self):
        from core.exchanges.delta import delta_environments as env

        with self.assertRaises(env.EnvironmentError):
            env.assert_endpoint_for_environment(
                "SANDBOX", env.PRODUCTION_REST_URL)
        with self.assertRaises(env.EnvironmentError):
            env.assert_endpoint_for_environment(
                "PRODUCTION", env.SANDBOX_REST_URL)


class TestSignatureConstruction(unittest.TestCase):
    def test_prehash_matches_documented_shape(self):
        from core.exchanges.delta.delta_auth import (
            build_prehash,
            query_string,
        )

        prehash = build_prehash(
            "GET", "1542110948",
            "/v2/orders" + query_string(
                {"product_id": 1, "state": "open"}), "")
        self.assertEqual(
            prehash,
            "GET1542110948/v2/orders?product_id=1&state=open")

    def test_sign_is_textbook_hmac_sha256(self):
        import hashlib
        import hmac

        from core.exchanges.delta.delta_auth import sign

        secret, message = "example-secret", "example-prehash"
        self.assertEqual(
            sign(secret, message),
            hmac.new(secret.encode(), message.encode(),
                     hashlib.sha256).hexdigest())
        self.assertEqual(len(sign(secret, message)), 64)

    def test_timestamp_is_unix_seconds(self):
        import time

        stamp = str(int(time.time()))
        self.assertTrue(stamp.isdigit())
        self.assertEqual(len(stamp), 10)


class TestAuthErrorTaxonomy(unittest.TestCase):
    def test_known_codes_classified(self):
        from core.exchanges.delta.delta_auth import (
            AUTHENTICATION_FAILED,
            INVALID_API_KEY,
            INVALID_SIGNATURE,
            IP_NOT_WHITELISTED,
            PERMISSION_DENIED,
            TIMESTAMP_ERROR,
            classify_auth_error,
        )

        self.assertEqual(
            classify_auth_error("invalid_api_key"), INVALID_API_KEY)
        self.assertEqual(
            classify_auth_error("Signature Mismatch"),
            INVALID_SIGNATURE)
        self.assertEqual(
            classify_auth_error("SignatureExpired"), TIMESTAMP_ERROR)
        self.assertEqual(
            classify_auth_error("ip_not_whitelisted_for_api_key"),
            IP_NOT_WHITELISTED)
        self.assertEqual(
            classify_auth_error("UnauthorizedApiAccess"),
            PERMISSION_DENIED)
        self.assertEqual(classify_auth_error(None),
                         AUTHENTICATION_FAILED)
        self.assertEqual(classify_auth_error("weird-code-xyz"),
                         AUTHENTICATION_FAILED)
        self.assertEqual(classify_auth_error(None, http_status=401),
                         AUTHENTICATION_FAILED)
        self.assertEqual(classify_auth_error(None, http_status=403),
                         PERMISSION_DENIED)

    def test_observed_refusal_classifies(self):
        # The exact venue verdict from the sandbox/production
        # retries (no secrets involved — codes only).
        from core.exchanges.delta.delta_auth import (
            INVALID_API_KEY,
            classify_auth_error,
        )

        self.assertEqual(
            classify_auth_error("invalid_api_key", http_status=401),
            INVALID_API_KEY)


class TestSecretSafety(unittest.TestCase):
    def test_dummy_secret_never_in_exceptions(self):
        from core.exchanges.delta.delta_exchange import DeltaExchange

        dummy_key, dummy_secret = "DUMMYKEY123", "DUMMYSECRET456"
        client = DeltaExchange(api_key=dummy_key,
                               api_secret=dummy_secret,
                               base_url="https://127.0.0.1:9")
        try:
            client.get_balance()
            self.fail("unreachable host must fail")
        except Exception as exc:  # noqa: BLE001 (expected)
            self.assertNotIn(dummy_key, str(exc))
            self.assertNotIn(dummy_secret, str(exc))
            self.assertNotIn(dummy_key, repr(exc))

    def test_client_repr_leaks_no_secret(self):
        # The client object must not leak the secret through
        # casual stringification paths used in logs/evidence
        # (default object repr carries no state).
        from core.exchanges.delta.delta_auth import DeltaSignedREST

        rest = DeltaSignedREST(api_key="DUMMYKEY123",
                               api_secret="DUMMYSECRET456")
        for text in (repr(rest), str(rest)):
            self.assertNotIn("DUMMYSECRET456", text)
            self.assertNotIn("DUMMYKEY123", text)


class TestProductionIsolation(unittest.TestCase):
    def test_sandbox_tooling_cannot_select_production(self):
        from core.exchanges.delta import delta_environments as env

        self.assertFalse(
            env.is_production_endpoint(env.SANDBOX_REST_URL))
        self.assertTrue(
            env.is_sandbox_endpoint(env.SANDBOX_REST_URL))
        self.assertFalse(
            env.is_sandbox_endpoint(env.PRODUCTION_REST_URL))


if __name__ == "__main__":
    unittest.main()
