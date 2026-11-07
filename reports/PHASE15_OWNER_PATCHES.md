# PHASE 15 — OWNER PATCHES (Category B — PROPOSED, NOT APPLIED)

Prepared by Phase 15 agent from HEAD `ffefa14a8729f6d2160db3735a06257cbb6ab48b`.
None of the following is applied. Each requires explicit operator approval, and
approval must name these exact file-and-value substitutions (not an unrestricted
rewrite of frozen research). Run the listed test plan after application, then
regenerate `BUILD_MANIFEST.sha256` with
`python scripts/generate_manifest.py --root . --write BUILD_MANIFEST.sha256`
and verify with `--verify` (exit 0 required).

---

## PATCH-1 (B-01) — canonical strategy-digest re-registration (4 substitutions)

Exact replacements (line-level):

```diff
--- a/tests/test_oos_feasibility_17.py        (line 42)
@update
-STRATEGY_HASH = ("c52e648ca24fb03b9ba818ebb766e32b035b48df201d5a2a1b254d04f7f3d5a6")
+STRATEGY_HASH = ("9c56f3ff7dea2a3ea98adf226aff775d263ebfcf1bbb2697ca244ab6cd54f35a")

--- a/tests/test_oos_validation_18.py        (line 38)
@update
-STRATEGY_HASH = ("c52e648ca24fb03b9ba818ebb766e32b035b48df201d5a2a1b254d04f7f3d5a6")
+STRATEGY_HASH = ("9c56f3ff7dea2a3ea98adf226aff775d263ebfcf1bbb2697ca244ab6cd54f35a")

--- a/tests/test_oos_data_extension_19.py   (line 38)
@update
-STRATEGY_HASH = ("c52e648ca24fb03b9ba818ebb766e32b035b48df201d5a2a1b254d04f7f3d5a6")
+STRATEGY_HASH = ("9c56f3ff7dea2a3ea98adf226aff775d263ebfcf1bbb2697ca244ab6cd54f35a")

--- a/research/results/phase14_executable_edge_forensics.json (line 1029)
@update
-  "strategy_hash": "c52e648ca24fb03b9ba818ebb766e32b035b48df201d5a2a1b254d04f7f3d5a6",
+  "strategy_hash": "9c56f3ff7dea2a3ea98adf226aff775d263ebfcf1bbb2697ca244ab6cd54f35a",
```

Evidence basis (all VERIFIED BY BYTE/HASH CHECK, refresh-verified today):
worktree raw construction = `9c56f3ff…`; `QuantEngine_PHASE{165..185}_RELEASE_CANDIDATE.zip`
all carry `9c56f3ff…` for the same 9 files; PHASE161/162 carry the pre-165 epoch
`f8407e77…`; HEAD-committed raw construction = `9eff61b7…`; the pin
`c52e648c…` matches neither.
`tests/test_readiness_16.py::test_strategy_hash_pinned` auto-passes with no
source edit once the JSON artifact carries the new constant.

Additional constraint this phase (project's own read-only procedure):
`python scripts/recertify_strategy_digest.py --json` →
`recorded_digest = c52e648c…`, `canonical_digest(CRLF→LF construction) =
ba17582d0ab96913f81d0e6ac652368e609bb28f22a24200f53bf9b6cd60ded5`,
`matches_recorded = false`, `status = BLOCKED` (no recorded research
re-execution under the current source). Meaning: PIN-9C56 re-registration
aligns the tests+archives with the RELEASED bytes (a release-lineage repair)
but is NOT a strategy re-certification; EDGE/status stays
`EDGE NOT ESTABLISHED` regardless. Owner may authorize the subs while
acknowledging this boundary, or defer pending an authorized research
re-execution.

Test plan after PATCH-1 (exact):
```
python -m pytest tests/test_oos_feasibility_17.py tests/test_oos_validation_18.py tests/test_oos_data_extension_19.py tests/test_readiness_16.py -q   => expect 0 failed (5 previously red nodes go green)
python -m pytest tests -k "oos or readiness or provenance" -q                                                                                        => expect 0 failed
python scripts/recertify_strategy_digest.py            => still BLOCKED (unchanged policy; do NOT edit the script)
```

## PATCH-2 (F4) — stage4 sequential-ledger fixture geometry (frozen test, owner edit)

Exact replacement block (`tests/test_stage4_paper_certification.py`,
`TestPaperAccounting::test_sequential_ledger_matches_registry`,
current lines 307-317; only 2 logical changes: conditional geometry in `mk()`,
second bar high `161.0`→`171.0`):

```diff
--- a/tests/test_stage4_paper_certification.py
@@ TestPaperAccounting.test_sequential_ledger_matches_registry @@
         mk = lambda d, e, q=2.0, i="S": SimpleNamespace(
             direction=d, entry=e, stop_loss=e - 10.0,
             take_profit=e + 60.0, quantity=q, risk_amount=20.0,
@@
         sim.open_trade(mk("BEARISH", 160.0, i="T"), timestamp=3)
         sim.update(SimpleNamespace(high=161.0, low=150.0, close=150.0,
                                    timestamp=4))
```

Proposed after-state (keeps BULLISH leg byte-identical; makes the BEARISH leg
valid per the frozen guard `core/backtesting/trade.py:184-192` and lets it
close in-bar by touching its own stop above entry):

```python
        mk = lambda d, e, q=2.0, i="S": SimpleNamespace(
            direction=d, entry=e,
            stop_loss=(e - 10.0) if d == "BULLISH" else (e + 10.0),
            take_profit=(e + 60.0) if d == "BULLISH" else (e - 60.0),
            quantity=q, risk_amount=20.0,
            risk_reward=6.0, score=80.0, confidence=85.0,
            setup_id="%s-%s" % (i, e), symbol="TEST")
        sim.open_trade(mk("BULLISH", 100.0), timestamp=1)
        sim.update(SimpleNamespace(high=170.0, low=99.0, close=160.0,
                                   timestamp=2))
        sim.open_trade(mk("BEARISH", 160.0, i="T"), timestamp=3)
        sim.update(SimpleNamespace(high=171.0, low=150.0, close=150.0,
                                   timestamp=4))
```

Rationale (invariant preserved): the node tests sequential
ledger==registry net accounting across two in-bar-closed legs; geometry was
never its intent. 1:6 RR is preserved (stop distance 10, tp distance 60 both
directions). Blast radius: this single function (grep-verified). 1-line
alternative (weaker; not recommended): flip leg 2 to BULLISH.

Test plan after PATCH-2:
```
python -m pytest tests/test_stage4_paper_certification.py -q            => expect 0 failed
python -m pytest tests -k "paper_accounting or registry" -q             => expect 0 failed
```
Engine files: ZERO changes. `OPEN_TRADE_VALIDATION_FAILED` must no longer
appear for `setup_id=T-160.0`.

## PATCH-3 (F5b) — Phase155 scan-boundary vs provenance input documentation

Exact change (`tests/test_release_consistency_phase155.py`, in
`test_no_text_artifact_embeds_own_archive_hash`, insert directly after the
existing `BUILD_MANIFEST.sha256` skip, line 119-121):

```diff
--- a/tests/test_release_consistency_phase155.py
@@
             if path.name == "BUILD_MANIFEST.sha256":
                 continue
+            if "reports" in rel.parts and rel.name.endswith("_PROVENANCE.json"):
+                continue
             if path.name.startswith("QuantEngine_") and path.suffix.lower() == ".zip":
                 continue
```

Rationale: `reports/PHASE165_PROVENANCE.json` `input` block (lines 61-64)
documents `input.archive`/`input.sha256` = the PHASE162 archive hash
`e687f791…` — provenance documentation of an external input, not an unprovable
self-reference; the phase155 invariant targets self-embedding. Skipping
`reports/*_PROVENANCE.json` mirrors the existing structural skips
(`BUILD_MANIFEST.sha256`, `QuantEngine_*.zip`). The provenance record stays
byte-frozen; `test_gates_files_do_not_embed_archive_hash` (lines 70-86) stays
red-able for the enumerated gates files.

Test plan after PATCH-3:
```
python -m pytest tests/test_release_consistency_phase155.py -q          => expect 0 failed (self-embed invariant intact for all non-provenance files)
python -m pytest tests -k "release_consistency or release_records" -q   => expect 0 failed
```

---

## Application protocol (owner-authorized apply)

1. Owner approval names PATCH-1/2/3 explicitly (file+value level).
2. Agent applies ONLY the approved substitutions (no other edits).
3. Run each patch's test plan (above) — all must pass; failures stop everything.
4. `python scripts/generate_manifest.py --root . --write BUILD_MANIFEST.sha256`
   then `--verify` (exit 0).
5. Update the register/ledger rows (B-01 nodes green; F4/F5b closed) with the
   run outputs appended verbatim.
6. Any decline keeps current behavior: the affected nodes stay red with the
   documented classifications (fixture-drift / scan-boundary / stale-pin).
