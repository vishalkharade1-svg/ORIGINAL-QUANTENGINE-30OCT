"""
====================================================
QuantEngine -- Phase 18 frozen-strategy OOS executor.

Research-only, deterministic. Runs the FROZEN canonical
Backtester + InstitutionalPipeline over a supplied
chronological bar slice with ZERO configuration changes.
No thresholds, no RR changes, no entry-model changes, no
symbol/direction selection: the caller supplies the bars,
this module executes them exactly as the frozen baseline
does.

Returns a pure funnel dict; never writes ledgers, never
submits orders, never touches live/paper state.
====================================================
"""

from __future__ import annotations

import os

from collections import Counter


def _to_candles(rows_asc):
    from core.history.candle import Candle

    candles = []
    for r in rows_asc:
        candles.append(Candle(
            timestamp=int(r["time"]),
            open=float(r["open"]),
            high=float(r["high"]),
            low=float(r["low"]),
            close=float(r["close"]),
            volume=float(r["volume"]),
        ))
    return candles


def load_verified_funding_schedule(artifact_path, market_data_path, rows_asc):
    """Load genuine funding evidence bound to the exact OOS market-data file.

    The artifact must be REAL and its declared evidence window must cover the
    complete OOS candle interval. No missing-funding-to-zero fallback exists.
    """
    from research.economics.funding_evidence import load_and_verify, to_schedule

    rows = list(rows_asc or ())
    if not rows:
        raise ValueError("rows_asc must be non-empty")
    artifact = load_and_verify(artifact_path, market_data_path=market_data_path)
    if artifact.provenance_status != "REAL":
        raise ValueError("funding evidence is not genuine venue evidence")
    start = int(rows[0]["time"])
    end = int(rows[-1]["time"])
    if artifact.start > start or artifact.end < end:
        raise ValueError("funding evidence window does not cover the OOS candle interval")
    schedule = to_schedule(artifact)
    if not schedule.covers(start, end):
        raise ValueError("funding schedule does not cover the OOS candle interval")
    return schedule


def run_frozen_oos(rows_asc, symbol="BTCUSDT", *, funding_schedule=None,
                   order_trace=None):
    """Execute the frozen strategy over one chronological slice.

    rows_asc: venue-verbatim rows sorted ascending by time.
    Returns funnel dict with mutually-exclusive terminal counts,
    completed trades, wins/losses/pnl, actual-fill RR list and
    direction breakdown. When ``funding_schedule`` is supplied, funding
    is applied only at verified settlement timestamps inside each holding
    interval and is included in net P&L attribution. Empty slices raise
    ValueError (never fabricate a period result).

    Phase 26 observability: when ``order_trace`` is a list, per-order
    lifecycle records are appended to it after the run. Capture is
    passive (a temporary root-log handler plus post-run registry reads)
    and cannot change execution semantics or the returned funnel.
    """
    rows = list(rows_asc)
    if not rows:
        raise ValueError("rows_asc must be non-empty")

    from core.backtesting.trade_simulator import TradeSimulator
    from core.events.event_bus import EventBus
    from core.market_state import MarketState
    from core.pipeline.institutional_pipeline import InstitutionalPipeline
    from core.pipeline.pipeline_context import PipelineContext
    from backtesting.backtester import Backtester

    candles = _to_candles(rows)
    if funding_schedule is not None:
        first_ts = int(rows[0]["time"])
        last_ts = int(rows[-1]["time"])
        if not funding_schedule.covers(first_ts, last_ts):
            raise ValueError("funding evidence does not cover the OOS candle interval")
    context = PipelineContext()
    context.market = MarketState(symbol=symbol)
    bus = EventBus()
    pipeline = InstitutionalPipeline(context)
    pipeline.subscribe(bus)
    simulator = TradeSimulator()
    backtester = Backtester(pipeline, bus, simulator, funding_schedule=funding_schedule)

    # Frozen-research runtime isolation: the replay must execute under
    # the Phase-14 frozen semantics, impervious to runtime policy
    # drift. The scope is exactly backtester.run; the previous user
    # environment is restored in finally.
    from core.research.strategy_identity import FROZEN_OOS_ENV

    _capture = None
    _captured: list[str] = []
    if order_trace is not None:
        from core.research.oos_validation.order_trace import LogCapture

        _capture = LogCapture().start()

    _prev_frozen = os.environ.get(FROZEN_OOS_ENV)
    os.environ[FROZEN_OOS_ENV] = "1"
    try:
        backtester.run(candles)
    finally:
        if _capture is not None:
            _captured = _capture.stop()
        if _prev_frozen is None:
            os.environ.pop(FROZEN_OOS_ENV, None)
        else:
            os.environ[FROZEN_OOS_ENV] = _prev_frozen

    oreg = getattr(context, "order_registry", None)
    raw_orders = []
    if oreg is not None and hasattr(oreg, "_orders"):
        try:
            raw_orders = list(oreg._orders.values())
        except (TypeError, AttributeError):
            raw_orders = []

    if order_trace is not None:
        from core.research.oos_validation.order_trace import build_order_records

        order_trace.extend(build_order_records(
            raw_orders, _captured, rows, symbol=symbol))

    terminal = Counter(getattr(o, "status", "?") for o in raw_orders)
    directional = Counter(
        (getattr(o, "direction", "?"), getattr(o, "status", "?"))
        for o in raw_orders
    )

    try:
        closed = list(simulator.registry.all())
    except (AttributeError, TypeError):
        closed = []
    closed = [t for t in closed if getattr(t, "status", "") == "CLOSED"]

    from core.backtesting.accounting import realized_rr

    rr_list = []
    wins = 0
    losses = 0
    breakeven = 0
    gross = 0.0
    funding = 0.0
    commission = 0.0
    slippage = 0.0
    for t in closed:
        pnl = float(getattr(t, "pnl", 0.0) or 0.0)
        trade_funding = float(getattr(t, "funding", 0.0) or 0.0)
        trade_commission = float(getattr(t, "commission", 0.0) or 0.0)
        trade_slippage = float(getattr(t, "slippage", 0.0) or 0.0)
        funding += trade_funding
        commission += trade_commission
        slippage += trade_slippage
        gross += pnl + trade_funding + trade_commission + trade_slippage
        if pnl > 0:
            wins += 1
        elif pnl < 0:
            losses += 1
        else:
            breakeven += 1
        rr_list.append(realized_rr(
            getattr(t, "direction", ""),
            getattr(t, "entry", 0.0),
            getattr(t, "stop_loss", 0.0),
            getattr(t, "take_profit", 0.0),
        ))

    fills = len(closed)
    orders = len(raw_orders)
    return {
        "bars": len(rows),
        "orders": orders,
        "terminal": dict(terminal),
        "directional": {
            "%s/%s" % (d, s): int(c) for (d, s), c in directional.items()
        },
        "fills": fills,
        "completed_trades": fills,
        "wins": wins,
        "losses": losses,
        "breakeven": breakeven,
        "gross_pnl": gross,
        "commission": commission,
        "slippage": slippage,
        "funding": funding,
        "net_pnl": gross - commission - slippage - funding,
        "actual_fill_rr": list(rr_list),
        "rr_rejections": None,
        "bars_per_fill": (len(rows) / fills) if fills else None,
        "order_to_fill": (fills / orders) if orders else 0.0,
    }
