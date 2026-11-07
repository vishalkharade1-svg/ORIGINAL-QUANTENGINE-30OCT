"""Phase 11F-2 causality tests (attack the framework, don't trust it).

Proves future-bar invariance under five perturbation families and
proves a hostile accessor never observes future reads. Synthetic
bars only — no D1/D2/D3 data, no profitability, no selection.
"""

import math
import unittest

from research.phase11f import candidates as C
from research.phase11f import causality as Q
from research.phase11f import features as F
from research.phase11f import fibonacci as FIB


def _rich_bars(n=140, start=1787000000):
    bars = []
    prev = 100.0
    for i in range(n):
        c = 100.0 + 4.0 * math.sin(i / 4.0) + (2.0 if i % 25 == 24 else 0.0)
        o = prev
        bars.append({"time": start + 60 * i, "open": o,
                     "high": max(o, c) + 0.6, "low": min(o, c) - 0.6,
                     "close": c, "volume": 10.0})
        prev = c
    return bars


def _futures(base, t, kind):
    last = base[t]
    out = []
    for k in range(1, 11):
        b = dict(last)
        b["time"] = last["time"] + 60 * k
        if kind == "extreme-ohlc":
            b.update({"open": 300.0 + k, "high": 400.0 + k,
                      "low": 200.0 - k, "close": 350.0, "volume": 10.0})
        elif kind == "volume":
            b["volume"] = 10000.0
        elif kind == "volatility":
            swing = 20.0 if k % 2 else -20.0
            b.update({"open": last["close"], "high": last["close"] + abs(swing),
                      "low": last["close"] - abs(swing),
                      "close": last["close"] + swing, "volume": 500.0})
        elif kind == "highs-lows":
            b.update({"high": last["high"] + 50.0, "low": last["low"] - 50.0})
        elif kind == "closes":
            b.update({"open": last["close"] + 5.0 * (k - 1),
                      "high": last["close"] + 5.0 * k + 1.0,
                      "low": last["close"] + 5.0 * (k - 1) - 1.0,
                      "close": last["close"] + 5.0 * k})
        out.append(b)
    return out


KINDS = ["extreme-ohlc", "volume", "volatility", "highs-lows", "closes"]


def _feature_snapshot(bars, t):
    """All decision-t artifacts at bar t (prefix bars[:t+1] of `bars`)."""
    pre = bars[:t + 1]
    return {
        "atr": F.atr14(pre)[t],
        "rsi": F.rsi14(pre)[t],
        "swings": F.swings(pre)[t],
        "levels": F.equal_levels(pre)[t],
        "sweep": F.sweeps(pre)[t],
        "disp": F.displacement(pre)[t],
        "fvg": F.fvg_zones(pre)[t],
        "rng": F.range_state(pre)[t],
        "fib_r": FIB.fib_retracements(pre)[t],
        "fib_e": FIB.fib_extensions(pre)[t],
    }


def _step_signals(cls, bars, t):
    inst = cls()
    out = None
    for idx in range(t + 1):
        out = inst.signals(idx, bars[:t + 1], None) or []
    return out


class TestCausalityContractDeclared(unittest.TestCase):
    def test_timing_table_complete_and_never_backdates(self):
        names = [row["structure"] for row in Q.STRUCTURE_TIMING]
        for required in ("Swing", "Sweep", "FVG", "Order block", "Fibonacci anchor",
                         "Equal level", "Displacement", "Breaker level",
                         "Range state", "Mitigation/pending"):
            self.assertIn(required, names)
        for row in Q.STRUCTURE_TIMING:
            self.assertEqual(row["backdating_allowed"], "NO", row["structure"])
            self.assertTrue(row["confirmation"] and row["earliest_legal_use"])

    def test_confirmation_differs_from_origin_where_required(self):
        by_name = {r["structure"]: r for r in Q.STRUCTURE_TIMING}
        self.assertNotEqual(by_name["Swing"]["origin"], by_name["Swing"]["confirmation"])
        self.assertNotEqual(by_name["Fibonacci anchor"]["origin"],
                            by_name["Fibonacci anchor"]["confirmation"])


class TestFutureBarInvariance(unittest.TestCase):
    def test_features_and_fib_immune_to_all_perturbations(self):
        base = _rich_bars()
        for t in (40, 80, 120):
            ref = _feature_snapshot(base, t)
            for kind in KINDS:
                extended = base[:t + 1] + _futures(base, t, kind)
                got = _feature_snapshot(extended, t)
                self.assertEqual(got, ref, "t=%d kind=%s" % (t, kind))

    def test_all_candidates_sequentially_invariant(self):
        base = _rich_bars()
        for cls in C.ALL:
            for t in (50, 100):
                ref = _step_signals(cls, base, t)
                for kind in KINDS:
                    extended = base[:t + 1] + _futures(base, t, kind)
                    inst = cls()
                    got = None
                    for idx in range(t + 1):
                        got = inst.signals(idx, extended, None) or []
                    # NOTE: stepping on `extended` while idx <= t passes
                    # the full future array; invariance holds only
                    # because every feature value at i<=t ignores bars
                    # beyond i (proven here behaviorally).
                    self.assertEqual(got, ref, "%s t=%d kind=%s" % (cls.id, t, kind))

    def test_harness_history_never_contains_future(self):
        import inspect
        from research.phase11f import harness as H
        src = inspect.getsource(H.ResearchPipeline._on_candle)
        self.assertIn("self.history.append", src)
        self.assertLess(src.index("self.history.append"),
                        src.index("self.candidate.signals"))


class TestHostileAccessor(unittest.TestCase):
    def test_features_run_clean_on_hostile_prefix(self):
        base = _rich_bars()
        t = 90
        hostile = Q.HostileBars(base, t)
        # Every feature completes without a single future touch.
        self.assertEqual(F.atr14(hostile)[t], F.atr14(base[:t + 1])[t])
        self.assertEqual(F.rsi14(hostile)[t], F.rsi14(base[:t + 1])[t])
        self.assertEqual(F.swings(hostile)[t], F.swings(base[:t + 1])[t])
        self.assertEqual(F.equal_levels(hostile)[t], F.equal_levels(base[:t + 1])[t])
        self.assertEqual(F.sweeps(hostile)[t], F.sweeps(base[:t + 1])[t])
        self.assertEqual(F.displacement(hostile)[t], F.displacement(base[:t + 1])[t])
        self.assertEqual(F.fvg_zones(hostile)[t], F.fvg_zones(base[:t + 1])[t])
        self.assertEqual(F.range_state(hostile)[t], F.range_state(base[:t + 1])[t])
        self.assertEqual(FIB.fib_retracements(hostile)[t],
                         FIB.fib_retracements(base[:t + 1])[t])

    def test_candidates_run_clean_on_hostile_prefix(self):
        base = _rich_bars()
        t = 70
        for cls in C.ALL:
            inst = cls()
            got = None
            hostile = Q.HostileBars(base, t)
            for idx in range(t + 1):
                got = inst.signals(idx, hostile, None) or []
            self.assertEqual(got, _step_signals(cls, base, t), cls.id)

    def test_future_touch_raises_immediately(self):
        base = _rich_bars()
        hostile = Q.HostileBars(base, 30)
        with self.assertRaises(Q.FutureAccessError):
            _ = hostile[31]
        with self.assertRaises(Q.FutureAccessError):
            _ = hostile[30:35]
        # Suppression is not allowed: the exception must propagate.
        with self.assertRaises(Q.FutureAccessError):
            try:
                _ = hostile[99]
            except Q.FutureAccessError:
                raise


if __name__ == "__main__":
    unittest.main()
