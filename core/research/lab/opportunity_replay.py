"""
====================================================

QuantEngine

Research Lab -- opportunity replay engine (Phase 9B)

Deterministically replays ONE historical OpportunityRecord
forward through the candles under an ExperimentConfig, producing
a CounterfactualOutcome.

Causal ordering (identical to the real backtester):
   * the decision bar is the LAST bar known at decision time
   * the experimental entry is derived from decision-time facts
     only (source entry, decision-time ATR)
   * the entry model may fill from decision+1 onward
   * once filled, the trade is walked forward with the SAME
     stop-before-target exit ordering the production
     TradeSimulator uses
   * MAE / MFE are tracked from the fill bar onward only

No lookahead. The outcome is COUNTERFACTUAL and never enters the
production ledger.
====================================================
"""

from core.research.lab.entry_models import EntryModels, _atr_at_decision
from core.research.lab.exit_models import derive_stop, derive_target
from core.research.lab.counterfactual import CounterfactualOutcome

LONG = "BULLISH"
SHORT = "BEARISH"

_exit_reason_loss = "LOSS"
_exit_reason_win = "WIN"
_exit_reason_no_entry = "NO_ENTRY"
_exit_reason_unsettled = "UNSETTLED_END_OF_SERIES"


def _derive_experimental_entry(config, source_entry, atr, direction):
    offset = config.entry_offset + (config.entry_offset_atr * (atr or 0.0))
    if offset == 0.0:
        return float(source_entry)
    if direction == LONG:
        return float(source_entry) + offset
    return float(source_entry) - offset


class OpportunityReplay:
    """Replays one OpportunityRecord through a candle series."""

    def __init__(self, candles):
        self.candles = candles

    def _source(self, record):
        """Best-effort source economics from the opportunity
        record. Prefers the order (when an order exists) else the
        setup -- so rejected / missed setups replay too."""
        direction = record.direction or ""
        strategy = record.strategy or ""
        setup_id = record.setup_id or ""
        setup = record.setup or {}
        order = record.order or {}

        def first(*keys):
            for k in keys:
                if order.get(k):
                    return order[k]
                if setup.get(k):
                    return setup[k]
            return 0.0

        entry = float(first("entry", "entry_price") or 0.0)
        stop = float(first("stop_loss") or 0.0)
        target = float(first("take_profit") or 0.0)
        rr = float(first("risk_reward") or 0.0)
        atr = float(first("atr") or 0.0)

        decision_bar = order.get("created_bar")
        if decision_bar is None:
            decision_bar = setup.get("bar", 0)
        decision_bar = int(decision_bar or 0)

        rejection = ""
        reasons = setup.get("rejection_reasons") or [""]
        if isinstance(reasons, (list, tuple)) and reasons:
            rejection = ";".join(str(r) for r in reasons if r)

        return {
            "direction": direction,
            "strategy": strategy,
            "setup_id": setup_id,
            "canonical_id": record.canonical_id,
            "exchange": record.exchange,
            "instrument_id": record.instrument_id,
            "timeframe": record.timeframe,
            "entry": entry,
            "stop": stop,
            "target": target,
            "rr": rr,
            "atr": atr,
            "decision_bar": decision_bar,
            "rejection": rejection,
            "baseline_terminal": record.terminal_outcome or "",
        }

    # -------------------------------------------------

    def replay(self, record, config, experiment_id=""):
        """Replay `record` under `config`. Returns
        CounterfactualOutcome."""
        src = self._source(record)
        o = CounterfactualOutcome(
            experiment_id=experiment_id,
            opportunity_id=record.canonical_id or record.setup_id,
            config=config,
        )
        for k in ("baseline_terminal", "canonical_id",
                  "exchange", "instrument_id", "timeframe", "direction",
                  "strategy", "setup_id"):
            setattr(o, k, src[k])
        o.baseline_rejection = src["rejection"]
        baseline_eligible = src["baseline_terminal"] not in ("REJECTED", "CANCELLED")
        o.baseline_eligible = baseline_eligible

        if not src["direction"] or not src["entry"]:
            o.warnings.append("missing source direction/entry")
            return o

        decision_bar = src["decision_bar"]
        o.decision_bar = decision_bar
        o.n_bars_available = len(self.candles) - (decision_bar + 1)

        if decision_bar < 0 or decision_bar >= len(self.candles):
            o.warnings.append("decision bar outside candle series")
            return o

        # decision-time ATR (existing indicator, no lookahead)
        atr = _atr_at_decision(self.candles, decision_bar)
        if not src["atr"] and atr:
            src["atr"] = atr
        atr = src["atr"] or atr

        experimental_entry = _derive_experimental_entry(
            config, src["entry"], atr, src["direction"]
        )
        experimental_stop = derive_stop(
            config, experimental_entry, src["stop"], atr, src["direction"]
        )
        experimental_target = derive_target(
            config, experimental_entry, experimental_stop,
            src["target"], atr, src["direction"],
        )
        risk = abs(experimental_entry - experimental_stop)
        experimental_rr = (
            abs(experimental_target - experimental_entry) / risk
            if risk > 0 else 0.0
        )

        o.experimental_entry = experimental_entry
        o.experimental_stop = experimental_stop
        o.experimental_target = experimental_target
        o.experimental_rr = experimental_rr

        # entry
        direction = src["direction"]
        expiry = config.expiry
        model = config.entry_model
        fm = EntryModels
        if model == "LIMIT_RETEST":
            fi, fp, reason = fm.limit_retest(
                self.candles, decision_bar, config, direction,
                experimental_entry, expiry,
            )
        elif model == "MARKET_CONFIRMATION":
            fi, fp, reason = fm.market_confirmation(
                self.candles, decision_bar, config, direction,
                experimental_entry, expiry,
            )
        else:
            fi, fp, reason = fm.breakout_continuation(
                self.candles, decision_bar, config, direction,
                experimental_entry, expiry,
            )

        if fi is None:
            o.entry_reached = False
            o.filled = False
            o.exit_reason = _exit_reason_no_entry
            return o

        o.entry_reached = True
        o.filled = True
        o.bars_to_entry = fi - decision_bar
        entry_price = fp

        # walk forward, stop-before-target (TradeSimulator parity)
        end = len(self.candles)
        exit_price = None
        exit_i = None
        result = ""
        reason_exit = ""
        mae = 0.0
        mfe = 0.0

        for i in range(fi, end):
            c = self.candles[i]
            # excursion tracking
            if direction == LONG:
                mae = max(mae, entry_price - c.low)
                mfe = max(mfe, c.high - entry_price)
            else:
                mae = max(mae, c.high - entry_price)
                mfe = max(mfe, entry_price - c.low)

            if direction == LONG:
                if c.low <= experimental_stop:
                    exit_i, exit_price, result, reason_exit = i, experimental_stop, "LOSS", "STOP"
                    break
                if c.high >= experimental_target:
                    exit_i, exit_price, result, reason_exit = i, experimental_target, "WIN", "TARGET"
                    break
            else:
                if c.high >= experimental_stop:
                    exit_i, exit_price, result, reason_exit = i, experimental_stop, "LOSS", "STOP"
                    break
                if c.low <= experimental_target:
                    exit_i, exit_price, result, reason_exit = i, experimental_target, "WIN", "TARGET"
                    break

        if exit_i is None:
            o.filled = True
            o.exit_reason = _exit_reason_unsettled
            o.mae = mae
            o.mfe = mfe
            o.bars_in_trade = len(self.candles) - fi
            return o

        o.exit_bar = exit_i
        o.exit_price = exit_price
        o.result = result
        o.exit_reason = reason_exit
        o.mae = mae
        o.mfe = mfe
        o.bars_in_trade = exit_i - fi

        pnl_points = (
            (exit_price - entry_price)
            if direction == LONG
            else (entry_price - exit_price)
        )
        o.pnl = pnl_points
        o.r = (pnl_points / risk) if risk > 0 else 0.0
        return o
