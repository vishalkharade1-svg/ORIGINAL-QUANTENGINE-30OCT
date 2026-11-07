# Real Delta 5000-Bar Baseline

> Generated 2026-09-05 09:44:37 UTC, code b873870

## Dataset
- Symbol: BTCUSDT, Timeframe: 1m, Source: Delta /v2/history/candles
- Requested: 5000, Received: 5000, Usable: 5000, Duplicates: 0, Missing: 0
- Range: 2026-09-01 22:25:00 to 2026-09-05 09:44:00 (1788301500 to 1788601440)

## Configuration
- STARTING_BALANCE=2000, RISK_PER_TRADE=0.01, MAX_ALLOCATION=500, LEVERAGE=10.0
- ENTRY_MODE=BREAKOUT_CONTINUATION, MAX_WAIT_BARS=30, ENTRY_DELAY_BARS=1
- Fees: {'commission_per_trade': 0.0, 'commission_rate': 0.0, 'slippage_bps': 0.0} -- **explicit zero-cost** (from risk_settings, not invented; real Delta taker fee would be ~0.02% -- not configured, so 0 is documented)

## Fill Model
- {'entry_mode': 'BREAKOUT_CONTINUATION', 'next_bar_open': 'BREAKOUT_CONTINUATION fills at next bar open', 'sl_tp': 'conservative SL-first, ambiguous flagged', 'expiry': 'eligible_from_bar + 30', 'invalidation': 'structural stop breach', 'fees': {'commission_per_trade': 0.0, 'commission_rate': 0.0, 'slippage_bps': 0.0}, 'slippage': '0.0 bps'}

## Results
- n_bars: 5000, setups: 0, orders: 27, fills: 11, expirations: 10, invalidations: 6, rejected: 0
- wins: 6, losses: 5, breakevens: 0, win_rate: 54.55%, breakeven_rate: 0.00%
- gross_profit: 5.47, gross_loss: 1.66, commissions: 0.0, slippage: 0.0, **net_pnl: 3.81**, return: 0.1904%
- max_drawdown: 1.04 (0.0520%), sharpe: 0.5969, sortino: 1.4532, expectancy: 0.3463, PF: 3.2982
- ambiguous: 0 (0.00%), avg_R: 0.0768, median_R: 0.0441
- total_exposure: 0, max_exposure: 0

## Reproducibility
- Dataset identity: BTCUSDT-1m-1788301500-1788601440-5000
- Second run must match all above counts and pnl within 1e-6 (deterministic pipeline).

## Notes
- Post-9Q Wilder ATR, causal displacement, canonical accounting, breakeven, timestamp canonical, etc. -- **0 trades is valid if the funnel is selective**; do not optimize strategy to look better.
- Real Delta 5000-bar baseline is the **final 9S proof** that the engine measures reality correctly.
