# QUANTENGINE PHASE 185 — SYMBOL ELIGIBILITY & UNIVERSE REGISTRY

**Audit Date**: 2026-10-21  
**Phase**: 185  
**Venue**: Delta Exchange India Testnet (`https://cdn-ind.testnet.deltaex.org`)  
**Operating Posture**: `NOT_PRODUCTION_READY` | `EDGE NOT ESTABLISHED`  
**Registry Module**: `core/execution/symbol_registry.py`  
**Evidence Source**: `research/results/phase185_testnet_products_snapshot.json`  

---

## 1. Executive Summary

Phase 185 transitioned QuantEngine from a hard-coded single-symbol (`BTCUSD`) execution harness to an extensible, fail-closed multi-symbol eligibility registry. 
From an authenticated venue capture of 665 products on Delta Exchange India Testnet:
- **16 Perpetual Futures** were evaluated.
- **5 Liquid Perpetual Contracts** were certified as `ELIGIBLE` for demo execution.
- High-multiplier contracts (e.g. `DOGEUSD`, mult 100) are classified as `RISK_VERIFIED` pending risk sizing audit.
- Synthetic stock index perps (e.g. `QQQXUSD`, `SPYXUSD`, `NVDAXUSD`) are classified as `BLOCKED_EVIDENCE` due to market-hours discontinuities.

---

## 2. Symbol Lifecycle State Machine

The registry enforces strict state transitions:
$$\text{DISCOVERED} \longrightarrow \text{METADATA\_VERIFIED} \longrightarrow \text{DATA\_VERIFIED} \longrightarrow \text{RISK\_VERIFIED} \longrightarrow \text{TESTNET\_VERIFIED} \longrightarrow \mathbf{ELIGIBLE}$$
$$\text{Any Gate Failure} \longrightarrow \mathbf{REJECTED} \quad\text{or}\quad \mathbf{BLOCKED\_EVIDENCE}$$

Only instruments in `ELIGIBLE` state are permitted to be submitted to order creation, queue simulation, or demo execution pipelines.

---

## 3. Certified Eligible Instruments

### 3.1 BTCUSD (Product ID: 84) — Multiplier Authority Certified
- **Symbol**: `BTCUSD`
- **Product ID**: `84`
- **Exchange Environment**: Delta Exchange India Testnet / Live
- **Contract Type**: `perpetual_futures` (Linear USD settlement)
- **Contract Multiplier**: `0.001` (1 contract = 0.001 BTC)
- **Denomination**: USD
- **Quote / Settlement Asset**: USD / USD
- **Tick Size**: `0.10`
- **Step Size / Min Qty**: `1` contract / `1` contract
- **Min Notional**: $1.00 USD
- **Fee Structure**: Maker `0.0002` (2 bps), Taker `0.0005` (5 bps), GST `18%`
- **Funding Model**: 8-hour funding intervals (UTC 00:00, 08:00, 16:00)
- **Order Support**: LIMIT_POST_ONLY, LIMIT, MARKET
- **Status**: **`ELIGIBLE`**
- **Evidence**: `research/results/phase185_testnet_products_snapshot.json` (resolves `BLOCK-184-03`)

### 3.2 ETHUSD (Product ID: 1699)
- **Symbol**: `ETHUSD`
- **Product ID**: `1699`
- **Contract Type**: `perpetual_futures` (Linear USD settlement)
- **Contract Multiplier**: `0.01` (1 contract = 0.01 ETH)
- **Quote / Settlement Asset**: USD / USD
- **Tick Size**: `0.05`
- **Step Size / Min Qty**: `1` contract / `1` contract
- **Fee Structure**: Maker `0.0002` (2 bps), Taker `0.0005` (5 bps), GST `18%`
- **Status**: **`ELIGIBLE`**

### 3.3 SOLUSD (Product ID: 92572)
- **Symbol**: `SOLUSD`
- **Product ID**: `92572`
- **Contract Type**: `perpetual_futures` (Linear USD settlement)
- **Contract Multiplier**: `1.0` (1 contract = 1.0 SOL)
- **Quote / Settlement Asset**: USD / USD
- **Tick Size**: `0.0001`
- **Step Size / Min Qty**: `1` contract / `1` contract
- **Fee Structure**: Maker `0.0002` (2 bps), Taker `0.0005` (5 bps), GST `18%`
- **Status**: **`ELIGIBLE`**

### 3.4 XRPUSD (Product ID: 93723)
- **Symbol**: `XRPUSD`
- **Product ID**: `93723`
- **Contract Type**: `perpetual_futures` (Linear USD settlement)
- **Contract Multiplier**: `1.0` (1 contract = 1.0 XRP)
- **Quote / Settlement Asset**: USD / USD
- **Tick Size**: `0.0001`
- **Step Size / Min Qty**: `1` contract / `1` contract
- **Fee Structure**: Maker `0.0002` (2 bps), Taker `0.0005` (5 bps), GST `18%`
- **Status**: **`ELIGIBLE`**

### 3.5 ADAUSD (Product ID: 101760)
- **Symbol**: `ADAUSD`
- **Product ID**: `101760`
- **Contract Type**: `perpetual_futures` (Linear USD settlement)
- **Contract Multiplier**: `1.0` (1 contract = 1.0 ADA)
- **Quote / Settlement Asset**: USD / USD
- **Tick Size**: `0.00001`
- **Step Size / Min Qty**: `1` contract / `1` contract
- **Fee Structure**: Maker `0.0002` (2 bps), Taker `0.0005` (5 bps), GST `18%`
- **Status**: **`ELIGIBLE`**

---

## 4. Evaluated Candidates In Non-Eligible States

| Symbol | Product ID | Contract Multiplier | Tick Size | State | Reason / Blocker |
|---|---|---|---|---|---|
| **DOGEUSD** | 101555 | `100.0` | `0.000001` | `RISK_VERIFIED` | High multiplier (100x) requires conservative sizing guard before activation. |
| **DOGSUSD** | 200007 | `1000.0` | `0.00000001` | `RISK_VERIFIED` | 1000x contract multiplier pending extreme-leverage volatility testing. |
| **1000SHIBUSD** | 162764 | `1000.0` | `0.000001` | `RISK_VERIFIED` | Multiplier requires micro-notional minimum trade enforcement. |
| **QQQXUSD** | 184020 | `0.01` | `0.01` | `BLOCKED_EVIDENCE` | Synthetic stock index perp; US equity market hours trading breaks uncalibrated. |
| **SPYXUSD** | 184021 | `0.01` | `0.01` | `BLOCKED_EVIDENCE` | Synthetic stock index perp; overnight gap risk model not yet established. |
| **NVDAXUSD** | 165774 | `0.1` | `0.01` | `BLOCKED_EVIDENCE` | Equity derivative; earnings volatility and market-hours halts unmodeled. |
| **XAUTUSD** | 181689 | `0.001` | `0.01` | `DATA_VERIFIED` | Gold token perp; low testnet book depth and wide testnet spread. |
| **PAXGUSD** | 169532 | `0.001` | `0.01` | `DATA_VERIFIED` | Gold token perp; insufficient liquidity on testnet orderbook. |
| **SLVONUSD** | 184019 | `0.1` | `0.01` | `BLOCKED_EVIDENCE` | Silver synthetic commodity; funding schedule uncalibrated. |
| **USOONUSD** | 192449 | `0.1` | `0.01` | `BLOCKED_EVIDENCE` | Oil synthetic commodity; roll-over and funding mechanics unmodeled. |
| **SNDKBUSD** | 189558 | `0.01` | `0.01` | `BLOCKED_EVIDENCE` | Synthetic commodity; low liquidity. |

---

## 5. Risk, Sizing, and Protective Bracket Rules for Multi-Symbol Universe

1. **Multiplier Safety**: Contract multiplier MUST be retrieved directly from `SymbolEligibilityRegistry.get_metadata(symbol)`. Multipliers must NEVER be defaulted to 1.0 or copied between contracts.
2. **Pip & Tick Alignment**: Prices MUST be quantized to `meta.tick_size` via `normalize_price_to_tick()` with `TickRoundingPolicy.CONSERVATIVE`.
3. **Step Size Enforcement**: Quantities MUST be positive integers aligned to `meta.step_size` and `>= meta.min_quantity`.
4. **Fee Drag Calculation**: Sizing calculations MUST include Maker fee (0.02%), Taker fee (0.05%), and 18% GST on all fees.
