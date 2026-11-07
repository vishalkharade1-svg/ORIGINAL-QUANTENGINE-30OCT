"""
====================================================

QuantEngine

Institutional Backtester Test

====================================================
"""

from config.settings import settings

from config import risk_settings

from data.historical_loader import HistoricalLoader

from core.market_state import MarketState

from core.pipeline.pipeline_context import PipelineContext
from core.pipeline.institutional_pipeline import InstitutionalPipeline

from core.events.event_bus import EventBus

from core.backtesting.trade_simulator import TradeSimulator

from backtesting.backtester import Backtester

import logging
from core.common.logging_config import configure_logging

# This is an interactive diagnostic script, unlike the
# unittest suite (which should stay silent by default) --
# enable INFO-level logging so pagination diagnostics
# (why candles_paginated stopped where it did) are visible.
configure_logging(level=logging.INFO)


def main():

    print()

    print("=" * 70)
    print("QUANTENGINE BACKTEST")
    print("=" * 70)

    loader = HistoricalLoader()

    # A single request caps out around 2000 candles (Delta's
    # API limit) -- candles_paginated() walks backward across
    # multiple requests to gather more. 5000 x 1m candles is
    # roughly 3.5 days of history, enough for EMA200 warmup
    # (200 bars) plus a meaningful window for the pipeline to
    # actually find displacement/FVG/OB confluence in, unlike
    # the ~339-bar window this used to load by default.
    history = loader.candles_paginated(
        settings.SYMBOLS[0],
        resolution=settings.TIMEFRAME,
        total_candles=5000,
    )

    from data.candle_builder import CandleBuilder

    builder = CandleBuilder(max_history=len(history["result"]) or 1)

    builder.load_history(

        list(reversed(history["result"]))

    )

    candles = list(builder.history)

    print(f"Loaded {len(candles)} candles.")

    # -------------------------------------------------

    market = MarketState(

        symbol=settings.SYMBOLS[0]

    )

    context = PipelineContext()

    context.market = market

    event_bus = EventBus()

    pipeline = InstitutionalPipeline(

        context

    )

    # -------------------------------------------------
    # Register Engines
    # -------------------------------------------------

    pipeline.subscribe(

        event_bus

    )

    simulator = TradeSimulator()

    backtester = Backtester(

        pipeline,

        event_bus,

        simulator,

    )

    trades = backtester.run(

        candles

    )

    print()

    print("=" * 70)
    print("BACKTEST COMPLETE")
    print("=" * 70)

    print()

    print(
        "Bars Processed :",

        backtester.total_bars,

    )

    print()

    # -------------------------------------------------
    # Phase 4E order/setup ledger (the economic report the
    # 5000-bar regression must carry):
    #   structural setups discovered  -- distinct structural setup
    #       ids the EconomicSetupRegistry ever saw;
    #   economic duplicates suppressed -- exotic variants collapsed
    #       (identical fingerprint + clustered near-identical);
    #   clusters formed  -- near-identical execution zones merged;
    #   orders created / filled / expired / invalidated;
    #   pending capacity (average / maximum live pending orders).
    # The OBJECTIVE is independence of opportunities, not a higher
    # trade count -- identical economics must never consume more
    # than one pending slot.
    # -------------------------------------------------

    order_registry = context.order_registry

    economic = context.economic_registry

    created_orders = len(order_registry.all())

    filled_orders = len(order_registry.filled())

    expired_orders = len(order_registry.expired())

    invalidated_orders = len(order_registry.invalidated())

    econ_stats = economic.summary() if economic is not None else {}

    print("Phase 4E Ledger")

    print()

    print(

        "Structural Setups Discovered :",

        econ_stats.get("distinct_structural_ids", 0),

    )

    print(

        "Economic Duplicates Suppressed :",

        econ_stats.get("duplicates_suppressed", 0),

    )

    print(

        "Distinct Economic Ideas :",

        econ_stats.get("distinct_fingerprints", 0),

    )

    print(

        "Clusters Formed :",

        econ_stats.get("clusters_formed", 0),

    )

    print()

    print("Orders Created :", created_orders)

    print("Orders Filled :", filled_orders)

    print("Orders Expired :", expired_orders)

    print("Orders Invalidated :", invalidated_orders)

    print()

    print(

        "Re-Entry Cooldown Suppressions :",

        econ_stats.get("reentry_cooldown_suppressed", 0),

    )

    print()

    print(

        "Avg Pending Orders :",

        round(backtester.pending_orders_average, 2),

    )

    print(

        "Max Pending Orders :",

        backtester.pending_orders_max,

    )

    print()

    print("Max Pending Explanation :")

    print("First reached at bar :", backtester.pending_orders_max_bar)

    max_directions = backtester.pending_orders_max_directions

    for direction in ("BULLISH", "BEARISH"):

        print(

            f"{direction} pending at the max bar :",

            max_directions.get(direction, 0),

        )

    print()

    # -------------------------------------------------
    # Phase 4F ENTRY FEASIBILITY REPORT (STEP 3 / 4):
    # what price ACTUALLY did after each setup was created,
    # measured only after the creating candle (no look-ahead):
    #   how far the entry was on the four normalization axes
    #       (absolute / percent / ATR multiples / ticks);
    #   how often the entry was genuinely reachable;
    #   the largest retracement toward the entry observed after;
    #   the average distance still remaining at expiration;
    #   MISSED_CONTINUATION -- entry never touched yet the
    #       market ran >= 50% of the way to the target within
    #       the tracking window.
    # Purely DIAGNOSTIC. Never altered a live decision.
    # -------------------------------------------------

    tracker = getattr(context, "entry_tracker", None)

    if tracker is not None:

        def _feasibility_block(title, rep):

            print(f"ENTRY FEASIBILITY {title}")

            print("Setups Tracked :", rep["total_setups"])

            for cls, n in rep["by_class"].items():

                if n:

                    print("  ", cls, ":", n)

            print("Entries Reached :", rep["entries_reached"])

            print("Entries Not Reached :", rep["entries_not_reached"])

            print("Avg Entry Distance :", rep["avg_entry_distance"])

            print("Median Entry Distance :", rep["median_entry_distance"])

            print("Avg Entry Distance (ATR):", rep["avg_entry_distance_atr"])

            print("Median Entry Distance (ATR):", rep["median_entry_distance_atr"])

            print("Avg Retracement Toward Entry :", rep["avg_retracement_toward_entry"])

            print("Avg Remaining Distance At Terminal :", rep["avg_distance_remaining_at_terminal"])

            print("Missed Continuations :", rep["missed_continuation"])

            for status, n in rep["by_terminal_state"].items():

                print("  Terminal :", status, ":", n)

            for mode, n in rep["entry_modes"].items():

                print("  Entry Mode :", mode, ":", n)

            print()

        _feasibility_block("REPORT (ALL)", tracker.report())

        _feasibility_block("BULLISH", tracker.report("BULLISH"))

        _feasibility_block("BEARISH", tracker.report("BEARISH"))

    # -------------------------------------------------
    # Phase 4G ORDER BLOCK FRESHNESS REPORT (STEP 11) +
    # ENTRY ELIGIBILITY REPORT (STEP 12): an AT-CREATION
    # ledger of every canonical structural zone the builder
    # generated a candidate for -- eligible or rejected -- with
    # its zone age (bucketed 0-5/6-15/16-30/31-60/61-120/120+),
    # freshness state, entry distance and explicit rejection
    # reason. Everything is snapshotted at the creating candle
    # (no future bars). Rejections counted here are zones the
    # Phase 4F funnel could never see because no order/state
    # was minted for them. Diagnostic only.
    # -------------------------------------------------

    zone_log = getattr(context, "zone_eligibility", None)

    if zone_log is not None:

        def _eligibility_block(title, rep):

            print(f"ENTRY ELIGIBILITY {title}")

            print("Zones Considered :", rep["zones_considered"])

            print("Distinct Economic Ideas :", rep["distinct_fingerprints"])

            print("Structurally Valid :", rep["structurally_valid"])

            print("Structurally Invalid :", rep["structurally_invalid"])

            print("Trade Eligible :", rep["trade_eligible"])

            print("Trade Ineligible :", rep["trade_ineligible"])

            for reason, n in rep["by_reason"].items():

                if n:

                    print("  Rejected :", reason, ":", n)

            print("Diagnostic Weak Displacement :", rep["weak_displacement"])

            print("Diagnostic Too Many Touches :", rep["too_many_touches"])

            print()

            print(f"ORDER BLOCK FRESHNESS {title}")

            for state, n in rep["by_freshness"].items():

                if n:

                    print("  Freshness :", state, ":", n)

            for bucket, n in rep["by_age_bucket"].items():

                if n:

                    print("  Age Bucket :", bucket, ":", n)

            print("Avg Zone Age Bars :", rep["avg_zone_age_bars"])

            print("Avg Zone Distance :", rep["avg_zone_distance"])

            print("Avg Zone Distance (ATR) :", rep["avg_zone_distance_atr"])

            if title.startswith("REPORT (ALL)"):

                print("Structural Zone Duplicates Suppressed :",
                      rep["structural_suppressed"])

            print()

        _eligibility_block("REPORT (ALL)", zone_log.report())

        _eligibility_block("BULLISH", zone_log.report("BULLISH"))

        _eligibility_block("BEARISH", zone_log.report("BEARISH"))

    # -------------------------------------------------
    # Phase 4G extension ENTRY MODEL COMPARISON REPORT:
    # reachability under all three entry models --
    #   LIMIT_RETEST            (the executable baseline)
    #   MARKET_CONFIRMATION     (shadow)
    #   BREAKOUT_CONTINUATION   (shadow)
    # measured over every trade-eligible structural setup, plus
    # the ATR-DISTANCE vs MAX_WAIT_BARS EXPIRY relationship
    # (whether ~15-ATR-average entries vs a 30-bar expiry is
    # structural or calibration). LIMIT_RETEST stays the ONLY
    # executable mode. Diagnostic only; gated on
    # ENABLE_ENTRY_SHADOW.
    # -------------------------------------------------

    entry_shadow = getattr(context, "entry_shadow", None)

    if (
        entry_shadow is not None
        and bool(
            getattr(risk_settings, "ENABLE_ENTRY_SHADOW", True)
        )
    ):

        from core.setup.entry_shadow import format_shadow_report

        shadow_rep = entry_shadow.report()

        print(format_shadow_report(
            shadow_rep, "ENTRY MODEL COMPARISON REPORT (ALL)"
        ))

        print()

        print(format_shadow_report(
            entry_shadow.report("BULLISH"),
            "ENTRY MODEL COMPARISON (BULLISH)",
        ))

        print()

        print(format_shadow_report(
            entry_shadow.report("BEARISH"),
            "ENTRY MODEL COMPARISON (BEARISH)",
        ))

        print()

    # -------------------------------------------------
    # PHASE 4H CAUSAL BREAKOUT VALIDATION REPORT:
    # BREAKOUT_CONTINUATION re-run under STRICT causal rules
    # (frozen setup, trigger at the trigger candle's close,
    # entry at the OPEN of the trigger + 1, deterministic
    # intrabar SL/TP policies) with win rate / profit factor /
    # expectancy / average R / MAE-MFE / max drawdown, a
    # bullish-vs-bearish split, and the MARKET_CONFIRMATION
    # rejection-stage diagnosis. LIMIT_RETEST stays the ONLY
    # executable mode -- this validator produces no order.
    # Diagnostic only; gated on ENABLE_CAUSAL_VALIDATION with
    # the INTRABAR_POLICY-selected primary policy.
    # -------------------------------------------------

    causal_validation = getattr(context, "causal_validation", None)

    if (
        causal_validation is not None
        and bool(
            getattr(
                risk_settings, "ENABLE_CAUSAL_VALIDATION", True
            )
        )
    ):

        from core.setup.causal_validation import format_causal_report

        setups_discovered = econ_stats.get(
            "distinct_structural_ids", 0
        )

        causal_rep = causal_validation.report()

        print(format_causal_report(
            causal_rep,
            "PHASE 4H CAUSAL BREAKOUT VALIDATION (ALL)",
            setups_discovered=setups_discovered,
        ))

        print()

        print(format_causal_report(
            causal_validation.report("BULLISH"),
            "PHASE 4H CAUSAL BREAKOUT VALIDATION (BULLISH)",
            setups_discovered=setups_discovered,
        ))

        print()

        print(format_causal_report(
            causal_validation.report("BEARISH"),
            "PHASE 4H CAUSAL BREAKOUT VALIDATION (BEARISH)",
            setups_discovered=setups_discovered,
        ))

        print()

    # Order counts by entry mode (Phase 4F STEP 6 ledger).

    from collections import Counter

    mode_counts = Counter(
        o.entry_mode for o in order_registry.all()
    )

    for mode, n in sorted(mode_counts.items()):

        print("Orders By Entry Mode :", mode, ":", n)

    print()

    print(

        "Trades :",

        trades.count(),

    )

    print()

    if trades.count():

        last = trades.all()[-1]

        print("LAST TRADE")

        print(

            "Direction :",

            last.direction,

        )

        print(

            "Entry :",

            round(last.entry, 2),

        )

        print(

            "Exit :",

            round(last.exit_price, 2),

        )

        print(

            "Result :",

            last.result,

        )

        print(

            "PnL :",

            round(last.pnl, 2),

        )

    loader.close()


if __name__ == "__main__":

    main()