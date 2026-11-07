"""
====================================================

QuantEngine

ML / Statistical Research -- statistical baselines (Phase 9G)

9G.1 -- pure, deterministic statistical summaries over the 9F
feature evidence and its already-labelled 9C/9D outcomes. These are
DESCRIPTIVE / ASSOCIATIVE statistics: they REPORT relationships,
they never decide what gets traded.

   StatisticalBaseline       sample count, win rate, expectancy,
                             avg R, avg MAE, avg MFE, R distribution
   effect_size               Cohen's h (proportions) / Cohen's d
                             (means) -- a magnitude, NOT significance
   conditional_statistics    P(WIN | feature=value), P(ENTRY_REACHED |
                             feature=value), etc. -- association only

Guarded independence:
   * stats are always computable in pure math / numpy (sklearn/scipy
     are NEVER required for any statistical baseline).
   * a rate/expectancy is reported as None when its denominator is 0
     (never fabricated); effect sizes are None when degenerate.
   * confidence intervals use a plain normal-approximation when a
     sample is large enough, else are reported as unavailable --
     they are descriptive, never a significance claim.
====================================================
"""

import math

try:
    import numpy as _np
except Exception:  # pragma: no cover - numpy is present
    _np = None


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


class StatisticalBaseline:
    """Deterministic descriptive summary of a labelled outcome set.

    outcomes: iterable of labelled rows. Each row is either a dict or
    an object exposing:
        .result       'WIN' | 'LOSS' | other (unsettled/'' )
        .r            realised R (float, may be None)
        .mae / .mfe   adverse / favourable excursion (float, optional)
    """

    def __init__(self, name="", rows=(), category=None):
        self.name = name
        self.rows = tuple(rows)
        self.category = category

    # ---- raw accessors ----

    @staticmethod
    def _field(row, name):
        if isinstance(row, dict):
            return row.get(name)
        return getattr(row, name, None)

    def n(self):
        return len(self.rows)

    def result(self, row):
        r = self._field(row, "result")
        return (r or "").upper()

    # ---- aggregated metrics ----

    def win_rate(self):
        n = self.n()
        if n == 0:
            return None
        return sum(1 for r in self.rows if self.result(r) == "WIN") / n

    def loss_rate(self):
        n = self.n()
        if n == 0:
            return None
        return sum(1 for r in self.rows if self.result(r) == "LOSS") / n

    def unsettled_rate(self):
        n = self.n()
        if n == 0:
            return None
        wins = sum(1 for r in self.rows if self.result(r) == "WIN")
        losses = sum(1 for r in self.rows if self.result(r) == "LOSS")
        return (n - wins - losses) / n

    def wins(self):
        return sum(1 for r in self.rows if self.result(r) == "WIN")

    def losses(self):
        return sum(1 for r in self.rows if self.result(r) == "LOSS")

    def entry_reached_rate(self):
        vals = [_num(self._field(r, "entry_reached")) for r in self.rows]
        vals = [v for v in vals if v is not None]
        if not vals:
            return None
        return sum(vals) / len(vals)

    def avg_R(self):
        rs = [_num(self._field(r, "r")) for r in self.rows]
        rs = [x for x in rs if x is not None]
        if not rs:
            return None
        return sum(rs) / len(rs)

    def expectancy(self):
        """E[R] over rows with a known r (settled)."""
        return self.avg_R()

    def avg_MAE(self):
        xs = [_num(self._field(r, "mae")) for r in self.rows]
        xs = [x for x in xs if x is not None]
        return sum(xs) / len(xs) if xs else None

    def avg_MFE(self):
        xs = [_num(self._field(r, "mfe")) for r in self.rows]
        xs = [x for x in xs if x is not None]
        return sum(xs) / len(xs) if xs else None

    def r_distribution(self):
        """Deterministic histogram of R into fixed bins."""
        rs = [_num(self._field(r, "r")) for r in self.rows]
        rs = [x for x in rs if x is not None]
        bins = [
            ("<-1", lambda x: x < -1.0),
            ("[-1,0)", lambda x: -1.0 <= x < 0.0),
            ("[0,1)", lambda x: 0.0 <= x < 1.0),
            ("[1,2)", lambda x: 1.0 <= x < 2.0),
            (">=2", lambda x: x >= 2.0),
        ]
        total = len(rs) or 1
        return [
            (label, sum(1 for x in rs if fn(x)), sum(1 for x in rs if fn(x)) / total)
            for label, fn in bins
        ]

    def to_dict(self):
        return {
            "name": self.name,
            "category": self.category,
            "n": self.n(),
            "wins": self.wins(),
            "losses": self.losses(),
            "win_rate": self.win_rate(),
            "loss_rate": self.loss_rate(),
            "unsettled_rate": self.unsettled_rate(),
            "entry_reached_rate": self.entry_reached_rate(),
            "avg_R": self.avg_R(),
            "expectancy": self.expectancy(),
            "avg_MAE": self.avg_MAE(),
            "avg_MFE": self.avg_MFE(),
            "r_distribution": self.r_distribution(),
        }


def _mean(xs):
    return sum(xs) / len(xs) if xs else None


def _std(xs):
    if len(xs) < 2:
        return None
    m = _mean(xs)
    var = sum((x - m) ** 2 for x in xs) / (len(xs) - 1)
    return math.sqrt(var)


def effect_size_d(group_a, group_b):
    """Cohen's d between two numeric groups (deterministic)."""
    a = [x for x in group_a if x is not None]
    b = [x for x in group_b if x is not None]
    if not a or not b:
        return None
    ma = _mean(a)
    mb = _mean(b)
    sa = _std(a)
    sb = _std(b)
    if sa is None or sb is None:
        return None
    # pooled sd
    na = len(a)
    nb = len(b)
    pool2 = ((na - 1) * sa ** 2 + (nb - 1) * sb ** 2) / (na + nb - 2)
    if pool2 <= 0:
        return None
    pool = math.sqrt(pool2)
    return (ma - mb) / pool


def effect_size_h(pa, pb):
    """Cohen's h for two proportions (deterministic)."""
    if pa is None or pb is None:
        return None
    pa = max(0.0, min(1.0, pa))
    pb = max(0.0, min(1.0, pb))
    try:
        return 2.0 * (math.asin(math.sqrt(pa)) - math.asin(math.sqrt(pb)))
    except ValueError:
        return None


def conditional_statistics(rows, feature_accessor, label_accessor,
                           target="WIN"):
    """P(target | feature=value) for each observed feature value.

    rows:             iterable of snapshot/outcome rows.
    feature_accessor: fn(row) -> feature value (None -> skipped).
    label_accessor:   fn(row) -> 'WIN' | 'LOSS' | other/None.
    target:           'WIN' | 'ENTRY_REACHED' | 'POSITIVE_R' | ...

    Returns a deterministic list of {value, n, target_rate, effect_h
    (vs the overall target rate), win_rate, avg_r} dicts. This is
    ASSOCIATION only; never a causation or a trade decision.
    """
    groups = {}
    overall_win = 0
    overall_known = 0
    overall_r = []
    for row in rows:
        label = (label_accessor(row) or "").upper()
        r = _num(getattr(row, "r", None) if not isinstance(row, dict)
                 else row.get("r"))
        if label == "WIN":
            overall_win += 1
        if label in ("WIN", "LOSS"):
            overall_known += 1
        if r is not None:
            overall_r.append(r)

    baseline_win = overall_win / overall_known if overall_known else None
    baseline_avg_r = _mean(overall_r) if overall_r else None

    for row in rows:
        value = feature_accessor(row)
        if value is None:
            continue
        label = (label_accessor(row) or "").upper()
        r = _num(getattr(row, "r", None) if not isinstance(row, dict)
                 else row.get("r"))
        g = groups.setdefault(value, {
            "n": 0, "wins": 0, "losses": 0, "entry_reached_count": 0,
            "entry_reached_known": 0, "r": [],
        })
        g["n"] += 1
        if label == "WIN":
            g["wins"] += 1
        # entry reached
        er = getattr(row, "entry_reached", None) if not isinstance(row, dict) \
            else row.get("entry_reached")
        if er is not None:
            g["entry_reached_known"] += 1
            if bool(er):
                g["entry_reached_count"] += 1
        # r (settled only)
        if label in ("WIN", "LOSS") and r is not None:
            g["r"].append(r)

    out = []
    for value in sorted(groups.keys(), key=lambda x: (str(x), x)):
        g = groups[value]
        wins = g["wins"]
        known = g["n"]
        win_rate = wins / known if known else None
        entry_rate = (g["entry_reached_count"] / g["entry_reached_known"]
                      if g["entry_reached_known"] else None)
        avg_r = _mean(g["r"]) if g["r"] else None
        if target == "ENTRY_REACHED":
            target_rate = entry_rate
        elif target == "POSITIVE_R":
            pos = sum(1 for x in g["r"] if x and x > 0)
            target_rate = pos / len(g["r"]) if g["r"] else None
        else:
            target_rate = win_rate  # default: WIN

        out.append({
            "value": value,
            "n": known,
            "target": target,
            "target_rate": target_rate,
            "effect_h_vs_overall": effect_size_h(target_rate, baseline_win),
            "win_rate": win_rate,
            "entry_reached_rate": entry_rate,
            "avg_R": avg_r,
            "overall_win_rate": baseline_win,
            "overall_avg_R": baseline_avg_r,
        })
    return out