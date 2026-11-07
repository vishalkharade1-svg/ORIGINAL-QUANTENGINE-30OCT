"""
====================================================

QuantEngine

Phase 4E: Economic Setup Deduplication Tests

Run with:

    python -m unittest tests.test_economic_setup_dedup -v

Proves the SECOND deduplication layer end-to-end:

    1. Two structurally distinct order blocks (OB-5 / OB-6) whose
       trade economics are IDENTICAL collapse to ONE setup and ONE
       pending order -- the same fingerprint, normalized to the
       instrument tick grid, never burns two MAX_PENDING_ORDERS
       slots (the live-6000-bar case: OB-954 and OB-956 were both
       ordered with identical entry/stop/target).
    2. NEAR-identical execution zones (entry 77616 vs 77620 on the
       same stop/target) cluster when the distance is inside the
       configurable tolerance (tick multiples / percent / ATR
       fraction -- no hard-coded BTC point distances).
    3. Genuinely independent zones never cluster.
    4. The cluster canonical is selected deterministically by
       score -> confidence -> liquidity alignment -> reward/risk ->
       newest structural state -> structural id (never random).
    5. MAX_PENDING_ORDERS is applied AFTER clustering, so duplicate
       variants cannot starve independent opportunities.

Stdlib only -- no network.

====================================================
"""

import unittest
from unittest import mock

from config import risk_settings

from core.setup.setup_candidate import SetupCandidate
from core.setup.economic_setup_registry import (
    EconomicSetupRegistry,
    fingerprint_of,
)

from core.execution.order_registry import PENDING

from tests.test_execution_lifecycle import (
    run_world,
    miss_candle,
)


def candidate(
    structural="OB-5",
    entry=110.0,
    stop=100.0,
    target=130.0,
    score=85.0,
    confidence=85.0,
):
    risk = abs(entry - stop)
    reward = abs(target - entry)
    rr = reward / risk if risk else 0.0
    c = SetupCandidate(
        direction="BULLISH",
        entry=entry,
        stop_loss=stop,
        take_profit=target,
        risk_reward=rr,
        confidence=confidence,
        score=score,
    )
    c.structural_id = (
        "TEST-1m-BULLISH-{}-{:.2f}-{:.2f}-{:.2f}".format(
            structural, entry, stop, target
        )
    )
    c.setup_id = c.structural_id
    return c


class TestEconomicSetupDeduplication(unittest.TestCase):

    # --------------------------------------------------
    # Exact economics -> one canonical setup
    # --------------------------------------------------

    def test_same_trade_economics_different_ob_ids_produces_one_setup(self):
        # OB-954 vs OB-956: different structural discoveries, ONE
        # market idea. The registry must produce exactly one setup.
        a = candidate(structural="OB-5", entry=110.0, stop=100.0,
                      target=130.0)
        b = candidate(structural="OB-6", entry=110.0, stop=100.0,
                      target=130.0)

        registry = EconomicSetupRegistry()

        reps = registry.observe([a, b], order_registry=None, bar=1)

        self.assertEqual(len(reps), 1)
        survivor = reps[0]

        duplicates = [
            s for s in (a, b)
            if s is not survivor and s.is_economic_duplicate
        ]
        self.assertEqual(len(duplicates), 1)
        self.assertEqual(
            duplicates[0].economic_canonical_id,
            survivor.structural_id,
        )

        self.assertEqual(
            fingerprint_of(survivor, symbol="TEST", timeframe="1m"),
            fingerprint_of(duplicates[0], symbol="TEST", timeframe="1m"),
        )

        # Deterministic tie-break picks OB-5 (structural id
        # ascending) when every ranking axis ties.
        self.assertIn("OB-5", survivor.structural_id)

        stats = registry.summary()
        self.assertEqual(stats["distinct_fingerprints"], 1)
        self.assertEqual(stats["duplicates_suppressed"], 1)

    def test_same_entry_stop_target_creates_one_pending_order(self):
        # Full pipeline: the identical-economics world (two OBs,
        # same entry/stop/target) mints exactly ONE pending order.
        # Phase 4G STEP 9 (structural clustering): the two
        # identical-geometry twins collapse to ONE canonical
        # candidate (OB-5) at the BUILDER, before the economic
        # layer even sees them, so exactly one setup reaches the
        # funnel and exactly one order exists.
        _, simulator, pipeline, order_registry = run_world(
            [miss_candle(1)], world="same"
        )

        setup_ids = {
            s.setup_id for s in pipeline.context.trade_setups
        }
        self.assertEqual(len(setup_ids), 1)
        ordered_id = next(iter(setup_ids))
        self.assertIn("OB-5", ordered_id)

        self.assertEqual(len(order_registry.all()), 1)
        order = order_registry.all()[0]
        self.assertEqual(order.status, PENDING)

        # The single order inherits the shared tick-normalized
        # economic fingerprint.
        expected = fingerprint_of(
            order.setup, symbol="TEST", timeframe="1m"
        )
        self.assertTrue(expected)
        self.assertEqual(order.economic_fingerprint, expected)
        self.assertEqual(simulator.registry.count(), 0)

    # --------------------------------------------------
    # Clustering near-identical zones
    # --------------------------------------------------

    def test_nearby_entries_cluster_when_threshold_allows(self):
        # Entry 110.0 vs 110.4 (snaps to the 0.5 tick grid as 110.5)
        # and stop 100.0 vs 100.4 (snaps 100.5), same target: inside
        # the default 8-tick / 0.1% tolerance -> ONE execution zone.
        a = candidate(structural="OB-5", entry=110.0, stop=100.0,
                      target=130.0)
        b = candidate(structural="OB-6", entry=110.4, stop=100.4,
                      target=130.0)

        self.assertNotEqual(
            fingerprint_of(a, symbol="TEST", timeframe="1m"),
            fingerprint_of(b, symbol="TEST", timeframe="1m"),
        )

        registry = EconomicSetupRegistry()

        reps = registry.observe([a, b], order_registry=None, bar=1)

        self.assertEqual(len(reps), 1)
        stats = registry.summary()
        self.assertEqual(stats["clusters_formed"], 1)
        self.assertEqual(stats["duplicates_suppressed"], 1)

    def test_independent_setups_do_not_cluster(self):
        # Entry 110 vs 120 (10 > tolerance), stop 100 vs 106 (6 >
        # tolerance), target 130 vs 140 (10 > tolerance): genuinely
        # independent opportunities must stay independent.
        a = candidate(structural="OB-5", entry=110.0, stop=100.0,
                      target=130.0)
        b = candidate(structural="OB-6", entry=120.0, stop=106.0,
                      target=140.0)

        registry = EconomicSetupRegistry()

        reps = registry.observe([a, b], order_registry=None, bar=1)

        self.assertEqual(len(reps), 2)
        stats = registry.summary()
        self.assertEqual(stats["clusters_formed"], 0)
        self.assertEqual(stats["duplicates_suppressed"], 0)
        self.assertFalse(reps[0].is_economic_duplicate)
        self.assertFalse(reps[1].is_economic_duplicate)

    def test_cluster_selects_highest_priority_setup(self):
        # Within one cluster the canonical is the highest-ranked
        # setup (score -> confidence -> ... -> structural id),
        # NOT whichever structural discovery came first.
        low = candidate(structural="OB-5", entry=110.0, stop=100.0,
                        target=130.0, score=80.0)
        high = candidate(structural="OB-6", entry=110.4, stop=100.4,
                         target=130.0, score=95.0)

        registry = EconomicSetupRegistry()

        reps = registry.observe([low, high], order_registry=None, bar=1)

        self.assertEqual(len(reps), 1)
        self.assertIs(reps[0], high)

        self.assertFalse(high.is_economic_duplicate)
        self.assertTrue(low.is_economic_duplicate)
        self.assertEqual(low.economic_canonical_id, high.structural_id)

    # --------------------------------------------------
    # Pending capacity applies after clustering
    # --------------------------------------------------

    def test_pending_order_limit_applies_after_clustering(self):
        # (a) Economically identical variants (world="same") with a
        # comfortable MAX_PENDING_ORDERS=2 still mint exactly ONE
        # order. Phase 4G STEP 9: the identical twins now collapse
        # to ONE canonical candidate at the STRUCTURAL layer (the
        # builder), so dedup runs before the cap at every level --
        # a duplicate can never consume a second pending slot.
        with mock.patch.object(risk_settings, "MAX_PENDING_ORDERS_TOTAL", 2):
            _, _, pipeline, order_registry = run_world(
                [miss_candle(1)], world="same"
            )

        setup_ids = {
            s.setup_id for s in pipeline.context.trade_setups
        }
        self.assertEqual(len(setup_ids), 1)
        self.assertEqual(len(order_registry.all()), 1)

        # (b) Independent opportunities: with MAX_PENDING_ORDERS=1
        # the best-ranked canonical setup is ordered and the other
        # independent idea queues (the cap still applies AFTER the
        # clustering step).
        with mock.patch.object(risk_settings, "MAX_PENDING_ORDERS_TOTAL", 1):
            _, _, _, order_registry = run_world(
                [miss_candle(1)], world="distinct"
            )

        self.assertEqual(len(order_registry.all()), 1)
        ordered = order_registry.all()[0]
        self.assertIn("OB-5", ordered.setup_id)


if __name__ == "__main__":

    unittest.main()