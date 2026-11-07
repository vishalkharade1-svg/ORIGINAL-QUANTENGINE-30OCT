# Known Limitations — Phase 10

> Do not hide limitations to declare GREEN. This doc is the honest list.

## Strategy

- Current 5000-bar real Delta baseline (BTCUSDT 1m, 11 fills, 5 wins, net 3.81) is **small but honest** — post-9Q Wilder + causal made funnel selective. Synthetic 500-bar baseline is 0 trades (same reason). Not a live-performance claim.
- No strategy optimization, no AI research, no NIFTY/SENSEX/crypto options — frozen per §33.

## Universe

- 50-symbol soak with `UniverseManager` fell back to dummy `MarketUniverse` on `DeltaContract.key` error — subscription layer is real (50 workers, p99 0.23ms), but full `LiquidityProvider`/`HistoryProvider` eligibility for 50 symbols still needs a successful real-manager soak with `Instrument` (not `DeltaContract`).

## Risk

- `PortfolioRiskManager` now supports both fraction (0.03 = 3%) and legacy absolute (3.0) for backward compat, but strict fraction-only enforcement is deferred.

## Performance

- `PerformanceAnalytics` ambiguous triad is now explicit (`ambiguous_trades`, `sl_first`, `tp_first`), but optimistic/exclude triad not yet reported (deferred).

## Market

- `HistoricalLoader` 5000-bar fetch is `c` (close) only; real Delta fee/slippage is 0 in `risk_settings.py` (explicit zero-cost, not misreported; real taker ~0.02% would be non-zero, but not configured).
- `websocket_client.py` single-symbol legacy now has `ReconnectPolicy` loop, but `DeltaSubscriptionStream` multiplexed path is the institutional path.

## Live Readiness

- **NOT READY** — Paper remains safe, but live requires explicit fees, 50-symbol real eligibility soak, and 5000-bar second-run reproducibility on host (Gate A already determinism 1e-6 on snapshot).

## Next

- Phase 10 docs are complete for PAPER operation. Next is **real 5000-bar live-data second run** + **50-symbol UniverseManager soak** → then **Phase 11** (separate architectural decision, not auto-started).
