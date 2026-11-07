# Windowed reconciliation for bounded private-fill captures (2026-10-16)

## The blocker this closes

The standing "repeat-match robustness" blocker was recorded as *reconciliation
blocked on exact-set window semantics*. It is a real design gap, not a flake:

`reconcile_with_rest()` compares the **entire** REST fill set for the symbol
against the socket fills, and refuses on any difference. That is correct only
when a capture spans the account's whole fill history. A bounded capture cannot
satisfy it — fills that happened before the socket was opened have no frame to
match — so every bounded capture was flagged `missing_from_ws` and refused:

- Phase125: strict BLOCKED, 6 pre-window REST-only fills, 0 phantoms,
  0 mismatches.
- Phase152: legs both filled, WS frames present, reconciliation BLOCKED, same
  class.

Both refusals were honest, and both left the run uncertifiable.

## What was added

`reconcile_with_rest_windowed(capture, rest_artifact, *, window_ms=None)` in
`research/economics/delta_private_fill_capture.py`, alongside the strict
function, which is unchanged.

It claims **strictly less** than the strict certificate:

- every REST fill is classified `pre-window`, `in-window` or `post-window`;
- the in-window REST set must match the socket set **exactly** — same
  `missing_from_rest` / `missing_from_ws` / field-mismatch refusals as strict;
- out-of-window fills are reported **by id**, never dropped;
- the returned status is `MATCHED_WINDOWED`, never `MATCHED`, and the record
  carries a `claim` string stating it is window-scoped only — so it cannot be
  mistaken for an account-level certificate;
- the record is fingerprinted (`reconciliation_sha256`) over the window, the
  classified ids and the REST evidence hash, so a window cannot be widened
  after the fact without the fingerprint moving.

`window_ms` defaults to the socket fill span, and may be passed explicitly.

## The trap: two timestamp units

Socket fills carry venue **microseconds** (`t`); REST fills carry
**milliseconds**. A window comparison that guessed units would silently compare
the wrong instants. The window is therefore always expressed in milliseconds,
and a socket fill whose unit is not declared as microseconds is **refused**
rather than interpreted — legacy frames without `t` cannot use the windowed path
at all.

## It is not a gate relaxation

Five negative cases are pinned as refusals:

| Case | Outcome |
|---|---|
| in-window REST fill with no socket frame | refuses (`missing_from_ws`) |
| socket fill absent from REST | refuses (`missing_from_rest`) |
| extra in-window REST fill | refuses (`missing_from_ws`) |
| field mismatch inside the window | refuses (`mismatches`) |
| phantom socket fill | refuses (`missing_from_rest`) |

Plus: window start after end, an explicit window that excludes a socket fill,
non-REAL REST provenance, and symbol mismatch all refuse.

## Verification

- New: `tests/test_private_fill_windowed_reconciliation.py` — 13 tests, all
  green. One of them pins the blocker itself: the strict reconciler on the same
  inputs still raises with `missing_from_ws = ["F1", "F4"]`.
- Consumers of the patched module: `test_delta_fill_evidence_phase80`,
  `test_delta_private_fill_capture_phase81`,
  `test_fill_error_taxonomy_phase154`, `test_phase85_capture_orchestrator`,
  plus the new file — **56 passed**, no regressions.

## Honest limits

The windowed record certifies a **window**, not the account. Out-of-window fills
are classified and reported but not reconciled against anything — for a bounded
capture there is nothing to reconcile them against. It does not retire the
strict path, which remains the right comparison when the capture does span the
fill history. Repeat-match robustness is unblocked in the sense that a bounded
run can now be certified for its window with every fill accounted for; it is
not a claim that any particular repeat match has been observed.
