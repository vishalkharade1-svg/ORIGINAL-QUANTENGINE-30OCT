# Phase154 evidence error-handling repair (EXECUTED, TESTED)

## Finding (high priority, confirmed by reading `delta_fill_evidence.py:219`)

`scripts/bounded_testnet_reconciled_experiment.py` (Phase145 fix) caught ALL `ValueError` from `capture_authenticated_fills()` and labeled it "no fills in window". But the module raises `ValueError` for: empty input, malformed rows, symbol mismatch, missing ids, duplicates, bad side/role/size/price/commission/timestamp, unordered fills, non-list results — only ONE of which (empty-after-symbol-filter) means "no fills". A corrupt feed would have been misreported as negative evidence. The Phase85 script had the same shape (message-substring check).

## Repair (smallest complete)

- New `EmptySymbolWindowError(ValueError)` in `research/economics/delta_fill_evidence.py:19`, raised ONLY at the empty-after-filter site (counts preserved in message). Subclassing keeps the existing `pytest.raises(ValueError, match="non-empty")` contract green.
- Recon script: catches ONLY the typed error for the empty path; `(ValueError, RuntimeError)` → `rest_fills: FAILED` fail-closed. Phase85 script: `isinstance(exc, EmptySymbolWindowError)` instead of message-substring.
- No artifact meanings changed; no historical evidence rewritten.

## Regression (21 passed)

`tests/test_fill_error_taxonomy_phase154.py` (9 tests) + `tests/test_delta_fill_evidence_phase80.py` (12): empty→typed; malformed/non-list/duplicate/bad-timestamp/unauth/unsuccessful/mismatch all prove NOT typed; recon-script source contract pins FAILED mapping. One test-side correction during development (filter-then-validate order), implementation exonerated.

## Files changed

`research/economics/delta_fill_evidence.py`, `scripts/bounded_testnet_reconciled_experiment.py`, `scripts/run_phase85_delta_testnet_capture.py`, `tests/test_fill_error_taxonomy_phase154.py`.
