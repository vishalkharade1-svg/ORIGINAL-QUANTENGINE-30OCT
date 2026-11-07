"""
====================================================

QuantEngine

Institutional Trade

====================================================
"""

from dataclasses import dataclass, field
import math
from typing import Any

from core.backtesting.trailing_stop import SUPPORTED_TRAILING_METHODS


@dataclass(slots=True)
class Trade:

    direction: str = ""

    entry: float = 0.0

    stop_loss: float = 0.0

    take_profit: float = 0.0

    # Exit policy. take_profit may be 0.0 for a pure trailing plan;
    # when a target is present it remains an independent exit.
    exit_mode: str = "FIXED_TARGET"

    # Explicit trailing parameters, meaningful only for TRAILING_STOP.
    trailing_activation_r: float = 0.0
    trailing_distance_r: float = 0.0
    trailing_enabled: bool = False
    trailing_method: str = "R_DISTANCE"
    trailing_step_r: float = 0.0

    # Instrument price increment used for stop rounding (0 = unknown/off).
    tick_size: float = 0.0

    # Auditable trailing state.  peak_price is the completed-close high-water
    # mark used for the trailing calculation, not the intrabar excursion.
    trailing_activated: bool = False
    trailing_peak_price: float = 0.0
    trailing_updates: int = 0
    trailing_history: list = field(default_factory=list)
    last_update_timestamp: Any = 0
    stale_update_count: int = 0

    # Excursions from entry, in initial-risk units, measured from OHLC.
    mfe_r: float = 0.0
    mae_r: float = 0.0

    # Original stop price at open time.  Active stop_loss trails on
    # TRAILING_STOP trades; this field preserves the original distance
    # so trailing-activation and trailing-distance R-multiples remain
    # anchored to the position's inception risk.
    # Read via getattr(trade, "initial_stop_loss", trade.stop_loss) in
    # trade_simulator.update() to guard against any serialisation round-trip
    # that strips unknown fields.
    initial_stop_loss: float = 0.0

    quantity: float = 0.0

    # The dollar amount at risk when the trade opened, carried
    # from OrderIntent.risk_amount so portfolio-level risk can be
    # released symmetrically when this trade closes.
    risk_amount: float = 0.0

    entry_time: int = 0

    exit_time: int = 0

    exit_price: float = 0.0

    pnl: float = 0.0

    pnl_percent: float = 0.0

    commission: float = 0.0

    slippage: float = 0.0

    funding: float = 0.0
    funding_events: int = 0

    status: str = "OPEN"

    result: str = ""

    exit_reason: str = ""

    bars_held: int = 0

    # Signal quality score at open time (copied from the setup/order's
    # `score` attribute).  No explicit Python analytics consumer reads
    # this field directly; it is included in open-trade API snapshots via
    # dataclasses.asdict() in core.monitoring.api_server._json_safe().
    # Action required: either wire into an explicit report/research record
    # with a covering test, OR deprecate via a documented API/schema change
    # before the next major release.  Do NOT delete without checking the
    # API contract.
    setup_score: float = 0.0

    confidence: float = 0.0

    # The symbol the trade was traded on, carried from
    # OrderIntent.symbol at open time so portfolio-level
    # per-symbol exposure can be released symmetrically when
    # this trade closes.
    symbol: str = ""

    # Phase 4C identity chain. Carried from the OrderIntent at
    # open time and completed by OrderRegistry.mark_filled
    # (trade_id). TRADE_CLOSED logs key off these.
    setup_id: str = ""

    order_id: str = ""

    trade_id: str = ""

    # Phase 4F: the entry mode the order filled under (LIMIT_RETEST
    # baseline), copied from the OrderIntent at open time so the
    # backtest result can be sliced by entry model.
    entry_mode: str = ""

    # Phase 6C: the canonical multi-symbol setup identity, copied
    # VERBATIM from the OrderIntent at open time so the trade is
    # sliceable by full market identity without re-derivation.
    canonical_id: str = ""

    # Phase 9Q-11: intrabar ambiguity. True when the exit bar's
    # high/low straddled BOTH SL and TP, so the true intrabar
    # order is unknown without lower-timeframe data. Conservative
    # policy: SL first (LOSS). Never silently assume favorable.
    ambiguous: bool = False

    # ------------------------------------------------------------------
    # Execution-boundary validation
    # ------------------------------------------------------------------

    _VALID_DIRECTIONS = frozenset({"BULLISH", "BEARISH"})
    _VALID_EXIT_MODES = frozenset({"FIXED_TARGET", "TRAILING_STOP"})

    def validate_executable(self) -> "Trade":
        """Raise ValueError if this Trade is not fit for execution.

        Call this at the execution boundary — after a Trade is fully
        constructed from a live setup or order — NOT in __post_init__.
        Partial Trade instances (test fixtures, record stubs, serialised
        snapshots) must remain constructable with default/empty fields
        without triggering this validation.

        Returns self so the call can be chained:
            trade = Trade(...).validate_executable()

        Raises:
            ValueError — with a descriptive message on the first violated
                         invariant.  Callers should log the message and
                         refuse to route/simulate the trade.
        """
        if self.direction not in self._VALID_DIRECTIONS:
            raise ValueError(
                f"Trade.direction must be BULLISH or BEARISH, got {self.direction!r}. "
                "An invalid direction causes the update() side-selection to silently "
                "treat the trade as the opposite direction."
            )
        if self.exit_mode not in self._VALID_EXIT_MODES:
            raise ValueError(
                f"Trade.exit_mode must be FIXED_TARGET or TRAILING_STOP, "
                f"got {self.exit_mode!r}."
            )
        if not (math.isfinite(self.entry) and self.entry > 0):
            raise ValueError(
                f"Trade.entry must be a positive finite number, got {self.entry}."
            )
        if not (math.isfinite(self.stop_loss) and self.stop_loss > 0):
            raise ValueError(
                f"Trade.stop_loss must be a positive finite number, got {self.stop_loss}."
            )
        if not (math.isfinite(self.quantity) and self.quantity > 0):
            raise ValueError(
                f"Trade.quantity must be a positive finite number, got {self.quantity}."
            )
        if not (math.isfinite(self.risk_amount) and self.risk_amount >= 0):
            raise ValueError(
                f"Trade.risk_amount must be a non-negative finite number, got {self.risk_amount}."
            )
        if not (math.isfinite(self.take_profit) and self.take_profit >= 0):
            raise ValueError(
                f"Trade.take_profit must be a non-negative finite number, got {self.take_profit}."
            )

        # Inconsistent target/stop geometry
        if self.direction == "BULLISH":
            if self.stop_loss > self.entry:
                raise ValueError(
                    f"Inconsistent BULLISH geometry: stop_loss ({self.stop_loss}) > entry ({self.entry})."
                )
            if self.take_profit > 0 and self.take_profit <= self.entry:
                raise ValueError(
                    f"Inconsistent BULLISH geometry: take_profit ({self.take_profit}) <= entry ({self.entry})."
                )
        elif self.direction == "BEARISH":
            if self.stop_loss < self.entry:
                raise ValueError(
                    f"Inconsistent BEARISH geometry: stop_loss ({self.stop_loss}) < entry ({self.entry})."
                )
            if self.take_profit > 0 and self.take_profit >= self.entry:
                raise ValueError(
                    f"Inconsistent BEARISH geometry: take_profit ({self.take_profit}) >= entry ({self.entry})."
                )

        if self.exit_mode == "TRAILING_STOP":
            if not self.trailing_enabled:
                raise ValueError(
                    "Trade.exit_mode is TRAILING_STOP but trailing_enabled is False."
                )
            if abs(self.entry - self.stop_loss) <= 0:
                raise ValueError(
                    f"Trade stop distance is zero (entry={self.entry}, "
                    f"stop_loss={self.stop_loss}) for TRAILING_STOP. Cannot calculate trailing R-multiples."
                )
            if self.trailing_activation_r <= 0 or not math.isfinite(self.trailing_activation_r):
                raise ValueError(
                    f"Trade.trailing_activation_r must be > 0 for TRAILING_STOP, "
                    f"got {self.trailing_activation_r}."
                )
            if self.trailing_distance_r <= 0 or not math.isfinite(self.trailing_distance_r):
                raise ValueError(
                    f"Trade.trailing_distance_r must be > 0 for TRAILING_STOP, "
                    f"got {self.trailing_distance_r}."
                )
            if str(self.trailing_method or "").strip().upper() not in SUPPORTED_TRAILING_METHODS:
                raise ValueError(
                    f"Unsupported Trade.trailing_method {self.trailing_method!r}."
                )
            if (not math.isfinite(self.trailing_step_r)
                    or self.trailing_step_r < 0):
                raise ValueError(
                    "Trade.trailing_step_r must be a non-negative finite number."
                )
            if not (math.isfinite(self.tick_size) and self.tick_size >= 0):
                raise ValueError(
                    "Trade.tick_size must be a non-negative finite number."
                )
        return self