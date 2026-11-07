"""
====================================================

Institutional Trade Simulator

====================================================
"""

from core.backtesting.accounting import (
    classify_pnl,
    gross_pnl,
    net_pnl,
    position_return_percent,
)
from core.backtesting.trade import Trade
from core.backtesting.trade_registry import TradeRegistry
from core.backtesting.trailing_stop import (
    METHOD_R_DISTANCE,
    SUPPORTED_TRAILING_METHODS,
    TrailingStopConfig,
    evaluate_trailing_stop,
)

from core.common.logging_config import get_logger
from core.risk.costs import post_cost_rr, post_cost_trailing
from core.risk.position_manager import PositionManager
from core.execution.economics import FundingSchedule
from config import risk_settings

import json
import math
from dataclasses import asdict, fields as dataclass_fields
from pathlib import Path
from tempfile import mkstemp
from threading import RLock

log = get_logger(__name__)

_STATE_SCHEMA = "quantengine.trade_state.v1"


class TradeSimulator:

    def __init__(self, position_manager=None, funding_schedule=None,
                 tick_size=None, gap_fill_mode="CONSERVATIVE",
                 state_path=None):

        self.registry = TradeRegistry()

        self.current_trade = None

        if funding_schedule is not None and not isinstance(funding_schedule, FundingSchedule):
            raise TypeError("funding_schedule must be a FundingSchedule")
        self.funding_schedule = funding_schedule

        # Instrument tick used to round trailing stops.  None means use the
        # configured economic tick; callers working with a verified contract
        # may pass the exact increment.  0.0 explicitly disables rounding.
        if tick_size is None:
            tick_size = float(getattr(risk_settings, "ECONOMIC_TICK_SIZE", 0.0) or 0.0)
        tick_size = float(tick_size or 0.0)
        if not math.isfinite(tick_size) or tick_size < 0.0:
            raise ValueError("tick_size must be a non-negative finite number")
        self.tick_size = tick_size

        self.gap_fill_mode = str(gap_fill_mode or "CONSERVATIVE").upper()
        if self.gap_fill_mode not in ("CONSERVATIVE", "STOP_PRICE"):
            raise ValueError("gap_fill_mode must be CONSERVATIVE or STOP_PRICE")

        self.state_path = Path(state_path) if state_path is not None else None
        self._state_lock = RLock()
        self._update_sequence = 0
        if self.state_path is not None:
            self._load_state()

        # Execution-layer quantity hygiene enforced by the
        # SHARED PositionManager at the single choke point every
        # mode (Backtest / Paper / Live Broker) passes through.
        self.position_manager = (
            position_manager
            if position_manager is not None
            else PositionManager()
        )

    # -------------------------------------------------
    # Open-trade persistence (paper restart safety)
    # -------------------------------------------------

    def configure_state_path(self, path, load=True):
        """Attach a state file after construction (paper runtime convenience)."""
        with self._state_lock:
            if self.current_trade is not None:
                raise ValueError("cannot change state_path while a trade is open")
            self.state_path = Path(path)
            if load:
                self._load_state()

    def _load_state(self):
        if self.state_path is None or not self.state_path.exists():
            return
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
            if payload.get("schema") != _STATE_SCHEMA:
                raise ValueError("unsupported trade state schema")
            raw = payload.get("trade")
            self._update_sequence = int(payload.get("update_sequence", 0) or 0)
            if raw is None:
                return
            self.restore_trade_state(raw)
        except Exception as exc:  # noqa: BLE001 (fail closed)
            raise ValueError("invalid trade state: %s" % exc) from exc

    def export_trade_state(self):
        with self._state_lock:
            return asdict(self.current_trade) if self.current_trade is not None else None

    def restore_trade_state(self, raw):
        if not isinstance(raw, dict):
            raise ValueError("trade state must be an object")
        allowed = {f.name for f in dataclass_fields(Trade)}
        unknown = set(raw) - allowed
        if unknown:
            raise ValueError("unknown trade state fields: %s"
                             % ", ".join(sorted(unknown)))
        trade = Trade(**raw)
        if trade.status != "OPEN":
            raise ValueError("persisted trade is not OPEN")
        trade.validate_executable()
        if trade.tick_size <= 0.0:
            trade.tick_size = self.tick_size
        self.current_trade = trade


    def _persist_state(self):
        if self.state_path is None:
            return
        with self._state_lock:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "schema": _STATE_SCHEMA,
                "update_sequence": int(self._update_sequence),
                "trade": asdict(self.current_trade) if self.current_trade is not None else None,
            }
            data = json.dumps(payload, sort_keys=True, indent=2) + "\n"
            fd, name = mkstemp(prefix="trade_state.", suffix=".tmp",
                               dir=str(self.state_path.parent))
            try:
                with open(fd, "w", encoding="utf-8", newline="\n", closefd=True) as fh:
                    fh.write(data)
                    fh.flush()
                Path(name).replace(self.state_path)
            finally:
                try:
                    Path(name).unlink()
                except FileNotFoundError:
                    pass

    # -------------------------------------------------

    def open_trade(

        self,

        setup,

        timestamp,

        quantity=1.0,

        commission=0.0,

        slippage=0.0,

    ):

        if self.current_trade is not None:

            return None

        # Refine the order (rounding, notional cap, dust drop)
        # BEFORE it becomes a position so every mode books the
        # same corrected quantity. manage() never mutates the
        # caller's order.
        pre_quantity = float(getattr(setup, "quantity", quantity))

        setup = self.position_manager.manage(setup)

        quantity = float(getattr(setup, "quantity", quantity))

        entry = float(setup.entry)

        stop_loss = float(setup.stop_loss)

        take_profit = float(getattr(setup, "take_profit", 0.0) or 0.0)
        exit_mode = str(getattr(setup, "exit_mode", "FIXED_TARGET") or "FIXED_TARGET").upper()
        trailing_activation_r = float(getattr(setup, "trailing_activation_r", 0.0) or 0.0)
        trailing_distance_r = float(getattr(setup, "trailing_distance_r", 0.0) or 0.0)
        trailing_enabled = bool(getattr(setup, "trailing_enabled", exit_mode == "TRAILING_STOP"))
        trailing_method = str(getattr(setup, "trailing_method", METHOD_R_DISTANCE)
                              or METHOD_R_DISTANCE).strip().upper()
        try:
            trailing_step_r = float(getattr(setup, "trailing_step_r", 0.0) or 0.0)
            order_tick = float(getattr(setup, "tick_size", 0.0) or 0.0)
        except (TypeError, ValueError):
            return None
        trade_tick = order_tick if order_tick > 0.0 else self.tick_size

        if trailing_method not in SUPPORTED_TRAILING_METHODS:
            return None
        if not (math.isfinite(trailing_step_r) and trailing_step_r >= 0.0):
            return None
        if not (math.isfinite(trade_tick) and trade_tick >= 0.0):
            return None

        # Fail closed (11E-Prep C1-C): the executable
        # quantity must be finite AND > 0. `quantity <= 0`
        # alone is not sufficient because NaN <= 0 is False
        # and a NaN quantity would otherwise become a Trade.
        # Entry/stop/take-profit must be finite too: they
        # price the fill and size the risk booked on the
        # trade.
        if exit_mode not in ("FIXED_TARGET", "TRAILING_STOP"):
            return None
        if exit_mode == "TRAILING_STOP":
            if not trailing_enabled:
                return None
            initial_risk = abs(entry - stop_loss)
            if initial_risk <= 0 or trailing_activation_r <= 0 or trailing_distance_r <= 0:
                return None
        if not (
            math.isfinite(quantity)
            and math.isfinite(entry)
            and math.isfinite(stop_loss)
            and math.isfinite(take_profit)
            and math.isfinite(trailing_activation_r)
            and math.isfinite(trailing_distance_r)
            and quantity > 0
        ):

            return None

        # Phase 13 mandatory post-cost R:R validation (single
        # authority: core.risk.costs.post_cost_rr). This is the ONE
        # fill choke point every executable mode (Backtest, Paper,
        # Live Broker dry-run, plus the legacy signal fallback)
        # passes through, so no mode and no fallback can bypass
        # cost-aware validation. Layering contract (explicit):
        #
        #   * Non-finite commission/slippage ALWAYS fails closed —
        #     corrupt economics can never become a position.
        #   * Zero costs (commission == 0 and slippage == 0) leave
        #     behavior byte-identical to the pre-gate path: there is
        #     no erosion to validate, and gross R:R remains the duty
        #     of the upstream Decision / Risk / mode fill gates
        #     (all wired). The gate is the COST-aware layer, not a
        #     second gross gate.
        #   * Nonzero costs shift the entry adversely (LONG up /
        #     SHORT down, symmetric) and the fill is REFUSED when
        #     post-cost R:R falls below the active minimum-R policy
        #     — BEFORE any mutation (no Trade is constructed, the
        #     caller's order is untouched) and WITHOUT altering
        #     booking: the same commission/slippage are still
        #     subtracted exactly once at close via
        #     accounting.net_pnl.
        commission_f = float(commission)
        slippage_f = float(slippage)
        if not (math.isfinite(commission_f)
                and math.isfinite(slippage_f)):

            log.error(
                "OPEN_TRADE_BLOCKED_NON_FINITE_COSTS setup_id=%s",
                getattr(setup, "setup_id", "") or "",
            )

            return None

        if commission_f != 0.0 or slippage_f != 0.0:

            try:
                direction = str(setup.direction).upper()
            except Exception:  # noqa: BLE001 (fail closed)
                direction = ""

            if exit_mode == "TRAILING_STOP":
                verdict = post_cost_trailing(
                    direction=direction, entry=entry, stop=stop_loss,
                    quantity=quantity, commission=commission_f,
                    slippage=slippage_f, target=take_profit,
                    symbol=getattr(setup, "symbol", None),
                )
            else:
                verdict = post_cost_rr(
                    direction=direction, entry=entry, stop=stop_loss,
                    target=take_profit, quantity=quantity,
                    commission=commission_f, slippage=slippage_f,
                    exit_mode=exit_mode,
                    symbol=getattr(setup, "symbol", None),
                )

            if not verdict.allowed:

                log.error(
                    "OPEN_TRADE_BLOCKED_POST_COST_RR setup_id=%s "
                    "direction=%s rr=%.4f reason=%s",
                    getattr(setup, "setup_id", "") or "",
                    direction,
                    verdict.rr,
                    verdict.reason,
                )

                return None

        # Actual risk from the FINAL executable quantity
        # (11E-Prep H1-C): only when the manager changed the
        # quantity (allocation cap, dust, rounding) is the
        # order's risk_amount stale — then the trade books
        # final_quantity x stop_distance. Otherwise the
        # order's own risk_amount is preserved verbatim
        # (scripted/authored flows carry it independently).
        if quantity != pre_quantity:
            final_risk_amount = quantity * abs(entry - stop_loss)
        else:
            final_risk_amount = float(
                getattr(setup, "risk_amount", 0.0)
            )

        trade = Trade(

            direction=setup.direction,

            entry=setup.entry,

            stop_loss=setup.stop_loss,

            take_profit=setup.take_profit,

            exit_mode=exit_mode,
            trailing_activation_r=trailing_activation_r,
            trailing_distance_r=trailing_distance_r,
            trailing_enabled=trailing_enabled,
            trailing_method=trailing_method,
            trailing_step_r=trailing_step_r,
            tick_size=trade_tick,
            initial_stop_loss=stop_loss,
            trailing_peak_price=entry,

            quantity=quantity,

            risk_amount=final_risk_amount,

            commission=commission,

            slippage=slippage,

            entry_time=timestamp,

            setup_score=getattr(setup, "score", 0.0),

            confidence=getattr(setup, "confidence", 0.0),

            symbol=getattr(setup, "symbol", ""),

            # Phase 4C identity chain: carried from the order at
            # open time; trade_id is completed by the mode adapter
            # via OrderRegistry.mark_filled.
            setup_id=getattr(setup, "setup_id", ""),

            order_id=getattr(setup, "order_id", ""),

            # Phase 4F: the entry model the order was opened under.
            entry_mode=getattr(setup, "entry_mode", ""),

            # Phase 6C: the canonical setup identity carried
            # unchanged from the OrderIntent at open time.
            canonical_id=getattr(setup, "canonical_id", ""),

        )

        try:
            trade.validate_executable()
        except ValueError as err:
            log.error(
                "OPEN_TRADE_VALIDATION_FAILED setup_id=%s reason=%s",
                getattr(setup, "setup_id", "") or "",
                err,
            )
            return None

        self.current_trade = trade
        self._persist_state()

        return trade

    # -------------------------------------------------

    def update(
        self,
        candle,
    ):
        trade = self.current_trade

        if trade is None:
            return

        timestamp = getattr(candle, "timestamp", None)
        if not self._timestamp_is_newer(timestamp, trade.last_update_timestamp):
            trade.stale_update_count += 1
            log.warning(
                "TRADE_UPDATE_SKIPPED_STALE setup_id=%s timestamp=%r last=%r",
                trade.setup_id, timestamp, trade.last_update_timestamp,
            )
            self._persist_state()
            return

        try:
            high = float(candle.high)
            low = float(candle.low)
            close_raw = getattr(candle, "close", None)
            close = float(close_raw) if close_raw is not None else None
        except (TypeError, ValueError, AttributeError):
            trade.stale_update_count += 1
            log.error("TRADE_UPDATE_SKIPPED_INVALID_CANDLE setup_id=%s", trade.setup_id)
            self._persist_state()
            return
        if not (math.isfinite(high) and math.isfinite(low) and high >= low):
            trade.stale_update_count += 1
            log.error("TRADE_UPDATE_SKIPPED_INVALID_RANGE setup_id=%s high=%r low=%r",
                      trade.setup_id, high, low)
            self._persist_state()
            return
        if close is not None and not math.isfinite(close):
            trade.stale_update_count += 1
            log.error("TRADE_UPDATE_SKIPPED_NON_FINITE_CLOSE setup_id=%s", trade.setup_id)
            self._persist_state()
            return

        trade.bars_held += 1
        trade.last_update_timestamp = timestamp
        self._update_sequence += 1
        is_bull = trade.direction == "BULLISH"

        initial_risk = abs(trade.entry - getattr(trade, "initial_stop_loss", trade.stop_loss))
        if math.isfinite(initial_risk) and initial_risk > 0.0:
            favorable = (high - trade.entry) if is_bull else (trade.entry - low)
            adverse = (trade.entry - low) if is_bull else (high - trade.entry)
            trade.mfe_r = max(float(trade.mfe_r or 0.0), favorable / initial_risk)
            trade.mae_r = max(float(trade.mae_r or 0.0), adverse / initial_risk)

        active_stop = trade.stop_loss
        hit_sl = (low <= active_stop) if is_bull else (high >= active_stop)
        hit_tp = bool(trade.take_profit) and (
            (high >= trade.take_profit) if is_bull else (low <= trade.take_profit)
        )
        ambiguous = bool(hit_sl and hit_tp)

        if hit_sl:
            fill_price = self._stop_fill_price(candle, active_stop, is_bull)
            trailing_hit = bool(
                trade.exit_mode == "TRAILING_STOP"
                and (trade.trailing_activated
                     or active_stop != getattr(trade, "initial_stop_loss", active_stop))
            )
            reason = "TRAILING_STOP" if trailing_hit else "INITIAL_STOP"
            if ambiguous:
                reason += "_AMBIGUOUS_SL_TP"
            self._close_trade(
                timestamp, fill_price, result=None,
                ambiguous=ambiguous, reason=reason,
            )
            return

        if hit_tp:
            self._close_trade(timestamp, trade.take_profit, result=None,
                              reason="TAKE_PROFIT")
            return

        if (trade.exit_mode == "TRAILING_STOP" and trade.trailing_enabled
                and close is not None):
            self._apply_trailing(trade, close, timestamp)

        self._persist_state()

    # -------------------------------------------------

    def _apply_trailing(self, trade, close, timestamp):
        config = TrailingStopConfig(
            activation_r=float(trade.trailing_activation_r),
            distance_r=float(trade.trailing_distance_r),
            method=str(trade.trailing_method or METHOD_R_DISTANCE),
            step_r=float(trade.trailing_step_r or 0.0),
            tick_size=float(trade.tick_size or 0.0),
        )
        decision = evaluate_trailing_stop(
            direction=trade.direction,
            entry=trade.entry,
            initial_stop=getattr(trade, "initial_stop_loss", trade.stop_loss),
            current_stop=trade.stop_loss,
            close=float(close),
            activated=trade.trailing_activated,
            peak_price=trade.trailing_peak_price,
            config=config,
        )
        was_activated = trade.trailing_activated
        trade.trailing_peak_price = decision.peak_price
        trade.trailing_activated = decision.activated
        if decision.accepted:
            trade.stop_loss = decision.new_stop
            trade.trailing_updates = int(trade.trailing_updates or 0) + 1
            entry = {
                "update_index": int(self._update_sequence),
                "timestamp": timestamp,
                "old_stop": decision.old_stop,
                "candidate_stop": decision.candidate_stop,
                "new_stop": decision.new_stop,
                "close": float(close),
                "favorable_r": decision.favorable_r,
                "peak_price": decision.peak_price,
                "tick_size": decision.tick_size,
                "reason": decision.reason,
            }
            history = list(trade.trailing_history or [])
            history.append(entry)
            if len(history) > 500:
                history = history[-500:]
            trade.trailing_history = history
            log.info(
                "TRAILING_STOP_UPDATED setup_id=%s old=%.8f new=%.8f "
                "close=%.8f r=%.4f",
                trade.setup_id, decision.old_stop, decision.new_stop,
                float(close), decision.favorable_r,
            )
        elif decision.reason in ("INVALID_CONFIG", "INVALID_DIRECTION",
                                 "NON_FINITE_INPUT", "ZERO_INITIAL_RISK",
                                 "STOP_AT_OR_THROUGH_PRICE"):
            log.error(
                "TRAILING_STOP_REJECTED setup_id=%s reason=%s candidate=%.8f",
                trade.setup_id, decision.reason, decision.candidate_stop,
            )
        elif trade.trailing_activated != was_activated:
            log.info("TRAILING_STOP_ACTIVATED setup_id=%s r=%.4f",
                     trade.setup_id, decision.favorable_r)

    # -------------------------------------------------

    @staticmethod
    def _timestamp_is_newer(new, old):
        if old is None or old == "" or old == 0:
            return True
        if isinstance(new, (int, float)) and not isinstance(new, bool) and \
                isinstance(old, (int, float)) and not isinstance(old, bool):
            return float(new) > float(old)
        return str(new) != str(old)

    def _stop_fill_price(self, candle, stop, is_bull):
        if self.gap_fill_mode != "CONSERVATIVE":
            return stop
        try:
            open_price = float(getattr(candle, "open", None))
        except (TypeError, ValueError):
            return stop
        if not math.isfinite(open_price):
            return stop
        if is_bull and open_price <= stop:
            return open_price
        if (not is_bull) and open_price >= stop:
            return open_price
        return stop

    # -------------------------------------------------

    def request_exit(self, timestamp, exit_price, reason="SIGNAL_EXIT"):
        """Close an open trade at the supplied observed price.

        This is the deterministic runtime escape hatch for an explicit
        QuantEngine exit/book-profit signal. It never fabricates a price:
        callers must provide the observed market price.
        """
        trade = self.current_trade
        if trade is None:
            return False
        pnl = gross_pnl(trade.direction, trade.entry, float(exit_price), trade.quantity)
        result = "WIN" if pnl > 0 else "LOSS" if pnl < 0 else "BREAKEVEN"
        self._close_trade(timestamp, float(exit_price), result, reason=str(reason))
        return True

    def _close_trade(

        self,

        timestamp,

        exit_price,

        result,

        ambiguous: bool = False,
        reason: str = "",

    ):

        trade = self.current_trade

        trade.exit_time = timestamp

        trade.exit_price = exit_price

        trade.result = str(result or "")
        trade.exit_reason = str(reason or "")

        trade.status = "CLOSED"

        trade.ambiguous = bool(ambiguous)

        gross = gross_pnl(trade.direction, trade.entry, exit_price, trade.quantity)

        # Net of round-trip commission + slippage. Both
        # default to 0.0 on the fixed-quantity legacy path,
        # where net == gross. Canonical accounting.
        funding_cost = 0.0
        funding_events = 0
        if self.funding_schedule is not None:
            funding_cost, funding_events = self.funding_schedule.cost(
                entry_time=int(trade.entry_time), exit_time=int(trade.exit_time),
                direction=trade.direction, entry=trade.entry, quantity=trade.quantity)
        trade.funding = funding_cost
        trade.funding_events = funding_events
        trade.pnl = net_pnl(gross, trade.commission, trade.slippage, funding_cost)

        # The exit reason is separate from the P&L classification.  A trailing
        # stop above entry is a WIN even though the exit mechanism was a stop.
        if not trade.result:
            trade.result = classify_pnl(trade.pnl)

        trade.pnl_percent = position_return_percent(trade.pnl, trade.entry, trade.quantity)

        self.registry.add(trade)

        self.current_trade = None
        self._persist_state()

        # Phase 4C: identity-based TRADE_CLOSED at the single
        # close choke point shared by Backtest / Paper / Live.
        if trade.trade_id or trade.order_id:

            log.info(
                "TRADE_CLOSED setup_id=%s order_id=%s "
                "trade_id=%s result=%s pnl=%.2f ts=%s",
                trade.setup_id,
                trade.order_id,
                trade.trade_id,
                trade.result,
                trade.pnl,
                timestamp,
            )

    # -------------------------------------------------

    def reset(self):

        self.registry.clear()

        self.current_trade = None
        self._update_sequence = 0
        self._persist_state()