# Phase 10 Architecture — Production-Grade PAPER

> Frozen: No AI/research changes. This doc is the single source of truth for the PAPER runtime.

## Stack

```
Delta REST (/v2/products, /v2/history/candles) + Delta WS (wss://public-socket.delta.exchange, ticker)
  ↓ ProductClient + DeltaContractLoader + DeltaMapper
  ↓ InstrumentRegistry (Instrument, key = exchange:instrument_id)
  ↓ UniverseManager + MarketUniverse + UniversePolicy (eligibility cascade)
  ↓ RefreshScheduler (60s, clock)
  ↓ RealTimeEngine (per-symbol PipelineRegistry + PaperRuntime + BrokerEngine dry_run)
  ↓ DeltaSubscriptionStream (multiplexed, one WS, CandleBuilder per symbol, RLock)
  ↓ CandleRouter
  ↓ CandleBuilder (1m buckets, timestamp.py canonical seconds, RLock, history+series)
  ↓ SymbolPipeline (20+ engines: indicators, trend, swings, structure, liquidity, displacement, FVG, order blocks, regime, setup, decision, execution, risk)
  ↓ MarketState (symbol/timeframe/mark_price, under market.lock)
  ↓ PortfolioRiskManager / SharedCapital (0.03 = 3% fraction)
  ↓ PositionSizer / PositionManager (requested vs actual)
  ↓ PAPER EXECUTION (TradeSimulator, OrderRegistry, TradeRegistry, Account)
  ↓ Accounting (core/backtesting/accounting.py, canonical)
  ↓ Analytics (PerformanceAnalytics, ambiguous/sl_first/tp_first)
  ↓ Monitoring (Control API 8787 + Remote Gateway 9443 + desktop/PWA)
```

Every stage is observable and testable. No parallel trading logic.

## Key Invariants

- One pipeline, one BaseEngine, one PipelineContext (slots=True)
- Strategies never submit orders — Risk validates, Execution creates
- Research never mutates production state — dataset is append-only
- Replay, Paper, Live share canonical logic (TradeSimulator vs BrokerEngine dry_run)

## Current Baseline

- HEAD `4515c96`, 1716 tests, PAPER-only, `BREAKOUT_CONTINUATION`, `RISK_PER_TRADE=0.01`, `STARTING_BALANCE=2000`, `MAX_ALLOCATION=500`, `LEVERAGE=10`
- Real Delta baseline: 5000 bars BTCUSDT 1m, 11 fills, net 3.81, Sharpe 0.59 (synthetic and real both deterministic)
