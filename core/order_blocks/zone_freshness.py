"""
====================================================

QuantEngine

Structural Zone Freshness

Phase 4G -- structural freshness, zone age, entry
eligibility and canonical zone selection.

THIS MODULE CONTAINS ONLY PURE, AT-CREATION MEASUREMENT:

    * how old a structural zone is  (age in bars / seconds),
    * what its derived freshness state is
      (FRESH / ACTIVE / TESTED / MITIGATED / STALE /
      INVALIDATED),
    * whether a zone may mint a trade setup
      (entry eligibility + an explicit rejection reason),
    * structural zone clustering before setup generation
      (STEP 9 / 10: overlapping duplicate zones collapse
      to ONE canonical zone per execution surface).

No function here reads a single bar AFTER the creating
candle, and no function mutates any engine state -- the
no-future-information guarantee is structural.

The zone AGE is measured as current_bar - origin_bar (a
direct measurement, never an accumulated counter), because
the scanners re-derive blocks from the trailing window every
candle: a counter would reset on every re-scan, a measurement
cannot.

====================================================
"""

from config import risk_settings


# ==========================================================
# Freshness states (Phase 4G STEP 2)
#
#     NEW            zone discovered this candle (== FRESH for a
#                    brand-new origin)
#     FRESH          age <= FRESH_ORDER_BLOCK_AGE_BARS
#     ACTIVE         age out of FRESH but within max age
#     TESTED         at least one candle traded into the zone
#     MITIGATED      price moved through / closed past the zone
#     STALE          age > MAX_ORDER_BLOCK_AGE_BARS (timeframe-aware)
#     INVALIDATED    structure invalidated
#
# The lifecycle NEW -> FRESH -> ACTIVE -> TESTED -> MITIGATED
# -> STALE is a DERIVED state machine: the block is re-stamped
# every scan from (age, touches, mitigated, invalidated), so
# there is no mutable, drifty transition counter to leak look-ahead.
# ==========================================================

FRESHNESS_FRESH = "FRESH"
FRESHNESS_ACTIVE = "ACTIVE"
FRESHNESS_TESTED = "TESTED"
FRESHNESS_MITIGATED = "MITIGATED"
FRESHNESS_STALE = "STALE"
FRESHNESS_INVALIDATED = "INVALIDATED"

# From most to least usable. Used for canonical-zone rank ties.
FRESHNESS_RANK = {
    FRESHNESS_FRESH: 5,
    FRESHNESS_ACTIVE: 4,
    FRESHNESS_TESTED: 3,
    FRESHNESS_MITIGATED: 2,
    FRESHNESS_STALE: 1,
    FRESHNESS_INVALIDATED: 0,
}

# ==========================================================
# Entry rejection reasons (Phase 4G STEP 4)
#
# STALE_LIQUIDITY_CONTEXT and STALE_TARGET are reserved values
# in the taxonomy: nothing emits them yet because the zone model
# does not carry liquidity-context / target age data. They exist
# so the reasons vocabulary is complete and future-proof.
# ==========================================================

REASON_INVALIDATED_STRUCTURE = "INVALIDATED_STRUCTURE"
REASON_ALREADY_MITIGATED = "ALREADY_MITIGATED"
REASON_STALE_ZONE = "STALE_ZONE"
REASON_TOO_FAR_FROM_MARKET = "TOO_FAR_FROM_MARKET"
REASON_TOO_MANY_TOUCHES = "TOO_MANY_TOUCHES"
REASON_INSUFFICIENT_RISK_WIDTH = "INSUFFICIENT_RISK_WIDTH"
REASON_WEAK_DISPLACEMENT = "WEAK_DISPLACEMENT"
REASON_STALE_LIQUIDITY_CONTEXT = "STALE_LIQUIDITY_CONTEXT"
REASON_STALE_TARGET = "STALE_TARGET"

# Primary-reason priority when several blocking conditions hold
# at once: the MOST conservative reason wins (deterministic).
_REJECTION_PRIORITY = (
    REASON_INVALIDATED_STRUCTURE,
    REASON_ALREADY_MITIGATED,
    REASON_STALE_ZONE,
    REASON_TOO_FAR_FROM_MARKET,
    REASON_INSUFFICIENT_RISK_WIDTH,
)

# Human labels for the DecisionEngine's SETUP_REJECTED reason log.
REASON_LABELS = {
    REASON_INVALIDATED_STRUCTURE: "Invalidated Structure",
    REASON_ALREADY_MITIGATED: "Already Mitigated",
    REASON_STALE_ZONE: "Stale Zone",
    REASON_TOO_FAR_FROM_MARKET: "Entry Too Far",
    REASON_TOO_MANY_TOUCHES: "Too Many Touches",
    REASON_INSUFFICIENT_RISK_WIDTH: "Insufficient Risk Width",
    REASON_WEAK_DISPLACEMENT: "Weak Displacement",
    REASON_STALE_LIQUIDITY_CONTEXT: "Stale Liquidity Context",
    REASON_STALE_TARGET: "Stale Target",
}

# ==========================================================
# Timeframe-aware max age
# ==========================================================


def max_order_block_age_bars(timeframe=""):
    """
    MAX_ORDER_BLOCK_AGE_BARS for the given timeframe. A zone older
    than this is STALE and can never mint a LIMIT_RETEST order.
    Per-timeframe overrides win; otherwise the global default.
    """

    by_tf = getattr(
        risk_settings, "MAX_ORDER_BLOCK_AGE_BARS_BY_TIMEFRAME", None
    ) or {}

    tf = timeframe or ""

    if tf in by_tf:

        value = int(by_tf[tf])

        if value > 0:

            return value

    return int(getattr(risk_settings, "MAX_ORDER_BLOCK_AGE_BARS", 500))


# ==========================================================
# Age
# ==========================================================


def compute_zone_age(origin_bar, current_bar):
    """
    Zone age in bars: current_bar - origin_bar. A direct
    measurement of the STRUCTURE, so it is identical on every
    re-scan of the same zone. Unknown origin (hand-seeded block,
    origin_bar < 0) reads as age 0 / fresh -- the harness
    convention that a hand-seeded zone is alive.
    """

    if origin_bar is None or current_bar is None or origin_bar < 0:

        return 0

    return max(0, int(current_bar) - int(origin_bar))


# ----------------------------------------------------------


def age_bucket(age):
    """
    Phase 4G STEP 11 report bucket for an age in bars. Reporting
    only -- never a strategy threshold.
    """

    if age <= 5:
        return "0-5"
    if age <= 15:
        return "6-15"
    if age <= 30:
        return "16-30"
    if age <= 60:
        return "31-60"
    if age <= 120:
        return "61-120"
    return "120+"


# ==========================================================
# Freshness classification
# ==========================================================


def classify_freshness(block, age_bars=None, max_age_bars=None):
    """
    Derived freshness state of a zone. Priority: INVALIDATED >
    MITIGATED > STALE (age > max) > TESTED (touches > 0) >
    FRESH (age <= FRESH_ORDER_BLOCK_AGE_BARS) > ACTIVE.
    """

    invalidated = bool(getattr(block, "invalidated", False))

    if invalidated:

        return FRESHNESS_INVALIDATED

    mitigated = bool(getattr(block, "mitigated", False))

    if mitigated:

        return FRESHNESS_MITIGATED

    if age_bars is None:

        age_bars = getattr(block, "age_bars", None)

        if age_bars is None or age_bars < 0:

            age_bars = compute_zone_age(
                getattr(block, "origin_bar", -1),
                getattr(block, "created_bar", 0),
            )

    age = int(age_bars or 0)

    if max_age_bars is None:

        max_age_bars = max_order_block_age_bars(
            getattr(block, "timeframe", "")
        )

    if age > max_age_bars:

        return FRESHNESS_STALE

    if int(getattr(block, "touches", 0) or 0) > 0:

        return FRESHNESS_TESTED

    fresh = int(getattr(risk_settings, "FRESH_ORDER_BLOCK_AGE_BARS", 5))

    if age <= fresh:

        return FRESHNESS_FRESH

    return FRESHNESS_ACTIVE


# ==========================================================
# Structural clustering helpers (STEP 9 / 10)
# ==========================================================


def effective_zone_tolerance(price, atr=0.0):
    """
    The effective closeness tolerance for structural-zone
    clustering at a price level -- the SAME formula the Phase 4E
    economic registry uses, so "one execution surface" means the
    same thing structurally as it does economically:

        tolerance = max(
            tick * ECONOMIC_CLUSTER_TICKS,
            price * ECONOMIC_CLUSTER_PCT,
            atr   * ECONOMIC_CLUSTER_ATR_FRACTION,
        )
    """

    tick = float(getattr(risk_settings, "ECONOMIC_TICK_SIZE", 0.5) or 0.0)

    ticks = int(getattr(risk_settings, "ECONOMIC_CLUSTER_TICKS", 0) or 0)

    pct = float(getattr(risk_settings, "ECONOMIC_CLUSTER_PCT", 0.0) or 0.0)

    atr_frac = float(
        getattr(risk_settings, "ECONOMIC_CLUSTER_ATR_FRACTION", 0.0) or 0.0
    )

    return max(
        tick * ticks,
        (abs(price) if price else 0.0) * pct,
        (abs(atr) if atr else 0.0) * atr_frac,
    )


# ----------------------------------------------------------


def zones_overlap(a, b, atr=0.0):
    """
    True when two zones describe the same structural execution
    surface: same direction and both the entry AND the stop lie
    within the effective economic tolerance (so the price ranges
    overlap in a way that cannot also describe two independently
    tradeable zones). Genuinely independent zones -- e.g. entry
    110 vs entry 120 -- never merge; identical duplicates always
    do (OB-791..796 collapse to one cluster).
    """

    if a.direction != b.direction:

        return False

    entry_tol = effective_zone_tolerance(
        min(a.entry, b.entry), atr
    )

    stop_tol = effective_zone_tolerance(
        min(a.stop, b.stop), atr
    )

    return (
        abs(a.entry - b.entry) <= entry_tol
        and abs(a.stop - b.stop) <= stop_tol
    )


# ----------------------------------------------------------


def _canonical_key(block):
    """
    Deterministic canonical-zone rank (STEP 10): freshest zone
    wins, then strongest displacement, then highest score, then
    least-tested, then widest risk stop, then lowest block index
    (Phase 4E parity -- OB-5 beats OB-6 on an exact-identical
    tie). Never random.
    """

    return (
        -int(FRESHNESS_RANK.get(
            getattr(block, "freshness", "") or FRESHNESS_FRESH,
            FRESHNESS_RANK[FRESHNESS_FRESH],
        )),
        -(float(getattr(block, "displacement_strength", 0.0) or 0.0)),
        -(float(getattr(block, "score", 0.0) or 0.0)),
        int(getattr(block, "touches", 0) or 0),
        -(float(abs(block.entry - block.stop) or 0.0)),
        int(getattr(block, "index", 0) or 0),
    )


# ----------------------------------------------------------


def cluster_structural_zones(blocks, atr=0.0):
    """
    STEP 9 / 10: collapse overlapping duplicate zones of the same
    candle into structural clusters BEFORE setup generation, and
    stamp every block with its cluster identity:

        cluster_id        e.g. CL-0002 (per-candle ordinal)
        is_canonical      True only for the cluster's canonical
        canonical_zone_id the canonical block's index ("" when the
                          zone is the only member, or not clustered)

    Stable greedy clustering preserving input order (deterministic,
    mirrors the Phase 4E economic clustering on blocks instead of
    candidates). Mutates nothing else. Returns
    (clusters, non_canonical_count).
    """

    clusters = []

    for block in blocks:

        placed = False

        for cluster in clusters:

            if zones_overlap(cluster[0], block, atr):

                cluster.append(block)

                placed = True

                break

        if not placed:

            clusters.append([block])

    non_canonical = 0

    for cl_i, members in enumerate(clusters):

        members.sort(key=_canonical_key)

        canonical = members[0]

        cluster_id = "CL-{:04d}".format(cl_i)

        for block in members:

            block.cluster_id = cluster_id

            block.is_canonical = block is canonical

            block.canonical_zone_id = (
                "" if len(members) == 1 else str(canonical.index)
            )

            if block is not canonical:

                non_canonical += 1

    return clusters, non_canonical


# ==========================================================
# Entry eligibility (STEP 4 / 5 / 6 / 8)
# ==========================================================

# The expansion of MAX_LIMIT_ENTRY_DISTANCE_ATR read target:
# also used by the report to call out the TOO_FAR_FROM_MARKET
# share of the funnel. Keep the single-source constant name.
MAX_LIMIT_ENTRY_DISTANCE_ATR_KEY = "MAX_LIMIT_ENTRY_DISTANCE_ATR"


def evaluate_entry_eligibility(block, candidate, atr=0.0):
    """
    Phase 4G STEP 4-8: decide whether a zone may mint a trade
    setup, and WHY NOT, at the CURRENT candle only (no future
    bars touched).

    Blocking reasons (candidate.trade_eligible = False):
        INVALIDATED_STRUCTURE   block.invalidated
        ALREADY_MITIGATED       block.mitigated
        STALE_ZONE              age > timeframe max age
        TOO_FAR_FROM_MARKET     entry distance > MAX_LIMIT_
                                ENTRY_DISTANCE_ATR x ATR
        INSUFFICIENT_RISK_WIDTH entry-stop < MIN_RISK_WIDTH_ATR
                                x ATR (ALL setup paths)

    Diagnosed but NEVER blocking this phase (baseline config):
        WEAK_DISPLACEMENT       displacement_strength below
                                MIN_ORDER_BLOCK_DISPLACEMENT
        TOO_MANY_TOUCHES        touch_count above
                                MAX_ORDER_BLOCK_TOUCHES

    Returns (structurally_valid, trade_eligible, primary_reason,
             diagnostics). At the [0, ...] head:

        structurally_valid -- the zone is not invalidated/mitigated
            (structural validity is INDEPENDENT of trade eligibility:
            a stale but unbroken zone stays structurally valid).
        trade_eligible      -- may mint an order this candle.
        primary_reason      -- the most conservative blocking reason
            ("" when eligible).
        diagnostics         -- measured, non-blocking notes.
    """

    diagnostics = []

    invalidated = bool(getattr(block, "invalidated", False))

    mitigated = bool(getattr(block, "mitigated", False))

    structurally_valid = not invalidated and not mitigated

    blocking = []

    if invalidated:

        blocking.append(REASON_INVALIDATED_STRUCTURE)

    if mitigated:

        blocking.append(REASON_ALREADY_MITIGATED)

    age = int(getattr(block, "age_bars", 0) or 0)

    max_age = max_order_block_age_bars(
        getattr(block, "timeframe", "")
    )

    if age > max_age:

        blocking.append(REASON_STALE_ZONE)

    atr = float(atr or 0.0)

    distance_atr = (
        float(getattr(block, "distance_from_current_price_atr", 0.0) or 0.0)
        if atr > 0
        else 0.0
    )

    max_distance = float(
        getattr(risk_settings, MAX_LIMIT_ENTRY_DISTANCE_ATR_KEY, 30.0)
        or 30.0
    )

    # ATR axis only: without an ATR there is no normalized
    # "too far" measurement, so the gate stays pass-through
    # (harness convention: 0.0 ATR means not measurable).
    if atr > 0 and distance_atr > 0 and distance_atr > max_distance:

        blocking.append(REASON_TOO_FAR_FROM_MARKET)

    risk = abs(
        float(getattr(candidate, "entry", 0.0) or 0.0)
        - float(getattr(candidate, "stop_loss", 0.0) or 0.0)
    )

    min_width = float(
        getattr(risk_settings, "MIN_RISK_WIDTH_ATR", 0.10) or 0.10
    )

    # All-paths minimum-risk-width gate (STEP 8): the ATR floor
    # applies on every path ANY time an ATR axis exists. A
    # 1.0-point stop on a ~289-ATR BTC 1m minute is ~0.003 ATR:
    # far below the 0.10 baseline, so the 237R abomination can
    # never mint a pending order through ANY pipeline path.
    if atr > 0 and risk <= 0:

        blocking.append(REASON_INSUFFICIENT_RISK_WIDTH)

    elif atr > 0 and (risk / atr) < min_width:

        blocking.append(REASON_INSUFFICIENT_RISK_WIDTH)

    min_displacement = float(
        getattr(risk_settings, "MIN_ORDER_BLOCK_DISPLACEMENT", 0.0) or 0.0
    )

    if min_displacement > 0 and (
        float(getattr(block, "displacement_strength", 0.0) or 0.0)
        < min_displacement
    ):

        diagnostics.append(REASON_WEAK_DISPLACEMENT)

    max_touches = int(
        getattr(risk_settings, "MAX_ORDER_BLOCK_TOUCHES", 0) or 0
    )

    if max_touches > 0 and (
        int(getattr(block, "touches", 0) or 0) > max_touches
    ):

        diagnostics.append(REASON_TOO_MANY_TOUCHES)

    primary = ""

    if blocking:

        for reason in _REJECTION_PRIORITY:

            if reason in blocking:

                primary = reason

                break

    return (
        structurally_valid,
        not blocking,
        primary,
        diagnostics,
    )