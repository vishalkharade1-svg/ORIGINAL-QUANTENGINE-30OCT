# Dependency and supply-chain review — Phase 159 (2026-10-17)

Phase 159 is a hardening-only cycle: the declared dependency set is identical to
the one the Phase158 evidence was produced with.  This file re-executes the
Phase158 evaluation against this tree — the pin contract, the advisory list
(from a fresh OSV query, not carried over), and the reachability question — and
re-states the decision.

## 1. Declared set and environment agreement

`requirements.txt` declares exactly:

| package | pinned | installed in the evidence environment | agrees |
|---|---|---|---|
| httpx | 0.28.1 | 0.28.1 | yes |
| websockets | 12.0 | 12.0 | yes |
| python-dotenv | 1.0.1 | 1.0.1 | yes |
| pandas | 2.2.2 | 2.2.2 | yes |
| numpy | 2.1.1 | 2.1.1 | yes |
| pyarrow | 18.0.0 | 18.0.0 | yes |
| pytest | 8.4.2 | 8.4.2 | yes |

Interpreter: CPython 3.12.10, pip 25.0.1, Windows 10 build 19045.
`tests/test_dependency_pin_contract.py` enforces that `requirements.txt` and the
release-gates record name exactly the same versions; drift fails a test instead
of sitting in a report as a note.

Transitive note: `pyarrow` is documented in `requirements.txt` as a *transitive
runtime* dependency (pandas parquet I/O in `core/history/history_storage.py`)
despite having no direct importer in this codebase; it is pinned deliberately
and must not be dropped without replacing parquet persistence.

## 2. Advisory check (fresh this phase)

Method: OSV query API (`https://api.osv.dev/v1/query`), one POST per pinned
package at its pinned version, executed 2026-10-17 in this phase.  Raw
responses: `reports/PHASE159_OSV_SCAN.json`.  Two advisories are listed per
affected package because OSV returns both the GHSA and PYSEC records of the same
issue; they are one underlying vulnerability each.

| package | pinned | advisories affecting the pinned version |
|---|---|---|
| httpx | 0.28.1 | none |
| websockets | 12.0 | none |
| pandas | 2.2.2 | none |
| numpy | 2.1.1 | none |
| python-dotenv | 1.0.1 | CVE-2026-28684 / PYSEC-2026-2270 — symlink following in `set_key` allows arbitrary file overwrite via cross-device rename fallback |
| pyarrow | 18.0.0 | CVE-2026-25087 / PYSEC-2026-113 — potential use-after-free reading an IPC file with pre-buffering |
| pytest | 8.4.2 | CVE-2025-71176 / PYSEC-2026-1845 — vulnerable tmpdir handling |

Identical to the Phase158 evaluation — expected, since no pin moved; recorded
here from a fresh network query so this file stands on this phase's own
evidence.

## 3. Reachability, per advisory (re-verified by search in this tree)

* **python-dotenv `set_key` (CVE-2026-28684).**  The vulnerable function is the
  *write* path.  Repository searches in this tree again find the read paths
  only: `load_dotenv` (`config/settings.py`, `scripts/funding_settlement_hold.py`)
  and `dotenv_values` (credential diagnostics test).  No `set_key` call exists.
  **Not reachable** in this tree.
* **pyarrow IPC use-after-free (CVE-2026-25087).**  The vulnerable surface is
  `pyarrow.ipc` file reading.  No `ipc` reference exists in this tree:
  pyarrow is touched only through `pandas.to_parquet` / `read_parquet`
  (`core/history/history_storage.py`) and `pyarrow.parquet`
  (`research/phase11g/storage/store.py`).  The parquet files read are in-tree,
  project-generated artifacts rather than untrusted input.  **Not reachable**
  in this tree.
* **pytest tmpdir handling (CVE-2025-71176).**  A *test-tool* advisory, not a
  runtime dependency of the product.  The suite does create temporary
  directories, so the code path is used; the attack requires a local adversary
  able to pre-create symlinks in the operator's own temp directory.  **Reachable
  in principle, accepted**, with the evaluated upgrade path below.

## 4. Decision (carried, with the reason it stays)

Decision for Phase 159: **not adopted** — same reasons, now with one more:

1. `requirements.txt` is the reproducibility contract for every piece of
   evidence in this release.  Adopting a new environment without re-deriving
   the evidence under it would make the recorded `verification_environment`
   false for everything that ran before the change — and Phase159 is
   deliberately *not* an evidence-changing phase.
2. Two of the three advisories are unreachable from this codebase, so adoption
   buys nothing today that the reachability analysis does not.
3. The pytest advisory affects local test execution only.
4. Bonus reason this phase: the shipped recorded evidence (worktree and
   extracted runs) was produced under the pinned set; changing the set now
   would invalidate the very numbers a release record claims.

The block with the full disposition stays in
`reports/PHASE159_BLOCKERS.json` (`BLOCK-159-06`, `ACCEPTED_RISK_DEFERRED`).
