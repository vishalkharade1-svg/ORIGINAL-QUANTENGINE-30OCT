# Phase 9Q Defect Matrix — Hypotheses from Ling 3.0 / Muse Spark / Direct Inspection

> Classification = exactly one of TRUE / FALSE / PARTIAL / ALREADY FIXED / NEEDS FURTHER AUDIT. Never label TRUE merely because an AI reviewer claimed it. Evidence = file:line + observed code.

| ID | Source | Finding | File | Function | Evidence | Reproduction | Classification | Severity | Risk | Proposed Fix | Regression Test | Status |
|----|--------|---------|------|----------|----------|--------------|----------------|----------|------|--------------|-----------------|--------|
| 9Q-ATR-01 | Ling/Muse | ATR uses SMA `sum(window)/period` not Wilder RMA | `core/indicators/atr.py:98-112,166-175` | `ATR.calculate/update` | `sum(window)/period` loop | `ATR(14).calculate(bars)` vs Wilder diverges | **TRUE** | P0 CRITICAL | Risk-width miscomputed | Wilder RMA `6aec29f` | FIXED |
| 9Q-ATR-02 | Ling | ADX also SMA | `core/indicators/adx.py` | `ADX.calculate` | Verified `adx.py` already Wilder | — | **FALSE** | P0 | — | No fix | CLOSED |
| 9Q-CAUS-01 | Muse | Displacement latest ATR (lookahead) | `core/displacement/displacement_scanner.py:72-82,122-203` | `DisplacementScanner.scan` | `latest("ATR_14")` for all bars | Future bars altered historical `atr_multiple` | **TRUE** | P0 | Non-causal | Per-bar `ATR_series[N]` `45eb621` | FIXED |
| 9Q-CAUS-02 | Muse | Same lookahead in FVG/OB/Breaker | `core/fvg/fvg_scanner.py`, `order_blocks/order_block_scanner.py`, `breaker_scanner.py` | `scan` | Audited: FVG/Breaker/Mitigation no ATR; OB uses current ATR (causal) | Grep + read | **PARTIAL** | P0 | — | OB current distance is causal, no fix | CLOSED |
| 9Q-ACCT-01 | Ling/Muse | `pnl_percent = pnl/entry*100` | `trade_simulator.py:236`, `broker_engine.py:718`, `performance.py:302` | `_close_trade` | `pnl/entry*100` should be `pnl/notional*100` | qty2 → 10% vs 5% | **TRUE** | P0 | Inflated return | `accounting.py` canonical `d4d03ec` | FIXED |
| 9Q-ACCT-02 | Ling | Zero-PnL counted as WIN | `core/risk/account.py:98` | `book_profit` | `>=0` as win vs `>0` | `pnl==0` mismatch | **TRUE** | P0 | Win-rate inflation | `book_breakeven` `d4d03ec` | FIXED |
| 9Q-TS-01 | Ling | WS ts µs vs ms | `data/websocket_client.py:85`, `delta_subscription_stream.py:113`, `candle_builder.py:156` | `start`, `_emit_ticker` | Raw `ts` assumed µs | 13-digit → 1970 bucket | **TRUE** | P0 | Live vs backtest diverge | `timestamp.py` canonical `8e00d19` | FIXED |
| 9Q-CB-01 | Ling/Muse | CandleBuilder race | `data/candle_builder.py:156`, `delta_subscription_stream.py:121` | `update/current/clear` | No lock on `_pump_loop` | Torn high/low | **TRUE** | P0 | Torn candles | `RLock` `8e00d19` | FIXED |
| 9Q-RISK-01 | Ling | Risk `_PCT` mixing | `config/risk_settings.py`, `portfolio.py:_allows` | `_allows` | Audit done, contract `risk_config_contract.md` created, validation partially enforced | Check units | **PARTIAL** | P0 | Cap misconfig | Doc `279fe51`, full validation pending 9S | PARTIAL |
| 9Q-SIZE-01 | Ling | Allocation cap silent | `core/risk/position_sizer.py:229` | `PositionSizer` | `risk_amount=expected_loss` hides scaling | Tight stop → 3% intent | **TRUE** | P0 | Under-exposure | `PositionSize` requested vs actual `cc32b31` | FIXED |
| 9Q-EXEC-01 | Ling | Breakout resize dust | `core/live/broker_engine.py:749`, `backtester.py:1108` | `_resize_for_actual_entry` | No `PositionManager.audit` | Gap → inf/qty | **PARTIAL** | P0 | Invalid fills | `PositionManager` guards at choke point; resize audit deferred to 9S | PARTIAL |
| 9Q-EXEC-02 | Muse | Intrabar SL always wins | `core/backtesting/trade_simulator.py:133` | `update` | `low<=SL && high>=TP → LOSS` | Pessimistic –1R | **TRUE** | P1 | Bias | Conservative + `ambiguous` flag `279fe51`/`cc32b31` | FIXED |
| 9Q-CFG-01 | Muse | Settings string | `config/settings.py:36` | `Settings` | Raw `os.getenv` string | TypeError late | **TRUE** | P1 | Late fail | `_env_float/_env_int` `279fe51` | FIXED |
| 9Q-PIPE-01 | Prior audit | Missing `liquidity_target` | `core/pipeline/pipeline_context.py` | `PipelineContext` | Inspected: field exists `liquidity_target: Any = None` line 157 | — | **FALSE** | P1 | — | No fix | CLOSED |
| 9Q-PORT-01 | Muse | `available_capital` negative | `core/risk/capital.py:102` | `available_capital` | No floor | Negative snapshot | **TRUE** | P1 | Confusing | `max(0, ...)` `cc32b31` | FIXED |

Notes:
- All TRUE findings verified against live repo at `F:\vishal 3\1\files\QuantEngine\QuantEngine`.
- NEEDS FURTHER AUDIT = not yet reproduced/inspected beyond reviewer claim; must inspect file before labeling TRUE.
- FALSE / PARTIAL / ALREADY FIXED to be filled as audit proceeds.
- This matrix is living; update Status as each 9Q subphase completes.
