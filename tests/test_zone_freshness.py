"""
====================================================

QuantEngine

Structural Zone Freshness + Entry Eligibility Tests

Phase 4G -- ages, freshness states, the entry-eligibility
split (structurally_valid vs trade_eligible), the full
decision/execution/risk chokepoints, structural zone
clustering, canonical zone selection, and the no-future-
information guarantees.

The e2e tests drive the SAME four-engine chain the Phase 4F
harness does (TradeSetupBuilder -> DecisionEngine ->
ExecutionEngine -> RiskEngine) over hand-seeded worlds whose
blocks carry explicit zone-age / freshness / distance
stamps. The no-leak tests drive the real registered
InstitutionalPipeline over a synthetic feed and assert the
scanner stamps stay in the past.

Stdlib only -- no network.

====================================================
"""

import unittest
from contextlib import ExitStack
from unittest import mock

from config import risk_settings

from core.market_state import MarketState
from core.pipeline.pipeline_context import PipelineContext
from core.pipeline.institutional_pipeline import InstitutionalPipeline

from core.setup.trade_setup_builder import TradeSetupBuilder
from core.setup.decision_engine import DecisionEngine
from core.execution.execution_engine import ExecutionEngine
from core.risk.risk_engine import RiskEngine
from core.execution.order_registry import OrderRegistry

from core.order_blocks.order_block import OrderBlock
from core.order_blocks.order_block_registry import OrderBlockRegistry
from core.order_blocks.zone_freshness import (
    classify_freshness,
    cluster_structural_zones,
    compute_zone_age,
    max_order_block_age_bars,
    REASON_STALE_ZONE,
    REASON_TOO_FAR_FROM_MARKET,
    REASON_INSUFFICIENT_RISK_WIDTH,
)

from core.fvg.fvg_registry import FVGRegistry

from core.backtesting.trade_simulator import TradeSimulator

from backtesting.backtester import Backtester

from tests.test_execution_lifecycle import (
    Candle,
    EventBus,
    FakeIndicators,
    liquidity_target,
    ob,
    regime,
    trend,
)
from tests.test_pipeline_regressions import make_candles


# ==========================================================
# Fixtures
# ==========================================================


def zone_ob(direction, high, low, index=5, score=85.0, age=0,
            distance=1.0, distance_atr=0.13, touches=0,
            disp=None, invalidated=False, mitigated=False,
            atr=15.0):
    """
    An OrderBlock seeded with an explicit Phase 4G snapshot
    (the same fields OrderBlockScanner stamps at creation):
    zone age, freshness, entry-distance axes, touches and
    structure status. Unknown origin (origin_bar < 0) reads
    age 0 / fresh by compute_zone_age, so a hand-seeded block
    is alive by default. Structure status + touches are set
    BEFORE the freshness stamp so the stamped state is
    internally consistent.
    """
    block = ob(direction, high, low, index=index, score=score)
    block.displacement_strength = disp if disp is not None else score
    block.touches = touches
    block.invalidated = invalidated
    block.mitigated = mitigated
    block.age_bars = age
    block.origin_bar = -1 if age == 0 else 10 - age
    block.created_bar = 10
    block.freshness = classify_freshness(
        block,
        block.age_bars,
        max_age_bars=max_order_block_age_bars("1m"),
    )
    block.distance_from_current_price = float(distance or 0.0)
    block.distance_from_current_price_atr = float(distance_atr or 0.0)
    return block


def zone_world(*blocks, liquidity_price=170.0):
    """A seeded-world factory for the four-engine ZoneWorld."""
    def _seed(context):
        registry = OrderBlockRegistry()
        for block in blocks:
            registry.add(block)
        context.order_blocks = registry
        context.liquidity_target = liquidity_target(price=liquidity_price)
        context.trend = trend()
        context.regime = regime()
        context.fvgs = FVGRegistry()
    return _seed


class ZoneWorld:
    """
    Four-engine mirror of WorldPipeline (Phase 4F harness),
    parameterized by a seeded-world factory and an ATR axis so
    the Phase 4G gates can be exercised end-to-end.
    """

    def __init__(self, seed_fn, atr=15.0):
        self.builder = TradeSetupBuilder()
        self.decision = DecisionEngine()
        self.execution = ExecutionEngine()
        self.risk = RiskEngine()
        self._seed = seed_fn
        self._atr = atr
        self.reset()

    def reset(self):
        self.context = PipelineContext()
        self.context.market = MarketState(symbol="TEST", timeframe="1m")
        self.context.indicators = FakeIndicators(self._atr)
        self._seed(self.context)
        for engine in (self.builder, self.decision,
                       self.execution, self.risk):
            engine.reset()

    def on_candle(self, event):
        self._seed(self.context)
        self.context.add_candle(event.candle)
        self.context.market.timestamp = event.candle.timestamp
        self.builder.analyze(self.context)
        self.decision.analyze(self.context)
        self.execution.analyze(self.context)
        self.risk.analyze(self.context)


def run_zone(candles, seed_fn, atr=15.0, **patches):
    """
    Replay candles through the four-engine chain plus the real
    Backtester adapter. Patches (name=value) are applied to
    risk_settings for the duration of the run, mirroring the
    existing mock.patch.object convention. Returns
    (pipeline, registry).
    """
    with ExitStack() as stack:
        if patches:
            for name, value in patches.items():
                stack.enter_context(
                    mock.patch.object(risk_settings, name, value)
                )
        pipeline = ZoneWorld(seed_fn, atr=atr)
        event_bus = EventBus(pipeline)
        simulator = TradeSimulator()
        backtester = Backtester(pipeline, event_bus, simulator)
        backtester.run(candles)
        return pipeline, pipeline.context.order_registry


def two_candles():
    return [
        Candle(high=111.0, low=109.0, close=110.0, timestamp=1000),
        Candle(high=111.5, low=109.5, close=110.5, timestamp=1100),
    ]


def one_candle():
    return [Candle(
        high=111.0, low=109.0, close=110.0, timestamp=1000)]


def report(pipeline, direction=None):
    return pipeline.context.zone_eligibility.report(direction)


# ==========================================================
# 1. Pure zone-age measurement
# ==========================================================


class TestZoneAge(unittest.TestCase):

    def test_zone_age_is_a_direct_measurement(self):
        self.assertEqual(compute_zone_age(3, 9), 6)
        self.assertEqual(compute_zone_age(9, 3), 0)
        self.assertEqual(compute_zone_age(-1, 9), 0)
        self.assertEqual(compute_zone_age(None, 9), 0)
        self.assertEqual(compute_zone_age(3, None), 0)


# ==========================================================
# 2. Freshness classification
# ==========================================================


class TestFreshnessClassification(unittest.TestCase):

    def test_stale_classification_at_cap(self):
        block = zone_ob("BULLISH", 110.0, 100.0, age=900)
        self.assertEqual(block.freshness, "STALE")

    def test_fresh_classification_within_baseline_age(self):
        self.assertEqual(classify_freshness(
            zone_ob("BULLISH", 110.0, 100.0, age=2),
        ), "FRESH")

    def test_touched_zone_is_tested_not_fresh(self):
        block = zone_ob("BULLISH", 110.0, 100.0, age=2, touches=1)
        self.assertEqual(block.freshness, "TESTED")


# ==========================================================
# 3. End-to-end creation gates
# ==========================================================


class TestEntryEligibility(unittest.TestCase):

    def test_fresh_order_block_is_entry_eligible(self):
        pipeline, registry = run_zone(
            two_candles(),
            zone_world(zone_ob(
                "BULLISH", 110.0, 100.0, index=5, age=2,
            )),
        )
        rep = report(pipeline)
        self.assertEqual(rep["trade_eligible"], 1)
        self.assertEqual(rep["trade_ineligible"], 0)
        self.assertEqual(len(registry.all()), 1)
        order = registry.all()[0]
        self.assertEqual(order.direction, "BULLISH")
        self.assertEqual(order.entry, 110.0)
        self.assertEqual(order.stop_loss, 100.0)

    def test_old_order_block_becomes_stale(self):
        pipeline, registry = run_zone(
            two_candles(),
            zone_world(zone_ob(
                "BULLISH", 110.0, 100.0, index=5, age=900,
            )),
        )
        rep = report(pipeline)
        self.assertEqual(rep["by_freshness"].get("STALE", 0), 1)
        self.assertEqual(rep["by_reason"].get("STALE_ZONE", 0), 1)
        self.assertEqual(rep["trade_ineligible"], 1)
        self.assertEqual(len(registry.all()), 0,
                         "A stale zone may never mint a pending order.")

    def test_stale_order_block_can_remain_structurally_valid(self):
        # STEP 7: structural validity is INDEPENDENT of trade
        # eligibility -- an old but unbroken zone stays valid.
        pipeline, registry = run_zone(
            two_candles(),
            zone_world(zone_ob(
                "BULLISH", 110.0, 100.0, index=5, age=900,
            )),
        )
        rep = report(pipeline)
        self.assertEqual(rep["structurally_valid"], 1)
        self.assertEqual(rep["structurally_invalid"], 0)
        self.assertEqual(rep["trade_eligible"], 0)
        self.assertEqual(len(registry.all()), 0)

    def test_far_order_block_is_not_limit_entry_eligible(self):
        pipeline, registry = run_zone(
            two_candles(),
            zone_world(zone_ob(
                "BULLISH", 110.0, 100.0, index=5, age=2,
                distance=600.0, distance_atr=40.0,
            )),
        )
        rep = report(pipeline)
        self.assertEqual(
            rep["by_reason"].get("TOO_FAR_FROM_MARKET", 0), 1)
        self.assertEqual(rep["trade_ineligible"], 1)
        self.assertEqual(len(registry.all()), 0)

    def test_near_order_block_remains_limit_entry_eligible(self):
        pipeline, registry = run_zone(
            two_candles(),
            zone_world(zone_ob(
                "BULLISH", 110.0, 100.0, index=5, age=2,
                distance=2.0, distance_atr=0.13,
            )),
        )
        rep = report(pipeline)
        self.assertEqual(rep["trade_eligible"], 1)
        self.assertEqual(len(registry.all()), 1)

    def test_minimum_risk_width_applies_to_all_setup_paths(self):
        # Builder gate: a stop narrower than MIN_RISK_WIDTH_ATR x
        # ATR (0.5 / 15 = 0.033 < 0.10 baseline) is barred before an
        # order can ever be minted.
        pipeline, registry = run_zone(
            two_candles(),
            zone_world(zone_ob(
                "BULLISH", 110.5, 110.0, index=5, age=2,
            )),
        )
        rep = report(pipeline)
        self.assertEqual(
            rep["by_reason"].get("INSUFFICIENT_RISK_WIDTH", 0), 1)
        self.assertEqual(rep["trade_ineligible"], 1)
        self.assertEqual(len(registry.all()), 0)

    def test_minimum_risk_width_defense_in_depth_at_risk_engine(self):
        # STEP 8 (all-paths): the SAME ATR-risk-width floor holds
        # at RiskEngine even if a signal bypasses the builder gate.
        # A wide patched floor kills a thin stop outright; a normal
        # stop clears it, proving the gate is what binds, not
        # something else on the chain.
        with mock.patch.object(risk_settings, "MIN_RISK_WIDTH_ATR", 0.5):
            from core.setup.setup_candidate import SetupCandidate

            def make_signal(entry, stop):
                signal = SetupCandidate(
                    direction="BULLISH",
                    entry=entry,
                    stop_loss=stop,
                    take_profit=170.0,
                    risk_reward=abs(170.0 - entry) / abs(entry - stop),
                    confidence=85.0,
                    score=85.0,
                )
                signal.atr = 15.0
                signal.setup_id = "S-{}-{:.2f}".format(entry, stop)
                signal.economic_fingerprint = signal.setup_id
                return signal

            thin = make_signal(110.5, 110.0)   # risk 0.5 -> 0.033 ATR
            normal = make_signal(110.0, 100.0)  # risk 10.0 -> 0.667 ATR

            context = PipelineContext()
            context.account.balance = 10000.0
            context.account.equity = 10000.0
            context.market = MarketState(symbol="TEST", timeframe="1m")
            context.order_registry = OrderRegistry()
            context.execution_signals = [thin]
            RiskEngine().analyze(context)
            self.assertEqual(len(context.order_registry.all()), 0,
                             "Thin stop must never mint an order at "
                             "RiskEngine.")

            context = PipelineContext()
            context.account.balance = 10000.0
            context.account.equity = 10000.0
            context.market = MarketState(symbol="TEST", timeframe="1m")
            context.order_registry = OrderRegistry()
            context.execution_signals = [normal]
            RiskEngine().analyze(context)
            self.assertEqual(len(context.order_registry.all()), 1,
                             "The same gate lets a wide stop through.")


# ==========================================================
# 4. Structural clustering + canonical selection
# ==========================================================


class TestStructuralClustering(unittest.TestCase):

    def test_duplicate_overlapping_order_blocks_form_one_cluster(self):
        a = zone_ob("BULLISH", 110.0, 100.0, index=5, age=18)
        b = zone_ob("BULLISH", 109.0, 100.5, index=6, age=6)
        clusters, suppressed = cluster_structural_zones(
            [a, b], atr=15.0)
        self.assertEqual(len(clusters), 1)
        self.assertEqual(suppressed, 1)
        self.assertFalse(b.is_canonical)
        self.assertEqual(b.canonical_zone_id, "5")

        pipeline, registry = run_zone(
            one_candle(),
            zone_world(a, b),
        )
        rep = report(pipeline)
        self.assertEqual(rep["structural_suppressed"], 1)
        self.assertEqual(len(registry.all()), 1,
                         "One execution surface -> exactly one order.")

    def test_cluster_selects_canonical_order_block(self):
        # Fresher + stronger displacement wins the cluster (STEP 10).
        a = zone_ob("BULLISH", 110.0, 100.0, index=5, age=18, score=85.0)
        b = zone_ob("BULLISH", 109.0, 100.5, index=6, age=2,
                    score=90.0, disp=92.0)
        clusters, _ = cluster_structural_zones([a, b], atr=15.0)
        self.assertEqual(len(clusters), 1)
        self.assertTrue(b.is_canonical)
        self.assertFalse(a.is_canonical)
        self.assertEqual(a.canonical_zone_id, "6")

        pipeline, registry = run_zone(
            two_candles(),
            zone_world(a, b),
        )
        rep = report(pipeline)
        self.assertEqual(rep["trade_eligible"], 1)
        self.assertEqual(len(registry.all()), 1)
        self.assertIn("OB-6", registry.all()[0].setup_id)

    def test_distinct_zones_never_merge(self):
        # The Phase 4E "distinct world": entry 110 vs 120 is far
        # beyond the economic tolerance and must produce TWO
        # independent opportunities, never a cluster.
        a = zone_ob("BULLISH", 110.0, 100.0, index=5, age=2)
        e = zone_ob("BULLISH", 120.0, 109.0, index=6, age=2)
        clusters, suppressed = cluster_structural_zones(
            [a, e], atr=15.0)
        self.assertEqual(len(clusters), 2)
        self.assertEqual(suppressed, 0)
        self.assertTrue(a.is_canonical)
        self.assertTrue(e.is_canonical)


# ==========================================================
# 5. Guard rails on the funnel
# ==========================================================


class TestFunnelGuardRails(unittest.TestCase):

    def test_trade_setup_is_created_only_from_entry_eligible_zone(self):
        # One fresh zone + one stale zone: exactly one setup is
        # created, from the eligible zone only.
        fresh = zone_ob("BULLISH", 110.0, 100.0, index=5, age=2)
        stale = zone_ob("BULLISH", 120.0, 109.0, index=6, age=900)
        pipeline, registry = run_zone(
            two_candles(),
            zone_world(fresh, stale),
        )
        rep = report(pipeline)
        self.assertEqual(rep["zones_considered"], 2)
        self.assertEqual(rep["trade_eligible"], 1)
        self.assertEqual(rep["trade_ineligible"], 1)
        self.assertEqual(rep["by_reason"].get("STALE_ZONE", 0), 1)
        self.assertEqual(len(registry.all()), 1)
        self.assertIn("OB-5", registry.all()[0].setup_id)
        self.assertNotIn("OB-6", registry.all()[0].setup_id)

    def test_rejection_reason_is_preserved(self):
        # The TOO_FAR reason stamps the candidate at creation,
        # surfaces in the eligibility report, and the DecisionEngine
        # rejects the ineligible candidate (it is never accepted).
        far = zone_ob("BULLISH", 110.0, 100.0, index=5, age=2,
                      distance=600.0, distance_atr=40.0)
        pipeline, registry = run_zone(
            two_candles(),
            zone_world(far),
        )
        rep = report(pipeline)
        self.assertEqual(
            rep["by_reason"].get("TOO_FAR_FROM_MARKET", 0), 1)
        self.assertGreaterEqual(
            len(pipeline.decision.rejected), 1,
            "The ineligible candidate is rejected on the last candle "
            "(DecisionEngine resets its per-candle ledger each bar).")
        self.assertEqual(len(registry.all()), 0)
        for reject in pipeline.decision.rejected:
            self.assertNotEqual(reject.reasons, [])
            self.assertIn("Entry Too Far", reject.reasons)

    def test_decision_engine_logs_one_rejected_per_dedup_key(self):
        # While the rejection IS re-evaluated every candle, the
        # SETUP_REJECTED audit log is deduped per (reason,
        # fingerprint) so a drifting re-derivation cannot spam it.
        far = zone_ob("BULLISH", 110.0, 100.0, index=5, age=2,
                      distance=600.0, distance_atr=40.0)
        pipeline, registry = run_zone(
            two_candles(),
            zone_world(far),
        )
        self.assertEqual(len(pipeline.decision._logged_reject), 1)


# ==========================================================
# 6. No-future-information guarantees (real pipeline)
# ==========================================================


class TestNoFutureInformation(unittest.TestCase):

    def _run_real_pipeline(self, n=400):
        InstitutionalPipeline.DEBUG = False
        context = PipelineContext()
        context.market = MarketState(symbol="TEST", timeframe="1m")
        pipeline = InstitutionalPipeline(context)
        snapshots = []
        for i, candle in enumerate(make_candles(n=n)):
            context.add_candle(candle)
            pipeline.process()
            blocks = (
                context.order_blocks.active()
                if context.order_blocks is not None
                else []
            )
            for b in blocks:
                snapshots.append((i, b))
        return pipeline, context, snapshots

    def test_order_block_age_increases_each_bar(self):
        # The same zone re-minted on later candles must carry a
        # LARGER age -- measured from its origin, never a stale or
        # resettable counter (a counter would reset on every scan).
        _, context, snapshots = self._run_real_pipeline()

        by_tick = {}
        for bar, block in snapshots:
            key = (round(block.high, 2), round(block.low, 2))
            by_tick.setdefault(key, []).append((bar, block.age_bars))

        matched = 0
        for key, obs in by_tick.items():
            obs.sort()
            for (b1, a1), (b2, a2) in zip(obs, obs[1:]):
                if a2 - a1 == b2 - b1:
                    matched += 1
                self.assertEqual(
                    a2 - a1, b2 - b1,
                    "Zone %s aged %d bars over %d candle(s) -- "
                    "the age must grow with the window." % (
                        key, a2 - a1, b2 - b1))
        self.assertGreater(
            matched, 0,
            "Expected at least one zone re-minted on a later candle "
            "to verify age growth; none appeared in the feed.")

    def test_freshness_does_not_use_future_information(self):
        # Every scanner stamp must be derived from the current bar
        # at the latest: age <= candles seen, origin never in the
        # future, age-time >= 0, and the stamped freshness state
        # must be consistent with the same-candle structure state.
        # A lifecycle step may legally upgrade a zone FRESH/ACTIVE ->
        # TESTED (or -> MITIGATED / INVALIDATED) WITHIN the same
        # candle, after the scanner's snapshots -- that is a
        # current-bar measurement, never a future one.
        _, context, snapshots = self._run_real_pipeline()
        self.assertGreater(len(snapshots), 0,
                           "Expected the synthetic feed to mint "
                           "order blocks at all.")

        for bar, block in snapshots:
            self.assertGreaterEqual(block.age_bars, 0)
            self.assertLessEqual(block.age_bars, bar + 1)
            self.assertLessEqual(block.origin_bar, bar + 1)
            self.assertGreaterEqual(block.age_time_seconds, 0)

            current_ts = block.timestamp
            origin_ts = current_ts - block.age_time_seconds
            self.assertLessEqual(origin_ts, current_ts)

            max_age = max_order_block_age_bars(block.timeframe)
            stale = block.age_bars > max_age

            self.assertEqual(
                block.freshness == "STALE", stale,
                "STALE must be exactly the age-based verdict at "
                "creation: age %d vs cap %d." % (
                    block.age_bars, max_age))

            if not stale and int(getattr(block, "touches", 0) or 0) == 0:
                self.assertIn(
                    block.freshness,
                    ("FRESH", "ACTIVE", "MITIGATED", "INVALIDATED"),
                    "An untouched, un-broken, non-stale zone must be "
                    "reported FRESH or ACTIVE at creation.")


if __name__ == "__main__":
    unittest.main()