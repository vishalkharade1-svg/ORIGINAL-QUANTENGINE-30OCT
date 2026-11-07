# QUANTENGINE PHASE 180 — INSTRUMENT SEMANTICS RECONCILIATION

**Audit Date**: 2026-10-20  
**Phase**: 180  
**Status**: VERIFIED & RECONCILED  
**Mandatory Posture**: NOT_PRODUCTION_READY | EDGE NOT ESTABLISHED  

---

## 1. Executive Summary & Root Cause Resolution

In Phase 179, numerical examples in prose cited a contract multiplier of `1.0` and described 1 contract as 1 BTC (e.g., $\$60,000$ notional, $\$499.90$ gross loss, and $\$549.17$ total risk). Conversely, Phase 176–178 documentation and the underlying codebase (`InstrumentMetadata.for_btcusd()`) defined Delta Exchange India BTCUSD Product ID 84 with a contract multiplier of `0.001`.

Phase 180 independently audited and empirically resolved this discrepancy:
1. **Authoritative Exchange Instrument (Product ID 84)**:
   - Live authenticated queries to Delta Exchange India API (`https://cdn-ind.testnet.deltaex.org/v2/products/84`) and the frozen MCP payload (`data/fixtures/delta/delta_mcp_public_products_20260925.json`) confirm that Delta Exchange India BTCUSD has `contract_value = "0.001"`, `tick_size = "0.1"`, and `notional_type = "vanilla"`.
   - **1 contract = 0.001 BTC**.
2. **Phase 179 Multiplier 1.0 Classification**:
   - The multiplier of `1.0` is formally classified as **Category B: A synthetic test instrument** (or representing 1.0 whole BTC coin notional, which is exactly equivalent to 1,000 Delta Exchange India contracts).
3. **Explicit Isolation**:
   - Synthetic test instruments are now explicitly separated from production exchange specifications.
   - Authoritative exchange code paths default to `0.001` for Product ID 84, while synthetic test fixtures explicitly declare their multiplier.

---

## 2. Authoritative Exchange Instrument Specification (Delta India Product ID 84)

Directly verified against live Delta Exchange India API:

| Field | Authoritative Value | Verification Source |
|---|---|---|
| **Product ID** | `84` | Delta Exchange India API / MCP Payload |
| **Symbol** | `BTCUSD` | Delta Exchange India API (`/v2/products/84`) |
| **Contract Type** | `perpetual_futures` | Live API response |
| **Payoff Semantics** | `vanilla` (Linear) | `notional_type: "vanilla"`, `is_quanto: false` |
| **Contract Multiplier** | `0.001` | `contract_value: "0.001"` (1 contract = 0.001 BTC) |
| **Tick Size** | `0.10` USD | `tick_size: "0.1"` |
| **Quantity Step (Step Size)** | `1` contract | `step_size: "1"` |
| **Minimum Order Quantity** | `1` contract | `min_quantity: "1"` ($0.001$ BTC notional ≈ $\$60.00$ at $\$60,000$) |
| **Minimum Notional** | `$1.00` USD | Exchange trading rules |
| **Quoting Asset** | `USD` | `quoting_asset: {"symbol": "USD"}` |
| **Settling Asset** | `USD` | `settling_asset: {"symbol": "USD"}` |
| **Maker Commission Rate** | `2.00 bps` ($0.0002$) | Live product metadata |
| **Taker Commission Rate** | `5.00 bps` ($0.0005$) | Live product metadata |
| **GST Rate** | `18.00%` | Applicable statutory rate |
| **Effective Maker Rate (inc. GST)** | `2.36 bps` ($0.000236$) | $0.0002 \times 1.18$ |
| **Effective Taker Rate (inc. GST)** | `5.90 bps` ($0.000590$) | $0.0005 \times 1.18$ |

---

## 3. Mathematical Reconciliation: Product ID 84 vs Synthetic Multiplier 1.0

### Linear Payoff Equation
For a vanilla linear contract quoted and settled in USD:
$$\text{Notional} = \text{Price} \times \text{Quantity} \times \text{Multiplier}$$
$$\text{Gross P\&L} = (\text{Exit Price} - \text{Entry Price}) \times \text{Quantity} \times \text{Multiplier}$$

### Case Comparison at Entry $60,000.00 and Stop $59,500.10

| Parameter | Delta Product ID 84 (1 Contract) | Delta Product ID 84 (1,000 Contracts) | Synthetic Instrument (1.0 Unit) |
|---|---|---|---|
| **Contract Multiplier** | `0.001` | `0.001` | `1.0` |
| **Quantity** | `1` | `1,000` | `1.0` |
| **Underlying BTC Exposure** | `0.001 BTC` | `1.000 BTC` | `1.000 BTC` |
| **Entry Notional** | $\$60.00$ | $\$60,000.00$ | $\$60,000.00$ |
| **Stop Exit Notional** | $\$59.5001$ | $\$59,500.10$ | $\$59,500.10$ |
| **Gross Planned Loss** | $\$0.49990000$ | $\$499.90000000$ | $\$499.90000000$ |
| **Maker Entry Fee (2.36 bps)** | $\$0.01416000$ | $\$14.16000000$ | $\$14.16000000$ |
| **Taker Exit Fee (5.90 bps)** | $\$0.03510506$ | $\$35.10505900$ | $\$35.10505900$ |
| **Total Cost-Adjusted Risk** | **$\$0.54916506$** | **$\$549.16505900$** | **$\$549.16505900$** |

### Reconciliation Insight
The numerical values reported in Phase 179 ($\$499.90$ gross loss, $\$549.17$ total risk) are **mathematically exact** for:
- 1,000 contracts of Delta Exchange India Product ID 84, OR
- 1.0 unit of a Synthetic Multiplier-1.0 instrument.

When trading a single contract of Delta Exchange India Product ID 84, the total planned risk is **$\$0.54916506$ USD**.

---

## 4. Position Sizing & Budget Enforcement

Under a given Risk Budget $B$:
$$\text{Max Contracts} = \left\lfloor \frac{B}{\text{Total Risk Per Contract}} \right\rfloor$$

For $B = \$550.00$ USD:
$$\text{Max Contracts} = \left\lfloor \frac{550.00}{0.549165059} \right\rfloor = 1,001 \text{ contracts}$$

- $1,000\text{ contracts} \implies \text{Total Risk} = \$549.165059 \le \$550.00 \implies$ **APPROVED**
- $1,002\text{ contracts} \implies \text{Total Risk} = \$550.263389 > \$550.00 \implies$ **REJECTED_RISK**

Tested and verified in `tests/test_phase180_instrument_semantics.py`.
