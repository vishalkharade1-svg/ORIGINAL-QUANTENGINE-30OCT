"""
====================================================

QuantEngine

Research Journal -- core observer (Phase 9A)

A pure OBSERVER of the settled trading state. It reads the
authoritative engine state produced by the frozen Backtester /
PaperRuntime (PipelineContext + TradeRegistry) at the end of
every bar and appends RESEARCH EVENTS describing what actually
happened. It NEVER:

   * mutates an order, setup, strategy, risk or portfolio object
   * returns a value the engine consumes
   * blocks / raises into the trading path (fail-safe, logged)

Reconciliation model (deterministic, replay-safe):
An identical candle sequence + identical engine yields an
identical event stream and an identical OpportunityRecord
snapshot. No wall-clock, no random UUIDs -- event_id derives
from a per-journal sequence counter + bar.

MAE / MFE / R are consumed from the existing authoritative
diagnostic source (context.causal_validation.breakout_mae /
breakout_mfe / breakout_r_multiple) where available; never
fabricated.
====================================================
"""

from dataclasses import dataclass, field

from core.common.logging_config import get_logger

from core.research.journal.research_enums import (
    Provenance,
    SetupLifecycle,
    OrderLifecycle,
    Result,
    EntryReached,
    EventType,
)
from core.research.journal.research_event import ResearchEvent
from core.research.journal.setup_record import SetupRecord
from core.research.journal.order_record import OrderRecord
from core.research.journal.trade_record import TradeRecord
from core.research.journal.opportunity_record import OpportunityRecord
from core.research.journal.research_repository import ResearchRepository

log = get_logger(__name__)

# Number of bars over which an unfilled order's post-terminal
# market path is observed for missed-continuation facts.
_MISSED_TRACK_BARS = 30


@dataclass
class _PathObserver:
    """Bounded post-terminal market-path observer for an
    unfilled opportunity (missed-continuation facts)."""

    key: str
    canonical_id: str = ""
    setup_id: str = ""
    order_id: str = ""
    direction: str = ""
    entry: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    terminal_bar: int = 0
    trade_id: str = ""
    bars_tracked: int = 0
    max_price: float = None
    min_price: float = None
    max_favorable: float = None
    max_adverse: float = None
    target_reached: bool = False
    stop_breached: bool = False
    resolved: bool = False


@dataclass
class _OpportunityState:
    """Internal per-opportunity working state (combines
    setup/order/trade facts before final assembly)."""

    key: str = ""
    canonical_id: str = ""
    setup: dict = None
    order: dict = None
    trade: dict = None
    trade_id: str = ""
    order_status: str = None
    trade_result: str = None
    terminal_outcome: str = "ORDER_NOT_CREATED"


class ResearchJournal:
    """Append-only observer of the settled trading lifecycle."""

    def __init__(self, repository=None, provenance=None):
        self.repository = repository or ResearchRepository()
        self._seq = 0
        self._first_bar = None
        self._opportunities = {}
        self._orders_seen = set()
        self._trades_seen = set()
        self._path = {}
        self._provenance = (
            provenance if provenance is not None else Provenance.BACKTEST.value
        )
        self._failures = 0

    # --------------------------------------------------
    # Identity helpers
    # --------------------------------------------------

    @staticmethod
    def _market_identity(context):
        market = getattr(context, "market", None)
        exchange = getattr(market, "exchange", "") or ""
        instrument_id = getattr(market, "instrument_id", "") or ""
        timeframe = getattr(market, "timeframe", "") or ""
        return exchange, instrument_id, timeframe

    def _next_event(
        self, event_type, bar, timestamp, identity, setup_id="",
        order_id="", payload=None
    ):
        exchange, instrument_id, timeframe, canonical_id, strategy = identity
        self._seq += 1
        return ResearchEvent(
            event_id=f"evt-{self._seq}-{bar}-{self._provenance}",
            provenance=self._provenance,
            event_type=event_type,
            bar=bar,
            timestamp=timestamp,
            canonical_id=canonical_id,
            exchange=exchange,
            instrument_id=instrument_id,
            timeframe=timeframe,
            direction=payload.get("direction", "") if payload else "",
            strategy=strategy,
            setup_id=setup_id,
            order_id=order_id,
            payload=dict(payload or {}),
        )

    # --------------------------------------------------
    # Public observer hook -- called once per settled bar
    # --------------------------------------------------

    def on_bar_observed(
        self,
        context,
        candle=None,
        registry=None,
        provenance=None,
        bar=None,
    ):
        """Reconcile authoritative engine state after one candle
        has fully settled. Fail-safe: never raises into trading."""
        provenance = provenance or self._provenance
        if bar is None:
            bar = getattr(context, "current_index", None) or 0
        if self._first_bar is None:
            self._first_bar = bar
            self._provenance = provenance
        try:
            self._reconcile(
                context, candle, registry, provenance=provenance, bar=bar
            )
        except Exception:
            self._failures += 1
            if self._failures <= 3:
                log.exception(
                    "research_journal reconcile error at bar=%s", bar
                )

    # --------------------------------------------------

    def _reconcile(self, context, candle, registry, provenance, bar):
        exchange, instrument_id, timeframe = self._market_identity(context)
        ts = getattr(candle, "timestamp", None) if candle is not None else None

        # 1) setups (current candle's discoveries)
        setups = getattr(context, "trade_setups", None) or []
        for cand in setups:
            self._reconcile_setup(
                cand, exchange, instrument_id, timeframe, provenance, bar, ts
            )

        # 2) orders (registry is session-persistent; reconcile deltas)
        order_registry = getattr(context, "order_registry", None)
        if order_registry is not None:
            for order in list(order_registry.all()):
                self._reconcile_order(
                    order, exchange, instrument_id, timeframe,
                    provenance, bar, ts, context,
                )

        # 3) closed trades (authoritative TradeRegistry)
        if registry is not None:
            for trade in registry.all():
                self._reconcile_trade(
                    trade, exchange, instrument_id, timeframe,
                    provenance, context,
                )

        # 4) advance post-terminal path observers (missed continuation)
        self._advance_path(
            context, candle, exchange, instrument_id, timeframe
        )

        # 5) resolve opportunities whose lifecycle is now terminal
        self._resolve_terminal(bar)

    # --------------------------------------------------
    # Setup reconciliation
    # --------------------------------------------------

    def _candidate_identity(self, cand, exchange, instrument_id, timeframe):
        canonical_id = getattr(cand, "canonical_id", "") or ""
        setup_id = getattr(cand, "setup_id", "") or ""
        direction = getattr(cand, "direction", "") or ""
        strategy = getattr(cand, "entry_mode", "") or ""
        if not canonical_id and setup_id:
            canonical_id = setup_id
        return (exchange, instrument_id, timeframe, canonical_id, strategy)

    def _reconcile_setup(
        self, cand, exchange, instrument_id, timeframe, provenance, bar, ts
    ):
        identity = self._candidate_identity(
            cand, exchange, instrument_id, timeframe
        )
        _, _, _, canonical_id, strategy = identity
        setup_id = getattr(cand, "setup_id", "") or ""
        # Key must be symbol-scoped: distinct instruments can share a
        # setup_id, so empty canonical ids must not collide across
        # symbols (deterministic ordering by exchange:instrument_id).
        key = canonical_id or (
            f"{exchange}:{instrument_id}:{timeframe}:{setup_id}"
            if setup_id
            else f"{exchange}:{instrument_id}:{timeframe}:{bar}"
        )

        direction = getattr(cand, "direction", "") or ""

        lifecycle = getattr(cand, "lifecycle", "") or SetupLifecycle.DISCOVERED.value
        structurally_valid = bool(getattr(cand, "structurally_valid", True))
        trade_eligible = bool(getattr(cand, "trade_eligible", True))
        entry_rejection = getattr(cand, "entry_rejection_reason", "") or ""

        # Collect ALL rejection reasons verbatim.
        rejection_reasons = []
        zone_diag = list(getattr(cand, "zone_diagnostics", None) or [])
        if not structurally_valid:
            rejection_reasons.append("STRUCTURALLY_INVALID")
        if not trade_eligible and entry_rejection:
            rejection_reasons.append(entry_rejection)
        for diag in zone_diag:
            txt = getattr(diag, "reason", None) or str(diag)
            if txt:
                rejection_reasons.append(txt)

        is_rejected = (
            lifecycle == SetupLifecycle.REJECTED.value
            or entry_rejection != ""
            or (not structurally_valid)
        )
        if is_rejected:
            eff_lifecycle = SetupLifecycle.REJECTED.value
        elif lifecycle in (
            SetupLifecycle.ACCEPTED.value,
            SetupLifecycle.ORDER_CREATED.value,
            SetupLifecycle.PENDING.value,
            SetupLifecycle.FILLED.value,
            SetupLifecycle.CLOSED.value,
        ):
            eff_lifecycle = lifecycle
        else:
            eff_lifecycle = SetupLifecycle.DISCOVERED.value

        ev_type = (
            EventType.SETUP_REJECTED
            if is_rejected
            else EventType.SETUP_DISCOVERED
        )

        record = SetupRecord(
            provenance=provenance,
            exchange=exchange,
            instrument_id=instrument_id,
            timeframe=timeframe,
            direction=direction,
            strategy=strategy,
            setup_id=setup_id,
            structural_id=getattr(cand, "structural_id", "") or "",
            economic_fingerprint=(
                getattr(cand, "economic_fingerprint", "") or ""
            ),
            canonical_id=canonical_id,
            entry=float(getattr(cand, "entry", 0.0) or 0.0),
            stop_loss=float(getattr(cand, "stop_loss", 0.0) or 0.0),
            take_profit=float(getattr(cand, "take_profit", 0.0) or 0.0),
            risk_reward=float(getattr(cand, "risk_reward", 0.0) or 0.0),
            atr=float(getattr(cand, "atr", 0.0) or 0.0),
            entry_distance=float(getattr(cand, "zone_distance", 0.0) or 0.0),
            entry_distance_atr=float(
                getattr(cand, "zone_distance_atr", 0.0) or 0.0
            ),
            observed_price=float(getattr(cand, "observed_price", 0.0) or 0.0),
            score=float(getattr(cand, "score", 0.0) or 0.0),
            confidence=float(getattr(cand, "confidence", 0.0) or 0.0),
            entry_mode=strategy,
            lifecycle=eff_lifecycle,
            structurally_valid=structurally_valid,
            trade_eligible=trade_eligible,
            entry_rejection_reason=entry_rejection,
            rejection_reasons=rejection_reasons,
            zone_diagnostics=zone_diag,
            zone_freshness=getattr(cand, "zone_freshness", "") or "",
            zone_age_bars=int(getattr(cand, "zone_age_bars", 0) or 0),
            is_economic_duplicate=bool(
                getattr(cand, "is_economic_duplicate", False)
            ),
            bar=bar,
            timestamp=ts,
        )

        payload = {"direction": direction, "entry_mode": strategy}
        self.repository.append_event(
            self._next_event(
                ev_type, bar, ts, identity, setup_id=setup_id, payload=payload
            )
        )

        state = self._get_state(key, identity)
        state.setup = record.to_dict()
        self._opportunities[key] = state

        if is_rejected:
            state.terminal_outcome = "REJECTED"

    # --------------------------------------------------
    # Order reconciliation
    # --------------------------------------------------

    def _order_identity(self, order, exchange, instrument_id, timeframe):
        canonical_id = getattr(order, "canonical_id", "") or ""
        setup_id = getattr(order, "setup_id", "") or ""
        strategy = getattr(order, "entry_mode", "") or ""
        return (exchange, instrument_id, timeframe, canonical_id, strategy)

    def _reconcile_order(
        self, order, exchange, instrument_id, timeframe,
        provenance, bar, ts, context,
    ):
        order_id = getattr(order, "order_id", "") or ""
        if not order_id:
            return
        setup_id = getattr(order, "setup_id", "") or ""
        identity = self._order_identity(order, exchange, instrument_id, timeframe)
        _, _, _, canonical_id, strategy = identity
        # Symbol-scoped key (see _reconcile_setup): empty canonical ids
        # must not collide across instruments.
        key = canonical_id or (
            f"{exchange}:{instrument_id}:{timeframe}:{setup_id}"
            if setup_id
            else f"order:{order_id}"
        )
        direction = getattr(order, "direction", "") or ""
        status = getattr(order, "status", "") or OrderLifecycle.PENDING.value

        # Orders are deduped by (symbol, order_id), never by order_id
        # alone -- distinct instruments may share identical order_id
        # patterns in a multi-symbol journal.
        order_dedup = (exchange, instrument_id, order_id)
        is_new = order_dedup not in self._orders_seen

        if is_new:
            self._orders_seen.add(order_dedup)

            record = OrderRecord(
                provenance=provenance,
                exchange=exchange,
                instrument_id=instrument_id,
                timeframe=timeframe,
                direction=direction,
                strategy=strategy,
                setup_id=setup_id,
                canonical_id=canonical_id,
                order_id=order_id,
                trade_id=getattr(order, "trade_id", "") or "",
                entry=float(getattr(order, "entry", 0.0) or 0.0),
                stop_loss=float(getattr(order, "stop_loss", 0.0) or 0.0),
                take_profit=float(getattr(order, "take_profit", 0.0) or 0.0),
                risk_reward=float(getattr(order, "risk_reward", 0.0) or 0.0),
                risk_amount=float(getattr(order, "risk_amount", 0.0) or 0.0),
                expected_loss=float(getattr(order, "expected_loss", 0.0) or 0.0),
                expected_profit=float(
                    getattr(order, "expected_profit", 0.0) or 0.0
                ),
                position_value=float(
                    getattr(order, "position_value", 0.0) or 0.0
                ),
                entry_mode=strategy,
                score=float(getattr(order, "score", 0.0) or 0.0),
                confidence=float(getattr(order, "confidence", 0.0) or 0.0),
                status=status,
                created_bar=getattr(order, "created_bar", None),
                eligible_from_bar=getattr(order, "eligible_from_bar", None),
                expires_at_bar=getattr(order, "expires_at_bar", None),
                filled_bar=getattr(order, "filled_bar", None),
                terminal_bar=getattr(order, "terminal_bar", None),
                waited_bars=int(getattr(order, "waited_bars", 0) or 0),
                bars_pending=int(getattr(order, "bars_pending", 0) or 0),
                entry_distance_from_nearest_price=getattr(
                    order, "entry_distance_from_nearest_price", None
                ),
                min_low_since_creation=getattr(
                    order, "min_low_since_creation", None
                ),
                max_high_since_creation=getattr(
                    order, "max_high_since_creation", None
                ),
                reason="",
            )
            # Entry-reached fact: derive from min/max excursion facts.
            min_low = record.min_low_since_creation
            max_high = record.max_high_since_creation
            entry = record.entry
            if (
                min_low is not None
                and max_high is not None
                and min_low <= entry <= max_high
            ):
                record.entry_reached = EntryReached.REACHED.value

            payload = {
                "direction": direction,
                "entry_mode": strategy,
                "status": status,
            }
            self.repository.append_event(
                self._next_event(
                    EventType.ORDER_CREATED, bar, ts, identity,
                    setup_id=setup_id, order_id=order_id, payload=payload,
                )
            )

            state = self._get_state(key, identity)
            state.order = record.to_dict()
            state.order_status = status
            if status == OrderLifecycle.FILLED.value:
                state.terminal_outcome = "FILLED_OPEN"
            elif status in (
                OrderLifecycle.EXPIRED.value,
                OrderLifecycle.INVALIDATED.value,
                OrderLifecycle.REJECTED.value,
                OrderLifecycle.CANCELLED.value,
            ):
                state.terminal_outcome = status
                self._register_path(record, state)
            self._opportunities[key] = state

        else:
            # Existing order -- detect status transition. Guard
            # against a state whose order facts were never recorded
            # (e.g. a cross-symbol order_id first seen in isolation).
            state = self._opportunities.get(key)
            if state is None or not isinstance(state.order, dict):
                return
            prev_status = state.order_status
            cur_record = OrderRecord(**state.order)
            if prev_status != status:
                cur_record.status = status
                cur_record.filled_bar = getattr(order, "filled_bar", None) or cur_record.filled_bar
                cur_record.terminal_bar = getattr(order, "terminal_bar", None) or cur_record.terminal_bar
                cur_record.bars_pending = int(
                    getattr(order, "bars_pending", 0) or cur_record.bars_pending
                )
                state.order = cur_record.to_dict()
                state.order_status = status

                ev = {
                    OrderLifecycle.FILLED.value: (EventType.ORDER_FILLED, "FILLED_OPEN"),
                    OrderLifecycle.EXPIRED.value: (EventType.ORDER_EXPIRED, "EXPIRED"),
                    OrderLifecycle.INVALIDATED.value: (EventType.ORDER_INVALIDATED, "INVALIDATED"),
                    OrderLifecycle.REJECTED.value: (EventType.ORDER_REJECTED, "REJECTED"),
                    OrderLifecycle.CANCELLED.value: (EventType.ORDER_REJECTED, "CANCELLED"),
                }.get(status)
                if ev is not None:
                    ev_type, terminal_outcome = ev
                    payload = {"direction": direction, "entry_mode": strategy}
                    self.repository.append_event(
                        self._next_event(
                            ev_type, bar, ts, identity,
                            setup_id=setup_id, order_id=order_id,
                            payload=payload,
                        )
                    )
                    if status in (
                        OrderLifecycle.EXPIRED.value,
                        OrderLifecycle.INVALIDATED.value,
                        OrderLifecycle.REJECTED.value,
                        OrderLifecycle.CANCELLED.value,
                    ):
                        state.terminal_outcome = terminal_outcome
                        self._register_path(cur_record, state)

    def _get_state(self, key, identity):
        state = self._opportunities.get(key)
        if state is None:
            _, _, _, canonical_id, _ = identity
            state = _OpportunityState(
                key=key, canonical_id=canonical_id or key
            )
            self._opportunities[key] = state
        return state

    def _register_path(self, record, state):
        """Start an unfilled post-terminal path observer to record
        missed-continuation OBSERVED facts (was target reached after
        expiry? what extremes did the market print?)."""
        key = state.key
        if key in self._path and self._path[key].resolved:
            return
        direction = record.direction
        entry = record.entry
        obs = _PathObserver(
            key=key,
            canonical_id=record.canonical_id,
            setup_id=record.setup_id,
            order_id=record.order_id,
            direction=direction,
            entry=entry,
            stop_loss=record.stop_loss,
            take_profit=record.take_profit,
            terminal_bar=record.terminal_bar,
            trade_id=record.trade_id,
        )
        self._path[key] = obs

    # --------------------------------------------------
    # Trade reconciliation
    # --------------------------------------------------

    @staticmethod
    def _causal_state(causal, setup_id=None, order_id=None):
        """Locate a CausalValidationState for the given setup/order
        from the authoritative CausalValidator, tolerating both its
        callable `states()` (returns list) and dict-like views."""
        if causal is None:
            return None
        states = None
        for attr in ("states", "validation_states", "_states"):
            obj = getattr(causal, attr, None)
            if callable(obj) and not isinstance(obj, dict):
                try:
                    obj = obj()
                except Exception:
                    obj = None
            if isinstance(obj, (dict, list, tuple)):
                states = obj
                break
        if not states:
            return None
        if isinstance(states, dict):
            for key, s in states.items():
                if key == setup_id or getattr(s, "setup_id", None) == setup_id:
                    return s
        else:
            for s in states:
                if (
                    getattr(s, "setup_id", None) == setup_id
                    or getattr(s, "order_id", None) == order_id
                ):
                    return s
        return None

    def _reconcile_trade(
        self, trade, exchange, instrument_id, timeframe, provenance, context
    ):
        trade_id = getattr(trade, "trade_id", "") or ""
        trade_dedup = (exchange, instrument_id, trade_id)
        if not trade_id or trade_dedup in self._trades_seen:
            return
        status = getattr(trade, "status", "") or ""
        if status == "OPEN":
            return
        self._trades_seen.add(trade_dedup)

        # Derive identity. Trade usually carries canonical_id; fall
        # back to the current context market identity for symbol.
        canonical_id = getattr(trade, "canonical_id", "") or ""
        setup_id = getattr(trade, "setup_id", "") or ""
        order_id = getattr(trade, "order_id", "") or ""

        risk_amount = float(getattr(trade, "risk_amount", 0.0) or 0.0)
        pnl = float(getattr(trade, "pnl", 0.0) or 0.0)
        result = getattr(trade, "result", None) or Result.UNSETTLED.value
        result = (
            result.value if isinstance(result, Result) else str(result)
        )

        # MAE / MFE / R consumed from authoritative diagnostic source.
        mae = mfe = None
        causal = getattr(context, "causal_validation", None)
        cand_state = self._causal_state(
            causal, setup_id=setup_id, order_id=order_id
        )
        if cand_state is not None:
            mae = getattr(cand_state, "breakout_mae", None)
            mfe = getattr(cand_state, "breakout_mfe", None)

        strategy = getattr(trade, "entry_mode", "") or ""

        record = TradeRecord(
            provenance=provenance,
            exchange=exchange,
            instrument_id=instrument_id,
            timeframe=timeframe,
            direction=getattr(trade, "direction", "") or "",
            strategy=strategy,
            setup_id=getattr(trade, "setup_id", "") or "",
            canonical_id=canonical_id,
            order_id=getattr(trade, "order_id", "") or "",
            trade_id=trade_id,
            entry=float(getattr(trade, "entry", 0.0) or 0.0),
            stop_loss=float(getattr(trade, "stop_loss", 0.0) or 0.0),
            take_profit=float(getattr(trade, "take_profit", 0.0) or 0.0),
            exit_price=float(getattr(trade, "exit_price", 0.0) or 0.0),
            quantity=float(getattr(trade, "quantity", 0.0) or 0.0),
            risk_amount=risk_amount,
            entry_mode=strategy,
            entry_time=getattr(trade, "entry_time", None),
            exit_time=getattr(trade, "exit_time", None),
            bars_held=int(getattr(trade, "bars_held", 0) or 0),
            result=result,
            pnl=pnl,
            commission=float(getattr(trade, "commission", 0.0) or 0.0),
            slippage=float(getattr(trade, "slippage", 0.0) or 0.0),
            funding=float(getattr(trade, "funding", 0.0) or 0.0),
            funding_events=int(getattr(trade, "funding_events", 0) or 0),
            mae=mae,
            mfe=mfe,
        )

        self.repository.append_event(
            ResearchEvent(
                event_id=f"evt-trade-{self.repository.count}-{trade_id}",
                provenance=provenance,
                event_type=EventType.TRADE_CLOSED,
                bar=0,
                timestamp=record.exit_time,
                canonical_id=canonical_id,
                exchange=exchange,
                instrument_id=instrument_id,
                timeframe=timeframe,
                direction=record.direction,
                strategy=strategy,
                setup_id=record.setup_id,
                order_id=record.order_id,
                payload={"result": result, "pnl": pnl},
            )
        )

        # Attach trade to its opportunity state. Prefer the real
        # canonical id, then the symbol-scoped setup key (states are
        # keyed by symbol, so a bare setup_id never matches).
        setup_id = record.setup_id
        state = None
        if canonical_id and canonical_id in self._opportunities:
            state = self._opportunities[canonical_id]
        else:
            sym_key = (
                f"{exchange}:{instrument_id}:{timeframe}:{setup_id}"
                if setup_id
                else canonical_id
            )
            state = (
                self._opportunities.get(sym_key)
                if sym_key
                else None
            )
        if state is not None:
            state.trade = record.to_dict()
            state.trade_result = result
            # Propagate the authoritative canonical identity from the
            # filled trade (the order may have been keyed by setup_id
            # only when its own canonical_id was empty at creation).
            if canonical_id:
                state.canonical_id = canonical_id
            state.terminal_outcome = "FILLED_CLOSED"
            self._opportunities[state.key] = state

    # --------------------------------------------------
    # Missed-continuation path tracking
    # --------------------------------------------------

    def _advance_path(self, context, candle, exchange, instrument_id, timeframe):
        if candle is None:
            return
        bar = getattr(context, "current_index", 0) or 0
        high = getattr(candle, "high", None)
        low = getattr(candle, "low", None)
        if high is None or low is None:
            return
        high = float(high)
        low = float(low)

        for key in list(self._path.keys()):
            obs = self._path[key]
            if obs.resolved:
                continue
            if bar - (obs.terminal_bar or 0) > _MISSED_TRACK_BARS:
                obs.resolved = True
                continue
            obs.bars_tracked += 1
            obs.max_price = high if obs.max_price is None else max(obs.max_price, high)
            obs.min_price = low if obs.min_price is None else min(obs.min_price, low)

            # Favorable / adverse in price-distance terms vs entry.
            if obs.direction and obs.direction.upper() == "BULLISH":
                fav = high - obs.entry if obs.entry else None
                adv = obs.entry - low if obs.entry else None
                if obs.take_profit and obs.take_profit > 0 and high >= obs.take_profit:
                    obs.target_reached = True
                if obs.stop_loss and obs.stop_loss > 0 and low <= obs.stop_loss:
                    obs.stop_breached = True
            else:
                fav = obs.entry - low if obs.entry else None
                adv = high - obs.entry if obs.entry else None
                if obs.take_profit and obs.take_profit > 0 and low <= obs.take_profit:
                    obs.target_reached = True
                if obs.stop_loss and obs.stop_loss > 0 and high >= obs.stop_loss:
                    obs.stop_breached = True

            if fav is not None:
                obs.max_favorable = (
                    fav if obs.max_favorable is None else max(obs.max_favorable, fav)
                )
            if adv is not None:
                obs.max_adverse = (
                    adv if obs.max_adverse is None else max(obs.max_adverse, adv)
                )

            # Resolve early once both levels satisfied or window elapsed.
            if obs.target_reached and obs.stop_breached:
                obs.resolved = True

    # --------------------------------------------------
    # Terminal resolution + assembly
    # --------------------------------------------------

    def _resolve_terminal(self, bar):
        for key, state in list(self._opportunities.items()):
            if state.terminal_outcome == "ORDER_NOT_CREATED":
                continue

    def _attach_missed_facts(self, state):
        """Annotate an opportunity's order facts with the observed
        post-terminal path (missed continuation). Returns True when
        still tracking (unresolved)."""
        obs = self._path.get(state.key)
        if obs is None:
            return False
        order = state.order or {}
        missed = {
            "post_terminal_target_reached": obs.target_reached,
            "post_terminal_stop_breached": obs.stop_breached,
            "post_terminal_max_favorable": obs.max_favorable,
            "post_terminal_max_adverse": obs.max_adverse,
            "post_terminal_max_price": obs.max_price,
            "post_terminal_min_price": obs.min_price,
            "post_terminal_bars_tracked": obs.bars_tracked,
        }
        order = dict(order)
        order["missed_continuation"] = missed
        state.order = order
        return not obs.resolved

    def finalize(self):
        """Assemble final OpportunityRecords into the repository.
        Idempotent + deterministic. Call once at end of run."""
        if getattr(self, "_finalized", False):
            return self
        self._finalized = True
        for key, state in self._opportunities.items():
            self._attach_missed_facts(state)
            outcome = state.terminal_outcome
            if (
                outcome in (
                    OrderLifecycle.FILLED.value,
                    "FILLED_OPEN",
                )
                and state.trade is not None
            ):
                outcome = "FILLED_CLOSED"
            record = OpportunityRecord(
                canonical_id=state.canonical_id or key,
                provenance=self._provenance,
                exchange=(
                    state.setup or state.order or {}
                ).get("exchange", ""),
                instrument_id=(
                    state.setup or state.order or {}
                ).get("instrument_id", ""),
                timeframe=(
                    state.setup or state.order or {}
                ).get("timeframe", ""),
                direction=(
                    state.setup or state.order or {}
                ).get("direction", ""),
                strategy=(
                    state.setup or state.order or {}
                ).get("strategy", ""),
                setup_id=(state.setup or {}).get("setup_id", ""),
                setup=state.setup or {},
                order=state.order or {},
                trade=state.trade or {},
                terminal_outcome=outcome,
            )
            self.repository.append_record(record)
        return self

    # --------------------------------------------------

    @property
    def failures(self):
        return self._failures

    @property
    def opportunity_count(self):
        return len(self._opportunities)
