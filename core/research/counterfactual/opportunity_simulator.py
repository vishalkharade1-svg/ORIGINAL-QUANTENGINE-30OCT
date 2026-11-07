"""
====================================================

QuantEngine

Counterfactual Simulation -- opportunity simulator (Phase 9C)

Deterministic facade that takes an original OpportunityRecord +
historical candles + a CounterfactualConfig and evaluates what
would have happened under that explicit alternative configuration.

FROZEN ENTRY ROUTING: entry is decided ONLY by the canonical
production deciders (core/execution/entry_model.get_entry_model)
for LIMIT_RETEST / MARKET_CONFIRMATION / BREAKOUT_CONTINUATION.
No entry semantics are reimplemented here. A mode with no canonical
decider is rejected at config construction and here defensively
reported NON_EVALUABLE -- never invented.

CAUSALITY (no lookahead):
    decision candle -> canonical entry decision -> executable fill
    -> future candles only -> stop/target outcome.
For BREAKOUT_CONTINUATION: trigger at N -> next executable bar ->
NEXT_BAR_OPEN fill. The trigger candle's future is never used to
derive the execution price.

OUTCOME HORIZON: after a fill, the trade is walked forward with the
EXPLICIT CounterfactualConfig.outcome_bars horizon. The default
(None) walks until stop/target or the end of the supplied series --
exactly the production TradeSimulator holding contract
(MAX_WAIT_BARS only bounds the ENTRY window, never post-fill
holding). So the default counterfactual holding horizon == production.

EXPERIMENTAL LEVELS are computed independently and validated; the
source OpportunityRecord is NEVER mutated and is reusable for any
number of experiments.

LEDGER BOUNDARY: output provenance === COUNTERFACTUAL; the result
never enters TradeRegistry / Account / PortfolioState / SharedCapital
/ paper / live / production ledger.
====================================================
"""

import math

from core.execution.entry_model import get_entry_model
from core.research.counterfactual import opportunity_categories as _cat
from core.research.lab.counterfactual import CounterfactualOutcome
from core.research.lab.entry_models import _atr_at_decision
from core.research.lab.exit_models import derive_stop, derive_target

LONG = "BULLISH"
SHORT = "BEARISH"
_EVALUABLE_DIRECTIONS = (LONG, SHORT)

_exit_reason_no_entry = "ENTRY_NOT_REACHED"
_exit_reason_no_exec_bar = "NO_EXECUTABLE_BAR"
_exit_reason_unsettled = "UNSETTLED_END_OF_SERIES"
_exit_reason_stop = "STOP"
_exit_reason_target = "TARGET"


def _window_end(candles, start, expiry):
    """Entry search window end (expiry-aware)."""
    if expiry is None:
        return len(candles) - 1
    return min(len(candles) - 1, start + int(expiry) - 1)


def _derive_experimental_entry(cfg, source_entry, atr, direction):
    offset = cfg.entry_offset + (cfg.entry_offset_atr * (atr or 0.0))
    if offset == 0.0:
        return float(source_entry)
    return (
        float(source_entry) + offset
        if direction == LONG
        else float(source_entry) - offset
    )


def _finite(x):
    try:
        f = float(x)
    except (TypeError, ValueError):
        return False
    return math.isfinite(f)


def _validate_geometry(entry, stop, target, direction):
    """Validate experimental geometry. Returns a reason string if
    invalid, else None."""
    if not (_finite(entry) and _finite(stop) and _finite(target)):
        return "non-finite experimental geometry"
    risk = abs(entry - stop)
    if risk <= 0:
        return "zero-risk geometry (|entry - stop| == 0)"
    if direction == LONG and not (stop < entry < target):
        return f"invalid geometry: need stop<entry<target for {LONG}"
    if direction == SHORT and not (target < entry < stop):
        return f"invalid geometry: need target<entry<stop for {SHORT}"
    return None


class OpportunitySimulator:
    """Deterministic counterfactual replay of one opportunity."""

    def _source(self, record):
        """Source extraction with EXPLICIT None checks -- a present
        zero-like value is NOT treated as missing."""
        setup = record.setup or {}
        order = record.order or {}

        def first(*keys):
            for k in keys:
                if k in order and order[k] is not None:
                    return order[k]
            for k in keys:
                if k in setup and setup[k] is not None:
                    return setup[k]
            return None

        created_bar = order.get("created_bar")
        if created_bar is None:
            created_bar = setup.get("bar")
        reasons = setup.get("rejection_reasons") or []
        rejection = ""
        if isinstance(reasons, (list, tuple)):
            rejection = ";".join(str(r) for r in reasons if r)

        return {
            "direction": (record.direction or "").upper(),
            "strategy": record.strategy or "",
            "setup_id": record.setup_id or "",
            "canonical_id": record.canonical_id,
            "exchange": record.exchange,
            "instrument_id": record.instrument_id,
            "timeframe": record.timeframe,
            "entry": first("entry", "entry_price"),
            "stop": first("stop_loss"),
            "target": first("take_profit"),
            "atr": first("atr"),
            "decision_bar": created_bar,
            "rejection": rejection,
            "baseline_terminal": record.terminal_outcome or "",
        }

    # -------------------------------------------------

    def simulate(self, record, config, candles, experiment_id=None):
        """Replay `record` under `config` through `candles`.
        Returns CounterfactualOutcome."""
        cfg = config.to_config()
        src = self._source(record)

        o = CounterfactualOutcome(
            opportunity_id=src["canonical_id"] or src["setup_id"],
            config=cfg,
        )
        o.experiment_id = experiment_id or config.experiment_id()
        o.baseline_terminal = src["baseline_terminal"]
        o.baseline_rejection = src["rejection"]
        for k in ("canonical_id", "exchange", "instrument_id", "timeframe",
                  "direction", "strategy", "setup_id"):
            setattr(o, k, src[k])
        o.category = _cat.classify_opportunity(record)

        # ---- direction validation ----
        direction = src["direction"]
        if direction not in _EVALUABLE_DIRECTIONS:
            o.warnings.append(
                f"invalid direction {src['direction']!r} -- not evaluable"
            )
            o.category = _cat.NON_EVALUABLE
            return o

        # ---- canonical decider availability ----
        model = get_entry_model(cfg.entry_model)
        if model is None:
            o.warnings.append(
                f"no canonical decider for entry model {cfg.entry_model!r}"
            )
            o.category = _cat.NON_EVALUABLE
            return o

        # ---- decision bar bounds ----
        decision_bar = src["decision_bar"]
        o.decision_bar = int(decision_bar or 0)
        o.n_bars_available = len(candles) - (o.decision_bar + 1)
        if o.decision_bar < 0 or o.decision_bar >= len(candles):
            o.warnings.append("decision bar outside candle series")
            o.category = _cat.NON_EVALUABLE
            return o

        # ---- experimental levels (independent, decision-time only) ----
        atr = src["atr"]
        if atr is None or not _finite(atr):
            atr = _atr_at_decision(candles, o.decision_bar)
        atr = float(atr or 0.0)

        source_entry = float(src["entry"] or 0.0)
        source_stop = float(src["stop"] or 0.0)
        source_target = float(src["target"] or 0.0)

        experimental_entry = _derive_experimental_entry(
            cfg, source_entry, atr, direction
        )
        experimental_stop = derive_stop(
            cfg, experimental_entry, source_stop, atr, direction
        )
        experimental_target = derive_target(
            cfg, experimental_entry, experimental_stop,
            source_target, atr, direction,
        )

        geo_err = _validate_geometry(
            experimental_entry, experimental_stop, experimental_target, direction
        )
        if geo_err:
            o.warnings.append(f"invalid experimental geometry: {geo_err}")
            o.category = _cat.NON_EVALUABLE
            return o

        risk = abs(experimental_entry - experimental_stop)
        experimental_rr = abs(experimental_target - experimental_entry) / risk
        if not math.isfinite(experimental_rr) or experimental_rr <= 0:
            o.warnings.append(f"invalid experimental RR: {experimental_rr!r}")
            o.category = _cat.NON_EVALUABLE
            return o

        o.experimental_entry = experimental_entry
        o.experimental_stop = experimental_stop
        o.experimental_target = experimental_target
        o.experimental_rr = experimental_rr

        from core.research.counterfactual.counterfactual_config import setup_view
        view = setup_view(
            experimental_entry, experimental_stop, experimental_target,
            direction, src["setup_id"],
        )

        # ---- canonical entry routing over the entry window ----
        start = o.decision_bar + 1
        end = _window_end(candles, start, cfg.expiry)
        model_mode = cfg.entry_model
        fill_bar = None
        fill_price = None

        for i in range(start, end + 1):
            decision = model.decide(view, candles[i], i)
            if not decision.triggered:
                continue
            if model_mode == "BREAKOUT_CONTINUATION":
                eb = decision.entry_bar
                if eb is None or eb >= len(candles):
                    # canonical trigger existed but no executable bar
                    o.entry_reached = False
                    o.filled = False
                    o.exit_reason = _exit_reason_no_exec_bar
                    o.mae = 0.0
                    o.mfe = 0.0
                    return o
                fill_bar = eb
                fill_price = float(candles[eb].open)  # NEXT_BAR_OPEN
            else:
                fill_bar = decision.entry_bar
                fill_price = float(decision.entry_price or 0.0)
            break

        if fill_bar is None or fill_price is None or fill_price <= 0:
            o.entry_reached = False
            o.filled = False
            o.exit_reason = _exit_reason_no_entry
            o.mae = 0.0
            o.mfe = 0.0
            return o

        o.entry_reached = True
        o.filled = True
        o.fill_bar = fill_bar
        o.bars_to_entry = fill_bar - o.decision_bar
        entry_price = fill_price
        # the ACTUAL executed fill price (parity: production uses the
        # fill price as the trade's entry price).
        o.entry_price = fill_price
        # R multiple uses the ACTUAL fill price for risk, in parity
        # with the canonical _r_multiple contract: risk = |fill - stop|.
        fill_risk = abs(entry_price - experimental_stop)
        o.fill_risk = fill_risk

        # ---- outcome walk (TradeSimulator parity: stop-before-target)
        #      within the EXPLICIT outcome horizon ----
        horizon_end = (
            len(candles)
            if config.outcome_bars is None
            else min(len(candles), fill_bar + int(config.outcome_bars))
        )
        exit_i = None
        exit_price = None
        result = ""
        reason_exit = ""
        mae = 0.0
        mfe = 0.0
        for i in range(fill_bar, horizon_end):
            c = candles[i]
            if direction == LONG:
                mae = max(mae, entry_price - c.low)
                mfe = max(mfe, c.high - entry_price)
            else:
                mae = max(mae, c.high - entry_price)
                mfe = max(mfe, entry_price - c.low)

            if direction == LONG:
                if c.low <= experimental_stop:
                    exit_i, exit_price, result, reason_exit = (
                        i, experimental_stop, "LOSS", _exit_reason_stop
                    )
                    break
                if c.high >= experimental_target:
                    exit_i, exit_price, result, reason_exit = (
                        i, experimental_target, "WIN", _exit_reason_target
                    )
                    break
            else:
                if c.high >= experimental_stop:
                    exit_i, exit_price, result, reason_exit = (
                        i, experimental_stop, "LOSS", _exit_reason_stop
                    )
                    break
                if c.low <= experimental_target:
                    exit_i, exit_price, result, reason_exit = (
                        i, experimental_target, "WIN", _exit_reason_target
                    )
                    break

        if exit_i is None:
            o.exit_reason = _exit_reason_unsettled
            o.mae = mae
            o.mfe = mfe
            o.bars_in_trade = horizon_end - fill_bar
            return o

        o.exit_bar = exit_i
        o.exit_price = exit_price
        o.result = result
        o.exit_reason = reason_exit
        o.mae = mae
        o.mfe = mfe
        # bars the trade lived, counting the fill bar through the exit
        # bar, mirroring production bars_held (the fill candle is the
        # first update candle).
        o.bars_in_trade = exit_i - fill_bar + 1

        pnl_points = (
            (exit_price - entry_price)
            if direction == LONG
            else (entry_price - exit_price)
        )
        o.pnl = pnl_points
        o.r = (pnl_points / fill_risk) if fill_risk > 0 else 0.0
        return o
