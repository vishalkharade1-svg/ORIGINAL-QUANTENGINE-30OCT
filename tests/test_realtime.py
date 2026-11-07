"""
====================================================

QuantEngine

Phase 6D -- Real-time multi-symbol subscriptions.

Offline tests: a FakeTransport models Delta's multiplexed
subscription model (one connection, many symbol routes) and
a FakeClock drives the worker/manager pump deterministically.
No network, no threads.

Covers the Phase 6D contract:
  * subscription lifecycle (eligible -> created; dynamic add / remove;
    ineligible & delisted -> removed; no restart)
  * universe diff (pass1 BTC,ETH -> pass2 BTC,SOL => BTC retained,
    ETH unsubscribed, SOL subscribed)
  * failure isolation (A and C continue while B reconnects)
  * reconnection (restored, no duplicate subscription, no duplicate
    candle across the reconnect boundary)
  * candle integrity (duplicate / out-of-order / forming vs closed /
    closed-once / reconnect boundary)
  * staleness and reconnect-budget exhaustion
====================================================
"""

import unittest

from core.history.candle import Candle
from core.registry.instrument import Instrument
from core.registry.product_types import PRODUCT_STATE_DELISTED
from core.registry.product_types import PRODUCT_STATE_ELIGIBLE
from data.realtime import CandleRouter
from data.realtime import MultiSymbolSubscriptionManager
from data.realtime import ReconnectExhausted
from data.realtime import ReconnectPolicy
from data.realtime import SubscriptionState
from data.realtime import SubscriptionStatus
from data.realtime import SubscriptionWorker
from data.realtime import assert_valid_transition


def make_instrument(symbol, state=PRODUCT_STATE_ELIGIBLE):

    return Instrument(

        instrument_id=f"id-{symbol}",
        symbol=symbol,
        exchange="delta",
        product_type="CURRENCY",
        tick_size=0.01,
        quantity_step=0.001,
        minimum_quantity=0.001,
        trading_enabled=True,
        state=state,

    )


class FakeUniverse:

    """Duck-typed MarketUniverse snapshot (eligible cut only)."""

    def __init__(self, instruments):

        self._instruments = list(instruments)

    def eligible_instruments(self):

        return self._instruments


class FakeTransport:

    """One multiplexed connection carrying many symbol routes.
    push/down target a single route so worker A cannot be affected
    by worker B."""

    def __init__(self, fail_on_subscribe=None):

        self._routes = {}
        self._fail = set(fail_on_subscribe or [])
        self.subscribe_calls = {}
        self.unsubscribed = []
        self.closed = False

    def subscribe(self, symbol, on_candle, on_down):

        self.subscribe_calls[symbol] = self.subscribe_calls.get(symbol, 0) + 1

        if symbol in self._fail:

            raise RuntimeError(f"subscribe failed: {symbol}")

        self._routes[symbol] = (on_candle, on_down)

    def unsubscribe(self, symbol):

        self._routes.pop(symbol, None)
        self.unsubscribed.append(symbol)

    def push(self, symbol, candle):

        route = self._routes.get(symbol)

        if route is not None:

            route[0](candle)

    def down(self, symbol):

        route = self._routes.get(symbol)

        if route is not None:

            route[1]()

    def close(self):

        self.closed = True
        self._routes.clear()


class FakeClock:

    def __init__(self, start=100.0):

        self.t = start

    def __call__(self):

        return self.t

    def advance(self, delta):

        self.t += delta


def candle(timestamp, closed=True, symbol="BTC", close=100.0):
    """Canonical closed/forming candle helper."""

    return Candle(

        timestamp=timestamp,
        open=close - 1.0,
        high=close + 1.0,
        low=close - 1.0,
        close=close,
        volume=1.0,
        closed=closed,
        symbol=symbol,

    )


def make_manager(clock=None, policy=None, callback=None, transport=None):
    """Shared-transport manager against a fake multiplexed stream."""

    clock = clock or FakeClock()
    transport = transport or FakeTransport()

    manager = MultiSymbolSubscriptionManager(

        transport_factory=lambda: transport,
        clock=clock,
        policy=policy or ReconnectPolicy(base_delay=1.0, factor=2.0),
        candles_callback=callback,

    )

    return manager, transport, clock


# =====================================================
# Candle integrity (CandleRouter), candle provenance
# =====================================================

class TestCandleProvenance(unittest.TestCase):

    def test_backtest_candle_stays_closed_and_untagged(self):
        """Adding Phase 6D fields must not change the backtest
        candle shape (default closed=True, symbol="")."""

        plain = Candle(
            timestamp=1, open=2.0, high=3.0, low=1.0, close=2.5, volume=1.0,
        )

        self.assertTrue(plain.closed)
        self.assertEqual(plain.symbol, "")

    def test_live_candle_can_be_marked_forming(self):

        forming = candle(timestamp=5, closed=False)

        self.assertFalse(forming.closed)
        self.assertEqual(forming.symbol, "BTC")


class TestCandleRouterIntegrity(unittest.TestCase):

    def test_closed_candle_delivered_once(self):

        router = CandleRouter(symbol="BTC")

        first = router.route(candle(timestamp=100))
        second = router.route(candle(timestamp=100))

        self.assertIsNotNone(first)
        self.assertIsNone(second)
        self.assertEqual(router.delivered, 1)
        self.assertEqual(router.duplicates, 1)
        self.assertEqual(router.last_delivered_ts, 100)

    def test_forming_candle_never_delivered(self):

        router = CandleRouter(symbol="BTC")

        out = router.route(candle(timestamp=100, closed=False))

        self.assertIsNone(out)
        self.assertEqual(router.delivered, 0)
        self.assertEqual(router.forming_skipped, 1)

    def test_out_of_order_closed_candle_dropped(self):

        router = CandleRouter(symbol="BTC")

        router.route(candle(timestamp=200))
        dropped = router.route(candle(timestamp=150))

        self.assertIsNone(dropped)
        self.assertEqual(router.out_of_order, 1)
        self.assertEqual(router.delivered, 1)

    def test_reconnect_boundary_duplicate_then_new(self):

        router = CandleRouter(symbol="BTC")

        router.route(candle(timestamp=100))

        # Simulated reconnect replays the last candle, then a stale
        # older one, then a new timestamp.
        replayed = router.route(candle(timestamp=100))
        stale_old = router.route(candle(timestamp=60))
        newer = router.route(candle(timestamp=110))

        self.assertIsNone(replayed)   # duplicate
        self.assertIsNone(stale_old)  # out-of-order
        self.assertIsNotNone(newer)
        self.assertEqual(router.duplicates, 1)
        self.assertEqual(router.out_of_order, 1)
        self.assertEqual(router.delivered, 2)
        self.assertEqual(router.last_delivered_ts, 110)

    def test_chronological_order_preserved(self):

        router = CandleRouter(symbol="BTC")
        delivered = []

        for ts in (100, 101, 102):

            out = router.route(candle(timestamp=ts))

            if out is not None:

                delivered.append(out.timestamp)

        self.assertEqual(delivered, [100, 101, 102])


# =====================================================
# State machine (SubscriptionState)
# =====================================================

class TestSubscriptionStateMachine(unittest.TestCase):

    def test_statuses_explicit(self):
        """The six explicit lifecycle states; no implicit boolean."""

        self.assertEqual(
            {
                SubscriptionStatus.STOPPED,
                SubscriptionStatus.CONNECTING,
                SubscriptionStatus.LIVE,
                SubscriptionStatus.RECONNECTING,
                SubscriptionStatus.STALE,
                SubscriptionStatus.FAILED,
            },
            {
                "STOPPED", "CONNECTING", "LIVE",
                "RECONNECTING", "STALE", "FAILED",
            },
        )

    def test_illegal_transition_raises(self):

        with self.assertRaises(ValueError):

            assert_valid_transition(
                SubscriptionStatus.STOPPED,
                SubscriptionStatus.LIVE,
            )

    def test_state_initial(self):

        state = SubscriptionState(symbol="BTC")

        self.assertEqual(state.status, SubscriptionStatus.STOPPED)
        self.assertEqual(state.received, 0)
        self.assertEqual(state.delivered, 0)


# =====================================================
# SubscriptionWorker lifecycle
# =====================================================

class TestSubscriptionWorker(unittest.TestCase):

    def _worker(self, transport=None, policy=None, max_stale=10.0,
                clock=None, callback=None):

        clock = clock or FakeClock()
        transport = transport or FakeTransport()

        worker = SubscriptionWorker(
            symbol="BTC",
            transport=transport,
            clock=clock,
            policy=policy or ReconnectPolicy(base_delay=1.0, factor=2.0),
            max_stale_seconds=max_stale,
            on_closed_candle=callback,
        )

        return worker, transport, clock

    def test_eligible_starts_live(self):

        worker, transport, clock = self._worker()

        worker.start()

        self.assertEqual(worker.state.status, SubscriptionStatus.LIVE)
        self.assertIn("BTC", transport.subscribe_calls)

    def test_disconnect_triggers_reconnecting(self):

        worker, transport, clock = self._worker()

        worker.start()
        transport.down("BTC")

        self.assertEqual(worker.state.status, SubscriptionStatus.RECONNECTING)
        self.assertEqual(worker.state.reconnect_attempts, 1)

    def test_reconnect_restores_subscription_no_duplicate_sub(self):

        worker, transport, clock = self._worker()

        worker.start()
        transport.down("BTC")

        clock.advance(1.0)
        worker.poll()

        self.assertEqual(worker.state.status, SubscriptionStatus.LIVE)
        self.assertEqual(worker.state.reconnect_attempts, 0)
        self.assertEqual(transport.subscribe_calls["BTC"], 2)

    def test_forming_candle_keeps_live_but_not_delivered(self):

        delivered = []
        worker, transport, clock = self._worker(callback=delivered.append)

        worker.start()
        transport.push("BTC", candle(timestamp=100, closed=False))
        transport.push("BTC", candle(timestamp=101, closed=False))

        self.assertEqual(worker.state.status, SubscriptionStatus.LIVE)
        self.assertEqual(worker.state.received, 2)
        self.assertEqual(worker.state.forming_skipped, 2)
        self.assertEqual(delivered, [])

    def test_closed_candle_delivered_once_through_worker(self):

        delivered = []
        worker, transport, clock = self._worker(callback=delivered.append)

        worker.start()
        transport.push("BTC", candle(timestamp=100))
        transport.push("BTC", candle(timestamp=100))
        transport.push("BTC", candle(timestamp=101))

        self.assertEqual([c.timestamp for c in delivered], [100, 101])
        self.assertEqual(worker.state.delivered, 2)
        self.assertEqual(worker.state.duplicates, 1)

    def test_worker_ignores_other_symbols_candle(self):

        delivered = []
        worker, transport, clock = self._worker(callback=delivered.append)

        worker.start()
        transport.push("BTC", candle(timestamp=100, symbol="ETH"))

        self.assertEqual(worker.state.received, 0)
        self.assertEqual(delivered, [])

    def test_staleness_transition(self):

        worker, transport, clock = self._worker(max_stale=10.0)

        worker.start()

        clock.advance(15.0)
        worker.poll()

        self.assertEqual(worker.state.status, SubscriptionStatus.STALE)

        transport.push("BTC", candle(timestamp=200, closed=False))
        self.assertEqual(worker.state.status, SubscriptionStatus.LIVE)

    def test_reconnect_exhaustion_yields_failed(self):

        policy = ReconnectPolicy(
            base_delay=1.0,
            factor=1.0,
            max_attempts=2,
        )
        transport = FakeTransport(fail_on_subscribe=["BTC"])
        worker, _, clock = self._worker(transport=transport, policy=policy)

        worker.start()

        # Every retry fails, so the budget is consumed then exhausted.
        clock.advance(1.0)
        worker.poll()
        clock.advance(1.0)

        with self.assertRaises(ReconnectExhausted):

            worker.poll()

        self.assertEqual(worker.state.status, SubscriptionStatus.FAILED)

    def test_subscribe_raises_at_start_becomes_reconnecting(self):

        transport = FakeTransport(fail_on_subscribe=["BTC"])
        worker, _, clock = self._worker(transport=transport)

        worker.start()

        self.assertEqual(worker.state.status, SubscriptionStatus.RECONNECTING)
        self.assertEqual(worker.state.last_error, "subscribe failed: BTC")

    def test_stop_unsubscribes_full_stop(self):

        worker, transport, clock = self._worker()

        worker.start()
        worker.stop()

        self.assertEqual(worker.state.status, SubscriptionStatus.STOPPED)
        self.assertIn("BTC", transport.unsubscribed)


# =====================================================
# MultiSymbolSubscriptionManager
# =====================================================

class TestManagerUniverseDiff(unittest.TestCase):

    def test_eligible_instruments_subscribed(self):

        manager, transport, clock = make_manager()

        result = manager.sync([
            make_instrument("BTC"),
            make_instrument("ETH"),
        ])

        self.assertEqual(set(manager.symbols), {"BTC", "ETH"})
        self.assertEqual(result["added"], ["BTC", "ETH"])
        self.assertEqual(
            manager.status("BTC").status,
            SubscriptionStatus.LIVE,
        )
        self.assertTrue(transport.closed is False)

    def test_universe_accepts_market_universe_snapshot(self):
        """The eligible-instruments source can be a MarketUniverse
        duck (Phase 6B shape)."""

        manager, transport, clock = make_manager()

        manager.sync(FakeUniverse([make_instrument("BTC")]))

        self.assertEqual(manager.symbols, ("BTC",))

    def test_dynamic_add_no_restart(self):
        """A newly eligible instrument is subscribed on the next
        pass against the SAME shared transport (no new connection)."""

        manager, transport, clock = make_manager()
        manager.sync([make_instrument("BTC")])

        transport_before = manager.transport
        result = manager.sync([
            make_instrument("BTC"),
            make_instrument("SOL"),
        ])

        self.assertEqual(result["added"], ["SOL"])
        self.assertEqual(set(manager.symbols), {"BTC", "SOL"})
        self.assertIs(manager.transport, transport_before)

    def test_universe_change_btc_eth_to_btc_sol(self):
        """Pass1 BTC,ETH -> Pass2 BTC,SOL: BTC retained (same worker
        object), ETH unsubscribed, SOL subscribed."""

        manager, transport, clock = make_manager()
        manager.sync([
            make_instrument("BTC"),
            make_instrument("ETH"),
        ])

        btc_worker_old = manager._workers["BTC"]

        result = manager.sync([
            make_instrument("BTC"),
            make_instrument("SOL"),
        ])

        self.assertEqual(result["kept"], ["BTC"])
        self.assertEqual(result["removed"], ["ETH"])
        self.assertEqual(result["added"], ["SOL"])

        # BTC worker object is retained: subscription kept alive.
        self.assertIs(manager._workers["BTC"], btc_worker_old)
        self.assertEqual(
            manager.status("BTC").status,
            SubscriptionStatus.LIVE,
        )

        # ETH is gone from the manager and stopped on the transport.
        self.assertNotIn("ETH", manager.statuses())
        self.assertIn("ETH", transport.unsubscribed)

        # SOL is freshly subscribed and live.
        self.assertEqual(
            manager.status("SOL").status,
            SubscriptionStatus.LIVE,
        )

    def test_ineligible_and_delisted_removed(self):
        """Once the eligibility layer stops listing a symbol, the
        subscription is removed safely regardless of why."""

        manager, transport, clock = make_manager()
        manager.sync([make_instrument("BTC"), make_instrument("ETH")])

        # Next pass: ETH is no longer in the eligible cut (it may be
        # ineligible, delisted, or merely absent -- the manager sees
        # the same thing).
        manager.sync([make_instrument("BTC")])

        self.assertEqual(manager.symbols, ("BTC",))
        self.assertIn("ETH", transport.unsubscribed)

        inst = make_instrument("SOL", state=PRODUCT_STATE_DELISTED)
        self.assertEqual(inst.state, PRODUCT_STATE_DELISTED)

    def test_sync_idempotent(self):

        manager, transport, clock = make_manager()
        manager.sync([make_instrument("BTC"), make_instrument("ETH")])

        result = manager.sync([
            make_instrument("BTC"),
            make_instrument("ETH"),
        ])

        self.assertEqual(result["added"], [])
        self.assertEqual(result["removed"], [])
        self.assertEqual(set(result["kept"]), {"BTC", "ETH"})
        self.assertEqual(transport.subscribe_calls["BTC"], 1)
        self.assertEqual(transport.subscribe_calls["ETH"], 1)


class TestManagerFailureIsolation(unittest.TestCase):

    def test_a_and_c_continue_while_b_reconnects(self):
        """BTC and SOL keep delivering while ETH is disconnected and
        then restores independently."""

        delivered = []
        manager, transport, clock = make_manager(callback=delivered.append)

        manager.sync([
            make_instrument("BTC"),
            make_instrument("ETH"),
            make_instrument("SOL"),
        ])

        transport.down("ETH")

        self.assertEqual(
            manager.status("ETH").status,
            SubscriptionStatus.RECONNECTING,
        )
        self.assertEqual(
            manager.status("BTC").status,
            SubscriptionStatus.LIVE,
        )
        self.assertEqual(
            manager.status("SOL").status,
            SubscriptionStatus.LIVE,
        )

        # A and C keep flowing while B is down.
        transport.push("BTC", candle(timestamp=1, symbol="BTC"))
        transport.push("SOL", candle(timestamp=1, symbol="SOL"))

        self.assertEqual([c.symbol for c in delivered], ["BTC", "SOL"])

        # B reconnects independently; A and C are untouched.
        clock.advance(1.0)
        manager.poll()

        self.assertEqual(
            manager.status("ETH").status,
            SubscriptionStatus.LIVE,
        )
        self.assertEqual(
            manager.status("BTC").status,
            SubscriptionStatus.LIVE,
        )

        transport.push("ETH", candle(timestamp=2, symbol="ETH"))
        self.assertEqual(
            [c.symbol for c in delivered],
            ["BTC", "SOL", "ETH"],
        )

    def test_one_stream_failing_to_subscribe_does_not_kill_others(self):

        transport = FakeTransport(fail_on_subscribe=["ETH"])
        delivered = []
        manager, _, clock = make_manager(
            transport=transport,
            callback=delivered.append,
        )

        manager.sync([
            make_instrument("BTC"),
            make_instrument("ETH"),
            make_instrument("SOL"),
        ])

        self.assertEqual(
            manager.status("ETH").status,
            SubscriptionStatus.RECONNECTING,
        )
        self.assertEqual(
            manager.status("BTC").status,
            SubscriptionStatus.LIVE,
        )
        self.assertEqual(
            manager.status("SOL").status,
            SubscriptionStatus.LIVE,
        )

        transport.push("BTC", candle(timestamp=1, symbol="BTC"))
        self.assertEqual([c.symbol for c in delivered], ["BTC"])

        # The failing stream heals: subscription restored, no other
        # worker disturbed.
        transport._fail.discard("ETH")
        clock.advance(1.0)
        manager.poll()

        self.assertEqual(
            manager.status("ETH").status,
            SubscriptionStatus.LIVE,
        )

    def test_exhausted_stream_fails_alone(self):

        policy = ReconnectPolicy(base_delay=1.0, factor=1.0, max_attempts=1)
        transport = FakeTransport(fail_on_subscribe=["ETH"])
        manager, _, clock = make_manager(transport=transport, policy=policy)

        manager.sync([
            make_instrument("BTC"),
            make_instrument("ETH"),
        ])

        clock.advance(1.0)
        # poll isolates ReconnectExhausted: no exception escapes.
        manager.poll()

        self.assertEqual(
            manager.status("ETH").status,
            SubscriptionStatus.FAILED,
        )
        self.assertEqual(
            manager.status("BTC").status,
            SubscriptionStatus.LIVE,
        )
        self.assertTrue(manager.errors)

    def test_failed_worker_healed_on_next_universe_pass(self):
        """A FAILED subscription is re-subscribed the next time the
        same universe is synced (the diff treats it as re-ADD)."""

        transport = FakeTransport(fail_on_subscribe=["ETH"])
        policy = ReconnectPolicy(base_delay=1.0, factor=1.0, max_attempts=1)
        manager, _, clock = make_manager(transport=transport, policy=policy)

        manager.sync([make_instrument("BTC"), make_instrument("ETH")])
        clock.advance(1.0)
        manager.poll()

        self.assertEqual(
            manager.status("ETH").status,
            SubscriptionStatus.FAILED,
        )

        transport._fail.discard("ETH")
        result = manager.sync([make_instrument("BTC"), make_instrument("ETH")])

        self.assertEqual(
            manager.status("ETH").status,
            SubscriptionStatus.LIVE,
        )
        self.assertNotIn("ETH", result["kept"])
        self.assertIn("ETH", result["added"])


class TestManagerStopAll(unittest.TestCase):

    def test_stop_all_closes_transport(self):

        manager, transport, clock = make_manager()

        manager.sync([make_instrument("BTC"), make_instrument("ETH")])
        manager.stop_all()

        self.assertEqual(manager.count, 0)
        self.assertTrue(transport.closed)
        self.assertEqual(
            manager.status("BTC"),
            None,
        )

    def test_manager_restarts_transport_after_stop_all(self):
        """stop_all releases the shared connection; a later sync
        builds a fresh transport (no crawling zombie sockets)."""

        manager, transport, clock = make_manager()

        manager.sync([make_instrument("BTC")])
        manager.stop_all()
        manager.sync([make_instrument("BTC")])

        self.assertEqual(manager.symbols, ("BTC",))
        self.assertIsNotNone(manager.transport)


if __name__ == "__main__":

    unittest.main()