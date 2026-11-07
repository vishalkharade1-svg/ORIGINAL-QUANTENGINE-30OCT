# QuantEngine Phase 189: Testnet Experiment Authorization Template

**Document**: `reports/PHASE189_TESTNET_AUTHORIZATION.md`  
**Date**: `2026-10-21`  
**Authorization State**: `PENDING_OPERATOR_APPROVAL`  
**Execution Status**: **`STRICTLY_BLOCKED / NOT_AUTHORIZED_FOR_EXECUTION`**  
**Governing Gate**: `core/execution/testnet_authorization_gate.py` (`TestnetAuthorizationGate`)  
**Phase Invariant**: Phase 189 is an authorization preflight phase only. Zero exchange orders placed, modified, or cancelled (`exchange_order_writes = 0`).

---

## 1. Operating Notice & Legal Disclaimer

> [!CAUTION]
> **THIS TEMPLATE IS UNAPPROVED AND DOES NOT AUTHORIZE VENUE EXECUTION.**  
> Neither the existence of this file, nor passing mock test suites, nor simulated paper runs constitute operator authorization. Automated execution scripts MUST reject this document fail-closed until an authorized operator explicitly replaces all placeholders with cryptographic signatures and verified credentials. Real-money production trading remains strictly prohibited.

---

## 2. Authorization Scope & Boundary Specification

If and when authorized by an explicit operator signature, execution shall be strictly confined to the following non-negotiable boundaries:

| Scope Dimension | Authorized Boundary | Enforcement Mechanism |
| :--- | :--- | :--- |
| **Execution Environment** | Delta India Testnet (Sandbox) | Hard-coded endpoint whitelist in `TestnetSafetyGate` |
| **Target REST Endpoint** | `https://cdn-ind.testnet.deltaex.org` | Any other URL raises `ProductionEndpointAttemptedError` |
| **Target Private WS Endpoint** | `wss://socket-ind.testnet.deltaex.org` | Rejects production WebSocket endpoints |
| **Target Public WS Endpoint** | `wss://socket-ind-pub.testnet.deltaex.org` | Read-only market data stream |
| **Eligible Instrument** | **BTCUSD** (Product ID `84`) | Verified from `research/results/phase185_testnet_products_snapshot.json` |
| **Contract Multiplier** | `0.001` BTC per contract | Contract semantics locked; mismatch aborts |
| **Tick Size** | `$0.10` USD | Non-tick-aligned prices rejected pre-flight |
| **Order Sizing** | Exactly **1 contract** (0.001 BTC / ~$82.80 notional) | Rejection if size > 1 contract |
| **Maximum Simultaneous Open Orders** | Exactly **1 open order** | Strictly serialized: Order $N+1$ blocked until Order $N$ is terminal |
| **Maximum Cumulative Orders** | Exactly **20 orders total** | Enforced across process restarts via persistent ledger |
| **Order Resting Policy** | Strict **120.0 seconds** max resting time | Active cancellation dispatched at 120s; no market chasing |
| **Order Type** | Strict **Post-Only Limit** | Rejection if taker match attempted; no market conversion |
| **Max Realized Loss Budget** | **$5.00 USD** | Immediate process halt if realized loss $\ge \$5.00$ |
| **Account Pre-Conditions** | Account equity $\ge \$50.00$, zero open positions | Verified flat before first submission |

---

## 3. Mandatory Operator Pre-Flight Checklist

Before an operator signs this authorization, every prerequisite must be independently verified:

- [ ] **1. Credential Isolation**: Dedicated testnet credentials loaded only in `DELTA_INDIA_TESTNET_API_KEY` / `DELTA_INDIA_TESTNET_API_SECRET`. Zero production credentials exposed or loaded.
- [ ] **2. Read-Only Account Audit**: `scratch/testnet_account_read_only.py` verified account equity $\ge \$50.00$, zero open positions, zero resting orders.
- [ ] **3. Working Tree Integrity**: Git working tree clean and committed to SHA-256 manifest (`BUILD_MANIFEST.sha256`).
- [ ] **4. Offline Mock Verification**: 100% pass on `tests/test_phase188_gated_execution_mock.py` and `tests/test_phase189_authorization_preflight.py`.
- [ ] **5. Endpoint Separation**: Verification that `TestnetSafetyGate` actively blocks `https://api.delta.exchange` and `https://india.delta.exchange`.
- [ ] **6. Persistent Ledger Initialized**: `research/results/phase189_testnet_experiment_ledger.jsonl` exists and records 0 cumulative orders.
- [ ] **7. Kill Switch Operational**: Operator confirms manual kill switch command line and abort triggers are understood.

---

## 4. Operator Signoff & Cryptographic Authorization Fields

*(All fields below must be populated by the human operator. Any unreplaced bracketed token results in immediate preflight refusal by `TestnetAuthorizationGate`.)*

- **Authorization ID**: `[OPERATOR_ASSIGNED_ID_REQUIRED]`
- **Status**: `PENDING_OPERATOR_APPROVAL`
- **Authorizing Operator**: `[OPERATOR_KEY_ID_REQUIRED]`
- **Operator Role**: `[OPERATOR_TITLE_OR_ROLE_REQUIRED]`
- **Signed Timestamp UTC**: `[ISO8601_TIMESTAMP_REQUIRED]`
- **Expiry Timestamp UTC**: `[ISO8601_EXPIRY_TIMESTAMP_REQUIRED]`
- **Authorized Execution Window Duration**: `3600_SECONDS`
- **Operator Signature Scheme**: `ED25519`
- **Operator Signature**: `[OPERATOR_SIGNATURE_REQUIRED]`

---

## 5. Automated Refusal Audit

`TestnetAuthorizationGate.evaluate_preflight()` automatically checks this document on every order submission attempt:
```python
# Evaluated at runtime:
if auth_record.state == AuthorizationState.PENDING_OPERATOR_APPROVAL:
    raise TestnetBlockedError("Authorization record is in PENDING_OPERATOR_APPROVAL state")
if re.search(r"\[(OPERATOR_[A-Z0-9_]+|REQUIRED|PENDING)\]", raw_content):
    raise AuthorizationIntegrityError("Unreplaced operator placeholders detected in authorization document")
```
Execution is strictly blocked.
