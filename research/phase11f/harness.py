"""Phase 11F research harness (research-only).

Drives the PRODUCTION Backtester with an injected research
pipeline: candidate signals -> certified PositionSizer math ->
OrderIntent -> OrderRegistry lifecycle -> TradeSimulator
fills/exits -> Account booking. The strategy, risk engine,
sizing, costs formula, and safety code are imported and
reused, never modified.

Signal contract: candidate.signals(idx, bars, ctx) returns a
list of dicts, each describing ONE setup decided at bars[idx]
using bars[0..idx] only (bars is the run's full chronological
history; idx is 0-based):
  {direction, entry, stop, take_profit, setup_id, confidence}

Order assembly mirrors the certified risk economics
(PositionSizer + allocation/leverage + commission/slippage
formula); a parity test pins it against RiskEngine math.
"""

from unittest import mock

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

COST_SCENARIOS_11F = {
    # A zero (=11B A_zero); B moderate (=11B C_moderate);
    # C conservative (=11B D_adverse); D adverse-stress
    # (2x conservative, pre-registered in datasets.json).
    "A": {"COMMISSION_PER_TRADE": 0.0, "COMMISSION_RATE": 0.0, "SLIPPAGE_BPS": 0.0},
    "B": {"COMMISSION_PER_TRADE": 0.0, "COMMISSION_RATE": 0.0005, "SLIPPAGE_BPS": 2.0},
    "C": {"COMMISSION_PER_TRADE": 0.0, "COMMISSION_RATE": 0.00059, "SLIPPAGE_BPS": 5.0},
    "D": {"COMMISSION_PER_TRADE": 0.0, "COMMISSION_RATE": 0.00118, "SLIPPAGE_BPS": 10.0},
}


def to_candles(raw_bars, symbol):
    """Validated raw bars -> production Candle objects (C1-E rules)."""
    builder = CandleBuilder(max_history=len(raw_bars) or 1)
    builder.load_history(list(raw_bars))
    out = []
    for c in builder.history:
        out.append(Candle(
            timestamp=c.timestamp, open=c.open, high=c.high,
            low=c.low, close=c.close, volume=c.volume,
            closed=True, symbol=symbol,
        ))
    return out


class ResearchPipeline:
    """Minimal pipeline adapter: candidate signals become
    registry-managed pending orders for the production
    Backtester. Owns a fresh PipelineContext per run."""

    def __init__(self, context, candidate, account, symbol,
                 timeframe="1m", cost_key="A"):
        self.context = context
        self.candidate = candidate
        self.account = account
        self.symbol = symbol
        self.timeframe = timeframe
        self.cost_key = cost_key
        self.sizer = PositionSizer()
        # Full chronological history (context.candles is a
        # bounded deque — candidates index THIS list).
        self.history = []

    def reset(self):
        pass

    def subscribe(self, bus):
        bus.subscribe(EventType.CANDLE, self._on_candle)

    def _on_candle(self, event):
        candle = event.candle
        self.context.add_candle(candle)
        bar = self.context.current_index
        # Candidate-visible history uses plain bar dicts (the
        # feature layer contract); reconstructed 1:1 from the
        # delivered candle so indices can never diverge.
        self.history.append({
            "time": int(candle.timestamp),
            "open": float(candle.open),
            "high": float(candle.high),
            "low": float(candle.low),
            "close": float(candle.close),
            "volume": float(getattr(candle, "volume", 0.0) or 0.0),
        })
        idx = len(self.history) - 1
        for sig in self.candidate.signals(idx, self.history, self.context) or ():
            intent = assemble_intent(
                sig, self.account, self.sizer, self.symbol,
                self.timeframe, self.cost_key,
            )
            if intent is None:
                continue
            self.context.order_registry.create(
                intent, bar=bar, timestamp=candle.timestamp)
            self.context.order = intent
            self.context.execution_signal = intent


def assemble_intent(sig, account, sizer, symbol, timeframe, cost_key):
    """Signal dict -> risk-validated OrderIntent (certified math)."""
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
        entry_execution="LIMIT",
        canonical_id="11F-%s" % sig["setup_id"],
        status="NEW",
        valid=True,
    )


def run_candidate(raw_bars, candidate, symbol, cost_key="A",
                  max_wait_bars=None, timeframe="1m"):
    """One deterministic evaluation run. Returns plain-dict trades
    (production-booked gross/commission/slippage/net) + orders.

    Research execution channel: intents carry the canonical
    LIMIT_RETEST resting-touch model, activated research-only
    (production default is BREAKOUT_CONTINUATION-only). The
    touch/invalidation/expiry/SL-first machinery is the
    certified production path, unchanged.
    """
    candles = to_candles(raw_bars, symbol)
    ctx = PipelineContext()
    ctx.market = MarketState(symbol=symbol, timeframe=timeframe)
    bus = EventBus()
    account = Account(starting_balance=risk_settings.STARTING_BALANCE)
    pipeline = ResearchPipeline(ctx, candidate, account, symbol,
                                timeframe, cost_key)
    pipeline.subscribe(bus)
    sim = TradeSimulator()
    bt = Backtester(pipeline=pipeline, event_bus=bus, simulator=sim,
                    account=account)
    patches = {"ACTIVE_ENTRY_MODES": ("LIMIT_RETEST",)}
    if max_wait_bars is not None:
        patches["MAX_WAIT_BARS"] = max_wait_bars
    with mock.patch.multiple(risk_settings, **patches):
        bt.run(candles)
    orders = []
    if ctx.order_registry:
        for o in ctx.order_registry.all():
            orders.append({
                "order_id": o.order_id, "status": o.status,
                "setup_id": o.setup_id,
                "entry": float(o.entry),
                "quantity": float(o.quantity),
            })
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
            "final_balance": account.balance}
