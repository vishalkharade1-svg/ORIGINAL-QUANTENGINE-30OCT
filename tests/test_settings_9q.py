"""
Phase 9Q-12 — Settings type safety.
Every config value must have declared type, parser, default, validation.
"""

import os
import unittest
from unittest.mock import patch


class TestSettingsParsing(unittest.TestCase):

    def _reload_settings(self, env):
        with patch.dict(os.environ, env, clear=False):
            # Need to reimport settings module
            import importlib
            import config.settings as mod
            importlib.reload(mod)
            return mod.settings

    def test_min_quote_volume_float(self):
        s = self._reload_settings({"MIN_QUOTE_VOLUME_24H": "1234.5"})
        self.assertAlmostEqual(s.MIN_QUOTE_VOLUME_24H, 1234.5)
        self.assertIsInstance(s.MIN_QUOTE_VOLUME_24H, float)

    def test_min_quote_volume_none_when_empty(self):
        s = self._reload_settings({"MIN_QUOTE_VOLUME_24H": ""})
        self.assertIsNone(s.MIN_QUOTE_VOLUME_24H)

    def test_min_quote_volume_none_when_unset(self):
        env = os.environ.copy()
        env.pop("MIN_QUOTE_VOLUME_24H", None)
        with patch.dict(os.environ, env, clear=True):
            import importlib
            import config.settings as mod
            # Need to handle that patch clear removes all env, but load_dotenv may set defaults
            # Instead test via direct helper
            from config.settings import _env_float
            self.assertIsNone(_env_float("MIN_QUOTE_VOLUME_24H", None))

    def test_min_history_bars_int(self):
        s = self._reload_settings({"MIN_HISTORY_BARS": "100"})
        self.assertEqual(s.MIN_HISTORY_BARS, 100)
        self.assertIsInstance(s.MIN_HISTORY_BARS, int)

    def test_min_history_bars_none_when_empty(self):
        s = self._reload_settings({"MIN_HISTORY_BARS": ""})
        self.assertIsNone(s.MIN_HISTORY_BARS)

    def test_invalid_float_raises(self):
        with self.assertRaises(ValueError):
            self._reload_settings({"MIN_QUOTE_VOLUME_24H": "not_a_number"})

    def test_invalid_int_raises(self):
        with self.assertRaises(ValueError):
            self._reload_settings({"MIN_HISTORY_BARS": "12.3.4"})

    def test_invalid_int_with_text_raises(self):
        with self.assertRaises(ValueError):
            self._reload_settings({"MIN_HISTORY_BARS": "abc"})

    def test_provider_lookback_default(self):
        # Unset should default to 7
        env = {"PROVIDER_HISTORY_LOOKBACK_DAYS": ""}
        s = self._reload_settings(env)
        self.assertEqual(s.PROVIDER_HISTORY_LOOKBACK_DAYS, 7)

    def test_provider_lookback_int(self):
        s = self._reload_settings({"PROVIDER_HISTORY_LOOKBACK_DAYS": "14"})
        self.assertEqual(s.PROVIDER_HISTORY_LOOKBACK_DAYS, 14)

    def test_control_api_port_is_int(self):
        from config.settings import settings
        self.assertIsInstance(settings.CONTROL_API_PORT, int)
        self.assertIsInstance(settings.CONTROL_API_POLL_SECONDS, float)

    def test_remote_gateway_port_is_int(self):
        from config.settings import settings
        self.assertIsInstance(settings.REMOTE_GATEWAY_PORT, int)
