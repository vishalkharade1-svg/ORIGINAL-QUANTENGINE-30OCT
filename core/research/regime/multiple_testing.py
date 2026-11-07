"""
====================================================

QuantEngine

Regime / Opportunity Discovery (Phase 9K) -- multiple-testing guard

9J/9K can generate many conditional hypotheses; a naive discovery
would celebrate whichever combination happened to look best. This
module applies a CONSERVATIVE, deterministic correction so a finding
only survives when its sample is strong enough given HOW MANY
conditional hypotheses were actually tested.

Heuristic (documented, conservative):
   * hypotheses      = the number of distinct (config x dimension)
                       pairs tested in one run;
   * corrected alpha = Sidak-style familywise control across the
                       tested hypotheses;
   * required_min_n  = min_cell_n + log2(1 + hypotheses) -- the per-
                       cell sample requirement rises with the number
                       of hypotheses tried;
   * a finding survives only when its status is material AND its cell
       n meets the raised requirement (else it is flagged "possible
       lucky combination / insufficient after correction" and reported,
       not hidden).

This is an anti-overfitting guard for RESEARCH claims, not a
significance engine and not a trade decision.
====================================================
"""

import math


def sidak_alpha(alpha, n_hypotheses):
    if n_hypotheses <= 0:
        return alpha
    return 1.0 - (1.0 - alpha) ** (1.0 / n_hypotheses)


def required_min_n(min_cell_n, n_hypotheses):
    if n_hypotheses <= 0:
        return min_cell_n
    return min_cell_n + int(math.ceil(math.log2(1.0 + n_hypotheses)))


def multiple_testing_summary(cells, findings, min_cell_n,
                             delta_threshold, alpha=0.05):
    """Per-finding survival flags after the conservative correction.
    Deterministic; every finding is retained with a note."""
    hypotheses = set()
    for c in cells:
        hypotheses.add((c.config_id, c.dimension))
    n_tests = len(hypotheses)
    corrected = sidak_alpha(alpha, n_tests)
    required_n = required_min_n(min_cell_n, n_tests)
    per_finding = {}
    for f in findings:
        if f.cell_n is None:
            survives = False
        else:
            material = f.status in ("CONDITIONAL", "CONDITIONAL_WEAK")
            strong = f.status == "CONDITIONAL" and \
                f.delta is not None and f.delta >= delta_threshold
            survives = material and f.cell_n >= required_n and (
                strong or (f.status == "CONDITIONAL_WEAK" and
                           f.delta is not None and f.delta > 0)
            )
        note = (
            "%d conditional hypotheses tested -> familywise-alpha "
            "%.4f and per-cell sample requirement raised to %d; %s" % (
                n_tests, corrected, required_n,
                "survives the conservative correction"
                if survives else "flagged possible lucky combination / "
                "insufficient sample after correction -- retained, not "
                "hidden",
            )
        )
        per_finding[f.finding_id] = {
            "survives": survives,
            "required_min_n": required_n,
            "note": note,
        }
    n_survive = sum(1 for d in per_finding.values() if d["survives"])
    return {
        "n_hypotheses_tested": n_tests,
        "alpha": alpha,
        "corrected_alpha": round(corrected, 6),
        "required_min_n": required_n,
        "n_survive": n_survive,
        "per_finding": per_finding,
    }