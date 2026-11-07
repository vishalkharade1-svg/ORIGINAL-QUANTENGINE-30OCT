"""Delta MCP configuration safety boundary for this task.

Stdlib-only. The repository's default MCP configuration must be
testnet-safe: it may select the testnet environment, but it must
never carry credential material (real or placeholder) and must
never select production for this evidence workflow. Key material,
when the operator provisions it, lives in the operator/MCP secret
configuration (client secret storage or the shared
~/.delta-exchange-mcp/config.env file) -- never in this repository.

No QuantEngine production path may consume MCP configuration.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MCP_CONFIG = REPO_ROOT / ".vscode" / "mcp.json"

SAFE_ENVS = ("india_testnet",)

FORBIDDEN_ENV_KEYS = (
    "DELTA_API_KEY",
    "DELTA_API_SECRET",
    "DELTA_MCP_DEBUG_FILE",
)


def _load_config():
    return json.loads(MCP_CONFIG.read_text(encoding="utf-8"))


def _env_blocks(config):
    servers = config.get("servers", {})
    blocks = []
    for name, server in servers.items():
        if "delta" in str(name).lower():
            env = (server or {}).get("env", {})
            if isinstance(env, dict):
                blocks.append(env)
    return blocks


class TestMcpConfigTestnetSafe(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = _load_config()
        cls.envs = _env_blocks(cls.config)

    def test_config_exists_with_delta_server(self):
        self.assertTrue(self.envs, "no delta MCP env block found")

    def test_environment_is_testnet(self):
        for env in self.envs:
            self.assertIn(env.get("DELTA_MCP_ENV"), SAFE_ENVS)

    def test_no_production_environment_selected(self):
        text = json.dumps(self.envs).lower()
        self.assertNotIn("prod", text)

    def test_no_credential_material(self):
        for env in self.envs:
            for key in FORBIDDEN_ENV_KEYS:
                self.assertNotIn(key, env)
            for key, value in env.items():
                lowered = key.lower()
                self.assertNotIn("key", lowered)
                self.assertNotIn("secret", lowered)
                if isinstance(value, str):
                    self.assertNotIn("your-api", value.lower())

    def test_trading_tools_not_required(self):
        # The evidence workflow uses keyless public tools plus the
        # setup connection-status tool; nothing here may demand a
        # trading-capable key.
        for env in self.envs:
            for key in env:
                self.assertNotIn("trad", key.lower())


class TestMcpConfigNotConsumedByProduction(unittest.TestCase):
    def test_no_production_module_reads_mcp_config(self):
        offenders = []
        for path in list((REPO_ROOT / "core").rglob("*.py")) + list(
                (REPO_ROOT / "config").rglob("*.py")):
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            if "mcp.json" in text or "DELTA_MCP_ENV" in text:
                offenders.append(str(path.relative_to(REPO_ROOT)))
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
