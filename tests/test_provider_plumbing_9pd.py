"""
====================================================

QuantEngine

Provider Plumbing (Phase 9P-d) tests

Validates that the missing LIVE LIQUIDITY / HISTORY provider
plumbing now feeds the CANONICAL Phase 6B eligibility cascade
-- without touching the universe architecture:

  REAL/NORMALIZED PROVIDER DATA
      -> canonical UniverseManager (InstrumentRegistry +
         InstrumentEligibility gate cascade)
      -> the ELIGIBLE multi-symbol set
      -> SymbolPipeline reconciliation / subscriptions (engine)

Code verified with MOCKED Delta responses (offline, zero
network). NEVER treats missing data as eligible: a symbol with
no / unmeasurable turnover or history is DENIED, not assumed
liquid or sufficiently-historied. The default explicit-symbol
fallback (UNIVERSE="explicit") is preserved.

Stdlib only.

====================================================
"""

import unittest

from config.settings import settings

from core.registry.instrument_registry import InstrumentRegistry
from core.registry.eligibility import IneligibleReason
from core.registry.instrument import Instrument
from core.registry.product_types import (
    PRODUCT_STATE_ELIGIBLE,
    PRODUCT_STATE_NEWLY_LISTED,
)
from core.universe.liquidity_provider import (
    DeltaLiquidityProvider,
    _to_float_or_none,
    TICKERS_ENDPOINT,
)
from core.universe.history_provider import DeltaHistoryProvider
from core.universe.universe_policy import UniversePolicy
from core.universe.universe_manager import UniverseManager
from core.runtime.paper_main import (
    build_paper_engine,
    build_provider_universe_manager,
    provider_policy,
    _configured_float,
    _configured_int,
    ExplicitSymbolUniverseManager,
)


# =====================================================
# Fakes (offline, no network)
# =====================================================


class FakeTransport:
    """Mirrors DeltaREST.get(endpoint, params=None); records the
    requested endpoints so tests assert the provider talks to the
    real, documented Delta surface (no invented endpoints)."""

    def __init__(self, payload=None, error=None):
        self.payload = payload
        self.error = error
        self.calls = []

    def get(self, endpoint, params=None, headers=None):
        self.calls.append((endpoint, params))
        if self.error is not None:
            raise self.error
        return self.payload


class FakeHistory:
    """Mirrors DeltaHistory.candles(symbol, resolution, days=...)."""

    def __init__(self, counts=None, error=None):
        self.counts = counts or {}  # (symbol, timeframe) -> count
        self.error = error
        self.calls = []

    def candles(self, symbol, resolution="1m", days=None, **kwargs):
        self.calls.append((symbol, resolution, days))
        if self.error is not None:
            raise self.error
        count = self.counts.get((symbol, resolution), 0)
        return [None] * count


def ticker_row(symbol, turnover_usd):
    return {"symbol": symbol, "turnover_usd": turnover_usd}


def make_instrument(symbol, product_type="PERPETUAL",
                    instrument_id=None, trading_enabled=True):
    return Instrument(
        instrument_id=instrument_id or symbol,
        symbol=symbol,
        exchange="DELTA",
        product_type=product_type,
        underlying_asset=symbol,
        quote_asset="USDT",
        tick_size=0.5,
        quantity_step=1.0,
        minimum_quantity=0.001,
        trading_enabled=trading_enabled,
        state=PRODUCT_STATE_NEWLY_LISTED,
    )


def promote_to_active(registry, *instruments):
    for inst in instruments:
        registry.upsert(inst)
    keys = [i.key for i in instruments]
    registry.mark_present(keys)
    registry.mark_present(keys)
    return [registry.get(k) for k in keys]


# =====================================================
# LiquidityProvider
# =====================================================


class TestLiquidityProvider(unittest.TestCase):

    def test_parses_string_turnover_to_float(self):
        payload = {"result": [
            ticker_row("BTCUSDT", "3083174.2395"),
            ticker_row("ETHUSDT", "4202142.863000001"),
        ]}
        provider = DeltaLiquidityProvider(
            transport=FakeTransport(payload=payload),
        )
        self.assertTrue(provider.refresh())
        self.assertEqual(
            provider.quote_volume_24h("BTCUSDT"), 3083174.2395,
        )
        self.assertEqual(
            provider.quote_volume_24h("ETHUSDT"), 4202142.863000001,
        )

    def test_uses_real_documented_tickers_endpoint(self):
        transport = FakeTransport(payload={"result": []})
        provider = DeltaLiquidityProvider(transport=transport)
        provider.refresh()
        self.assertTrue(
            any(ep == TICKERS_ENDPOINT for ep, _ in transport.calls),
        )

    def test_empty_turnover_is_none_not_eligible(self):
        payload = {"result": [
            ticker_row("BTCUSDT", ""),       # inactive -> empty string
        ]}
        provider = DeltaLiquidityProvider(
            transport=FakeTransport(payload=payload),
        )
        provider.refresh()
        self.assertIsNone(provider.quote_volume_24h("BTCUSDT"))

    def test_missing_symbol_is_none(self):
        provider = DeltaLiquidityProvider(
            transport=FakeTransport(payload={"result": [
                ticker_row("BTCUSDT", "123.0"),
            ]}),
        )
        provider.refresh()
        self.assertIsNone(provider.quote_volume_24h("NOTLISTED"))

    def test_zero_turnover_is_none(self):
        provider = DeltaLiquidityProvider(
            transport=FakeTransport(payload={"result": [
                ticker_row("BTCUSDT", "0"),
            ]}),
        )
        provider.refresh()
        self.assertIsNone(provider.quote_volume_24h("BTCUSDT"))

    def test_invalid_turnover_is_none(self):
        for bad in ("not-a-number", None, [], {}, True):
            self.assertIsNone(_to_float_or_none(bad))
        self.assertEqual(_to_float_or_none("12.5"), 12.5)

    def test_transport_failure_returns_false_no_raise(self):
        provider = DeltaLiquidityProvider(
            transport=FakeTransport(
                payload=None, error=RuntimeError("boom"),
            ),
        )
        self.assertFalse(provider.refresh())
        self.assertIsNone(provider.quote_volume_24h("BTCUSDT"))

    def test_refresh_repopulates_snapshot(self):
        provider = DeltaLiquidityProvider(
            transport=FakeTransport(payload={"result": [
                ticker_row("BTCUSDT", "100.0"),
            ]}),
        )
        provider.refresh()
        self.assertEqual(provider.quote_volume_24h("BTCUSDT"), 100.0)

    def test_fetch_callback_injectable(self):
        calls = []

        def fetch():
            calls.append(1)
            return {"result": [ticker_row("BTCUSDT", "77.0")]}

        provider = DeltaLiquidityProvider(fetch=fetch)
        provider.refresh()
        self.assertEqual(calls, [1])
        self.assertEqual(provider.quote_volume_24h("BTCUSDT"), 77.0)


# =====================================================
# HistoryProvider
# =====================================================


class TestHistoryProvider(unittest.TestCase):

    def test_returns_bar_count_from_real_history(self):
        fake = FakeHistory(counts={("BTCUSDT", "1m"): 1440})
        provider = DeltaHistoryProvider(history=fake)
        self.assertEqual(provider.history_bars("BTCUSDT", "1m"), 1440)
        self.assertEqual(fake.calls, [("BTCUSDT", "1m", 7)])

    def test_passes_lookback_days_through(self):
        fake = FakeHistory(counts={("ETHUSDT", "5m"): 100})
        provider = DeltaHistoryProvider(history=fake, lookback_days=30)
        provider.history_bars("ETHUSDT", "5m")
        self.assertEqual(fake.calls, [("ETHUSDT", "5m", 30)])

    def test_zero_bars_is_measured_zero(self):
        fake = FakeHistory(counts={})
        provider = DeltaHistoryProvider(history=fake)
        self.assertEqual(provider.history_bars("BTCUSDT", "1m"), 0)

    def test_error_returns_none(self):
        fake = FakeHistory(error=RuntimeError("network"))
        provider = DeltaHistoryProvider(history=fake)
        self.assertIsNone(provider.history_bars("BTCUSDT", "1m"))
        self.assertEqual(len(provider.errors), 1)


# =====================================================
# Policy + threshold coercion
# =====================================================


class TestProviderPolicy(unittest.TestCase):

    def test_configured_float(self):
        self.assertIsNone(_configured_float(None))
        self.assertIsNone(_configured_float(""))
        self.assertIsNone(_configured_float("   "))
        self.assertEqual(_configured_float("10_000_000"), 10000000.0)

    def test_configured_float_invalid_raises(self):
        with self.assertRaises(ValueError):
            _configured_float("garbage")

    def test_configured_int(self):
        self.assertIsNone(_configured_int(None))
        self.assertIsNone(_configured_int(""))
        self.assertEqual(_configured_int("300"), 300)

    def test_configured_int_invalid_raises(self):
        with self.assertRaises(ValueError):
            _configured_int("12.5")

    def test_provider_policy_unconfigured_requires_no_history(self):
        policy = provider_policy()
        self.assertFalse(policy.requires_history)


# =====================================================
# Provider-backed manager assembly + full cascade
# =====================================================


class FakeLiquidity:
    def __init__(self, volumes):
        self.volumes = volumes

    def quote_volume_24h(self, symbol):
        return self.volumes.get(symbol)


class FakeHist:
    def __init__(self, bars):
        self.bars = bars

    def history_bars(self, symbol, timeframe="1m"):
        return self.bars.get(symbol)


def build_registry_with(*instruments):
    registry = InstrumentRegistry()
    promote_to_active(registry, *instruments)
    return registry


class TestProviderManagerAssembly(unittest.TestCase):

    def test_builds_canonical_manager_with_real_providers(self):
        mgr, reg, liq, hist = build_provider_universe_manager()
        self.assertIsInstance(mgr, UniverseManager)
        self.assertIsInstance(liq, DeltaLiquidityProvider)
        self.assertIsInstance(hist, DeltaHistoryProvider)
        self.assertIs(liq, mgr.liquidity_provider)
        self.assertIs(hist, mgr.history_provider)

    def test_delegates_to_real_providers_when_none_injected(self):
        mgr, reg, liq, hist = build_provider_universe_manager()
        # build_universe() must ask the injected real providers,
        # not a conditionless fallback: with no discovered
        # instruments the cascade stays empty, never "everything
        # goes".
        universe = mgr.build_universe(timeframe="1m")
        self.assertEqual(universe.count, 0)


class TestProviderCascadeToEligibleSet(unittest.TestCase):
    """The critical acceptance path: real/normalized provider data
    -> canonical UniverseManager -> eligibility cascade -> the
    ELIGIBLE multi-symbol set."""

    def setUp(self):
        self.btc = make_instrument("BTCUSDT")
        self.eth = make_instrument("ETHUSDT")
        self.registry = build_registry_with(self.btc, self.eth)
        self.policy = UniversePolicy(
            min_quote_volume_24h=1_000_000.0,
            min_history_bars=300,
        )
        self.manager = UniverseManager(
            registry=self.registry,
            policy=self.policy,
            liquidity_provider=FakeLiquidity({
                "BTCUSDT": 3_000_000.0,
                "ETHUSDT": 4_000_000.0,
            }),
            history_provider=FakeHist({
                "BTCUSDT": 1440,
                "ETHUSDT": 1440,
            }),
        )

    def test_provider_data_drives_eligible_multi_symbol_set(self):
        universe = self.manager.build_universe()
        self.assertEqual(set(universe.symbols), {"BTCUSDT", "ETHUSDT"})
        self.assertEqual(universe.count, 2)
        for key in (self.btc.key, self.eth.key):
            self.assertEqual(
                self.registry.get(key).state, PRODUCT_STATE_ELIGIBLE,
            )

    def test_low_volume_is_denied_not_assumed_eligible(self):
        manager = UniverseManager(
            registry=self.registry,
            policy=UniversePolicy(min_quote_volume_24h=10_000_000.0),
            liquidity_provider=FakeLiquidity({
                "BTCUSDT": 500_000.0, "ETHUSDT": 500_000.0,
            }),
        )
        universe = manager.build_universe()
        self.assertEqual(universe.count, 0)
        self.assertEqual(
            self.registry.get_by_symbol("BTCUSDT").state,
            "INELIGIBLE",
        )

    def test_missing_volume_is_none_deny(self):
        manager = UniverseManager(
            registry=self.registry,
            policy=UniversePolicy(),
            liquidity_provider=FakeLiquidity({
                "BTCUSDT": 3_000_000.0,  # ETH missing entirely
            }),
        )
        universe = manager.build_universe()
        self.assertEqual(universe.symbols, ("BTCUSDT",))
        self.assertEqual(
            self.registry.get_by_symbol("ETHUSDT").state,
            "INELIGIBLE",
        )

    def test_missing_history_is_deny_when_configured(self):
        manager = UniverseManager(
            registry=self.registry,
            policy=UniversePolicy(min_history_bars=300),
            liquidity_provider=FakeLiquidity({
                "BTCUSDT": 3_000_000.0, "ETHUSDT": 4_000_000.0,
            }),
            history_provider=FakeHist({"BTCUSDT": 1440}),
        )
        universe = manager.build_universe()
        self.assertEqual(universe.symbols, ("BTCUSDT",))
        self.assertEqual(
            self.registry.get_by_symbol("ETHUSDT").state,
            "INELIGIBLE",
        )


class TestPaperEngineProviderMode(unittest.TestCase):

    def test_explicit_fallback_default_preserved(self):
        engine, manager = build_paper_engine()
        self.assertIsInstance(manager, ExplicitSymbolUniverseManager)

    def test_provider_mode_builds_canonical_manager(self):
        engine, manager = build_paper_engine(
            universe_mode="provider",
            registry=build_registry_with(
                make_instrument("BTCUSDT"),
            ),
            liquidity_provider=FakeLiquidity(
                {"BTCUSDT": 3_000_000.0},
            ),
            history_provider=FakeHist({"BTCUSDT": 1440}),
        )
        self.assertIsInstance(manager, UniverseManager)
        # the injected providers are the ones feeding the cascade
        self.assertEqual(
            manager.liquidity_provider.quote_volume_24h("BTCUSDT"),
            3_000_000.0,
        )
        engine.stop()

    def test_provider_mode_invalid_threshold_raises(self):
        original = settings.MIN_QUOTE_VOLUME_24H
        try:
            settings.MIN_QUOTE_VOLUME_24H = "NaN"
            with self.assertRaises(ValueError):
                build_provider_universe_manager()
        finally:
            settings.MIN_QUOTE_VOLUME_24H = original

    def test_provider_mode_threshold_applied(self):
        original = settings.MIN_QUOTE_VOLUME_24H
        original_bars = settings.MIN_HISTORY_BARS
        try:
            settings.MIN_QUOTE_VOLUME_24H = "10000000"
            settings.MIN_HISTORY_BARS = "300"
            policy = provider_policy()
            self.assertEqual(policy.min_quote_volume_24h, 10000000.0)
            self.assertEqual(policy.min_history_bars, 300)
            self.assertTrue(policy.requires_history)
        finally:
            settings.MIN_QUOTE_VOLUME_24H = original
            settings.MIN_HISTORY_BARS = original_bars


if __name__ == "__main__":
    unittest.main()
