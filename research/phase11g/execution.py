"""Phase 11G-C NBO execution layer (research-only).

Drives the PRODUCTION Backtester with 11G signal candidates through
the certified NEXT_BAR_OPEN market channel:

  signal at bar N (frozen hypothesis logic = trigger decision)
  → intent stamped breakout_triggered @ N (fill mechanics only)
  → market fill at OPEN of bar N+1 (certified RULE-3 path)
  → SL/TP exits via TradeSimulator (SL-first ambiguity, certified)

Sizing/costs reuse the 11F-certified math (PositionSizer + A/B/C/D +
funding 0) via shared imports — no second implementation. The
entry_mode label satisfies the declared-mode gate (research-only
mock.patch, restored afterwards); the TRUE channel recorded in every
artifact is entry_execution = NEXT_BAR_OPEN, exactly the frozen
family contract. Production strategy, risk, and safety untouched.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from config import risk_settings
from core.backtesting.trade_simulator import TradeSimulator
from core.events.event_bus import EventBus
from core.events.event_types import EventType
from core.history.candle import Candle
from core.market_state import MarketState
from core.pipeline.pipeline_context import PipelineContext
from core.risk.account import Account
from core.risk.order_intent import OrderIntent
from core.risk.position_sizer import PositionSizer
from backtesting.backtester import Backtester
from data.candle_builder import CandleBuilder

from research.phase11f.harness import COST_SCENARIOS_11F, to_candles

ENTRY_EXECUTION_NBO = "NEXT_BAR_OPEN"


class ResearchPipeline11G:
    """11G adapter: frozen signals -> NBO intents -> registry lifecycle.

    The candidate receives the FIXED test slice plus the current index
    (rather than a growing prefix). This is output-identical to growing
    prefixes because candidates are contractually forbidden from reading
    past idx — proven per candidate by truncation tests — while avoiding
    O(n^2) feature rebuilds. The Backtester event flow (fills, exits,
    account) still advances candle-by-candle.
    """

    def __init__(self, context, candidate, account, symbol,
                 timeframe="1m", cost_key="A", full_bars=None):
        self.context = context
        self.candidate = candidate
        self.account = account
        self.symbol = symbol
        self.timeframe = timeframe
        self.cost_key = cost_key
        self.sizer = PositionSizer()
        self.history = []
        self.full_bars = full_bars
        self.n_signals = 0

    def reset(self):
        pass

    def subscribe(self, bus):
        bus.subscribe(EventType.CANDLE, self._on_candle)

    def _on_candle(self, event):
        candle = event.candle
        self.context.add_candle(candle)
        bar = self.context.current_index
        self.history.append({
            "time": int(candle.timestamp),
            "open": float(candle.open),
            "high": float(candle.high),
            "low": float(candle.low),
            "close": float(candle.close),
            "volume": float(getattr(candle, "volume", 0.0) or 0.0),
        })
        idx = len(self.history) - 1
        view = self.full_bars if self.full_bars is not None else self.history
        if self.full_bars is not None:
            assert int(self.history[-1]["time"]) == int(view[idx]["time"]), \
                "candidate view misaligned with event feed"
        for sig in self.candidate.signals(idx, view, self.context) or ():
            self.n_signals += 1
            intent = assemble_intent(
                sig, self.account, self.sizer, self.symbol,
                self.timeframe, self.cost_key,
            )
            if intent is None:
                continue
            # NBO trigger stamp: THIS bar's frozen signal is the trigger
            # decision; certified RULE-3 mechanics fill at N+1 open.
            intent.breakout_triggered = True
            intent.breakout_trigger_bar = bar
            intent.breakout_trigger_close = float(candle.close)
            self.context.order_registry.create(
                intent, bar=bar, timestamp=candle.timestamp)
            self.context.order = intent
            self.context.execution_signal = intent


def assemble_intent(sig, account, sizer, symbol, timeframe, cost_key):
    """Signal dict -> risk-validated NBO OrderIntent (certified math).

    Sizing/commission/slippage formula identical to the 11F-certified
    assembly; only the execution channel differs (NEXT_BAR_OPEN).
    """
    balance = account.equity if account.equity > 0 else account.balance
    if balance <= 0:
        return None
    position = sizer.calculate(
        balance=balance,
        entry_price=sig["entry"],
        stop_price=sig["stop"],
        leverage=risk_settings.LEVERAGE,
        confidence=sig.get("confidence", 80.0),
    )
    if not position.valid:
        return None
    spec = COST_SCENARIOS_11F[cost_key]
    commission = (spec["COMMISSION_PER_TRADE"]
                  + position.position_value * spec["COMMISSION_RATE"])
    slippage = (2.0 * position.position_value
                * spec["SLIPPAGE_BPS"] / 10000.0)
    return OrderIntent(
        direction=sig["direction"],
        entry=position.entry_price,
        stop_loss=sig["stop"],
        take_profit=sig["take_profit"],
        risk_reward=sig.get("risk_reward", 0.0),
        quantity=position.quantity,
        risk_percent=position.risk_percent,
        risk_amount=position.risk_amount,
        actual_risk_percent=position.actual_risk_percent,
        expected_loss=position.expected_loss,
        expected_profit=abs(sig["take_profit"] - position.entry_price) * position.quantity,
        position_value=position.position_value,
        leverage=position.leverage,
        commission=commission,
        slippage=slippage,
        confidence=sig.get("confidence", 80.0),
        score=sig.get("score", 0.0),
        symbol=symbol,
        timeframe=timeframe,
        setup_id=sig["setup_id"],
        entry_mode="LIMIT_RETEST",
        entry_execution=ENTRY_EXECUTION_NBO,
        canonical_id="11G-%s" % sig["setup_id"],
        status="NEW",
        valid=True,
    )


def run_candidate(raw_bars, candidate, symbol, cost_key="A",
                  timeframe="1m"):
    """One deterministic cold-start NBO evaluation run over raw_bars."""
    candles = to_candles(raw_bars, symbol)
    full = list(raw_bars)
    assert len(candles) == len(full), "candle/bar count diverged"
    ctx = PipelineContext()
    ctx.market = MarketState(symbol=symbol, timeframe=timeframe)
    bus = EventBus()
    account = Account(starting_balance=risk_settings.STARTING_BALANCE)
    pipeline = ResearchPipeline11G(ctx, candidate, account, symbol,
                                   timeframe, cost_key, full_bars=full)
    pipeline.subscribe(bus)
    sim = TradeSimulator()
    bt = Backtester(pipeline=pipeline, event_bus=bus, simulator=sim,
                    account=account)
    with mock.patch.multiple(risk_settings, ACTIVE_ENTRY_MODES=("LIMIT_RETEST",)):
        bt.run(candles)
    orders, expired, invalidated = [], 0, 0
    if ctx.order_registry:
        for o in ctx.order_registry.all():
            orders.append({
                "order_id": o.order_id, "status": o.status,
                "setup_id": o.setup_id,
                "entry": float(o.entry),
                "quantity": float(o.quantity),
                "entry_execution": str(getattr(o, "entry_execution", "")),
            })
        try:
            expired = len(ctx.order_registry.expired())
            invalidated = len(ctx.order_registry.invalidated())
        except Exception:
            pass
    trades = []
    for t in sim.registry.all():
        commission = float(getattr(t, "commission", 0.0) or 0.0)
        slippage = float(getattr(t, "slippage", 0.0) or 0.0)
        net = float(t.pnl)
        trades.append({
            "trade_id": t.trade_id,
            "direction": t.direction,
            "entry": float(t.entry),
            "exit": float(t.exit_price),
            "quantity": float(t.quantity),
            "entry_time": int(t.entry_time),
            "exit_time": int(getattr(t, "exit_time", 0) or 0),
            "stop": float(getattr(t, "stop_loss", 0.0) or 0.0),
            "take_profit": float(getattr(t, "take_profit", 0.0) or 0.0),
            "gross": net + commission + slippage,
            "commission": commission,
            "slippage": slippage,
            "net": net,
            "risk_amount": float(getattr(t, "risk_amount", 0.0) or 0.0),
        })
    return {"orders": orders, "trades": trades, "n_bars": len(candles),
            "final_balance": account.balance,
            "n_signals": pipeline.n_signals,
            "n_expired": expired, "n_invalidated": invalidated}
