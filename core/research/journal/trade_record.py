"""
====================================================

QuantEngine

Research Journal -- trade record (Phase 9A)

Factual outcome record for a filled -> closed trade (Trade
facts). Captures the terminal outcome (WIN / LOSS /
UNSETTLED), PnL, R multiple, exit price/bar, entry price/bar,
stop/target hit, and MAE/MFE when an authoritative source
provides it.

R is derived from the trade's own risk_amount:
    R = pnl / risk_amount   (None when risk_amount == 0)

MAE/MFE are consumed from the existing authoritative
diagnostic source (entry_shadow / causal_validation) where
available; they are NEVER fabricated here.
====================================================
"""

from dataclasses import dataclass, field

from core.research.journal.research_enums import (
    Provenance,
    Result,
)


def _r(pnl, risk_amount):
    if not risk_amount:
        return None
    return pnl / risk_amount


@dataclass
class TradeRecord:
    """Factual record of a filled trade's outcome."""

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
    exit_price: float = 0.0
    quantity: float = 0.0
    risk_amount: float = 0.0
    entry_mode: str = ""

    entry_bar: int = None
    exit_bar: int = None
    entry_time: object = None
    exit_time: object = None
    bars_held: int = 0

    result: str = Result.UNSETTLED.value
    pnl: float = 0.0
    commission: float = 0.0
    slippage: float = 0.0
    funding: float = 0.0
    funding_events: int = 0
    stop_hit: bool = False
    target_hit: bool = False

    mae: float = None
    mfe: float = None

    @property
    def r(self):
        return _r(self.pnl, self.risk_amount)

    @property
    def won(self):
        return self.result == Result.WIN.value

    @property
    def lost(self):
        return self.result == Result.LOSS.value

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
            "exit_price": self.exit_price,
            "quantity": self.quantity,
            "risk_amount": self.risk_amount,
            "entry_mode": self.entry_mode,
            "entry_bar": self.entry_bar,
            "exit_bar": self.exit_bar,
            "entry_time": self.entry_time,
            "exit_time": self.exit_time,
            "bars_held": self.bars_held,
            "result": self.result,
            "pnl": self.pnl,
            "commission": self.commission,
            "slippage": self.slippage,
            "funding": self.funding,
            "funding_events": self.funding_events,
            "stop_hit": self.stop_hit,
            "target_hit": self.target_hit,
            "mae": self.mae,
            "mfe": self.mfe,
            "r": self.r,
        }
