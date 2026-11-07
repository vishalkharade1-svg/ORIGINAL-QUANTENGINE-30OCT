"""
====================================================

Institutional Decision Engine

Pipeline Native

Consumes:
    context.trade_setups

Produces:
    context.decision

====================================================
"""

from core.common.base_engine import BaseEngine
from core.common.logging_config import get_logger

from config import risk_settings

from core.order_blocks.zone_freshness import (
    REASON_LABELS,
)
from core.setup.trade_setup_registry import TradeSetupRegistry
from core.setup.setup_rejection import SetupRejection
from core.backtesting.accounting import risk_reward_allowed
from core.research.strategy_identity import (
    FROZEN_ERA_MIN_RR,
    frozen_runtime_requested,
)

log = get_logger(__name__)


class DecisionEngine(BaseEngine):

    priority = 700

    dependencies = [
        "TradeSetupBuilder",
    ]

    enabled = True

    MIN_REGIME_SCORE = 70
    # No MIN_CONFIDENCE shadow here (Phase 4 verified correction): the
    # authoritative threshold lives ONLY in config MIN_CONFIDENCE (80)
    # and is read per analysis below. A setup with confidence < 80 is
    # rejected deterministically.
    # No MIN_RISK_REWARD shadow here (Stage 1-3 hardening): no
    # class-level threshold. Level-3 research remains frozen at 1:6
    # (research artifact only; runtime trading uses the central
    # risk_reward_allowed() policy (1:1..1:20 or
    # explicitly enabled trailing stop).

    def __init__(self):

        super().__init__()

        self.accepted = TradeSetupRegistry()

        self.rejected = []

        # Phase 4C: which setup_ids have had their one
        # SETUP_ACCEPTED event logged this run. Cleared on
        # reset() so a fresh run can accept the same setup again.
        self._logged_accept = set()

        # Phase 4G: which (reason, fingerprint) pairs have had a
        # SETUP_REJECTED logged (trade-ineligible candidates).
        # Deduplicated so the drifting re-derivations of one bad
        # zone cannot spam the log. Cleared on reset().
        self._logged_reject = set()

    # ==================================================

    def analyze(self, context):

        self.accepted.clear()

        self.rejected.clear()

        candidates = context.trade_setups or []

        for candidate in candidates:

            reject = SetupRejection()

            reject.direction = candidate.direction

            reject.candidate = candidate

            quality = 100

            # -------------------------------------------------
            # Phase 4G STEP 4 / 7: a structurally trade-INELIGIBLE
            # candidate is rejected outright -- a stale / too-far /
            # mitigated / invalidated / too-thin zone may never be
            # accepted regardless of confidence, regime or reward-
            # risk. The explicit reason travels to the report.
            # -------------------------------------------------

            reason = (
                getattr(candidate, "entry_rejection_reason", "")
                or ""
            )

            if (
                getattr(candidate, "trade_eligible", True) is False
                and reason
            ):

                label = REASON_LABELS.get(reason, reason)

                reject.add(label)

                quality = 0

                candidate.quality_score = 0

                fingerprint = getattr(
                    candidate, "economic_fingerprint", ""
                ) or reason

                dedup_key = (reason, fingerprint)

                if (
                    candidate.setup_id
                    and dedup_key not in self._logged_reject
                ):

                    self._logged_reject.add(dedup_key)

                    log.info(
                        "SETUP_REJECTED reason=%s setup_id=%s "
                        "direction=%s zone_age_bars=%d "
                        "zone_freshness=%s (%s)",
                        reason,
                        candidate.setup_id,
                        candidate.direction,
                        getattr(candidate, "zone_age_bars", 0)
                        or 0,
                        getattr(candidate, "zone_freshness", "")
                        or "FRESH",
                        label,
                    )

                self.rejected.append(reject)

                continue

            # -------------------------------------------------
            # Trend Alignment
            # -------------------------------------------------

            trend = getattr(candidate, "trend", None)

            if trend is None:

                reject.add("Missing Trend")

                quality -= 30

            elif trend.direction != candidate.direction:

                reject.add("Trend Filter")

                quality -= 30

            # -------------------------------------------------
            # Market Regime
            # -------------------------------------------------

            regime = getattr(candidate, "regime", None)

            if regime is None:

                reject.add("Missing Regime")

                quality -= 20

            elif regime.score < self.MIN_REGIME_SCORE:

                reject.add("Weak Market")

                quality -= (
                    self.MIN_REGIME_SCORE - regime.score
                )

            # -------------------------------------------------
            # Risk Reward
            # -------------------------------------------------

            rr = getattr(candidate, "risk_reward", 0)
            symbol = getattr(getattr(context, "market", None), "symbol", "")
            exit_mode = getattr(candidate, "exit_mode", risk_settings.EXIT_MODE_FIXED_TARGET)

            if frozen_runtime_requested():
                # Frozen OOS replay semantics (Phase-14 era artifacts):
                # the runtime policy layer does not apply; the era RR
                # gate is enforced verbatim. See
                # core/research/strategy_identity.py for the contract.
                if rr < FROZEN_ERA_MIN_RR:
                    reject.add("Risk Reward")

                    quality -= 20
            else:
                from core.risk.trading_policy import trading_policy
                policy = trading_policy(symbol)

                if exit_mode == risk_settings.EXIT_MODE_TRAILING_STOP:
                    if not policy.trailing_enabled:
                        reject.add("Trailing Stop Disabled")
                        quality -= 20
                    elif not risk_reward_allowed(rr, exit_mode=exit_mode, symbol=symbol) and not (getattr(candidate, "stop_loss", 0.0) and getattr(candidate, "entry", 0.0)):
                        reject.add("Trailing Stop Geometry")
                        quality -= 20
                elif not risk_reward_allowed(rr, exit_mode=exit_mode, symbol=symbol):
                    reject.add("Risk Reward")

                    quality -= 20

            # -------------------------------------------------
            # Confidence
            # -------------------------------------------------

            confidence = getattr(candidate, "confidence", 0)

            if confidence < risk_settings.MIN_CONFIDENCE:

                reject.add("Confidence")

                quality -= (
                    risk_settings.MIN_CONFIDENCE - confidence
                ) * 0.5

            # -------------------------------------------------
            # Future Validators
            # -------------------------------------------------

            extra_errors = getattr(

                candidate,

                "validation_errors",

                None,

            )

            if extra_errors:

                for error in extra_errors:

                    reject.add(error)

                    quality -= 5

            # -------------------------------------------------

            quality = max(0, min(100, int(quality)))

            candidate.quality_score = quality

            if reject.reasons:

                self.rejected.append(reject)

            else:

                candidate.lifecycle = "ACCEPTED"

                self.accepted.add(candidate)

                # One SETUP_ACCEPTED event per setup_id per run
                # (Phase 4C acceptance criterion max = 1).
                if candidate.setup_id and (
                    candidate.setup_id not in self._logged_accept
                ):

                    self._logged_accept.add(candidate.setup_id)

                    log.info(
                        "SETUP_ACCEPTED setup_id=%s direction=%s "
                        "entry=%.2f stop=%.2f target=%.2f",
                        candidate.setup_id,
                        candidate.direction,
                        candidate.entry,
                        candidate.stop_loss,
                        candidate.take_profit,
                    )

        context.decision = self.accepted

    # ==================================================

    @property
    def acceptance_rate(self):

        total = len(self.accepted) + len(self.rejected)

        if total == 0:

            return 0.0

        return (len(self.accepted) / total) * 100

    # -------------------------------------------------

    @property
    def rejection_rate(self):

        total = len(self.accepted) + len(self.rejected)

        if total == 0:

            return 0.0

        return (len(self.rejected) / total) * 100

    # ==================================================

    def reset(self):

        self.accepted.clear()

        self.rejected.clear()

        self._logged_accept.clear()

        self._logged_reject.clear()