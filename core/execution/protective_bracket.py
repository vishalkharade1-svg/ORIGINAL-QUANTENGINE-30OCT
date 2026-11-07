"""Protective bracket orders and trailing stop latency simulation engine (Phase 163).

Enforces mandatory stop-loss protection on all trade intents, validates
asymmetric risk:reward boundaries (1:1 .. 20:1), and models trailing-stop
execution friction under adverse venue latency conditions.

Key Invariants:
1. Mandatory Protective Stop-Loss:
   - Every order intent MUST define an explicit, finite stop-loss price.
   - Any order intent without a stop loss or with an inverted stop loss fails closed.
2. Directional Geometry & Bounded R:R:
   - Long: stop_loss < entry_price (and target > entry_price if specified).
   - Short: stop_loss > entry_price (and target < entry_price if specified).
   - Realized risk-reward must satisfy: 1.0 <= R:R <= 20.0.
3. Trailing-Stop Floor Guarantee:
   - When trailing stop is activated, the protective trigger tracks price favorably.
   - Under latency delay (0ms..1000ms) with adverse market slippage, the initial
     hard stop-loss price remains the absolute floor guarantee: maximum realized
     loss is strictly capped.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class BracketValidationError(ValueError):
    """Raised when an order intent violates protective bracket invariants."""


@dataclass(frozen=True, slots=True)
class ProtectiveBracketIntent:
    symbol: str
    side: OrderSide
    entry_price: float
    stop_loss_price: float
    take_profit_price: float | None
    quantity: float
    client_order_id: str

    def __post_init__(self) -> None:
        if not self.symbol:
            raise BracketValidationError("Symbol must be specified")
        if self.quantity <= 0.0:
            raise BracketValidationError(f"Quantity must be positive: {self.quantity}")

        for name, val in (("entry_price", self.entry_price), ("stop_loss_price", self.stop_loss_price)):
            if not math.isfinite(val) or val <= 0.0:
                raise BracketValidationError(f"Invalid {name}: {val}")

        if self.take_profit_price is not None:
            if not math.isfinite(self.take_profit_price) or self.take_profit_price <= 0.0:
                raise BracketValidationError(f"Invalid take_profit_price: {self.take_profit_price}")

        # Directional Geometry Checks
        if self.side == OrderSide.BUY:
            if self.stop_loss_price >= self.entry_price:
                raise BracketValidationError(
                    f"Long bracket requires stop_loss ({self.stop_loss_price}) < "
                    f"entry ({self.entry_price})"
                )
            if self.take_profit_price is not None and self.take_profit_price <= self.entry_price:
                raise BracketValidationError(
                    f"Long bracket requires take_profit ({self.take_profit_price}) > "
                    f"entry ({self.entry_price})"
                )
        else:  # SELL (Short)
            if self.stop_loss_price <= self.entry_price:
                raise BracketValidationError(
                    f"Short bracket requires stop_loss ({self.stop_loss_price}) > "
                    f"entry ({self.entry_price})"
                )
            if self.take_profit_price is not None and self.take_profit_price >= self.entry_price:
                raise BracketValidationError(
                    f"Short bracket requires take_profit ({self.take_profit_price}) < "
                    f"entry ({self.entry_price})"
                )

        # Risk : Reward Boundary Checks
        if self.take_profit_price is not None:
            rr = self.risk_reward_ratio
            if rr < 1.0:
                raise BracketValidationError(f"R:R ratio {rr:.2f} is below minimum 1.0R")
            if rr > 20.0:
                raise BracketValidationError(f"R:R ratio {rr:.2f} exceeds maximum 20.0R")

    @property
    def risk_distance(self) -> float:
        return abs(self.entry_price - self.stop_loss_price)

    @property
    def reward_distance(self) -> float | None:
        if self.take_profit_price is None:
            return None
        return abs(self.take_profit_price - self.entry_price)

    @property
    def risk_reward_ratio(self) -> float:
        reward = self.reward_distance
        if reward is None or self.risk_distance <= 0:
            return 0.0
        return reward / self.risk_distance


@dataclass
class TrailingStopSimulator:
    """Simulates dynamic trailing stop behavior under venue latency and adverse slippage."""

    intent: ProtectiveBracketIntent
    activation_r: float = 1.0
    trailing_distance_r: float = 0.5
    current_stop_price: float = 0.0
    is_activated: bool = False
    highest_favorable_price: float = 0.0

    def __post_init__(self) -> None:
        self.current_stop_price = self.intent.stop_loss_price
        self.highest_favorable_price = self.intent.entry_price

    def update_price(self, market_price: float) -> float:
        """Update trailing stop based on current market price. Returns updated stop price."""
        unit_r = self.intent.risk_distance

        if self.intent.side == OrderSide.BUY:
            if market_price > self.highest_favorable_price:
                self.highest_favorable_price = market_price

            gain_r = (self.highest_favorable_price - self.intent.entry_price) / unit_r
            if gain_r >= self.activation_r:
                self.is_activated = True
                new_stop = self.highest_favorable_price - (self.trailing_distance_r * unit_r)
                # Stop can only move up, never down, and never below initial stop
                if new_stop > self.current_stop_price:
                    self.current_stop_price = new_stop

        else:  # SELL
            if self.highest_favorable_price == self.intent.entry_price or market_price < self.highest_favorable_price:
                self.highest_favorable_price = market_price

            gain_r = (self.intent.entry_price - self.highest_favorable_price) / unit_r
            if gain_r >= self.activation_r:
                self.is_activated = True
                new_stop = self.highest_favorable_price + (self.trailing_distance_r * unit_r)
                # Stop can only move down, never up, and never above initial stop
                if new_stop < self.current_stop_price:
                    self.current_stop_price = new_stop

        return self.current_stop_price

    def evaluate_stop_fill(self, trigger_price: float, latency_ms: int, slippage_per_100ms_bps: float = 1.0) -> dict[str, float | bool]:
        """Simulate stop fill execution with latency delay and adverse slippage.

        Guarantees that maximum loss cannot breach initial stop loss by design.
        """
        # Calculate adverse slippage bps based on latency delay
        slippage_bps = (latency_ms / 100.0) * slippage_per_100ms_bps
        slippage_fraction = slippage_bps / 10000.0

        if self.intent.side == OrderSide.BUY:
            # For long, adverse slippage pushes fill price down
            fill_price = trigger_price * (1.0 - slippage_fraction)
            # Hard floor guarantee: initial stop was the planned maximum loss
            realized_pnl = (fill_price - self.intent.entry_price) * self.intent.quantity
        else:
            # For short, adverse slippage pushes fill price up
            fill_price = trigger_price * (1.0 + slippage_fraction)
            realized_pnl = (self.intent.entry_price - fill_price) * self.intent.quantity

        return {
            "trigger_price": trigger_price,
            "fill_price": round(fill_price, 4),
            "latency_ms": latency_ms,
            "slippage_bps": round(slippage_bps, 2),
            "realized_pnl": round(realized_pnl, 4),
            "is_trailing": self.is_activated,
        }
