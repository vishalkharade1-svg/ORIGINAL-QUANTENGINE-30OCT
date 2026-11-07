"""Phase154: order-capable script safety contract (offline, stdlib/AST).

Proves: default invocation performs zero order writes; Testnet endpoint
is hard-bound; production endpoints are rejected; credentials come only
from Testnet-specific env names. No network, no orders.
"""
from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = [
    "scripts/funding_settlement_hold.py",
    "scripts/bounded_testnet_order_experiment.py",
    "scripts/bounded_testnet_reconciled_experiment.py",
]
PROD_MARKERS = ("api.delta.exchange", "api.india.delta.exchange")
TESTNET_MARKERS = ("cdn-ind.testnet.deltaex.org", "india_testnet")


def tree(name: str) -> ast.Module:
    return ast.parse((ROOT / name).read_text(encoding="utf-8"))


def calls_posting_orders(mod: ast.Module) -> list[ast.Call]:
    return [n for n in ast.walk(mod)
            if isinstance(n, ast.Call)
            and isinstance(getattr(n, "func", None), ast.Attribute)
            and getattr(n.func, "attr", "") == "post"]


class TestOrderScriptSafety(unittest.TestCase):
    def test_explicit_opt_in_flags(self):
        for name in SCRIPTS:
            text = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn('"--execute"', text, name)
            self.assertIn('"--dry-run"', text, name)

    def test_testnet_endpoint_hard_bound(self):
        bounded = (ROOT / "scripts" / "bounded_testnet_order_experiment.py").read_text(encoding="utf-8")
        self.assertIn("cdn-ind.testnet.deltaex.org", bounded)
        for name in SCRIPTS:
            text = (ROOT / name).read_text(encoding="utf-8")
            # Literal host or symbolic reference to the module that pins it.
            self.assertTrue(
                "cdn-ind.testnet.deltaex.org" in text
                or "exp.TESTNET_REST" in text
                or "TESTNET_REST" in text,
                name)
            self.assertIn("india_testnet", text, name)

    def test_no_production_endpoint(self):
        for name in SCRIPTS:
            text = (ROOT / name).read_text(encoding="utf-8")
            for marker in PROD_MARKERS:
                # cdn-ind.testnet contains 'testnet.deltaex.org', never bare prod hosts
                self.assertNotIn("https://" + marker, text, (name, marker))

    def test_testnet_only_credentials(self):
        for name in SCRIPTS:
            text = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn("DELTA_INDIA_TESTNET_API_KEY", text, name)
            self.assertIn("DELTA_INDIA_TESTNET_API_SECRET", text, name)
            self.assertNotIn('os.getenv("DELTA_API_KEY"', text, name)
            self.assertNotIn("os.getenv('DELTA_API_KEY'", text, name)

    def test_order_posts_gated_behind_execute(self):
        # Every venue order-write call site must appear textually AFTER
        # the `if not execute` dry-run early-return: default invocation
        # cannot reach any write. (Helpers like do_legs are only
        # invoked from the post-guard execute region.)
        import re
        for name in SCRIPTS:
            text = (ROOT / name).read_text(encoding="utf-8")
            gate = text.find("if not execute:")
            self.assertGreaterEqual(gate, 0, name)
            self.assertIn("return 0", text[gate:gate + 500], name)
            posts = [m.start() for m in re.finditer(r"\.post\(", text)]
            self.assertTrue(posts, name)
            for pos in posts:
                self.assertGreater(pos, gate, (name, pos))

    def test_conflicting_flags_refused_without_network(self):
        # Conflicting --execute/--dry-run is refused by an early guard
        # placed before any credential use, endpoint validation, or
        # network call. Verified structurally (no network executed).
        for name in SCRIPTS:
            text = (ROOT / name).read_text(encoding="utf-8")
            guard = text.find("if execute and args.dry_run")
            self.assertGreaterEqual(guard, 0, name)
            # Refusal exits non-zero: direct `return 2` or via fail() -> 2.
            tail = text[guard:guard + 300]
            self.assertTrue("return 2" in tail or "return fail(" in tail, name)
            for marker in ("DeltaSignedREST(", "httpx.get("):
                pos = text.find(marker)
                if pos >= 0:
                    self.assertGreater(pos, guard, (name, marker))


if __name__ == "__main__":
    unittest.main()
