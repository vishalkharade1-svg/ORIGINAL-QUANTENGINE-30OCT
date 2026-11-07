"""
====================================================

Trade Setup Candidate

====================================================
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SetupCandidate:

    # -------------------------------------------------
    # Identity (Phase 4C)
    # -------------------------------------------------

    # Stable per-run identity composed by TradeSetupBuilder from
    # symbol, timeframe, direction, the originating order block's
    # index and the exact economics (entry/stop/target). Re-scan
    # of the SAME order block with the SAME economics reuses the
    # same setup_id, which is what makes "one setup == one order"
    # enforceable across bars.
    setup_id: str = ""

    # Phase 4E: the structural identity -- the same value as
    # setup_id, made explicit so an economic deduplication layer
    # can distinguish "same structural discovery" from "same
    # economic trade idea". Two different order-block structures
    # with identical economics share an economic_fingerprint but
    # never a structural_id.
    structural_id: str = ""

    # Phase 4E: the tick-normalized economic fingerprint (symbol,
    # timeframe, direction, entry/stop/target buckets), produced by
    # the TradeSetupBuilder. The EconomicSetupRegistry collapses
    # setups that share a fingerprint (identical trade economics)
    # and clusters near-identical ones within configurable
    # thresholds, so pending-order capacity is never consumed by
    # variants of one idea.
    economic_fingerprint: str = ""

    # Phase 6C: the canonical multi-symbol setup identity
    # ({exchange}:{instrument_id}:{timeframe}:{direction}:{strategy}:{setup_id}).
    # Built ONCE by TradeSetupBuilder at creation and carried
    # VERBATIM onto OrderIntent and Trade so the identity never
    # needs to be reconstructed downstream. Empty when the market
    # scope (exchange / instrument_id) is not present -- e.g.
    # legacy single-symbol harnesses that only set market.symbol.
    canonical_id: str = ""

    # Phase 4E deduplication bookkeeping: when this setup is an
    # economically-suppressed duplicate, is_economic_duplicate is
    # True and economic_canonical_id names the structural_id of the
    # canonical setup it was collapsed into. Cleared on the
    # canonical setup itself.
    is_economic_duplicate: bool = False

    economic_canonical_id: str = ""

    # Bar at which the setup was last observed by the
    # EconomicSetupRegistry (canonical-selection tie-break: newest
    # valid structural state wins).
    observed_bar: int = 0

    # Phase 4F re-entry cooldown bookkeeping (EconomicSetupRegistry):
    # True when this structurally-fresh discovery of an economic
    # fingerprint that was just EXPIRED / INVALIDATED had to wait out
    # its REENTRY_COOLDOWN_BARS. The count of suppressed re-discoveries
    # tics the registry's reentry_cooldown_suppressed summary.
    reentry_cooldown_suppressed: bool = False

    # -------------------------------------------------
    # Structural Freshness & Entry Eligibility (Phase 4G)
    # -------------------------------------------------

    # Step 7: structural validity and trade eligibility are
    # SEPARATE axes. A zone can remain structurally valid
    # (not invalidated / not mitigated) while being INELIGIBLE
    # to trade (stale, too far from market, too thin a stop).
    structurally_valid: bool = True

    trade_eligible: bool = True

    # Primary blocking reason when trade_eligible is False
    # (Phase 4G taxonomy): STALE_ZONE, TOO_FAR_FROM_MARKET,
    # ALREADY_MITIGATED, INVALIDATED_STRUCTURE,
    # INSUFFICIENT_RISK_WIDTH. "" when eligible.
    entry_rejection_reason: str = ""

    # Measured but non-blocking notes the decision should never
    # act on this phase: WEAK_DISPLACEMENT / TOO_MANY_TOUCHES.
    zone_diagnostics: list[str] = field(default_factory=list)

    # Zone-age snapshot at creation (diagnostic, at-creation only).
    zone_age_bars: int = 0

    zone_freshness: str = "FRESH"

    zone_distance: float = 0.0

    zone_distance_atr: float = 0.0

    # Structural-cluster identity (STEP 9/10): which cluster the
    # zone belongs to this candle and whether it is the canonical
    # representative. Only canonical zones mint setups.
    zone_cluster_id: str = ""

    zone_canonical_zone_id: str = ""

    zone_is_canonical: bool = True

    # -------------------------------------------------
    # Entry Feasibility (Phase 4F)
    # -------------------------------------------------

    # The explicit entry mode this setup enters with (Phase 4F
    # STEP 6). Default LIMIT_RETEST; carried verbatim onto the
    # OrderIntent and the Trade so the entry model is a first-class
    # value on every hop of the setup -> order -> trade chain.
    entry_mode: str = ""

    # Market snapshot at build time: the price that PRODUCED the
    # setup (creating candle close) and the ATR_14 available then.
    # 0.0 in a scripted harness with no indicator stack.
    observed_price: float = 0.0

    atr: float = 0.0

    # Point-in-time feasibility measurement (Phase 4F STEP 1-2):
    # an EntryFeasibility snapshot with the four distance axes
    # (absolute / percent of price / ATR multiples / ticks) and the
    # classification. Stamped by TradeSetupBuilder; consumed by the
    # EntryTracker.
    entry_feasibility: Any = None

    # Setup lifecycle (Step 6 of Phase 4C): NEW -> ACCEPTED ->
    # ORDER_CREATED -> FILLED -> CLOSED, or -> INVALIDATED /
    # EXPIRED. Stored on the setup itself, distinct from order
    # status and trade status.
    lifecycle: str = "NEW"

    # -------------------------------------------------
    # Trade
    # -------------------------------------------------

    direction: str = ""

    entry: float = 0.0

    stop_loss: float = 0.0

    take_profit: float = 0.0

    risk_reward: float = 0.0

    # Exit policy: fixed target or explicitly provisioned trailing stop.
    exit_mode: str = "FIXED_TARGET"
    trailing_activation_r: float = 0.0
    trailing_distance_r: float = 0.0
    trailing_enabled: bool = False

    # -------------------------------------------------
    # Scores
    # -------------------------------------------------

    confidence: float = 0.0

    score: float = 0.0

    quality_score: float = 0.0

    # A calibrated win probability is deliberately distinct from the
    # heuristic score/confidence fields above. None means no calibrated model
    # and must never be rendered or consumed as a percentage probability.
    calibrated_probability: float | None = None

    # -------------------------------------------------
    # Market Context
    # -------------------------------------------------

    trend: Any = None

    regime: Any = None

    liquidity: Any = None

    confluence: Any = None

    # -------------------------------------------------
    # Smart Money
    # -------------------------------------------------

    order_block: Any = None

    fvg: Any = None

    breaker: Any = None

    mitigation: Any = None

    # -------------------------------------------------
    # Future Institutional Modules
    # -------------------------------------------------

    footprint: Any = None

    cumulative_delta: Any = None

    volume_profile: Any = None

    market_profile: Any = None

    fibonacci: Any = None

    gann: Any = None

    wyckoff: Any = None

    ict: Any = None

    ai_analysis: Any = None

    # -------------------------------------------------
    # Diagnostics
    # -------------------------------------------------

    checks: dict = field(default_factory=dict)

    validation_errors: list[str] = field(
        default_factory=list
    )

    metadata: dict = field(
        default_factory=dict
    )

    # -------------------------------------------------

    @property
    def valid(self):

        return len(self.validation_errors) == 0

    # -------------------------------------------------

    @property
    def expected_reward(self):

        return abs(
            self.take_profit - self.entry
        )

    # -------------------------------------------------

    @property
    def expected_risk(self):

        return abs(
            self.entry - self.stop_loss
        )

    # -------------------------------------------------

    def add_validation_error(
        self,
        message: str,
    ):

        if message not in self.validation_errors:
            self.validation_errors.append(message)
