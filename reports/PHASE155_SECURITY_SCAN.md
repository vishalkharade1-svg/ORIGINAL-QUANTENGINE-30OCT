# Phase155 — security scan (tools now EXECUTED, previously BLOCKED)

Phase154 recorded the formal security-tooling gate as `BLOCKED` because
`pip-audit` and `bandit` were not installed. This phase installs both and
runs them for real. Findings are reported as-is and triaged; nothing is
hidden behind a skip.

- `pip-audit` 2.10.1, `bandit` 1.9.4 installed into the authoritative
  Python 3.12.10 environment.
- Dependency drift check: the tools pulled only dev tooling
  (CacheControl, cyclonedx-python-lib, bandit, stevedore, …). Project
  runtime pins (httpx, websockets, python-dotenv, pandas, numpy, pyarrow,
  pytest) were **not** changed. See `../freeze_before_phase155.txt` vs
  `../freeze_after_phase155.txt`.

## 1. Dependency audit — `python -m pip_audit -r requirements.txt`

Result: **6 known advisories across 3 pinned packages** (each advisory is
reported twice by the tool; 3 unique).

| Package | Pinned | Advisory | Fix version |
|---|---|---|---|
| python-dotenv | 1.0.1 | PYSEC-2026-2270 | 1.2.2 |
| pyarrow | 18.0.0 | PYSEC-2026-113 | 23.0.1 |
| pytest | 8.4.2 | PYSEC-2026-1845 | 9.0.3 |

Triage: real advisories against the **pinned** versions. `python-dotenv`
and `pyarrow` are runtime deps; `pytest` is a test-only dep. This is not
fixed in Phase155 by upgrading, because the pins are deliberate
(reproducibility) and `NEXT_ACTIONS.md` already schedules bumps "with a
full green run" — silently upgrading would violate the dependency-drift
rule and could break the 3,900-test suite. Recorded as an open,
operator-visible item with explicit fix versions.

## 2. Static analysis — `python -m bandit -r core scripts -x tests,_archive`

Baseline: **80 findings** — 10 HIGH, 3 MEDIUM, 67 LOW.

After Phase155 hardening: **77 findings** — 10 HIGH, **0 MEDIUM**, 67 LOW.

### 2a. MEDIUM B310 (`urlopen` scheme) — FIXED (3 → 0)

Three `urllib.request.urlopen` sites allowed `file://`/custom schemes.
Each now validates the scheme is `http`/`https` before opening:

- `core/client/http_client.py` (`ApiClient._open`)
- `core/remote/gateway.py` (`_GatewayHandler._fetch`)
- `scripts/evaluate_evidence_gates.py` (`_http`)

Bandit's B310 is a static call-site check and still flags the call after
an upstream guard, so each call carries a justified `# nosec B310`
annotation. Regression: `tests/test_url_scheme_guard_phase155.py`
(5 tests — real `file://`/`ftp://` refusals + source contract for the
gateway, whose URL is built with a literal `http://`).

### 2b. HIGH B324 (weak SHA1) — ACCEPTED RISK (10, reviewed)

All ten are `hashlib.sha1(...)` used to build **deterministic content
identifiers / fingerprints** (row ids, experiment ids, memory digests)
across `core/research/**`. SHA1 is not a security boundary here — it
names content, and collision resistance is irrelevant to that purpose.

Not changed, deliberately: an annotation edit would alter bytes of ten
research files for zero security benefit and risk perturbing
research-pinned artifacts. The strategy digest covers only nine files
(`scripts/recertify_strategy_digest.py:STRATEGY_FILES`), none of these,
but the broader research-pin set is already `BLOCKED` and is not worth
churning. Reviewed and accepted with rationale.

### 2c. LOW findings — triaged, none real

- B105/B106/B107 "hardcoded password" (7): empty-string defaults
  (`token=""`, `secret=""`) and one deliberate negative-test fixture
  (`token="wrong-token"` in `evaluate_evidence_gates.py:451`). No real
  credential.
- B101 `assert` (22), B110 `try/except/pass` (19), B112 `try/except/continue`
  (2), B603/B607 subprocess (11), B404 subprocess import (4),
  B311 non-crypto `random` (2): standard low-severity patterns, no
  security impact identified. Recorded, not suppressed.

## 3. Secret scan

Unchanged from Phase154: worktree `SECRET_SCAN_FAIL` on the operator's
gitignored `.env` (lines 1–2, live Testnet secrets) — correct behavior;
the extracted package is clean. Values are never printed.

## 4. Privacy

Unchanged: `phase153_ledger/wallet_100.json` carries `user_id` on 33/33
rows and is RESTRICTED; Phase155 reports contain aggregates only. A
secret-scan pass is not a privacy clearance — stated, not implied.

## Verdict

Security-tooling gate: **EXECUTED** (was BLOCKED). 1 medium class fixed
and regression-tested; 1 high class reviewed and accepted with rationale;
dependency advisories recorded with fix versions and left as an
operator-visible pin-upgrade item. Overall release verdict remains
`NOT_PRODUCTION_READY`.
