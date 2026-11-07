"""
====================================================

QuantEngine

Live Broker Engine

Routes the RiskEngine OrderIntent produced by the
institutional pipeline to the REAL Delta exchange through a
DeltaOrderExecutor, tracks the open position, and books
closed P&L into the shared TradeRegistry + Account.

Shares the canonical execution flow with the Backtester and
PaperTradingEngine:

    Finished Candle
            │
            ▼
   BrokerEngine.run_candle
            │
            ├── pipeline.on_candle (driven EXPLICITLY so the
            │       institutional flow + RiskEngine always
            │       run before the route; RiskEngine sizes
            │       from the synced live equity in context)
            ▼
        route: intent -> executor.execute
            │         (dry-run: record the would-be intent)
            ▼
        manage: dry == TradeSimulator (exit by candle SL/TP)
            │        live == exchange position sync
            ▼
        book closed P&L -> TradeRegistry + Account
            │
            ▼
        live only: account equity sync from executor.balance

dry_run=True (DEFAULT) guarantees ZERO exchange writes: the
would-be intent is recorded on `placed` and the position is
managed through the same TradeSimulator the Backtester uses,
so the whole flow runs offline. Live placement requires an
explicit opt-in AND the DeltaExchange._require_auth guard
(no private endpoint fires without DELTA_API_KEY/SECRET).

The executor protocol consumed here is exactly the
DeltaOrderExecutor surface: execute(intent), fetch(order_id),
cancel(order_id), balance(), positions() -- responses are read
tolerantly via candidate field names so Delta's JSON schema
can drift without breaking the engine.

====================================================
"""

from config import risk_settings

from core.backtesting.accounting import (
    classify_pnl,
    directional_geometry_ok,
    gross_pnl,
    net_pnl,
    order_rr,
    position_return_percent,
    risk_reward_allowed,
)
from core.backtesting.trade import Trade
from core.backtesting.trade_registry import TradeRegistry
from core.backtesting.trade_simulator import TradeSimulator
from core.live.reconciler import Reconciler
from core.events.candle_event import CandleEvent
from core.events.event_types import EventType
from core.execution.live_safety_gate import LiveSafetyGate
from core.execution.order_ack import (
    ACKNOWLEDGED,
    CANCELLED,
    EXPIRED,
    FILLED,
    PARTIAL,
    REJECTED,
    UNKNOWN,
    classify_ack,
    classify_exception,
)
from core.execution.order_executor import order_seq_value
from core.execution.order_registry import PENDING, FILLED
from core.risk.account import Account
from core.risk.costs import (
    paper_cost_profile,
    paper_profile_name,
    post_cost_rr,
    post_cost_trailing,
)
from core.risk.risk_engine import kill_switch_active

from core.common.logging_config import get_logger

log = get_logger(__name__)


def _field(data, *candidates, default=None):
    """
    Tolerant field extraction. Reads the first present,
    non-None candidate key off a dict (or unwraps a Delta
    {"result": ...} envelope); returns `default` otherwise.

    Phase 11C schema-drift observability: every fallback
    (first candidate missing, later candidate used) and
    every total miss is counted in the module-level
    _SCHEMA_DRIFT ledger so silent exchange/API schema
    changes become measurable instead of invisible. Use
    drain_schema_drift_stats() in tests/ops to read and
    reset the counters. Behavior is unchanged -- this
    reader stays tolerant; it is now OBSERVED.
    """

    if isinstance(data, dict):
        result = data
    elif isinstance(data, list):
        result = None
    else:
        result = None

    if isinstance(data, dict) and "result" in data:
        result = data["result"]

    if isinstance(result, dict):
        for index, key in enumerate(candidates):
            if key in result and result[key] is not None:
                if index > 0:
                    _note_drift("fallback", candidates[0], key)
                return result[key]
    elif isinstance(result, list):
        for item in result:
            if isinstance(item, dict):
                for index, key in enumerate(candidates):
                    if key in item and item[key] is not None:
                        if index > 0:
                            _note_drift("fallback", candidates[0], key)
                        return item[key]

    _note_drift("miss", candidates[0] if candidates else "", "")

    return default


def _fields_list(data):
    """Unwrap a Delta envelope into a list of records."""

    result = data if isinstance(data, list) else data

    if isinstance(data, dict) and "result" in data:
        result = data["result"]

    if isinstance(result, list):
        return result

    _note_drift("miss", "<list>", "")

    return []


# --------------------------------------------------
# Phase 11C schema-drift ledger (module-level counters).
# --------------------------------------------------

_SCHEMA_DRIFT = {
    "fallback": 0,
    "miss": 0,
    "details": [],
}

_SCHEMA_DRIFT_MAX_DETAILS = 64


def _note_drift(kind, wanted, used):
    """Record one tolerant-read event (fallback or miss)."""

    _SCHEMA_DRIFT[kind] = _SCHEMA_DRIFT.get(kind, 0) + 1

    details = _SCHEMA_DRIFT["details"]

    if len(details) < _SCHEMA_DRIFT_MAX_DETAILS:
        details.append(
            {"kind": kind, "wanted": wanted, "used": used}
        )


def get_schema_drift_stats():
    """Snapshot of tolerant-reader drift counters."""

    return {
        "fallback": _SCHEMA_DRIFT.get("fallback", 0),
        "miss": _SCHEMA_DRIFT.get("miss", 0),
        "details": list(_SCHEMA_DRIFT.get("details", [])),
    }


def drain_schema_drift_stats():
    """Read and reset the drift counters (tests/ops)."""

    snapshot = get_schema_drift_stats()

    _SCHEMA_DRIFT["fallback"] = 0
    _SCHEMA_DRIFT["miss"] = 0
    _SCHEMA_DRIFT["details"] = []

    return snapshot


def schema_health():
    """Degraded-health indicator for tolerant parsing.

    HEALTHY  -- no fallback/miss recorded since last drain.
    DEGRADED -- fallbacks or misses observed: the exchange
                schema may be drifting; investigate details.
    """

    if _SCHEMA_DRIFT.get("fallback", 0) or _SCHEMA_DRIFT.get("miss", 0):
        return "DEGRADED"

    return "HEALTHY"


class BrokerEngine:
    """
    Live trading consumer.

    Parameters
    ----------
    pipeline:
        An InstitutionalPipeline (or a pipeline-compatible
        object exposing `.context`, `.on_candle(event)` and
        `.reset()`). Driven explicitly, pipeline-first.
    event_bus:
        EventBus for subscribe(); kept for symmetry with the
        Backtester / PaperTradingEngine.
    executor:
        The live order routing adapter. The canonical wiring
        uses DeltaOrderExecutor(DELTA); tests use a recording
        fake. Must expose execute/fetch/cancel/balance/
        positions.
    simulator:
        TradeSimulator used by DRY-RUN mode for paper-style
        fills and exits. Created if not given.
    account:
        Account mirror of realized P&L. In live mode its
        balance is also re-synced from the exchange ledger
        each cycle (external-authority model). Created from
        risk_settings.STARTING_BALANCE if not given.
    dry_run:
        Default True = ZERO exchange writes. The would-be
        intent is appended to `placed` and the position is
        managed through `simulator` exactly like paper.
        Set False only to arm real placement -- and then
        ONLY with an armed Phase 11A safety decision (see
        `safety`): constructing BrokerEngine(dry_run=False)
        without one raises LiveBlockedError, so a future
        caller cannot obtain live execution by accident.
        (The exchange adapter still refuses without API
        keys via DeltaExchange._require_auth.)
    safety:
        Phase 11A arming token: an allowed SafetyDecision
        from LiveSafetyGate.require (production, via
        main.py) or LiveSafetyGate.test_armed (offline
        unit tests with fake transports). REQUIRED when
        dry_run=False; ignored (may be None) when
        dry_run=True. Production code MUST NOT use
        test_armed().
    """

    def __init__(
        self,
        pipeline,
        event_bus,
        executor,
        simulator=None,
        account=None,
        dry_run=True,
        portfolio_gate=None,
        portfolio_release=None,
        safety=None,
        reconciler=None,
        snapshot_path=None,
    ):

        self.pipeline = pipeline

        self.event_bus = event_bus

        self.executor = executor

        # Optional portfolio-level risk hooks (Phase 8), mirroring the
        # Backtester contract. portfolio_gate(order) -> bool is
        # consulted right before an order would be routed; a False
        # verdict declines the otherwise-valid order WITHOUT mutating
        # it (the portfolio layer never changes strategy semantics).
        # portfolio_release(closed_trade) is invoked after a close so
        # the shared portfolio ledger can release its exposure. Both
        # default to None and are then never called -- behavior is
        # unchanged without a gate.
        self.portfolio_gate = portfolio_gate

        self.portfolio_release = portfolio_release

        self.simulator = (
            simulator
            if simulator is not None
            else TradeSimulator()
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

        self.dry_run = bool(dry_run)

        # Phase 11A: live mode requires the centralized
        # arming token UP FRONT. Accidental
        # BrokerEngine(..., dry_run=False) without it fails
        # closed here -- before any candle is processed.
        self._safety = safety

        if not self.dry_run:
            self._safety = LiveSafetyGate.require_decision(
                safety,
                component="BrokerEngine.__init__",
            )

        # Unified closed-trade ledger for BOTH modes, so the
        # analytics layer consumes the same TradeRegistry
        # whether a close came from paper management or from
        # an exchange bracket fill.
        self.registry = TradeRegistry()

        self.total_bars = 0

        # Audit trail: every routed would-be intent (dry) or
        # executor response (live).
        self.placed = []

        # ---- live runtime state ----
        self._last_intent = None

        self._last_entry_time = 0

        self._open_order_id = None

        self._product_id = None

        self._in_position = False

        self._live_trade = None

        # Phase 12 acknowledgement truth: the local mirror above
        # is a WORKING order until the exchange confirms a fill.
        # _ack_state is the last classified acknowledgement
        # (ACKNOWLEDGED / FILLED / PARTIAL / REJECTED /
        # CANCELLED / EXPIRED / UNKNOWN); _fill_confirmed flips
        # only on fill evidence (explicit filled ack or a visible
        # position). _last_error is the typed record of the most
        # recent execution failure (never a fill).
        self._ack_state = None

        self._fill_confirmed = False

        self._last_error = None

        # Stage 1-3 hardening: local-vs-exchange reconciliation.
        # The broker's own executor is the default position feed for
        # LIVE engines that expose a callable positions() probe
        # (paper engines stay passive: no exchange authority exists
        # to compare against). An explicit reconciler (main.py LIVE
        # branch) always wins. A live engine with no usable feed
        # logs a loud RECONCILE_INERT warning -- silent unverified
        # live trading is exactly what this mechanism exists to
        # prevent.
        if reconciler is not None:
            self.reconciler = reconciler
        else:
            feed = None
            if not self.dry_run and callable(
                    getattr(executor, "positions", None)):
                feed = executor
            self.reconciler = Reconciler(
                executor=feed, snapshot_path=snapshot_path)
        self._reconcile_armed = False
        self._order_placed_bar = None
        if not self.dry_run and self.reconciler.executor is None:
            log.error(
                "RECONCILE_INERT no position feed wired; pass an "
                "explicit reconciler (or snapshot_path) for live "
                "position verification"
            )

    # ==================================================
    # Lifecycle
    # ==================================================

    def reset(self):

        self.total_bars = 0

        self.pipeline.reset()

        self.simulator.reset()

        self.registry.clear()

        # Phase 11B: reset IN PLACE (identity preserved --
        # see Backtester.reset).
        self.account.reset(self._starting_balance)

        self.placed = []

        self._last_intent = None

        self._last_entry_time = 0

        self._open_order_id = None

        self._product_id = None

        self._in_position = False

        self._live_trade = None

        self._ack_state = None

        self._fill_confirmed = False

        self._last_error = None

        # Stage 1-3 hardening: re-arm on explicit reset (fresh
        # evaluation next live candle). The halt flag is NEVER
        # cleared here (explicit resolve() only) and the snapshot
        # journal is NEVER deleted here (crash evidence survives).
        self._reconcile_armed = False
        self._order_placed_bar = None

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

        context.reset_cycle()

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

        # RiskEngine sizes from the broker's current equity:
        # dry-run = the local paper balance, live = the last
        # exchange-synced equity.
        context.account = self.account.state

        # Pipeline FIRST -- the institutional flow plus the
        # RiskEngine OrderIntent complete before _route reads
        # context.order. Explicit drive (no bus dispatch) so
        # subscription order can never starve the engine.
        self.pipeline.on_candle(
            CandleEvent(
                candle=candle,
                symbol=context.market.symbol,
                timeframe=context.market.timeframe,
            )
        )

        # ---------------------------------------------
        # Route a new intent (only when flat)
        # ---------------------------------------------

        # Stage 1-3 hardening: live auto-arm. The first live candle
        # runs the reconciler startup check (fresh boot vs exchange
        # authority + snapshot journal); a mismatch halts routing
        # above before any order can go out. Paper never arms (no
        # exchange authority exists to compare against). The safety
        # gate is enforced FIRST so a refused gate performs ZERO
        # transport calls -- not even the verification read.
        if not self.dry_run and not self._reconcile_armed:
            self._reconcile_armed = True
            LiveSafetyGate.require_decision(
                self._safety,
                component="BrokerEngine._reconcile_arm",
            )
            verdict = self.reconciler.startup_check(dry_run=False)
            log.info(
                "RECONCILE_ARMED verdict=%s reason=%s",
                verdict.get("verdict"), verdict.get("reason", ""),
            )

        self._route(candle)

        # ---------------------------------------------
        # Manage the open position / monitor the fill
        # ---------------------------------------------

        if self.dry_run:
            self._manage_paper(candle)
        else:
            self._sync_live(candle)
            self._reconcile_live(candle)

        self.total_bars += 1

    # ==================================================
    # Routing
    # ==================================================

    def _should_exit_trade(self, signal, trade):
        if signal is None or trade is None:
            return False, ""
        metadata = getattr(signal, "metadata", None) or {}
        action = str(metadata.get("action", metadata.get("signal_action", "")) or "").upper()
        if action in {"EXIT", "CLOSE", "BOOK_PROFIT", "TAKE_PROFIT", "FLATTEN"}:
            return True, action
        if bool(metadata.get("exit", False)) or bool(metadata.get("book_profit", False)):
            return True, "SIGNAL_EXIT"
        direction = str(getattr(signal, "direction", "") or "").upper()
        from core.risk.trading_policy import trading_policy
        policy = trading_policy(getattr(trade, "symbol", ""))
        opposite = {"BULLISH": "BEARISH", "BEARISH": "BULLISH"}
        if policy.auto_exit_on_opposite_signal and direction == opposite.get(str(getattr(trade, "direction", "")).upper()):
            return True, "OPPOSITE_SIGNAL"
        return False, ""

    def _route(self, candle):

        # Stage 1-3 hardening: a reconciled halt blocks ALL new
        # orders (fail closed) until explicit operator resolution.
        # Checked before everything, including the position gate.
        if self.reconciler.halt_new_orders:
            log.error(
                "ROUTE_BLOCKED_RECONCILE reason=%s",
                self.reconciler.halt_reason,
            )
            return

        # Phase 12 kill-switch coverage (existing exposure):
        # an active kill switch blocks ALL routing -- dry and
        # live -- before any mirror is created. Creation stops
        # in RiskEngine; this is the second seam so a parked
        # intent (or a hand-fed context.order) can never route
        # while the switch is active. Open state stays
        # observable; recovery requires explicit operator
        # action (the switch itself is cleared out of band).
        if kill_switch_active(
            getattr(self.account, "state", None)
        ):
            _pipeline = getattr(self, "pipeline", None)
            _pending = (
                getattr(_pipeline, "context", None)
                if _pipeline is not None
                else None
            )
            log.error(
                "ROUTE_BLOCKED_KILL_SWITCH setup_id=%s",
                getattr(
                    getattr(_pending, "order", None),
                    "setup_id",
                    "",
                )
                or "",
            )
            return

        if self.current_trade is not None:
            context = self.pipeline.context
            signal = getattr(context, "execution_signal", None)
            should_exit, reason = self._should_exit_trade(signal, self.current_trade)
            if should_exit:
                if self.dry_run:
                    price = float(getattr(candle, "close", 0.0) or 0.0)
                    if price > 0:
                        self.simulator.request_exit(candle.timestamp, price, reason)
                else:
                    log.info("LIVE_EXIT_SIGNAL_DEFERRED reason=%s", reason)
            return

        context = self.pipeline.context

        order = getattr(context, "order", None)

        if order is None:

            order = getattr(
                context,
                "execution_signal",
                None,
            )

        if order is None:
            return

        # Phase 8 portfolio gate: an otherwise-valid order may be
        # declined because portfolio-level risk is already exhausted.
        # PURE decision -- the gate never mutates the order / setup
        # / strategy. A False verdict simply routes nothing.
        if (
            self.portfolio_gate is not None
            and not self.portfolio_gate(order)
        ):

            log.info(
                "PORTFOLIO_GATE_DECLINED setup_id=%s symbol=%s "
                "direction=%s risk_amount=%.2f",
                getattr(order, "setup_id", "") or "",
                getattr(order, "symbol", "") or "",
                getattr(order, "direction", "") or "",
                getattr(order, "risk_amount", 0.0) or 0.0,
            )

            return

        self._last_intent = order

        self._last_entry_time = candle.timestamp

        # Phase 14 live-boundary gates (mandatory, dry AND live —
        # this shared path runs before EITHER branch). The
        # execution_signal fallback is pre-risk: a signal the
        # RiskEngine just rejected (or a hand-fed context) must
        # never reach routing on any path. Mirrors the paper
        # engine's fallback gates plus the cost-aware layer, so
        # no order bypasses RiskEngine through this fallback:
        #   1. directional geometry (inverted plans refuse);
        #   2. gross R:R within the active minimum-R policy
        #      (RiskEngine's wired duty, re-enforced here
        #      defense-in-depth);
        #   3. post-cost R:R via the single authority
        #      (costs-aware; vacuous at zero costs, enforced
        #      when nonzero, non-finite fails closed).
        # Refusal returns BEFORE any mirror or transport state.
        route_direction = str(getattr(order, "direction", "") or "")
        try:
            route_entry = float(getattr(order, "entry", 0.0) or 0.0)
            route_stop = float(getattr(order, "stop_loss", 0.0) or 0.0)
            route_target = float(
                getattr(order, "take_profit", 0.0) or 0.0)
        except (TypeError, ValueError):
            log.error(
                "ROUTE_BLOCKED_NON_FINITE_PRICE setup_id=%s",
                getattr(order, "setup_id", "") or "",
            )
            return

        if not directional_geometry_ok(
            route_direction, route_entry, route_stop, route_target,
        ):
            log.error(
                "ROUTE_BLOCKED_GEOMETRY setup_id=%s",
                getattr(order, "setup_id", "") or "",
            )
            return

        symbol = str(getattr(order, "symbol", "") or "")
        from core.risk.trading_policy import trading_policy
        policy = trading_policy(symbol)
        route_rr = order_rr(route_entry, route_stop, route_target)
        # Single authority: qualify the planned target as FIXED even when the
        # order will be trailing-managed (mirrors RiskEngine: authored target
        # validated first, then trailing promotion). Threads per-symbol policy.
        if (
            route_rr is None
            or not risk_reward_allowed(route_rr, exit_mode="FIXED_TARGET", symbol=symbol)
        ):
            log.error(
                "ROUTE_BLOCKED_RR setup_id=%s rr=%s",
                getattr(order, "setup_id", "") or "",
                route_rr,
            )
            return

        try:
            route_quantity = float(
                getattr(order, "quantity", 1.0) or 0.0)
            route_commission = float(
                getattr(order, "commission", 0.0) or 0.0)
            route_slippage = float(
                getattr(order, "slippage", 0.0) or 0.0)
        except (TypeError, ValueError):
            log.error(
                "ROUTE_BLOCKED_NON_FINITE_COSTS setup_id=%s",
                getattr(order, "setup_id", "") or "",
            )
            return

        route_exit_mode = str(getattr(order, "exit_mode", "FIXED_TARGET") or "FIXED_TARGET").upper()
        if route_exit_mode == "TRAILING_STOP":
            route_verdict = post_cost_trailing(
                direction=route_direction,
                entry=route_entry,
                stop=route_stop,
                quantity=route_quantity,
                commission=route_commission,
                slippage=route_slippage,
                target=route_target,
                symbol=symbol,
            )
        else:
            route_verdict = post_cost_rr(
                direction=route_direction,
                entry=route_entry,
                stop=route_stop,
                target=route_target,
                quantity=route_quantity,
                commission=route_commission,
                slippage=route_slippage,
                exit_mode=route_exit_mode,
                symbol=symbol,
            )
        if not route_verdict.allowed:
            log.error(
                "ROUTE_BLOCKED_POST_COST_RR setup_id=%s rr=%.4f "
                "reason=%s",
                getattr(order, "setup_id", "") or "",
                route_verdict.rr,
                route_verdict.reason,
            )
            return

        # The live trade is the engine's local mirror of the
        # position it is working for -- created on ANY routed
        # intent, so current_trade() correctly suppresses a
        # second fill while the first is still working.
        self._live_trade = Trade(
            direction=order.direction,
            entry=order.entry,
            stop_loss=order.stop_loss,
            take_profit=order.take_profit,
            exit_mode=getattr(order, "exit_mode", risk_settings.EXIT_MODE_FIXED_TARGET),
            trailing_enabled=bool(getattr(order, "trailing_enabled", policy.trailing_enabled)),
            trailing_activation_r=float(getattr(order, "trailing_activation_r", policy.trailing_activation_r) or 0.0),
            trailing_distance_r=float(getattr(order, "trailing_distance_r", policy.trailing_distance_r) or 0.0),
            trailing_method=str(getattr(order, "trailing_method", getattr(policy, "trailing_method", "R_DISTANCE")) or "R_DISTANCE"),
            trailing_step_r=float(getattr(order, "trailing_step_r", getattr(policy, "trailing_step_r", 0.0)) or 0.0),
            tick_size=float(getattr(self.simulator, "tick_size", 0.0) or 0.0),
            initial_stop_loss=order.stop_loss,
            quantity=route_quantity,
            risk_amount=getattr(order, "risk_amount", 0.0),
            commission=getattr(order, "commission", 0.0),
            slippage=getattr(order, "slippage", 0.0),
            entry_time=candle.timestamp,
            setup_score=getattr(order, "score", 0.0),
            confidence=getattr(order, "confidence", 0.0),
            symbol=symbol,
        )
        try:
            self._live_trade.validate_executable()
        except ValueError as err:
            log.error(
                "ROUTE_BLOCKED_INVALID_TRADE setup_id=%s reason=%s",
                getattr(order, "setup_id", "") or "",
                err,
            )
            self._live_trade = None
            return

        self._order_placed_bar = self.total_bars

        if self.dry_run:

            # Zero exchange writes: record the would-be intent
            # and manage a paper position through the SAME
            # TradeSimulator the Backtester uses.
            self.placed.append(order)

            # Phase 13 paper-economics unification: dry-run fills
            # consume the ONE authoritative paper economics object
            # (core.risk.costs.paper_cost_profile — the same object
            # readiness/certification reporting uses), re-minted
            # from the fill notional. Under the default
            # explicit-zero-neutral profile this yields (0.0, 0.0)
            # and behavior is byte-identical to the legacy path;
            # when the operator configures nonzero PAPER_* costs,
            # fills carry them (and the simulator's post-cost R:R
            # gate validates them). The caller's order is NOT
            # mutated: re-minted values travel only as open_trade
            # args, so booking still subtracts exactly once and
            # the registry's stored intent is untouched. A broken
            # notional falls back to the intent costs (never an
            # invented number).
            try:
                _paper_spec = paper_cost_profile()
                _fill_notional = float(
                    getattr(order, "quantity", 1.0) or 0.0
                ) * float(getattr(order, "entry", 0.0) or 0.0)
                if _fill_notional > 0:
                    dry_commission, dry_slippage = _paper_spec.compute(
                        _fill_notional
                    )
                else:
                    dry_commission = float(
                        getattr(order, "commission", 0.0) or 0.0)
                    dry_slippage = float(
                        getattr(order, "slippage", 0.0) or 0.0)
            except Exception:  # noqa: BLE001 (fail open to legacy)
                dry_commission = float(
                    getattr(order, "commission", 0.0) or 0.0)
                dry_slippage = float(
                    getattr(order, "slippage", 0.0) or 0.0)

            log.info(
                "DRY_RUN_ECONOMICS setup_id=%s profile=%s "
                "commission=%.4f slippage=%.4f",
                getattr(order, "setup_id", "") or "",
                paper_profile_name(),
                dry_commission,
                dry_slippage,
            )

            trade = self.simulator.open_trade(
                order,
                candle.timestamp,
                quantity=getattr(order, "quantity", 1.0),
                commission=dry_commission,
                slippage=dry_slippage,
            )

            if trade is not None:

                self._mark_order_filled(
                    order, trade, candle.timestamp
                )

                # Dry-run fills come from the shared
                # TradeSimulator -- the fill evidence itself --
                # so the confirmation flags track it.
                self._fill_confirmed = True

                self._ack_state = FILLED

            return

        # ---- LIVE: real place (auth-guarded by the adapter) ----
        #
        # Phase 11A defense in depth: re-enforce the gate on
        # EVERY live route (not just construction), then hand
        # the arming token to executors that support it. A
        # refused gate raises BEFORE the transport is called.

        LiveSafetyGate.require_decision(
            self._safety,
            component="BrokerEngine._route",
        )

        # Phase 12 fail-closed execution boundary: an executor
        # exception means the exchange state is UNPROVEN, so the
        # transient mirror is cleared, a typed failure is
        # recorded, and routing halts -- the engine never
        # continues believing an unconfirmed order is filled,
        # and never re-routes blindly into a possible
        # duplicate. Recovery is explicit operator resolution
        # (reconciler.resolve) after out-of-band verification.
        try:
            if getattr(self.executor, "supports_safety", False):
                result = self.executor.execute(
                    order, safety=self._safety
                )
            else:
                result = self.executor.execute(order)
        except Exception as exc:  # noqa: BLE001 (fail closed)
            ack = classify_exception(exc)

            self._last_error = {
                "stage": "execute",
                "reason": ack.detail,
                "setup_id": getattr(order, "setup_id", "") or "",
                "order_id": getattr(order, "order_id", "") or "",
            }

            self.placed.append(
                {
                    "success": False,
                    "reason": "EXECUTOR_EXCEPTION",
                    "detail": ack.detail,
                }
            )

            self._live_trade = None

            self._last_intent = None

            self._ack_state = UNKNOWN

            self._fill_confirmed = False

            log.error(
                "Live order exception (state UNKNOWN, routing "
                "halted): %s",
                ack.detail,
            )

            self.reconciler._halt(
                "EXECUTOR_EXCEPTION state UNKNOWN",
            )

            return

        self.placed.append(result)

        if result is None or not result.get("success"):

            reason = (
                result.get("reason")
                if isinstance(result, dict)
                else "execute returned no result"
            )

            log.error(
                "Live order rejected: %s",
                reason,
            )

            self._live_trade = None

            self._last_intent = None

            self._ack_state = REJECTED

            self._fill_confirmed = False

            return

        response = result.get("response") or {}

        self._open_order_id = (
            _field(response, "id", "order_id")
            if isinstance(response, dict)
            else _field(result, "id", "order_id")
        )

        contract = result.get("contract")

        if contract is not None:
            self._product_id = getattr(contract, "product_id", None)

        # Phase 12 acknowledgement truth: executor success is
        # NOT a fill. The raw acknowledgement is classified
        # into an explicit state and only a FILLED verdict --
        # explicit filled label plus fill-quantity evidence --
        # may take the filled transition. A working order stays
        # a working mirror (suppression intact, nothing booked);
        # PARTIAL or UNKNOWN halt routing until the exchange
        # truth is resolved; terminal dead states clear the
        # mirror so a dead order never blocks reuse.
        ack = classify_ack(response)

        self._ack_state = ack.state

        if ack.state == FILLED:

            self._confirm_live_fill(
                order, candle.timestamp
            )

        elif ack.state == ACKNOWLEDGED:

            log.info(
                "ORDER_ACKNOWLEDGED setup_id=%s order_id=%s "
                "exchange_order_id=%s ts=%s",
                getattr(order, "setup_id", "") or "",
                getattr(order, "order_id", "") or "",
                self._open_order_id,
                candle.timestamp,
            )

        elif ack.state == PARTIAL:

            log.error(
                "Live order partially filled (never FILLED, "
                "routing halted): setup_id=%s order_id=%s "
                "detail=%s",
                getattr(order, "setup_id", "") or "",
                getattr(order, "order_id", "") or "",
                ack.detail,
            )

            self.reconciler._halt(
                "PARTIAL_FILL never FILLED",
            )

        elif ack.state in (REJECTED, CANCELLED, EXPIRED):

            log.error(
                "Live order dead on arrival (%s): setup_id=%s "
                "order_id=%s detail=%s",
                ack.state,
                getattr(order, "setup_id", "") or "",
                getattr(order, "order_id", "") or "",
                ack.detail,
            )

            self._live_trade = None

            self._last_intent = None

            self._open_order_id = None

            self._fill_confirmed = False

        else:

            self._last_error = {
                "stage": "acknowledge",
                "reason": ack.detail,
                "setup_id": getattr(order, "setup_id", "") or "",
                "order_id": getattr(order, "order_id", "") or "",
            }

            log.error(
                "Live order acknowledgement UNKNOWN "
                "(never FILLED, routing halted): setup_id=%s "
                "order_id=%s detail=%s",
                getattr(order, "setup_id", "") or "",
                getattr(order, "order_id", "") or "",
                ack.detail,
            )

            self.reconciler._halt(
                "UNKNOWN_ACK state unproven",
            )

    # ==================================================
    # Order-lifecycle completion (Phase 4C)
    # ==================================================

    def _mark_order_filled(self, order, trade, timestamp):

        order_registry = getattr(
            self.pipeline.context, "order_registry", None
        )

        order_id = getattr(order, "order_id", "") or ""

        if order_registry is None or not order_id:
            return

        registered = order_registry.get(order_id)

        if registered is None or registered.status != PENDING:
            return

        trade_id = order_registry.mark_filled(order, trade)

        order.trade_id = trade_id

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

    def _confirm_live_fill(self, order, timestamp):
        """Record an exchange-confirmed fill (Phase 12).

        The ONLY live transition into FILLED. Callers must
        supply fill evidence: an explicit FILLED ack, a
        visible exchange position, or a fetch-confirmed
        filled order record. Sets the confirmation flags so
        repeat sightings never double-book.
        """

        if getattr(self, "_fill_confirmed", False):
            return

        self._fill_confirmed = True

        self._ack_state = FILLED

        self._mark_order_filled(
            order,
            self._live_trade,
            timestamp,
        )

    # ==================================================
    # Stage 1-3 hardening: live reconciliation driver
    # ==================================================

    def _reconcile_live(self, candle):
        rec = self.reconciler
        if rec.executor is None:
            return
        local = None
        if self._in_position and self._live_trade is not None:
            mirror = self._live_trade
            local = {"side": getattr(mirror, "direction", None),
                     "quantity": getattr(mirror, "quantity", 0.0),
                     "entry": getattr(mirror, "entry", None)}
        local_order = None
        if self._open_order_id and not self._in_position:
            placed = (self._order_placed_bar
                      if self._order_placed_bar is not None
                      else self.total_bars)
            local_order = {"order_id": self._open_order_id,
                           "status": "PENDING",
                           "age_bars": self.total_bars - placed}
        if self.total_bars % rec.check_interval_bars == 0:
            verdict = rec.runtime_check(
                self.total_bars, candle.timestamp,
                local_position=local, local_order=local_order)
            log.info(
                "RECONCILE_CHECK verdict=%s reason=%s",
                verdict.get("verdict"), verdict.get("reason", ""),
            )
        rec.persist(rec.snapshot_state(
            self._in_position, self._open_order_id, self._product_id,
            self._live_trade, candle.timestamp,
            ack_state=getattr(self, "_ack_state", None),
            order_seq=order_seq_value()))

    # ==================================================
    # Dry-run position management (paper semantics)
    # ==================================================

    def _manage_paper(self, candle):

        before = self.registry.count()

        self.simulator.update(candle)

        self._book_closed(
            self.simulator.registry.all()[before:],
            candle,
        )

    # ==================================================
    # Live position sync (exchange authority)
    # ==================================================

    def _sync_live(self, candle):

        try:

            records = _fields_list(
                self.executor.positions()
            )

        except Exception as exc:  # noqa: BLE001

            log.error(
                "Live position sync failed: %s",
                exc,
            )

            return

        # A "position" means a working, non-zero record. Zero-size
        # records that Delta keeps after a bracket wheels the book
        # flat are NOT positions.
        position = self._find_position(records, include_zero=False)

        if position is None and self._open_order_id:

            # Order placed but never became a position: the fill
            # watch also catches a cancelled / expired / rejected
            # order so a dead order never blocks reuse.
            self._watch_open_order()

        if position is None:

            if self._in_position:

                self._book_live_close(candle, records)

                self._in_position = False

            self._sync_equity(candle)

            return

        # Phase 12 fill confirmation: a visible exchange
        # position is fill evidence for a working mirror that
        # was only ACKNOWLEDGED at placement. The registry
        # FILLED transition happens HERE (or on an explicit
        # filled ack/fetch), never at execute() return.
        if (
            self._live_trade is not None
            and not getattr(self, "_fill_confirmed", False)
            and self._last_intent is not None
        ):

            self._confirm_live_fill(
                self._last_intent, candle.timestamp
            )

        self._in_position = True

    # --------------------------------------------------

    def _find_position(self, records, include_zero=False):

        if not records:
            return None

        def working(record):
            if include_zero:
                return True
            try:
                size = abs(
                    float(
                        _field(
                            record,
                            "size",
                            "quantity",
                            default=0.0,
                        )
                    )
                )
            except (TypeError, ValueError):
                # Malformed size field: not a working
                # position, never a crash (11C-D required
                # vs optional: size is REQUIRED to claim a
                # position; an unreadable size degrades to
                # "no position" and is counted as drift).
                _note_drift("miss", "size", "")
                return False
            return size > 0

        if self._product_id is not None:

            for record in records:

                pid = _field(record, "product_id", "productId")

                if pid is None:
                    continue

                try:
                    matches = int(pid) == int(self._product_id)
                except (TypeError, ValueError):
                    # Malformed product id: cannot match this
                    # record; skip it instead of crashing the
                    # live sync loop.
                    _note_drift("miss", "product_id", "")
                    continue

                if matches and working(record):
                    return record

            return None

        for record in records:

            if working(record):
                return record

        return None

    # --------------------------------------------------

    def _watch_open_order(self):

        try:

            response = self.executor.fetch(self._open_order_id)

        except Exception as exc:  # noqa: BLE001

            log.error(
                "Live order watch failed: %s",
                exc,
            )

            return

        # Phase 12: the fetched order record is classified
        # through the same acknowledgement truth as placement.
        # A fetch-confirmed fill completes the working mirror;
        # a partial fill halts (never FILLED); dead states clear
        # the id so a dead order never blocks reuse; anything
        # else keeps watching (never assume, never clear).
        ack = classify_ack(response)

        if ack.state == FILLED:

            if (
                self._live_trade is not None
                and not getattr(self, "_fill_confirmed", False)
                and self._last_intent is not None
            ):

                self._confirm_live_fill(
                    self._last_intent,
                    getattr(
                        self.pipeline.context.market,
                        "timestamp",
                        None,
                    )
                    if getattr(self, "pipeline", None)
                    is not None
                    else None,
                )

            return

        if ack.state == PARTIAL:

            log.error(
                "Live order watch saw PARTIAL fill (never "
                "FILLED, routing halted): order_id=%s",
                self._open_order_id,
            )

            self.reconciler._halt(
                "PARTIAL_FILL seen on watch",
            )

            return

        if ack.state in (REJECTED, CANCELLED, EXPIRED):

            self._open_order_id = None

    # --------------------------------------------------

    def _book_live_close(self, candle, records):

        trade = self._live_trade

        self._live_trade = None

        self._open_order_id = None

        self._fill_confirmed = False

        self._ack_state = None

        if trade is None:
            return

        # The flat record the exchange keeps after the bracket
        # wheeled the position is the authority for the exit price
        # and the realized P&L (already net of fees when reported).
        flat = self._find_position(records, include_zero=True)

        exit_price = trade.entry

        reported_price = (
            _field(
                flat,
                "exit_price",
                "close_price",
                "average_exit_price",
            )
            if flat is not None
            else None
        )

        if reported_price is not None:
            try:
                exit_price = float(reported_price)
            except (TypeError, ValueError):
                # Malformed exit price: keep the entry price
                # (zero-P&L close) rather than crashing or
                # booking a fabricated exit.
                _note_drift("miss", "exit_price", "")

        trade.exit_time = candle.timestamp

        trade.exit_price = exit_price

        trade.status = "CLOSED"

        gross = gross_pnl(trade.direction, trade.entry, exit_price, trade.quantity)

        exchange_pnl = (
            _field(flat, "realized_pnl", "realised_pnl")
            if flat is not None
            else None
        )

        if exchange_pnl is not None:

            # Exchange-reported P&L is the ledger truth and is
            # already net of fees -- subtract nothing, and drop
            # the modeled costs so analytics never add fees twice.
            try:
                pnl = float(exchange_pnl)
            except (TypeError, ValueError):
                # Malformed exchange P&L: degrade to the
                # modeled net P&L (same as "not reported")
                # instead of crashing or fabricating a figure.
                _note_drift("miss", "realized_pnl", "")
                exchange_pnl = None

        if exchange_pnl is not None:

            trade.commission = 0.0

            trade.slippage = 0.0

        else:

            pnl = net_pnl(gross, trade.commission, trade.slippage)

        trade.pnl = pnl

        trade.pnl_percent = position_return_percent(trade.pnl, trade.entry, trade.quantity)

        trade.result = classify_pnl(pnl)

        self.registry.add(trade)

        # Canonical classification: WIN >0, LOSS <0, BREAKEVEN ==0
        if classify_pnl(pnl) == "WIN":
            self.account.book_profit(pnl)
        elif classify_pnl(pnl) == "LOSS":
            self.account.book_loss(-pnl)
        else:
            self.account.book_breakeven()

        if self.portfolio_release is not None:

            self.portfolio_release(trade)

    # --------------------------------------------------

    def _sync_equity(self, candle):  # noqa: ARG001

        try:

            response = self.executor.balance()

        except Exception as exc:  # noqa: BLE001

            log.error(
                "Live equity sync failed: %s",
                exc,
            )

            return

        equity = _field(
            response,
            "total_equity",
            "equity",
            "total_balance",
        )

        if equity is None:
            return

        try:
            equity_value = float(equity)
        except (TypeError, ValueError):
            # Malformed equity figure: keep the last synced
            # equity instead of crashing or storing garbage.
            _note_drift("miss", "total_equity", "")
            return

        self.account.state.balance = equity_value

        self.account.update_equity()

    # ==================================================
    # Shared booking (dry-run closes)
    # ==================================================

    def _book_closed(self, closed_now, candle):  # noqa: ARG001

        if not closed_now:
            return

        if len(closed_now) != 1:

            raise RuntimeError(
                "BrokerEngine: expected exactly one trade closed "
                f"per candle, got {len(closed_now)}."
            )

        closed = closed_now[0]

        self.registry.add(closed)

        # Canonical classification via accounting
        from core.backtesting.accounting import classify_pnl

        kind = classify_pnl(closed.pnl)
        if kind == "WIN":
            self.account.book_profit(closed.pnl)
        elif kind == "LOSS":
            self.account.book_loss(-closed.pnl)
        else:
            self.account.book_breakeven()

        if self.portfolio_release is not None:

            self.portfolio_release(closed)

    # ==================================================
    # Results
    # ==================================================

    @property
    def trades(self):

        return self.registry

    # --------------------------------------------------

    @property
    def completed_trades(self):

        return self.registry.all()

    # --------------------------------------------------

    @property
    def current_trade(self):

        if self.dry_run:

            return self.simulator.current_trade

        return self._live_trade

    # --------------------------------------------------

    @property
    def _is_in_position(self):

        if self.dry_run:

            return self.simulator.current_trade is not None

        return self._in_position

    # --------------------------------------------------

    @property
    def processed_bars(self):

        return self.total_bars

    # --------------------------------------------------

    @property
    def last_intent(self):

        return self._last_intent