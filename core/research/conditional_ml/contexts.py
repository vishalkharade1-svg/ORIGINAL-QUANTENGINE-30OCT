"""
====================================================

QuantEngine

Conditional ML / Opportunity Discovery (Phase 9L) -- contexts

Builds the immutable, decision-time OpportunityContext per 9A
opportunity: the regime labels AT the decision bar and (when a 9C
baseline fill exists) AT the counterfactual fill bar, the 9F
decision-time feature snapshot evidence, and the frozen baseline
entry state.

Rules:
   * decision bar follows the frozen 9K `decision_bar` helper
     (order.created_bar -> setup.bar -> 0),
   * regime labels come from the data-gated 9K MarketRegime detector;
     no fabrications, no lookahead,
   * fill bar = decision_bar + baseline bars_to_entry (a 9C fact);
     when the baseline never filled there is NO fill-context,
   * feature evidence comes from the 9F FeatureAnalyzer snapshot
     (values or UNAVAILABLE; order-flow / footprint stay UNAVAILABLE
     unless a real order-flow stream exists).
====================================================
"""

from core.research.conditional_ml.types import (
    OpportunityContext,
    UNAVAILABLE,
    ENTRY_STATE_FILLED,
    ENTRY_STATE_NOT_FILLED,
    ENTRY_STATE_UNKNOWN,
)
from core.research.regime import decision_bar, detect_regime, REGIME_DIMENSIONS
from core.research.features.feature_analyzer import FeatureAnalyzer


def _regime_map(mr):
    """dict dimension->label for a MarketRegime; UNAVAILABLE when gated."""
    out = {}
    for dim in REGIME_DIMENSIONS:
        value = getattr(mr, dim, None)
        out[dim] = value if value not in (None, UNAVAILABLE) else UNAVAILABLE
    return out


def _baseline_r(outcome):
    if outcome is None:
        return None
    r = getattr(outcome, "r", None)
    return r


def _safe_detect(candles, bar):
    try:
        return detect_regime(candles, bar)
    except Exception:
        return None


def context_for_record(record, candles, outcome=None, analyzer=None,
                       lookback=20):
    """One OpportunityContext for a single 9A record."""
    bar = decision_bar(record)
    symbol = getattr(record, "symbol", None) or \
        getattr(record, "instrument_id", "")
    direction = (getattr(record, "direction", "") or "").upper()

    generator_regime = _safe_detect(candles, bar)
    generated = _regime_map(generator_regime) if generator_regime else {}

    features = {}
    if analyzer is not None:
        try:
            snap = analyzer.snapshot(record, candles)
            features = dict(getattr(snap, "features", {}) or {})
        except Exception:
            features = {}

    # --- fill context (9C fact, only when the baseline actually
    # --- reached a fill) ---
    filled = {}
    fill_bar = None
    entry_state = ENTRY_STATE_UNKNOWN
    baseline_terminal = ""
    baseline_rejection = ""
    if outcome is not None:
        baseline_terminal = getattr(outcome, "baseline_terminal", "")
        baseline_rejection = getattr(outcome, "baseline_rejection", "")
        if bool(getattr(outcome, "filled", False)):
            entry_state = ENTRY_STATE_FILLED
            bte = getattr(outcome, "bars_to_entry", 0)
            try:
                bte = int(bte)
            except (TypeError, ValueError):
                bte = 1
            fill_bar = bar + max(1, bte)
            fill_mr = _safe_detect(candles, fill_bar)
            filled = _regime_map(fill_mr) if fill_mr else {}
    else:
        baseline_terminal = getattr(record, "terminal_outcome", "")
        entry_state = (
            ENTRY_STATE_FILLED
            if str(baseline_terminal).startswith("FILLED")
            else ENTRY_STATE_NOT_FILLED
        )

    return OpportunityContext(
        opportunity_id=getattr(record, "canonical_id", "") or "",
        symbol=symbol,
        direction=direction,
        decision_bar=bar,
        fill_bar=fill_bar,
        generated_regime=generated,
        filled_regime=filled,
        features=features,
        entry_state=entry_state,
        baseline_terminal=baseline_terminal,
        baseline_rejection=baseline_rejection,
        baseline_r=_baseline_r(outcome),
        baseline_filled=bool(getattr(outcome, "filled", False))
        if outcome is not None else False,
    )


def build_contexts(opportunities, candles, baseline_outcomes=None,
                   lookback=20):
    """Deterministic OpportunityContext list, ordered by
    (decision_bar, canonical_id) -- the 9L row order."""
    analyzer = FeatureAnalyzer(lookback=lookback)
    baseline_outcomes = baseline_outcomes or {}
    rows = []
    for record in opportunities:
        cid = getattr(record, "canonical_id", "") or ""
        outcome = baseline_outcomes.get(cid)
        ctx = context_for_record(record, candles, outcome=outcome,
                                 analyzer=analyzer, lookback=lookback)
        if not ctx.opportunity_id:
            continue
        rows.append(ctx)
    rows.sort(key=lambda c: (c.decision_bar, c.opportunity_id))
    return rows