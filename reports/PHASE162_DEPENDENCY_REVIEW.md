# Dependency review — Phase 162

**Status:** Pinned set carried from Phase 161; verified 0 drift and 0 open advisories.

## 1. Pinned Set & Environment

`requirements.txt` is what a reproducer installs; `reports/PHASE162_RELEASE_GATES.json` (`verification_environment`) records the evidence environment:

| package | pin | change this phase |
|---|---|---|
| httpx | 0.28.1 | carried |
| websockets | 12.0 | carried |
| python-dotenv | 1.2.2 | carried |
| pandas | 2.2.2 | carried |
| numpy | 2.1.1 | carried |
| pyarrow | 23.0.1 | carried |
| pytest | 9.0.3 | carried |

Interpreter: Python 3.12.10 on Windows-10-10.0.19045-SP0.
`tests/test_dependency_pin_contract.py` enforces agreement between `requirements.txt` and the highest-numbered gates record.

## 2. Advisory Check

Method: OSV query API (`https://api.osv.dev/v1/query`), one POST per pinned package at its pinned version (`reports/PHASE162_OSV_SCAN.json`).

| package | pinned | advisories affecting the pinned version |
|---|---|---|
| httpx | 0.28.1 | none |
| websockets | 12.0 | none |
| python-dotenv | 1.2.2 | none |
| pandas | 2.2.2 | none |
| numpy | 2.1.1 | none |
| pyarrow | 23.0.1 | none |
| pytest | 9.0.3 | none |

No advisory remains open against any pinned version.

## 3. Reachability Greps

* `set_key` (python-dotenv write path): zero hits in `config/settings.py` and `scripts/funding_settlement_hold.py` — only `load_dotenv` / `dotenv_values` used.
* `pyarrow.ipc`: zero references in `core/history/history_storage.py` and `research/phase11g/storage/store.py`; pyarrow is used only for parquet persistence.
