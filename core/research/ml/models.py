"""
====================================================

QuantEngine

ML / Statistical Research -- simple ML baselines (Phase 9G)

9G.2 -- SIMPLE, deterministic, dependency-isolated ML baselines that
DISCOVER relationships; they never decide what gets traded.

Dependency isolation (required contract):
   * the statistical baselines and split builders never need
     sklearn / scipy.
   * the numpy-backed simple models (logistic regression, decision
     tree) are ALWAYS available and deterministic.
   * sklearn is OPTIONAL: it is probed lazily inside functions. When
     sklearn is NOT installed, MlBackend reports
     ML_BACKEND_UNAVAILABLE and the engine STILL installs, compiles,
     tests and runs -- sklearn is never a production dependency.

Targets encoded here (binary classifiers for research, not trades):
   ENTRY_REACHED, WIN, POSITIVE_R, EXPECTED_R (threshold), RECOVERY_SUCCESS.

All models return probabilities (P(target)) via predict_proba; the
layer reports calibrated/relative probabilities and AUC where
available, ALWAYS framed as association, never as a signal to trade.
====================================================
"""

import math

try:
    import numpy as _np
except Exception:  # pragma: no cover - numpy is present
    _np = None

ML_BACKEND_UNAVAILABLE = "ML_BACKEND_UNAVAILABLE"
_ML_IMPORT_FAILURE = None
try:
    from sklearn.linear_model import LogisticRegression as _SkLogReg
    from sklearn.tree import DecisionTreeClassifier as _SkTree
    from sklearn.ensemble import RandomForestClassifier as _SkForest
    from sklearn.metrics import roc_auc_score as _sk_auc
    _HAS_SKLEARN = True
except Exception as _exc:  # sklearn not installed -> gracefully degrade
    _HAS_SKLEARN = False
    _ML_IMPORT_FAILURE = str(_exc)


def ml_backend_available():
    return _HAS_SKLEARN


def ml_backend_status():
    if _HAS_SKLEARN:
        return "sklearn"
    return ML_BACKEND_UNAVAILABLE


# ------------------------------------------------------------------
# Targets
# ------------------------------------------------------------------


def _result(row):
    if isinstance(row, dict):
        return (row.get("result") or "").upper()
    return (getattr(row, "result", "") or "").upper()


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def encode_target(outcomes, target):
    """Deterministic binary label per outcome for a research target.

    target in {ENTRY_REACHED, WIN, POSITIVE_R, EXPECTED_R,
    RECOVERY_SUCCESS}. Returns (labels, available_mask) where
    available_mask marks rows whose label is KNOWN (unsettled / no
    evidence rows are excluded, never fabricated).
    """
    labels = []
    mask = []
    for o in outcomes:
        result = _result(o)
        if target == "ENTRY_REACHED":
            er = (o.get("entry_reached") if isinstance(o, dict)
                  else getattr(o, "entry_reached", None))
            if er is None:
                labels.append(0)
                mask.append(False)
            else:
                labels.append(1 if bool(er) else 0)
                mask.append(True)
        elif target == "WIN":
            if result == "WIN":
                labels.append(1)
                mask.append(True)
            elif result == "LOSS":
                labels.append(0)
                mask.append(True)
            else:
                labels.append(0)
                mask.append(False)
        elif target == "POSITIVE_R":
            r = _num(o.get("r") if isinstance(o, dict) else getattr(o, "r", None))
            if r is None or result not in ("WIN", "LOSS"):
                labels.append(0)
                mask.append(False)
            else:
                labels.append(1 if r > 0 else 0)
                mask.append(True)
        elif target == "EXPECTED_R":
            r = _num(o.get("r") if isinstance(o, dict) else getattr(o, "r", None))
            if r is None:
                labels.append(0)
                mask.append(False)
            else:
                labels.append(1 if r > 0.1 else 0)
                mask.append(True)
        elif target == "RECOVERY_SUCCESS":
            rec = (o.get("recovered") if isinstance(o, dict)
                   else getattr(o, "recovered", False))
            labels.append(1 if bool(rec) else 0)
            mask.append(True)
        else:
            labels.append(0)
            mask.append(False)
    return labels, mask


# ------------------------------------------------------------------
# Pure-numpy logistic regression (deterministic)
# ------------------------------------------------------------------


class NumpyLogisticRegression:
    """Deterministic binary logistic regression via fixed-iteration
    gradient descent (L2-regularised). Pure numpy; no sklearn."""

    def __init__(self, learning_rate=0.1, iterations=200, l2=1e-3):
        self.learning_rate = learning_rate
        self.iterations = iterations
        self.l2 = l2
        self._w = None
        self._b = 0.0

    def _sigmoid(self, z):
        z = _np.clip(z, -30.0, 30.0)
        expz = _np.exp(-z)
        out = 1.0 / (1.0 + expz)
        # handle overflow-safe already via clip
        return out

    def fit(self, X, y):
        X = _np.asarray(X, dtype=float)
        y = _np.asarray(y, dtype=float)
        n, d = X.shape
        # deterministic zero init
        self._w = _np.zeros(d)
        self._b = 0.0
        for _ in range(self.iterations):
            z = X @ self._w + self._b
            p = self._sigmoid(z)
            grad = (X.T @ (p - y)) / n
            grad_w = grad + (self.l2 / n) * self._w
            self._w -= self.learning_rate * grad_w
            self._b -= self.learning_rate * ((p - y).sum() / n)
        return self

    def predict_proba(self, X):
        X = _np.asarray(X, dtype=float)
        z = X @ self._w + self._b
        return self._sigmoid(z)

    @staticmethod
    def kind():
        return "NumpyLogisticRegression"


# ------------------------------------------------------------------
# Pure-numpy decision tree (deterministic, information-gain)
# ------------------------------------------------------------------


class NumpyDecisionTree:
    """Deterministic binary decision-tree classifier via greedy
    information-gain splits. Pure numpy; no sklearn."""

    def __init__(self, max_depth=3, min_samples=3):
        self.max_depth = max_depth
        self.min_samples = min_samples
        self._tree = None

    class _Node:
        __slots__ = ("feature", "value", "left", "right", "leaf_prob")

        def __init__(self):
            self.feature = None
            self.value = None
            self.left = None
            self.right = None
            self.leaf_prob = None

    def _entropy(self, y):
        if len(y) == 0:
            return 0.0
        p = y.mean()
        if p <= 0.0 or p >= 1.0:
            return 0.0
        return -(p * math.log2(p) + (1 - p) * math.log2(1 - p))

    def _best_split(self, X, y):
        best_gain = -1.0
        best = None
        H = self._entropy(y)
        n, d = X.shape
        if n == 0:
            return None
        for f in range(d):
            col = X[:, f]
            uniq = sorted(set(float(v) for v in col))
            for th in uniq[1:]:
                left = y[col < th]
                right = y[col >= th]
                if len(left) == 0 or len(right) == 0:
                    continue
                ig = H - (len(left) / n * self._entropy(left)
                          + len(right) / n * self._entropy(right))
                if ig > best_gain:
                    best_gain = ig
                    best = (f, th)
        if best is None or best_gain <= 1e-12:
            return None
        return best, best_gain

    def _build(self, X, y, depth):
        node = self._Node()
        if len(y) == 0:
            node.leaf_prob = 0.0
            return node
        node.leaf_prob = y.mean()
        if depth >= self.max_depth or len(y) < self.min_samples:
            return node
        split = self._best_split(X, y)
        if split is None:
            return node
        (f, th), _ = split
        node.feature = f
        node.value = th
        lsel = X[:, f] < th
        node.left = self._build(X[lsel], y[lsel], depth + 1)
        node.right = self._build(X[~lsel], y[~lsel], depth + 1)
        return node

    def fit(self, X, y):
        X = _np.asarray(X, dtype=float)
        y = _np.asarray(y, dtype=int).astype(float)
        self._tree = self._build(X, y, 0)
        return self

    def predict_proba(self, X):
        X = _np.asarray(X, dtype=float)
        out = []
        for row in X:
            node = self._tree
            while node.feature is not None and node.left is not None:
                if row[node.feature] < node.value:
                    node = node.left
                else:
                    node = node.right
            out.append(node.leaf_prob)
        return _np.asarray(out, dtype=float)

    @staticmethod
    def kind():
        return "NumpyDecisionTree"


# ------------------------------------------------------------------
# Optional sklearn-backed models (graceful degradation)
# ------------------------------------------------------------------


def _sklearn_model(kind):
    if not _HAS_SKLEARN:
        return None
    if kind == "LOGISTIC":
        return _SkLogReg(max_iter=1000, solver="lbfgs")
    if kind == "TREE":
        return _SkTree(max_depth=3, random_state=0)
    if kind == "FOREST":
        return _SkForest(n_estimators=20, max_depth=3, random_state=0)
    return None


# ------------------------------------------------------------------
# Unified simple-model wrapper
# ------------------------------------------------------------------


class SimpleModel:
    """Deterministic simple-ML classifier over a research target.

    backend: 'numpy' (always) or 'sklearn' (only when installed).
    kind:    'LOGISTIC' | 'TREE' | 'FOREST'.
    """

    def __init__(self, kind="LOGISTIC", backend=None,
                 target="WIN", thresholds=None):
        self.kind = kind
        self.backend = backend or ("sklearn" if _HAS_SKLEARN else "numpy")
        self.target = target
        self._model = None

    def fit(self, X, y):
        if self.backend == "sklearn" and not _HAS_SKLEARN:
            self._model = None
            return self
        if self.backend == "numpy":
            if self.kind == "TREE":
                self._model = NumpyDecisionTree().fit(X, y)
            else:
                self._model = NumpyLogisticRegression().fit(
                    _np.asarray(X, float), _np.asarray(y, float))
            return self
        self._model = _sklearn_model(self.kind)
        if self._model is None:
            return self
        self._model.fit(X, y)
        return self

    @property
    def trained(self):
        return self._model is not None

    def predict_proba(self, X):
        if self._model is None:
            return None
        if isinstance(self._model, (NumpyLogisticRegression,
                                    NumpyDecisionTree)):
            return self._model.predict_proba(X)
        return self._model.predict_proba(X)[:, 1]


def auc(targets, probs):
    """Deterministic Area-Under-ROC via rank-sum (numpy). sklearn-free."""
    targets = [int(t) for t in targets]
    probs = [float(p) for p in probs]
    if len(targets) != len(probs):
        return None
    pos = [probs[i] for i in range(len(probs)) if targets[i] == 1]
    neg = [probs[i] for i in range(len(probs)) if targets[i] == 0]
    if not pos or not neg:
        return None
    # average-rank (ties get mean rank)
    ties = {}
    for i, v in enumerate(sorted(probs)):
        ties.setdefault(v, []).append(i + 1)
    rank_of = {}
    for v, idxs in ties.items():
        rank_of[v] = sum(idxs) / len(idxs)
    sum_pos = sum(rank_of[p] for p in pos)
    n_pos = len(pos)
    n_neg = len(neg)
    return float((sum_pos - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg))