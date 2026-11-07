"""
====================================================

QuantEngine

Execution Engine

Consumes:
    context.decision

Produces:
    Orders

====================================================
"""

from config import risk_settings

from core.common.base_engine import BaseEngine
from core.common.logging_config import get_logger

log = get_logger(__name__)


def pending_total_capacity(legacy_max=1):
    """
    Phase 4F STEP 8: the TOTAL pending-order budget -- the smaller
    of MAX_PENDING_ORDERS_TOTAL and MAX_PENDING_ORDERS_PER_SYMBOL.
    Reads MAX_PENDING_ORDERS_TOTAL with the Phase 4D MAX_PENDING_
    ORDERS key as the legacy fallback so pre-4F embeddings configure
    the same knob. A silent zero (bad config) degrades to 1 -- never
    a silently unlimited funnel.
    """

    total = getattr(
        risk_settings, "MAX_PENDING_ORDERS_TOTAL", None
    )

    if total is None:

        total = getattr(
            risk_settings, "MAX_PENDING_ORDERS", legacy_max
        )

    per_symbol = getattr(
        risk_settings, "MAX_PENDING_ORDERS_PER_SYMBOL", total
    )

    total = int(total or legacy_max)

    per_symbol = int(per_symbol or total)

    return max(min(total, per_symbol), 1)


def pending_direction_capacity():
    """
    Phase 4F STEP 8: the per-direction pending budget
    (MAX_PENDING_ORDERS_PER_DIRECTION). Overlapping same-direction
    BTC exposure can never silently consume every slot.
    """

    per_direction = getattr(
        risk_settings, "MAX_PENDING_ORDERS_PER_DIRECTION", 4
    )

    return max(int(per_direction or 4), 1)


class ExecutionEngine(BaseEngine):

    priority = 700

    dependencies = [
        "DecisionEngine",
    ]

    enabled = True

    def __init__(self):

        super().__init__()

    # -------------------------------------------------

    def analyze(self, context):

        registry = context.decision

        if registry is None:

            # No decision produced this candle: clear any
            # previously selected signals so a stale setup can
            # never be re-entered by the backtester/simulator
            # on a later candle.
            context.execution_signals = None
            context.execution_signal = None
            return

        setups = registry.all()

        if not setups:

            context.execution_signals = None
            context.execution_signal = None
            return

        order_registry = getattr(
            context, "order_registry", None
        )

        # =====================================================
        # Phase 4C idempotency (Step 5) plus Phase 4D STEP 8:
        # the persistent OrderRegistry is the primary source of
        # truth. A setup that ALREADY has a primary order --
        # PENDING, FILLED or terminal -- must never be emitted,
        # risk-checked or ordered again.
        # =====================================================

        # =====================================================
        # Phase 4E economic funnel: BEFORE the pending-slot cap is
        # applied, the EconomicSetupRegistry collapses economically
        # duplicate setups (identical tick-normalized fingerprints,
        # whether from a live pending order or within this candle)
        # and clusters near-identical execution zones, then returns
        # only the ranked canonical representatives. The slot cap
        # below therefore spends MAX_PENDING_ORDERS on INDEPENDENT
        # opportunities -- never on two variants of one idea.
        # An absent economic registry (legacy embedding) falls
        # through with Phase 4C/4D behavior unchanged.
        # =====================================================

        economic_registry = getattr(
            context, "economic_registry", None
        )

        if (
            economic_registry is not None
            and order_registry is not None
        ):

            setups = economic_registry.observe(
                setups,
                order_registry,
                bar=getattr(context, "current_index", 0),
            )

        # =====================================================
        # Phase 4F STEP 3: record the surviving canonical setups in
        # the persistent EntryTracker (post-economic-funnel, before
        # the pending-slot cap). One record per structural_id on its
        # FIRST canonical appearance; the tracker then measures what
        # price actually does AFTER this candle -- diagnostics only,
        # never a signal. An absent tracker (legacy embedding) is
        # a no-op.
        # =====================================================

        tracker = getattr(context, "entry_tracker", None)

        if tracker is not None:

            tracker.track(
                setups,
                bar=getattr(context, "current_index", 0),
                order_registry=order_registry,
            )

        # From the remaining canonical accepted setups we emit the
        # top pending-budget by score (ties keep registration
        # order, so determinism is preserved), capped by how many
        # pending slots the registry still has AND by the
        # per-direction budget (Phase 4F STEP 8). Accepted setups
        # are never silently dropped: they queue and a slot frees on
        # the next fill/expiry/invalidation.

        pending_slots = 0

        max_pending = pending_total_capacity()

        per_direction = pending_direction_capacity()

        if order_registry is not None:

            pending_slots = max(
                max_pending - len(order_registry.pending()),
                0,
            )

        else:

            pending_slots = max_pending

        chosen = []

        chosen_direction = {}

        for setup in sorted(
            setups,
            key=lambda s: (-s.score, 0),
        ):

            if len(chosen) >= pending_slots:

                break

            direction = (
                getattr(setup, "direction", "") or ""
            ).upper()

            # Phase 4F STEP 8: per-direction pending budget --
            # overlapping same-direction exposure can never consume
            # every slot.
            live_direction = (
                sum(
                    1
                    for o in order_registry.pending()
                    if (o.direction or "").upper() == direction
                )
                if order_registry is not None
                else 0
            ) + chosen_direction.get(direction, 0)

            if live_direction >= per_direction:

                continue

            setup_id = getattr(setup, "setup_id", "") or ""

            if (
                order_registry is not None
                and setup_id
                and order_registry.has_order_for_setup(setup_id)
            ):

                existing = order_registry.get_by_setup_id(setup_id)

                log.debug(
                    "ExecutionEngine skipped re-emission for %s "
                    "order %s status=%s (one setup == one order)",
                    setup_id,
                    existing.order_id if existing is not None
                    else "?",
                    existing.status if existing is not None else "?",
                )

                continue

            chosen.append(setup)

            chosen_direction[direction] = (
                chosen_direction.get(direction, 0) + 1
            )

        context.execution_signals = chosen or None

        context.execution_signal = chosen[0] if chosen else None

    # -------------------------------------------------

    def reset(self):

        pass