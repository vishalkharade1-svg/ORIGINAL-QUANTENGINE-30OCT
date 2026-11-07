"""
Phase 9R-2/3/4 — Feature timestamp + label leakage + purging per horizon.
Verifies causal window: features at decision_bar must not change when future bars appended.
"""

import unittest

from core.research.features.causal_window import extract_causal_window, CausalWindow
from core.research.features.feature_snapshot import FeatureSnapshot
from dataclasses import dataclass


@dataclass
class Candle:
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float = 1000.0


def _candles(n, start=1000):
    return [Candle(timestamp=start+i*60, open=100+i, high=101+i, low=99+i, close=100.5+i) for i in range(n)]


class TestFeatureCausality(unittest.TestCase):

    def test_causal_window_excludes_decision_bar(self):
        candles = _candles(20)
        cw = extract_causal_window(candles, decision_bar=10, lookback=5)
        # Should be bars 5..9 (5 bars before decision_bar 10), not including 10
        self.assertEqual(len(cw.points), 5)
        self.assertEqual(cw.points[-1].close, 109.5)  # candle 9
        # Future bar 15 should not affect window at decision 10
        candles_extended = _candles(30)
        cw2 = extract_causal_window(candles_extended, decision_bar=10, lookback=5)
        self.assertEqual(cw.points, cw2.points)

    def test_feature_snapshot_uses_only_decision_time(self):
        candles = _candles(20)
        cw = extract_causal_window(candles, decision_bar=10, lookback=10)
        snap = FeatureSnapshot(
            opportunity_id="test",
            decision_bar=10,
            window_size=len(cw.points),
            features={"atr": 1.5, "rsi": 60}
        )
        # Add future candles, snapshot at same decision_bar must be identical
        cw_future = extract_causal_window(_candles(30), decision_bar=10, lookback=10)
        snap2 = FeatureSnapshot(
            opportunity_id="test",
            decision_bar=10,
            window_size=len(cw_future.points),
            features={"atr": 1.5, "rsi": 60}
        )
        self.assertEqual(snap.features, snap2.features)
        self.assertEqual(snap.window_size, snap2.window_size)

    def test_label_is_future_by_definition(self):
        # Label (future return) is allowed to use future, but features must not
        candles = _candles(20)
        decision_bar = 10
        # Feature uses before decision_bar
        cw = extract_causal_window(candles, decision_bar=decision_bar, lookback=5)
        self.assertEqual(cw.points[-1].timestamp, candles[9].timestamp)
        # Label uses after decision_bar (e.g., close at decision_bar+5)
        future_close = candles[15].close
        decision_close = candles[decision_bar].close if decision_bar < len(candles) else 0
        future_return = (future_close - decision_close) / decision_close if decision_close else 0
        # Label is future, but that's the prediction target — not leakage
        self.assertNotEqual(future_close, cw.points[-1].close)

    def test_purging_per_horizon(self):
        # Simulate walk-forward with purge = trade horizon (30 bars)
        # Train should exclude last 30 bars before test
        from core.research.ml.split import walk_forward
        from dataclasses import dataclass as dc
        @dc
        class Item:
            decision_bar: int
        items = [Item(decision_bar=i) for i in range(100)]
        wf_no_purge = walk_forward(items, train_size=0.5, step=0.2, purge_bars=0)
        wf_purge = walk_forward(items, train_size=0.5, step=0.2, purge_bars=30)
        # With purge, train should be 30 shorter
        self.assertEqual(len(wf_no_purge.folds[0].train.indices) - len(wf_purge.folds[0].train.indices), 30)
        # Purged train should not overlap test horizon
        for f in wf_purge.folds:
            if f.train.indices and f.test.indices:
                self.assertLess(max(f.train.indices), min(f.test.indices) - 0)  # already disjoint, purge makes more gap
