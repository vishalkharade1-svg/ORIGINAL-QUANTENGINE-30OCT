# Dependency advisory evaluation (2026-10-16)

## Why this was done

Phase155 recorded three `pip-audit` advisories and deferred the fixes "to a
scheduled green-run window". That window cannot arrive: the suite carries 43
pre-existing failures (23 digest-pin + 18 no-git-ancestry + 2 live-`.env`
guard), so "wait for a green run" meant "never". This evaluation answers the
question the deferral was hiding: **do the upgrades actually break anything?**

## Method

An isolated venv in a temp directory — the project environment and its pins were
not touched at any point.

1. `python -m venv` + `pip install -r requirements.txt` (the declared pins).
2. Upgrade ONLY the three advisory packages:
   `python-dotenv` 1.0.1 → 1.2.2, `pyarrow` 18.0.0 → 23.0.1,
   `pytest` 8.4.2 → 9.0.3.
3. Align `httpx` to **0.28.1** to match the authoritative environment.

Step 3 matters. The authoritative environment has httpx 0.28.1 installed against
a pinned 0.27.2, and the comparison baseline was produced there. A fresh venv
would have installed 0.27.2 and changed httpx behaviour underneath the
comparison, making any difference unattributable. With httpx aligned, the venv
differs from the baseline environment in exactly the three packages under test.

Target versions were confirmed to exist on PyPI rather than trusted from the
advisory text.

## Result

Affected surfaces first (fast signal before the long run):

| Surface | Baseline failures | Under upgraded pins |
|---|---|---|
| `test_history_storage`, `test_history_database`, `test_delta_history` | 0 | passed |
| `test_pipeline_regressions` | 0 | passed |
| `test_settings_9q`, `test_sandbox_credential_diagnostics_16` | 0 | passed |
| **total** | **0** | **40 passed** |

A parquet round-trip (`to_parquet`/`read_parquet`) under pyarrow 23.0.1 +
pandas 2.2.2 also passed — the plausible failure mode was pyarrow moving five
major versions against a pinned pandas, and it did not materialise.

pytest 9.0.3 collected **4,009 tests** with no configuration complaints: the
repository's `pytest.ini` (`testpaths = tests`, `norecursedirs`,
`python_files/classes/functions`) was accepted **unchanged** under pytest 9, so
none of the options it uses is deprecated or removed in that major version. This
is a stronger statement than "no config file exists", and it is the accurate one
— an earlier draft of this report claimed the repository had no pytest config
file, which was wrong (the claim came from a file-existence check that silently
returned nothing).

Full suite under the upgraded pins:

```
43 failed, 3956 passed, 10 skipped, 330 subtests passed in 2210.75s (0:36:50)
EXIT:1
```

**Zero new failures.** The failure set is identical to the pre-existing set, and
its categories are identical too:

| Category | Baseline | Upgraded |
|---|---|---|
| hash-or-digest pin | 23 | 23 |
| no-git ancestry | 18 | 18 |
| live `.env` guard (by design) | 2 | 2 |
| **total** | **43** | **43** |

The three failures that disappeared against the older baseline are exactly the
drift trio (worktree ahead of the manifest) that the Phase156 rebuild resolved —
not upgrade effects.

Two incidental observations:

- pytest 9 reports `330 subtests passed`; pytest 8 did not surface that line.
  Cosmetic reporting difference, not a behavioural one.
- The run was ~9% faster (2210.75s vs 2429.30s).

## Recommendation

The three upgrades are safe to adopt in this environment: no failure is
attributable to them. They are **not** adopted here — `requirements.txt` pins
are the reproducibility contract, and a pin change deserves its own deliberate
step with a post-change full run. This evaluation is the evidence that such a
step would not regress the suite.

Residual caveat, stated plainly: this is one run in one isolated venv. It does
not make the suite green (the 43 pre-existing failures remain the Gate A
blocker, unchanged in kind), and it did not exercise the authoritative
environment's extra dev tooling (`pip-audit`, `bandit`).

## Evidence

- `reports/DEPENDENCY_UPGRADE_EVAL_SUITE.txt` — raw full-suite output
- `reports/DEPENDENCY_UPGRADE_EVAL_FAILURES.json` — the 43 failure node ids
- `reports/DEPENDENCY_UPGRADE_EVAL_FREEZE.txt` — exact venv package set
