"""
====================================================

QuantEngine

Order Registry

The persistent, cross-cycle source of truth for the
Phase 4C execution-lifecycle invariant:

    ONE SETUP ID == MAXIMUM ONE PRIMARY ORDER == ONE TRADE

Lives on the shared PipelineContext (session state, exactly
like AccountState and the signal cache), so EVERY mode --
Backtest / Paper / Live Broker, and the portfolio multi-
symbol backtester -- dedupes through the SAME registry.

The registry is created by PipelineContext.__post_init__ and
re-created on a full reset() so a fresh run starts empty; it
is deliberately NOT touched by reset_cycle(), which only
clears per-candle pipeline outputs.

Order lifecycle states stored on each OrderIntent:

    NEW      (created by RiskEngine, not yet registered)
    PENDING  (registered by OrderRegistry.create)
    FILLED   (consumed exactly once by a mode adapter)
    CANCELLED / REJECTED / EXPIRED (terminal, cannot fill)

Trade lifecycle is tracked on the Trade itself via its
status (OPEN / CLOSED). Setup lifecycle is tracked on the
SetupCandidate (NEW / ACCEPTED / ORDER_CREATED / FILLED /
CLOSED / INVALIDATED / EXPIRED).

====================================================
"""

from config import risk_settings


# Order status constants (Step 6 of Phase 4C; INVALIDATED added
# by Phase 4D STEP 6 so a thesis break is NOT classified as an
# expiration).
NEW = "NEW"
PENDING = "PENDING"
FILLED = "FILLED"
CANCELLED = "CANCELLED"
REJECTED = "REJECTED"
EXPIRED = "EXPIRED"
INVALIDATED = "INVALIDATED"

# Stage 1-3 hardening: exchange-observed transit states. These are
# NEVER written by OrderRegistry (the registry only tracks the local
# lifecycle above) — they exist so the reconciler and tests name the
# same thing: an exchange-acknowledged or partially-filled order is
# NOT a FILLED order. PARTIAL == FILLED is forbidden without explicit
# fill evidence; a quantity divergence halts new orders (see
# core/live/reconciler.py PARTIAL_FILL_QTY). The simulator is
# single-slot all-or-nothing by design; partials are handled
# fail-closed at reconciliation, never by silent completion.
SUBMITTED = "SUBMITTED"
ACKNOWLEDGED = "ACKNOWLEDGED"
PARTIAL = "PARTIAL"


class OrderRegistry:
    """
    Keyed by both order_id and setup_id.

        create(order, bar=None, timestamp=None)
                                     -> stamps NEW -> PENDING,
                                     assigns order_id + Phase 4D
                                     bar metadata, returns it
        get(order_id)
        get_by_setup_id(setup_id)
        has_order_for_setup(setup_id)
        pending() / filled() / terminal()
        advance(bar=None, timestamp=None)
                                     -> (bar-based) expires orders
                                     whose current bar passes
                                     expires_at_bar, or (barless,
                                     legacy) counter-ages pending
                                     orders past MAX_WAIT_BARS
        invalidate(order, ...)       -> PENDING -> INVALIDATED
        mark_filled(order_id, trade)
                                     -> FILLED + trade_id linkage

    The critical invariant is enforced at has_order_for_setup
    -- callers (ExecutionEngine before risk validation, and
    RiskEngine before order creation) must SKIP when it returns
    True. create() also re-checks and returns the EXISTING
    order rather than silently minting a duplicate.
    """

    def __init__(self, max_wait_bars=None):

        self.max_wait_bars = (
            max_wait_bars
            if max_wait_bars is not None
            else risk_settings.MAX_WAIT_BARS
        )

        # order_id -> order
        self._orders = {}

        # setup_id -> order
        self._by_setup = {}

        # setup_id -> per-setup sequence counter
        self._seq = {}

    # ==================================================
    # Creation
    # ==================================================

    def create(self, order, bar=None, timestamp=None):
        """
        Register a primary order for a setup. One setup_id may
        ever hold exactly one primary order in this registry.
        Returns the (possibly pre-existing) registered order and
        its order_id.

        Phase 4D bar metadata (STEP 2): when `bar` is supplied,
        stamps created_bar / created_timestamp and derives the
        eligibility window:

            eligible_from_bar = created_bar + ENTRY_DELAY_BARS
            expires_at_bar     = eligible_from_bar + max_wait_bars

        The eligibility window is stamped exactly once, at first
        registration, so a pre-existing order keeps its original
        window even if create() is hit again on a later bar.
        """

        setup_id = getattr(order, "setup_id", "") or ""

        if setup_id:

            existing = self._by_setup.get(setup_id)

            if existing is not None:

                return existing, existing.order_id

        order_id = getattr(order, "order_id", "") or ""

        if order_id and order_id in self._orders:

            return self._orders[order_id], order_id

        if not order_id:

            order_id = self._mint_order_id(setup_id, order)

        order.order_id = order_id
        order.status = PENDING
        order.wait_bars = getattr(order, "wait_bars", 0)

        if bar is not None and order.eligible_from_bar in (None, 0):

            delay = getattr(
                risk_settings, "ENTRY_DELAY_BARS", 1
            )

            order.created_bar = bar
            order.created_timestamp = timestamp
            order.eligible_from_bar = bar + delay
            order.expires_at_bar = (
                order.eligible_from_bar + self.max_wait_bars
            )

        self._orders[order_id] = order

        if setup_id:

            self._by_setup[setup_id] = order

        return order, order_id

    # ==================================================

    def _mint_order_id(self, setup_id, order):

        if setup_id:

            self._seq[setup_id] = self._seq.get(setup_id, 0) + 1

            return f"{setup_id}-ORDER-{self._seq[setup_id]}"

        symbol = getattr(order, "symbol", "") or ""

        self._seq[symbol] = self._seq.get(symbol, 0) + 1

        return f"{symbol}-ORDER-{self._seq[symbol]}"

    # ==================================================
    # Lookup
    # ==================================================

    def get(self, order_id):

        return self._orders.get(order_id)

    # --------------------------------------------------

    def get_by_setup_id(self, setup_id):

        return self._by_setup.get(setup_id)

    # --------------------------------------------------

    def has_order_for_setup(self, setup_id):

        return setup_id in self._by_setup

    # ==================================================
    # Lifecycle filters
    # ==================================================

    def all(self):

        return list(self._orders.values())

    # --------------------------------------------------

    def by_status(self, *statuses):

        wanted = set(statuses)

        return [
            o
            for o in self._orders.values()
            if o.status in wanted
        ]

    # --------------------------------------------------

    def pending(self):

        return self.by_status(PENDING)

    # --------------------------------------------------

    def filled(self):

        return self.by_status(FILLED)

    # --------------------------------------------------

    def expired(self):

        return self.by_status(EXPIRED)

    # --------------------------------------------------

    def invalidated(self):

        return self.by_status(INVALIDATED)

    # --------------------------------------------------

    def rejected(self):

        return self.by_status(REJECTED, CANCELLED)

    # --------------------------------------------------

    def terminal(self):

        return self.by_status(
            FILLED, CANCELLED, REJECTED, EXPIRED, INVALIDATED
        )

    # ==================================================
    # Transitions
    # ==================================================

    def advance(self, bar=None, timestamp=None):
        """
        End-of-candle expiry pass. Returns the list of orders
        expired by THIS call.

        Bar-anchored mode (Phase 4D): when `bar` is supplied and
        the order carries an expires_at_bar window, an order is
        EXPIRED only when bar >= expires_at_bar. Because the
        backtester runs this pass AFTER the candle's fill and
        invalidation checks, the expiry candle itself still gets
        its fill chance before the order is terminaled.

        Legacy counter mode: when no bar is supplied (or the
        order has no expiry window, e.g. scripted registry unit
        tests), the historical wait_bars += 1 behaviour is kept
        so callers that never opted into bar metadata are
        unchanged.
        """

        expired = []

        for order in self.pending():

            if bar is not None and order.expires_at_bar is not None:

                created = getattr(order, "created_bar", None)

                if created is not None:

                    order.wait_bars = max(
                        order.wait_bars,
                        bar - created,
                    )

                if bar >= order.expires_at_bar:

                    self._transition(order, EXPIRED)

                    order.terminal_bar = bar

                    order.waited_bars = max(
                        order.expires_at_bar
                        - order.eligible_from_bar,
                        0,
                    )

                    expired.append(order)

                continue

            order.wait_bars = (
                getattr(order, "wait_bars", 0) + 1
            )

            if order.wait_bars > self.max_wait_bars:

                self._transition(order, EXPIRED)

                order.terminal_bar = getattr(
                    order, "created_bar", None
                ) or bar

                expired.append(order)

        return expired

    # --------------------------------------------------

    def invalidate(self, order, reason="", bar=None, price=None, level=None):
        """
        Phase 4D STEP 6: classify a structural thesis break --
        the stop (order-block boundary) was breached -- as
        INVALIDATED, NOT as an expiration. A pending order that
        reached its entry first is allowed to fill; invalidation
        is only the terminal path when the structural level broke
        first on an eligible bar. No-op for anything not PENDING.
        Returns True when the order was terminaled here.
        """

        if order is None:

            return False

        if order.status != PENDING:

            return False

        self._transition(order, INVALIDATED)

        order.terminal_bar = bar

        order.waited_bars = max(
            bar - (order.eligible_from_bar or bar),
            0,
        )

        order.reason = reason

        order.invalidation_level = (
            level if level is not None
            else getattr(order, "invalidation_level", 0.0)
        )

        order.invalidation_price = price if price is not None else 0.0

        return True

    # --------------------------------------------------

    def mark_filled(self, order, trade=None):
        """
        Consume a PENDING order exactly once. Assigns the
        trade_id (setup -> ORDER -> TRADE chain) onto both the
        order and the fill. No-op for anything not PENDING.
        Returns the trade_id or None.
        """

        if order is None:

            return None

        if order.status != PENDING:

            return None

        if trade is not None:

            trade_id = self._mint_trade_id(
                getattr(order, "setup_id", "") or "",
                order.order_id,
            )

            order.trade_id = trade_id
            order.status = FILLED

            trade.trade_id = trade_id
            trade.setup_id = order.setup_id
            trade.order_id = order.order_id

            if hasattr(trade, "status"):

                trade.status = "OPEN"

            return trade_id

        order.status = FILLED

        return None

    # --------------------------------------------------

    def _mint_trade_id(self, setup_id, order_id):

        # The order_id is the more specific base: a trade id like
        # "...-ORDER-1-TRADE-1" traces straight back to its order,
        # and only falls back to the setup id / a bare "TRADE" id
        # when no order identity exists (legacy scripted flows).
        base = order_id or setup_id

        if not base:

            base = "TRADE"

        self._seq[base] = self._seq.get(base, 0) + 1

        return f"{base}-TRADE-{self._seq[base]}"

    # --------------------------------------------------

    def _transition(self, order, status):

        order.status = status

        setup_id = getattr(order, "setup_id", "") or ""

        setup = getattr(order, "setup", None)

        lifecycle = getattr(setup, "lifecycle", "")

        if setup is not None and status == FILLED:

            setup.lifecycle = "FILLED"

        elif status == EXPIRED and setup is not None:

            setup.lifecycle = "EXPIRED"

        # Inherit the terminal state onto the setup lifecycle so
        # a terminal setup is never eligible again.
        if setup is not None and lifecycle not in (
            "FILLED", "CLOSED"
        ):

            setup.lifecycle = status

    # ==================================================
    # Reset
    # ==================================================

    def clear(self):

        self._orders.clear()

        self._by_setup.clear()

        self._seq.clear()

    def reset(self):

        self.clear()