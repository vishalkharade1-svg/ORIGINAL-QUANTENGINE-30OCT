"""
====================================================

QuantEngine -- Phase 11A LIVE safety invariant tests.

Genuine, executable safety tests for the centralized
LiveSafetyGate (core/execution/live_safety_gate.py).

Every test performs a MEANINGFUL ACTION followed by a
MEANINGFUL ASSERTION:

  * gate decisions are evaluated AND enforced (require
    raises or returns -- never just read);
  * the REAL order-submission boundary
    (DeltaExchange.place_order -> rest.post("/v2/orders"))
    is instrumented with a counting fake transport, so
    "zero transport calls" is measured, not assumed;
  * the positive control proves LIVE is deliberately
    armable against the fake (not permanently disabled);
  * loops assert non-emptiness BEFORE asserting over
    elements (no 0-iteration vacuity);
  * no test only snapshots a settings default.

Conventions: unittest, stdlib only. No real network, no
real credentials -- the "valid credentials" below are
synthetic strings presented to a local fake transport.

Matrix (§28): PAPER allowed; LIVE+ALLOW_LIVE=false /
LIVE_EXECUTE=false / missing / empty creds rejected;
LIVE fully armed + fake transport reaches the fake
exactly once; UNKNOWN and PAPER+LIVE conflict rejected;
PAPER lifecycle shows zero live transport calls;
rejected LIVE attempts show zero transport calls.

====================================================
"""

import unittest
from unittest.mock import patch

from core.events.event_bus import EventBus
from core.exchanges.contract_registry import ContractRegistry
from core.exchanges.delta.delta_contract import DeltaContract
from core.exchanges.delta.delta_exchange import DeltaExchange
from core.execution.live_safety_gate import (
    ConfigurationError,
    ExecutionMode,
    LiveBlockedError,
    LiveSafetyGate,
)
from core.execution.order_executor import DeltaOrderExecutor
from core.live.broker_engine import BrokerEngine
from core.pipeline.institutional_pipeline import InstitutionalPipeline
from core.pipeline.pipeline_context import PipelineContext
from core.risk.order_intent import OrderIntent


# ==================================================
# Shared fakes (production-shaped, local only)
# ==================================================


class CountingREST:
    """Local stand-in for DeltaSignedREST at the exact
    transport boundary DeltaExchange.place_order calls:
    rest.post("/v2/orders", payload=...). Records every
    call; no network."""

    def __init__(self, authenticated=True):
        self.authenticated = authenticated
        self.calls = []

    def post(self, path, payload=None):
        self.calls.append(("post", path, payload))
        return {
            "result": {
                "id": "FAKE-ORDER-1",
                "status": "open",
            }
        }

    def get(self, path, params=None):
        self.calls.append(("get", path, params))
        return {"result": []}

    def delete(self, path):
        self.calls.append(("delete", path))
        return {"result": {"id": "FAKE-ORDER-1"}}


def live_exchange(fake):
    """A REAL DeltaExchange object (real place_order ->
    _require_auth -> rest.post chain) bound to the local
    counting fake with SYNTHETIC credentials."""

    return DeltaExchange(
        api_key="SYNTHETIC-TEST-KEY",
        api_secret="SYNTHETIC-TEST-SECRET",
        rest=fake,
    )


def registry(symbol="BTCUSDT"):
    reg = ContractRegistry()
    reg.add(
        DeltaContract(
            symbol=symbol,
            exchange="DELTA",
            contract_type="perpetual_futures",
            tick_size=0.01,
            quantity_step=0.001,
            min_quantity=0.00001,
            max_leverage=100.0,
            maker_fee=0.0005,
            taker_fee=0.001,
            price_precision=2,
            quantity_precision=5,
            product_id=2,
            live_execution_verified=True,
            live_execution_evidence="synthetic test fixture",
        )
    )
    return reg


def intent(symbol="BTCUSDT"):
    # Phase-14 maintenance: gate-compliant economics (gross RR
    # (83500-80000)/500 = 7.0 >= 6), because BrokerEngine._route
    # now enforces the mandatory geometry + gross-RR + post-cost
    # gates before any live write. Transport-boundary intent
    # unchanged (exactly one POST to /v2/orders).
    return OrderIntent(
        direction="BULLISH",
        entry=80000.0,
        stop_loss=79500.0,
        take_profit=83500.0,
        quantity=0.0623,
        symbol=symbol,
        valid=True,
        reason="accepted by risk engine",
    )


def refused(**overrides):
    """A refused gate decision: fully armed EXCEPT the
    overridden condition(s)."""

    params = {
        "mode": ExecutionMode.LIVE,
        "allow_live": True,
        "live_execute": True,
        "has_credentials": True,
    }
    params.update(overrides)
    return LiveSafetyGate.decide(**params)


class Candle:
    def __init__(self, timestamp, symbol="BTCUSDT"):
        self.timestamp = timestamp
        self.open = 80000.0
        self.high = 80100.0
        self.low = 79900.0
        self.close = 80050.0
        self.volume = 100.0
        self.symbol = symbol
        self.timeframe = "1m"


class ScriptedPipeline:
    """Pipeline double serving one scripted valid intent
    (proves routing without re-implementing strategy)."""

    def __init__(self, script):
        self.script = script
        self._idx = 0
        self.context = PipelineContext()

    def reset(self):
        pass

    def on_candle(self, event):
        self.context.order = self.script.get(self._idx, None)
        self._idx += 1


# ==================================================
# Mode resolution: explicit, conflict/unknown rejected
# ==================================================


class TestExecutionMode(unittest.TestCase):

    def test_paper_flag_resolves_paper(self):
        self.assertEqual(
            ExecutionMode.resolve(paper_mode=True),
            ExecutionMode.PAPER,
        )

    def test_live_flag_resolves_live(self):
        self.assertEqual(
            ExecutionMode.resolve(live_mode=True),
            ExecutionMode.LIVE,
        )

    def test_neither_flag_resolves_analyze(self):
        self.assertEqual(
            ExecutionMode.resolve(),
            ExecutionMode.ANALYZE,
        )

    def test_paper_and_live_conflict_rejected(self):
        with self.assertRaises(ConfigurationError) as ctx:
            ExecutionMode.resolve(
                paper_mode=True, live_mode=True
            )

        self.assertIn("cannot both be enabled", str(ctx.exception))

    def test_unknown_override_rejected(self):
        for bad in ("UNKNOWN", "LIVE_PAPER", "foo", "live-paper"):
            with self.assertRaises(
                ConfigurationError, msg="override={!r}".format(bad)
            ):
                ExecutionMode.resolve(execution_mode=bad)

    def test_invalid_bool_rejected(self):
        with self.assertRaises(ConfigurationError):
            ExecutionMode.resolve(paper_mode="sometimes")

    def test_explicit_override_is_authoritative(self):
        self.assertEqual(
            ExecutionMode.resolve(
                paper_mode=True, execution_mode="paper"
            ),
            ExecutionMode.PAPER,
        )


# ==================================================
# Gate decision matrix (each row executes the gate)
# ==================================================


class TestLiveSafetyGateMatrix(unittest.TestCase):

    def test_paper_mode_never_arms_live(self):
        decision = LiveSafetyGate.decide(
            mode=ExecutionMode.PAPER,
            allow_live=True,
            live_execute=True,
            has_credentials=True,
        )

        self.assertFalse(decision.allowed)

        with self.assertRaises(LiveBlockedError):
            LiveSafetyGate.require(
                mode=ExecutionMode.PAPER,
                allow_live=True,
                live_execute=True,
                has_credentials=True,
                component="test",
            )

    def test_allow_live_false_blocks_fully_armed_rest(self):
        decision = refused(allow_live=False)

        self.assertFalse(decision.allowed)
        self.assertIn("ALLOW_LIVE=false", decision.reason)

        with self.assertRaises(LiveBlockedError):
            LiveSafetyGate.require_decision(
                decision, component="test"
            )

    def test_live_execute_false_blocks(self):
        decision = refused(live_execute=False)

        self.assertFalse(decision.allowed)
        self.assertIn("LIVE_EXECUTE=false", decision.reason)

        with self.assertRaises(LiveBlockedError):
            LiveSafetyGate.require_decision(
                decision, component="test"
            )

    def test_missing_credentials_block(self):
        for key, secret in ((None, None), ("", ""), ("k", ""), ("", "s")):
            decision = LiveSafetyGate.decide(
                mode=ExecutionMode.LIVE,
                allow_live=True,
                live_execute=True,
                api_key=key,
                api_secret=secret,
            )

            self.assertFalse(
                decision.allowed,
                msg="creds={!r}".format((key, secret)),
            )
            self.assertIn("credentials missing", decision.reason)

    def test_all_conditions_arms(self):
        decision = LiveSafetyGate.decide(
            mode=ExecutionMode.LIVE,
            allow_live=True,
            live_execute=True,
            api_key="SYNTHETIC",
            api_secret="SYNTHETIC",
        )

        self.assertTrue(decision.allowed)
        self.assertTrue(decision.armed)

        armed = LiveSafetyGate.require(
            mode=ExecutionMode.LIVE,
            allow_live=True,
            live_execute=True,
            api_key="SYNTHETIC",
            api_secret="SYNTHETIC",
            component="test",
        )
        self.assertTrue(armed.allowed)

    def test_unknown_mode_decide_rejected(self):
        with self.assertRaises(ConfigurationError):
            LiveSafetyGate.decide(mode="BOGUS")

    def test_missing_token_refused(self):
        with self.assertRaises(LiveBlockedError):
            LiveSafetyGate.require_decision(
                None, component="test"
            )


# ==================================================
# Dangerous boundary: real chain, counting transport
# ==================================================


class TestLiveTransportBoundary(unittest.TestCase):

    def test_blocked_execute_makes_zero_transport_calls(self):
        fake = CountingREST()
        executor = DeltaOrderExecutor(
            exchange=live_exchange(fake),
            registry=registry(),
            order_id_factory=lambda i: "QE-TEST",
        )

        with self.assertRaises(LiveBlockedError):
            executor.execute(
                intent(), safety=refused(allow_live=False)
            )

        self.assertEqual(fake.calls, [])

    def test_default_settings_execute_blocked_zero_calls(self):
        """No explicit token: the gate falls back to
        operator settings. With the test-forced
        ALLOW_LIVE=false default the production-shaped
        execute() refuses BEFORE the transport."""

        import config.settings as s

        saved = s.settings.ALLOW_LIVE
        s.settings.ALLOW_LIVE = False
        try:
            fake = CountingREST()
            executor = DeltaOrderExecutor(
                exchange=live_exchange(fake),
                registry=registry(),
                order_id_factory=lambda i: "QE-TEST",
            )

            with self.assertRaises(LiveBlockedError):
                executor.execute(intent())

            self.assertEqual(fake.calls, [])
        finally:
            s.settings.ALLOW_LIVE = saved

    def test_armed_positive_control_reaches_fake_once(self):
        """Deliberately armable: fully-armed gate +
        synthetic creds + fake transport reaches the
        transport EXACTLY once. No real network: the
        transport IS the local fake (asserted)."""

        fake = CountingREST()
        exchange = live_exchange(fake)
        executor = DeltaOrderExecutor(
            exchange=exchange,
            registry=registry(),
            order_id_factory=lambda i: "QE-TEST",
        )

        result = executor.execute(
            intent(), safety=LiveSafetyGate.test_armed()
        )

        self.assertTrue(result["success"])
        self.assertIs(exchange.rest, fake)
        self.assertEqual(len(fake.calls), 1)

        kind, path, payload = fake.calls[0]
        self.assertEqual(kind, "post")
        self.assertEqual(path, "/v2/orders")
        self.assertEqual(payload["product_id"], 2)

    def test_auth_guard_preserved_without_credentials(self):
        """Defense in depth: the pre-existing _require_auth
        still fails closed on empty creds (no network: the
        guard raises before any transport write)."""

        exchange = DeltaExchange(api_key="", api_secret="")

        with self.assertRaises(RuntimeError):
            exchange._require_auth()

        with self.assertRaises(RuntimeError):
            exchange.place_order({"product_id": 2})

    def test_broker_live_construction_requires_safety(self):
        """Accidental BrokerEngine(dry_run=False) without
        the arming token fails at construction -- zero
        candles processed, zero transport possible."""

        with self.assertRaises(LiveBlockedError):
            BrokerEngine(
                ScriptedPipeline({}),
                event_bus=None,
                executor=CountingREST(),
                dry_run=False,
            )

    def test_broker_live_route_reaches_fake_once(self):
        """Production-shaped live route: scripted intent
        -> BrokerEngine(dry_run=False, armed) -> REAL
        DeltaOrderExecutor -> fake transport, exactly one
        post to /v2/orders."""

        fake = CountingREST()
        executor = DeltaOrderExecutor(
            exchange=live_exchange(fake),
            registry=registry(symbol="TEST"),
            order_id_factory=lambda i: "QE-TEST",
        )
        engine = BrokerEngine(
            ScriptedPipeline({0: intent(symbol="TEST")}),
            event_bus=None,
            executor=executor,
            dry_run=False,
            safety=LiveSafetyGate.test_armed(),
        )

        engine.run_candle(Candle(timestamp=1, symbol="TEST"))

        # The order-submission boundary specifically: exactly
        # ONE post to /v2/orders. (The live engine also
        # syncs balance/positions after routing, which adds
        # read calls on the same fake -- those are not order
        # submissions and are excluded by the filter.)
        posts = [
            call
            for call in fake.calls
            if call[0] == "post" and call[1] == "/v2/orders"
        ]
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0][2]["product_id"], 2)
        self.assertIsNotNone(engine.current_trade)

    def test_broker_route_rechecks_gate_every_candle(self):
        """Tampering the token after construction still
        blocks the route: per-candle enforcement, zero
        transport calls."""

        fake = CountingREST()
        executor = DeltaOrderExecutor(
            exchange=live_exchange(fake),
            registry=registry(symbol="TEST"),
            order_id_factory=lambda i: "QE-TEST",
        )
        engine = BrokerEngine(
            ScriptedPipeline({0: intent(symbol="TEST")}),
            event_bus=None,
            executor=executor,
            dry_run=False,
            safety=LiveSafetyGate.test_armed(),
        )

        engine._safety = refused(allow_live=False)

        with self.assertRaises(LiveBlockedError):
            engine.run_candle(Candle(timestamp=1, symbol="TEST"))

        self.assertEqual(fake.calls, [])


# ==================================================
# PAPER lifecycle: real runtime, zero live transport
# ==================================================


class TestPaperLifecycle(unittest.TestCase):

    def test_paper_runtime_uses_paper_adapter_zero_live(self):
        """Real build_paper_engine offline (fake network
        transport, default world factory): runtimes exist
        (non-vacuous), every one is PaperExecutionAdapter
        + dry_run, pushed candles route, and the patched
        live surface observes ZERO calls while candles
        actually flowed."""

        from core.runtime.execution_port import PaperExecutionAdapter
        from core.runtime.paper_main import (
            ExplicitSymbolUniverseManager,
            build_paper_engine,
        )

        class FakeTransport:
            def __init__(self):
                self._routes = {}
                self.closed = False

            def subscribe(self, symbol, on_candle, on_down):
                self._routes[symbol] = (on_candle, on_down)

            def unsubscribe(self, symbol):
                self._routes.pop(symbol, None)

            def push(self, symbol, candle):
                route = self._routes.get(symbol)
                if route is not None:
                    route[0](candle)

            def close(self):
                self.closed = True
                self._routes.clear()

        from core.history.candle import Candle as HistCandle

        transport = FakeTransport()
        engine, _manager = build_paper_engine(
            universe_manager=ExplicitSymbolUniverseManager(
                symbols=["BTC"], timeframe="1m"
            ),
            transport_factory=lambda: transport,
            clock=lambda: 1000.0,
            timeframe="1m",
            refresh_interval_seconds=0,
        )
        engine.start()
        try:
            self.assertGreater(
                len(engine.runtimes), 0
            )

            for runtime in engine.runtimes.values():
                self.assertIsInstance(
                    runtime.port, PaperExecutionAdapter
                )
                self.assertTrue(runtime.engine.dry_run)

            live_calls = []
            original = DeltaOrderExecutor.execute

            def spy(self, _intent, **kwargs):
                live_calls.append(_intent)
                return original(self, _intent, **kwargs)

            pushed = 30
            with patch.object(
                DeltaOrderExecutor, "execute", spy
            ):
                for n in range(pushed):
                    transport.push(
                        "BTC",
                        HistCandle(
                            timestamp=1000 + n * 60,
                            open=80000.0,
                            high=80100.0,
                            low=79900.0,
                            close=80050.0,
                            volume=100.0,
                            closed=True,
                            symbol="BTC",
                        ),
                    )

            # Candles genuinely flowed through the runtime...
            self.assertEqual(engine.routed, pushed)
            # ...and the live surface was never touched.
            self.assertEqual(live_calls, [])
        finally:
            engine.stop()


# ==================================================
# Configuration shapes (main.py startup contract)
# ==================================================


class TestStartupConfiguration(unittest.TestCase):

    def _stub_settings(self, **overrides):
        params = {
            "PAPER_MODE": False,
            "LIVE_MODE": False,
            "LIVE_EXECUTE": False,
            "ALLOW_LIVE": False,
            "EXECUTION_MODE": "",
            "API_KEY": "",
            "API_SECRET": "",
        }
        params.update(overrides)
        return type("StubSettings", (), params)()

    def test_conflict_rejected_from_settings_shape(self):
        stub = self._stub_settings(
            PAPER_MODE=True, LIVE_MODE=True
        )

        with self.assertRaises(ConfigurationError):
            LiveSafetyGate.from_settings(stub)

    def test_unknown_mode_rejected_from_settings_shape(self):
        stub = self._stub_settings(EXECUTION_MODE="LIVE_PAPER")

        with self.assertRaises(ConfigurationError):
            LiveSafetyGate.from_settings(stub)

    def test_startup_banner_states_are_observable(self):
        blocked = refused(allow_live=False)
        lines = LiveSafetyGate.format_banner(blocked)

        self.assertIn("EXECUTION MODE: LIVE", lines[0])
        self.assertIn("BLOCKED", lines[1])
        self.assertIn("ALLOW_LIVE=false", lines[2])

        armed = LiveSafetyGate.test_armed()
        armed_lines = LiveSafetyGate.format_banner(armed)

        self.assertIn("ARMED", armed_lines[1])

    def test_safety_describe_never_leaks_secrets(self):
        decision = LiveSafetyGate.decide(
            mode=ExecutionMode.LIVE,
            allow_live=True,
            live_execute=True,
            api_key="REAL-LOOKING-KEY",
            api_secret="REAL-LOOKING-SECRET",
        )
        state = LiveSafetyGate.describe(decision)
        banner = "\n".join(
            LiveSafetyGate.format_banner(decision)
        )

        self.assertNotIn("REAL-LOOKING-KEY", banner)
        self.assertNotIn("REAL-LOOKING-SECRET", banner)
        self.assertNotIn("REAL-LOOKING-KEY", str(state))
        self.assertNotIn("REAL-LOOKING-SECRET", str(state))


if __name__ == "__main__":
    unittest.main()
