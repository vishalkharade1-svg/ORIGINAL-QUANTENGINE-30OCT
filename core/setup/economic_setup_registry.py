"""
====================================================

QuantEngine

Economic Setup Registry

Phase 4E -- economic setup deduplication and clustering.

The OrderRegistry enforces ONE STRUCTURAL SETUP == ONE ORDER:
a setup is keyed by setup_id (symbol + timeframe + direction +
order-block index + exact economics), so two DIFFERENT order
blocks whose structural discovery happens to describe the SAME
market idea (e.g. OB-954 entry 77616 / stop 77631.5 / target
77455.42 and OB-956 with identical economics) were never seen
as duplicates -- each produced its own pending order and burned
a MAX_PENDING_ORDERS slot on a variant of one idea.

This registry adds the SECOND deduplication layer:

    structural_id  -- what the setup IS structurally
                      (== setup_id; unique per discovery).
    economic_fingerprint -- what the setup IS economically
                      (symbol, timeframe, direction, and the
                      entry / stop / target BUCKETS normalized
                      to the instrument's tick grid, so equal
                      economics yield one identical string).

Flow prescribed by Phase 4E:

    Discover setups
        -> Structural dedup (OrderRegistry: one setup == one order)
        -> Economic dedup (identical fingerprint, exact)
        -> Cluster (near-identical economics within thresholds)
        -> Rank canonical setups (deterministic)
        -> Risk validation (MAX_PENDING_ORDERS / exposure)
        -> Create pending orders

observe(setups, order_registry, bar) implements the middle four
steps and returns the ranked canonical representatives only. The
ExecutionEngine then applies the pending-slot cap to a funnel
that is no longer polluted by economically duplicate variants.

Clustering is OPTIONAL and configurable via config.risk_settings
-- thresholds expressed as tick multiples and percentage
distance (and an ATR fraction hook), never as hard-coded point
distances for a single symbol:

    ECONOMIC_TICK_SIZE           instrument tick (per symbol)
    ECONOMIC_CLUSTER_TICKS       tick multiples of tolerance
    ECONOMIC_CLUSTER_PCT         percent-of-price tolerance
    ECONOMIC_CLUSTER_ATR_FRACTION  ATR fraction (default 0 = off)

Canonical selection within a cluster is deterministic:

    highest setup score
    -> highest structural confidence
    -> best liquidity alignment
    -> best reward/risk
    -> newest valid structural state (observed_bar)
    -> structural_id (ascending -- stable, never random)

Session state lives on the shared PipelineContext exactly like
the OrderRegistry: created once per run, untouched by
reset_cycle(), re-created only on reset().

====================================================
"""

from config import risk_settings

from core.execution.order_registry import (
    EXPIRED,
    FILLED,
    INVALIDATED,
)


# ==========================================================
# Economic lifecycle states (Phase 4F STEP 9)
# ==========================================================

# An economic idea's state, tracked per economic fingerprint:
#
#     ACTIVE        a canonical order for the idea is pending /
#                   about to be minted this candle.
#     FILLED        an order for the idea FILLED (realized; NO
#                   cooldown -- a later structural discovery of the
#                   same economics is a genuinely new opportunity).
#     EXPIRED / INVALIDATED
#                   an order for the idea reached a terminal state
#                   WITHOUT filling. The idea enters COOLDOWN and
#                   may not be re-ordered for REENTRY_COOLDOWN_BARS
#                   after its terminal bar, even when a NEW order
#                   block later discovers the same tick-normalized
#                   economics.
#     COOLDOWN      (effective state while bar <= cooldown_until)
ECONOMIC_LIFECYCLE_ACTIVE = "ACTIVE"

ECONOMIC_LIFECYCLE_COOLDOWN = "COOLDOWN"


# ==========================================================
# Fingerprint
# ==========================================================


def snap_price(price, tick=None):
    """
    Snap a price to the nearest tick-grid level -- the ONLY
    price comparison the economic fingerprint relies on (never
    arbitrary float-string equality). With no tick configured the
    price passes through untouched (still deterministic: Python
    float equality).
    """

    if tick is None:

        tick = getattr(
            risk_settings, "ECONOMIC_TICK_SIZE", 0.0
        ) or 0.0

    if tick and tick > 0 and price:

        return tick * round(price / tick)

    return price


def fingerprint_of(obj, symbol=None, timeframe=None):
    """
    Tick-normalized economic fingerprint of a setup / order /
    any object exposing symbol, timeframe, direction, entry,
    stop_loss and take_profit. Two objects with identical trade
    economics (symbol + timeframe + direction + entry/stop/target
    buckets) always yield the identical string, regardless of the
    structural discovery that produced them.

    `symbol` / `timeframe` may be supplied explicitly for objects
    that do not carry them (SetupCandidate deliberately does not)
    so the fingerprint still names the market surface.

    Idempotent: when `obj` already carries a non-empty
    economic_fingerprint attribute it is returned unchanged, and
    when it is writable the computed value is stamped back so a
    single fingerprint is used everywhere downstream.
    """

    existing = getattr(obj, "economic_fingerprint", "") or ""

    if existing:

        return existing

    symbol = (
        symbol
        or getattr(obj, "symbol", "") or ""
    )

    timeframe = (
        timeframe
        or getattr(obj, "timeframe", "") or ""
    )

    direction = getattr(obj, "direction", "") or ""

    entry = snap_price(getattr(obj, "entry", 0.0) or 0.0)

    stop = snap_price(getattr(obj, "stop_loss", 0.0) or 0.0)

    target = snap_price(getattr(obj, "take_profit", 0.0) or 0.0)

    fp = "{}-{}-{}-E-{}-S-{}-T-{}".format(
        symbol,
        timeframe,
        direction,
        "{:g}".format(entry),
        "{:g}".format(stop),
        "{:g}".format(target),
    )

    try:

        obj.economic_fingerprint = fp

    except (AttributeError, TypeError):

        pass

    return fp


# ==========================================================
# Clustering tolerance
# ==========================================================


def price_tolerance(price, atr=None):
    """
    Configurable proximity threshold at a price level. A pair of
    setups cluster only when entry/stop/target all differ by no
    more than their level's tolerance:

        tolerance = max(
            tick * ECONOMIC_CLUSTER_TICKS,
            price * ECONOMIC_CLUSTER_PCT,
            atr  * ECONOMIC_CLUSTER_ATR_FRACTION,  (optional)
            minimum of one tick,
        )

    Thresholds come from config/risk_settings -- nothing is
    hard-coded to a single symbol's point grid.
    """

    tick = getattr(
        risk_settings, "ECONOMIC_TICK_SIZE", 0.0
    ) or 0.0

    ticks = getattr(
        risk_settings, "ECONOMIC_CLUSTER_TICKS", 8
    ) or 0

    pct = getattr(
        risk_settings, "ECONOMIC_CLUSTER_PCT", 0.0
    ) or 0.0

    atr_fraction = getattr(
        risk_settings, "ECONOMIC_CLUSTER_ATR_FRACTION", 0.0
    ) or 0.0

    tick_tol = tick * ticks

    pct_tol = (price or 0.0) * pct

    atr_tol = (atr or 0.0) * atr_fraction

    tolerance = max(tick_tol, pct_tol, atr_tol)

    # Never cluster distinct tick levels when NO threshold is
    # configured (all knobs at 0) -- exact-fingerprint dedup only.
    if tolerance <= 0:

        return 0.0

    return tolerance


def _setup_atr(setup):

    atr = getattr(setup, "atr", None)

    if atr:

        return atr

    # Architecture hook: a setup may carry its ATR on the regime
    # or in its metadata. Reads are defensive; a missing ATR
    # simply disables the ATR fraction of the tolerance.
    regime = getattr(setup, "regime", None)

    if regime is not None:

        atr = getattr(regime, "atr", None)

        if atr:

            return atr

    metadata = getattr(setup, "metadata", None) or {}

    return metadata.get("atr")


def _close(a, b):

    atr = max(_setup_atr(a) or 0.0, _setup_atr(b) or 0.0)

    for axis in ("entry", "stop_loss", "take_profit"):

        pa = getattr(a, axis, 0.0) or 0.0

        pb = getattr(b, axis, 0.0) or 0.0

        tolerance = max(
            price_tolerance(pa, atr),
            price_tolerance(pb, atr),
        )

        if abs(pa - pb) > tolerance:

            return False

    return True


# ==========================================================
# Canonical ranking
# ==========================================================


def liquidity_alignment(setup):
    """
    How well the setup's liquidity target lines up with the trade
    direction: a BUY-side target for a BULLISH entry (and a
    SELL-side target for a BEARISH entry) is fully aligned, then
    blended with the target's confidence score. Deterministic.
    """

    target = getattr(setup, "liquidity", None)

    if target is None:

        return 0.0

    side = (getattr(target, "side", "") or "").upper()

    direction = (getattr(setup, "direction", "") or "").upper()

    alignment = 0.0

    if side == "BUY" and direction == "BULLISH":

        alignment += 1.0

    elif side == "SELL" and direction == "BEARISH":

        alignment += 1.0

    alignment += (
        float(getattr(target, "score", 0.0) or 0.0) / 100.0
    )

    return alignment


def rank_key(setup):
    """
    Deterministic canonical-selection order for a cluster:

        (score, confidence, liquidity alignment, risk/reward,
         newest observed bar, structural id ascending)

    Ties on every axis resolve by structural_id -- ascending,
    so the surviving canonical is always the same for a given
    cluster (never random).
    """

    structural_id = getattr(
        setup, "structural_id", ""
    ) or getattr(setup, "setup_id", "") or ""

    return (
        -float(getattr(setup, "score", 0.0) or 0.0),
        -float(getattr(setup, "confidence", 0.0) or 0.0),
        -liquidity_alignment(setup),
        -float(getattr(setup, "risk_reward", 0.0) or 0.0),
        -int(getattr(setup, "observed_bar", 0) or 0),
        structural_id,
    )


# ==========================================================
# Registry
# ==========================================================


class EconomicSetupRegistry:

    def __init__(self):

        # ---------------- Stats (per-run) ----------------

        # Candidate setups fed to observe() (structural
        # discoveries after the DecisionEngine accepted them).
        self.structural_observed = 0

        # Setups suppressed as economically duplicate: identical
        # fingerprint to an active order, exact within-candle
        # fingerprint duplicates, or clustered near-identical
        # variants. These never consume a pending slot.
        self.duplicates_suppressed = 0

        # Setups skipped only because their structural id is
        # already ordered (the OrderRegistry one-setup rule, seen
        # again defensively here -- not an economic duplicate).
        self.pre_ordered = 0

        # Number of distinct economic fingerprints ever observed.
        self.distinct_fingerprints = 0

        # Number of clusters containing MORE than one structurally
        # distinct setup (the phenomenon economic dedup is for).
        self.clusters_formed = 0

        # Canonical representatives passed onward to RiskEngine.
        self.canonical_selected = 0

        # Setups suppressed ONLY because their economic fingerprint
        # is in its post-expiry/invalidation RE-ENTRY COOLDOWN
        # (Phase 4F STEP 9). Distinct from duplicates_suppressed:
        # the economics are identical, but a fresh structure could
        # legally order them after the cooldown passes.
        self.reentry_cooldown_suppressed = 0

        # ---------------- Identity space ----------------

        self._fingerprints = set()

        self._structural_ids = set()

        # ---------------- Economic lifecycle (Phase 4F) ----------------

        # fingerprint -> lifecycle state (ACTIVE / FILLED / EXPIRED /
        # INVALIDATED). Updated by mark_terminal() / sync_lifecycles().
        self._lifecycle = {}

        # fingerprint -> bar until which re-ordering is suppressed.
        self._cooldown_until = {}

    # ------------------------------------------------------

    def reset(self):

        self.__init__()

    # ------------------------------------------------------

    def observe(self, setups, order_registry=None, bar=0):
        """
        Phase 4E funnel: economic dedup -> cluster -> rank, for
        one candle's accepted setups. Returns the ranked canonical
        representatives ONLY.

            1. structural dedup (defensive): setups whose setup_id
               already has an order are skipped (the OrderRegistry
               is the primary guard).
            2. active economic dedup: a setup whose fingerprint
               matches an already-PENDING order is a duplicate of
               a live idea -- linked to the canonical order's
               setup_id and suppressed.
            3. exact fractional dedup: within THIS candle, one
               canonical setup per fingerprint.
            4. clustering: near-identical survivors (entry, stop
               and target all within tolerance) group into one
               execution zone.
            5. ranking: one canonical setup per zone, selected by
               the deterministic rank_key, rest marked economic
               duplicates.
        """

        self.structural_observed += len(setups)

        if not setups:

            return []

        active = self._active_fingerprints(order_registry)

        survivors = []

        for setup in setups:

            stamp = getattr(setup, "observed_bar", None)

            if stamp is not None:

                setup.observed_bar = bar

            structural_id = getattr(
                setup, "structural_id", ""
            ) or getattr(setup, "setup_id", "")

            if structural_id:

                self._structural_ids.add(structural_id)

            if order_registry is not None and structural_id:

                if order_registry.has_order_for_setup(structural_id):

                    self.pre_ordered += 1

                    continue

            fp = fingerprint_of(setup)

            if fp:

                self._fingerprints.add(fp)

            self.distinct_fingerprints = len(self._fingerprints)

            # ---- 1b. re-entry cooldown (Phase 4F STEP 9) ------
            #
            # A fingerprint that EXPIRED / INVALIDATED recently is
            # in COOLDOWN: structurally NEW discoveries of the same
            # tick-normalized economics are suppressed until the
            # cooldown bar passes, so endlessly-mintable identical
            # ideas cannot re-create every window. Time-based only:
            # a genuinely new structural setup at the same prices is
            # legal the moment the cooldown lapses.
            if fp and self._in_cooldown(fp, bar):

                setup.is_economic_duplicate = True

                setup.reentry_cooldown_suppressed = True

                setup.economic_canonical_id = fp

                self.reentry_cooldown_suppressed += 1

                continue

            # ---- 2. duplicate of a live idea --------------

            if fp and fp in active:

                setup.is_economic_duplicate = True

                setup.economic_canonical_id = active[fp]

                self.duplicates_suppressed += 1

                continue

            survivors.append(setup)

        # ---- 3. exact dedup within this candle -------------

        per_fp = {}

        for setup in survivors:

            per_fp.setdefault(
                fingerprint_of(setup), []
            ).append(setup)

        canonical_by_fp = []

        for fp, members in per_fp.items():

            ordered = sorted(members, key=rank_key)

            best = ordered[0]

            for other in ordered[1:]:

                other.is_economic_duplicate = True

                other.economic_canonical_id = (
                    getattr(best, "structural_id", "")
                    or best.setup_id
                )

                self.duplicates_suppressed += 1

            canonical_by_fp.append(best)

        # ---- 4. clustering near-identical zones ------------

        survivors = sorted(canonical_by_fp, key=rank_key)

        clusters = []

        for setup in survivors:

            placed = False

            for cluster in clusters:

                if _close(cluster[0], setup):

                    cluster.append(setup)

                    placed = True

                    break

            if not placed:

                clusters.append([setup])

        zoned = []

        for members in clusters:

            if len(members) > 1:

                self.clusters_formed += 1

            best = members[0]

            for other in members[1:]:

                other.is_economic_duplicate = True

                other.economic_canonical_id = (
                    getattr(best, "structural_id", "")
                    or best.setup_id
                )

                self.duplicates_suppressed += 1

            zoned.append(best)

        # ---- 5. ranked canonical representatives ----------

        zoned.sort(key=rank_key)

        self.canonical_selected += len(zoned)

        # A canonical that survived the funnel is a LIVE idea: its
        # fingerprint (re)activates (Phase 4F STEP 9 bookkeeping).
        for setup in zoned:

            fp = getattr(
                setup, "economic_fingerprint", ""
            ) or fingerprint_of(setup)

            if fp:

                self._lifecycle[fp] = ECONOMIC_LIFECYCLE_ACTIVE

        return zoned

    # ------------------------------------------------------

    def _active_fingerprints(self, order_registry):
        """
        fingerprint -> structural id(s) of every order currently
        PENDING in the registry. An identical fingerprint against
        a live order is an economically duplicate order-wait --
        no second pending order may be minted for the same idea.
        """

        result = {}

        if order_registry is None:

            return result

        for order in order_registry.pending():

            fp = fingerprint_of(order)

            if not fp:

                continue

            structural_id = getattr(
                order, "structural_id", ""
            ) or getattr(order, "setup_id", "")

            result.setdefault(fp, structural_id)

        return result

    # ------------------------------------------------------

    def mark_terminal(self, fp, outcome, terminal_bar):
        """
        Phase 4F STEP 9: record an economic idea's terminal outcome.

            FILLED         -> realized: NO cooldown (a later
                              structural discovery of the same
                              economics is a genuinely NEW
                              opportunity and is re-entered).
            EXPIRED / INVALIDATED -> the idea enters COOLDOWN until
                terminal_bar + REENTRY_COOLDOWN_BARS; a structurally
                new setup with the same fingerprint is suppressed
                during that window.
        """

        if not fp:

            return

        self._lifecycle[fp] = outcome

        if outcome == FILLED:

            self._cooldown_until.pop(fp, None)

            return

        if outcome not in (EXPIRED, INVALIDATED):

            return

        cooldown = int(getattr(
            risk_settings, "REENTRY_COOLDOWN_BARS", 0
        ) or 0)

        if cooldown > 0:

            self._cooldown_until[fp] = (
                int(terminal_bar or 0) + cooldown
            )

    # ------------------------------------------------------

    def sync_lifecycles(self, order_registry, bar=0):
        """
        Phase 4F STEP 9: reconcile the economic lifecycle against
        every TERMINAL order in the OrderRegistry. Called by the
        Backtester at the END of every candle, AFTER the expiry
        pass, so a fingerprint whose order just EXPIRED / was
        INVALIDATED enters COOLDOWN before the next candle's
        structural discoveries are funneled.
        """

        if order_registry is None:

            return

        for order in order_registry.terminal():

            fp = fingerprint_of(order)

            if not fp:

                continue

            terminal_bar = getattr(
                order, "terminal_bar", None
            )

            if terminal_bar is None:

                continue

            self.mark_terminal(
                fp, order.status, terminal_bar
            )

    # ------------------------------------------------------

    def _in_cooldown(self, fp, bar):
        """
        True while a fingerprint's re-entry is suppressed at `bar`
        (COOLDOWN, expiring as soon as the window lapses). A no-op
        when no cooldown was ever set.
        """

        until = self._cooldown_until.get(fp, 0)

        if not until:

            return False

        if bar <= until:

            return True

        # Cooldown lapsed: a fresh structural discovery of the same
        # economics is legal again.
        self._cooldown_until.pop(fp, None)

        return False

    # ------------------------------------------------------

    def lifecycle_of(self, fp):

        return self._lifecycle.get(fp, "")

    # ------------------------------------------------------

    def summary(self):

        return {
            "structural_observed": self.structural_observed,
            "distinct_structural_ids": len(self._structural_ids),
            "pre_ordered": self.pre_ordered,
            "duplicates_suppressed": self.duplicates_suppressed,
            "reentry_cooldown_suppressed": (
                self.reentry_cooldown_suppressed
            ),
            "distinct_fingerprints": self.distinct_fingerprints,
            "clusters_formed": self.clusters_formed,
            "canonical_selected": self.canonical_selected,
            "cooldown_active": len(self._cooldown_until),
        }