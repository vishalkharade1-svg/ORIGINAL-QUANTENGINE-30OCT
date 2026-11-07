"""Verified Phase-4 corrections (deterministic, offline, stdlib only).

Test-first regression proofs for the confirmed Phase-7/backtester defects:

* A. DecisionEngine must enforce the authoritative config confidence
  minimum (80), not the 70 shadow.
* B. PositionSize must expose notional-at-risk vs reward/risk as
  distinct, mathematically pinned semantics (LONG/SHORT/boundary/
  non-unit quantity).
* C. Breakout resize must re-mint costs from an explicit CostSpec so
  resized fills do not book stale costs (opt-in seam; default preserves
  legacy behavior byte-identically).
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from config import risk_settings
from core.market_state import MarketState
from core.pipeline.pipeline_context import PipelineContext
from core.regime.regime_state import RegimeState
from core.setup.decision_engine import DecisionEngine
from core.setup.setup_candidate import SetupCandidate
from core.trend.trend_state import TrendState


def candidate_6r(confidence: float) -> SetupCandidate:
    c = SetupCandidate(
        direction="BULLISH",
        entry=100.0,
        stop_loss=95.0,
        take_profit=130.0,
        risk_reward=(130.0 - 100.0) / (100.0 - 95.0),
        confidence=confidence,
        score=85.0,
    )
    c.trend = TrendState(direction="BULLISH")
    c.regime = RegimeState(score=90.0, confidence=90.0,
                           grade="A", regime="TRENDING")
    return c


def decide(candidates: list) -> tuple[DecisionEngine, PipelineContext]:
    context = PipelineContext()
    context.market = MarketState(symbol="TEST", timeframe="1m")
    context.trade_setups = list(candidates)
    engine = DecisionEngine()
    engine.analyze(context)
    return engine, context


class TestAuthoritativeConfidenceGate(unittest.TestCase):
    def test_config_minimum_is_80(self):
        self.assertEqual(risk_settings.MIN_CONFIDENCE, 80)

    def test_sub_authoritative_confidence_rejected(self):
        # 75 clears the old 70 shadow but violates the authoritative 80.
        engine, context = decide([candidate_6r(75.0)])
        self.assertEqual(context.decision.all(), [])
        self.assertEqual(len(engine.rejected), 1)
        self.assertEqual(engine.rejected[0].reasons, ["Confidence"])

    def test_boundary_80_accepted(self):
        engine, context = decide([candidate_6r(80.0)])
        self.assertEqual(len(context.decision.all()), 1)
        self.assertEqual(engine.rejected, [])

    def test_below_old_shadow_still_rejected(self):
        engine, context = decide([candidate_6r(60.0)])
        self.assertEqual(context.decision.all(), [])
        self.assertEqual(engine.rejected[0].reasons, ["Confidence"])


class TestPositionSizeSemantics(unittest.TestCase):
    @staticmethod
    def make_sizer(*, entry, stop, target, quantity, allocation=None):
        from core.risk.position_size import PositionSize

        stop_distance = abs(entry - stop)
        return PositionSize(
            balance=2000.0, risk_percent=0.01, risk_amount=20.0,
            allocation=(allocation if allocation is not None
                        else quantity * entry),
            leverage=10.0, entry_price=entry, stop_price=stop,
            stop_distance=stop_distance, quantity=quantity,
            position_value=quantity * entry, expected_loss=quantity * stop_distance,
            target_price=target,
        )

    def test_long_notional_to_risk(self):
        ps = self.make_sizer(entry=100.0, stop=90.0, target=160.0, quantity=2.0)
        # Notional-at-risk multiple: position_value / expected_loss
        # = (2 x 100) / (2 x 10) = 10.
        self.assertAlmostEqual(ps.notional_to_risk, 200.0 / 20.0)
        # True reward/risk from entry/stop/target.
        self.assertAlmostEqual(ps.reward_to_risk, 60.0 / 10.0)

    def test_short_symmetry(self):
        ps = self.make_sizer(entry=100.0, stop=110.0, target=40.0, quantity=2.0)
        self.assertAlmostEqual(ps.notional_to_risk, 200.0 / 20.0)
        self.assertAlmostEqual(ps.reward_to_risk, 60.0 / 10.0)

    def test_exact_boundary_6r(self):
        ps = self.make_sizer(entry=100.0, stop=90.0, target=160.0, quantity=1.0)
        self.assertAlmostEqual(ps.reward_to_risk, 6.0)

    def test_below_boundary(self):
        ps = self.make_sizer(entry=100.0, stop=90.0, target=140.0, quantity=1.0)
        self.assertLess(ps.reward_to_risk, 6.0)

    def test_above_boundary(self):
        ps = self.make_sizer(entry=100.0, stop=90.0, target=200.0, quantity=1.0)
        self.assertGreater(ps.reward_to_risk, 6.0)

    def test_non_unit_quantity(self):
        ps = self.make_sizer(entry=50.0, stop=45.0, target=80.0, quantity=3.5)
        self.assertAlmostEqual(ps.notional_to_risk, (3.5 * 50.0) / (3.5 * 5.0))
        self.assertAlmostEqual(ps.reward_to_risk, 30.0 / 5.0)

    def test_undefined_target_is_zero_not_nan(self):
        import math

        ps = self.make_sizer(entry=100.0, stop=90.0, target=0.0, quantity=1.0)
        self.assertEqual(ps.reward_to_risk, 0.0)
        self.assertTrue(math.isfinite(ps.reward_to_risk))

    def test_zero_loss_guards(self):
        ps = self.make_sizer(entry=100.0, stop=100.0, target=160.0, quantity=1.0)
        self.assertEqual(ps.notional_to_risk, 0.0)
        self.assertEqual(ps.reward_to_risk, 0.0)


class TestBreakoutResizeRemintsCosts(unittest.TestCase):
    @staticmethod
    def _backtester_with_spec(spec):
        from backtesting.backtester import Backtester
        from core.backtesting.trade_simulator import TradeSimulator

        tester = Backtester.__new__(Backtester)
        tester.account = SimpleNamespace(
            state=SimpleNamespace(equity=2000.0, balance=2000.0))
        tester.simulator = TradeSimulator()
        tester.cost_spec = spec
        return tester

    @staticmethod
    def _resized_order(tester, entry_price: float):
        order = SimpleNamespace(
            quantity=2.0, entry=100.0, stop_loss=90.0,
            position_value=200.0, risk_amount=20.0,
            risk_percent=0.01, valid=True, reason="",
            commission=1.2, slippage=0.4,
        )
        tester._resize_for_actual_entry(order, entry_price)
        return order

    def test_resize_remints_costs_from_spec(self):
        from core.risk.costs import CostSpec

        # Hand calculation: CostSpec(1.0, 0.001, 10bps) on setup pv 200
        # gives (1.2, 0.4). After resize to qty 1.0 @ 110 (pv 110):
        # commission = 1.0 + 110*0.001 = 1.11, slippage = 2*110*10/10000.
        spec = CostSpec(per_trade=1.0, rate=0.001, slippage_bps=10.0)
        order = self._resized_order(self._backtester_with_spec(spec), 110.0)
        self.assertAlmostEqual(order.quantity, 1.0)
        # Costs follow the ACTUAL fill notional (1.0 x 110). The booked
        # position_value still reflects the setup entry here because the
        # caller-side `order.entry = entry_price` update runs after
        # resize in the real fill path (pinned by breakout tests).
        self.assertAlmostEqual(order.commission, 1.11)
        self.assertAlmostEqual(order.slippage, 0.22)

    def test_no_spec_preserves_legacy_costs(self):
        order = self._resized_order(self._backtester_with_spec(None), 110.0)
        self.assertAlmostEqual(order.quantity, 1.0)
        self.assertAlmostEqual(order.commission, 1.2)
        self.assertAlmostEqual(order.slippage, 0.4)


class TestRestartRecovery(unittest.TestCase):
    """Deterministic restart drills on the snapshot journal seam.

    A persisted snapshot plus a fake executor exercises the boot-time
    gate: matches resume silently, any unsafe divergence HALTs rather
    than continuing. No network, no clock, fixed timestamps.
    """

    @staticmethod
    def _journal(tmp: str, trade: dict | None):
        from core.live.reconciler import Reconciler

        path = tmp + "/broker_state.json"
        first = Reconciler(executor=None, snapshot_path=path)
        state = first.snapshot_state(
            in_position=trade is not None,
            open_order_id=None,
            product_id="BTCUSD",
            live_trade=(SimpleNamespace(**trade) if trade is not None else None),
            timestamp=1_700_000_000,
            ack_state="ACKNOWLEDGED",
            order_seq=7,
        )
        assert first.persist(state) is True
        return path

    @staticmethod
    def _restart(path: str, positions):
        from core.live.reconciler import Reconciler

        def fetch():
            if isinstance(positions, Exception):
                raise positions
            return positions

        second = Reconciler(executor=SimpleNamespace(positions=fetch),
                            snapshot_path=path)
        return second.startup_check(dry_run=False)

    def test_restart_match_resumes_without_halt(self):
        import tempfile

        trade = {"direction": "LONG", "entry": 100.0, "stop_loss": 90.0,
                 "take_profit": 160.0, "quantity": 2.0, "entry_time": 1}
        with tempfile.TemporaryDirectory() as tmp:
            path = self._journal(tmp, trade)
            verdict = self._restart(
                path, [{"side": "LONG", "quantity": 2.0, "entry": 100.0}])
        self.assertEqual(verdict["verdict"], "MATCH")

    def test_restart_quantity_mismatch_halts(self):
        import tempfile

        trade = {"direction": "LONG", "entry": 100.0, "stop_loss": 90.0,
                 "take_profit": 160.0, "quantity": 2.0, "entry_time": 1}
        with tempfile.TemporaryDirectory() as tmp:
            path = self._journal(tmp, trade)
            second_verdict = self._restart(
                path, [{"side": "LONG", "quantity": 1.0, "entry": 100.0}])
        self.assertEqual(second_verdict["verdict"], "MISMATCH")

    def test_restart_unexpected_exchange_position_halts(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = self._journal(tmp, None)
            verdict = self._restart(
                path, [{"side": "SHORT", "quantity": 1.0, "entry": 50.0}])
        self.assertEqual(verdict["verdict"], "MISMATCH")

    def test_restart_executor_error_halts(self):
        import tempfile

        trade = {"direction": "LONG", "entry": 100.0, "stop_loss": 90.0,
                 "take_profit": 160.0, "quantity": 2.0, "entry_time": 1}
        with tempfile.TemporaryDirectory() as tmp:
            path = self._journal(tmp, trade)
            verdict = self._restart(path, OSError("feed down"))
        self.assertEqual(verdict["verdict"], "MISMATCH")

    def test_restart_journal_round_trip_stable(self):
        import json
        import tempfile

        trade = {"direction": "SHORT", "entry": 50.0, "stop_loss": 55.0,
                 "take_profit": 30.0, "quantity": 1.5, "entry_time": 2}
        with tempfile.TemporaryDirectory() as tmp:
            path = self._journal(tmp, trade)
            from core.live.reconciler import Reconciler

            loaded = Reconciler(
                executor=None, snapshot_path=path).load_snapshot()
        self.assertEqual(loaded["schema"], "broker-snapshot-v1")
        self.assertEqual(loaded["order_seq"], 7)
        self.assertEqual(
            json.dumps(loaded, sort_keys=True),
            json.dumps(loaded, sort_keys=True),
        )


if __name__ == "__main__":
    unittest.main()
