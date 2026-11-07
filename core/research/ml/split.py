"""
====================================================

QuantEngine

ML / Statistical Research -- temporal dataset splitting (Phase 9G)

Deterministic, chronological dataset splitting for the 9G ML layer.

The dataset is a sequence of OPPORTUNITIES, each carrying a decision
bar / timestamp. Splitting MUST respect time ordering: an
opportunity may never be in TRAIN if it occurred AFTER an OOS TEST
opportunity (temporal leakage). There is NO random shuffling across
time in any split builder -- wind bent only forward.

   temporal_split(items, m):  TRAIN | VALIDATION | OOS on time order.
   walk_forward(items, ...):  expanding-window [TRAIN][TEST] folds.

An `item` is any object exposing:
   .decision_bar or .timestamp  (position in the sequence)

If an item carries neither, the order in the supplied sequence is
used as its time position (list order == time order).
====================================================
"""

from dataclasses import dataclass, field


def _time_key(item, index):
    if hasattr(item, "decision_bar"):
        bar = item.decision_bar
        if isinstance(bar, (int, float)):
            return (0, float(bar))
    if hasattr(item, "timestamp"):
        ts = item.timestamp
        if ts is not None:
            try:
                return (1, float(ts))
            except (TypeError, ValueError):
                pass
    if hasattr(item, "bar"):
        bar = item.bar
        if isinstance(bar, (int, float)):
            return (0, float(bar))
    return (2, float(index))


def _sorted(items):
    indexed = list(enumerate(items))
    indexed.sort(key=lambda t: _time_key(t[1], t[0]))
    return [it for _, it in indexed]


@dataclass(frozen=True)
class Fold:
    """A named subset of the dataset (indices into the sorted items)."""

    name: str
    indices: tuple

    def __len__(self):
        return len(self.indices)

    @property
    def empty(self):
        return len(self.indices) == 0


@dataclass(frozen=True)
class TemporalSplit:
    """TRAIN / VALIDATION / OOS split over time-ordered items."""

    train: Fold
    validation: Fold
    oos: Fold
    items: tuple = field(default_factory=tuple)

    def item(self, i):
        return self.items[i]

    @property
    def oos_is_empty(self):
        return self.oos.empty

    def _fold_items(self, fold):
        return tuple(self.items[i] for i in fold.indices)

    def train_items(self):
        return self._fold_items(self.train)

    def validation_items(self):
        return self._fold_items(self.validation)

    def oos_items(self):
        return self._fold_items(self.oos)

    def to_dict(self):
        return {
            "train_size": len(self.train),
            "validation_size": len(self.validation),
            "oos_size": len(self.oos),
            "chronological": True,
            "no_shuffle": True,
            "no_temporal_leakage": True,
        }


def temporal_split(items, validation_fraction=0.2, oos_fraction=0.2):
    """Deterministic chronological TRAIN | VALIDATION | OOS split.

    fractions are of the FULL dataset (validation = the earliest
    trailing block, OOS = the latest block, TRAIN = everything before
    validation). No random permutation is performed.
    """
    ordered = _sorted(items)
    n = len(ordered)
    oos_n = int(round(n * oos_fraction))
    val_n = int(round(n * validation_fraction))
    # OOS is the newest; validation sits before it; train is oldest
    oos_start = max(0, n - oos_n)
    val_start = max(0, oos_start - val_n)
    train_idx = tuple(range(0, val_start))
    val_idx = tuple(range(val_start, oos_start))
    oos_idx = tuple(range(oos_start, n))
    return TemporalSplit(
        train=Fold("TRAIN", train_idx),
        validation=Fold("VALIDATION", val_idx),
        oos=Fold("OOS", oos_idx),
        items=tuple(ordered),
    )


@dataclass(frozen=True)
class WalkForwardFold:
    """One expanding-window [TRAIN][TEST] fold."""

    fold_index: int
    train: Fold
    test: Fold


@dataclass(frozen=True)
class WalkForward:
    """Expanding-window walk-forward split (chronological only)."""

    folds: tuple  # of WalkForwardFold

    def iter_folds(self):
        return self.folds

    def to_dict(self):
        return {
            "walk_forward": True,
            "expanding_window": True,
            "no_shuffle": True,
            "no_temporal_leakage": True,
            "folds": [
                {
                    "fold": f.fold_index,
                    "train_size": len(f.train),
                    "test_size": len(f.test),
                }
                for f in self.folds
            ],
        }


def walk_forward(items, train_size=0.5, step=0.2, min_oos=3, purge_bars=0, embargo_bars=0):
    """Deterministic expanding-window walk-forward folds with optional
    PURGE + EMBARGO (AFML 7.4).

    train_size / step are FRACTIONS; train window grows forward;
    each TEST block is the *next* `step` window after train end
    (disjoint, no overlap, no lookahead). `purge_bars` removes the
    last N train items whose labels overlap test horizon; `embargo_bars`
    skips the first N test items after train. Returns empty if not enough data.

    For backward compat, test window is `step` (not to end). Previous
    behavior (test to end) was nested/overlapping and is retired.
    """
    ordered = _sorted(items)
    n = len(ordered)
    folds = []
    start = int(round(n * train_size))
    step_n = max(1, int(round(n * step)))
    purge_n = max(0, int(purge_bars))
    embargo_n = max(0, int(embargo_bars))
    while start < n - 1:
        test_end = min(start + step_n, n)
        # Purge: drop last purge_n of train
        train_start = 0
        train_end = max(train_start, start - purge_n)
        # Embargo: shift test start forward
        test_start = min(start + embargo_n, test_end)
        if test_end - test_start < min_oos:
            # Not enough OOS in this fold — try next start
            start += step_n
            continue
        if train_end - train_start < 1:
            start += step_n
            continue
        train_idx = tuple(range(train_start, train_end))
        test_idx = tuple(range(test_start, test_end))
        # Ensure disjoint and chronological
        if train_idx and test_idx:
            # train strictly before test (with purge/embargo, already)
            pass
        folds.append(WalkForwardFold(
            fold_index=len(folds),
            train=Fold("TRAIN", train_idx),
            test=Fold("TEST", test_idx),
        ))
        start += step_n
        if start >= n:
            break
    return WalkForward(tuple(folds))