# ARCHIVE — Phase 11F-4 UNCERTIFIED HISTORICAL EXECUTION

Do NOT use for decisions. Do NOT overwrite.

These files are the byte-identical Phase 11F-4 evidence as committed
in 23125181, preserved here because post-freeze review confirmed a
walk-forward methodology discrepancy:

* `build_folds()` generated ROLLING train windows
  (`train_start = k*step_bars`);
* the frozen 11F-3 protocol specifies EXPANDING-ORIGIN
  (`train_start = 0`, `train_end = train_min_bars + k*step_bars`).

Consequences (verified by trace, see phase11f_5 report §F):
test slices — and therefore every strategy trade — are IDENTICAL
under either geometry (cold-start engines on the same test windows);
only train-derived fitted quantities (regime terciles, random-baseline
k) differ. The 11F-4 verdicts (7× INSUFFICIENT_EVIDENCE, 1× FAIL) are
retained as historical record, superseded by the 11F-5 corrected
re-execution. No file in this directory may be modified.
