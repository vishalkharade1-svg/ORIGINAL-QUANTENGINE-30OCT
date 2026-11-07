# QUANTENGINE — STAGE 1–3 PRODUCTION HARDENING: FINAL REPORT

Verdict: **CONDITIONAL PAPER** (NO-GO for live; see gate matrix §22).

> Passing tests do not equal production readiness. Engineering
> correctness does not equal trading profitability. No OOS evidence
> means no strategy certification. No strategy is promoted here.

Point-in-time forensics (pre-change) live in
`docs/stage123_baseline_audit.md` (HEAD `07def05`, verified
2026-09-09). This report records what was changed, what was proven,
and what still blocks production.

---

## 1. Exact starting commit

`07def0523e4e945281b0bb4e277d7a6c1eb6deda` — branch `main`,
`docs(phase11g): correct U observation chronology wording`.
`origin/main` (`699ca76`, 2026-08-01 `first commit`) is 125 commits
behind HEAD (stale remote, fetch-only — no push performed).
Extra refs are agent-checkpoint debris
(`refs/agents/be5197f0-*/checkpoints/*`) plus an unrelated local
branch `agents/todo-list-analysis-fix` (untouched). Reachable
commits on HEAD: 178 (`git rev-list --all --count`).

The working tree was ALREADY dirty at arrival (12 modified files +
4 untracked milestone files from a prior partial attempt). That
prior work (RR 6.0 config gate, `core/risk/costs.py`,
`core/live/reconciler.py`, `tests/test_hardening_stage123.py`,
fixture retargets) was forensically reviewed, kept where sound,
and completed/fixed where deficient (see §3).

## 2. Exact final commit

No commit was made (no commit/push requested or authorized).
Final state = starting commit `07def05` + working tree below (§3).
`git status --short` at close lists 18 modified + 7 untracked
paths (5 milestone + 2 pre-existing unrelated notes files
`muse suggetions*.md`, untouched).

## 3. Files changed (tracked modifications)

| File | Change |
|---|---|
| `config/risk_settings.py` | `MIN_RISK_REWARD` 2.5 → **6.0**, authoritative comment (pre-existing dirty; kept) |
| `core/setup/decision_engine.py` | Removed `MIN_RISK_REWARD = 2.0` shadow; gate reads `risk_settings.MIN_RISK_REWARD` live (pre-existing dirty; kept) |
| `core/risk/risk_engine.py` | Defense-in-depth RR revalidation from signal prices (never the self-reported field) + cost via `CostSpec` (pre-existing dirty; kept) |
| `core/live/broker_engine.py` | Reconciler wiring: auto-feed from broker executor (LIVE only), gate-first arming (zero transport on refused gate), halt blocks routing, snapshot journal every live candle (extended this session: auto-wire + gate-first) |
| `main.py` | LIVE branch wires `Reconciler(executor, snapshot data/runtime/broker_state.json)` (pre-existing dirty; kept) |
| `core/risk/portfolio.py` | **NEW this session**: fail-closed non-finite inputs (`non_finite_input` / `non_finite_equity` / `non_finite_daily_pnl` block new entries) |
| `core/market_structure/swing_engine.py` | **NEW**: bounded `_fractal_cache` (FIFO, 5000) + `cache_size()`; eviction recomputes identically |
| `data/delta/delta_subscription_stream.py` | **NEW**: explicit `heartbeat_frames` (keepalive no longer pollutes `unknown_frames`), `_last_heartbeat_ts`, 0.5 s stop-aware pump-restart backoff |
| `core/execution/order_registry.py` | **NEW**: `SUBMITTED`/`ACKNOWLEDGED`/`PARTIAL` constants documenting exchange-observed transit states; `PARTIAL != FILLED` pinned |
| `tests/test_broker_engine.py` | 3 live tests re-choreographed to verified-boot contract (boot flat + visibility beat; ALL assertions preserved, close/reentry timestamps +1 bar — see §9) |
| `tests/test_operational_robustness_11c.py` | 1 test updated to pin the new heartbeat contract (heartbeat→`heartbeat_frames`, unknown still→`unknown_frames` — strengthened, not weakened) |
| `tests/test_{backtester_breakout,risk_execution_contract,setup_decision_contract,execution_lifecycle,scanning,zone_freshness,research_journal_9a}.py` | Fixture retargets to RR ≥ 6.0 (pre-existing dirty; verified assertion-preserving, kept) |

New files: `core/live/reconciler.py`, `core/risk/costs.py`,
`tests/test_hardening_stage123.py` (kept; fixed unreachable-code
bug §16), `tests/test_stage123_operational.py` (new, 52 tests),
`docs/stage123_baseline_audit.md` (kept), this report.

## 4. Files unchanged (materially)

`research/` (zero modifications — verified `git status` clean),
`backtesting/`, `core/backtesting/*`, `risk/`, `config/settings.py`,
`config/trading_profile.py`, `core/execution/live_safety_gate.py`,
`core/exchanges/`, D3, all frozen datasets/manifests, `.env`
(ignored, never committed).

## 5. Security findings — SECURITY_BLOCKED (fail-closed)

Tracked source: CLEAN — every `API_KEY`/`API_SECRET` hit is a
synthetic fixture, empty default, env indirection, or isolation-guard
name literal (new negative test
`test_security_scan_no_real_credentials` enforces this).
`.env.example` ships empty credentials by design; `.gitignore`
covers `.env`/`.env.*`/`*.pem`/`*.key`.
NEVER were credential values printed anywhere (shapes/commit IDs
only, per baseline §1). `LiveSafetyGate` never logs secrets
(presence-boolean only). Working-tree `.env` (ignored) carries
live-shaped values whose validity was deliberately UNTESTED (no
exchange contact). **Operator actions (outside this milestone, no
auto-rotation performed): confirm rotation/revocation of the
historically exposed Delta pair; restrict the local `.env` host;
explicitly authorize-or-decline history purge. No rewrite, no
force-push, no programmatic rotation was performed.**

## 6. Credential-history evidence

6 commits touch `.env` (all ancestors of HEAD, reachable forever
without rewrite): `63cd4f1` (add), `e686ccd`, `d5846fc`,
`e49f61e` (checkpoint re-add), `2f9bf0e`, `131660f` (untrack).
5 historical blobs carry live-format `DELTA_API_KEY` (31-char) /
`DELTA_API_SECRET` (62-char) values (hashes recorded in baseline
audit, values never reproduced). Untracked since `131660f`, never
purged, no rotation evidence in-repo. **Verdict stays
SECURITY_BLOCKED while exposure is unresolved.**

## 7. Cost-path evidence

Single production formula (frozen, now centralized):
`commission = per_trade + notional * rate`,
`slippage = 2 * notional * slippage_bps / 10000`
(`core/risk/costs.py:48-55`, `CostSpec` immutable, NaN/inf/negative
refused). Production defaults explicit zero
(`COMMISSION_PER_TRADE/RATE/SLIPPAGE_BPS = 0.0` — unchanged; any
paper/live profitability claim on defaults is cost-unrealistic BY
CONSTRUCTION, documented in module + report). Path:
`risk_settings → from_settings() → RiskEngine → OrderIntent →
TradeSimulator.open_trade → accounting.net_pnl`
(verified shared by backtest/paper/live-dry; live-exchange closes
use exchange authority, modeled costs zeroed to avoid
double-count). `COMMISSION_RATE = 0 / SLIPPAGE_BPS = 0` do NOT
affect frozen research: 11F/11G economics assemble explicit
`COST_SCENARIOS_11F` specs (A/B/C/D pinned; research ladder test
passes) and never read production globals. Legacy 11B script ladder
is script-only. No frozen result was altered.

## 8. RR-path evidence

One authoritative source: `config/risk_settings.py:403`
`MIN_RISK_REWARD = 6.0`. Calc:
`trade_setup_builder.py:191-193`
`rr = |target-entry| / |entry-stop|` (side-checked, no costs, no
tick rounding at calc — documented). Primary gate:
`decision_engine.py:188` (`rr < 6.0` → terminal "Risk Reward"
rejection). Defense-in-depth: `risk_engine.py:273-287` recomputes
from entry/stop/tp and skips sizing (`ORDER_SKIPPED_RR`) — a lying
`risk_reward` field (tested: 5.0-as-99.0) cannot pass. Dead:
`trading_profile.min_rr` (no production importer — test-pinned).
Confusing-but-inert: `PositionSize.risk_reward`
(notional/expected_loss — semantics pinned by test, never gated).
Research `risk_reward: 2.0` pins are frozen-hypothesis constants,
never production gates (untouched). Boundaries proven:
5.99 rejects / 6.00 accepts / 6.01 accepts / tick-short rejects.

## 9. Reconciliation architecture (`core/live/reconciler.py`)

Fail-closed comparator, never trades: verdicts
MATCH / IN_FLIGHT / MISMATCH (halt) / UNKNOWN→halt / SKIP (paper).
Startup: journal + exchange vs local; any divergence → halt +
explicit `resolve(note)` required (empty note refused).
Runtime (every 30 bars): qty (incl. `PARTIAL_FILL_QTY`), side,
entry (tolerance), unexpected/missing, stale orders past transit
window, executor errors. Snapshot journal atomic (tmp+replace),
schema-checked, corrupt→degraded (never crash); halt flag NOT
persisted (every boot re-derives). Broker wiring: LIVE auto-feed
from executor, paper passive, refused gate = zero transport
(includes verification read), halt blocks `_route` first.
`Delta {"result": [...]}` envelopes unwrapped (matches `_sync_live`).
Pre-existing live-test choreography change (this session):
boot-flat + visibility beat in 3 tests; assertions preserved
(registry counts, execute counts, PnL 0.62, no-double-reentry,
refill). This adapts fakes to the mandated contract; it does not
weaken them.

## 10. Restart behavior

RAM-only (unchanged, documented): order/position registries,
account/PnL/drawdown, cooldowns, cooldowns/pending windows, swing
cache, router dedupe, halt flag. Durable: reconciler snapshot
(`data/runtime/broker_state.json`, created lazily) + instrument
catalog/research JSON/parquet (non-trading). Crash drill proven by
test: open snapshot + flat exchange → MISMATCH halt, zero routing
until operator resolves; clean flat boot arms; halt latches across
re-checks. Restart does NOT duplicate (halt precedes route),
does NOT forget (journal re-read), does NOT auto-resolve.

## 11. WebSocket behavior

Multiplexed `DeltaSubscriptionStream` (one connection, full
re-subscribe payload), per-symbol workers own reconnect with capped
backoff+jitter, resubscribe without restart, `CandleRouter`
dedupe(256)/disorder-drop/forming-skip, staleness health.
This session: keepalive/control frames (`heartbeat/subscribed/
success/pong/ping`) counted as `heartbeat_frames` (were polluting
`unknown_frames`), liveness timestamp tracked, pump hot-spin fixed
with 0.5 s stop-aware backoff. Still absent BY DESIGN (documented,
not claimed): WS ping/pong (public ticker feed — liveness is
data-driven staleness), sequence-gap detection + REST backfill
(gaps counted, never repaired — router is detect-and-drop).
Failure tests: malformed/duplicate/out-of-order/heartbeat/
reconnect-payload/multi-symbol isolation all pass; a malformed
frame never kills the multiplexed pump (isolation pre-existed,
re-verified).

## 12. Order lifecycle behavior

Registry states: NEW→PENDING→FILLED / CANCELLED / REJECTED /
EXPIRED / INVALIDATED (terminal). Exchange-observed transit named
(`SUBMITTED`/`ACKNOWLEDGED`/`PARTIAL`) but never registry-written.
Simulator is single-slot all-or-nothing BY DESIGN (second
concurrent open refused; registry dedupes per setup_id — tested).
Partial fills are handled fail-closed at reconciliation
(`PARTIAL_FILL_QTY` halt), never by silent completion; test pins
`PARTIAL != FILLED`. Exits remain SL/TP-only (SL-first ambiguity
unchanged, documented). Cancelled/expired watch-clear verified.

## 13. Paper/live parity

Shared (proven identical): InstitutionalPipeline, RiskEngine sizing
(same signal → same order, tested), OrderIntent, TradeSimulator,
Account math, OrderRegistry, CostSpec path. Divergent (pinned
intentional): paper = multi-symbol per-key runtimes
(`RealTimeEngine` + `PaperExecutionAdapter`: execute records
locally, all live-only reads raise `PaperOnlyError` — tested);
LIVE = single-symbol (`SYMBOLS[0]` legacy feed + `BrokerEngine`
dry_run=False). LIVE stays single-symbol (scope pin, not expanded
here). Paper makes zero exchange writes (negative-tested,
transport-call counted). Shutdown/restart: paper resets clean;
live re-arms + re-verifies.

## 14. Configuration authority map

AUTHORITATIVE (`config/risk_settings.py`): balances, RISK_PER_TRADE,
allocation, quantity/dust, exposure/pending/direction caps,
feasibility ATR bands, entry modes/windows, zone ages (500/5),
distance cap (30 ATR), stop floor (0.10 ATR), cooldowns (30),
tick/economic cluster, costs (0.0×3), loss caps (2 %/5 %/10 %),
open/risk/correlation caps, MIN_CONFIDENCE 80, MIN_RISK_REWARD 6.0,
PAPER/LIVE flags. SHADOW (engine hard-code, documented YELLOW —
not in mandate scope, unchanged): DecisionEngine confidence 70
(vs config 80), regime score 70 (no config twin), sizer
confidence/regime/drawdown scalers, execution-engine direction-cap
fallback. DEAD: `trading_profile.min_rr` (test-pinned unread).
RESEARCH-ONLY: 11E/11F/11G ladders + frozen pins.

## 15. Mathematical verification

ATR Wilder RMA (seed SMA + recurrence) pinned against independent
recomputation; sizing `risk_amount/stop_distance == quantity`;
PnL direction-explicit (long/short × win/loss signs);
fees/slippage explicit (`net = gross − commission − slippage`,
hostile ±1e-6 mutations all move the result);
RR `reward/risk`; `actual_risk ≤ configured_risk` (expected_loss ≤
1 % × 2000); accounting identity
`opening + realized − fees = ending`. Daily breaker exact
boundary (−40.00 blocks, −39.99 permits on 2000 @ 2 %),
above/below/NaN/inf (fail-closed), ledger-fed, reset-cleared,
multi-symbol uniform.

## 16. Tests added (+ fixed)

- `tests/test_hardening_stage123.py` (37 tests): cost authority,
  1:6 RR + mutations + tick grid + lying-field, reconciler
  startup/runtime/wiring, config governance. **Fixed this
  session**: 3 governance tests were unreachable dead code after a
  duplicated `unittest.main()` block — promoted to a real
  `TestConfigGovernance` class (+1 auto-verify wiring test).
- `tests/test_stage123_operational.py` (52 tests, new): WS
  isolation/gaps, lifecycle, restart drills, parity, breakers,
  cache bound (6000-bar slide + eviction-identical + determinism),
  math regression, determinism reruns, production isolation incl.
  tracked-source credential scan.
- Modified (adaptation, disclosed): 3 broker live tests (verified
  boot), 1 heartbeat test (strengthened). No assertion weakened.

## 17. Complete test count

Full canonical suite (`pytest tests/`, run in 6 chunks):
360 + 454 + 543 + (695 + 8 seal-content passes*) + 292 + 250 =
**2594 passed, 16 failed** — all 16 are research phase-seal
tree-cleanliness guards (`test_tree_only_expected` /
`test_tree_clean_except_notes` / `test_no_production_paths` in
`test_researcher_11g_{n..u}`) that assert the working tree contains
ONLY that phase's files. They tripped at arrival (tree already
dirty) and trip on any later milestone by design; every
research-content assertion (hypotheses, freeze `f803fe7d`, lineage,
OOS gates) passes, and `research/` is byte-untouched. These seals
must NOT be edited to pass. (*chunk-4a full: 695 passed/16 failed;
targeted seal rerun: 391 passed/16 failed — same 16.)
New suites rerun twice: 89/89 identical both runs.
`python -m compileall -q .`: clean (exit True, no output).

## 18. Compileall result

Clean — no output, exit success.

## 19. Deterministic rerun result

Stage-1–3 suites twice byte-identical (89/89 both runs);
decision/cost/reconciler/config-fingerprint reruns identical;
swing 1500-bar scan identical; research determinism suites green.

## 20. Mutation-test result

RR: 6.0→5.99 rejected, 6.0 accepted, 6.01 accepted, tick-short
rejected, lying-field rejected (decision + risk layers). Costs:
±1e-6 on any leg moves net. Breakers: boundary ±1 unit + NaN/inf
all fail-closed. Registry: duplicate setup returns existing (no
second order). Gate: tampered token still refuses with zero
transport calls.

## 21. Production-isolation result

LIVE disabled by default (PAPER True / LIVE False / ALLOW_LIVE
False); `LiveSafetyGate.require` refuses default LIVE;
refused-gate candle performs ZERO transport calls (read included);
no order bypasses RiskEngine (halt check precedes route);
research harness contains no exchange-write path; paper adapter
records locally, live-only ops raise `PaperOnlyError`; dry-run
counts zero executor writes. Research cannot submit orders.

## 22. Remaining blockers + gate matrix

| Gate | GREEN | YELLOW | RED | BLOCKED |
|---|---|---|---|---|
| Security | | | | X (credential history unpurged/unrotated) |
| Accounting | X | | | |
| Cost Model | | X (explicit zero-cost default; realism gap for any live/paper P&L claim) | | |
| RR 1:6 | X (policy+enforcement) | | | |
| Risk | X (gates+fail-closed numerics) | | | |
| Reconciliation | X (mechanism+tests) | | | |
| Restart | | X (journal covers live position/orders; full risk/cooldown/PnL restore absent) | | |
| WebSocket | | X (reconnect/isolation proven; no ping/pong, no gap-fill by design) | | |
| Order Lifecycle | | X (partials fail-closed, no partial-fill execution; SL/TP-only exits) | | |
| Paper/Live Parity | | X (shared math proven; LIVE single-symbol scope pin) | | |
| Research | X (untouched, seals content-green) | | | |
| OOS | | | X (absent) | |
| Strategy Edge | | | X (NO EDGE ESTABLISHED stands) | |
| Live Safety | | | X (SECURITY_BLOCKED ⇒ no live) | |

P0s: (1) credential-history exposure unresolved; (2) zero-cost
production defaults (any live/paper profitability claim invalid
until real venue fees configured — values change, frozen formula
does not); (3) no OOS evidence / no edge. Non-P0 YELLOWs above are
documented limitations, not launch approvals.

## 23. Explicit research status

UNTOUCHED. 11E/11F/11G hypotheses, frozen datasets (`f803fe7d`
manifest verified by seal suites), D3 (sealed 0/0/0), and all
historical conclusions byte-identical. **NO EDGE ESTABLISHED**
stands. No optimization, no threshold tuning for trade count (the
6.0 gate is a project requirement, not a fitted parameter), no D3
activity, no promotion of any strategy.

## 24. Explicit OOS status

ABSENT. No new out-of-sample evidence was fabricated, mined, or
claimed. No strategy is certified. The mandated RR change WILL
shift production-pipeline outputs (Gate A fingerprint delta is
RR-only by construction: thresholds + retargeted fixtures, no
logic change) — that delta is declared, not hidden.

## 25. Final GO/NO-GO — CONDITIONAL PAPER

Rationale: measurement, safety, execution, and operational
foundations are now trustworthy within the stated bounds
(reconciliation fail-closed, verified boot, 1:6 enforced at two
layers, costs centralized with explicit zero defaults, breakers
fail-closed, WS isolation proven, restart drills green,
production-isolation negative-tested). Live is refused by
unresolved credential exposure alone, and strategy certification
is refused by absent OOS/edge. Paper/shadow operation is
permitted ONLY with real-fee cost overlays (never default-zero
claims) and continuous reconciliation monitoring. Never LIVE READY
while any P0 stands — three stand.
