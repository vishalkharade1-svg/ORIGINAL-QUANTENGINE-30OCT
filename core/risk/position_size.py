"""
====================================================

Position Size Result

====================================================
"""

from dataclasses import dataclass


@dataclass(slots=True)
class PositionSize:

    # ==================================================
    # Account
    # ==================================================

    balance: float

    risk_percent: float

    risk_amount: float

    allocation: float

    leverage: float

    # ==================================================
    # Trade
    # ==================================================

    entry_price: float

    stop_price: float

    stop_distance: float

    quantity: float

    position_value: float

    expected_loss: float

    # ==================================================
    # Explicit 9Q-9: requested vs actual (allocation cap)
    # ==================================================

    requested_quantity: float = 0.0

    requested_position_value: float = 0.0

    requested_risk_amount: float = 0.0

    requested_risk_percent: float = 0.0

    actual_risk_percent: float = 0.0

    capped: bool = False

    cap_reason: str = ""

    # ==================================================
    # Status
    # ==================================================

    valid: bool = True

    reason: str = ""

    # --------------------------------------------------
    # Phase 4 verified correction: the take-profit leg needed
    # to express a true reward/risk ratio. Optional (0.0 =
    # undefined) so all existing constructions stay valid.
    # --------------------------------------------------

    target_price: float = 0.0

    # ==================================================

    @property
    def margin_required(self) -> float:

        if self.leverage <= 0:

            return 0.0

        return self.position_value / self.leverage

    # --------------------------------------------------

    @property
    def notional_to_risk(self) -> float:
        """Notional-at-risk multiple: position_value / expected_loss.

        Phase 4 verified correction: this is what the former
        ``risk_reward`` actually computed. It is NOT a reward/risk
        ratio and must never gate entries; use ``reward_to_risk``.
        """

        if self.expected_loss <= 0:

            return 0.0

        return self.position_value / self.expected_loss

    # --------------------------------------------------

    @property
    def reward_to_risk(self) -> float:
        """True reward/risk from entry/stop/target legs.

        Symmetric by construction (absolute distances): LONG and
        SHORT with mirrored legs yield the same ratio. Returns 0.0
        (never NaN/inf) when the target is undefined or the risk
        leg is unusable.
        """
        import math

        try:
            target = float(self.target_price)
            entry = float(self.entry_price)
            risk = abs(float(self.stop_distance))
        except (TypeError, ValueError):
            return 0.0
        if not (
            math.isfinite(target)
            and math.isfinite(entry)
            and math.isfinite(risk)
        ):
            return 0.0
        if target <= 0 or risk <= 0:
            return 0.0
        return abs(target - entry) / risk

    # --------------------------------------------------

    def __bool__(self):

        return self.valid