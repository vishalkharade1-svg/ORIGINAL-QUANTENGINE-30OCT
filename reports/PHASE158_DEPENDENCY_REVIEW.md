# Dependency and supply-chain review — Phase 158 (2026-10-16/17)

Scope: the repaired tree's declared dependency set, the environment that
produced its evidence, and every known advisory that touches a pinned version.
This is a re-run of the Phase157 evaluation against the repaired tree, with the
reachability question answered rather than deferred.

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

Interpreter: CPython 3.12.10, pip 25.0.1.
`tests/test_dependency_pin_contract.py` enforces that `requirements.txt` and
`reports/PHASE158_RELEASE_GATES.json → verification_environment.dependencies`
name exactly the same versions, so drift fails a test instead of sitting in a
report as a note — the httpx 0.27.2-vs-0.28.1 drift that motivated the contract
is the precedent.

Transitive note: `pyarrow` is documented in `requirements.txt` as a *transitive
runtime* dependency (pandas parquet I/O in `core/history/history_storage.py`)
despite having no direct importer in this codebase; it is pinned deliberately
and must not be dropped without replacing parquet persistence.

## 2. Advisory check (fresh, this phase)

Method: OSV query API (`https://api.osv.dev/v1/query`), one request per pinned
package at its pinned version, executed 2026-10-16. Raw response:
`reports/PHASE158_OSV_SCAN.json`. Two advisories are listed per affected package
because OSV returns both the GHSA and PYSEC records of the same issue; they are
one underlying vulnerability each.

| package | pinned | advisories affecting the pinned version |
|---|---|---|
| httpx | 0.28.1 | none |
| websockets | 12.0 | none |
| pandas | 2.2.2 | none |
| numpy | 2.1.1 | none |
| python-dotenv | 1.0.1 | CVE-2026-28684 / PYSEC-2026-2270 — symlink following in `set_key` allows arbitrary file overwrite via cross-device rename fallback |
| pyarrow | 18.0.0 | CVE-2026-25087 / PYSEC-2026-113 — potential use-after-free reading an IPC file with pre-buffering |
| pytest | 8.4.2 | CVE-2025-71176 / PYSEC-2026-1845 — vulnerable tmpdir handling |

## 3. Reachability, per advisory (the part that decides the action)

An advisory that cannot be reached from this codebase is not the same risk as
one that can, and the difference is checkable here rather than arguable:

* **python-dotenv `set_key` (CVE-2026-28684).** The vulnerable function is the
  *write* path. This codebase only ever uses the read paths: `load_dotenv`
  (`config/settings.py:4,8`, `scripts/funding_settlement_hold.py:89`) and
  `dotenv_values` (`tests/test_sandbox_credential_diagnostics_16.py:36`).
  A repository-wide search finds no `set_key` call, no `import dotenv` other
  than the two above. **Not reachable** in this tree.
* **pyarrow IPC use-after-free (CVE-2026-25087).** The vulnerable surface is
  `pyarrow.ipc` file reading. A repository-wide search finds no `ipc` reference:
  pyarrow is touched only through `pandas.to_parquet` / `pandas.read_parquet`
  (`core/history/history_storage.py:120,158`) and `pyarrow.parquet`
  (`research/phase11g/storage/store.py:40-61`). The parquet files read are
  in-tree, project-generated artifacts rather than untrusted input.
  **Not reachable** in this tree.
* **pytest tmpdir handling (CVE-2025-71176).** This is a *test-tool* advisory,
  not a runtime dependency of the product. The suite does create temporary
  directories (`tempfile.TemporaryDirectory`, `mkdtemp`), so the code path is
  used, but the attack requires a local adversary able to pre-create symlinks in
  the operator's own temp directory. Exposure is bounded to local test
  execution. **Reachable in principle, accepted**, with the evaluated upgrade
  path below.

## 4. Decision on the three advisory upgrades

The candidate upgrades were already evaluated once, in an isolated venv, with
the *affected surfaces first* and then the full suite (Phase157,
`reports/DEPENDENCY_UPGRADE_EVALUATION.md`: 43 failed / 3956 passed, zero new
failures, identical failure categories; `pytest.ini` accepted unchanged under
pytest 9, 4,009 tests collected).

Decision for Phase 158: **not adopted.** The reasons are specific, not
faith-based:

1. `requirements.txt` is the reproducibility contract for every piece of
   evidence in this release. Adopting a new environment without re-deriving the
   evidence under it would make the recorded `verification_environment` false
   for whatever ran before the change.
2. Two of the three advisories are unreachable from this codebase (section 3),
   so adoption buys nothing today that the reachability analysis does not.
3. The third (pytest) affects local test execution only, and its upgrade path is
   already validated: pytest 9.0.3 collects the full suite, produces the same
   failure set, and the repository's `pytest.ini` needs no change.

## 5. What a future adopter must do

If the pins are upgraded (for example to python-dotenv 1.2.2, pyarrow 23.0.1,
pytest 9.0.3):

1. Change `requirements.txt` **and** the release record's
   `verification_environment.dependencies` in the same commit — the contract
   test fails otherwise, by design.
2. Re-run the authoritative full suite under the new environment and re-record
   `reports/PHASE158_FULL_SUITE_RUN.txt`-equivalent evidence; the failure set
   must be compared as a *multiset*, not a count.
3. Re-run the parquet round-trip and the affected surfaces
   (`test_history_storage`, `test_history_database`, `test_delta_history`,
   `test_pipeline_regressions`, `test_settings_9q`,
   `test_sandbox_credential_diagnostics_16`) — the evidence for those under the
   upgraded pins is in `reports/DEPENDENCY_UPGRADE_EVALUATION.md`.
4. Re-derive any evidence whose environment claim would otherwise change
   silently.

## 6. Supply-chain observations beyond advisories

* No package is installed from a URL, path, or Git reference; every pin is a
  PyPI release version.
* No dependency is vendored into the tree, so there is no second copy to drift.
* The secret scanner and the privacy scanner both run over the tree and the
  archive (`reports/PHASE158_SECURITY_SCAN.md`,
  `reports/PHASE158_PRIVACY_REVIEW.md`); dependency review is reported
  separately from both, and from source integrity, deliberately — a clean
  dependency review does not imply a clean package.
* `httpx` is worth restating as its own line item because of its history here:
  the pin had drifted for many phases (declared 0.27.2, running 0.28.1) and the
  drift had silently broken order cancellation (`Client.delete()` lost its
  `content` kwarg in 0.28). The pin now matches reality and
  `tests/test_dependency_pin_contract.py` names that exact case.
