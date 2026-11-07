import json
import tempfile
import unittest
from pathlib import Path

from core.risk.trading_policy import TradingPolicy, TradingPolicyManager


class TestTradingPolicy(unittest.TestCase):
    def test_default_bounds_and_trailing(self):
        p = TradingPolicy()
        self.assertEqual(p.min_rr, 1.0)
        self.assertEqual(p.max_rr, 20.0)
        self.assertTrue(p.trailing_enabled)
        self.assertEqual(p.trailing_activation_r, 1.0)
        self.assertEqual(p.trailing_distance_r, 0.5)

    def test_bounds_fail_closed(self):
        with self.assertRaises(ValueError):
            TradingPolicy(min_rr=0.99).validate()
        with self.assertRaises(ValueError):
            TradingPolicy(max_rr=20.01).validate()
        with self.assertRaises(ValueError):
            TradingPolicy(min_rr=10, max_rr=5).validate()

    def test_exact_instrument_override_wins_and_persists(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "policy.json"
            m = TradingPolicyManager(path)
            m.set_global({"min_rr": 1.0, "max_rr": 20.0,
                          "trailing_enabled": True,
                          "trailing_activation_r": 1.0,
                          "trailing_distance_r": 0.5,
                          "auto_exit_on_opposite_signal": True})
            m.set_instrument("BTCUSDT", {"min_rr": 2.0, "max_rr": 8.0,
                          "trailing_enabled": True,
                          "trailing_activation_r": 1.5,
                          "trailing_distance_r": 0.75,
                          "auto_exit_on_opposite_signal": True})
            self.assertEqual(m.get("BTCUSDT").min_rr, 2.0)
            self.assertEqual(m.get("ETHUSDT").min_rr, 1.0)
            m2 = TradingPolicyManager(path)
            self.assertEqual(m2.get("btcusdt").max_rr, 8.0)
            payload = json.loads(path.read_text())
            self.assertEqual(list(payload["instruments"]), ["BTCUSDT"])

    def test_symbol_formatting_normalizes_without_conflating_quote_assets(self):
        with tempfile.TemporaryDirectory() as td:
            m = TradingPolicyManager(Path(td) / "policy.json")
            m.set_instrument("BTC-USD", {"min_rr": 3.0, "max_rr": 9.0})
            self.assertEqual(m.get("BTC/USD").min_rr, 3.0)
            self.assertEqual(m.get("BTC_USD").max_rr, 9.0)
            # Different quote assets are different instruments, not aliases.
            self.assertEqual(m.get("BTCUSDT").min_rr, 1.0)
            self.assertEqual(m.get("DELTA:BTCUSD").min_rr, 1.0)

    def test_duplicate_normalized_persisted_keys_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "policy.json"
            values = {
                "min_rr": 2.0, "max_rr": 10.0,
                "trailing_enabled": True,
                "trailing_activation_r": 1.0,
                "trailing_distance_r": 0.5,
                "auto_exit_on_opposite_signal": True,
            }
            path.write_text(json.dumps({
                "global": {},
                "instruments": {"BTC-USD": values, "BTC/USD": values},
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "invalid persisted trading policy"):
                TradingPolicyManager(path)

    def test_reset_returns_to_global(self):
        with tempfile.TemporaryDirectory() as td:
            m = TradingPolicyManager(Path(td) / "policy.json")
            values = {"min_rr": 3.0, "max_rr": 10.0,
                      "trailing_enabled": True,
                      "trailing_activation_r": 1.0,
                      "trailing_distance_r": 0.5,
                      "auto_exit_on_opposite_signal": True}
            m.set_global(values)
            m.set_instrument("NIFTY", values)
            m.reset_instrument("NIFTY")
            self.assertEqual(m.get("NIFTY").min_rr, 3.0)

    def test_default_path_is_repo_anchored_not_cwd(self):
        import os
        from core.risk import trading_policy as tp_mod
        self.assertTrue(os.path.isabs(str(tp_mod._POLICY_PATH)))
        repo_root = Path(tp_mod.__file__).resolve().parents[2]
        self.assertEqual(tp_mod._POLICY_PATH,
                         repo_root / "data" / "runtime" /
                         "risk_policy_overrides.json")
        # From any working directory, a default manager resolves
        # the same repo-anchored file (read-only construction).
        previous = os.getcwd()
        with tempfile.TemporaryDirectory() as td:
            os.chdir(td)
            try:
                manager = TradingPolicyManager()
                self.assertEqual(manager.path, tp_mod._POLICY_PATH)
                self.assertTrue(manager.get("ANY").min_rr >= 1.0)
            finally:
                os.chdir(previous)

class TestTradingPolicyRuntime(unittest.TestCase):
    def test_instrument_minimum_is_enforced_by_risk_engine(self):
        from types import SimpleNamespace
        from core.market_state import MarketState
        from core.pipeline.pipeline_context import PipelineContext
        from core.risk.account_state import AccountState
        from core.risk.risk_engine import RiskEngine
        from core.setup.setup_candidate import SetupCandidate
        from core.risk.trading_policy import trading_policy_manager

        manager = trading_policy_manager()
        before = manager.snapshot()
        try:
            manager.set_instrument("POLICYTEST", {
                "min_rr": 5.0, "max_rr": 10.0,
                "trailing_enabled": True,
                "trailing_activation_r": 1.0,
                "trailing_distance_r": 0.5,
                "auto_exit_on_opposite_signal": True,
            })
            c = SetupCandidate(direction="BULLISH", entry=100, stop_loss=90,
                               take_profit=140, risk_reward=4.0,
                               confidence=90, score=90,
                               trend=SimpleNamespace(direction="BULLISH"),
                               regime=SimpleNamespace(score=90))
            ctx = PipelineContext()
            ctx.market = MarketState(symbol="POLICYTEST", timeframe="1m")
            ctx.account = AccountState(starting_balance=10000, balance=10000,
                                       equity=10000, peak_equity=10000)
            ctx.execution_signal = c
            RiskEngine().analyze(ctx)
            self.assertIsNone(ctx.order)
        finally:
            manager.set_global(before["global"])
            for key in list(manager.snapshot()["instruments"]):
                manager.reset_instrument(key)
            for key, values in before["instruments"].items():
                manager.set_instrument(key, values)

    def test_fixed_target_trade_receives_trailing_management(self):
        from types import SimpleNamespace
        from core.market_state import MarketState
        from core.pipeline.pipeline_context import PipelineContext
        from core.risk.account_state import AccountState
        from core.risk.risk_engine import RiskEngine
        from core.setup.setup_candidate import SetupCandidate

        c = SetupCandidate(direction="BULLISH", entry=100, stop_loss=90,
                           take_profit=160, risk_reward=6.0,
                           confidence=90, score=90,
                           trend=SimpleNamespace(direction="BULLISH"),
                           regime=SimpleNamespace(score=90))
        ctx = PipelineContext()
        ctx.market = MarketState(symbol="POLICYDEFAULT", timeframe="1m")
        ctx.account = AccountState(starting_balance=10000, balance=10000,
                                   equity=10000, peak_equity=10000)
        ctx.execution_signal = c
        RiskEngine().analyze(ctx)
        self.assertIsNotNone(ctx.order)
        self.assertEqual(ctx.order.exit_mode, "TRAILING_STOP")
        self.assertTrue(ctx.order.trailing_enabled)
        self.assertEqual(ctx.order.trailing_activation_r, 1.0)
        self.assertEqual(ctx.order.trailing_distance_r, 0.5)
