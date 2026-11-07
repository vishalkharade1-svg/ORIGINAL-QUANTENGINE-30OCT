"""
====================================================

QuantEngine

Order Intent

The risk-validated order produced by RiskEngine.

Consumes: a SetupCandidate (context.execution_signal) plus
the computed PositionSize from the PositionSizer.

Produced by: core.risk.risk_engine.RiskEngine
Consumed by: backtesting/backtester.py (which reads
context.order and hands it to the TradeSimulator) and
core/backtesting/trade_simulator.py (which reads
quantity / commission / slippage).

====================================================
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class OrderIntent:

    # -------------------------------------------------
    # Trade
    # -------------------------------------------------

    direction: str = ""

    entry: float = 0.0

    stop_loss: float = 0.0

    take_profit: float = 0.0

    risk_reward: float = 0.0

    # Exit policy carried unchanged from the validated setup.
    exit_mode: str = "FIXED_TARGET"
    trailing_activation_r: float = 0.0
    trailing_distance_r: float = 0.0
    trailing_enabled: bool = False
    trailing_method: str = "R_DISTANCE"
    trailing_step_r: float = 0.0

    # Stage 4: REALIZED reward:risk at the actual fill price,
    # SIGNED by side (accounting.realized_rr convention: positive
    # = distance remains toward target; negative = fill beyond
    # target or target on wrong side; 0.0 = no mutating fill or
    # degenerate risk). Stamped ONLY by fill paths that mutate
    # `entry` after the gates ran (Backtester NEXT_BAR_OPEN market
    # fill at the next open). `risk_reward` keeps the gated
    # order-time value; this field records what the market
    # actually gave, so fill-price RR erosion is measured, never
    # hidden. 0.0 means "filled at decision price / not a
    # mutating fill".
    actual_risk_reward: float = 0.0

    # -------------------------------------------------
    # Position
    # -------------------------------------------------

    quantity: float = 0.0

    risk_percent: float = 0.0

    risk_amount: float = 0.0

    # Phase 11E-Prep H1-D: post-cap ACTUAL risk percent
    # (fraction of balance truly on the line at the final
    # executable quantity). risk_percent/risk_amount carry
    # the sizer's requested (pre-manager-cap) sizing;
    # actual_risk_percent is aligned to the final position
    # (final_quantity x stop_distance / balance). Consumers
    # that need truthful risk must read this field, not the
    # requested one.
    actual_risk_percent: float = 0.0

    expected_loss: float = 0.0

    expected_profit: float = 0.0

    position_value: float = 0.0

    leverage: float = 1.0

    # -------------------------------------------------
    # Execution Costs
    # -------------------------------------------------

    commission: float = 0.0

    slippage: float = 0.0

    # -------------------------------------------------
    # Quality
    # -------------------------------------------------

    confidence: float = 0.0

    score: float = 0.0

    # -------------------------------------------------
    # Identity
    # -------------------------------------------------

    symbol: str = ""

    timeframe: str = ""

    # Phase 4C identity chain. setup_id comes from the
    # originating SetupCandidate; order_id and trade_id are
    # stamped by the OrderRegistry (setup -> order -> trade).
    # status carries the ORDER lifecycle (NEW / PENDING /
    # FILLED / CANCELLED / REJECTED / EXPIRED), separate from
    # the setup lifecycle on SetupCandidate and the trade
    # lifecycle on Trade.
    setup_id: str = ""

    # Phase 4E: the structural identity of the originating setup
    # (equals SetupCandidate.structural_id / setup_id). Economic
    # deduplication links duplicates onto the canonical structural
    # id via EconomicSetupRegistry.
    structural_id: str = ""

    # Phase 4E: the tick-normalized economic fingerprint (symbol,
    # timeframe, direction, entry/stop/target buckets) stamped from
    # the originating SetupCandidate. Identical economics from
    # different order-block structures share one fingerprint, which
    # is what lets the EconomicSetupRegistry suppress economically
    # duplicate orders before RiskEngine ever mints them.
    economic_fingerprint: str = ""

    # Phase 4F: the entry mode the originating setup carried
    # (LIMIT_RETEST baseline). Copied VERBATIM by RiskEngine so the
    # entry model is preserved end-to-end; the backtester's fill
    # gate only fills modes listed in ACTIVE_ENTRY_MODES.
    entry_mode: str = ""

    # Phase 5B: the order-execution channel this order enters with,
    # derived from entry_mode by the canonical entry model
    # (EXECUTION_LIMIT for every mode BUT BREAKOUT_CONTINUATION,
    # which uses EXECUTION_NEXT_BAR_OPEN -- a market fill at the
    # OPEN of the trigger bar + 1, decided under the Phase 4H
    # causal trigger rules). Defaults to "LIMIT" so every legacy
    # order is byte-identical.
    entry_execution: str = "LIMIT"

    # Phase 4F: the entry-feasibility CLASS (ENTRY_IMMEDIATE /
    # ENTRY_NEAR / ENTRY_RETRACE / ENTRY_DEEP_RETRACE /
    # ENTRY_TOO_FAR), copied from the setup's feasibility snapshot
    # so orders can be sliced by feasibility in the regression
    # report. Diagnostic only.
    entry_feasibility: str = ""

    # Phase 6C: the canonical multi-symbol setup identity
    # ({exchange}:{instrument_id}:{timeframe}:{direction}:{strategy}:{setup_id}),
    # copied VERBATIM by RiskEngine from the originating
    # SetupCandidate -- never reconstructed here so the whole
    # execution chain sees one unchanged identity.
    canonical_id: str = ""

    order_id: str = ""

    trade_id: str = ""

    status: str = "NEW"

    # Candles spent as a PENDING order; aged by
    # OrderRegistry.advance() and used to expire stale orders.
    wait_bars: int = 0

    # -------------------------------------------------
    # Bar Metadata (Phase 4D integrity)
    # -------------------------------------------------

    # Bar (1-based replay index of the candle that formed the
    # signal) at which the order was created, and the wall clock
    # of that candle. Stamped by OrderRegistry.create() when a
    # bar is supplied.
    created_bar: int = None

    created_timestamp: Any = None

    # First bar on which the order may fill / be invalidated:
    # created_bar + risk_settings.ENTRY_DELAY_BARS (default 1 --
    # the conservative no-same-candle-look-ahead rule).
    eligible_from_bar: int = None

    # Last bar on which the order may fill: eligible_from_bar +
    # max_wait_bars. Expiry is processed at the END of a candle
    # whose bar >= expires_at_bar -- after that candle's fill /
    # invalidation check.
    expires_at_bar: int = None

    # Bar on which the order filled / was invalidated / expired
    # (set once, on the single terminal event).
    filled_bar: int = None

    terminal_bar: int = None

    # Bars waited while eligible: event_bar - eligible_from_bar
    # (a fill / invalidation / expiry diagnostic).
    waited_bars: int = 0

    # -------------------------------------------------
    # Excursion Tracking (Phase 4E)
    # -------------------------------------------------

    # Lifetime high-water / low-water of price observed on EVERY
    # eligible pending candle -- NOT only the expiry candle, so an
    # ORDER_EXPIRED diagnostic can prove whether the market ever
    # reached the entry while the order was alive. Initialized on
    # the FIRST eligible candle (the creation candle is ineligible
    # under the no-same-candle-look-ahead rule and contributes
    # nothing), then rolled each eligible candle:
    #
    #     min_low_since_creation = min(..., candle.low)
    #     max_high_since_creation = max(..., candle.high)
    #
    # Entries are null until an eligible candle has been processed
    # once. bars_pending counts the eligible candles the order has
    # been carried (inclusive of the expiry bar, which still gets
    # its fill/invalidation chance).
    min_low_since_creation: float = None

    max_high_since_creation: float = None

    bars_pending: int = 0

    # Distance from the entry to the NEAREST extreme observed over
    # the order's whole eligible lifetime (0.0 when the market
    # touched the entry level -- min_low <= entry <= max_high).
    # Stamped on the terminal event for the ORDER_EXPIRED
    # diagnostic; lets the reader verify whether the market did or
    # did not reach the entry.
    entry_distance_from_nearest_price: float = None

    # Invalidation bookkeeping (structural stop breach).
    invalidation_level: float = 0.0

    invalidation_price: float = 0.0

    # -------------------------------------------------
    # Breakout trigger state (Phase 5B -- NEXT_BAR_OPEN orders)
    # -------------------------------------------------

    # Decided by the canonical BreakoutContinuationEntryModel
    # (Phase 4H RULE 2: BULLISH high > E AND close > E / BEARISH
    # low < E AND close < E, stop breach checked BEFORE the
    # trigger). The backtester stamps these on the trigger candle;
    # the order fills at the OPEN of breakout_trigger_bar + 1.
    breakout_triggered: bool = False

    breakout_trigger_bar: int = None

    breakout_trigger_close: float = None

    # -------------------------------------------------
    # Verified-contract attachment (Phase 13)
    # -------------------------------------------------

    # Optional verified-contract terms attached by provider
    # discovery (future) or tests. None (default) means
    # UNAVAILABLE: legacy float sizing applies and nothing is
    # invented. A dict with ``verified=True`` plus numeric
    # tick_size / quantity_step / minimum_quantity / multiplier
    # is ENFORCED by PositionManager.audit via
    # core.risk.contract_gate for every mode. Any other dict is
    # SYNTHETIC (labeled, never enforced as venue truth).
    contract_terms: Any = field(default=None, repr=False)

    # -------------------------------------------------
    # Status
    # -------------------------------------------------

    valid: bool = False

    reason: str = ""

    # The SetupCandidate that produced this order.
    setup: Any = field(default=None, repr=False)

    # -------------------------------------------------

    @property
    def net_exit_pnl(self) -> float:
        """
        Gross exit-based PnL (price-only) using the TP
        distance; fees/slippage are subtracted separately
        by the TradeSimulator at close time.
        """

        if self.quantity <= 0:
            return 0.0

        if self.direction == "BEARISH":
            return (self.entry - self.take_profit) * self.quantity

        return (self.take_profit - self.entry) * self.quantity

    # -------------------------------------------------

    def __bool__(self):

        return self.valid