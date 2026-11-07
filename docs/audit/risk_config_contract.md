# Risk Configuration Contract — Phase 9Q-8

> Every risk parameter's unit, type, range, default, semantic, owner, and consumer.
> Percentages are represented as **fraction** (0.01 = 1%) unless suffixed `_PCT` which is **percent points** (1.0 = 1%, 25.0 = 25%). Do not mix. Invalid config fails fast.

## Conventions

- **Amount** = quote currency (e.g. USDT, INR) — absolute.
- **Fraction** = 0.0–1.0 where 0.01 = 1%.
- **Percent points (_PCT)** = 0–100 where 1.0 = 1%, 25.0 = 25%. Consumers divide by 100.
- **Count** = integer.
- **Bars** = integer bar count.
- **Owner** = module that defines default.
- **Consumers** = modules that read the value.

## Account

| Name | Type | Unit | Valid Range | Default | Semantic | Owner | Consumers |
|------|------|------|-------------|---------|----------|-------|-----------|
| `STARTING_BALANCE` | float | quote | >0 | 2000 | Initial equity for Account | `config/risk_settings.py` | `Account`, `Backtester`, `BrokerEngine`, `PaperTradingEngine`, `PortfolioBacktester` |

## Position Risk

| Name | Type | Unit | Valid Range | Default | Semantic | Owner | Consumers |
|------|------|------|-------------|---------|----------|-------|-----------|
| `RISK_PER_TRADE` | float | fraction | 0 < x ≤ 0.1 | 0.01 | Fraction of equity risked per trade (fixed fractional) | `risk_settings.py` | `PositionSizer`, `RiskEngine` |
| `MAX_ALLOCATION_PER_TRADE` | float | quote | >0 | 500 | Max notional (entry*qty) per trade | `risk_settings.py` | `PositionManager` |
| `QUANTITY_PRECISION` | int | decimals | 0–8 | 8 | Quantity rounding | `risk_settings.py` | `PositionManager` |
| `MIN_QUANTITY` | float | quantity | >0 | 1e-6 | Dust threshold, quantity below → reject | `risk_settings.py` | `PositionManager` |
| `LEVERAGE` | float | multiple | ≥1 | 10.0 | Max leverage for notional cap (leverage*equity) | `risk_settings.py` | `PositionManager` (manage_into) |

## Pending Order Lifecycle

| Name | Type | Unit | Valid Range | Default | Semantic | Owner | Consumers |
|------|------|------|-------------|---------|----------|-------|-----------|
| `MAX_WAIT_BARS` | int | bars | >0 | 30 | Bars an order waits after eligible before expiry | `risk_settings.py` | `OrderRegistry` |
| `ENTRY_DELAY_BARS` | int | bars | ≥0 | 1 | Bars after creation before eligible (no look-ahead) | `risk_settings.py` | `OrderRegistry` |
| `MAX_PENDING_ORDERS` | int | count | >0 | 8 | Total pending slots | `risk_settings.py` | `ExecutionEngine`, `RiskEngine` |
| `MAX_PENDING_ORDERS_TOTAL` | int | count | >0 | 8 | Alias of above, per-registry | `risk_settings.py` | `RiskEngine` |
| `MAX_PENDING_ORDERS_PER_SYMBOL` | int | count | >0 | 8 | Per-symbol cap | `risk_settings.py` | `RiskEngine` |
| `MAX_PENDING_ORDERS_PER_DIRECTION` | int | count | >0 | 4 | Per-direction cap | `risk_settings.py` | `RiskEngine` |
| `MAX_PENDING_ORDERS_PER_CLUSTER` | int | count | >0 | 1 | Per-cluster cap (structural dedup) | `risk_settings.py` | `EconomicSetupRegistry` |
| `MAX_TOTAL_EXPOSURE_PCT` | float | percent points | 0–100 | 25.0 | Max total pending notional as % of equity (runaway backstop) | `risk_settings.py` | `RiskEngine` (divides by 100) |

## Entry Feasibility / Structural

| Name | Type | Unit | Valid Range | Default | Semantic | Owner | Consumers |
|------|------|------|-------------|---------|----------|-------|-----------|
| `ENTRY_FEASIBILITY_*_ATR` | float | ATR multiple | >0 | 0.10/0.35/0.75/1.50 | ATR-normalized distance classification | `risk_settings.py` | `EntryFeasibility` |
| `MAX_ORDER_BLOCK_AGE_BARS` | int | bars | >0 | 500 | Stale zone age (per timeframe map) | `risk_settings.py` | `ZoneFreshness` |
| `FRESH_ORDER_BLOCK_AGE_BARS` | int | bars | >0 | 5 | FRESH→ACTIVE boundary | `risk_settings.py` | `ZoneFreshness` |
| `MAX_LIMIT_ENTRY_DISTANCE_ATR` | float | ATR | >0 | 30.0 | LIMIT entry far limit | `risk_settings.py` | `TradeSetupBuilder` |
| `MIN_RISK_WIDTH_ATR` | float | ATR | >0 | 0.10 | Min entry-stop width | `risk_settings.py` | `TradeSetupBuilder`, `RiskEngine` |
| `ECONOMIC_TICK_SIZE` | float | price | >0 | 0.5 | Tick for economic fingerprint | `risk_settings.py` | `EconomicSetupRegistry` |
| `ECONOMIC_CLUSTER_*` | float/int | ticks/percent/ATR | ≥0 | 8 / 0.001 / 0.0 | Cluster tolerance | `risk_settings.py` | `EconomicSetupRegistry` |

## Execution Costs

| Name | Type | Unit | Valid Range | Default | Semantic | Owner | Consumers |
|------|------|------|-------------|---------|----------|-------|-----------|
| `COMMISSION_PER_TRADE` | float | quote | ≥0 | 0.0 | Fixed per trade (round-trip) | `risk_settings.py` | `RiskEngine`, `TradeSimulator` |
| `COMMISSION_RATE` | float | fraction | 0–0.01 | 0.0 | Rate on notional | `risk_settings.py` | `RiskEngine` |
| `SLIPPAGE_BPS` | float | bps | ≥0 | 0.0 | Slippage in bps on notional | `risk_settings.py` | `RiskEngine` |

## Drawdown / Profit Protection

| Name | Type | Unit | Valid Range | Default | Semantic | Owner | Consumers |
|------|------|------|-------------|---------|----------|-------|-----------|
| `MAX_DAILY_LOSS` | float | fraction | 0–1 | 0.02 | Max daily loss as fraction of equity (0.02=2%) — **consumer must NOT divide by 100 again** | `risk_settings.py` | `Account` (if used), `PortfolioRiskManager` |
| `MAX_WEEKLY_LOSS` | float | fraction | 0–1 | 0.05 | Weekly | `risk_settings.py` | — |
| `MAX_MONTHLY_LOSS` | float | fraction | 0–1 | 0.10 | Monthly | `risk_settings.py` | — |
| `PROFIT_PROTECTION` | bool | flag | — | True | Enable profit lock | `risk_settings.py` | `Account` |
| `PROFIT_LOCK_PERCENT` | int/float | percent points | 0–100 | 30 | Lock % | `risk_settings.py` | — |

> **WARNING — Unit Audit Finding (9Q-8):** `PortfolioRiskManager` previously treated `MAX_PORTFOLIO_RISK` as absolute quote and divided `MAX_DAILY_LOSS` by 100, making 0.02 → 0.02% instead of 2%. This contract freezes the intended units: `MAX_PORTFOLIO_RISK` etc. are **fractions** (0.03 = 3% of equity) and consumers must compute `cap = equity * fraction` (no /100). `_PCT` suffixed values are percent points and consumers do `/100`. Mixing is forbidden; validation must fail fast on out-of-range.

## Position Limits

| Name | Type | Unit | Valid Range | Default | Semantic | Owner | Consumers |
|------|------|------|-------------|---------|----------|-------|-----------|
| `MAX_OPEN_POSITIONS` | int | count | ≥1 | 1 | Max concurrent positions (single-position model) | `risk_settings.py` | `PortfolioRiskManager` |
| `MAX_PORTFOLIO_RISK` | float | fraction | 0–1 | 0.03 | Max portfolio risk as fraction of equity | `risk_settings.py` | `PortfolioRiskManager` (must be fraction, not absolute) |
| `MAX_CORRELATED_RISK` | float | fraction | 0–1 | 0.02 | Max correlated group risk | `risk_settings.py` | `PortfolioRiskManager` |

## Validation Rules (fail-fast)

- Any `*_PCT` must be 0–100; any fraction must be 0–1; amount must be >0; count/bars must be >0 integer.
- `MIN_QUOTE_VOLUME_24H` (float|None) and `MIN_HISTORY_BARS` (int|None) parsed via `_env_float`/`_env_int` with ValueError on invalid (see `config/settings.py`).
- `PROVIDER_HISTORY_LOOKBACK_DAYS` int >0.
- Invalid env values raise `ValueError` at import, not silently become string.

## Consumers Must

- Read via `config.risk_settings` or `config.settings` only.
- Never divide a fraction by 100; never treat a _PCT as fraction without /100.
- Never silently mutate requested risk; expose `REQUESTED vs ACTUAL` where caps apply (see 9Q-9).

## Status

- Contract created 2026-05-11 as part of 9Q-8.
- Remaining work: 9Q-9 (position sizing explicit), 9Q-10 (execution), 9Q-11 (intrabar) to enforce this contract in code.
