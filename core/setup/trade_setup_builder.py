"""
====================================================

Institutional Trade Setup Builder

Pipeline Native

Consumes:
    context.trend
    context.regime
    context.order_blocks
    context.liquidity_target
    context.fvgs

Produces:
    context.trade_setups

====================================================
"""

from config import risk_settings

from core.backtesting.accounting import directional_geometry_ok
from core.common.base_engine import BaseEngine
from core.common.logging_config import get_logger
from core.execution.entry_mode import select_entry_mode
from core.identity.instrument_identity import build_setup_identity
from core.order_blocks.zone_freshness import (
    cluster_structural_zones,
    evaluate_entry_eligibility,
    REASON_INSUFFICIENT_RISK_WIDTH,
    REASON_LABELS,
)
from core.setup.economic_setup_registry import fingerprint_of
from core.setup.entry_feasibility import create_entry_feasibility
from core.setup.setup_candidate import SetupCandidate

log = get_logger(__name__)


def _latest_atr(context):
    """
    ATR_14 from the canonical IndicatorCache when one is published
    (InstitutionalPipeline installs it). 0.0 in a scripted harness
    with no indicator stack -- the feasibility snapshot then falls
    back to percentage/tick normalization and the ATR axis stays 0.
    """

    indicators = getattr(context, "indicators", None)

    if indicators is None:

        return 0.0

    try:

        return float(indicators.latest("ATR_14") or 0.0)

    except Exception:

        return 0.0


class TradeSetupBuilder(BaseEngine):

    priority = 600

    dependencies = [
        "RegimeEngine",
        "OrderBlockScanner",
        "LiquidityTargetEngine",
    ]

    enabled = True

    def __init__(self):

        super().__init__()

        # SETUP_REJECTED reason=INSUFFICIENT_RISK_WIDTH is logged
        # once per (reason, economic fingerprint) per run, so the
        # drifting re-derivations of one bad zone cannot spam the
        # log. Cleared on reset().
        self._logged_min_risk = set()

    # ==================================================

    def analyze(self, context):

        trend = context.trend
        regime = context.regime
        order_blocks = context.order_blocks
        liquidity_target = context.liquidity_target
        fvg_registry = context.fvgs

        candidates = []

        if (
            trend is None
            or regime is None
            or order_blocks is None
            or liquidity_target is None
        ):

            context.trade_setups = candidates
            return

        atr = _latest_atr(context)

        bar = getattr(context, "current_index", 0)

        elig_log = getattr(context, "zone_eligibility", None)

        shadow = getattr(context, "entry_shadow", None)

        validation = getattr(context, "causal_validation", None)

        active_blocks = order_blocks.active()

        # ------------------------------------------------
        # Phase 4G STEP 9/10: structural zone clustering BEFORE
        # setup generation. Overlapping duplicate zones of the SAME
        # candle collapse to ONE canonical zone: identical-duplicate
        # re-derivations (the OB-791..796 family sharing entry/stop/
        # target) can never each mint a candidate. Non-canonical
        # zones are flagged for the eligibility report and never
        # produce a setup.
        # ------------------------------------------------

        clustering = bool(
            getattr(risk_settings, "ENABLE_STRUCTURAL_CLUSTERING", True)
        )

        non_canonical = 0

        if clustering and active_blocks:

            clusters, non_canonical = cluster_structural_zones(
                active_blocks,
                atr=atr,
            )

            if elig_log is not None and non_canonical:

                elig_log.note_structurally_suppressed(non_canonical)

        block_source = [
            block for block in active_blocks
            if block.is_canonical
        ]

        for block in block_source:

            if block.direction == "BULLISH":

                entry = block.high
                stop = block.low

            else:

                entry = block.low
                stop = block.high

            # Phase 12 directional geometry: an inverted
            # stop (LONG stop >= entry, SHORT stop <= entry)
            # hides behind abs() RR math and becomes a
            # deterministic instant loss. Reject before any
            # economics are computed. Well-formed blocks are
            # unaffected (strict ordering already holds).
            risk = abs(entry - stop)

            if risk <= 0:
                continue

            target = liquidity_target.price

            if not directional_geometry_ok(
                block.direction, entry, stop, target
            ):
                continue

            # A take-profit must sit on the profitable side of
            # the entry. LiquidityTargetEngine picks a *single*
            # best pool, which can be BUY-side (above price,
            # a bull target) or SELL-side (below price, a bear
            # target), so a BULLISH block can legally receive a
            # SELL-side target. Before, that produced setups
            # whose take_profit was below the entry while the
            # absolute-value reward/risk stayed positive -- the
            # DecisionEngine accepted them and the simulator
            # closed them as negative-PnL "WINS" (high >= TP
            # with TP < entry). Both side conditions must hold.
            if block.direction == "BULLISH":

                if target <= entry:
                    continue

            else:

                if target >= entry:
                    continue

            reward = abs(target - entry)

            rr = reward / risk

            candidate = SetupCandidate(

                direction=block.direction,

                entry=entry,

                stop_loss=stop,

                take_profit=target,

                risk_reward=rr,

                confidence=block.score,

                score=block.score,

            )

            # Phase 4C identity: the setup_id is the intersection
            # of the ORDER BLOCK index (stable across bars) and
            # the exact economics. Re-scanning the same block
            # with the same prices reuses the id, so the one-setup
            # == one-order enforcement works; a genuinely different
            # setup gets its own id.
            candidate.setup_id = "{}-{}-{}-OB-{}-{:.2f}-{:.2f}-{:.2f}".format(
                context.market.symbol,
                context.market.timeframe,
                block.direction,
                block.index,
                entry,
                stop,
                target,
            )

            # Phase 4E: structural_id is the canonical structural
            # identity (== setup_id, made explicit); the economic
            # fingerprint is the tick-normalized trade economics,
            # which two DIFFERENT order blocks with the SAME
            # market idea share -- the EconomicSetupRegistry's
            # second dedup layer keys on it, so economically
            # identical variants never both reach RiskEngine.
            candidate.structural_id = candidate.setup_id

            candidate.economic_fingerprint = fingerprint_of(
                candidate,
                symbol=context.market.symbol,
                timeframe=context.market.timeframe,
            )

            # ------------------------------------------------
            # Phase 4G STEP 1-4 / 7: stamp the zone's at-creation
            # freshness snapshot + structural/trade-eligibility
            # split onto the candidate. Everything here is data
            # available at the creating candle -- no future bars.
            # ------------------------------------------------

            candidate.zone_age_bars = int(
                getattr(block, "age_bars", 0) or 0
            )

            candidate.zone_freshness = (
                getattr(block, "freshness", "") or "FRESH"
            )

            candidate.zone_distance = float(
                getattr(block, "distance_from_current_price", 0.0) or 0.0
            )

            candidate.zone_distance_atr = float(
                getattr(block, "distance_from_current_price_atr", 0.0)
                or 0.0
            )

            candidate.zone_cluster_id = (
                getattr(block, "cluster_id", "") or ""
            )

            candidate.zone_canonical_zone_id = (
                getattr(block, "canonical_zone_id", "") or ""
            )

            candidate.zone_is_canonical = bool(
                getattr(block, "is_canonical", True)
            )

            (
                candidate.structurally_valid,
                candidate.trade_eligible,
                candidate.entry_rejection_reason,
                candidate.zone_diagnostics,
            ) = evaluate_entry_eligibility(block, candidate, atr)

            if (
                candidate.entry_rejection_reason
                == REASON_INSUFFICIENT_RISK_WIDTH
            ):

                risk_atr = (
                    risk / atr if atr and atr > 0 else 0.0
                )

                min_atr = float(
                    getattr(risk_settings, "MIN_RISK_WIDTH_ATR", 0.10)
                    or 0.10
                )

                dedup_key = (
                    REASON_INSUFFICIENT_RISK_WIDTH,
                    candidate.economic_fingerprint,
                )

                if dedup_key not in self._logged_min_risk:

                    self._logged_min_risk.add(dedup_key)

                    # SETUP_REJECTED reason=INSUFFICIENT_RISK_WIDTH
                    # (Phase 4G STEP 8): logged once per
                    # (reason, fingerprint) per run on the builder
                    # path, with the risk-width audit numbers.
                    log.info(
                        "SETUP_REJECTED reason=%s structural_id=%s "
                        "direction=%s risk_distance=%.2f "
                        "risk_atr=%.4f minimum_required_risk_atr=%.4f "
                        "(%s)",
                        REASON_INSUFFICIENT_RISK_WIDTH,
                        candidate.structural_id,
                        candidate.direction,
                        risk,
                        risk_atr,
                        min_atr,
                        REASON_LABELS.get(
                            REASON_INSUFFICIENT_RISK_WIDTH,
                            REASON_INSUFFICIENT_RISK_WIDTH,
                        ),
                    )

            # Phase 4F entry feasibility (STEP 1-2): the market
            # price that produced the setup, the ATR then available,
            # the explicit entry mode, and the four-distance-axis
            # feasibility snapshot. All DIAGNOSTIC: they travel on
            # the candidate -> order -> trade chain and feed the
            # EntryTracker, but never influence accept/avoid.
            candidate.observed_price = float(
                getattr(context.market, "mark_price", 0.0) or 0.0
            )

            candidate.atr = _latest_atr(context)

            candidate.entry_mode = select_entry_mode(candidate)

            # Phase 6C: build the canonical setup identity ONCE at
            # setup creation and stamp it so the exact same string
            # flows unchanged through Decision -> OrderIntent ->
            # Trade -> Registry. Only built when the market scope
            # names an exchange + instrument_id (the scanner/
            # discovery path); legacy single-symbol harnesses keep
            # canonical_id "" and are byte-identical to before.
            exchange = getattr(
                context.market, "exchange", ""
            )

            instrument_id = getattr(
                context.market, "instrument_id", ""
            )

            if exchange and instrument_id:
                candidate.canonical_id = build_setup_identity(
                    exchange=exchange,
                    instrument_id=instrument_id,
                    timeframe=context.market.timeframe,
                    direction=candidate.direction,
                    strategy=candidate.entry_mode,
                    setup_id=candidate.setup_id,
                )

            candidate.entry_feasibility = create_entry_feasibility(
                candidate,
                creation_price=candidate.observed_price,
                atr=candidate.atr,
                creation_bar=getattr(
                    context, "current_index", 0
                ),
            )

            candidate.trend = trend
            candidate.regime = regime

            candidate.order_block = block
            candidate.liquidity = liquidity_target

            if fvg_registry:

                active = [

                    f

                    for f in fvg_registry.active()

                    if f.direction == block.direction

                ]

                if active:

                    candidate.fvg = active[-1]

                    candidate.score += 3

            candidate.score = round(

                min(candidate.score, 100),

                2,

            )

            candidate.confidence = round(

                min(candidate.confidence, 100),

                2,

            )

            candidates.append(candidate)

            # Phase 4G eligibility log: record the canonical zone's
            # at-creation statement on its FIRST appearance (the
            # same dedup rule the EntryTracker uses, so the report
            # population is comparable to Phase 4F's tracked count).
            # Recorded whether eligible or not -- the whole POINT is
            # to count the rejections. Read-only: never a signal.
            if elig_log is not None:

                elig_log.observe(
                    candidate,
                    bar,
                )

            # Phase 4G extension entry shadow: capture every TRADE-ELIGIBLE
            # canonical candidate (the same population the eligibility
            # gate defined in Phase 4G) for the three-model entry
            # reachability comparison. The observe() itself filters to
            # trade-eligible candidates and deduplicates on first
            # appearance per structural_id. DIAGNOSTIC ONLY -- never
            # a signal, gated on ENABLE_ENTRY_SHADOW.
            if shadow is not None:

                shadow.observe(
                    candidate,
                    bar,
                )

            # Phase 4H causal validation: capture every TRADE-ELIGIBLE
            # canonical candidate (the same Phase 4G population) for the
            # CausalValidator. The observe() freezes the candidate
            # (RULE 1), filters to trade-eligible, deduplicates on first
            # appearance per structural_id, and self-gates on
            # ENABLE_CAUSAL_VALIDATION. DIAGNOSTIC ONLY -- never a
            # signal, produces no order.
            if validation is not None:

                validation.observe(
                    candidate,
                    bar,
                )

        context.trade_setups = candidates

    # ==================================================

    def reset(self):

        self._logged_min_risk.clear()