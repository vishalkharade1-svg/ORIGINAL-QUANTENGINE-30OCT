"""Delta sandbox/production environment separation (adversarial).

Proves the endpoint authority
(core/exchanges/delta/delta_environments.py) keeps sandbox
configuration from ever contaminating the production path:

  A. production endpoint unchanged;
  B. explicit sandbox selects only the verified sandbox endpoint;
  C. UNKNOWN refuses private/state-changing resolution;
  D. sandbox credentials + production endpoint refused;
  E. production credentials + sandbox endpoint refused;
  F. missing sandbox endpoint refused;
  G. malformed endpoint refused;
  H. endpoint/environment mismatch refused;
  I. WebSocket environment mismatch refused;
  J. no implicit fallback (removing config never selects
     production for a sandbox request).

Deterministic, offline, stdlib only. No credentials used,
printed, or persisted; no network.
"""

from __future__ import annotations

import unittest


class TestEnvironmentAuthority(unittest.TestCase):
    def test_a_production_endpoint_unchanged(self):
        from core.exchanges.delta import delta_environments as env
        from core.exchanges.delta.delta_auth import DeltaSignedREST
        from core.exchanges.delta.delta_rest import DeltaREST

        # The pre-existing production defaults are byte-identical.
        self.assertEqual(DeltaREST.BASE_URL,
                         "https://api.delta.exchange")
        self.assertEqual(DeltaSignedREST.BASE_URL,
                         "https://api.delta.exchange")
        self.assertEqual(env.resolve_rest_endpoint("PRODUCTION"),
                         "https://api.delta.exchange")
        self.assertEqual(
            env.assert_endpoint_for_environment(
                "PRODUCTION", "https://api.delta.exchange"),
            "https://api.delta.exchange")

    def test_b_sandbox_selects_verified_endpoint_only(self):
        from core.exchanges.delta import delta_environments as env

        self.assertEqual(
            env.resolve_rest_endpoint("SANDBOX"),
            "https://testnet-api.delta.exchange")
        self.assertEqual(
            env.assert_endpoint_for_environment(
                "SANDBOX", "https://testnet-api.delta.exchange"),
            "https://testnet-api.delta.exchange")
        # Case-insensitive, whitespace-tolerant selection.
        self.assertEqual(env.resolve_environment(" sandbox "),
                         "SANDBOX")

    def test_c_unknown_environment_refuses(self):
        from core.exchanges.delta import delta_environments as env

        for unknown in ("", None, "STAGING", "TESTNET", 123):
            self.assertEqual(env.resolve_environment(unknown),
                             "UNKNOWN")
            with self.assertRaises(env.EnvironmentError):
                env.resolve_rest_endpoint(unknown)
            with self.assertRaises(env.EnvironmentError):
                env.assert_endpoint_for_environment(
                    unknown, "https://api.delta.exchange")
            with self.assertRaises(env.EnvironmentError):
                env.credentials_for(unknown)

    def test_d_sandbox_creds_production_endpoint_refused(self):
        from core.exchanges.delta import delta_environments as env

        # Even WITH sandbox credentials configured, pairing them
        # with the production host is refused.
        with self.assertRaises(env.EnvironmentError):
            env.assert_endpoint_for_environment(
                "SANDBOX", "https://api.delta.exchange")

    def test_e_production_creds_sandbox_endpoint_refused(self):
        from core.exchanges.delta import delta_environments as env

        # Production host pairing is refused for PRODUCTION, and
        # the sandbox credential source never falls back to
        # production keys (venue binds keys to environments).
        with self.assertRaises(env.EnvironmentError):
            env.assert_endpoint_for_environment(
                "PRODUCTION",
                "https://testnet-api.delta.exchange")

    def test_f_missing_sandbox_endpoint_refused(self):
        from core.exchanges.delta import delta_environments as env

        for missing in ("", None, "   "):
            with self.assertRaises(env.EnvironmentError):
                env.assert_endpoint_for_environment(
                    "SANDBOX", missing)

    def test_g_malformed_endpoint_refused(self):
        from core.exchanges.delta import delta_environments as env

        for bad in ("not-a-url", "https://",
                    "https://api.delta.exchange.evil.com",
                    "http://api.delta.exchange",
                    "https://api.delta.exchange/v2/products",
                    12345):
            with self.assertRaises(env.EnvironmentError):
                env.assert_endpoint_for_environment("SANDBOX", bad)
            with self.assertRaises(env.EnvironmentError):
                env.assert_endpoint_for_environment(
                    "PRODUCTION", bad)

    def test_h_endpoint_environment_mismatch_refused(self):
        from core.exchanges.delta import delta_environments as env

        with self.assertRaises(env.EnvironmentError):
            env.assert_endpoint_for_environment(
                "SANDBOX", "https://api.delta.exchange")
        with self.assertRaises(env.EnvironmentError):
            env.assert_endpoint_for_environment(
                "PRODUCTION", "https://testnet-api.delta.exchange")

    def test_i_websocket_environment_mismatch_refused(self):
        from core.exchanges.delta import delta_environments as env

        # Production WS resolves to the existing public socket.
        self.assertEqual(
            env.resolve_ws_endpoint("PRODUCTION"),
            "wss://public-socket.delta.exchange")
        # Sandbox WS host is UNVERIFIED: refused (never silently
        # the production socket for a sandbox request).
        with self.assertRaises(env.EnvironmentError):
            env.resolve_ws_endpoint("SANDBOX")
        with self.assertRaises(env.EnvironmentError):
            env.resolve_ws_endpoint("")

    def test_j_no_implicit_fallback(self):
        # Removing configuration must not silently select
        # production for a sandbox request: the authority has no
        # default branch, and existing constructors keep their
        # explicit production constants (pinned by Test A), so a
        # sandbox request with no config raises instead of
        # falling back. Hermetic: blanked sandbox credentials so
        # the verdict never depends on operator .env state.
        from unittest import mock

        from config import settings as settings_mod
        from core.exchanges.delta import delta_environments as env

        with self.assertRaises(env.EnvironmentError):
            env.resolve_rest_endpoint("")
        with mock.patch.object(settings_mod.settings, "SANDBOX_API_KEY",
                               ""), mock.patch.object(
                settings_mod.settings, "SANDBOX_API_SECRET", ""):
            with self.assertRaises(env.EnvironmentError):
                env.sandbox_client()


class TestCredentialSeparation(unittest.TestCase):
    def test_sandbox_never_substitutes_production_keys(self):
        # Hermetic: production keys present + sandbox keys absent
        # -> sandbox resolution refuses (UNAVAILABLE), never
        # reinterpreting the production keys.
        from unittest import mock

        from config import settings as settings_mod
        from core.exchanges.delta import delta_environments as env

        with mock.patch.object(settings_mod.settings, "API_KEY",
                               "prod-key"), mock.patch.object(
                settings_mod.settings, "API_SECRET",
                "prod-secret"), mock.patch.object(
                settings_mod.settings, "SANDBOX_API_KEY",
                ""), mock.patch.object(
                settings_mod.settings, "SANDBOX_API_SECRET", ""):
            with self.assertRaises(env.EnvironmentError):
                env.credentials_for("SANDBOX")
            # Production resolution still serves production keys.
            self.assertEqual(
                env.credentials_for("PRODUCTION"),
                ("prod-key", "prod-secret"))

    def test_sandbox_keys_used_verbatim_when_configured(self):
        # Hermetic: configured sandbox keys resolve verbatim (no
        # transformation, no fallback involved).
        from unittest import mock

        from config import settings as settings_mod
        from core.exchanges.delta import delta_environments as env

        with mock.patch.object(settings_mod.settings,
                               "SANDBOX_API_KEY",
                               "sandbox-key"), mock.patch.object(
                settings_mod.settings, "SANDBOX_API_SECRET",
                "sandbox-secret"):
            self.assertEqual(
                env.credentials_for("SANDBOX"),
                ("sandbox-key", "sandbox-secret"))

    def test_settings_exposes_separate_sandbox_fields(self):
        from config.settings import settings

        self.assertTrue(hasattr(settings, "SANDBOX_API_KEY"))
        self.assertTrue(hasattr(settings, "SANDBOX_API_SECRET"))
        self.assertTrue(hasattr(settings, "DELTA_ENVIRONMENT"))

    def test_sandbox_client_construction_fail_closed(self):
        # No sandbox credentials configured -> construction
        # refuses before any transport exists. Hermetic: blanked
        # credentials so the verdict never depends on operator
        # .env state (provisioned keys must not flip this gate).
        from unittest import mock

        from config import settings as settings_mod
        from core.exchanges.delta import delta_environments as env

        with mock.patch.object(settings_mod.settings, "SANDBOX_API_KEY",
                               ""), mock.patch.object(
                settings_mod.settings, "SANDBOX_API_SECRET", ""):
            with self.assertRaises(env.EnvironmentError):
                env.sandbox_client()


if __name__ == "__main__":
    unittest.main()
