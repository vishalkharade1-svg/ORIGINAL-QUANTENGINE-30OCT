# Phase 11F Baseline (§2 inspection record)

Date (UTC): 2026-09-07. All statements verified by execution/read this session.

- HEAD: `dbf210e` (fix(phase11e): close research methodology certification gaps)
- Repository status: clean (`git status` shows only pre-existing untracked
  `muse suggetions*.md` notes plus `__pycache__` churn, both untracked/ignored)
- Python: 3.12.10
- Dependencies (all match `requirements.txt` pins): httpx 0.27.2,
  websockets 12.0, python-dotenv 1.0.1, loguru 0.7.2, pandas 2.2.2,
  numpy 2.1.1, pyarrow 18.0.0, pytest 8.4.2
- Test command: `python -m pytest tests/ -q`
- Test count: 2001 collected, 0 collection errors (pytest.ini, testpaths=tests)
- Production strategy state: FROZEN BREAKOUT_CONTINUATION
  (InstitutionalPipeline + entry models, NEXT_BAR_OPEN fills, SL/TP exits);
  Gate A fingerprint 27 orders / 11 fills / 6W / 5L / 0BE / net +0.117534,
  deterministic (re-verified via research harness this phase before any
  candidate work)
- LIVE state: ALLOW_LIVE=False, LIVE_EXECUTE=False, PAPER_MODE=True,
  LIVE_MODE=False, EXECUTION_MODE='' — LIVE remains disabled
- Research infrastructure: `research/phase11e/` (spec `0ede560`, evidence
  `f681b14`, closure `dbf210e`); certified reuse components: Backtester,
  TradeSimulator, Account, OrderRegistry, PositionSizer, PositionManager,
  accounting, production indicator classes (ATR/RSI/EMA), CandleBuilder
- Available historical datasets:
  - Gate A snapshot `docs/audit/baseline_9s_delta_5000_raw.json`: 5000 bars,
    BTCUSDT 1m, 2026-09-01T22:25Z→2026-09-05T09:44Z, complete
  - Phase-7 file `data/history/BTCUSDT_1m_oos.json`: 10000 bars,
    2026-08-24T12:45Z→2026-08-31T11:24Z, complete
  - Fresh OOS `research/phase11e/data/oos_fresh.json`: 2499 bars,
    2026-09-05T09:45Z→2026-09-07T03:23Z, sha256 recorded
  - Calibration `research/phase11e/data/calib_pre_d2.json`: 4001 bars,
    strictly pre-D2, sha256 recorded
  - Footprint/tick bid-ask split: DATA_UNAVAILABLE (candle schema carries
    total volume only — verified `CandleMapper.map`); volume work uses
    explicitly labeled PROXY_FEATURE aggregates
- Data lineage: Gate A set = certification/contaminated; Phase-7 file =
  lineage-contaminated; Sep-5–7 file = opened in 11E (validation-tier max
  for 11F); brand-new post-11F fetch = untouched D3 holdout (to be fetched,
  hashed, and unopened until freeze)
- Known limitations: ~2.5k–10k bars per dataset; 1m BTCUSDT only unless
  more history is provisioned; funding unmodeled; perps only
- Phase 11E result: RED / NO EDGE — REAFFIRMED, unchanged by Phase 11F.
  Phase 11F does not alter, rescue, or re-litigate that result; the frozen
  BREAKOUT_CONTINUATION is preserved as LEGACY_REJECTED_CONTROL only.
