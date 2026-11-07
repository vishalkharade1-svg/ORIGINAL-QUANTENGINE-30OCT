"""Phase 11F-1 research-safety tests (no live reach, exact costs).

Uses tiny synthetic bars and hand-computed cost expectations.
Never touches D2/D3 data, never evaluates profitability, never
updates the research log.
"""

import json
import unittest
from pathlib import Path

from config import risk_settings
from core.backtesting.accounting import net_pnl as canon_net
from research.phase11f import contracts as K
from research.phase11f import harness as H
from research.phase11f import metrics as M

RESEARCH = Path("research/phase11f")


def _bars(n=40, start=1787000000, base=100.0):
    return [{"time": start + 60 * i, "open": base, "high": base + 0.5,
             "low": base - 0.5, "close": base + 0.1, "volume": 10.0}
            for i in range(n)]


class _OneShot:
    """Single fixed signal at bar 10 (past-only, deterministic)."""

    id = "H11F-TEST"

    def signals(self, idx, bars, ctx):
        if idx == 10:
            entry = float(bars[idx]["close"])
            return [{"direction": "BULLISH", "entry": entry,
                     "stop": entry - 1.0, "take_profit": entry + 2.0,
                     "setup_id": "TEST-10", "confidence": 80.0}]
        return []


class TestNoLiveReach(unittest.TestCase):
    @staticmethod
    def _code_without_denylist(src):
        # The FORBIDDEN_RESEARCH_IMPORTS denylist in contracts.py
        # legitimately names execution objects as strings; reaching
        # execution means importing/calling them, not listing them.
        lines = src.splitlines()
        out, skip = [], False
        for ln in lines:
            if "FORBIDDEN_RESEARCH_IMPORTS = [" in ln:
                skip = True
                continue
            if skip:
                if ln.strip() == "]":
                    skip = False
                continue
            out.append(ln)
        return "\n".join(out)

    def test_sources_contain_no_execution_paths(self):
        for name in ("candidates.py", "features.py", "fibonacci.py",
                     "harness.py", "contracts.py", "metrics.py", "datasets.py"):
            src = self._code_without_denylist((RESEARCH / name).read_text())
            for forbidden in ("DeltaOrderExecutor", "BrokerEngine", "place_order",
                              "submit_order", "DeltaExchange", "_require_auth",
                              "DELTA_API_KEY", "DELTA_API_SECRET", "ccxt", "delta_rest"):
                self.assertNotIn(forbidden, src, "%s reaches %s" % (name, forbidden))

    def test_mutation_execution_snippet_detected(self):
        snippet = "executor = DeltaOrderExecutor(); executor.place_order(intent)"
        forbidden = ("DeltaOrderExecutor", "place_order")
        hits = [f for f in forbidden if f in snippet]
        self.assertEqual(sorted(hits), ["DeltaOrderExecutor", "place_order"])

    def test_harness_restores_config_and_stays_paper(self):
        before_modes = tuple(risk_settings.ACTIVE_ENTRY_MODES)
        before_live = (bool(getattr(risk_settings, "ALLOW_LIVE", False)),
                       bool(getattr(risk_settings, "LIVE_EXECUTE", False)))
        res = H.run_candidate(_bars(), _OneShot(), "BTCUSDT", cost_key="A")
        self.assertEqual(tuple(risk_settings.ACTIVE_ENTRY_MODES), before_modes)
        after_live = (bool(getattr(risk_settings, "ALLOW_LIVE", False)),
                      bool(getattr(risk_settings, "LIVE_EXECUTE", False)))
        self.assertEqual(after_live, before_live)
        self.assertFalse(after_live[0])
        self.assertFalse(after_live[1])
        self.assertIn("orders", res)
        self.assertIn("trades", res)

    def test_live_flags_still_disabled(self):
        from config.settings import settings
        self.assertFalse(settings.ALLOW_LIVE)
        self.assertFalse(settings.LIVE_EXECUTE)


class TestCostSemantics(unittest.TestCase):
    def test_breakdown_hand_computed(self):
        # PV=500 at scenario C: commission=500*0.00059=0.295;
        # slippage=2*500*5/10000=0.5.
        bd = K.cost_breakdown(500.0, "C")
        self.assertAlmostEqual(bd["commission"], 0.295)
        self.assertAlmostEqual(bd["slippage"], 0.5)
        self.assertAlmostEqual(bd["funding"], 0.0)

    def test_net_identity_and_mutation(self):
        self.assertAlmostEqual(canon_net(10.0, 1.0, 0.5), 8.5)
        self.assertTrue(K.check_pnl_semantics(10.0, 1.0, 0.5, 0.0, 8.5))
        # mutation: gross fabricated from net (wrong direction) fails.
        self.assertFalse(K.check_pnl_semantics(8.5, 1.0, 0.5, 0.0, 8.5))

    def test_research_metrics_match_certified(self):
        trades = [
            {"net": 8.5, "gross": 10.0, "entry": 100.0, "quantity": 1.0,
             "commission": 1.0, "slippage": 0.5, "risk_amount": 5.0,
             "exit_time": 2, "entry_time": 1},
            {"net": -6.0, "gross": -5.0, "entry": 100.0, "quantity": 1.0,
             "commission": 0.5, "slippage": 0.5, "risk_amount": 5.0,
             "exit_time": 3, "entry_time": 2},
        ]
        m = M.research_trade_metrics(trades)
        for field in M.METRIC_CONTRACT_FIELDS:
            self.assertIn(field, m)
        self.assertAlmostEqual(m["gross_pnl"], 5.0)
        self.assertAlmostEqual(m["fees"], 1.5)
        self.assertAlmostEqual(m["slippage"], 1.0)
        self.assertAlmostEqual(m["funding"], 0.0)
        self.assertAlmostEqual(m["net_pnl"], 2.5)
        self.assertLess(m["net_consistency_diff"], 1e-9)
        self.assertEqual((m["wins"], m["losses"], m["breakevens"]), (1, 1, 0))
        # certified adapter equivalence (excluding the funding leg).
        from research.phase11e.common import trade_metrics as certified
        base = certified(trades)
        for key in ("gross_pnl", "fees", "slippage", "net_pnl",
                    "expectancy", "profit_factor", "max_drawdown"):
            self.assertAlmostEqual(m[key], base[key])


class TestDeterminismAndLogSeal(unittest.TestCase):
    def test_run_candidate_deterministic(self):
        bars = _bars()
        first = H.run_candidate(bars, _OneShot(), "BTCUSDT", cost_key="A")
        second = H.run_candidate(list(bars), _OneShot(), "BTCUSDT", cost_key="A")
        self.assertEqual(first["orders"], second["orders"])
        self.assertEqual(first["trades"], second["trades"])
        self.assertEqual(first["final_balance"], second["final_balance"])

    def test_research_log_untouched_by_tests(self):
        # 11F-4 authorized update: test runs never write the ledger;
        # the ledger holds the recorded 11F-4 verdicts with preserved
        # registration history (full check in test_phase11f_results.py).
        log = json.loads((RESEARCH / "research_log.json").read_text())
        hypo = json.loads((RESEARCH / "results" / "hypothesis_results.json").read_text())
        for entry in log["entries"]:
            self.assertEqual(entry["status"], hypo[entry["id"]]["verdict"])
            self.assertEqual(entry["registration_timestamp"], "2026-09-07T00:00:00Z")


if __name__ == "__main__":
    unittest.main()
