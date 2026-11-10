# QuantEngine audit handover

## Deep hardening work — 2026-11-10

Working branch: `audit/deep-hardening-2026-11-10`

### Changes made
- Distinguished preflight authorization from an armed testnet order reservation in Phase 189/193B regression tests. A preflight decision alone must not authorize transport writes; the atomic reservation must bind the client order ID and payload.
- Restored deterministic offline BTC/ETH market-data fixtures used by the Phase 193B transport tests.
- Added a lock around the fallback client-order sequence so concurrent callers cannot receive duplicate generated IDs; added a multithreaded regression test.
- Hardened Phase 192 reconciliation: explicit exchange `filled + remaining` quantities must reconcile to total size. Invalid, negative, or non-finite quantities now produce a blocking contradiction and keep risk/quota held; omitted remaining size is derived only when the venue omitted it.
- Added adversarial tests for inconsistent remaining size and non-finite fill quantities.
- Added missing historical Git-object checks to evidence-mode guards; missing original objects are reported as blocked evidence rather than treated as verified ancestry.
- Kept the Phase 206 release gate and live-trading posture closed.

### CI evidence
- Repository working-tree/staged secret scan and historical credential-assignment scan: passed on commit `6d453a6bb1`.
- Phase 206 focused capture tests and its manifest refresh: passed on commit `6d453a6bb1`.
- Order-executor, testnet transport, and Phase 206 focused suites have prior green runs; the current changes are being revalidated.
- Full-suite run at `6d453a6bb1` stopped at strict manifest verification because the two latest reconciliation files had not yet been added to `BUILD_MANIFEST.sha256`. The Phase 206 workflow subsequently refreshed the manifest in commit `a77199e1a74ca5dad914c2d73535c1eb3707bdc3`. A fresh full-suite run is required against that manifest-current tree.

### Outstanding / not certified
- The complete repository test suite has not yet passed on the latest tree.
- Historical Phase 14/22 strategy pins remain immutable; current strategy identity drift remains unregistered and must not be silently blessed.
- Historical credential exposure in Git history remains an operator remediation item: revoke/rotate affected credentials and decide on history rewrite with repository owners.
- No live trading, testnet orders, credential rotation, destructive Git cleanup, or production release was performed by this audit.

### Additional authorization-gate hardening
- Moved the BTCUSD USD-notional ceiling into the authorization gate itself. The signed scope now binds the observed 0.001 BTC contract value, and each reservation computes notional from contract count × signed contract value × limit price.
- The gate now refuses incomplete order details and any extra caller-supplied fields; ledger identity, symbol, product, size, state, and timestamps cannot be overwritten through `order_details`.
- Both bounded testnet experiment entry points verify that the live BTCUSD contract is operational and matches the signed contract-value scope before any write.
- Added tests for notional-cap enforcement and attempted ledger-identity override. The focused Phase 206 workflow passed these gate, transport, live-safety, and capture regressions.
