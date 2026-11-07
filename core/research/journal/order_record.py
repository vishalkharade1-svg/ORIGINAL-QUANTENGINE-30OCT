"""
====================================================

QuantEngine

Research Journal -- order record (Phase 9A)

Factual lifecycle + excursion record for a created order
(OrderIntent facts). Captures created / pending / filled /
expired / invalidated status, bar metadata, entry price, and
the observed excursion facts for UNFILLED opportunities:

   min_low_since_creation / max_high_since_creation
   entry_distance_from_nearest_price
   bars_pending

These are OBSERVED market facts -- never a hypothetical fill.

OBSERVED FACTS ONLY; optional fields remain optional.
====================================================
"""

from dataclasses import dataclass, field

from core.research.journal.research_enums import (
    Provenance,
    OrderLifecycle,
    EntryReached,
)


@dataclass
class OrderRecord:
    """Factual record of an order's lifecycle + excursion."""

    provenance: str = Provenance.BACKTEST.value
    exchange: str = ""
    instrument_id: str = ""
    timeframe: str = ""
    direction: str = ""
    strategy: str = ""
    setup_id: str = ""
    canonical_id: str = ""
    order_id: str = ""
    trade_id: str = ""

    entry: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    risk_reward: float = 0.0
    risk_amount: float = 0.0
    expected_loss: float = 0.0
    expected_profit: float = 0.0
    position_value: float = 0.0
    entry_mode: str = ""
    score: float = 0.0
    confidence: float = 0.0

    status: str = OrderLifecycle.CREATED.value
    created_bar: int = None
    eligible_from_bar: int = None
    expires_at_bar: int = None
    filled_bar: int = None
    terminal_bar: int = None
    waited_bars: int = 0
    bars_pending: int = 0

    entry_reached: str = EntryReached.NOT_REACHED.value
    entry_distance_from_nearest_price: float = None
    min_low_since_creation: float = None
    max_high_since_creation: float = None

    reason: str = ""

    @property
    def terminal(self):
        return self.status in (
            OrderLifecycle.FILLED.value,
            OrderLifecycle.EXPIRED.value,
            OrderLifecycle.INVALIDATED.value,
            OrderLifecycle.REJECTED.value,
            OrderLifecycle.CANCELLED.value,
        )

    @property
    def filled(self):
        return self.status == OrderLifecycle.FILLED.value

    def to_dict(self):
        return {
            "provenance": str(self.provenance),
            "exchange": self.exchange,
            "instrument_id": self.instrument_id,
            "timeframe": self.timeframe,
            "direction": self.direction,
            "strategy": self.strategy,
            "setup_id": self.setup_id,
            "canonical_id": self.canonical_id,
            "order_id": self.order_id,
            "trade_id": self.trade_id,
            "entry": self.entry,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "risk_reward": self.risk_reward,
            "risk_amount": self.risk_amount,
            "expected_loss": self.expected_loss,
            "expected_profit": self.expected_profit,
            "position_value": self.position_value,
            "entry_mode": self.entry_mode,
            "score": self.score,
            "confidence": self.confidence,
            "status": self.status,
            "created_bar": self.created_bar,
            "eligible_from_bar": self.eligible_from_bar,
            "expires_at_bar": self.expires_at_bar,
            "filled_bar": self.filled_bar,
            "terminal_bar": self.terminal_bar,
            "waited_bars": self.waited_bars,
            "bars_pending": self.bars_pending,
            "entry_reached": self.entry_reached,
            "entry_distance_from_nearest_price": self.entry_distance_from_nearest_price,
            "min_low_since_creation": self.min_low_since_creation,
            "max_high_since_creation": self.max_high_since_creation,
            "reason": self.reason,
        }
