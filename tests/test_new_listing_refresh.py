"""
====================================================

QuantEngine

New Listing Refresh + Refresh Scheduler (Phase 6B)

Proves, with a mocked /v2/products transport + a fake
clock:

  UniverseManager full heartbeat (discovery -> eligibility):
    - a brand-new product appears in a LATER exchange pass,
      is detected, becomes ACTIVE the pass after, and only
      THEN graduates to ELIGIBLE -- no first-pass trading;
    - a product that disappears is DELISTED and can never
      re-enter the universe on provider data alone;
    - repeated passes never duplicate catalog entries.

  RefreshScheduler:
    - due / run_if_due on an interval (fake clock);
    - interval <= 0 -> always due;
    - force_refresh runs regardless of the clock;
    - a failed pass is recorded and never kills the loop.

Stdlib only.

====================================================
"""

import unittest

from core.registry.instrument_registry import InstrumentRegistry
from core.universe.refresh_scheduler import RefreshScheduler
from core.universe.universe_manager import UniverseManager
from core.universe.universe_policy import UniversePolicy

from data.delta.product_client import ProductClient
from data.delta.product_normalizer import (
    DeltaProductNormalizer,
)


def product(product_id, symbol):
    return {
        "id": product_id,
        "symbol": symbol,
        "contract_type": "perpetual_futures",
        "underlying_asset": {"id": 1, "symbol": symbol.replace(
            "USDT", "")},
        "quoting_asset": {"id": 2, "symbol": "USDT"},
        "tick_size": 0.5,
        "contract_value": 1.0,
        "minimum_order_size": 0.001,
        "price_precision": 2,
        "contract_value_precision": 3,
        "is_delisted": False,
        "is_disabled": False,
        "is_unlisted": False,
        "state": "live",
    }


BTC = product(2, "BTCUSDT")
ETH = product(7, "ETHUSDT")
SOL = product(11, "SOLUSDT")


class FakeTransport:

    def __init__(self, products):
        self.products = list(products)

    def get(self, endpoint, params=None):
        return {"result": [dict(p) for p in self.products]}


class FakeClock:

    def __init__(self, now=0.0):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class RichLiquidity:

    def quote_volume_24h(self, symbol):
        return {
            "BTCUSDT": 100_000_000.0,
            "ETHUSDT": 40_000_000.0,
            "SOLUSDT": 60_000_000.0,
        }.get(symbol, None)


class RichHistory:

    def history_bars(self, symbol, timeframe="1m"):
        return 3000


class TestNewListingRefresh(unittest.TestCase):

    def setUp(self):
        self.registry = InstrumentRegistry()
        self.manager = UniverseManager(
            registry=self.registry,
            policy=UniversePolicy(
                min_quote_volume_24h=10_000_000.0,
                min_history_bars=300,
            ),
            liquidity_provider=RichLiquidity(),
            history_provider=RichHistory(),
        )

    def test_new_listing_graduates_only_after_confirmation(self):
        transport = FakeTransport([BTC, ETH])
        client = ProductClient(transport=transport)

        # Pass 1: BTC + ETH are brand-new single sightings.
        universe = self.manager.refresh(
            client=client, run_discovery=True
        )
        self.assertEqual(universe.count, 0)
        self.assertFalse(self.manager.executable_symbols())

        # Pass 2: confirmed -> ACTIVE -> gates pass -> ELIGIBLE.
        universe = self.manager.refresh(
            client=client, run_discovery=True
        )
        self.assertEqual(set(universe.symbols),
                         {"BTCUSDT", "ETHUSDT"})

        # Pass 3: a NEWLY LISTED product appears (SOL). It is
        # detected THIS pass but must NOT be tradable yet.
        transport.products = [BTC, ETH, SOL]
        universe = self.manager.refresh(
            client=client, run_discovery=True
        )
        self.assertNotIn("SOLUSDT", universe.symbols)
        self.assertNotIn(
            "SOLUSDT", self.manager.executable_symbols())
        self.assertEqual(
            self.registry.get_by_symbol("SOLUSDT").state,
            "NEWLY_LISTED",
        )

        # Pass 4: SOL confirmed -> ACTIVE -> ELIGIBLE.
        universe = self.manager.refresh(
            client=client, run_discovery=True
        )
        self.assertIn("SOLUSDT", universe.symbols)
        self.assertIn(
            "SOLUSDT", self.manager.executable_symbols())
        self.assertEqual(
            self.registry.get_by_symbol("SOLUSDT").state,
            "ELIGIBLE",
        )

    def test_delisted_cannot_reenable_via_provider_data(self):
        transport = FakeTransport([BTC, ETH])
        client = ProductClient(transport=transport)
        for _ in range(2):
            self.manager.refresh(client=client, run_discovery=True)

        self.assertEqual(
            set(self.manager.executable_symbols()),
            {"BTCUSDT", "ETHUSDT"},
        )

        # ETH vanishes from the exchange catalog.
        transport.products = [BTC]
        universe = self.manager.refresh(
            client=client, run_discovery=True
        )
        self.assertEqual(universe.symbols, ("BTCUSDT",))
        self.assertEqual(
            self.registry.get_by_symbol("ETHUSDT").state,
            "DELISTED",
        )

        # Provider data alone never revives a DELISTED product.
        self.manager.registry.mark_present([
            self.registry.get_by_symbol("BTCUSDT").key,
        ])
        universe = self.manager.build_universe()
        self.assertNotIn("ETHUSDT", universe.symbols)
        self.assertEqual(
            self.registry.get_by_symbol("ETHUSDT").state,
            "DELISTED",
        )

    def test_refresh_never_duplicates_catalog(self):
        transport = FakeTransport([BTC])
        client = ProductClient(transport=transport)
        for _ in range(5):
            self.manager.refresh(client=client, run_discovery=True)
        self.assertEqual(len(self.registry), 1)
        self.assertEqual(
            self.registry.get_by_symbol("BTCUSDT").state,
            "ELIGIBLE",
        )

    def test_refresh_without_discovery_runs_eligibility_only(self):
        transport = FakeTransport([BTC])
        client = ProductClient(transport=transport)
        # Pass 1 discovers (NEWLY_LISTED), pass 2 confirms (ACTIVE
        # -> ELIGIBLE under the rich providers).
        self.manager.refresh(client=client, run_discovery=True)
        self.manager.refresh(client=client, run_discovery=True)
        universe = self.manager.refresh(run_discovery=False)
        self.assertEqual(universe.count, 1)
        # The eligibility-only pass recomputes the cut but never
        # mutates the persistent catalog.
        self.assertEqual(len(self.registry), 1)


class TestRefreshScheduler(unittest.TestCase):

    def setUp(self):
        self.registry = InstrumentRegistry()
        self.clock = FakeClock(0.0)
        self.manager = UniverseManager(
            registry=self.registry,
            policy=UniversePolicy(
                min_quote_volume_24h=10_000_000.0,
                min_history_bars=300,
            ),
            liquidity_provider=RichLiquidity(),
            history_provider=RichHistory(),
        )
        # Every scheduler pass needs an injected transport -- the
        # schedule engine itself must never hit the network in tests.
        self.client = ProductClient(
            transport=FakeTransport([BTC])
        )

    def test_run_if_due_honors_interval(self):
        scheduler = RefreshScheduler(
            self.manager, interval_seconds=60, clock=self.clock)
        self.assertTrue(scheduler.due)  # first run
        scheduler.run_if_due(client=self.client)
        self.assertEqual(scheduler.runs, 1)
        self.assertFalse(scheduler.due)  # not 60s yet
        self.assertIsNone(scheduler.run_if_due(client=self.client))
        self.assertEqual(scheduler.runs, 1)
        self.clock.advance(60)
        self.assertTrue(scheduler.due)
        scheduler.run_if_due(client=self.client)
        self.assertEqual(scheduler.runs, 2)

    def test_zero_interval_is_always_due(self):
        scheduler = RefreshScheduler(
            self.manager, interval_seconds=0, clock=self.clock)
        scheduler.run_if_due(client=self.client)
        scheduler.run_if_due(client=self.client)
        self.assertEqual(scheduler.runs, 2)

    def test_force_refresh_ignores_clock(self):
        scheduler = RefreshScheduler(
            self.manager, interval_seconds=3600, clock=self.clock)
        scheduler.force_refresh(client=self.client)
        scheduler.force_refresh(client=self.client)
        self.assertEqual(scheduler.runs, 2)

    def test_failed_discovery_is_recorded_and_loop_continues(self):
        # A throwing transport must not kill the scheduler loop.
        class BombingTransport(FakeTransport):

            def get(self, endpoint, params=None):
                raise RuntimeError("exchange down")

        client = ProductClient(transport=BombingTransport([BTC]))
        scheduler = RefreshScheduler(
            self.manager, interval_seconds=-1, clock=self.clock)
        universe = scheduler.run_if_due(client=client)
        # The refresh pass errored; the scheduler records it and the
        # eligibility pass still produced a verdict (empty).
        self.assertIsNotNone(universe)
        self.assertEqual(universe.count, 0)
        self.assertEqual(len(scheduler.errors), 1)
        scheduler.run_if_due(client=client)
        self.assertEqual(len(scheduler.errors), 2)
        self.assertEqual(scheduler.runs, 2)


if __name__ == "__main__":
    unittest.main()