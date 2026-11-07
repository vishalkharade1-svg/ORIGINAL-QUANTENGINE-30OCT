"""
====================================================

QuantEngine

Phase 12 -- confirmed-bar causality recertification.

Every downstream consumer requiring confirmed structure may
only act on swings whose right-side confirmation window has
closed: confirmed_bar (== index + right) <= current bar.
Proves (stdlib only, fabricated bars):

  swings:
    1. every emitted swing carries confirmed_bar == index
       + right with confirmed True;
    2. at every prefix length, no emitted swing exceeds the
       current bar's confirmation horizon;
    3. confirmed_as_of() embargos future swings, excludes
       unstamped legacy swings, and fails closed on bad input;
    4. divergent futures never alter prefix swings (future
       mutation invariance at the swing level);
  BOS:
    5. flat extensions leave breaks byte-identical;
    6. divergent futures leave pre-boundary breaks intact;
  FVG:
    7. divergent futures never alter prefix gaps;
  pipeline:
    8. appended future bars never alter already-created
       orders through the canonical setup pipeline.

====================================================
"""

import unittest
from collections import deque
from types import SimpleNamespace

from core.market_structure.swing_engine import SwingEngine

from tests.test_pipeline_regressions import make_candles


def snapshot_swings(swings):
    try:
        items = swings.all()
    except AttributeError:
        items = swings
    return sorted(
        (s.index, s.kind, round(float(s.price), 9),
         round(float(s.score or 0.0), 9), bool(s.institutional),
         int(s.confirmed_bar))
        for s in items
    )


class TestConfirmedBarStamping(unittest.TestCase):

    def test_confirmed_bar_equals_index_plus_right(self):
        engine = SwingEngine(left=3, right=3)
        registry = engine.scan(list(make_candles(n=60)),
                               start_index=0)
        self.assertGreater(len(registry.all()), 0)
        for swing in registry.all():
            self.assertTrue(swing.confirmed)
            self.assertEqual(swing.confirmed_bar,
                             swing.index + 3)

    def test_no_swing_exceeds_confirmation_horizon(self):
        # At EVERY prefix length L (current bar L - 1), every
        # emitted swing must already be confirmed.
        bars = list(make_candles(n=60))
        for length in (7, 8, 15, 30, 60):
            engine = SwingEngine(left=3, right=3)
            registry = engine.scan(bars[:length], start_index=0)
            current_bar = length - 1
            for swing in registry.all():
                self.assertLessEqual(
                    swing.confirmed_bar, current_bar,
                    msg=f"prefix={length} swing={swing.index}")

    def test_confirmed_as_of_embargos_future(self):
        engine = SwingEngine(left=3, right=3)
        registry = engine.scan(list(make_candles(n=60)),
                               start_index=0)
        everything = snapshot_swings(registry)
        self.assertGreater(len(everything), 0)
        current_bar = 59
        as_of_now = registry.confirmed_as_of(current_bar)
        self.assertEqual(snapshot_swings(as_of_now), everything)
        # One bar earlier must hide swings confirmed at 59.
        earlier = registry.confirmed_as_of(current_bar - 1)
        for swing in earlier:
            self.assertLessEqual(swing.confirmed_bar,
                                 current_bar - 1)
        hidden = len(everything) - len(snapshot_swings(earlier))
        self.assertGreaterEqual(hidden, 0)
        latest = max(s[5] for s in everything)
        self.assertLessEqual(latest, current_bar)
        if latest == current_bar:
            self.assertGreater(
                len(snapshot_swings(
                    registry.confirmed_as_of(latest - 1))),
                0)

    def test_confirmed_as_of_excludes_unstamped(self):
        from core.market_structure.swing import Swing
        from core.market_structure.swing_registry import (
            SwingRegistry,
        )
        registry = SwingRegistry()
        legacy = Swing(index=5, timestamp=5, kind="HIGH",
                       price=100.0, confirmed=True,
                       confirmed_bar=0)
        registry.add(legacy)
        self.assertEqual(registry.confirmed_as_of(1000), [])
        self.assertEqual(registry.confirmed_as_of(None), [])
        self.assertEqual(registry.confirmed_as_of("nope"), [])


class TestSwingFutureInvariance(unittest.TestCase):

    def test_divergent_futures_preserve_prefix_swings(self):
        prefix = list(make_candles(n=120))
        base = snapshot_swings(
            SwingEngine(left=3, right=3).scan(
                list(prefix), start_index=0))

        # Wildly divergent futures (rally, crash, flat).
        rally = list(make_candles(n=40, start_price=90000.0))
        crash = list(make_candles(n=40, start_price=1000.0))
        flat = list(make_candles(n=40, start_price=60000.0))

        for future in (rally, crash, flat):
            grown = snapshot_swings(
                SwingEngine(left=3, right=3).scan(
                    list(prefix) + list(future), start_index=0))
            base_ids = {(index, kind) for index, kind, _, _, _, _
                        in base}
            grown_by_id = {(index, kind): row for row in grown
                           for index, kind in [row[:2]]}
            for row in base:
                key = row[:2]
                # The duplicate filter may supersede a prefix
                # swing when the future extends its extreme --
                # but any swing surviving under the same
                # (index, kind) must be bit-identical (score,
                # price and confirmation never depend on the
                # future).
                if key in base_ids and key in grown_by_id:
                    self.assertEqual(grown_by_id[key], row)
            # Every prefix-confirmed swing still confirmed at
            # the same bar (confirmation never moves).
            base_conf = {r[0]: r[5] for r in base}
            grown_conf = {r[0]: r[5] for r in grown
                          if r[0] in base_conf}
            self.assertEqual(grown_conf, base_conf)


def bos_breaks(candles):
    """Drive SwingEngine + BOSEngine over `candles` (fresh
    engines) and return a deterministic break snapshot."""
    from core.market_state import MarketState
    from core.pipeline.pipeline_context import PipelineContext
    from core.market_structure.bos_engine import BOSEngine
    context = PipelineContext()
    context.market = MarketState(symbol="TEST", timeframe="1m")
    context.candles = deque(list(candles), maxlen=1000)
    swing_engine = SwingEngine(left=3, right=3)
    context.swings = swing_engine.scan(
        list(candles), start_index=0)
    bos = BOSEngine()
    bos.analyze(context)

    def snap(break_):
        return (
            getattr(break_, "direction", ""),
            getattr(break_, "bar_index",
                    getattr(break_, "index", 0)),
            round(float(getattr(break_, "price", 0.0)), 9),
        )

    return sorted(snap(b) for b in (context.bos or []))


class TestBOSFutureInvariance(unittest.TestCase):

    def test_flat_extension_byte_identical(self):
        prefix = list(make_candles(n=150))
        before = bos_breaks(prefix)
        grown = bos_breaks(
            list(prefix) + list(make_candles(n=30)))
        self.assertEqual(grown, before)

    def test_divergent_future_preserves_prefix_breaks(self):
        prefix = list(make_candles(n=150))
        before = bos_breaks(prefix)
        boundary = len(prefix)
        wild = list(make_candles(n=30, start_price=200000.0))
        grown = bos_breaks(list(prefix) + wild)
        # Breaks are compared structurally; any break the
        # grown run reports at a pre-boundary bar must equal
        # the prefix run's record (no retroactive rewrite).
        before_at = {b[1]: b for b in before}
        for entry in grown:
            if entry[1] < boundary and entry[1] in before_at:
                self.assertEqual(entry, before_at[entry[1]])


def fvg_gaps(candles, events):
    """Drive FVGScanner with a stubbed displacement feed and
    return a deterministic gap snapshot."""
    from core.market_state import MarketState
    from core.pipeline.pipeline_context import PipelineContext
    from core.fvg.fvg_scanner import FVGScanner
    context = PipelineContext()
    context.market = MarketState(symbol="TEST", timeframe="1m")
    context.candles = deque(list(candles), maxlen=1000)
    context.displacement = SimpleNamespace(
        strong=lambda: list(events))
    FVGScanner().analyze(context)

    def snap(gap):
        return (
            getattr(gap, "direction", ""),
            getattr(gap, "index", 0),
            round(float(getattr(gap, "upper", 0.0)), 9),
            round(float(getattr(gap, "lower", 0.0)), 9),
        )

    return sorted(snap(g) for g in (context.fvgs or []))


class TestFVGFutureInvariance(unittest.TestCase):

    def test_divergent_futures_preserve_prefix_gaps(self):
        prefix = list(make_candles(n=120))
        events = [
            SimpleNamespace(index=i, direction="BULLISH",
                            score=80.0)
            for i in range(2, 100, 7)
        ]
        before = fvg_gaps(prefix, events)
        self.assertGreater(len(before), 0)
        wild = list(make_candles(n=30, start_price=5000.0))
        after = fvg_gaps(list(prefix) + wild, events)
        # Prefix gap rows (index < boundary) are unchanged by
        # the divergent future.
        boundary = len(prefix)
        before_prefix = [g for g in before if g[1] < boundary]
        after_prefix = [g for g in after if g[1] < boundary]
        self.assertEqual(after_prefix, before_prefix)


class TestPipelineFutureInvariance(unittest.TestCase):

    def test_appended_bars_never_rewrite_created_orders(self):
        # Canonical four-engine setup pipeline (builder ->
        # decision -> execution -> risk) over the seeded
        # breakout world: capture created orders, append
        # divergent future bars, and require the earlier
        # orders byte-identical (ids, economics, trigger).
        from tests.test_backtester_breakout import (
            WorldPipeline,
            break_candle,
            miss_candle,
            open_above_candle,
        )
        from core.events.candle_event import CandleEvent

        def drive(candles):
            from core.risk.account_state import AccountState
            pipeline = WorldPipeline()
            # WorldPipeline has no backtester to publish a
            # funded account: seed one so the loss-limit gate
            # sees a real basis (zero-basis accounts cannot
            # size anything downstream either).
            pipeline.context.account = AccountState(
                starting_balance=2000.0, balance=2000.0,
                equity=2000.0, peak_equity=2000.0)
            for candle in candles:
                pipeline.on_candle(CandleEvent(
                    candle=candle, symbol="TEST",
                    timeframe="1m"))
            return sorted(
                (o.order_id, o.setup_id, o.direction,
                 round(float(o.entry), 9),
                 round(float(o.stop_loss), 9),
                 round(float(o.take_profit), 9),
                 o.entry_execution)
                for o in pipeline.context.order_registry.all()
            )

        base = [miss_candle(1), miss_candle(2), break_candle(3),
                open_above_candle(4)]
        before = drive(base)
        self.assertGreater(len(before), 0)
        wild = list(make_candles(n=10, start_price=300000.0))
        after = drive(list(base) + list(wild))
        # Order creation is append-only history: every order
        # created over the base run exists identically after
        # the divergent future.
        for row in before:
            self.assertIn(row, after)


if __name__ == "__main__":
    unittest.main()
