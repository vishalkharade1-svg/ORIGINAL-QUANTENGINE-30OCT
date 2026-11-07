"""
====================================================

QuantEngine

Conditional ML / Opportunity Discovery (Phase 9L) -- entry selection

Conditional ENTRY-MODEL selection -- selecting per context instead of
globally:

   setup A + TREND   -> BREAKOUT_CONTINUATION
   setup B + RANGE   -> LIMIT_RETEST
   setup C + high vol-> ...

The selection is made ONLY where the evidence supports it. A cell is
a (primary generated regime, direction) context. Every FIXED
supported alternative (LIMIT_RETEST / MARKET_CONFIRMATION /
BREAKOUT_CONTINUATION) is evaluated with its own conditional
probability model; the chosen alternative must:

   * have an OOS sample >= the raised min-n gate,
   * produce an OOS expectancy above the cell baseline by at least the
     economic margin,
   * survive the global familywise correction.

If any gate fails the cell reports ENTRY_SELECTION_INCONCLUSIVE with
every alternative row RETAINED (nothing hidden). The layer never
scans unbounded combinations.
====================================================
"""

from core.research.conditional_ml.types import (
    AlternativeEvidence,
    EntrySelection,
    ENTRY_SELECTION_SUPPORTED,
    ENTRY_SELECTION_INCONCLUSIVE,
    UNAVAILABLE,
)
from core.research.conditional_ml.probabilities import OutcomeModel
from core.research.conditional_ml.guards import required_min_n, z_prop_win


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _fitting_rows(orows, alt, indices):
    out = []
    for i in indices:
        r = orows[i]
        if not r.alt_filled.get(alt):
            continue
        label = r.labels.get(alt)
        if label is None:
            continue
        out.append(_ModelRow(r.ctx.tokens(), label, r.rs.get(alt)))
    return out


class _ModelRow:
    __slots__ = ("tokens", "label", "r")

    def __init__(self, tokens, label, r):
        self.tokens = tokens
        self.label = label
        self.r = r


def entry_selection(orows, split, alternatives, cells, gates, n_hypotheses=1):
    """orows: opportunity rows (see engine). split: TemporalSplit.
    cells: sorted list of (regime, direction) tuples. gates: dict."""
    min_oos = int(gates.get("min_entries_n", 5))
    delta_r = float(gates.get("economic_delta_r", 0.5))
    min_oos_n_gate = required_min_n(min_oos, n_hypotheses)

    train_idx = set(split.train.indices)
    oos_idx = set(split.oos.indices)
    val_idx = set(split.validation.indices)

    out = []
    for (regime, direction) in cells:
        cell_idx = [i for i in range(len(orows))
                    if (orows[i].ctx.primary_generated() or UNAVAILABLE) == regime
                    and (orows[i].ctx.direction or "").upper() == direction]
        cell_train = [i for i in cell_idx if i in train_idx]
        cell_oos = [i for i in cell_idx if i in oos_idx]

        baseline_expectancy_oos = _mean([
            orows[i].baseline_r for i in cell_oos
            if orows[i].baseline_filled
        ])

        alt_rows = []
        for alt in alternatives:
            model = OutcomeModel()
            train_rows = _fitting_rows(orows, alt, cell_train)
            model.fit(train_rows)

            oos_rows = _fitting_rows(orows, alt, cell_oos)
            n_oos = len(oos_rows)
            expected_r_oos = None
            p_win_oos = None
            if model.fitted() and oos_rows:
                ps = [model.predict_p(r.tokens) for r in oos_rows]
                p_win_oos = (sum(ps) / len(ps)) if ps else None
                ers = [model.predict_expected_r(r.tokens) for r in oos_rows]
                ers = [x for x in ers if x is not None]
                expected_r_oos = (sum(ers) / len(ers)) if ers else None

            # two-proportion p-value: alt wins vs baseline wins in OOS
            alt_filled_labels = [orows[i].labels.get(alt) for i in cell_oos
                                 if orows[i].labels.get(alt) is not None]
            baseline_wins = sum(1 for i in cell_oos
                                if orows[i].baseline_filled
                                and orows[i].baseline_r is not None
                                and orows[i].baseline_r > 0)
            baseline_known = sum(1 for i in cell_oos
                                 if orows[i].baseline_filled
                                 and orows[i].baseline_r is not None)
            p_ts = None
            if alt_filled_labels and baseline_known:
                p_ts = z_prop_win(
                    len(alt_filled_labels), sum(alt_filled_labels),
                    baseline_known, baseline_wins,
                )

            delta = None
            if expected_r_oos is not None and baseline_expectancy_oos is not None:
                delta = expected_r_oos - baseline_expectancy_oos

            alt_rows.append(AlternativeEvidence(
                alternative=alt,
                n_train=len(train_rows),
                n_oos=n_oos,
                p_win_oos=round(p_win_oos, 4) if p_win_oos is not None else None,
                expected_r_oos=round(expected_r_oos, 4)
                if expected_r_oos is not None else None,
                baseline_expectancy_oos=round(baseline_expectancy_oos, 4)
                if baseline_expectancy_oos is not None else None,
                delta_expectancy_oos=round(delta, 4) if delta is not None else None,
                p_two_sided=p_ts,
            ))

        valid = [a for a in alt_rows
                 if a.n_oos >= min_oos_n_gate and a.expected_r_oos is not None]
        selected = None
        if valid:
            selected = max(valid, key=lambda a: a.expected_r_oos).alternative
        supported = (
            selected is not None
            and alt_rows and
            any(a.alternative == selected and a.delta_expectancy_oos is not None
                and a.delta_expectancy_oos >= delta_r
                for a in alt_rows)
        )
        status = ENTRY_SELECTION_SUPPORTED if supported else ENTRY_SELECTION_INCONCLUSIVE

        out.append(EntrySelection(
            cell_id="%s|%s" % (regime, direction),
            regime=regime,
            direction=direction,
            selected=selected,
            status=status,
            alternatives=tuple(alt_rows),
            min_oos_n_gate=min_oos_n_gate,
            economic_delta_r=delta_r,
            survives_familywise=False,
        ))
    return out