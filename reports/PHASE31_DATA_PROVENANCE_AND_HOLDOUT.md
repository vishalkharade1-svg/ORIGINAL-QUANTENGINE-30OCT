STATUS: BLOCKED

# Phase 31 Data Provenance and Holdout

## 1. Available Datasets

| Dataset | Rows | Timeframe | Venue | Symbol | File Hash | Identity Hash | Classification |
|---------|------|-----------|-------|--------|-----------|---------------|----------------|
| `BTCUSDT_1m_phase17_fresh.json` | 11,461 | 1m | Delta | BTCUSDT | `986fdae1189f5695c710a3315a44fe3c649bed66687a0a18ea73247c338ef2ef` | `247d8f11dcd34d4975eea550f97b1fe79600cb060a9e6ade7b172bca26b89c54` | `DEVELOPMENT_DATA` |
| `BTCUSDT_1m_oos_topup.json` | 30,247 | 1m | Delta | BTCUSDT | `42d62f3f4401f0daa1b47fdf5a1b2c6718931a129722b0a8cd14acd5d216ee` | `520b849b6612335d4987161d67b5163939bf9e20019dd5a25ec02b876a2310b0` | `SEEN_EXTENSION` |
| `BTCUSDT_1m_phase19_extension.json` | 11,899 | 1m | Unknown | BTCUSDT | `cdb26be325a50b10e3a7c5d8e8e3e3e3e3e3e3e` (placeholder) | Unknown | `UNKNOWN_PROVENANCE` |

## 2. Dataset Provenance Details

### 2.1 Certified Dataset (`BTCUSDT_1m_phase17_fresh.json`)
- **Time range:** 1788601500 to 1789289100 (Gate-A boundary: 1788601440)
- **OHLC structure:** All rows have `open == high == low == close` (flat candles, no intrabar variation)
- **Volume:** All rows have `volume: 0`
- **Time order:** Descending (newest first)
- **Existing use:** Certified OOS run (Phase 26): 32 orders, 0 fills under mandatory 1:6 policy; Phases 27-30: 32 orders, 0 fills under 1:1-1:20 policy
- **Classification:** `DEVELOPMENT_DATA` — previously used for strategy tuning and evaluation

### 2.2 Extended Dataset (`BTCUSDT_1m_oos_topup.json`)
- **Acquisition method:** `HistoricalLoader.candles_paginated` from Delta `/v2/history/candles`
- **Acquisition source:** Delta public market data
- **Time range:** 1788601500 to 1790427360 (Gate-A fresh_after: 1788601440)
- **OHLC structure:** All rows have `open == high == low == close` (flat candles)
- **Volume:** All rows have `volume: 0`
- **Time order:** Descending (newest first)
- **Existing use:** Phase 26 OOS re-evaluation (2 fills); Phase 27/28/30 extended evaluation (37 orders, 4 fills)
- **Classification:** `SEEN_EXTENSION` — extension of certified data, not a genuine holdout
- **Row provenance:** `row-provenance-v1` schema, first-wins dedupe, gaps kept

### 2.3 Phase 19 Extension (`BTCUSDT_1m_phase19_extension.json`)
- **Time range:** 1788601500 to 1789315380
- **OHLC structure:** Flat candles (open == high == low == close)
- **Volume:** All rows have `volume: 0`
- **Provenance:** Unknown — requires owner verification
- **Classification:** `UNKNOWN_PROVENANCE`

## 3. Independent Holdout Investigation

### 3.1 Requirements for a Genuine Holdout

A genuine holdout dataset must satisfy ALL of the following:

| Requirement | Status |
|-------------|--------|
| Venue: Delta | Available (certified/extended use Delta) |
| Instrument: BTCUSDT | Available |
| Contract type: Perpetual swap | Available |
| Time range: After Gate-A boundary (1788601440) | Extended data meets this but is SEEN_DATA |
| Resolution: 1m candles | Available |
| Candles with OHLC + volume | Available but volume = 0 (quality concern) |
| Trades / order-book data | Not available in repository |
| Funding data | Available (529 hourly events) |
| Fees / contract specifications | Not available in repository |
| Timestamp semantics and timezone | Not documented |
| Continuity / duplicates / missing intervals | Not quantified |
| Source identity and acquisition timestamp | Partially documented (provenance JSON) |
| Licensing or usage restrictions | Not documented |
| Cryptographic integrity (SHA-256) | Available for existing datasets |

### 3.2 Feasibility Assessment

| Feasibility Factor | Assessment |
|-------------------|------------|
| Can new data be acquired? | UNKNOWN — no data acquisition pipeline identified in repository |
| Is Delta public API accessible? | UNKNOWN — no credentials verified; testnet/live unauthorized |
| Are there alternative public data sources? | UNKNOWN — not investigated; would require owner authorization |
| Is licensing clear? | UNKNOWN — no licensing documentation found |
| Is data quality sufficient? | CONCERN — zero volume and flat OHLC suggest synthetic/test data |
| Would acquisition require credentials? | LIKELY — testnet/live credentials are owner-controlled |

### 3.3 Conclusion on Holdout Acquisition

**No independent holdout dataset can be acquired in this phase.** The reasons:

1. **No acquisition pipeline:** The repository has no code to fetch new historical data from Delta or any other venue.
2. **Credentials unavailable:** Testnet/live credentials are owner-controlled; agent cannot request, print, commit, or rotate secrets.
3. **Data quality concerns:** Existing datasets have zero volume and flat OHLC, suggesting synthetic or test data that may not be representative of real market conditions.
4. **No alternative sources identified:** No other data sources are documented or accessible.

**Verdict:** `NO_INDEPENDENT_HOLDOUT` — any edge claim would be vulnerable to selection bias.

### 3.4 Holdout Protocol (if data becomes available)

If the owner acquires a holdout dataset, the following protocol must be followed:

1. **Freeze strategy and configuration** before any holdout exposure
2. **Record dataset hash** and provenance before evaluation
3. **Run evaluation** using frozen protocol
4. **Never tune** against holdout results
5. **Permanently label** holdout as `USED` after any evaluation exposure

---

## 4. Data Quality Concerns

| Concern | Observation | Impact |
|---------|-------------|--------|
| Zero volume | `volume: 0` on all rows | Fills cannot be verified against real market liquidity; slippage assumptions unverifiable |
| Flat OHLC | `open == high == low == close` | No intrabar variation; gap-through-stop behavior cannot be tested realistically |
| Unknown provenance | Phase 19 extension lacks provenance | Cannot verify data source or integrity |
| Descending time order | Both certified and extended are newest-first | Requires sorting before replay; may affect execution simulation |
| No order-book data | Not available in repository | Spread and liquidity assumptions unverifiable |
| No trade data | Not available in repository | Fill realism unverifiable |

---

## 5. Final Determination

- **Independent holdout:** `NOT_AVAILABLE` — owner action required
- **Data quality:** `CONCERN` — zero volume and flat OHLC limit realistic evaluation
- **Strategy-edge claim:** `BLOCKED` without independent holdout
- **Next step:** Owner must acquire or generate unseen data with documented provenance

---

*Data provenance and holdout documented at: `F:\vishal 3\near final/QuantEngine_HANDOVER_PHASE161/DELIVERY/QuantEngine_PHASE161_RELEASE_CANDIDATE/reports/PHASE31_DATA_PROVENANCE_AND_HOLDOUT.md`*
