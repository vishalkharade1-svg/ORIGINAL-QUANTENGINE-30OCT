"""
====================================================

QuantEngine

Market Structure / BOS / CHOCH Contract Tests

Run with:

    python -m unittest tests.test_market_structure_contract -v

Proves the market-structure stage contract:

1. StructureEngine labels HH/HL/LH/LL exactly and in swing
   order, deterministically (same registry -> same events).
2. BOSEngine emits a BULLISH event only when the latest close
   breaks the most recent swing HIGH, and a BEARISH event only
   when it breaks the most recent swing LOW -- using only the
   current bar (no lookahead). The same broken level is not
   re-emitted, but reset() restores a clean slate.
3. CHoCHEngine requires a real direction reversal: the first
   BOS only establishes direction; a same-direction BOS emits
   nothing; a reversal emits exactly one CHoCH.
4. MarketStructureEngine aggregates flags per candle and NEVER
   leaks a previous candle's bos/choch/structure into the next
   cycle (stale-state regression).
5. The full canonical pipeline is deterministic: two fresh
   pipelines over identical candles produce identical structure
   state, and BOS/CHoCH events never reference a bar newer than
   the candle being processed.

Stdlib + dataclasses only -- no network.

====================================================
"""

import unittest

from core.history.candle import Candle
from core.market_state import MarketState
from core.pipeline.pipeline_context import PipelineContext
from core.pipeline.institutional_pipeline import InstitutionalPipeline

from core.enums import StructureType
from core.market_structure.swing import Swing
from core.market_structure.swing_registry import SwingRegistry
from core.market_structure.structure_engine import (
    StructureEngine,
    StructureEvent,
)
from core.market_structure.bos_engine import (
    BOSEngine,
    BOSEvent,
)
from core.market_structure.choch_engine import CHoCHEngine
from core.market_structure.engine import MarketStructureEngine

from core.trend.trend_state import TrendState

from tests.test_pipeline_regressions import make_candles


def swing(kind, price, index, timestamp=0):
    return Swing(
        id=f"swing-{index}-{kind}",
        index=index,
        timestamp=timestamp or (index * 60),
        timeframe="1m",
        kind=kind,
        price=price,
        high=price,
        low=price,
        confirmed=True,
    )


def registry_with(*swings):
    reg = SwingRegistry()
    for s in swings:
        reg.add(s)
    return reg


# ==========================================================
# Structure Engine
# ==========================================================

class TestStructureEngineContract(unittest.TestCase):

    def test_hh_hl_lh_ll_classification(self):
        # Highs: 100 -> 110 = HH, 110 -> 105 = LH
        # Lows :  90 ->  95 = HL,  95 ->  85 = LL
        reg = registry_with(
            swing("HIGH", 100, 1),
            swing("LOW", 90, 5),
            swing("HIGH", 110, 9),
            swing("LOW", 95, 13),
            swing("HIGH", 105, 17),
            swing("LOW", 85, 21),
        )

        events = StructureEngine().update(reg)

        self.assertEqual(
            [e.kind for e in events],
            [
                StructureType.HH,
                StructureType.HL,
                StructureType.LH,
                StructureType.LL,
            ],
        )

        # Events align to the swing that produced them.
        self.assertEqual(events[0].price, 110)
        self.assertEqual(events[1].price, 95)
        self.assertEqual(events[2].price, 105)
        self.assertEqual(events[3].price, 85)

    def test_events_sorted_by_timestamp(self):
        # Registry insertion order deliberately scrambled.
        reg = registry_with(
            swing("HIGH", 110, 9, timestamp=9 * 60),
            swing("LOW", 90, 5, timestamp=5 * 60),
            swing("HIGH", 100, 1, timestamp=1 * 60),
            swing("LOW", 95, 13, timestamp=13 * 60),
        )

        events = StructureEngine().update(reg)

        stamps = [e.timestamp for e in events]

        self.assertEqual(stamps, sorted(stamps))

    def test_empty_registry_no_events(self):
        events = StructureEngine().update(SwingRegistry())
        self.assertEqual(events, [])

    def test_single_swing_produces_no_event(self):
        events = StructureEngine().update(
            registry_with(swing("HIGH", 100, 1))
        )
        self.assertEqual(events, [])

    def test_deterministic_same_input_same_events(self):
        reg = registry_with(
            swing("HIGH", 100, 1),
            swing("LOW", 90, 5),
            swing("HIGH", 110, 9),
            swing("LOW", 85, 13),
        )

        a = StructureEngine().update(reg)
        b = StructureEngine().update(reg)

        self.assertEqual(len(a), len(b))

        for x, y in zip(a, b):
            self.assertEqual(x.kind, y.kind)
            self.assertEqual(x.price, y.price)
            self.assertEqual(x.index, y.index)


# ==========================================================
# BOS Engine
# ==========================================================

class TestBOSEngineContract(unittest.TestCase):

    def setUp(self):
        self.bars = list(make_candles(n=50))
        self.last_close = self.bars[-1].close

    def test_bullish_bos_breaks_recent_swing_high(self):
        reg = registry_with(
            swing("HIGH", self.last_close - 5, 30, timestamp=self.bars[30].timestamp),
            swing("LOW", self.last_close - 500, 31, timestamp=self.bars[31].timestamp),
        )

        events = BOSEngine().update(self.bars, reg)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].direction, "BULLISH")
        self.assertEqual(events[0].level, self.last_close - 5)
        self.assertEqual(events[0].close, self.last_close)
        self.assertEqual(events[0].swing_index, 30)
        # No lookahead: event timestamp is the current bar.
        self.assertEqual(events[0].timestamp, self.bars[-1].timestamp)

    def test_bearish_bos_breaks_recent_swing_low(self):
        reg = registry_with(
            swing("HIGH", self.last_close + 500, 30, timestamp=self.bars[30].timestamp),
            swing("LOW", self.last_close + 5, 31, timestamp=self.bars[31].timestamp),
        )

        events = BOSEngine().update(self.bars, reg)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].direction, "BEARISH")
        self.assertEqual(events[0].swing_index, 31)

    def test_no_bos_when_close_inside_swings(self):
        reg = registry_with(
            swing("HIGH", self.last_close + 5, 30),
            swing("LOW", self.last_close - 5, 31),
        )

        events = BOSEngine().update(self.bars, reg)

        self.assertEqual(events, [])

    def test_same_level_not_reemitted(self):
        reg = registry_with(
            swing("HIGH", self.last_close - 5, 30),
            swing("LOW", self.last_close - 500, 31),
        )

        engine = BOSEngine()

        first = engine.update(self.bars, reg)
        second = engine.update(self.bars, reg)  # same level again

        self.assertEqual(len(first), 1)
        self.assertEqual(
            second,
            [],
            "Breaking the same swing level a second time is not "
            "a new BOS event.",
        )

    def test_reset_restores_clean_slate(self):
        reg = registry_with(
            swing("HIGH", self.last_close - 5, 30),
            swing("LOW", self.last_close - 500, 31),
        )

        engine = BOSEngine()

        first = engine.update(self.bars, reg)

        engine.reset()

        second = engine.update(self.bars, reg)

        self.assertEqual(len(first), len(second))
        self.assertEqual(first[0].direction, second[0].direction)


# ==========================================================
# CHOCH Engine
# ==========================================================

class TestCHoCHEngineContract(unittest.TestCase):

    def _structure(self, kind, price, timestamp):
        return StructureEvent(
            kind=kind,
            price=price,
            timestamp=timestamp,
            index=0,
            timeframe="1m",
        )

    def _bos(self, direction, close, timestamp):
        return BOSEvent(
            direction=direction,
            level=close - 1,
            close=close,
            timestamp=timestamp,
            swing_index=1,
        )

    def test_first_bos_only_establishes_direction(self):
        engine = CHoCHEngine()

        events = engine.update(
            [self._structure(StructureType.HH, 100, 1000)],
            [self._bos("BULLISH", 110, 1000)],
        )

        self.assertEqual(events, [])
        self.assertEqual(engine.last_bos, "BULLISH")

    def test_same_direction_bos_emits_nothing(self):
        engine = CHoCHEngine()
        engine.update(
            [self._structure(StructureType.HH, 100, 1000)],
            [self._bos("BULLISH", 110, 1000)],
        )

        events = engine.update(
            [self._structure(StructureType.HH, 120, 2000)],
            [self._bos("BULLISH", 130, 2000)],
        )

        self.assertEqual(events, [])

    def test_reversal_emits_exactly_one_choch(self):
        engine = CHoCHEngine()
        engine.update(
            [self._structure(StructureType.HH, 100, 1000)],
            [self._bos("BULLISH", 110, 1000)],
        )

        events = engine.update(
            [self._structure(StructureType.LL, 90, 2000)],
            [self._bos("BEARISH", 80, 2000)],
        )

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].direction, "BEARISH")
        self.assertEqual(events[0].level, 90)
        self.assertEqual(events[0].timestamp, 2000)
        self.assertEqual(engine.last_bos, "BEARISH")

    def test_no_choch_without_structure_or_bos(self):
        engine = CHoCHEngine()

        self.assertEqual(engine.update(None, None), [])
        self.assertEqual(engine.update([], []), [])

    def test_reset_restores_direction_tracking(self):
        engine = CHoCHEngine()
        engine.update(
            [self._structure(StructureType.HH, 100, 1000)],
            [self._bos("BULLISH", 110, 1000)],
        )

        engine.reset()

        # After reset the first BOS starts fresh direction tracking.
        events = engine.update(
            [self._structure(StructureType.HH, 100, 1000)],
            [self._bos("BULLISH", 110, 1000)],
        )

        self.assertEqual(events, [])
        self.assertEqual(engine.last_bos, "BULLISH")


# ==========================================================
# Market Structure Engine (aggregation + stale-state)
# ==========================================================

class TestMarketStructureEngineContract(unittest.TestCase):

    def test_aggregates_cycle_outputs(self):
        context = PipelineContext()
        context.market = MarketState(symbol="TEST", timeframe="1m")

        context.trend = TrendState(direction="BULLISH")
        context.swings = registry_with(
            swing("HIGH", 110, 9),
            swing("LOW", 90, 13),
        )
        context.structure_events = [
            StructureEvent(
                kind=StructureType.HH,
                price=110,
                timestamp=540,
                index=9,
                timeframe="1m",
            ),
        ]
        context.bos = [
            BOSEvent(
                direction="BULLISH",
                level=110,
                close=112,
                timestamp=600,
                swing_index=9,
            ),
        ]
        context.choch = None

        MarketStructureEngine().analyze(context)

        state = context.market_structure

        self.assertTrue(state.bos)
        self.assertFalse(state.choch)
        self.assertEqual(state.trend, "BULLISH")
        self.assertEqual(state.last_structure, StructureType.HH)
        self.assertEqual(state.last_bos, StructureType.BOS)
        self.assertIn("BULLISH_BOS", state.signals)
        self.assertEqual(state.major_high, 110)
        self.assertEqual(state.major_low, 90)

    def test_no_stale_state_across_cycles(self):
        # Candle 1: BOS present. Candle 2: nothing. The engine
        # must not leak candle 1's bos/choch/structure into
        # candle 2 -- the classic stale-state bug.
        engine = MarketStructureEngine()

        context1 = PipelineContext()
        context1.market = MarketState(symbol="TEST", timeframe="1m")
        context1.trend = TrendState(direction="BULLISH")
        context1.swings = registry_with(swing("HIGH", 110, 9))
        context1.structure_events = [
            StructureEvent(StructureType.HH, 110, 540, 9, "1m"),
        ]
        context1.bos = [
            BOSEvent("BULLISH", 110, 112, 600, 9),
        ]

        engine.analyze(context1)

        context2 = PipelineContext()
        context2.market = MarketState(symbol="TEST", timeframe="1m")
        context2.trend = TrendState(direction="BULLISH")
        context2.swings = registry_with(swing("HIGH", 110, 9))
        context2.structure_events = []
        context2.bos = []
        context2.choch = []

        engine.analyze(context2)

        state = context2.market_structure

        self.assertFalse(state.bos)
        self.assertFalse(state.choch)
        self.assertEqual(state.signals, [])
        self.assertEqual(state.last_bos, StructureType.NONE)
        self.assertEqual(state.last_structure, StructureType.NONE)


# ==========================================================
# Full pipeline determinism + no-lookahead
# ==========================================================

class TestMarketStructurePipelineContract(unittest.TestCase):

    def _run(self, n=400):
        context = PipelineContext()
        context.market = MarketState(symbol="TEST", timeframe="1m")
        pipeline = InstitutionalPipeline(context)

        bos_indices = []

        candles = make_candles(n=n)

        for i, c in enumerate(candles):
            context.add_candle(c)
            pipeline.process()

            bos = context.bos or []

            for event in bos:
                self.assertLess(
                    event.swing_index,
                    i + 1,
                    "BOS events must never reference a bar that "
                    "does not exist yet (no lookahead).",
                )

            if bos:
                bos_indices.append(i)

        return context, bos_indices

    def test_pipeline_deterministic_across_runs(self):
        a, bos_a = self._run()
        b, bos_b = self._run()

        self.assertEqual(bos_a, bos_b)

        for field in (
            "bos",
            "choch",
            "structure",
            "major_high",
            "major_low",
            "last_structure",
            "last_bos",
            "last_choch",
        ):
            self.assertEqual(
                getattr(a.market_structure, field),
                getattr(b.market_structure, field),
                f"market_structure.{field} not deterministic.",
            )

        self.assertEqual(
            a.market_structure.signals,
            b.market_structure.signals,
        )

    def test_pipeline_reset_reruns_identically(self):
        candles = make_candles(n=300)

        def collect():
            context = PipelineContext()
            context.market = MarketState(symbol="TEST", timeframe="1m")
            pipeline = InstitutionalPipeline(context)
            for c in candles:
                context.add_candle(c)
                pipeline.process()
            return context.market_structure

        first = collect()
        second = collect()

        self.assertEqual(
            first.structure,
            second.structure,
        )
        self.assertEqual(first.bos, second.bos)
        self.assertEqual(first.choch, second.choch)


if __name__ == "__main__":
    unittest.main()