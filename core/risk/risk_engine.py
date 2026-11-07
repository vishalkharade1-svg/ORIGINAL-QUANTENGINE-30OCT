"""
====================================================

QuantEngine

Risk Engine

The Signal -> Risk -> Order Intent adapter that turns the
best-scoring accepted setup into a risk-sized order.

Consumes:
    context.execution_signal
    context.account (equity/balance/drawdown)

Produces:
    context.order (core.risk.order_intent.OrderIntent)

Ranking:
    institutional_pipeline.py registers this at priority 750,
    after DecisionEngine (700) and ExecutionEngine (700), so
    it always sees a fresh, per-candle execution signal.

Behavior:
    - No execution signal  -> context.order = None
    - Zero/negative account -> context.order = None
    - Size is computed by the existing PositionSizer
      (fixed-fractional risk, confidence scaling, regime
      scaling, drawdown protection, allocation cap).
    - Commission/slippage come from config/risk_settings.py.

====================================================
"""

from __future__ import annotations

import math
import os

from config import risk_settings

from core.backtesting.accounting import (
    directional_geometry_ok,
    order_rr,
    risk_reward_allowed,
)
from core.common.base_engine import BaseEngine
from core.common.logging_config import get_logger

from core.execution.execution_engine import (
    pending_direction_capacity,
    pending_total_capacity,
)
from core.execution.entry_model import execution_type_for
from core.order_blocks.zone_freshness import (
    REASON_INSUFFICIENT_RISK_WIDTH,
    REASON_LABELS,
)
from core.risk.order_intent import OrderIntent
from core.risk.position_sizer import PositionSizer
from core.risk.account import roll_state_pnl_windows
from core.risk.costs import from_settings as _production_costs
from core.research.strategy_identity import (
    FROZEN_ERA_MIN_RR,
    frozen_runtime_requested,
)

log = get_logger(__name__)


def loss_limit_blocked(account):
    """Phase 12 loss-limit gate (single authority).

    Returns a reason string when new exposure must stop,
    else None. Windows are fractions of the starting
    balance (MAX_DAILY/WEEKLY/MONTHLY_LOSS in
    config/risk_settings.py); a window blocks when its PnL
    is at or beyond the negative allowance (exact equality
    blocks). A non-positive limit disables that window; a
    non-finite PnL/basis blocks fail-closed (an unreadable
    ledger must never authorize risk).
    """

    if account is None:
        return None

    basis = getattr(account, "starting_balance", 0.0)

    try:
        basis_f = float(basis)
    except (TypeError, ValueError):
        return "LOSS_LIMIT_NON_FINITE_BASIS"

    if not math.isfinite(basis_f):
        return "LOSS_LIMIT_NON_FINITE_BASIS"

    if basis_f <= 0:
        # Empty basis: no order can be sized downstream
        # (balance <= 0 blocks creation), so there is no
        # loss window to enforce -- defer, do not
        # misattribute the block to a loss limit.
        return None

    windows = (
        ("DAILY", getattr(account, "daily_pnl", 0.0),
         getattr(risk_settings, "MAX_DAILY_LOSS", 0.0)),
        ("WEEKLY", getattr(account, "weekly_pnl", 0.0),
         getattr(risk_settings, "MAX_WEEKLY_LOSS", 0.0)),
        ("MONTHLY", getattr(account, "monthly_pnl", 0.0),
         getattr(risk_settings, "MAX_MONTHLY_LOSS", 0.0)),
    )

    for label, pnl, limit in windows:

        try:
            limit_f = float(limit)
        except (TypeError, ValueError):
            return f"{label}_LOSS_LIMIT_NON_FINITE"

        if not math.isfinite(limit_f) or limit_f <= 0:
            continue

        try:
            pnl_f = float(pnl)
        except (TypeError, ValueError):
            return f"{label}_LOSS_NON_FINITE"

        if not math.isfinite(pnl_f):
            return f"{label}_LOSS_NON_FINITE"

        if pnl_f <= -(limit_f * basis_f):
            return f"{label}_LOSS_LIMIT"

    return None


def kill_switch_active(account=None):
    """Stage 4 kill-switch seam (single authority).

    Active when ANY of: AccountState.kill_switch truthy,
    AccountState.trading_enabled falsy, or the restart-persistent
    env override (risk_settings.KILL_SWITCH_ENV_VAR) truthy.
    Malformed values fail CLOSED (block). Recovery requires
    explicit operator action (clear flags + unset env).
    Existing state stays observable; only NEW orders stop.
    """
    try:
        if account is not None:
            if bool(getattr(account, "kill_switch", False)):
                return True
            if not getattr(account, "trading_enabled", True):
                return True
        env_var = getattr(risk_settings, "KILL_SWITCH_ENV_VAR",
                          "QE_KILL_SWITCH")
        return (os.getenv(env_var, "") or "").strip().lower() in (
            "1", "true", "yes", "on")
    except Exception:  # noqa: BLE001 (fail closed on unreadable state)
        return True


class RiskEngine(BaseEngine):

    priority = 750

    dependencies = [
        "ExecutionEngine",
    ]

    enabled = True

    def __init__(self):

        super().__init__()

        self.sizer = PositionSizer()

        # Phase 4G STEP 8 (all-paths): SETUP_REJECTED
        # reason=INSUFFICIENT_RISK_WIDTH is logged once per
        # (fingerprint) per run here too, so a bad stop width
        # that slips past the builder cannot spam the log.
        self._logged_reject = set()

    # -------------------------------------------------

    def analyze(self, context):

        order_registry = getattr(
            context, "order_registry", None
        )

        # Phase 4D STEP 8: RiskEngine accepts the whole ranked
        # batch ExecutionEngine emitted (context.execution_signals)
        # and creates ONE order per setup, subject to:
        #   - the one-setup == one-order rule (registry re-check),
        #   - the pending-order budget (Phase 4F STEP 8: total AND
        #     per-direction caps), and
        #   - the MAX_TOTAL_EXPOSURE_PCT aggregate-notional ceiling
        #     against current equity.
        # The single legacy path (context.execution_signal only,
        # e.g. pre-pipeline scripts) degrades to a batch of one.
        signals = getattr(
            context, "execution_signals", None
        )

        if not signals:

            signal = context.execution_signal

            signals = [signal] if signal is not None else []

        account = context.account

        created = []

        # Stage 4 kill switch: mandatory for EVERY order. Active →
        # zero new orders (existing positions stay observable and
        # are managed downstream; only creation stops here).
        if kill_switch_active(account):
            log.error("KILL_SWITCH_ACTIVE no new orders sized")
            context.orders = None
            context.order = None
            return

        # Phase 12 loss-limit gate: roll the UTC calendar
        # windows from this candle's timestamp, then block ALL
        # new exposure while any window sits at/beyond its
        # configured loss allowance. Existing positions stay
        # observable and are managed downstream; only creation
        # stops here (same emergency posture as the kill
        # switch). A fresh account (all windows zero) passes
        # through unchanged.
        if account is not None:
            roll_state_pnl_windows(
                account,
                getattr(
                    getattr(context, "market", None),
                    "timestamp",
                    None,
                ),
            )

        loss_reason = loss_limit_blocked(account)

        if loss_reason is not None:
            log.error(
                "LOSS_LIMIT_ACTIVE reason=%s no new orders sized",
                loss_reason,
            )
            context.orders = None
            context.order = None
            return

        # Pending slots this candle: MAX_PENDING_ORDERS minus
        # unresolved orders already in the registry.
        pending = (
            order_registry.pending()
            if order_registry is not None
            else []
        )

        max_pending = pending_total_capacity()

        per_direction = pending_direction_capacity()

        exposure_pct = risk_settings.MAX_TOTAL_EXPOSURE_PCT

        pending_notional = sum(
            getattr(o, "position_value", 0.0) or 0.0
            for o in pending
        )

        for signal in signals:

            if len(created) + len(pending) >= max_pending:
                break

            # Phase 4F STEP 8: per-direction pending budget. The
            # pipeline funnels one symbol, so overlapping
            # same-direction exposure is the runaway case this cap
            # exists for (it binds before the total ever would).
            direction = (
                getattr(signal, "direction", "") or ""
            ).upper()

            live_direction = sum(
                1
                for o in pending + created
                if (o.direction or "").upper() == direction
            )

            if live_direction >= per_direction:

                log.info(
                    "ORDER_SKIPPED_DIRECTION_CAP setup_id=%s "
                    "direction=%s live=%s cap=%s",
                    getattr(signal, "setup_id", "") or "",
                    direction,
                    live_direction,
                    per_direction,
                )

                continue

            setup_id = getattr(signal, "setup_id", "") or ""

            # ---------------------------------------------
            # Phase 4G STEP 8 (all-paths): the ATR-based minimum
            # risk-width gate applies at EVERY chokepoint that could
            # mint an order -- even if a signal bypassed the builder
            # gate (defense-in-depth). A stop narrower than
            # MIN_RISK_WIDTH_ATR x ATR can never be ordered. The
            # signal's `atr` is the ATR_14 available at creation;
            # legacy OrderIntent signals carry no ATR axis and pass
            # through unchanged.
            # ---------------------------------------------

            sig_atr = float(getattr(signal, "atr", 0.0) or 0.0)

            if sig_atr > 0:

                sig_risk = abs(
                    float(getattr(signal, "entry", 0.0) or 0.0)
                    - float(getattr(signal, "stop_loss", 0.0) or 0.0)
                )

                min_width = float(
                    getattr(risk_settings, "MIN_RISK_WIDTH_ATR", 0.10)
                    or 0.10
                )

                if (
                    sig_risk <= 0
                    or (sig_risk / sig_atr) < min_width
                ):

                    sig_atr_risk = (
                        sig_risk / sig_atr if sig_atr > 0 else 0.0
                    )

                    label = REASON_LABELS.get(
                        REASON_INSUFFICIENT_RISK_WIDTH,
                        REASON_INSUFFICIENT_RISK_WIDTH,
                    )

                    fingerprint = getattr(
                        signal, "economic_fingerprint", ""
                    ) or setup_id

                    if fingerprint not in self._logged_reject:

                        self._logged_reject.add(fingerprint)

                        log.info(
                            "SETUP_REJECTED reason=%s setup_id=%s "
                            "direction=%s risk_distance=%.2f "
                            "risk_atr=%.4f minimum_required_risk_atr=%.4f "
                            "(%s)",
                            REASON_INSUFFICIENT_RISK_WIDTH,
                            setup_id,
                            direction,
                            sig_risk,
                            sig_atr_risk,
                            min_width,
                            label,
                        )

                    continue

            # Phase 4C belt-and-braces guard, immediately before
            # order creation: the persistent registry is the primary
            # source of truth. If one primary order already exists
            # for this setup, never create another -- regardless of
            # how many times ExecutionEngine emitted the signal.
            if (
                order_registry is not None
                and setup_id
                and order_registry.has_order_for_setup(setup_id)
            ):

                continue

            if account is None:

                context.order = None
                return

            balance = (
                account.equity
                if account.equity > 0
                else account.balance
            )

            if balance <= 0:

                context.order = None
                return

            position = self.sizer.calculate(
                balance=balance,
                entry_price=signal.entry,
                stop_price=signal.stop_loss,
                leverage=risk_settings.LEVERAGE,
                confidence=signal.confidence,
                regime=getattr(signal, "regime", None),
                drawdown=account.drawdown_percent,
            )

            if not position.valid:

                continue

            # Stage 1-3 hardening + Phase 12 directional
            # geometry: defense-in-depth RR revalidation.
            # DecisionEngine is the primary gate; RiskEngine
            # re-derives reward/risk from the SAME signal prices
            # against the SAME active minimum-R policy
            # (trading_policy, below) so a setup that bypasses
            # decision can never be sized into an order. Phase 12: abs()
            # RR math alone cannot see an inverted stop (LONG
            # stop >= entry) or a non-finite leg, so the
            # canonical geometry check runs FIRST -- a positive
            # ratio never proves a valid trade.
            symbol = str(getattr(getattr(context, "market", None), "symbol", "") or "")
            requested_exit_mode = getattr(signal, "exit_mode", risk_settings.EXIT_MODE_FIXED_TARGET)
            # Validate the authored target as a normal fixed-target plan
            # before attaching trailing management. This preserves target
            # directionality: a bullish target below entry can never become
            # valid merely because trailing management is enabled.
            exit_mode = requested_exit_mode
            if frozen_runtime_requested():
                # Frozen OOS replay semantics (Phase-14 era artifacts):
                # the runtime policy layer does not apply; the era gates
                # are enforced verbatim (4-arg directional geometry,
                # minimum-RR revalidation, trailing disabled). See
                # core/research/strategy_identity.py for the contract.
                policy = None
                trailing_enabled = False
                trailing_activation_r = 0.0
                trailing_distance_r = 0.0
                trailing_method = "R_DISTANCE"
                trailing_step_r = 0.0
                if not directional_geometry_ok(
                    direction,
                    getattr(signal, "entry", 0.0),
                    getattr(signal, "stop_loss", 0.0),
                    getattr(signal, "take_profit", 0.0),
                ):
                    log.info(
                        "ORDER_SKIPPED_GEOMETRY setup_id=%s "
                        "direction=%s entry=%s stop=%s target=%s",
                        setup_id,
                        direction,
                        getattr(signal, "entry", 0.0),
                        getattr(signal, "stop_loss", 0.0),
                        getattr(signal, "take_profit", 0.0),
                    )
                    continue
                rr_check = order_rr(
                    getattr(signal, "entry", 0.0),
                    getattr(signal, "stop_loss", 0.0),
                    getattr(signal, "take_profit", 0.0),
                )
                if rr_check is None or rr_check < FROZEN_ERA_MIN_RR:
                    log.info(
                        "ORDER_SKIPPED_RR setup_id=%s rr=%s min_rr=%.2f",
                        setup_id, rr_check, FROZEN_ERA_MIN_RR,
                    )
                    continue
            else:
                from core.risk.trading_policy import trading_policy
                policy = trading_policy(symbol)
                if not directional_geometry_ok(
                    direction,
                    getattr(signal, "entry", 0.0),
                    getattr(signal, "stop_loss", 0.0),
                    getattr(signal, "take_profit", 0.0),
                    exit_mode=exit_mode,
                ):
                    log.info(
                        "ORDER_SKIPPED_GEOMETRY setup_id=%s "
                        "direction=%s entry=%s stop=%s target=%s",
                        setup_id,
                        direction,
                        getattr(signal, "entry", 0.0),
                        getattr(signal, "stop_loss", 0.0),
                        getattr(signal, "take_profit", 0.0),
                    )
                    continue
                rr_check = order_rr(
                    getattr(signal, "entry", 0.0),
                    getattr(signal, "stop_loss", 0.0),
                    getattr(signal, "take_profit", 0.0),
                )
                if rr_check is None or not risk_reward_allowed(rr_check, exit_mode=risk_settings.EXIT_MODE_FIXED_TARGET, symbol=symbol):
                    log.info(
                        "ORDER_SKIPPED_RR setup_id=%s rr=%s min_rr=%.2f max_rr=%.2f",
                        setup_id, rr_check, policy.min_rr, policy.max_rr,
                    )
                    continue
                if policy.trailing_enabled and exit_mode == risk_settings.EXIT_MODE_FIXED_TARGET:
                    exit_mode = risk_settings.EXIT_MODE_TRAILING_STOP
                if exit_mode == risk_settings.EXIT_MODE_TRAILING_STOP:
                    if (not policy.trailing_enabled
                            or float(policy.trailing_activation_r) <= 0.0
                            or float(policy.trailing_distance_r) <= 0.0):
                        log.info("ORDER_SKIPPED_TRAILING_POLICY setup_id=%s", setup_id)
                        continue
                trailing_enabled = bool(policy.trailing_enabled)
                trailing_activation_r = float(policy.trailing_activation_r if policy.trailing_enabled else getattr(signal, "trailing_activation_r", 0.0) or 0.0)
                trailing_distance_r = float(policy.trailing_distance_r if policy.trailing_enabled else getattr(signal, "trailing_distance_r", 0.0) or 0.0)
                trailing_method = str(getattr(policy, "trailing_method", "R_DISTANCE") or "R_DISTANCE")
                trailing_step_r = float(getattr(policy, "trailing_step_r", 0.0) or 0.0)

            # Phase 4D STEP 8 exposure ceiling: aggregate unresolved
            # notional (existing + already created this candle) must
            # not exceed exposure_pct * equity.
            equity_for_cap = balance

            total_notional = (
                pending_notional
                + sum(
                    getattr(o, "position_value", 0.0) or 0.0
                    for o in created
                )
                + position.position_value
            )

            if total_notional > equity_for_cap * exposure_pct:

                log.info(
                    "ORDER_SKIPPED_EXPOSURE setup_id=%s "
                    "notional=%.2f cap=%.2f (pending + size "
                    "exceed MAX_TOTAL_EXPOSURE_PCT)",
                    setup_id,
                    total_notional,
                    equity_for_cap * exposure_pct,
                )

                continue

            commission, slippage = _production_costs().compute(
                position.position_value
            )

            expected_profit = (
                abs(signal.take_profit - signal.entry)
                * position.quantity
            )

            intent = OrderIntent(
                direction=signal.direction,
                entry=position.entry_price,
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit,
                # Never propagate a self-reported RR field into the
                # authoritative order.  RR is re-derived from entry/stop/target
                # above and validated against the selected runtime policy.
                risk_reward=rr_check,
                exit_mode=exit_mode,
                trailing_enabled=trailing_enabled,
                trailing_activation_r=trailing_activation_r,
                trailing_distance_r=trailing_distance_r,
                trailing_method=trailing_method,
                trailing_step_r=trailing_step_r,
                quantity=position.quantity,
                risk_percent=position.risk_percent,
                risk_amount=position.risk_amount,
                # 11E-Prep H1-D: the sizer's post-cap actual
                # risk travels on the intent so downstream
                # consumers see the final position's risk,
                # not the abandoned pre-cap request.
                actual_risk_percent=position.actual_risk_percent,
                expected_loss=position.expected_loss,
                expected_profit=expected_profit,
                position_value=position.position_value,
                leverage=position.leverage,
                commission=commission,
                slippage=slippage,
                confidence=signal.confidence,
                score=signal.score,
                symbol=context.market.symbol,
                timeframe=context.market.timeframe,
                setup_id=setup_id,
                # Phase 4E identity: the order inherits the
                # originating setup's structural id and its
                # tick-normalized economic fingerprint, so the
                # EconomicSetupRegistry can match a LIVE pending
                # order against new setups of the same idea.
                structural_id=getattr(
                    signal, "structural_id", ""
                ) or setup_id,
                economic_fingerprint=getattr(
                    signal, "economic_fingerprint", ""
                )
                or "",
                # Phase 4F: the entry model and its feasibility
                # class carried VERBATIM from the setup so the
                # order -> trade chain is sliceable by entry mode.
                entry_mode=getattr(
                    signal, "entry_mode", ""
                ) or "",
                # Phase 6C: the canonical setup identity carried
                # VERBATIM from the setup (never reconstructed, so
                # setup -> order -> trade see the same string).
                canonical_id=getattr(
                    signal, "canonical_id", ""
                ) or "",
                # Phase 5B: the order-execution channel for that
                # mode (EXECUTION_LIMIT except BREAKOUT_CONTINUATION
                # -> EXECUTION_NEXT_BAR_OPEN), so the backtester
                # knows how to fill it WITHOUT reading the mode
                # string. Defaults to LIMIT.
                entry_execution=execution_type_for(
                    getattr(signal, "entry_mode", "")
                ),
                entry_feasibility=getattr(
                    getattr(signal, "entry_feasibility", None),
                    "classification",
                    "",
                ) or "",
                valid=True,
                setup=signal,
            )

            # =====================================================
            # Phase 4C: canonical ORDER creation + signal emission.
            # The OrderRegistry is the only place an order_id is
            # minted and is the persistent source of truth: exactly
            # one ORDER_CREATED and one EXECUTION_SIGNAL per unique
            # setup_id, in the required ordinal sequence
            # (ORDER_CREATED then EXECUTION_SIGNAL, so the signal
            # always carries the order_id it is about). Phase 4D
            # STEP 2: the registry stamps the bar metadata from the
            # current replay bar + wall clock.
            # =====================================================

            bar = getattr(context, "current_index", None)

            if order_registry is not None:

                intent, order_id = order_registry.create(
                    intent,
                    bar=bar,
                    timestamp=getattr(
                        context.market, "timestamp", None
                    ),
                )

                intent.setup_id = setup_id

            else:

                intent.order_id = intent.order_id or ""

            log.info(
                "ORDER_CREATED setup_id=%s order_id=%s "
                "direction=%s entry=%.2f stop=%.2f target=%.2f "
                "comm=%.2f slip=%.2f",
                setup_id,
                intent.order_id,
                intent.direction,
                intent.entry,
                intent.stop_loss,
                intent.take_profit,
                intent.commission,
                intent.slippage,
            )

            log.info(
                "EXECUTION_SIGNAL setup_id=%s order_id=%s "
                "direction=%s entry=%.2f stop=%.2f target=%.2f "
                "rr=%.2f score=%.2f",
                setup_id,
                intent.order_id,
                intent.direction,
                intent.entry,
                intent.stop_loss,
                intent.take_profit,
                intent.risk_reward,
                intent.score,
            )

            # Setup lifecycle: an ordered setup is no longer
            # eligible for selection/emission.
            setup = getattr(signal, "lifecycle", None)

            if setup is not None:

                signal.lifecycle = (
                    "ORDER_CREATED"
                    if signal.lifecycle in ("NEW", "ACCEPTED", "")
                    else signal.lifecycle
                )

            created.append(intent)

        context.orders = created or None

        context.order = created[0] if created else None

    # -------------------------------------------------

    def reset(self):

        self._logged_reject.clear()