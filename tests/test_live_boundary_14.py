"""Phase-14: live contract/economics boundary certification.

Proves the runtime cannot silently fall back from verified safety
semantics to legacy/unverified behavior on a live path. Every case
is deterministic, offline, stdlib only; fake executors/transports
replace the network (LOCAL_VERIFIED, never EXCHANGE_VERIFIED).

Case map (§6 A-J):
  A. verified contract + passing gates -> accepted;
  B. missing contract in research -> explicit LOCAL/UNVERIFIED;
  C. missing/synthetic contract in paper -> explicit, strict fails
     closed (symbol matrix incl. derivative-like names);
  D. missing contract on live -> REFUSED before execution;
  E. synthetic contract on live -> REFUSED (order-attached terms
     never authorize; the venue registry governs);
  F. off-tick price -> REFUSED at audit; venue-grid bound proven
     at the executor;
  G. step misalignment -> floored, never increased;
  H. below minimum -> REFUSED (audit + executor);
  I. multiplier budget breach -> REFUSED at audit (executor has
     no multiplier field: venue quantity semantics stay
     EXTERNALLY UNVERIFIED — stated, not tested);
  J. executor quantity mutation -> REFUSED or revalidated.

Plus: broker fallback gates (no RiskEngine bypass), live
economics (costed/non-finite), and the reconciler/halt wiring
pins that keep the live path fail-closed.
"""

from __future__ import annotations

import unittest

from core.exchanges.contract_registry import ContractRegistry
from core.exchanges.delta.delta_contract import DeltaContract
from core.execution.order_executor import (
    DeltaOrderExecutor,
    InvalidContractError,
)
from core.risk.order_intent import OrderIntent


def venue_contract(symbol="BTCUSDT", **overrides):
    values = dict(
        symbol=symbol,
        exchange="DELTA",
        contract_type="perpetual_futures",
        tick_size=0.01,
        quantity_step=0.001,
        min_quantity=0.001,
        max_leverage=100.0,
        maker_fee=0.0005,
        taker_fee=0.001,
        price_precision=2,
        quantity_precision=3,
        product_id=2,
        live_execution_verified=True,
        live_execution_evidence="phase-14 certification fixture",
    )
    values.update(overrides)
    return DeltaContract(**values)


def compliant_intent(symbol="BTCUSDT", **overrides):
    # Gross RR (170-100)/10 = 7.0 >= 6, zero costs (post-cost
    # layer vacuous), valid geometry.
    params = dict(direction="BULLISH", entry=100.0, stop_loss=90.0,
                  take_profit=170.0, quantity=2.0, risk_amount=20.0,
                  commission=0.0, slippage=0.0, confidence=85.0,
                  score=85.0, symbol=symbol, valid=True)
    params.update(overrides)
    return OrderIntent(**params)


class _RecordingExchange:
    authenticated = True

    def __init__(self):
        self.placed = []

    def post(self, path, payload=None):
        self.placed.append(payload)
        return {"success": True,
                "result": {"id": "order_1", "state": "open"}}


def live_executor(symbol="BTCUSDT", **contract_overrides):
    registry = ContractRegistry()
    registry.add(venue_contract(symbol=symbol, **contract_overrides))
    exchange = _RecordingExchange()
    executor = DeltaOrderExecutor(
        exchange=exchange, registry=registry,
        order_id_factory=lambda i: "QE-TEST")
    return executor, exchange


def armed():
    from core.execution.live_safety_gate import LiveSafetyGate

    return LiveSafetyGate.test_armed()


class TestLiveContractBoundary(unittest.TestCase):
    def test_case_a_verified_accepted(self):
        executor, exchange = live_executor()
        result = executor.execute(compliant_intent(),
                                  safety=armed())
        self.assertTrue(result["success"])
        self.assertEqual(len(exchange.placed), 1)
        self.assertEqual(exchange.placed[0],
                         result["payload"])

    def test_case_b_research_missing_is_local_unverified(self):
        from core.risk.contract_gate import UNAVAILABLE, resolve_terms

        order = compliant_intent()
        terms, status = resolve_terms(order)
        self.assertIsNone(terms)
        self.assertEqual(status, UNAVAILABLE)
        # Nothing on the order claims venue verification.
        self.assertIsNone(getattr(order, "venue_verified", None))
        self.assertIsNone(getattr(order, "contract_verified", None))

    def test_case_c_paper_symbol_matrix(self):
        from core.runtime.paper_main import (
            ContractUnavailableError,
            ExplicitSymbolUniverseManager,
            _eligible_instrument,
        )

        # Derivative-like and arbitrary symbols all fall back to
        # explicitly synthetic metadata — never venue truth.
        for symbol in ("BTCUSDT", "BTC-PERP", "ETHUSDT",
                       "NIFTY25D17000CE", "SENSEX-FUT", "XXX-TEST"):
            instrument = _eligible_instrument(symbol)
            self.assertTrue(
                instrument.metadata.get("synthetic_fallback"),
                symbol)
            self.assertNotIn("verified_contract_kind",
                             instrument.metadata, symbol)
        # Strict mode fails closed for every one of them.
        with self.assertRaises(ContractUnavailableError):
            ExplicitSymbolUniverseManager(
                symbols=["BTC-PERP"], strict_contracts=True)

    def test_case_c_verified_metadata_positive_control(self):
        # An instrument WITH verified_* evidence yields a spec
        # (proves the factory path is not a blanket refusal).
        from core.registry.instrument import Instrument
        from core.risk.contract_spec_factory import (
            contract_spec_from_instrument,
        )

        instrument = Instrument(
            instrument_id="BTCUSDT", symbol="BTCUSDT",
            exchange="DELTA", product_type="PERPETUAL",
            tick_size=0.5, quantity_step=0.001,
            minimum_quantity=0.001, trading_enabled=True,
            state="ELIGIBLE",
            metadata={"verified_contract_kind": "LINEAR",
                      "verified_contract_multiplier": "1.0",
                      "verified_venue_source": "venue-docs",
                      "verified_venue_verified_at": "2026-01-01"})
        availability = contract_spec_from_instrument(instrument)
        self.assertIsNotNone(availability.spec)

    def test_case_d_live_missing_contract_refused(self):
        exchange = _RecordingExchange()
        executor = DeltaOrderExecutor(
            exchange=exchange,
            registry=ContractRegistry(),
            order_id_factory=lambda i: "QE-TEST")
        # No contract_terms attached at all: still refused — the
        # venue registry (empty) governs, not the order.
        with self.assertRaises(InvalidContractError):
            executor.execute(compliant_intent(symbol="UNKNOWN"),
                             safety=armed())
        self.assertEqual(exchange.placed, [])

    def test_case_e_live_synthetic_terms_cannot_authorize(self):
        exchange = _RecordingExchange()
        executor = DeltaOrderExecutor(
            exchange=exchange,
            registry=ContractRegistry(),
            order_id_factory=lambda i: "QE-TEST")
        synthetic = compliant_intent(symbol="BTC-PERP")
        synthetic.contract_terms = {"synthetic_fallback": True,
                                    "product_type": "SPOT"}
        with self.assertRaises(InvalidContractError):
            executor.execute(synthetic, safety=armed())
        self.assertEqual(exchange.placed, [])

    def test_case_e_registry_governs_not_order_terms(self):
        # Trust-root separation, stated explicitly: when the venue
        # registry holds a verified contract, execution is
        # registry-governed; order-attached terms (even synthetic)
        # neither authorize nor block.
        executor, exchange = live_executor(symbol="BTC-PERP")
        order = compliant_intent(symbol="BTC-PERP")
        order.contract_terms = {"synthetic_fallback": True}
        result = executor.execute(order, safety=armed())
        self.assertTrue(result["success"])
        self.assertEqual(len(exchange.placed), 1)

    def test_case_f_executor_price_bound_to_tick(self):
        executor, exchange = live_executor()
        result = executor.execute(
            compliant_intent(entry=100.005), safety=armed())
        self.assertTrue(result["success"])
        price = float(result["payload"]["limit_price"])
        self.assertLessEqual(abs(price - 100.005), 0.01 / 2 + 1e-9)

    def test_case_f_audit_refuses_off_tick(self):
        from core.risk.contract_gate import apply_terms

        verdict = apply_terms(
            quantity=2.0, entry=100.13, stop=90.0, risk_amount=0.0,
            terms={"tick_size": 0.5, "quantity_step": 0.25,
                   "minimum_quantity": 0.5, "multiplier": 1.0})
        self.assertFalse(verdict.valid)

    def test_case_g_step_floor_never_increases(self):
        executor, exchange = live_executor()
        result = executor.execute(
            compliant_intent(quantity=2.3456), safety=armed())
        self.assertTrue(result["success"])
        size = float(result["payload"]["size"])
        self.assertLessEqual(size, 2.3456)
        self.assertAlmostEqual(size, 2.345, places=9)

    def test_case_h_executor_refuses_below_minimum(self):
        executor, exchange = live_executor()
        with self.assertRaises(InvalidContractError):
            executor.execute(compliant_intent(quantity=0.0004),
                             safety=armed())
        self.assertEqual(exchange.placed, [])

    def test_case_j_posted_payload_equals_validated(self):
        executor, exchange = live_executor()
        order = compliant_intent(quantity=2.3456)
        result = executor.execute(order, safety=armed())
        posted = exchange.placed[0]
        self.assertEqual(posted, result["payload"])
        self.assertLessEqual(float(posted["size"]),
                             float(order.quantity))
        self.assertGreater(float(posted["size"]), 0.0)

    def test_case_i_multiplier_audited_not_invented(self):
        # Multiplier budget control lives at the audit gate
        # (covered); the executor payload carries no multiplier
        # field, so venue quantity semantics remain EXTERNAL.
        from core.risk.contract_gate import apply_terms

        refused = apply_terms(
            quantity=2.0, entry=100.0, stop=90.0, risk_amount=20.0,
            terms={"tick_size": 0.5, "quantity_step": 0.25,
                   "minimum_quantity": 0.5, "multiplier": 10.0})
        self.assertFalse(refused.valid)
        admitted = apply_terms(
            quantity=0.5, entry=100.0, stop=90.0, risk_amount=300.0,
            terms={"tick_size": 0.5, "quantity_step": 0.25,
                   "minimum_quantity": 0.5, "multiplier": 10.0})
        self.assertTrue(admitted.valid)


class TestLiveEconomicsBoundary(unittest.TestCase):
    def test_cost_eroded_live_order_refused(self):
        executor, exchange = live_executor()
        # Gross 1.0 admits the new trading policy, but costs must not
        # erode post-cost R:R below the new 1.0 minimum.
        order = compliant_intent(entry=100.0, stop_loss=90.0,
                                 take_profit=110.0, quantity=1.0,
                                 commission=12.0, slippage=0.0)
        result = executor.execute(order, safety=armed())
        self.assertFalse(result["success"])
        self.assertIn("post-cost", result["reason"])
        self.assertEqual(exchange.placed, [])

    def test_compliant_costed_live_order_passes(self):
        executor, exchange = live_executor()
        order = compliant_intent(commission=3.0, slippage=2.0)
        result = executor.execute(order, safety=armed())
        self.assertTrue(result["success"])
        self.assertEqual(len(exchange.placed), 1)

    def test_non_finite_costs_fail_closed(self):
        executor, exchange = live_executor()
        for bad in (float("nan"), float("inf")):
            order = compliant_intent(commission=bad, slippage=0.0)
            result = executor.execute(order, safety=armed())
            self.assertFalse(result["success"], bad)
            order2 = compliant_intent(commission=0.0, slippage=bad)
            result2 = executor.execute(order2, safety=armed())
            self.assertFalse(result2["success"], bad)
        self.assertEqual(exchange.placed, [])

    def test_zero_cost_legacy_vacuous(self):
        # Zero costs: byte-identical legacy behavior (a sub-6
        # gross test-harness intent still executes here; gross
        # gating is RiskEngine's + the broker route's duty).
        executor, exchange = live_executor()
        order = compliant_intent(entry=100.0, stop_loss=90.0,
                                 take_profit=110.0)
        result = executor.execute(order, safety=armed())
        self.assertTrue(result["success"])


class TestBrokerFallbackGates(unittest.TestCase):
    @staticmethod
    def _engine(script, candles, **kwargs):
        from core.live.broker_engine import BrokerEngine
        from core.market_state import MarketState
        from core.pipeline.pipeline_context import PipelineContext

        class Candle:
            def __init__(self, **kw):
                self.__dict__.update(kw)
                self.symbol = "TEST"
                self.timeframe = "1m"

        class FakePipeline:
            def __init__(self, script):
                self.script = script
                self._idx = 0
                self.reset()

            def reset(self):
                self.context = PipelineContext()
                self.context.market = MarketState(
                    symbol="TEST", timeframe="1m")
                self._idx = 0

            def on_candle(self, event):
                self.context.add_candle(event.candle)
                self.context.market.timestamp = (
                    event.candle.timestamp)
                self.context.order = self.script.get(self._idx,
                                                     None)
                self._idx += 1

        class FakeExecutor:
            def __init__(self):
                self.calls = []

            def execute(self, intent, safety=None):
                self.calls.append(intent)
                return {"success": True, "intent": intent}

            def positions(self):
                return []

            def balance(self):
                return {}

        pipeline = FakePipeline(script)
        executor = FakeExecutor()
        engine = BrokerEngine(pipeline, event_bus=None,
                              executor=executor, dry_run=False,
                              **kwargs)
        for candle in candles:
            engine.run_candle(Candle(**candle))
        return engine, executor

    def test_rejected_signal_cannot_route_live(self):
        # A sub-6-RR signal (what RiskEngine would refuse) fed
        # straight to the live route must not reach execute().
        from core.execution.live_safety_gate import LiveSafetyGate

        bad = compliant_intent(entry=100.0, stop_loss=90.0,
                               take_profit=105.0)
        engine, executor = self._engine(
            {0: bad}, [dict(high=105.0, low=99.0, close=102.0,
                            timestamp=1)],
            safety=LiveSafetyGate.test_armed())
        self.assertEqual(executor.calls, [])
        self.assertIsNone(engine.current_trade)

    def test_inverted_geometry_cannot_route_live(self):
        from core.execution.live_safety_gate import LiveSafetyGate

        bad = compliant_intent(entry=100.0, stop_loss=110.0,
                               take_profit=170.0)
        engine, executor = self._engine(
            {0: bad}, [dict(high=105.0, low=99.0, close=102.0,
                            timestamp=1)],
            safety=LiveSafetyGate.test_armed())
        self.assertEqual(executor.calls, [])

    def test_compliant_signal_routes_live(self):
        from core.execution.live_safety_gate import LiveSafetyGate

        engine, executor = self._engine(
            {0: compliant_intent()},
            [dict(high=105.0, low=99.0, close=102.0, timestamp=1)],
            safety=LiveSafetyGate.test_armed())
        self.assertEqual(len(executor.calls), 1)

    def test_cost_eroded_signal_cannot_route_live(self):
        from core.execution.live_safety_gate import LiveSafetyGate

        eroded = compliant_intent(
            entry=100.0, stop_loss=90.0, take_profit=110.0,
            quantity=1.0, commission=12.0, slippage=0.0)
        engine, executor = self._engine(
            {0: eroded},
            [dict(high=105.0, low=99.0, close=102.0, timestamp=1)],
            safety=LiveSafetyGate.test_armed())
        self.assertEqual(executor.calls, [])


if __name__ == "__main__":
    unittest.main()
