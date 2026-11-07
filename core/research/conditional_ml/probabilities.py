"""
====================================================

QuantEngine

Conditional ML / Opportunity Discovery (Phase 9L) -- probabilities

A FIXED-FORM, deterministic, evidence-weighted conditional
probability model. It answers the 9L question -- "given THIS regime +
confluence feature context, what is the probability each candidate
alternative produces an economically useful outcome?" -- over
out-of-sample observations.

Model shape (deliberately NOT an optimizer):
   * additive log-odds over decision-time context tokens, each token
     contributing a Laplace-smoothed logit shift vs the training
     baseline (a naive-Bayes-style evidence aggregation);
   * additive expected-R contributions per token, clamped so no single
     token can dominate;
   * trained ONCE on the chronological TRAIN block, evaluated on
     VALIDATION / OOS only -- no hyper-parameter search, no
     per-fold re-fitting, no threshold hunting;
   * pure math -- deterministic and dependency-isolated.

The layer reports PROBABILITIES for research framing only, always
together with its OOS calibration (see calibration.py). It never
returns a trade directive.
====================================================
"""

import math

PROB_MIN = 0.02
PROB_MAX = 0.98
TOKEN_LOGIT_SHIFT_MAX = 2.5
TOKEN_R_SHIFT_MAX = 1.5


def _logit(p):
    p = max(0.01, min(0.99, p))
    return math.log(p / (1.0 - p))


def _inv_logit(z):
    z = max(-30.0, min(30.0, z))
    return 1.0 / (1.0 + math.exp(-z))


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _token_label(row):
    ok = getattr(row, "known", True)
    if ok is False:
        return None
    return getattr(row, "label", None)


class OutcomeModel:
    """Deterministic additive-logit conditional probability model."""

    def __init__(self):
        self.overall_p = None
        self.overall_logit = None
        self.overall_mean_r = None
        self._logit_shifts = {}
        self._r_shifts = {}
        self.n_train = 0

    # -------------------------------------------------

    def fit(self, rows):
        """rows: iterable of objects exposing .tokens (dict) and
        .label (0/1 or None) and .r (float or None)."""
        rows = [r for r in rows]
        labels = [(i, r) for i, r in enumerate(rows)
                  if _token_label(r) is not None]
        known = len(labels)
        wins = sum(1 for _, r in labels if int(_token_label(r)) == 1)
        self.n_train = known
        if known == 0:
            self.overall_p = None
            self.overall_logit = 0.0
            return self
        self.overall_p = wins / known
        self.overall_logit = _logit(self.overall_p)

        settled_r = [_num(_field_r(r)) for r in rows]
        settled_r = [x for x in settled_r if x is not None]
        self.overall_mean_r = sum(settled_r) / len(settled_r) \
            if settled_r else None

        # token statistics (each token = (feature, value))
        token_win = {}
        token_n = {}
        token_r = {}
        for r in rows:
            label = int(_token_label(r))
            for key, value in sorted(_tokens(r).items()):
                tok = (key, str(value))
                token_n[tok] = token_n.get(tok, 0) + 1
                if label == 1:
                    token_win[tok] = token_win.get(tok, 0) + 1
                rv = _field_r(r)
                if rv is not None and _token_label(r) is not None:
                    token_r.setdefault(tok, []).append(rv)

        self._logit_shifts = {}
        for tok, n in token_n.items():
            if n < 2:
                continue
            p_laplace = (token_win.get(tok, 0) + 1.0) / (n + 2.0)
            shift = _logit(p_laplace) - self.overall_logit
            shift = max(-TOKEN_LOGIT_SHIFT_MAX, min(TOKEN_LOGIT_SHIFT_MAX, shift))
            self._logit_shifts[tok] = shift

        self._r_shifts = {}
        if self.overall_mean_r is not None:
            for tok, rs in token_r.items():
                if len(rs) < 2:
                    continue
                mean_tok = sum(rs) / len(rs)
                shift = mean_tok - self.overall_mean_r
                shift = max(-TOKEN_R_SHIFT_MAX, min(TOKEN_R_SHIFT_MAX, shift))
                self._r_shifts[tok] = shift
        return self

    # -------------------------------------------------

    def predict_p(self, tokens):
        if self.overall_logit is None:
            return None
        z = self.overall_logit
        for key, value in sorted(tokens.items()):
            tok = (key, str(value))
            z += self._logit_shifts.get(tok, 0.0)
        p = _inv_logit(z)
        return max(PROB_MIN, min(PROB_MAX, p))

    def predict_expected_r(self, tokens):
        if self.overall_mean_r is None:
            return None
        out = self.overall_mean_r
        for key, value in sorted(tokens.items()):
            tok = (key, str(value))
            out += self._r_shifts.get(tok, 0.0)
        return out

    def fitted(self):
        return self.n_train > 0


def _tokens(row):
    t = getattr(row, "tokens", None)
    if t is None:
        return {}
    return dict(t)


def _field_r(row):
    return _num(getattr(row, "r", None))