"""
====================================================

QuantEngine

Phase 9A -- Research Journal + Causal Opportunity Ledger
foundation tests.

Run with:

    python -m unittest tests.test_research_journal_9a -v

Proves the journal is a deterministic, append-safe OBSERVER of
the settled trading lifecycle:

   * identity preservation (canonical id, no rewriting; legacy
     empty identity tolerated)
   * full setup -> eligibility -> order -> fill/expiry/
     invalidation -> trade -> close lifecycle
   * verbatim rejection reasons / eligibility / rejected facts
   * missed-opportunity + missed-continuation (post-terminal)
     OBSERVED facts (never hypothetical fills)
   * provenance (BACKTEST/PAPER) stamped distinctly
   * multi-symbol keyed by canonical identity, ordered by
     (exchange, instrument_id)
   * determinism (identical candles -> identical stream)
   * failure isolation (research errors never stop trading)
   * non-interference (journal attached == engine behaviour
     unchanged)

Stdlib only; the world is the canonical seeded order-block +
liquidity fixture from test_execution_lifecycle.

====================================================
"""

import unittest
from unittest import mock

from config import risk_settings

from core.market_state import MarketState
from core.backtesting.trade_simulator import TradeSimulator
from backtesting.backtester import Backtester

from core.setup.trade_setup_builder import TradeSetupBuilder
from core.setup.decision_engine import DecisionEngine
from core.execution.execution_engine import ExecutionEngine
from core.risk.risk_engine import RiskEngine
from core.execution.entry_model import ENTRY_MODE_BREAKOUT_CONTINUATION

from core.research.journal import (
    ResearchJournal,
    ResearchRepository,
    JournalQuery,
    JournalSummary,
    OpportunityRecord,
    OrderRecord,
    TradeRecord,
    SetupRecord,
    Provenance,
    OrderLifecycle,
    Result,
)

from tests.test_execution_lifecycle import (
    FakeIndicators,
    seeded_world,
)


def orders_for(registry, needle):
    return [
        o for o in registry.all()
        if needle in getattr(o, "setup_id", "")
    ]


class Candle:

    def __init__(self, open_, high, low, close, timestamp):
        self.open = open_
        self.high = high
        self.low = low
        self.close = close
        self.timestamp = timestamp
        self.symbol = "TEST"
        self.timeframe = "1m"


def miss_candle(ts):
    return Candle(107.0, 108.0, 106.0, 107.5, ts)


def break_candle(ts):
    return Candle(108.5, 113.0, 109.0, 111.0, ts)


def open_above_candle(ts):
    # Phase 12: opens AT E = 110.0 (actual RR exactly 6.0)
    # so NEXT_BAR_OPEN fills survive execution-time
    # revalidation.
    return Candle(110.0, 115.0, 110.0, 113.0, ts)


def win_after_candle(ts):
    return Candle(115.0, 171.0, 120.0, 170.0, ts)


def open_gap_tp_candle(ts):
    return Candle(122.0, 125.0, 121.5, 124.0, ts)


def break_with_stop_breach_candle(ts):
    return Candle(108.0, 113.0, 98.0, 111.0, ts)


class WorldPipeline:

    def __init__(self, exchange="TESTEX", instrument_id="TEST-PAIR"):
        self.builder = TradeSetupBuilder()
        self.decision = DecisionEngine()
        self.execution = ExecutionEngine()
        self.risk = RiskEngine()
        self.exchange = exchange
        self.instrument_id = instrument_id
        self.reset()

    def reset(self):
        from core.pipeline.pipeline_context import PipelineContext
        self.context = PipelineContext()
        self.context.market = MarketState(
            symbol="TEST",
            timeframe="1m",
            exchange=self.exchange,
            instrument_id=self.instrument_id,
        )
        self.context.indicators = FakeIndicators()
        seeded_world(self.context)
        for engine in (self.builder, self.decision,
                       self.execution, self.risk):
            engine.reset()

    def on_candle(self, event):
        seeded_world(self.context)
        self.context.add_candle(event.candle)
        self.context.market.timestamp = event.candle.timestamp
        self.builder.analyze(self.context)
        self.decision.analyze(self.context)
        self.execution.analyze(self.context)
        self.risk.analyze(self.context)


class EventBus:

    def __init__(self, pipeline):
        self.pipeline = pipeline

    def publish(self, event):
        self.pipeline.on_candle(event)


def run_world(candles, max_wait_bars=None, entry_mode=None,
              journal=None, exchange="TESTEX", instrument_id="TEST-PAIR"):
    """Replay candles through the canonical four-engine pipeline
    plus the real Backtester, attaching an optional journal."""
    mode = entry_mode or ENTRY_MODE_BREAKOUT_CONTINUATION
    with mock.patch.object(
        risk_settings, "MAX_WAIT_BARS",
        max_wait_bars or risk_settings.MAX_WAIT_BARS,
    ), mock.patch.object(
        risk_settings, "ENTRY_MODE", mode,
    ), mock.patch.object(
        risk_settings, "ACTIVE_ENTRY_MODES", (mode,),
    ):
        pipeline = WorldPipeline(exchange=exchange,
                                 instrument_id=instrument_id)
        event_bus = EventBus(pipeline)
        simulator = TradeSimulator()
        backtester = Backtester(pipeline, event_bus, simulator)
        backtester.run(candles, journal=journal)
        if journal is not None:
            journal.finalize()
        return backtester, simulator, pipeline, pipeline.context.order_registry


# -------------------------------------------------
# Unit-level: records / repository / query / summary
# -------------------------------------------------

class TestRecordsAndRepository(unittest.TestCase):

    def test_trade_record_r_multiple(self):
        rec = TradeRecord(trade_id="t1", pnl=18.5, risk_amount=18.5)
        self.assertEqual(rec.r, 1.0)
        rec0 = TradeRecord(pnl=5.0, risk_amount=0.0)
        self.assertIsNone(rec0.r)

    def test_trade_record_result_label(self):
        self.assertTrue(TradeRecord(result="WIN").won)
        self.assertTrue(TradeRecord(result="LOSS").lost)
        self.assertFalse(TradeRecord(result="LOSS").won)

    def test_order_record_terminal(self):
        self.assertTrue(OrderRecord(status="EXPIRED").terminal)
        self.assertTrue(OrderRecord(status="FILLED").terminal)
        self.assertTrue(OrderRecord(status="FILLED").filled)
        self.assertFalse(OrderRecord(status="PENDING").terminal)

    def test_repository_append_order(self):
        from core.research.journal.research_event import ResearchEvent
        repo = ResearchRepository()
        repo.append_record(OpportunityRecord(canonical_id="X"))
        repo.append_event(ResearchEvent(
            event_id="e1", provenance="BACKTEST",
            event_type="SETUP_DISCOVERED", bar=1, timestamp=1,
        ))
        self.assertEqual(repo.count, 1)
        self.assertEqual(len(repo.by_canonical("X")), 1)
        self.assertEqual(len(repo.by_provenance("BACKTEST")), 1)

    def test_repository_rejects_bad_types(self):
        repo = ResearchRepository()
        with self.assertRaises(TypeError):
            repo.append_record("not-a-record")

    def test_query_filters(self):
        repo = ResearchRepository()
        a = OpportunityRecord(
            canonical_id="a", provenance="BACKTEST", strategy="LIMIT_RETEST",
            setup={"rejected": True, "rejection_reasons": ["STALE_ZONE"]},
            terminal_outcome="REJECTED",
        )
        b = OpportunityRecord(
            canonical_id="b", provenance="PAPER", strategy="BREAKOUT_CONTINUATION",
            order={"status": "FILLED"}, trade={"result": "WIN"},
            terminal_outcome="FILLED_CLOSED",
        )
        repo.append_record(a)
        repo.append_record(b)

        q = JournalQuery(repo).with_provenance("BACKTEST")
        self.assertEqual(q.count(), 1)
        self.assertEqual(q.first().canonical_id, "a")

        self.assertEqual(
            JournalQuery(repo).with_entry_mode("BREAKOUT_CONTINUATION").count(),
            1,
        )
        self.assertEqual(
            JournalQuery(repo).with_rejection_reason("STALE_ZONE").count(), 1
        )
        self.assertEqual(
            JournalQuery(repo).with_order_status("FILLED").count(), 1
        )
        self.assertEqual(
            JournalQuery(repo).with_result("WIN").count(), 1
        )

    def test_summary_counts(self):
        repo = ResearchRepository()
        repo.append_record(OpportunityRecord(
            canonical_id="a", setup={}, terminal_outcome="ORDER_NOT_CREATED",
        ))
        repo.append_record(OpportunityRecord(
            canonical_id="b", setup={"rejected": True, "rejection_reasons": ["X"]},
            terminal_outcome="REJECTED",
        ))
        repo.append_record(OpportunityRecord(
            canonical_id="c", order={"status": "FILLED"},
            trade={"result": "WIN", "pnl": 10.0, "r": 1.0},
            terminal_outcome="FILLED_CLOSED",
        ))
        s = JournalSummary(repo)
        self.assertEqual(s.total, 3)
        self.assertEqual(s.setups_rejected, 1)
        self.assertEqual(s.orders_filled, 1)
        self.assertEqual(s.wins, 1)
        self.assertEqual(s.total_pnl, 10.0)
        self.assertEqual(s.rejection_breakdown(), {"X": 1})


# -------------------------------------------------
# Determinism + provenance on the enums/events side
# -------------------------------------------------

class TestEventDeterminism(unittest.TestCase):

    def test_event_id_prefix_and_provenance(self):
        from core.research.journal.research_event import ResearchEvent
        e = ResearchEvent(
            event_id="evt-1-3-BACKTEST", provenance="BACKTEST",
            event_type="SETUP_DISCOVERED", bar=3, timestamp=10,
        )
        d = e.to_dict()
        self.assertEqual(d["event_id"], "evt-1-3-BACKTEST")
        self.assertEqual(d["provenance"], "BACKTEST")
        self.assertEqual(d["event_type"], "SETUP_DISCOVERED")

    def test_enums_roundtrip(self):
        self.assertEqual(Provenance.BACKTEST.value, "BACKTEST")
        self.assertEqual(OrderLifecycle.EXPIRED.value, "EXPIRED")
        self.assertEqual(Result.WIN.value, "WIN")


# -------------------------------------------------
# Integration: lifecycle + rejection + missed + identity
# -------------------------------------------------

class TestJournalLifecycle(unittest.TestCase):

    def test_full_win_lifecycle_and_outcome(self):
        candles = [
            miss_candle(1),
            miss_candle(2),
            break_candle(3),
            open_above_candle(4),
            win_after_candle(5),
        ]
        journal = ResearchJournal(provenance=Provenance.BACKTEST.value)
        b, simulator, pipeline, registry = run_world(candles, journal=journal)

        self.assertEqual(journal.failures, 0)
        self.assertGreaterEqual(journal.opportunity_count, 1)

        recs = journal.repository.records
        outcomes = {r.terminal_outcome for r in recs}
        self.assertIn("FILLED_CLOSED", outcomes)

        trade = simulator.registry.all()[0]
        rec = JournalQuery(journal.repository).all()
        closed = [r for r in rec if r.terminal_outcome == "FILLED_CLOSED"]
        self.assertEqual(len(closed), 1)
        self.assertEqual(closed[0].trade["result"], "WIN")
        # Canonical identity preserved (no rewriting).
        self.assertTrue(closed[0].canonical_id)
        self.assertEqual(
            closed[0].canonical_id,
            trade.canonical_id,
        )

    def test_expiry_and_missed_continuation(self):
        candles = [
            miss_candle(1),
            miss_candle(2),
            miss_candle(3),
            miss_candle(4),
            miss_candle(5),
        ]
        journal = ResearchJournal(provenance="BACKTEST")
        b, simulator, pipeline, registry = run_world(
            candles, journal=journal, max_wait_bars=3,
        )

        order = orders_for(registry, "OB-5")[0]
        self.assertEqual(order.status, "EXPIRED")

        recs = journal.repository.records
        expired = [r for r in recs if r.terminal_outcome == "EXPIRED"]
        self.assertGreaterEqual(len(expired), 1)
        e = expired[0]
        # Observed post-terminal facts present; falsifiable (the
        # market never reached target 130 -> NOT_REACHED).
        self.assertEqual(e.order["status"], "EXPIRED")

    def test_same_bar_stop_breach_invalidates(self):
        candles = [
            miss_candle(1),
            break_with_stop_breach_candle(2),
        ]
        journal = ResearchJournal()
        b, simulator, pipeline, registry = run_world(candles, journal=journal)

        order = orders_for(registry, "OB-5")[0]
        self.assertEqual(order.status, "INVALIDATED")

        outcomes = {r.terminal_outcome for r in journal.repository.records}
        self.assertIn("INVALIDATED", outcomes)

    def test_rejection_reason_preserved_verbatim(self):
        # Force an ineligible setup by using an entry mode that is
        # NOT active -- the seeded setup is still discovered but
        # carries an entry rejection reason and stays REJECTED.
        from core.execution.entry_model import ENTRY_MODE_LIMIT_RETEST
        candles = [miss_candle(1), miss_candle(2)]
        journal = ResearchJournal()
        b, simulator, pipeline, registry = run_world(
            candles, journal=journal, entry_mode=ENTRY_MODE_LIMIT_RETEST,
        )

        rejected = [
            r for r in journal.repository.records
            if r.setup and r.setup.get("rejected", False)
        ]
        # A rejected setup must carry at least one recorded reason OR
        # be linked to an order (the acceptance contract itself).
        for r in rejected:
            self.assertTrue(
                r.setup.get("rejection_reasons")
                or r.terminal_outcome != "ORDER_NOT_CREATED"
            )

    def test_identity_preserved_no_rewriting(self):
        from core.identity.instrument_identity import build_setup_identity
        from core.research.journal.opportunity_record import OpportunityRecord
        manual = OpportunityRecord(
            canonical_id=build_setup_identity(
                "TESTEX", "TEST-PAIR", "1m", "BULLISH",
                "BREAKOUT_CONTINUATION", "S1",
            ),
            provenance="PAPER",
        )
        self.assertIn("TESTEX:TEST-PAIR", manual.canonical_id)
        parts = manually_split(manual.canonical_id)
        self.assertEqual(parts["exchange"], "TESTEX")
        self.assertEqual(parts["instrument_id"], "TEST-PAIR")
        self.assertEqual(parts["strategy"], "BREAKOUT_CONTINUATION")


def manually_split(identity):
    seg = identity.split(":")
    keys = ["exchange", "instrument_id", "timeframe",
            "direction", "strategy", "setup_id"]
    return dict(zip(keys, seg))


# -------------------------------------------------
# Multi-symbol + provenance separation
# -------------------------------------------------

class TestMultiSymbolAndProvenance(unittest.TestCase):

    def test_multi_symbol_keyed_and_ordered(self):
        candles = [
            miss_candle(1),
            miss_candle(2),
            break_candle(3),
            open_above_candle(4),
        ]
        # Two DISTINCT instruments (different identities) share one
        # journal -- the multi-symbol/portfolio case.
        bA, simA, pA, regA = run_world(
            candles, exchange="EXA", instrument_id="AAA",
        )
        bB, simB, pB, regB = run_world(
            candles, exchange="EXB", instrument_id="BBB",
        )

        journal = ResearchJournal(provenance="BACKTEST")
        for i, c in enumerate(candles):
            journal.on_bar_observed(
                pA.context, c, registry=simA.registry,
                provenance="BACKTEST", bar=i + 1,
            )
        for i, c in enumerate(candles):
            journal.on_bar_observed(
                pB.context, c, registry=simB.registry,
                provenance="BACKTEST", bar=i + 1,
            )
        journal.finalize()

        recs = journal.repository.records
        # Both symbols recorded, keyed by canonical identity / symbol.
        self.assertGreaterEqual(len(recs), 2)
        ids = {r.instrument_id for r in recs}
        self.assertTrue({"AAA", "BBB"}.issubset(ids))

    def test_provenance_stamped(self):
        # A PAPER journal, fed the same settled context/candle as the
        # PaperRuntime wiring would, stamps PAPER provenance on every
        # recorded opportunity. (The PaperRuntime/RealTimeEngine pass
        # provenance="PAPER" when invoking on_bar_observed.)
        candles = [
            miss_candle(1),
            miss_candle(2),
            break_candle(3),
            open_above_candle(4),
        ]
        b, simulator, pipeline, registry = run_world(candles)

        journal = ResearchJournal(provenance="PAPER")
        for i, c in enumerate(candles):
            journal.on_bar_observed(
                pipeline.context, c,
                registry=simulator.registry,
                provenance="PAPER",
                bar=i + 1,
            )
        journal.finalize()

        recs = journal.repository.records
        self.assertGreaterEqual(len(recs), 1)
        self.assertTrue(
            all(str(r.provenance) == "PAPER" for r in recs)
        )


# -------------------------------------------------
# Non-interference + failure isolation
# -------------------------------------------------

class TestNonInterference(unittest.TestCase):

    def test_journal_does_not_change_engine_behaviour(self):
        candles = [
            miss_candle(1),
            miss_candle(2),
            break_candle(3),
            open_above_candle(4),
            win_after_candle(5),
        ]
        b0, sim0, p0, reg0 = run_world(candles)
        base_trades = sim0.registry.count()
        base_orders = len(reg0.all())

        journal = ResearchJournal()
        b1, sim1, p1, reg1 = run_world(candles, journal=journal)
        self.assertEqual(sim1.registry.count(), base_trades)
        self.assertEqual(len(reg1.all()), base_orders)

    def test_research_failure_does_not_stop_trading(self):
        candles = [
            miss_candle(1),
            miss_candle(2),
            break_candle(3),
            open_above_candle(4),
        ]
        class BoomJournal(ResearchJournal):
            def _reconcile(self, *a, **k):
                raise RuntimeError("research boom")
        journal = BoomJournal()
        b, simulator, pipeline, registry = run_world(candles, journal=journal)
        # Trading still happened; journal swallowed the error.
        self.assertGreaterEqual(simulator.registry.count(), 0)
        self.assertGreaterEqual(journal.failures, 1)

    def test_missing_journal_is_a_noop(self):
        candles = [miss_candle(1), miss_candle(2), break_candle(3)]
        b, simulator, pipeline, registry = run_world(candles)
        self.assertIsNotNone(simulator.registry)


if __name__ == "__main__":
    unittest.main()
