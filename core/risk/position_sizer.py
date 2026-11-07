"""
====================================================

QuantEngine

Institutional Position Sizer

====================================================
"""

from config import risk_settings

from core.risk.position_size import PositionSize

import math


class PositionSizer:
    """
    Institutional Position Sizer.

    Features
    --------
    • Fixed fractional risk
    • Confidence adjustment
    • Market regime adjustment
    • Drawdown protection
    • Allocation cap (NOTIONAL: position value capped at
      MAX_ALLOCATION_PER_TRADE, independent of leverage)
    • Leverage support
    • AI optimization hook

    Numeric policy (11E-Prep C1): non-finite inputs (NaN,
    +Inf, -Inf) fail closed to valid=False with zero
    quantity — they can never become an executable size.
    """

    # -------------------------------------------------

    def calculate(

        self,

        balance: float,

        entry_price: float,

        stop_price: float,

        leverage: float = 10.0,

        confidence: float = 100.0,

        regime=None,

        drawdown: float = 0.0,

        risk_multiplier: float = 1.0,

    ) -> PositionSize:

        # ==================================================
        # Validation — fail closed on non-finite numerics
        # (11E-Prep C1-A). NaN/Inf comparisons are False, so
        # every bound below must be preceded by an explicit
        # finiteness check; otherwise non-finite inputs flow
        # into arithmetic and emerge as valid NaN quantities.
        # ==================================================

        if not math.isfinite(balance):

            return PositionSize(

                balance=0.0,

                risk_percent=0,

                risk_amount=0,

                allocation=0,

                leverage=leverage,

                entry_price=entry_price,

                stop_price=stop_price,

                stop_distance=0,

                quantity=0,

                position_value=0,

                expected_loss=0,

                valid=False,

                reason="Non-finite account balance",

            )

        if balance <= 0:

            return PositionSize(

                balance=balance,

                risk_percent=0,

                risk_amount=0,

                allocation=0,

                leverage=leverage,

                entry_price=entry_price,

                stop_price=stop_price,

                stop_distance=0,

                quantity=0,

                position_value=0,

                expected_loss=0,

                valid=False,

                reason="Invalid account balance",

            )

        if not math.isfinite(entry_price):

            return PositionSize(

                balance=balance,

                risk_percent=0,

                risk_amount=0,

                allocation=0,

                leverage=leverage,

                entry_price=0.0,

                stop_price=stop_price,

                stop_distance=0,

                quantity=0,

                position_value=0,

                expected_loss=0,

                valid=False,

                reason="Non-finite entry price",

            )

        if entry_price <= 0:

            return PositionSize(

                balance=balance,

                risk_percent=0,

                risk_amount=0,

                allocation=0,

                leverage=leverage,

                entry_price=entry_price,

                stop_price=stop_price,

                stop_distance=0,

                quantity=0,

                position_value=0,

                expected_loss=0,

                valid=False,

                reason="Invalid entry price",

            )

        if not math.isfinite(leverage) or leverage <= 0:

            leverage = 1.0

        # ==================================================
        # Base Risk
        # ==================================================

        risk_percent = risk_settings.RISK_PER_TRADE

        # ==================================================
        # Confidence Scaling — finite input required
        # (11E-Prep C1-A). max()/min() below would silently
        # launder NaN to a finite bound, so check first.
        # ==================================================

        if not math.isfinite(confidence):

            return PositionSize(

                balance=balance,

                risk_percent=0,

                risk_amount=0,

                allocation=0,

                leverage=leverage,

                entry_price=entry_price,

                stop_price=stop_price,

                stop_distance=0,

                quantity=0,

                position_value=0,

                expected_loss=0,

                valid=False,

                reason="Non-finite confidence",

            )

        confidence = max(

            0.0,

            min(

                confidence,

                100.0,

            ),

        )

        confidence_factor = (

            0.50

            + (confidence / 100.0) * 0.50

        )

        risk_percent *= confidence_factor

        # ==================================================
        # Market Regime
        # ==================================================

        if regime is not None:

            regime_name = getattr(

                regime,

                "regime",

                "",

            )

            if regime_name == "RANGING":

                risk_percent *= 0.75

            elif regime_name == "HIGH_VOLATILITY":

                risk_percent *= 0.60

            elif regime_name == "LOW_VOLATILITY":

                risk_percent *= 0.90

        # ==================================================
        # Drawdown Protection — finite input required
        # (11E-Prep C1-A). NaN comparisons are all False, so
        # a NaN drawdown would silently skip protection and
        # size at full risk.
        # ==================================================

        if not math.isfinite(drawdown):

            return PositionSize(

                balance=balance,

                risk_percent=0,

                risk_amount=0,

                allocation=0,

                leverage=leverage,

                entry_price=entry_price,

                stop_price=stop_price,

                stop_distance=0,

                quantity=0,

                position_value=0,

                expected_loss=0,

                valid=False,

                reason="Non-finite drawdown",

            )

        if drawdown >= 30:

            risk_percent *= 0.25

        elif drawdown >= 20:

            risk_percent *= 0.50

        elif drawdown >= 10:

            risk_percent *= 0.75

        # ==================================================
        # AI Optimizer Hook
        # ==================================================

        risk_percent *= risk_multiplier

        # Single choke point for every upstream scaling factor
        # (confidence, regime, drawdown, risk_multiplier): any
        # non-finite factor poisons risk_percent. This check
        # MUST precede the max/min clamp below — min/max with
        # NaN silently launder it to a finite value (e.g. NaN
        # confidence would otherwise become minimum risk).
        if not math.isfinite(risk_percent):

            return PositionSize(

                balance=balance,

                risk_percent=0,

                risk_amount=0,

                allocation=0,

                leverage=leverage,

                entry_price=entry_price,

                stop_price=stop_price,

                stop_distance=0,

                quantity=0,

                position_value=0,

                expected_loss=0,

                valid=False,

                reason="Non-finite risk percent",

            )

        risk_percent = max(

            0.001,

            min(

                risk_percent,

                risk_settings.RISK_PER_TRADE,

            ),

        )

        # ==================================================
        # Risk Amount
        # ==================================================

        risk_amount = balance * risk_percent

        allocation = min(

            balance,

            risk_settings.MAX_ALLOCATION_PER_TRADE,

        )

        stop_distance = abs(

            entry_price - stop_price

        )

        if not math.isfinite(stop_price) or not math.isfinite(
            stop_distance
        ):

            return PositionSize(

                balance=balance,

                risk_percent=risk_percent,

                risk_amount=0,

                allocation=allocation,

                leverage=leverage,

                entry_price=entry_price,

                stop_price=0.0,

                stop_distance=0,

                quantity=0,

                position_value=0,

                expected_loss=0,

                valid=False,

                reason="Non-finite stop price",

            )

        if stop_distance <= 0:

            return PositionSize(

                balance=balance,

                risk_percent=risk_percent,

                risk_amount=risk_amount,

                allocation=allocation,

                leverage=leverage,

                entry_price=entry_price,

                stop_price=stop_price,

                stop_distance=0,

                quantity=0,

                position_value=0,

                expected_loss=0,

                valid=False,

                reason="Stop distance must be greater than zero",

            )

        # ==================================================
        # Position Size
        # ==================================================

        quantity = risk_amount / stop_distance

        position_value = quantity * entry_price

        # 9Q-9: Preserve requested values before any cap
        requested_quantity = quantity
        requested_position_value = position_value
        requested_risk_amount = risk_amount
        requested_risk_percent = risk_percent
        capped = False
        cap_reason = ""

        # ==================================================
        # Allocation Cap — explicit, never silent (11E-Prep
        # H1). MAX_ALLOCATION_PER_TRADE is a NOTIONAL cap
        # (maximum position value, quote currency), matching
        # PositionManager.max_quantity/audit ("notional
        # limit"). It is intentionally independent of
        # leverage: leverage scales margin, never the cap.
        # ==================================================

        if position_value > allocation:

            scale = allocation / position_value

            quantity *= scale

            position_value = allocation

            capped = True
            cap_reason = f"allocation cap: notional {requested_position_value:.2f} > {allocation:.2f}, scaled {scale:.4f}"

        expected_loss = quantity * stop_distance

        # If the allocation cap scaled the position down, the
        # actual risk taken is now smaller than balance *
        # risk_percent. Reporting the unscaled risk_amount
        # overstates what is on the line, so align all three
        # metrics with the scaled expected loss.
        actual_risk_percent = risk_percent
        if capped or round(expected_loss, 10) < round(balance * risk_percent, 10):

            risk_amount = expected_loss

            actual_risk_percent = (
                (expected_loss / balance)
                if balance > 0
                else 0.0
            )
            if not capped:
                cap_reason = "risk_amount aligned to expected_loss"
        else:
            actual_risk_percent = risk_percent

        # ==================================================

        return PositionSize(

            balance=balance,

            risk_percent=risk_percent,

            risk_amount=risk_amount,

            allocation=allocation,

            leverage=leverage,

            entry_price=entry_price,

            stop_price=stop_price,

            stop_distance=stop_distance,

            quantity=quantity,

            position_value=position_value,

            expected_loss=expected_loss,

            requested_quantity=requested_quantity,

            requested_position_value=requested_position_value,

            requested_risk_amount=requested_risk_amount,

            requested_risk_percent=requested_risk_percent,

            actual_risk_percent=actual_risk_percent,

            capped=capped,

            cap_reason=cap_reason,

            valid=True,

        )