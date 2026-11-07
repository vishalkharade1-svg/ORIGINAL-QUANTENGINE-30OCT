"""
====================================================

QuantEngine

Phase 6A -- Instrument Discovery (mocked Delta)

Proves with mocked /v2/products responses (no network):

  ProductClient      -- fetch / fetch_cached / cache TTL
  DeltaProductNormalizer -- canonical Instrument fidelity
                          (perps vs options vs spot vs unknown,
                          trading_enabled from disable flags)
  ProductDiscovery   -- refresh_instrument_registry() end-to-end:
                          discover -> normalize -> upsert ->
                          mark_present -> save
  InstrumentRegistry -- lifecycle states (NEWLY_LISTED -> ACTIVE),
                          new-listing detection on a later pass,
                          graceful DELISTED, persistence round-trip
  InstrumentEligibility -- gates 1-4 + the NO_LIQUIDITY_DATA
                          safety default (never trade unmeasured)

Stdlib only -- a FakeTransport stands in for DeltaREST.

====================================================
"""

import json
import os
import tempfile
import unittest
from unittest import mock

from core.registry.instrument import Instrument
from core.registry.instrument_registry import InstrumentRegistry
from core.registry.eligibility import (
    InstrumentEligibility,
    IneligibleReason,
    run_basic_gates,
)
from core.registry.product_types import (
    PRODUCT_CALL_OPTION,
    PRODUCT_PERPETUAL,
    PRODUCT_SPOT,
    PRODUCT_STATE_ACTIVE,
    PRODUCT_STATE_DELISTED,
    PRODUCT_STATE_ELIGIBLE,
    PRODUCT_STATE_INELIGIBLE,
    PRODUCT_STATE_NEWLY_LISTED,
    PRODUCT_UNKNOWN,
)

from data.delta.product_client import ProductClient
from data.delta.product_normalizer import (
    DeltaProductNormalizer,
)
from data.delta.product_discovery import (
    refresh_instrument_registry,
)


# -------------------------------------------------
# Realistic mocked Delta /v2/products fixtures
# -------------------------------------------------

def product(
    product_id,
    symbol,
    contract_type="perpetual_futures",
    underlying="BTC",
    quote="USDT",
    tick_size=0.5,
    contract_value=1.0,
    minimum_order_size=0.001,
    is_delisted=False,
    is_disabled=False,
    is_unlisted=False,
    state="live",
    strike_price=None,
    expiry_time=None,
):
    return {
        "id": product_id,
        "symbol": symbol,
        "contract_type": contract_type,
        "underlying_asset": {"id": 1, "symbol": underlying},
        "quoting_asset": {"id": 2, "symbol": quote},
        "tick_size": tick_size,
        "contract_value": contract_value,
        "minimum_order_size": minimum_order_size,
        "price_precision": 2,
        "contract_value_precision": 3,
        "is_delisted": is_delisted,
        "is_disabled": is_disabled,
        "is_unlisted": is_unlisted,
        "state": state,
        "strike_price": strike_price,
        "expiry_time": expiry_time,
        "is_linear": True,
    }


BTC_PERP = product(2, "BTCUSDT")
ETH_PERP = product(7, "ETHUSDT")
SOL_PERP = product(11, "SOLUSDT")
BTC_CALL = product(
    21,
    "C-BTC-90000-300826",
    contract_type="call_options",
    underlying="BTC",
    strike_price=90000,
)
SDX_SPOT = product(
    40,
    "SDX.",
    contract_type="spot",
    underlying="SDX",
    tick_size=0.001,
)
AAPL_SPOT = product(
    62,
    "AAPL.",
    contract_type="spot",
    underlying="AAPL",
    tick_size=0.01,
)
MYSTERY = product(99, "MYSTERY-PAIR", contract_type="quantum_swap")
DELISTED = product(
    300,
    "OLDUSDT",
    is_delisted=True,
    state="archived",
)


class FakeTransport:

    def __init__(self, products):
        self.calls = 0
        self._products = products

    def get(self, endpoint, params=None):
        self.calls += 1
        return {"result": [dict(p) for p in self._products]}


# ==========================================================
# ProductClient
# ==========================================================


class TestProductClient(unittest.TestCase):

    def test_fetch_returns_result_rows(self):
        transport = FakeTransport([BTC_PERP, ETH_PERP])
        client = ProductClient(transport=transport)
        rows = client.fetch()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["symbol"], "BTCUSDT")
        self.assertEqual(rows[1]["symbol"], "ETHUSDT")

    def test_fetch_cached_obeys_ttl(self):
        transport = FakeTransport([BTC_PERP])
        client = ProductClient(transport=transport, cache_ttl=60)
        client.fetch_cached()
        client.fetch_cached()
        self.assertEqual(transport.calls, 1)
        client.clear_cache()
        client.fetch_cached()
        self.assertEqual(transport.calls, 2)

    def test_no_cache_when_ttl_zero(self):
        transport = FakeTransport([BTC_PERP])
        client = ProductClient(transport=transport)
        client.fetch_cached()
        client.fetch_cached()
        self.assertEqual(transport.calls, 2)


# ==========================================================
# Normalizer
# ==========================================================


class TestDeltaProductNormalizer(unittest.TestCase):

    def setUp(self):
        self.normalizer = DeltaProductNormalizer()

    def test_normalizes_perp_instrument(self):
        inst = self.normalizer.normalize(BTC_PERP)
        self.assertIsInstance(inst, Instrument)
        self.assertEqual(inst.symbol, "BTCUSDT")
        self.assertEqual(inst.exchange, "DELTA")
        self.assertEqual(inst.product_type, PRODUCT_PERPETUAL)
        self.assertEqual(inst.underlying_asset, "BTC")
        self.assertEqual(inst.quote_asset, "USDT")
        self.assertEqual(inst.tick_size, 0.5)
        self.assertEqual(inst.instrument_id, "2")
        self.assertTrue(inst.trading_enabled)
        self.assertTrue(inst.valid_precision)

    def test_normalizes_option_instrument(self):
        inst = self.normalizer.normalize(BTC_CALL)
        self.assertEqual(inst.product_type, PRODUCT_CALL_OPTION)
        self.assertEqual(inst.option_type, "call")
        self.assertEqual(inst.strike_price, 90000)

    def test_normalizes_spot_instrument(self):
        inst = self.normalizer.normalize(AAPL_SPOT)
        self.assertEqual(inst.product_type, PRODUCT_SPOT)
        self.assertTrue(inst.trading_enabled)

    def test_delisted_product_is_not_trading_enabled(self):
        inst = self.normalizer.normalize(DELISTED)
        self.assertFalse(inst.trading_enabled)

    def test_unknown_contract_type_is_still_normalized(self):
        inst = self.normalizer.normalize(MYSTERY)
        self.assertEqual(inst.product_type, PRODUCT_UNKNOWN)
        self.assertEqual(inst.symbol, "MYSTERY-PAIR")

    def test_round_price_uses_tick_size(self):
        inst = self.normalizer.normalize(BTC_PERP)
        self.assertEqual(inst.round_price(70324.37), 70324.5)
        self.assertEqual(inst.round_price(70324.0), 70324.0)


# ==========================================================
# Registry lifecycle
# ==========================================================


class TestInstrumentRegistryLifecycle(unittest.TestCase):

    def test_first_seen_is_newly_listed_then_active(self):
        registry = InstrumentRegistry()
        normalizer = DeltaProductNormalizer()
        inst, first = registry.upsert(normalizer.normalize(ETH_PERP))
        self.assertTrue(first)
        self.assertEqual(inst.state, PRODUCT_STATE_NEWLY_LISTED)

        again, first2 = registry.upsert(normalizer.normalize(ETH_PERP))
        self.assertFalse(first2)
        self.assertEqual(again.state, PRODUCT_STATE_ACTIVE)

    def test_state_flip_after_economics_change(self):
        registry = InstrumentRegistry()
        normalizer = DeltaProductNormalizer()
        registry.upsert(normalizer.normalize(ETH_PERP))
        changed = product(7, "ETHUSDT", tick_size=1.0)
        again, first2 = registry.upsert(normalizer.normalize(changed))
        self.assertFalse(first2)
        self.assertEqual(again.state, PRODUCT_STATE_NEWLY_LISTED)

    def test_graceful_delisting(self):
        registry = InstrumentRegistry()
        normalizer = DeltaProductNormalizer()
        registry.upsert(normalizer.normalize(BTC_PERP))
        registry.upsert(normalizer.normalize(ETH_PERP))
        registry.mark_present(
            [registry.get_by_symbol("BTCUSDT").key]
        )
        btc = registry.get_by_symbol("BTCUSDT")
        eth = registry.get_by_symbol("ETHUSDT")
        # A first sighting is a candidate, not yet confirmed; the
        # product absent from this pass is DELISTED.
        self.assertEqual(btc.state, PRODUCT_STATE_NEWLY_LISTED)
        self.assertEqual(eth.state, PRODUCT_STATE_DELISTED)

        # A later pass that confirms BTC brings it to ACTIVE.
        registry.mark_present([btc.key])
        self.assertEqual(registry.get_by_symbol("BTCUSDT").state,
                         PRODUCT_STATE_ACTIVE)

    def test_eligibility_transitions(self):
        registry = InstrumentRegistry()
        registry.upsert(
            DeltaProductNormalizer().normalize(BTC_PERP)
        )
        inst = registry.get_by_symbol("BTCUSDT")
        registry.mark_eligible(inst.key)
        self.assertEqual(inst.state, PRODUCT_STATE_ELIGIBLE)
        registry.mark_ineligible(inst.key, "thin")
        self.assertEqual(inst.state, PRODUCT_STATE_INELIGIBLE)
        self.assertEqual(inst.metadata.get("eligibility_reason"), "thin")

    def test_delisted_relist_becomes_candidate_again(self):
        registry = InstrumentRegistry()
        normalizer = DeltaProductNormalizer()
        registry.upsert(normalizer.normalize(ETH_PERP))
        registry.mark_present([])
        eth = registry.get_by_symbol("ETHUSDT")
        self.assertEqual(eth.state, PRODUCT_STATE_DELISTED)
        # The product reappears in a later catalog -> re-listed,
        # fresh NEWLY_LISTED candidate (never silently executable).
        relisted, first = registry.upsert(normalizer.normalize(ETH_PERP))
        self.assertFalse(first)
        self.assertEqual(relisted.state, PRODUCT_STATE_NEWLY_LISTED)

    def test_persistence_round_trip(self):
        directory = tempfile.mkdtemp(prefix="qe_registry_")
        path = os.path.join(directory, "registry.json")
        registry = InstrumentRegistry(path=path)
        normalizer = DeltaProductNormalizer()
        registry.upsert(normalizer.normalize(BTC_PERP))
        registry.upsert(normalizer.normalize(SOL_PERP))
        registry.save()

        loaded = InstrumentRegistry(path=path)
        self.assertEqual(len(loaded), 2)
        btc = loaded.get_by_symbol("BTCUSDT")
        self.assertEqual(btc.product_type, PRODUCT_PERPETUAL)
        self.assertEqual(btc.tick_size, 0.5)

    def test_executable_is_only_eligible(self):
        registry = InstrumentRegistry()
        normalizer = DeltaProductNormalizer()
        registry.upsert(normalizer.normalize(BTC_PERP))
        registry.upsert(normalizer.normalize(ETH_PERP))
        registry.mark_eligible(
            registry.get_by_symbol("BTCUSDT").key
        )
        self.assertEqual(
            [i.symbol for i in registry.executable()],
            ["BTCUSDT"],
        )


# ==========================================================
# End-to-end discovery / refresh (mocked transport)
# ==========================================================


class TestProductDiscoveryRefresh(unittest.TestCase):

    def test_refresh_dispatches_new_product_on_next_pass(self):
        directory = tempfile.mkdtemp(prefix="qe_disc_")
        path = os.path.join(directory, "registry.json")
        registry = InstrumentRegistry(path=path)

        transport = FakeTransport([BTC_PERP, ETH_PERP])
        first = refresh_instrument_registry(
            registry, client=ProductClient(transport=transport)
        )
        self.assertEqual(first["discovered"], 2)
        self.assertEqual(sorted(first["newly_listed"]),
                         ["BTCUSDT", "ETHUSDT"])

        # A newly listed product appears on the NEXT pass; the
        # engine detects it without a restart.
        transport._products = [BTC_PERP, ETH_PERP, SOL_PERP]
        second = refresh_instrument_registry(
            registry, client=ProductClient(transport=transport)
        )
        self.assertEqual(second["newly_listed"], ["SOLUSDT"])
        self.assertEqual(second["total_catalog"], 3)
        self.assertEqual(
            registry.get_by_symbol("SOLUSDT").state,
            PRODUCT_STATE_NEWLY_LISTED,
        )

    def test_refresh_detects_delisting(self):
        directory = tempfile.mkdtemp(prefix="qe_disc2_")
        path = os.path.join(directory, "registry.json")
        registry = InstrumentRegistry(path=path)

        transport = FakeTransport([BTC_PERP, ETH_PERP])
        refresh_instrument_registry(
            registry, client=ProductClient(transport=transport)
        )
        transport._products = [BTC_PERP]
        refresh_instrument_registry(
            registry, client=ProductClient(transport=transport)
        )
        eth = registry.get_by_symbol("ETHUSDT")
        self.assertEqual(eth.state, PRODUCT_STATE_DELISTED)
        self.assertEqual(
            [i.symbol for i in registry.delisted()],
            ["ETHUSDT"],
        )

    def test_refresh_never_duplicates(self):
        directory = tempfile.mkdtemp(prefix="qe_disc3_")
        path = os.path.join(directory, "registry.json")
        registry = InstrumentRegistry(path=path)
        transport = FakeTransport([BTC_PERP])
        for _ in range(3):
            refresh_instrument_registry(
                registry, client=ProductClient(transport=transport)
            )
        self.assertEqual(len(registry), 1)
        self.assertEqual(registry.get_by_symbol("BTCUSDT").product_type,
                         PRODUCT_PERPETUAL)

    def test_refresh_without_path_is_in_memory(self):
        registry = InstrumentRegistry()
        transport = FakeTransport([BTC_PERP])
        summary = refresh_instrument_registry(
            registry, client=ProductClient(transport=transport)
        )
        self.assertEqual(summary["total_catalog"], 1)
        self.assertEqual(len(registry), 1)


# ==========================================================
# Eligibility
# ==========================================================


class TestInstrumentEligibility(unittest.TestCase):

    def setUp(self):
        self.instrument = DeltaProductNormalizer().normalize(BTC_PERP)

    def test_basic_gates_four_plus_liquidity_pass(self):
        eligible, reason = InstrumentEligibility(
            min_quote_volume_24h=1000
        ).evaluate(self.instrument, quote_volume_24h=5000)
        self.assertTrue(eligible)
        self.assertEqual(reason, "")

    def test_disabled_instrument_is_denied(self):
        denied = DeltaProductNormalizer().normalize(DELISTED)
        eligible, reason = InstrumentEligibility().evaluate(
            denied, quote_volume_24h=5000
        )
        self.assertFalse(eligible)
        self.assertEqual(reason, IneligibleReason.NOT_ENABLED)

    def test_unknown_type_is_denied(self):
        mystery = DeltaProductNormalizer().normalize(MYSTERY)
        eligible, reason = InstrumentEligibility().evaluate(
            mystery, quote_volume_24h=5000
        )
        self.assertFalse(eligible)
        self.assertEqual(reason, IneligibleReason.UNKNOWN_TYPE)

    def test_option_is_discovered_but_not_strategy_eligible(self):
        option = DeltaProductNormalizer().normalize(BTC_CALL)
        self.assertEqual(option.product_type, PRODUCT_CALL_OPTION)
        eligible, reason = InstrumentEligibility().evaluate(
            option, quote_volume_24h=5000
        )
        self.assertFalse(eligible)
        self.assertEqual(reason, IneligibleReason.UNSUPPORTED_TYPE)

    def test_no_liquidity_data_denies_by_default(self):
        eligible, reason = InstrumentEligibility().evaluate(
            self.instrument
        )
        self.assertFalse(eligible)
        self.assertEqual(reason, IneligibleReason.NO_LIQUIDITY_DATA)

    def test_ms_vs_de_min_volume(self):
        eligible, reason = InstrumentEligibility(
            min_quote_volume_24h=100_000
        ).evaluate(self.instrument, quote_volume_24h=100)
        self.assertFalse(eligible)
        self.assertEqual(reason, IneligibleReason.LOW_LIQUIDITY)

    def test_run_basic_gates_uses_zero_volume(self):
        eligible, reason = run_basic_gates(self.instrument)
        self.assertTrue(eligible)


if __name__ == "__main__":
    unittest.main()