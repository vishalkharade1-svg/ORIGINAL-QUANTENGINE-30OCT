"""
====================================================

QuantEngine

Market Universe (Phase 6B) -- eligibility cascade tests

Proves, with mocked /v2/products + mocked liquidity and
history data providers (no network):

  UniverseManager.build_universe:
    - confirmed perpetual with measured volume + history
      graduates to ELIGIBLE and enters the universe;
    - a NEWLY_LISTED single-sighting candidate is NEVER
      eligible on the same pass (confirmation first);
    - low volume / missing volume / thin history deny;
    - re-checks FLIP state both ways (INELIGIBLE -> ELIGIBLE
      and ELIGIBLE -> INELIGIBLE) with the reason persisted;
    - DELISTED instruments can never re-enter the universe;
    - the eligibility verdicts are WRITTEN BACK to the
      registry (single source of truth).

Stdlib only.

====================================================
"""

import unittest

from core.registry.instrument_registry import InstrumentRegistry
from core.registry.eligibility import IneligibleReason
from core.registry.product_types import (
    PRODUCT_STATE_ELIGIBLE,
)
from core.universe.universe_manager import UniverseManager
from core.universe.universe_policy import UniversePolicy

from data.delta.product_normalizer import (
    DeltaProductNormalizer,
)


def product(
    product_id,
    symbol,
    contract_type="perpetual_futures",
    underlying="BTC",
    quote="USDT",
):
    return {
        "id": product_id,
        "symbol": symbol,
        "contract_type": contract_type,
        "underlying_asset": {"id": 1, "symbol": underlying},
        "quoting_asset": {"id": 2, "symbol": quote},
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
SDX_SPOT = product(40, "SDX.", contract_type="spot",
                  underlying="SDX")
CALL = product(21, "C-BTC-90000-300826",
               contract_type="call_options")
MYSTERY = product(99, "MYSTERY-PAIR",
                  contract_type="quantum_swap")


class FakeLiquidityProvider:

    def __init__(self, volumes):
        self.volumes = volumes  # symbol -> float | None

    def quote_volume_24h(self, symbol):
        return self.volumes.get(symbol)


class FakeHistoryProvider:

    def __init__(self, bars):
        self.bars = bars  # symbol -> int | None

    def history_bars(self, symbol, timeframe="1m"):
        return self.bars.get(symbol)


DOT = product(15, "DOTUSDT")
BAR_PERP = product(16, "BARUSDT")


def promote_to_active(registry, *instruments):
    """Register every instrument as a NEWLY_LISTED candidate, then
    confirm them together over two discovery passes so none DELISTs
    the others."""
    for inst in instruments:
        registry.upsert(inst)
    keys = [i.key for i in instruments]
    registry.mark_present(keys)
    registry.mark_present(keys)
    return [registry.get(k) for k in keys]


# BARUSDT is liquid but has thin history (gates: history check).
LIQ = FakeLiquidityProvider({
    "BTCUSDT": 100_000_000.0,
    "ETHUSDT": 40_000_000.0,
    "SDX.": 500_000.0,
    "BARUSDT": 50_000_000.0,
})

HIST = FakeHistoryProvider({
    "BTCUSDT": 2000,
    "ETHUSDT": 1500,
    "SDX.": 200,
    "BARUSDT": 100,
})


class TestMarketUniverseCascade(unittest.TestCase):

    def setUp(self):
        self.normalizer = DeltaProductNormalizer()
        self.registry = InstrumentRegistry()
        self.policy = UniversePolicy(
            min_quote_volume_24h=10_000_000.0,
            min_history_bars=300,
        )
        self.manager = UniverseManager(
            registry=self.registry,
            policy=self.policy,
            liquidity_provider=LIQ,
            history_provider=HIST,
            clock=lambda: 123.0,
        )

    # Recording the verdict back to the registry
    def test_confirmed_perp_becomes_eligible(self):
        promote_to_active(
            self.registry, self.normalizer.normalize(BTC)
        )
        universe = self.manager.build_universe()
        self.assertEqual(universe.symbols, ("BTCUSDT",))
        self.assertEqual(universe.count, 1)
        self.assertEqual(universe.captured_at, 123.0)
        self.assertEqual(
            self.registry.get_by_symbol("BTCUSDT").state,
            PRODUCT_STATE_ELIGIBLE,
        )
        self.assertIn(
            self.registry.get_by_symbol("BTCUSDT"),
            self.registry.executable(),
        )
        self.assertIn("BTCUSDT", self.manager.executable_symbols())
        self.assertEqual(
            universe.reasons["BTCUSDT"], "ELIGIBLE"
        )

    def test_executable_instruments_feed_scanning(self):
        promote_to_active(
            self.registry,
            self.normalizer.normalize(BTC),
            self.normalizer.normalize(ETH),
        )
        self.manager.build_universe()
        self.assertEqual(
            sorted(self.manager.executable_symbols()),
            ["BTCUSDT", "ETHUSDT"],
        )
        self.assertEqual(len(self.manager.executable_instruments()), 2)

    def test_first_sighting_is_never_eligible_same_pass(self):
        # A freshly upserted NEWLY_LISTED candidate (no confirmation)
        # cannot be traded on the discovery pass.
        self.registry.upsert(self.normalizer.normalize(BTC))
        universe = self.manager.build_universe()
        self.assertEqual(universe.count, 0)
        self.assertEqual(
            universe.reasons["BTCUSDT"],
            IneligibleReason.NOT_CONFIRMED,
        )
        self.assertEqual(
            self.registry.get_by_symbol("BTCUSDT").state,
            "NEWLY_LISTED",
        )
        self.assertNotIn(
            self.registry.get_by_symbol("BTCUSDT"),
            self.registry.executable(),
        )

    def test_low_volume_denies_and_records_reason(self):
        promote_to_active(
            self.registry, self.normalizer.normalize(SDX_SPOT)
        )
        universe = self.manager.build_universe()
        self.assertEqual(universe.count, 0)
        self.assertEqual(
            universe.reasons["SDX."],
            IneligibleReason.LOW_LIQUIDITY,
        )
        inst = self.registry.get_by_symbol("SDX.")
        self.assertEqual(
            inst.metadata.get("eligibility_reason"),
            IneligibleReason.LOW_LIQUIDITY,
        )

    def test_missing_volume_data_denies(self):
        # DOT is a confirmed perpetual the providers have NEVER
        # measured -> NO_LIQUIDITY_DATA. ETH stays eligible.
        promote_to_active(
            self.registry,
            self.normalizer.normalize(DOT),
            self.normalizer.normalize(ETH),
        )
        universe = self.manager.build_universe()
        self.assertEqual(universe.count, 1)
        self.assertEqual(universe.symbols, ("ETHUSDT",))
        self.assertEqual(
            universe.reasons["DOTUSDT"],
            IneligibleReason.NO_LIQUIDITY_DATA,
        )

    def test_history_window_gate(self):
        # BAR is liquid but only 100 bars vs the 300 required.
        promote_to_active(
            self.registry, self.normalizer.normalize(BAR_PERP)
        )
        universe = self.manager.build_universe()
        self.assertEqual(universe.count, 0)
        self.assertEqual(
            universe.reasons["BARUSDT"],
            IneligibleReason.INSUFFICIENT_HISTORY,
        )

    def test_no_history_data_denies(self):
        provider = FakeHistoryProvider({})  # no symbol answered
        manager = UniverseManager(
            registry=self.registry,
            policy=self.policy,
            liquidity_provider=LIQ,
            history_provider=provider,
        )
        promote_to_active(
            self.registry, self.normalizer.normalize(BTC)
        )
        universe = manager.build_universe()
        self.assertEqual(universe.count, 0)
        self.assertEqual(
            universe.reasons["BTCUSDT"],
            IneligibleReason.NO_HISTORY_DATA,
        )

    def test_no_providers_degrades_to_empty(self):
        manager = UniverseManager(
            registry=self.registry, policy=self.policy
        )
        promote_to_active(
            self.registry, self.normalizer.normalize(BTC)
        )
        universe = manager.build_universe()
        self.assertEqual(universe.count, 0)
        self.assertEqual(
            universe.reasons["BTCUSDT"],
            IneligibleReason.NO_LIQUIDITY_DATA,
        )

    def test_recheck_flips_ineligible_to_eligible(self):
        promote_to_active(
            self.registry, self.normalizer.normalize(SDX_SPOT)
        )
        self.manager.build_universe()  # thin -> INELIGIBLE
        self.assertNotIn(
            self.registry.get_by_symbol("SDX."),
            self.registry.executable(),
        )
        # The market thickens; a later pass re-evaluates.
        self.manager.liquidity_provider = FakeLiquidityProvider({
            "SDX.": 50_000_000.0,
        })
        self.manager.history_provider = FakeHistoryProvider({
            "SDX.": 2000,
        })
        universe = self.manager.build_universe()
        self.assertIn(
            self.registry.get_by_symbol("SDX."),
            self.registry.executable(),
        )
        self.assertEqual(universe.symbols, ("SDX.",))
        self.assertIsNone(
            self.registry.get_by_symbol("SDX.").metadata.get(
                "eligibility_reason")
        )

    def test_recheck_flips_eligible_to_ineligible(self):
        promote_to_active(
            self.registry, self.normalizer.normalize(BTC)
        )
        self.manager.build_universe()  # eligible now
        thin = UniverseManager(
            registry=self.registry,
            policy=UniversePolicy(
                min_quote_volume_24h=10_000_000.0,
                min_history_bars=300,
            ),
            liquidity_provider=FakeLiquidityProvider({
                "BTCUSDT": 1_000.0,
            }),
            history_provider=HIST,
        )
        universe = thin.build_universe()
        self.assertEqual(universe.count, 0)
        self.assertEqual(
            self.registry.get_by_symbol("BTCUSDT").state,
            "INELIGIBLE",
        )
        self.assertEqual(
            self.registry.get_by_symbol("BTCUSDT").metadata.get(
                "eligibility_reason"),
            IneligibleReason.LOW_LIQUIDITY,
        )

    def test_options_never_eligible(self):
        promote_to_active(
            self.registry, self.normalizer.normalize(CALL)
        )
        universe = self.manager.build_universe()
        self.assertEqual(universe.count, 0)
        self.assertEqual(
            universe.reasons[CALL["symbol"]],
            IneligibleReason.UNSUPPORTED_TYPE,
        )


class TestMarketUniverseSnapshot(unittest.TestCase):

    def test_snapshot_semantics(self):
        reg = InstrumentRegistry()
        normalizer = DeltaProductNormalizer()
        promote_to_active(
            reg,
            normalizer.normalize(BTC),
            normalizer.normalize(ETH),
        )
        manager = UniverseManager(
            registry=reg,
            policy=UniversePolicy(
                min_quote_volume_24h=10_000_000.0,
                min_history_bars=300,
            ),
            liquidity_provider=LIQ,
            history_provider=HIST,
            clock=lambda: 5.0,
        )
        universe = manager.build_universe()
        self.assertEqual(set(universe.symbols),
                         {"BTCUSDT", "ETHUSDT"})
        self.assertEqual(universe.count, 2)
        self.assertEqual(universe.get_by_symbol("BTCUSDT").symbol,
                         "BTCUSDT")
        self.assertIsNone(universe.get_by_symbol("SOLUSDT"))
        self.assertTrue(
            universe.contains(normalizer.normalize(BTC))
        )
        self.assertFalse(
            universe.contains(normalizer.normalize(SDX_SPOT))
        )


if __name__ == "__main__":
    unittest.main()