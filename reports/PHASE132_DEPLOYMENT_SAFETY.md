# Phase132-N/L deployment + auth safety (EXECUTED 2026-10-15)

## Defaults (safe, verified by execution)

- `PAPER_MODE=True`, `LIVE_MODE=False`, `ALLOW_LIVE=False`, `LIVE_EXECUTE=False`, `EXECUTION_MODE=''`
- `LiveSafetyGate.require_decision(None)` → `LiveBlockedError` (refuses without token)
- Source: `config/settings.py:62`, `core/execution/live_safety_gate.py`

## Auth/credential isolation (75 passed)

CMD: `pytest test_live_block_11 test_live_readiness_phase10 test_sandbox_credential_diagnostics_16 test_india_testnet_credential_isolation test_api_error_redaction_phase93 test_remote_gateway_9pk`
RESULT: 75 passed. Covers: live blocked without arming, readiness false, sandbox diagnostics, Testnet-only key names (no generic fallback), API error redaction, remote gateway auth.

## Dependencies

- Pins: `httpx==0.27.2 websockets==12.0 python-dotenv==1.0.1 pandas==2.2.2 numpy==2.1.1 pyarrow==18.0.0 pytest==8.4.2`
- Installed: all match except `httpx 0.28.1` (drift, recorded, behavior-neutral for offline paths). `pip-audit`/`bandit` not installed → formal scans BLOCKED.
- Python 3.12.10, Windows-10 64-bit. Reproducible via `requirements.txt` + `python -m venv`.

## Audit prompt

Created `docs/CLAUDE_INDEPENDENT_AUDIT_PROMPT.md` per Phase O/P (adversarial, evidence-only, no trust in reports).

## Verdict

Deployment starts safe non-live. Production readiness FALSE. No orders, no network.
