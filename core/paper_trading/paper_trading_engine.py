"""
====================================================

QuantEngine

Live / Replay Paper Trading Engine

Feed-driven paper trading that reuses the canonical
institutional pipeline end-to-end with NO exchange
credentials required.

It mirrors the Backtester's execution flow 1:1:

    Finished Candle (live websocket feed or replay)
              │
              ▼
   PaperTradingEngine.run_candle
              │
              ├── pipeline.on_candle (driven EXPLICITLY,
              │       NOT via EventBus dispatch) so the
              │       institutional flow + RiskEngine ALWAYS
              │       run before the fill. Subscription order
              │       on the bus can never starve the engine.
              │      RiskEngine sizes from the paper account's
              │       live equity (context.account).
              ▼
           paper fill (OrderIntent -> TradeSimulator.open_trade)
              │
              ▼
        TradeSimulator.update   <- SL / TP management
              │
              ▼
           Account booking

This is the canonical "Signal -> Risk -> Order Intent ->
Execution" path that Replay, Paper and Live all share.

====================================================
"""

from config import risk_settings

from core.backtesting.trade_simulator import TradeSimulator
from core.common.logging_config import get_logger
from core.events.candle_event import CandleEvent
from core.events.event_types import EventType
from core.execution.order_registry import PENDING, FILLED
from core.backtesting.accounting import (
    directional_geometry_ok,
    order_rr,
    risk_reward_allowed,
)
from core.risk.account import Account
from core.risk.account_state import AccountState
from core.risk.risk_engine import kill_switch_active
from core.risk.costs import paper_cost_profile

import json
import math

from dataclasses import asdict, fields as dataclass_fields
from pathlib import Path
from tempfile import mkstemp
from threading import RLock

log = get_logger(__name__)

_PAPER_STATE_SCHEMA = "quantengine.paper_state.v1"


class _SlippageAdjustedOrder:
    """
    Attribute-adapter that exposes the same protocol
    TradeSimulator.open_trade reads (direction, entry,
    stop_loss, take_profit, risk_amount, score, confidence)
    with an entry price modified by paper fill slippage.
    Works for any producer -- OrderIntent dataclass or a
    plain setup object -- without mutating the original.
    """

    __slots__ = ("_order", "entry")

    def __init__(self, order, entry):
        self._order = order
        self.entry = entry

    def __getattr__(self, name):
        return getattr(self._order, name)


class PaperTradingEngine:
    """
    Feed-driven paper trading engine.

    Parameters
    ----------
    pipeline:
        An InstitutionalPipeline (or pipeline-compatible
        object exposing `.context`, `.on_candle(event)` and
        `.reset()`). The engine drives it explicitly, in the
        same per-candle order as the canonical Backtester.
    event_bus:
        The submitted-to EventBus. Required only when using
        subscribe(); keep it for symmetry with the Backtester.
    simulator:
        A TradeSimulator. Created if not given. Position
        management (SL/TP) always runs inside it, so paper
        and backtest exits are byte-for-byte the same math.
    account:
        An Account. Created from risk_settings.STARTING_BALANCE
        if not given. RiskEngine sizes next orders from its
        live equity via context.account.
    fill_slippage_bps:
        Optional paper-only fill realism. Default 0.0 = fill
        exactly at the intent entry (identical to backtest).
        When > 0 a buy fills WORSE (entry + bps) and a sell
        fills WORSE (entry - bps); stops/targets stay put.
    mark_to_market:
        Default False = account equity only moves on booked
        closes (identical to backtest). True floats the open
        trade's net unrealized P&L into equity every candle.
    """

    def __init__(
        self,
        pipeline,
        event_bus,
        simulator=None,
        account=None,
        fill_slippage_bps=0.0,
        mark_to_market=False,
        state_path=None,
    ):

        self.pipeline = pipeline

        self.event_bus = event_bus

        if simulator is not None:
            if state_path is not None and getattr(simulator, "state_path", None) is not None:
                raise ValueError(
                    "PaperTradingEngine state_path and simulator.state_path "
                    "cannot both be configured"
                )
            self.simulator = simulator
        else:
            self.simulator = TradeSimulator(
                tick_size=risk_settings.ECONOMIC_TICK_SIZE,
            )

        self._starting_balance = (
            account.state.starting_balance
            if account is not None
            else risk_settings.STARTING_BALANCE
        )

        self.account = (
            account
            if account is not None
            else Account(
                starting_balance=self._starting_balance
            )
        )

        self.fill_slippage_bps = float(fill_slippage_bps or 0.0)

        self.mark_to_market = bool(mark_to_market)

        self.total_bars = 0

        self.state_path = Path(state_path) if state_path is not None else None
        self._state_lock = RLock()
        if self.state_path is not None:
            self._load_state()

    # ==================================================
    # Durable paper state (open trade + account + bars)
    # ==================================================

    def _load_state(self):
        if self.state_path is None or not self.state_path.exists():
            return
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
            if payload.get("schema") != _PAPER_STATE_SCHEMA:
                raise ValueError("unsupported paper state schema")
            self.total_bars = int(payload.get("total_bars", 0) or 0)
            raw_account = payload.get("account")
            if not isinstance(raw_account, dict):
                raise ValueError("paper state account is missing")
            allowed = {f.name for f in dataclass_fields(AccountState)}
            unknown = set(raw_account) - allowed
            if unknown:
                raise ValueError("unknown account state fields: %s"
                                 % ", ".join(sorted(unknown)))
            state = AccountState(**raw_account)
            for field in ("starting_balance", "balance", "equity", "free_margin",
                          "realized_pnl", "daily_pnl", "weekly_pnl", "monthly_pnl",
                          "peak_equity", "drawdown", "drawdown_percent", "max_drawdown"):
                value = float(getattr(state, field))
                if not math.isfinite(value):
                    raise ValueError("non-finite account state field %s" % field)
            if state.starting_balance <= 0 or state.balance < 0:
                raise ValueError("invalid account balances in paper state")
            self.account.state = state
            self._starting_balance = state.starting_balance
            raw_trade = payload.get("trade")
            if raw_trade is not None:
                self.simulator.restore_trade_state(raw_trade)
            elif self.simulator.current_trade is not None:
                self.simulator.current_trade = None
        except Exception as exc:  # noqa: BLE001 (fail closed)
            raise ValueError("invalid paper state: %s" % exc) from exc

    def _persist_state(self):
        if self.state_path is None:
            return
        with self._state_lock:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "schema": _PAPER_STATE_SCHEMA,
                "total_bars": int(self.total_bars),
                "account": asdict(self.account.state),
                "trade": self.simulator.export_trade_state(),
            }
            data = json.dumps(payload, sort_keys=True, indent=2) + "\n"
            fd, name = mkstemp(prefix="paper_state.", suffix=".tmp",
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

    # ==================================================
    # Lifecycle
    # ==================================================

    def reset(self):

        self.total_bars = 0

        self.pipeline.reset()

        self.simulator.reset()

        # Phase 11B: reset IN PLACE (identity preserved --
        # see Backtester.reset).
        self.account.reset(self._starting_balance)

        self._persist_state()

    # ==================================================
    # Wiring
    # ==================================================

    def subscribe(self, event_bus=None):

        bus = event_bus if event_bus is not None else self.event_bus

        if bus is None:
            return

        bus.subscribe(EventType.CANDLE, self.on_candle)

    # ==================================================
    # Feed
    # ==================================================

    def on_candle(self, event):

        self.run_candle(event.candle)

    # --------------------------------------------------

    def run_candle(self, candle):

        context = self.pipeline.context

        # ---------------------------------------------
        # New pipeline cycle (mirrors Backtester.run)
        # ---------------------------------------------

        context.reset_cycle()

        # ---------------------------------------------
        # Update market state
        # ---------------------------------------------

        context.market.timestamp = candle.timestamp

        context.market.symbol = getattr(
            candle,
            "symbol",
            context.market.symbol,
        )

        context.market.timeframe = getattr(
            candle,
            "timeframe",
            context.market.timeframe,
        )

        context.market.mark_price = candle.close

        context.market.best_bid = candle.close

        context.market.best_ask = candle.close

        context.market.spread = 0.0

        # ---------------------------------------------
        # Publish the account's live state into the
        # pipeline context so RiskEngine sizes from the
        # current paper equity, never a default
        # AccountState.
        # ---------------------------------------------

        context.account = self.account.state

        # ---------------------------------------------
        # Drive the institutional pipeline EXPLICITLY.
        #
        # This is the ordering guarantee: the pipeline
        # (and the RiskEngine OrderIntent) completes for
        # this candle BEFORE the engine reads context.order
        # in _execute_signal. Unlike event_bus.publish(),
        # it does not depend on callback subscription order.
        # ---------------------------------------------

        self.pipeline.on_candle(
            CandleEvent(
                candle=candle,
                symbol=context.market.symbol,
                timeframe=context.market.timeframe,
            )
        )

        # ---------------------------------------------
        # Execute simulated paper fills
        # ---------------------------------------------

        self._execute_signal(candle)

        before = self.simulator.registry.count()

        self.simulator.update(candle)

        self._book_closed_trades(before)

        self._mark_to_market(candle)

        self.total_bars += 1

        self._persist_state()

    # ==================================================
    # Signal -> Fill
    # ==================================================

    def _execute_signal(self, candle):

        if self.simulator.current_trade is not None:
            return

        context = self.pipeline.context

        # The risk-validated order takes precedence over the
        # raw setup. When no RiskEngine produced an order this
        # cycle, fall back to the execution signal so pre-risk
        # pipelines still work unchanged (same as Backtester).
        order = getattr(
            context,
            "order",
            None,
        )

        if order is None:

            order = getattr(
                context,
                "execution_signal",
                None,
            )

        if order is None:
            return

        # Phase 12 kill-switch coverage (existing exposure):
        # an active kill switch blocks paper fills as well as
        # creation -- a parked paper intent must not open
        # simulated exposure while the switch is active. The
        # SL/TP management below still runs (open state stays
        # observable and reconcilable).
        if kill_switch_active(context.account):
            log.error(
                "PAPER_FILL_BLOCKED_KILL_SWITCH setup_id=%s",
                getattr(order, "setup_id", "") or "",
            )
            return

        # Phase 13 legacy-path parity (execution-signal
        # fallback is pre-risk, like the backtester legacy
        # branch): the mandatory geometry + RR gates run here
        # too, so a hand-fed signal can never open paper
        # exposure that production gates would refuse.
        if not directional_geometry_ok(
            getattr(order, "direction", ""),
            getattr(order, "entry", 0.0),
            getattr(order, "stop_loss", 0.0),
            getattr(order, "take_profit", 0.0),
            exit_mode=getattr(order, "exit_mode", risk_settings.EXIT_MODE_FIXED_TARGET),
        ):
            log.error(
                "PAPER_FILL_BLOCKED_GEOMETRY setup_id=%s",
                getattr(order, "setup_id", "") or "",
            )
            return

        symbol = str(getattr(order, "symbol", "") or getattr(context.market, "symbol", "") or "")
        from core.risk.trading_policy import trading_policy
        policy = trading_policy(symbol)
        exit_mode = getattr(order, "exit_mode", risk_settings.EXIT_MODE_FIXED_TARGET)
        if policy.trailing_enabled and exit_mode == risk_settings.EXIT_MODE_FIXED_TARGET:
            from copy import copy
            order = copy(order)
            exit_mode = risk_settings.EXIT_MODE_TRAILING_STOP
            order.exit_mode = exit_mode
            order.trailing_enabled = True
            order.trailing_activation_r = policy.trailing_activation_r
            order.trailing_distance_r = policy.trailing_distance_r
            order.trailing_method = getattr(policy, "trailing_method", "R_DISTANCE")
            order.trailing_step_r = getattr(policy, "trailing_step_r", 0.0)
        paper_rr = order_rr(
            getattr(order, "entry", 0.0),
            getattr(order, "stop_loss", 0.0),
            getattr(order, "take_profit", 0.0),
        )

        # Single authority: qualify the planned target as FIXED even after
        # trailing promotion (mirrors RiskEngine). Threads per-symbol policy.
        if paper_rr is None or not risk_reward_allowed(
            paper_rr, exit_mode="FIXED_TARGET", symbol=symbol
        ):
            log.error(
                "PAPER_FILL_BLOCKED_RR setup_id=%s rr=%s",
                getattr(order, "setup_id", "") or "",
                paper_rr,
            )
            return

        # Paper fills consume the canonical paper-cost authority rather
        # than the production-cost fields minted on OrderIntent.  This
        # closes the paper-runtime split brain: PAPER_* configuration is
        # now the actual fill economics, while the production defaults
        # remain untouched.  An explicit fill_slippage_bps argument is
        # an additional fill-price model and is kept separate from the
        # round-trip accounting slippage below.
        quantity = float(getattr(order, "quantity", 1.0) or 0.0)
        position_value = abs(float(getattr(order, "entry", 0.0) or 0.0) * quantity)
        paper_costs = paper_cost_profile()
        commission, slippage = paper_costs.compute(position_value)

        if self.fill_slippage_bps > 0:
            order = _SlippageAdjustedOrder(
                order,
                self._model_fill_price(order),
            )

        trade = self.simulator.open_trade(
            order,
            candle.timestamp,
            quantity=quantity,
            commission=commission,
            slippage=slippage,
        )

        if trade is None:
            return

        self._mark_order_filled(order, trade, candle.timestamp)

    # --------------------------------------------------

    def _mark_order_filled(self, order, trade, timestamp):

        # Phase 4C: consume the registry entry exactly once and
        # complete the setup -> order -> trade identity chain.
        order_registry = getattr(
            self.pipeline.context, "order_registry", None
        )

        order_id = getattr(order, "order_id", "") or ""

        if order_registry is None or not order_id:
            return

        registered = order_registry.get(order_id)

        trade_id = order_registry.mark_filled(registered, trade)
        if trade_id is None:
            return

        order.trade_id = trade_id
        if hasattr(order, "status"):
            order.status = registered.status

        setup = getattr(order, "setup", None)

        if setup is not None and getattr(
            setup, "lifecycle", ""
        ) in ("ORDER_CREATED", "ACCEPTED", "NEW", ""):

            setup.lifecycle = FILLED

        log.info(
            "ORDER_FILLED setup_id=%s order_id=%s "
            "trade_id=%s ts=%s",
            getattr(order, "setup_id", "") or "",
            order_id,
            trade_id or "",
            timestamp,
        )

    # --------------------------------------------------

    def _model_fill_price(self, order):

        offset = order.entry * (self.fill_slippage_bps / 10000.0)

        if order.direction.upper() == "BEARISH":

            return order.entry - offset

        return order.entry + offset

    # ==================================================
    # Account Booking
    # ==================================================

    def _book_closed_trades(self, before):

        closed_now = self.simulator.registry.all()[before:]

        if not closed_now:
            return

        # Single-position model: the simulator closes at most
        # one trade per update() pass. Enforce it loudly --
        # identical guard to the canonical Backtester.
        if len(closed_now) != 1:

            raise RuntimeError(
                "PaperTradingEngine: expected exactly one trade "
                f"closed per candle, got {len(closed_now)}."
            )

        closed = closed_now[0]

        from core.backtesting.accounting import classify_pnl

        kind = classify_pnl(closed.pnl)
        if kind == "WIN":
            self.account.book_profit(closed.pnl)
        elif kind == "LOSS":
            self.account.book_loss(-closed.pnl)
        else:
            self.account.book_breakeven()

    # ==================================================
    # Paper-only realism (opt-in)
    # ==================================================

    def _mark_to_market(self, candle):

        if not self.mark_to_market:
            return

        trade = self.simulator.current_trade

        if trade is None:

            self.account.update_unrealized(0.0)

            return

        if trade.direction == "BULLISH":

            floating = (
                candle.close - trade.entry
            ) * trade.quantity

        else:

            floating = (
                trade.entry - candle.close
            ) * trade.quantity

        # Net of the round-trip commission + slippage the
        # intent already models.
        floating -= (
            trade.commission + trade.slippage
        )

        self.account.update_unrealized(floating)

    # ==================================================
    # Results
    # ==================================================

    @property
    def trades(self):

        return self.simulator.registry

    # --------------------------------------------------

    @property
    def completed_trades(self):

        return self.simulator.registry.all()

    # --------------------------------------------------

    @property
    def current_trade(self):

        return self.simulator.current_trade

    # --------------------------------------------------

    @property
    def processed_bars(self):

        return self.total_bars