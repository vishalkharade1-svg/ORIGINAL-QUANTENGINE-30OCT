# QUANTENGINE — STAGE 4 RECERTIFICATION REPORT

```text
STAGE 4 PAPER CONDITIONALLY CERTIFIED
STRATEGY = NO EDGE ESTABLISHED
OOS = ABSENT/BLOCKED
LIVE = NO-GO
SECURITY = BLOCKED
```

This milestone certifies engineering/paper execution behavior only.

It does not certify strategy profitability.

It does not constitute out-of-sample evidence.

It does not constitute live-trading approval.

No strategy is promoted.

LIVE remains NO-GO.

SECURITY remains BLOCKED until operator remediation.

If paper economics are negative, that result is preserved and is not optimized away.

PAPER ONLY / NOT OOS / NOT STRATEGY CERTIFICATION / NOT LIVE
```

Prior records: `docs/stage4_paper_certification.md` (initial
certification), `docs/stage123_final_report.md`,
`docs/stage123_closure_certification.md`. This report records ONLY
the recertification delta: forensic corrections, re-verification,
exact counts, and the single recertification commit. Sections
follow the mandated §36 A–P.

---

## A. Repository identity

```text
HEAD (recert commit): see §37 — single commit on main above 343f4ae
parent: 343f4ae (Stage 4, verified present; its parent fad7329)
branch: main
working tree at commit: clean except two pre-existing unrelated
  notes ("muse suggetions.md", "muse suggetions1.md") — untracked
  since before the research seals (the seals explicitly exempt
  them), left untracked per GIT DISCIPLINE.
```

Worktree-cleanliness finding (§4): in THIS environment the tree
was genuinely clean at arrival (no 491-file churn, `.env.example`
present and tracked, no deletions). The externally observed churn
is consistent with `core.autocrlf=true` checkout differences, not
with repository content changes — nothing to normalize or revert
here, no history action taken.

## B. Test accounting

```text
pytest collected: 2751 (stable across 3 consecutive collects;
  canonical per pytest.ini testpaths=tests)
pytest executed: 2751 passed, 0 failed, 0 errors, 0 skipped,
  0 collection failures (7 chunk runs + soak file; every one of
  184 tests/test_*.py files executed exactly once — verified by
  filename audit; research 11g content re-verified post-commit)
unittest discovered (scoped, canonical-equivalent
  `discover -s tests -t .`): 2739 ran — methodology delta vs
  pytest is 12 = 5 module-level function tests pytest collects
  but unittest ignores by design (test_trade_simulator.py:
  test_buy_take_profit, test_buy_stop, test_sell_take_profit,
  test_sell_stop, test_pnl) + 2 unattributed collection-rule
  residuals (both exact totals stated; pytest is canonical)
unittest executed: 2739 ran, 8 failed, 0 errors, 0 skipped
  (pre-commit run; all 8 = tree-seal tests tripped by the then-
  dirty recertification tree — same established mechanism;
  post-commit seals re-verified green, see N)
unittest discovered (bare root `discover`): TIMEOUT / NOT
  COMPLETED — collects .venv/_archive per pytest.ini warning;
  not a valid suite invocation (reported per rule, not as PASS)
Stage 4 tests: 64 (cert, incl. WS storm + gap detection + signed
  RR) + 3 (soak file) = 67, all passed
tree-seal tests: 32 governance (post-commit green) + full 11g
  content suites (post-commit green)
skipped: 0 | errors: 0 | failures: 0 (post-commit) |
  collection errors: 0 (pyarrow/pandas provisioned; parquet
  replay green)
```

## C. Defects corrected (all pre-existing or self-authored; none hidden)

1. `tests/test_stage4_paper_certification.py::TestCrashDrills`
   (`or True` restart assertion): old `assertTrue(A.isdisjoint(B)
   or True)` — always true. Replaced with: real disjointness
   `assertEqual(journal ∩ resumed, set())` per crash point +
   per-segment ledger identity + reconciler re-verification
   through the snapshot seam (MATCH consistent / MISMATCH+halt
   contradicted) + warmup-divergence tripwire
   (`assertNotEqual(union, reference)` — documents
   DURABLE_RUNTIME_STATE=YELLOW; a durable-state future must
   update it deliberately) + new `test_fresh_registry_ignores_
   journal` proving the RAM-only boundary (fresh registry mints
   a duplicate; same registry dedupes). Verified: crash matrix
   green.
2. `TestMultiSymbol::test_independent_symbols` (`or True`
   disjointness): replaced with same-seed BTC/ETH runs proving
   identical decisions yet zero shared mutable state (live
   object-identity disjointness, distinct registries/accounts/
   contexts/pipelines — ids never persisted, fixing my own
   determinism violation of comparing `id()` values across runs)
   + post-corruption ETH re-run equals reference + NEW
   `test_btc_failure_does_not_corrupt_eth` (poison candle fails
   BTC LOUDLY with TypeError; ETH matches reference exactly).
   Verified green. Incidental true finding: setup-id namespace
   carries no symbol prefix (same-seed ids identical across
   symbols) — harmless today (isolation is per-object), logged
   as a namespace limitation for any future shared layer.
3. `tests/test_market_hardening_9s.py:28` (pre-existing `or True`):
   removed the tautology tail; assertion now genuinely checks
   `ReconnectPolicy`/`exponential_backoff` presence (passes —
   strengthening, documented per modification rule).
4. `test_startup_cases` case D (`assertIn(..., (MATCH,MISMATCH))`):
   pinned to the documented degrade path (`load_snapshot()
   is None` + exact `MATCH`), so a future fail-closed change
   must update it deliberately.
5. Prior-report correction (§26): the production parquet was
   mischaracterized as a "flat stub" from head/tail sampling;
   full scan shows 1440 varied candles with volume (BTCUSDT 1m,
   2026-09-05→06). Replay metrics now printed by the test:
   1440 bars / 1 trade / +0.001345 (dust, NOT performance).
6. Prior-report economics preserved UNCHANGED: 30k soak
   (seed 42) 192 trades / net −10.451701 — same seed, same
   costs, same code path for economics (realized-RR sign change
   affects only the reported stamp, not fills/PnL). NOT
   optimized, seed/costs/trades intact.

## D. Paper certification

Startup A–E green (flat boot MATCH + paper SKIP with zero feed
touches; journaled-open vs flat HALT; flat vs open HALT; corrupt
journal degrades via documented path; missing state flat-inits
only). 30k synthetic soak (seed 42, BTCUSDT): 30000 bars /
192 signals→orders→fills / 0 rejections on-path (scripted-path
rejects in cert) / expiry proven in cert / 0 cancellations
(single-slot design, no cancel path) / 0 reconciliation halts on
the clean path (halt classes proven in cert drills) /
violations=[]. Real-data replay: 1440/1440 bars, 1 trade.

## E. Accounting

Zero-cost profile: gross +0.001345 replay / soak realized
−10.451701 with commission=slippage=0 explicitly (ZERO-COST
ENGINEERING SOAK — never a profitability claim). Nonzero
profile math certified separately (explicit CostSpec incl.
11F-C-shaped values as labeled scenario, hostile ±epsilon on
every leg). Funding unmodeled (explicit zero, documented).
Ledger identity holds every segment and run.

## F. RR

Order-time: 5.99 REJECT / 6.00 ACCEPT / 6.01 ACCEPT / tick-short
REJECT / lying-field REJECT, all 10 sized soak orders ≥6.0 at
gate time. Realized (signed, `actual_risk_reward`): deterministic
(`realized_rr()` pure helper + stamp-equality on every mutating
fill + double-run identical); long/short favorable/adverse gaps,
through-target negatives, tick moves, zero-risk→0.0 all tested.
Minimum observed on soak path: erosion to ~0.02 on gapped opens
(measured, reported). Classification: ORDER-TIME RR GATE = GREEN;
REALIZED FILL RR OBSERVABILITY = FIXED; REALIZED RR ECONOMIC
EROSION = YELLOW.

## G. Restart

12 drills: 10 resume-forward (journal → rebuild → reconcile →
no duplicate identity, per-segment ledger identity, MATCH on
consistent snapshot, HALT on contradiction) + partial-fill HALT +
mid-reconcile relatch + corrupt-journal HALT + fresh-registry
hazard proof. Durable: reconciler snapshot only (+test drill
journals, explicitly NOT production). RAM-only (re-stated):
positions, orders, PnL/drawdown, cooldowns, pending windows,
reservations, halt state, indicator warmup (proven divergent).
DURABLE_RUNTIME_STATE = YELLOW.

## H. WebSocket

Transport GREEN: connect/subscribe/receive, 5000-frame storm
(malformed isolated, heartbeat classified, unknown stays 0),
duplicate/out-of-order drops counted, resubscribe payload,
stale health degrades with no order surface (structural).
Gap: NEW `candle_gaps` detection counter at the transport
(finished-candle cadence vs builder window; tested: 2 skipped
buckets counted, steady cadence adds none). GAP_REPAIR =
NOT_IMPLEMENTED (no sequence numbers, no backfill) — detection
without repair; continuation policy unchanged and documented.

## I. Multi-symbol

BTCUSDT + ETHUSDT (exact symbols). Independent pipelines,
contexts, registries (order + economic), accounts, PnL;
mutation- and failure-injection proof; shared portfolio caps
(max_positions=1 blocks second symbol deterministically);
poison candle fails loud without cross-contamination. Two-symbol
evidence only — no universal claim. Setup-id namespace carries
no symbol (limitation logged; harmless per-object today).

## J. Determinism

10k metrics JSON byte-identical across two runs (340 s);
small-run doubles identical; 30k soak metrics deterministic
(proven identical path; rerun passed); no uuid/random/
wall-clock/process-hash in certification artifacts (transient
`id()` comparison removed from persisted metrics); soak
wall-clock printed as telemetry only.

## K. Causality

Dataset-B-differs-after-boundary and future-outcome-mutation
tests: all pre-boundary decisions (indicators, market state,
signals, risk, sizing, intents, accounting) identical.
CAUSALITY/LOOKAHEAD ENGINEERING ONLY — not OOS.

## L. Resource bounds

fractal_cache 5000 (ceiling HIT and HELD — reported, limit NOT
raised); backtester pending peak 7; registry 192 (closed-trade
retention); open_peak ≤1; no NaN/inf; no cross-contamination;
no bypass.

## M. Security

`git log --all -- .env`: 6 commits (63cd4f1, e686ccd, d5846fc,
e49f61e, 2f9bf0e, 131660f); no `*secret*` paths; tracked-source
scan clean (no live-format assignments). SECURITY = BLOCKED —
operator must revoke/rotate, provision securely, restrict local
`.env`, decide purge. No rotation/revocation/rewrite/push
performed here.

## N. Research

`git diff -- research/` empty; freeze `f803fe7d…` intact; 11F/11G
hypotheses, manifests, datasets untouched; D3 sealed (counters
green); conclusions unchanged: NO EDGE ESTABLISHED, OOS
ABSENT/BLOCKED. Post-commit: 32/32 seal governance + full 11g
content suites green.

## O. Final gate matrix

| Gate | Status | Evidence | Remaining limitation |
|---|---|---|---|
| Repository integrity | GREEN | closure+stage4 commits verified; clean tree | two pre-existing untracked notes (exempted) |
| Security | BLOCKED | 6 history commits reachable; source scan clean | operator rotation/provision/purge decision |
| Cost configuration | YELLOW | explicit profiles; venue values CONFIGURATION_REQUIRED | no venue-realistic numbers provisioned |
| Accounting | GREEN | identity every segment/run; hostile mutations | funding unmodeled (explicit zero) |
| RR order gate | GREEN | 5.99/6.00/6.01/tick/lying; 10/10 soak orders ≥6 | — |
| Realized RR | YELLOW | signed stamp deterministic; erosion measured | gapped fills erode to ~0.02 (market reality) |
| Risk | GREEN | gates+fail-closed numerics+kill seam | — |
| Paper execution | GREEN | 192/192 identity-chained fills; rejects/expiry/dupes | no cancel path (single-slot design) |
| Order lifecycle | GREEN | all terminals; PARTIAL≠FILLED; unknown no-op | partials halt (no partial execution) |
| Reconciliation | GREEN | 10 classes + startup A–E; halt at boundary | — |
| Restart fail-safe | GREEN | 12 drills; no dupes; halt relatches | resume≠uninterrupted (warmup) |
| Durable runtime state | YELLOW | reconciler snapshot only | RAM-only list re-stated; test journals ≠ production |
| WebSocket transport | GREEN | storm/reconnect/resubscribe/heartbeat/stale | — |
| WebSocket gap integrity | YELLOW | NEW detection counter; repair NOT_IMPLEMENTED | no sequence numbers/backfill |
| Kill switch | GREEN | 4 states + tamper + env + explicit recovery | env/flags are the whole mechanism (no HSM) |
| Multi-symbol paper | GREEN | BTC+ETH isolation+mutation+failure proofs | two symbols only; id namespace unprefixed |
| Paper/live isolation | GREEN | call-counted 0 writes (paper/research/AI) | — |
| Resource bounds | GREEN | cache/pending/registry peaks pinned | cache sits AT ceiling by design |
| Determinism | GREEN | byte-identical doubles; no nondeterministic ids | wall-clock telemetry separated |
| Causality | GREEN | both future-mutation suites identical prefix | engineering only, not OOS |
| Research immutability | GREEN | empty diff; freeze; seals post-commit green | — |
| Real-data soak | YELLOW | 1440/1440 replay green (dust economics) | 30k real INSUFFICIENT_DATA (only 1440 exist) |
| Synthetic soak | GREEN | 30k clean, violations empty | ZERO-COST label; not profitability |
| Strategy economics | ABSENT* | net −10.45 preserved, unoptimized | *no edge; reported not certified |
| OOS | ABSENT | no OOS created/claimed | BLOCKED pending separate phase |
| Strategy certification | ABSENT | NO EDGE ESTABLISHED stands | — |
| Live readiness | BLOCKED | NO-GO (security + no edge + no OOS) | operator prerequisites |

## P. Limitations (not hidden)

Security history exposure; venue-cost CONFIGURATION_REQUIRED;
funding unmodeled; realized-RR erosion; gap repair absent;
RAM-only trading state + warmup divergence; 1440-bar real-data
ceiling; negative synthetic economics; no OOS; prior-report
flat-stub mischaracterization corrected above; pytest/unittest
counts differ by collection rules (5 proven + 2 residual —
both exact totals stated); bare-root `unittest discover`
TIMEOUT/NOT COMPLETED (collects .venv per pytest.ini warning).
