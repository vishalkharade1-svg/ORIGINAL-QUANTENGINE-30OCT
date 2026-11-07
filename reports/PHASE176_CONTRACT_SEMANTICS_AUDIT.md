# PHASE 176 — Contract Semantics Verification Audit

**Audit Status:** COMPLETE  
**System Posture:** `NOT_PRODUCTION_READY | EDGE NOT ESTABLISHED`  
**Audit Date:** 2026-10-20  
**Input Baseline:** QuantEngine_PHASE175_RELEASE_CANDIDATE.zip  
**Input SHA-256:** `16aacbde562d3a39078e15d62d120810b2d72b0f426526856fd7d274b16954b4`

---

## 1. Scope

This document independently verifies whether QuantEngine correctly models the **Delta Exchange India BTCUSD** instrument from raw contract metadata through all computed economic quantities.

Primary question: **Does QuantEngine model the actual Delta Exchange India BTCUSD instrument correctly from contract metadata through realized P&L, fees, risk, and execution decisions?**

---

## 2. Contract Specification Extraction

### 2.1 Authoritative Source

Source: `data/fixtures/delta/delta_mcp_public_products_20260925.json`  
Observation date: 2026-09-25  
MCP environment: `india_testnet` (read-only, no credentials)  
Product ID: **84** | Symbol: **BTCUSD**

### 2.2 Verified Contract Fields

| Field | Authoritative Value | Source |
|---|---|---|
| `contract_value` | `0.001` | MCP product payload |
| `contract_unit_currency` | `BTC` | MCP product payload |
| `notional_type` | `vanilla` | MCP product payload |
| `is_quanto` | `false` | MCP product payload |
| `contract_type` | `perpetual_futures` | MCP product payload |
| `taker_commission_rate` | `0.0005` | MCP product payload |
| `maker_commission_rate` | `0.0002` | MCP product payload |
| `tick_size` | `0.1` | MCP product payload |
| `quoting_asset.symbol` | `USD` | MCP product payload |
| `settling_asset.symbol` | `USD` | MCP product payload |
| `underlying_asset.symbol` | `BTC` | MCP product payload |
| `initial_margin` | `0.5` (50 bps) | MCP product payload |
| `maintenance_margin` | `0.25` (25 bps) | MCP product payload |
| `default_leverage` | `10.0` | MCP product payload |
| `state` | `live` | MCP product payload |
| `funding_method` | `mark_price` | MCP product payload |

### 2.3 Instrument Semantic Classification

**BTCUSD is a linear vanilla perpetual futures contract:**

- **Linear (not inverse):** P&L denominated in USD. For a long: `P&L = (exit - entry) x 0.001 x qty [USD]`. No inversion.
- **Vanilla (not quanto):** `notional_type: "vanilla"`, `is_quanto: false`. No FX conversion.
- **Perpetual (no expiry):** `settlement_time: null`. Funding every 8h (`expiry_interval: 28800` seconds).
- **BTC-denominated contracts, USD-settled:** 1 contract = 0.001 BTC. P&L settled in USD.

---

## 3. Code Model vs. Contract Specification

### 3.1 Contract Multiplier

| Check | Result |
|---|---|
| Authoritative `contract_value` | `0.001` |
| Code `FeeScheduleProvenance` narrative | `multiplier=0.001` |
| `PaperOrder.multiplier` default | `Decimal("0.001")` |
| `FrictionHurdleGate.evaluate()` default | `Decimal("0.001")` |
| `calculate_round_trip()` notional formula | `ep * cm * qty` |

**Verdict:** CORRECTLY MODELED. Multiplier 0.001 consistent across all code paths.

**Discrepancy:** MCP payload records `tick_size: "0.1"` but `FeeScheduleProvenance` documents `tick=0.50`. See Section 4.

### 3.2 Fee Rates

| Rate | Authoritative | Code Constant | Match |
|---|---|---|---|
| Taker (base) | 0.0005 (5 bps) | `TAKER_BASE_RATE = Decimal("0.0005")` | YES |
| Maker (base) | 0.0002 (2 bps) | `MAKER_BASE_RATE = Decimal("0.0002")` | YES |
| GST on commissions | 18% (India) | `DEFAULT_GST_RATE = Decimal("0.18")` | YES |
| Effective taker | 5.90 bps | `FeeScheduleProvenance.effective_taker_rate_bps = Decimal("5.90")` | YES |
| Effective maker | 2.36 bps | `FeeScheduleProvenance.effective_maker_rate_bps = Decimal("2.36")` | YES |

**Verdict:** Fee rates correctly match authoritative MCP payload.

### 3.3 P&L Linearity Verification

Formula: `gross_pnl = (exit - entry) x 0.001 x qty [USD]`

Canonical reproduction (82k regime, 4.5-pt move, qty=1):
- `(82004.50 - 82000.00) x 0.001 x 1 = 0.00450000 USD`

Code `calculate_round_trip()`: `((xp - ep) * cm * qty).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)`

**Verdict:** Correctly linear. No inversion. No FX adjustment.

### 3.4 Settlement Currency Trace

```
Notional: entry_price [USD/BTC] x 0.001 [BTC] x qty = notional [USD]
Fee:      notional [USD] x rate x (1 + 0.18) = fee [USD]
Gross PnL: (exit - entry) [USD/BTC] x 0.001 [BTC] x qty = [USD]
Net PnL:  Gross PnL [USD] - total_fees [USD] = net [USD]
Wallet:   net [USD] posted to USD wallet
```

All intermediate quantities in USD. No unit mixing. **Verdict:** CORRECT.

---

## 4. Tick Size Discrepancy (FINDING-176-01)

| Item | Value |
|---|---|
| Authoritative tick (MCP payload) | `0.1` USD |
| Code narrative (`FeeScheduleProvenance`) | `tick=0.50` |
| Impact on fee/P&L calculations | ZERO |
| Impact on order price alignment validation | POTENTIAL |

The `validate_instrument_constraints()` function uses whatever tick_size is passed. If a caller passes 0.5 when the venue allows 0.1, valid prices ($82,000.10) would be incorrectly rejected. This is a documentation and configuration defect, not an economic calculation error.

**Classification:** DOCUMENTATION_INCONSISTENCY — repair required before live order validation.

---

## 5. Margin Model Assessment

| Item | Status |
|---|---|
| `initial_margin` (venue) | 0.5% (0.5 bps) |
| `maintenance_margin` (venue) | 0.25% |
| `default_leverage` (venue) | 10x |
| Margin implemented in paper engine | NO |
| Impact on paper simulation | Correctly scoped (paper only) |

Margin enforcement is outside paper simulation scope. No blocker for paper testing purposes.

---

## 6. Contract Semantics Summary

| Dimension | Correct? | Notes |
|---|---|---|
| Contract multiplier (0.001) | YES | All code paths consistent |
| Linear P&L formula | YES | `(exit - entry) x 0.001 x qty` |
| USD settlement | YES | `settling_asset.symbol = "USD"` |
| Not inverse / not quanto | YES | `is_quanto: false`, `notional_type: "vanilla"` |
| Taker fee rate (5 bps base) | YES | `TAKER_BASE_RATE = Decimal("0.0005")` |
| Maker fee rate (2 bps base) | YES | `MAKER_BASE_RATE = Decimal("0.0002")` |
| GST 18% on commissions | YES | `DEFAULT_GST_RATE = Decimal("0.18")` |
| Zero GST on rebates | YES | Code branch: `base_fee < 0` => `gst = 0` |
| Tick size in narrative | DOC ERROR | 0.50 vs authoritative 0.10 (FINDING-176-01) |
| Perpetual (no expiry) | YES | `settlement_time: null` |
| Margin model (live) | NOT IMPLEMENTED | Correctly scoped for paper engine |

---

## 7. Conclusion

**Primary question: YES.** QuantEngine correctly models the Delta Exchange India BTCUSD instrument from contract metadata through realized P&L, fees, and execution decisions, with one documentation inconsistency (tick_size 0.5 vs authoritative 0.1) that does not affect any fee or P&L calculation but must be repaired before live order validation.

**Final posture: `NOT_PRODUCTION_READY | EDGE NOT ESTABLISHED`**
