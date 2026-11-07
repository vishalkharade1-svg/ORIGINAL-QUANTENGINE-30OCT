"""Delta MCP adapter safety contract, based on current Delta MCP docs."""
from __future__ import annotations

import unittest


class TestDeltaMcpAdapter(unittest.TestCase):
    def test_documented_environments(self):
        from research.integrations.delta_mcp import normalize_environment
        self.assertEqual(normalize_environment("india_testnet"), "india_testnet")
        self.assertEqual(normalize_environment(" INDIA_PROD "), "india_prod")
        for bad in ("", None, "testnet", "SANDBOX", "production"):
            with self.assertRaises(ValueError):
                normalize_environment(bad)

    def test_keyless_command_is_testnet_by_default(self):
        from research.integrations.delta_mcp import server_command
        self.assertEqual(server_command(), ("uvx", "delta-exchange-mcp"))
        from research.integrations.delta_mcp import server_environment
        self.assertEqual(server_environment(), {"DELTA_MCP_ENV": "india_testnet"})

    def test_public_tool_allowlist(self):
        from research.integrations.delta_mcp import assert_public_tool
        self.assertEqual(assert_public_tool("get_ticker"), "get_ticker")
        self.assertEqual(assert_public_tool("get_orderbook"), "get_orderbook")
        for bad in ("place_order", "cancel_order", "close_all_positions", "edit_order"):
            with self.assertRaises(ValueError):
                assert_public_tool(bad)

    def test_trading_mode_fails_closed(self):
        from research.integrations.delta_mcp import assert_no_trading_authority
        assert_no_trading_authority(trading_mode=False)
        assert_no_trading_authority(trading_mode="false")
        for bad in (True, "true", "1", "trade"):
            with self.assertRaises(ValueError):
                assert_no_trading_authority(trading_mode=bad)

    def test_profile_contains_no_secret(self):
        from research.integrations.delta_mcp import McpConnectionProfile
        profile = McpConnectionProfile("india_testnet")
        self.assertEqual(profile.environment, "india_testnet")
        self.assertFalse(profile.credentials_configured)
        self.assertFalse(hasattr(profile, "api_key"))
        self.assertFalse(hasattr(profile, "api_secret"))


if __name__ == "__main__":
    unittest.main()
