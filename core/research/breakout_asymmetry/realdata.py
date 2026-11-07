"""
====================================================

QuantEngine

Phase 7E -- REAL-DATA OUT-OF-SAMPLE CAUSAL VALIDATION
(7E.2 -> 7E.9)

This is the REAL causal-data milestone. It answers the
single question that gates any directional policy:

    Does the directional asymmetry observed on the
    SYNTHETIC mirror (Phase 7, origin E geometry) survive
    on UNSEEN REAL causal data?

It is RESEARCH-ONLY and SEVERED FROM PRODUCTION in the
same way the rest of core/research/ is:

  * It consumes the FROZEN production causal pipeline
    (Backtester + InstitutionalPipeline + CausalValidator)
    -- the IDENTICAL causal execution path (causal pipeline,
    protocol 7E.3) -- to PRODUCE a population of real
    CausalValidationState records from untouched, out-of-
    sample real BTCUSDT 1m candles.
  * It emits ONLY evidence (an AsymmetryReport + a verdict).
  * It changes NO thresholds, NO strategy, NO frozen code.

The d3eb2c8 state is the immutable comparison baseline: the
current production behavior, no directional branch, frozen
thresholds. This module never mutates that baseline.

Data provenance (7E.2):
  * The unseen BTCUSDT 1m window (~10,000 bars) is fetched
    live from Delta via the existing HistoricalLoader and
    CACHED to a local (git-ignored) file so a later run is
    reproducible offline and the exact OOS sample is pinned.
  * The window is OUT-OF-SAMPLE by construction: it was never
    used to form the Phase 7 hypothesis.

Causal pipeline (7E.3):
  * The candles are replayed through the EXACT frozen
    construction used by the backtest harness:
        PipelineContext -> InstitutionalPipeline -> EventBus
        -> TradeSimulator -> Backtester.run(candles)
    with ENTRY_MODE = BREAKOUT_CONTINUATION.
  * The auto-wired PipelineContext.causal_validation collects
    a CausalValidationState per trade-eligible setup and
    settles them over the tracking window -- entirely in
    PRODUCTION code. Nothing here re-implements causality.

Direction split + geometry (7E.4-7E.6), origin decomposition
(7E.7) and the execution-held-constant counterfactual (7E.8)
are then re-run over the REAL states by the Phase 7 report
chain, and the verdict (7E.9) is rendered as GO / NO-GO /
INCONCLUSIVE against the A/B/C decision framework.

Usage:
    python -m core.research.breakout_asymmetry.realdata
====================================================
"""

import json
import os

from data.historical_loader import HistoricalLoader
from core.history.candle_mapper import CandleMapper

from core.market_state import MarketState
from core.pipeline.pipeline_context import PipelineContext
from core.pipeline.institutional_pipeline import InstitutionalPipeline
from core.events.event_bus import EventBus
from core.backtesting.trade_simulator import TradeSimulator
from backtesting.backtester import Backtester

from config import risk_settings
from core.execution.entry_model import ENTRY_MODE_BREAKOUT_CONTINUATION

from core.research.breakout_asymmetry import build_report

# ----------------------------------------------------------
# 7E verdict vocabulary
# ----------------------------------------------------------

# Outcome A -- hypothesis CONFIRMED: the Origin-E geometry
# asymmetry reproduces on real OOS data.
VERDICT_GO = "GO"

# Outcome B -- hypothesis REJECTED: real OOS does not
# reproduce it; discard the synthetic hypothesis.
VERDICT_NO_GO = "NO-GO"

# Outcome C -- INCONCLUSIVE: insufficient / unstable sample;
# collect more real data rather than tuning.
VERDICT_INCONCLUSIVE = "INCONCLUSIVE"


# ----------------------------------------------------------
# Baseline tie-back (7E.1): the immutable comparison state.
# ----------------------------------------------------------

BASELINE = {
    "commit": "d3eb2c8",
    "description": (
        "feat(phase7): breakout directional asymmetry research "
        "harness -- current production behavior, NO directional "
        "branch, frozen thresholds. Immutable baseline for 7E."
    ),
}


# ----------------------------------------------------------
# Data (7E.2): real unseen BTCUSDT 1m window + cache.
# ----------------------------------------------------------

DEFAULT_SYMBOL = "BTCUSDT"
DEFAULT_TIMEFRAME = "1m"
DEFAULT_WINDOW_BARS = 10000


def default_cache_path(symbol=DEFAULT_SYMBOL, timeframe=DEFAULT_TIMEFRAME):
    """Location of the pinned OOS sample (under the git-ignored
    data/history/ root so a run is reproducible offline)."""

    return os.path.join(
        "data",
        "history",
        f"{symbol}_{timeframe}_oos.json",
    )


def _fetch_delta_candles(symbol, timeframe, total_candles):
    """Pull the raw Delta candle dicts and return them resolved
    oldest-first (the Backtester expects chronological order;
    the loader returns newest-first)."""

    loader = HistoricalLoader()

    try:

        data = loader.candles_paginated(
            symbol=symbol,
            resolution=timeframe,
            total_candles=total_candles,
            request_delay=0.05,
        )

    finally:

        loader.close()

    result = data.get("result", []) or []

    # Oldest-first for the chronological replay.
    result.sort(key=lambda c: int(c.get("time", 0)))

    return result


def fetch_and_cache_oos_candles(
    symbol=DEFAULT_SYMBOL,
    timeframe=DEFAULT_TIMEFRAME,
    total_candles=DEFAULT_WINDOW_BARS,
    cache_path=None,
    refresh=False,
):
    """Fetch a real unseen window, cache the raw dicts to a
    local (git-ignored) file, and return real Candle objects
    (chromological). If a cache already exists and refresh is
    False, the cached sample is reused verbatim so the exact
    OOS window is pinned and reproducible offline."""

    cache_path = cache_path or default_cache_path(symbol, timeframe)

    if refresh or not os.path.exists(cache_path):

        raw = _fetch_delta_candles(
            symbol, timeframe, total_candles
        )

        os.makedirs(os.path.dirname(cache_path) or ".", exist_ok=True)

        with open(cache_path, "w", encoding="utf-8") as fh:

            json.dump(
                {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "requested": total_candles,
                    "fetched": len(raw),
                    "candles": raw,
                },
                fh,
            )

    else:

        with open(cache_path, encoding="utf-8") as fh:

            payload = json.load(fh)

        raw = payload.get("candles", [])

    mapper = CandleMapper()

    return mapper.map_all(raw), cache_path


def load_oos_candles(cache_path):
    """Load the pinned OOS sample from cache as Candle objects."""

    with open(cache_path, encoding="utf-8") as fh:

        payload = json.load(fh)

    return CandleMapper().map_all(payload.get("candles", []))


# ----------------------------------------------------------
# Causal pipeline (7E.3): the IDENTICAL frozen causal path.
# ----------------------------------------------------------


def run_oos_causal_pipeline(candles, symbol=DEFAULT_SYMBOL,
                            timeframe=DEFAULT_TIMEFRAME):
    """Replay real candles through the frozen production causal
    pipeline and return (states, backtester).

    Construction mirrors the canonical backtest harness exactly:
    a fresh PipelineContext (which AUTO-wires the CausalValidator
    on context.causal_validation), the real InstitutionalPipeline
    computing real indicators / order blocks from the real candles,
    and the Backtester driving observe()/advance() per candle.
    ENTRY_MODE is pinned to BREAKOUT_CONTINUATION so the causal
    filter is byte-identical to the baseline comparison.
    """

    context = PipelineContext()

    context.market = MarketState(
        symbol=symbol,
        timeframe=timeframe,
    )

    event_bus = EventBus()

    pipeline = InstitutionalPipeline(context)

    pipeline.subscribe(event_bus)

    simulator = TradeSimulator()

    backtester = Backtester(
        pipeline,
        event_bus,
        simulator,
    )

    original_mode = getattr(risk_settings, "ENTRY_MODE", None)
    original_active = getattr(risk_settings, "ACTIVE_ENTRY_MODES", None)

    try:

        setattr(risk_settings, "ENTRY_MODE",
                ENTRY_MODE_BREAKOUT_CONTINUATION)
        setattr(risk_settings, "ACTIVE_ENTRY_MODES",
                (ENTRY_MODE_BREAKOUT_CONTINUATION,))

        backtester.run(candles)

    finally:

        # Restore the frozen config verbatim -- this harness
        # never leaves a modified execution config behind.
        if original_mode is not None:
            setattr(risk_settings, "ENTRY_MODE", original_mode)

        if original_active is not None:
            setattr(risk_settings, "ACTIVE_ENTRY_MODES", original_active)

    states = list(context.causal_validation.states())

    return states, backtester


# ----------------------------------------------------------
# 7E gate (7E.9)
# ----------------------------------------------------------


def _verdict(origins, profiles):
    """The A/B/C gate over the REAL data.

    The 7E question is DIRECTION-SPECIFIC: does the SYNTHETIC
    hypothesis (bearish-STRONG / bullish-WEAK -- the direction the
    user's baseline reported; see the Objective) reproduce on
    UNSEEN real causal data?

    A bare geometric |asymmetry| is NOT enough for GO. The gate must
    test the SIGN of the directional profit signal, otherwise a real
    result whose asymmetry points the OPPOSITE way (as it does here:
    real data makes BULLISH slightly stronger) would be misread as
    confirmation. So:

      A (GO)  -- real data reproduces the DIRECTION of the
                 hypothesis: BEARISH beats BULLISH on the settled
                 profit signals (win rate AND expectancy) by a
                 materiality margin. Only then is the directional
                 policy a justified hypothesis for independent
                 validation.
      B (NO-GO) -- the DIRECTIONAL hypothesis does NOT reproduce:
                 either the real gap is below the materiality/ noise
                 band, or it points the OPPOSITE way (BULLISH >=
                 BEARISH). The synthetic hypothesis is discarded.
      C (INCONCLUSIVE) -- the real sample is too thin to separate
                 BULLISH / BEARISH cleanly; collect more real data,
                 do not tune.
    """

    # Too few real setups to separate BULLISH / BEARISH cleanly.
    min_sample = 8

    bull = profiles.get("BULLISH")
    bear = profiles.get("BEARISH")

    if bull is None or bear is None:

        return (
            VERDICT_INCONCLUSIVE,
            "one direction absent from the real sample -- "
            "collect more real data (outcome C), do not tune.",
        )

    if bull.count < min_sample or bear.count < min_sample:

        return (
            VERDICT_INCONCLUSIVE,
            f"real sample too thin (bull {bull.count}, bear "
            f"{bear.count} < {min_sample}) for a stable BULLISH/"
            f"BEARISH split -- collect more real data (outcome C), "
            f"do not tune.",
        )

    # Materiality: a real, signed directional gap large enough to
    # matter (in profit-factor / expectancy / win-rate terms), and
    # unambiguously in the hypothesis' direction.
    materiality_win_pp = 5.0
    materiality_exp_frac = 0.25

    bull_win = bull.win_rate()
    bear_win = bear.win_rate()
    bull_exp = bull.expectancy()
    bear_exp = bear.expectancy()

    # The hypothesis' asserted direction: BEARISH > BULLISH.
    win_gap = bear_win - bull_win
    exp_ref = max(abs(bull_exp), abs(bear_exp), 1e-9)
    exp_gap_frac = (bear_exp - bull_exp) / exp_ref

    reproduces_direction = (
        win_gap >= materiality_win_pp
        and exp_gap_frac >= materiality_exp_frac
    )

    if reproduces_direction:

        return (
            VERDICT_GO,
            "the synthetic DIRECTIONAL hypothesis (bearish-strong / "
            "bullish-weak) REPRODUCES on real OOS data: bearish win "
            f"rate {bear_win:.1f}% vs bullish {bull_win:.1f}% "
            f"(gap +{win_gap:.1f}pp >= {materiality_win_pp}pp) with "
            f"bearish expectancy {bear_exp:+.3f}R vs bullish "
            f"{bull_exp:+.3f}R -> DIRECTIONAL_POLICY is now a "
            "justified hypothesis for INDEPENDENT validation "
            "(outcome A).",
        )

    # The asymmetry, if any, does NOT point the way the hypothesis
    # asserts. Distinguish "reversed" (opposite sign, material) from
    # "absent/noise" so the message reflects the real observation.
    if win_gap <= -materiality_win_pp:

        return (
            VERDICT_NO_GO,
            "the synthetic DIRECTIONAL hypothesis (bearish-strong / "
            "bullish-weak) is REJECTED -- real OOS shows the "
            f"OPPOSITE: bullish win rate {bull_win:.1f}% vs bearish "
            f"{bear_win:.1f}% (gap {win_gap:+.1f}pp). The real "
            "asymmetry, where present, favors BULLISH, not the "
            "hypothesized BEARISH. Discard the synthetic hypothesis "
            "and do NOT branch on it (outcome B).",
        )

    return (
        VERDICT_NO_GO,
        "the synthetic DIRECTIONAL hypothesis does NOT reproduce on "
        f"real OOS data: win-rate gap {win_gap:+.1f}pp below the "
        f"{materiality_win_pp}pp materiality floor (bull "
        f"{bull_win:.1f}% vs bear {bear_win:.1f}%); expectancy "
        f"bull {bull_exp:+.3f}R vs bear {bear_exp:+.3f}R. The "
        "bearish-strong / bullish-weak signal is absent -> discard "
        "the synthetic hypothesis (outcome B).",
    )


# ----------------------------------------------------------
# Orchestrator
# ----------------------------------------------------------


def run_7e(
    symbol=DEFAULT_SYMBOL,
    timeframe=DEFAULT_TIMEFRAME,
    total_candles=DEFAULT_WINDOW_BARS,
    cache_path=None,
    refresh=False,
):
    """Full 7E flow: fetch/cache real data, run the identical
    causal pipeline, decompose on real states, and return the
    verdict along with the AsymmetryReport."""

    candles, used_cache = fetch_and_cache_oos_candles(
        symbol=symbol,
        timeframe=timeframe,
        total_candles=total_candles,
        cache_path=cache_path,
        refresh=refresh,
    )

    states, backtester = run_oos_causal_pipeline(
        candles,
        symbol=symbol,
        timeframe=timeframe,
    )

    report = build_report(states)

    verdict, message = _verdict(
        report.origins, report.profiles
    )

    metadata = {
        "phase": "7E",
        "baseline": BASELINE,
        "data": {
            "symbol": symbol,
            "timeframe": timeframe,
            "requested_bars": total_candles,
            "cached_bars": len(candles),
            "cache_path": used_cache,
            "out_of_sample": True,
        },
        "pipeline": {
            "identical_frozen_path": True,
            "entry_mode": ENTRY_MODE_BREAKOUT_CONTINUATION,
            "engine": "InstitutionalPipeline + Backtester + "
                      "CausalValidator",
        },
        "verdict": {
            "outcome": verdict,
            "message": message,
        },
    }

    return report, verdict, message, metadata


# ----------------------------------------------------------
# CLI entry
# ----------------------------------------------------------


def main():

    report, verdict, message, metadata = run_7e()

    print()
    print("=" * 66)
    print("PHASE 7E -- REAL-DATA OOS CAUSAL VALIDATION")
    print("=" * 66)
    print(f"baseline     : {metadata['baseline']['commit']}")
    print(f"symbol/tf    : {metadata['data']['symbol']} "
          f"{metadata['data']['timeframe']}")
    print(f"bars cached  : {metadata['data']['cached_bars']} "
          f"(requested {metadata['data']['requested_bars']})")
    print(f"cache        : {metadata['data']['cache_path']}")
    print(f"causal path  : {metadata['pipeline']['engine']}")
    print(f"entry mode   : {metadata['pipeline']['entry_mode']}")
    print()
    print(report.summary())
    print()
    print("=" * 66)
    print(f"7E VERDICT   : {verdict}")
    print("=" * 66)
    print(message)
    print()

    results_dir = os.path.join(
        os.path.dirname(__file__),
        "results",
    )

    os.makedirs(results_dir, exist_ok=True)

    dump_path = os.path.join(
        results_dir,
        "phase7e_real_oos_report.json",
    )

    payload = {
        "metadata": metadata,
        "report": report.as_dict(),
    }

    with open(dump_path, "w", encoding="utf-8") as fh:

        json.dump(payload, fh, indent=2)

    print(f"report dumped -> {dump_path}")


if __name__ == "__main__":

    main()
