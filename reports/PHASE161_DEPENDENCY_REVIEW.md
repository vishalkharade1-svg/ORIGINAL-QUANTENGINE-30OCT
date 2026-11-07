# Dependency review — Phase 161 (environment adoption)

**Decision: ADOPTED and re-verified.**  Phase161 executes the deliberate step
BLOCK-160-06 declared as its unblock: the three evaluated advisory upgrades are
adopted into `requirements.txt`, the installed environment is upgraded to
match, and the entire evidence set of this candidate is re-derived under the
adopted pins.  The pre-adoption evaluation is
`reports/DEPENDENCY_UPGRADE_EVALUATION.md` (isolated venv against the Phase157
tree: zero new failures; failures/passes/skips in the same pre-existing
categories); this record is the adoption-side verification.

## 1. The pinned set and the environment it describes

`requirements.txt` is what a reproducer installs;
`reports/PHASE161_RELEASE_GATES.json` (`verification_environment`) is what this
candidate's evidence was actually produced under.  Both name exactly:

| package | pin | change this phase |
|---|---|---|
| httpx | 0.28.1 | carried |
| websockets | 12.0 | carried |
| python-dotenv | 1.2.2 | 1.0.1 -> 1.2.2 |
| pandas | 2.2.2 | carried |
| numpy | 2.1.1 | carried |
| pyarrow | 23.0.1 | 18.0.0 -> 23.0.1 |
| pytest | 9.0.3 | 8.4.2 -> 9.0.3 |

Interpreter Python 3.12.10 on Windows-10-10.0.19045-SP0.
`tests/test_dependency_pin_contract.py` enforces the agreement against the
highest-numbered gates record.  Unlike the pre-adoption phases, this record
describes exactly the environment the evidence was produced under — because
the evidence was re-derived, not carried.

Transitive note: `pyarrow` is documented in `requirements.txt` as a *transitive
runtime* dependency (pandas parquet I/O in `core/history/history_storage.py`)
despite having no direct importer in this codebase; it is pinned deliberately
and must not be dropped without replacing parquet persistence.

Relevant transitive set as installed when this candidate's evidence was
produced (from the environment freeze): anyio 4.14.2, certifi 2026.7.22,
h11 0.16.0, httpcore 1.0.9, idna 3.18, sniffio 1.3.1, typing_extensions 4.16.0
(httpx stack); python-dateutil 2.9.0.post0, pytz 2026.3.post1, six 1.17.0,
tzdata 2026.3 (pandas stack); colorama 0.4.6, iniconfig 2.3.0, packaging 26.2,
pluggy 1.6.0, Pygments 2.20.0 (pytest stack).  None is pinned in
`requirements.txt`; each satisfies the pinned set's declared requirements.

## 2. Advisory check (fresh this phase, against the adopted pins)

Method: OSV query API (`https://api.osv.dev/v1/query`), one POST per pinned
package at its pinned version, executed 2026-10-18 in this phase after the
adoption.  Raw responses: `reports/PHASE161_OSV_SCAN.json`.

| package | pinned | advisories affecting the pinned version |
|---|---|---|
| httpx | 0.28.1 | none |
| websockets | 12.0 | none |
| python-dotenv | 1.2.2 | none |
| pandas | 2.2.2 | none |
| numpy | 2.1.1 | none |
| pyarrow | 23.0.1 | none |
| pytest | 9.0.3 | none |

The three advisories that stood against the pre-adoption pins (python-dotenv
1.0.1 / CVE-2026-28684, pyarrow 18.0.0 / CVE-2026-25087, pytest 8.4.2 /
CVE-2025-71176) are cleared at the adopted versions.  No advisory remains open
against any pinned version.

## 3. Reachability greps (carried evidence, still clean)

The pre-adoption reachability analysis is now history (the advisories no longer
apply), but its search evidence is carried and re-run so the record shows the
code paths remain independent of the vulnerable APIs:

* `set_key` (the python-dotenv write path): zero hits in `config/settings.py`
  and `scripts/funding_settlement_hold.py` — the read paths use `load_dotenv` /
  `dotenv_values` only (Phase160's search, re-run for this record).
* `pyarrow.ipc`: zero references in `core/history/history_storage.py` and
  `research/phase11g/storage/store.py`; pyarrow is touched only through
  `pandas.to_parquet` / `read_parquet` and `pyarrow.parquet`, on in-tree
  project-generated files.

## 4. Why adoption was the right phase for this (and what it cost)

1. BLOCK-160-06's unblock is exactly this step, and the evaluation had already
   established the zero-new-failure basis; the remaining work was the evidence
   re-derivation itself.
2. The cost is paid, not hidden: nothing is carried that claims the old
   environment.  Every suite number, scanner verdict, gate verdict, manifest
   and run record in this candidate was produced under the adopted pins; the
   Phase160 numbers remain only as the labelled pre-adoption baseline
   (`reports/PHASE161_RELEASE_GATES.json`, `test_evidence.baseline`).
3. The pyarrow major jump is the substantive one; its only touched surface is
   parquet I/O on project-generated files, and the dataset reconstruction
   contract was re-computed independently under 23.0.1 (13 checks, 0 failures,
   canonical hash `4feccebb…` matched) rather than assumed.
4. pytest 9.0.3 changes only the local test runner; the suite's failure set is
   unchanged (the same five deliberate digest detectors, `BLOCK-161-01`), and
   every skip is accounted for node-by-node in
   `reports/PHASE161_FULL_SUITE_RUN.txt`.

## 5. What did not move

No frozen pin, dataset byte, skip reason or historical record was rewritten;
the sealed Phase160 bytes were never edited; the restricted-package posture is
unchanged; no test was weakened.  The advisories item that was BLOCK-160-06 is
closed with this record set (see `reports/PHASE161_BLOCKERS.json`,
`closed_this_cycle`); everything else stands as carried.
