# PHASE154 Baseline inventory (authoritative env, EXECUTED)

- Python 3.12.10, Windows-10-10.0.19045-SP0 64bit, pytest 8.4.2.
- Deps: pandas 2.2.2, numpy 2.1.1, websockets 12.0, python-dotenv 1.0.1, pyarrow 18.0.0 — all pinned-match.
- DRIFT (unchanged, now with a fixed consequence): httpx 0.28.1 installed vs 0.27.2 pinned. Originally recorded as benign drift; Phase134 proved it broke `Client.delete(content=)` → live-cancel outage → repaired with request-with-fallback (`delta_auth.py:300`) + compat tests. Pin update still deferred to a green-run maintenance window.
- Git: no repository (`fatal: not a git repository`) — history-dependent checks are BLOCKED_EVIDENCE/UNVERIFIABLE, nothing fabricated.
- Full suite running in background under THIS environment (authoritative, not the 3.13.5/9.0.2 audit env): `reports/PHASE154_FULL_SUITE_RUN.txt` pending.
- Operator `.env` with live Testnet secrets present in worktree (gitignored, unpackaged): secret-scanner + packaging tests correctly FAIL while it exists — working as designed, must not be "fixed" by deletion or weakening.
