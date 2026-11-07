"""
====================================================

QuantEngine

Institutional Order Block

====================================================
"""

from dataclasses import dataclass, field

from core.common.base_market_object import BaseMarketObject


@dataclass(slots=True)
class OrderBlock(BaseMarketObject):

    # ==================================================
    # Identification
    # ==================================================

    index: int

    timestamp: int

    timeframe: str

    direction: str

    # ==================================================
    # Candle
    # ==================================================

    open: float

    high: float

    low: float

    close: float

    # ==================================================
    # Institutional Quality
    # ==================================================

    strength: float

    displacement_strength: float = 0.0

    volume_ratio: float = 0.0

    institutional_score: float = 0.0

    score: float = 0.0

    # ==================================================
    # Relationships
    # ==================================================

    bos_index: int = -1

    choch_index: int = -1

    swing_id: str | None = None

    fvg_index: int = -1

    # ==================================================
    # State
    # ==================================================

    active: bool = True

    mitigated: bool = False

    invalidated: bool = False

    broken: bool = False

    touches: int = 0

    mitigation_timestamp: int = 0

    invalidation_timestamp: int = 0

    # ==================================================
    # Structural Freshness (Phase 4G STEP 1-3)
    # ==================================================
    #
    # The scanner is re-run every candle and RE-CREATES each
    # block from the trailing window, so these fields are
    # re-stamped every scan (never accumulated): age_bars is a
    # DIRECT measurement (bars between the origin candle and the
    # current candle), never a counter that could drift. Blocks
    # built outside the scanner (scripted harnesses) leave
    # origin_bar = -1, which reads as age 0 / FRESH -- the
    # harness convention is that a hand-seeded zone is alive.

    # Absolute bar index of the candle that formed the zone
    # (the origin candle). -1 when unknown (hand-seeded block).
    origin_bar: int = -1

    # Absolute bar index of the candle on which this block
    # object was (re)created.
    created_bar: int = -1

    # How many bars the zone is old, measured at the CURRENT
    # candle: current_bar - origin_bar. Zone age is a fact about
    # the STRUCTURE, not about when the object happened to be
    # (re)built, so it is identical on every re-scan of the zone.
    age_bars: int = 0

    # Same measurement in wall-clock seconds (origin timestamp ->
    # current candle timestamp).
    age_time_seconds: int = 0

    # Derived freshness state (Phase 4G STEP 2): INVALIDATED /
    # MITIGATED / STALE / TESTED / FRESH / ACTIVE. STALE is age >
    # MAX_ORDER_BLOCK_AGE_BARS for the timeframe.
    freshness: str = "FRESH"

    # Price distance from the zone's entry to the current candle
    # close; the same distance normalized by ATR_14 (0.0 when no
    # ATR axis is available). Pre-pending LIMIT_RETEST eligibility
    # gates on the ATR-normalized value.
    distance_from_current_price: float = 0.0

    distance_from_current_price_atr: float = 0.0

    # NONE / TOUCHED / MITIGATED / INVALIDATED (filled by the
    # lifecycle; NONE for a hand-seeded or unmarked zone).
    mitigation_status: str = "NONE"

    # Bar + timestamp of the LAST candle that traded into the
    # zone (filled by the lifecycle on touch detection).
    last_tested_bar: int = -1

    last_tested_timestamp: int = 0

    # ==================================================
    # Structural Zone Clustering (Phase 4G STEP 9-10)
    # ==================================================
    #
    # Set by the TradeSetupBuilder BEFORE setup generation: zones
    # describing the same execution surface (overlapping price
    # ranges within the economic tolerance) collapse into one
    # structural cluster; only the canonical zone mints a setup.
    # Re-derived every candle (blocks are re-scanned), so these
    # are per-candle diagnostics, not persistent history.

    cluster_id: str = ""

    is_canonical: bool = True

    # Identity of the cluster's canonical zone (its block index
    # for this candle); "" for a cluster of one / not clustered.
    canonical_zone_id: str = ""

    # ==================================================
    # Metadata
    # ==================================================

    metadata: dict = field(

        default_factory=dict,

    )

    # ==================================================

    @property
    def entry(self):
        """The limit-retest entry level the zone describes:
        the top of a bullish zone, the bottom of a bearish one."""

        if self.direction == "BULLISH":
            return self.high

        return self.low

    # --------------------------------------------------

    @property
    def stop(self):
        """The structural invalidation level of the zone:
        the bottom of a bullish zone, the top of a bearish one."""

        if self.direction == "BULLISH":
            return self.low

        return self.high

    # --------------------------------------------------

    @property
    def touch_count(self):
        """Phase 4G STEP 3 metric: number of candles that traded
        into the zone. Backed by the existing `touches` field --
        a pure alias, never duplicated state."""

        return self.touches

    # --------------------------------------------------

    def is_bullish(self):

        return self.direction == "BULLISH"

    # --------------------------------------------------

    def is_bearish(self):

        return self.direction == "BEARISH"

    # --------------------------------------------------

    def mark_mitigated(

        self,

        timestamp: int,

    ):

        self.mitigated = True

        self.mitigation_timestamp = timestamp

        self.mitigation_status = "MITIGATED"

    # --------------------------------------------------

    def mark_invalid(

        self,

        timestamp: int,

    ):

        self.invalidated = True

        self.active = False

        self.invalidation_timestamp = timestamp

        self.mitigation_status = "INVALIDATED"

    # --------------------------------------------------

    def touch(self):

        self.touches += 1
