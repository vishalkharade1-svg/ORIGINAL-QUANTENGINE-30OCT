# Phase 11F Methodology Open Questions (11F-1 architecture record)

No economic hypothesis was changed to ease implementation. The
following interpretation points are recorded explicitly so the
later validation phases cannot silently re-decide them.

## Q1. NEXT_BAR_OPEN vs LIMIT_RETEST execution channel

- Hypotheses H11F-001/003/004/008 declare `NEXT_BAR_OPEN market fill`.
- Hypotheses H11F-002/005/006/007 declare `LIMIT touch fill on retest bars`.
- The research harness (`research/phase11f/harness.py`) assembles every
  intent with `entry_mode="LIMIT_RETEST"` and activates it research-only
  via `mock.patch(ACTIVE_ENTRY_MODES=("LIMIT_RETEST",))`.
- `research/phase11f/candidates.py` documents LIMIT-at-level as the
  uniform channel (NBO approximation note).
- Resolution for 11F-1: the harness channel is the single certified
  execution path; hypothesis `execution_model` text describes intent
  economics, not a second simulator. SweepReversal entry (= signal-bar
  close) fills on a subsequent touch of that level under SL-first /
  expiry machinery. Any fill-rate difference vs literal next-bar-open
  is a documented approximation, not a per-candidate optimization.
  No threshold was tuned on the basis of this difference (no research
  executed in 11F-1).

## Q2. Breaker BOS interpretation (H11F-006)

- Hypothesis text: `swing BOS (3/3 confirmed)`.
- Implementation: most-recent confirmed swing extreme (3/3) acts as the
  level; arming requires an actual close crossing back through it
  (prev close on one side, current close on the other), then a LIMIT
  retest within 5 bars.
- This avoids arming on every bar the condition merely holds (which
  would extend the window indefinitely). Recorded here as the frozen
  interpretation; not to be re-tuned after results.

## Q3. Order-block reference (H11F-005)

- Hypothesis text: `OB = last opposite-range candle before displacement`.
- Implementation: `order_block_before(bars, idx, side)` scans strictly
  before the displacement bar (exclusive). Overlapping-OB ambiguity is
  resolved by most-recent rule (documented in hypotheses.json).
- Frozen as stated.

## Q4. Fibonacci scope

- Fibonacci is feature infrastructure only in 11F-1
  (`research/phase11f/fibonacci.py`). No hypothesis was added or
  altered because Fibonacci became available. Ratios are frozen
  (retrace 0.382/0.5/0.618/0.786; extension 1.272/1.618); any future
  use must reference these levels causally (confirmed anchors only).

## Q5. Funding

- Funding is unmodeled (same limitation as 11E), represented explicitly
  as `funding = 0` in `contracts.py`/`metrics.py` so
  `net = gross - fees - slippage - funding` holds exactly. A future
  funding model would be a new protocol version, not a silent edit.

## Q6. D3 thin holdout

- D3 is 456 bars per symbol (~7.6h). Holdout verdicts are
  sample-limited by construction; INSUFFICIENT is an acceptable
  holdout outcome (per datasets.json). D3 remains SEALED in 11F-1.

## Q7. H11F-008 buffer parameter (contract completion, no economics change)

- H11F-008 `stop_definition` specifies `beyond range extreme + 0.25x
  ATR14 buffer`, but its `frozen_parameters` dict lists only
  range_lookback/rsi_period/rsi_low/rsi_high.
- Interpretation frozen here: `buffer_atr = 0.25` is implied-frozen
  by the stop text (same 0.25x ATR buffer used uniformly across all
  eight hypotheses), not an optimizable dimension. The candidate
  `RangeRSIFade(params buffer_atr=0.25)` matches this reading.
  `hypotheses.json` text is unchanged; the contract test pins the
  value rather than silently allowing arbitrary buffers.
