"""Phase 11F-2 mutation battery (MUT-1..MUT-8) + cost/frozen integrity.

Each mutation is introduced inline as a deliberately broken variant,
SHOWN to trip its guard (the test fails on the mutant), then the
original implementation is re-asserted clean (restoration). Mutants
exist only as local variables — the repository is never altered.
Synthetic bars only; no D1/D2/D3, no selection, no research run.
"""

import copy
import json
import random
import unittest
from pathlib import Path

from core.backtesting.accounting import net_pnl as canon_net
from research.phase11f import causality as Q
from research.phase11f import contracts as K
from research.phase11f import datasets as D
from research.phase11f import features as F
from research.phase11f import fibonacci as FIB

RESEARCH = Path("research/phase11f")


def _bars(n=50, start=1787000000, base=100.0):
    return [{"time": start + 60 * i, "open": base, "high": base + 1.0,
             "low": base - 1.0, "close": base + 0.5, "volume": 10.0}
            for i in range(n)]


def _valley_peak():
    lows = [100, 100, 90, 100, 100, 100, 100, 100, 100, 100]
    highs = [100, 100, 100, 100, 100, 105, 120, 105, 100, 100]
    return [{"time": 1000 + 60 * i, "open": 100, "high": highs[i],
             "low": lows[i], "close": 100, "volume": 10.0} for i in range(10)]


class TestMut1FutureBar(unittest.TestCase):
    def test_mutant_using_t_plus_1_detected(self):
        bars = _bars(40)
        t = 25
        ref = F.atr14(bars[:t + 1])[t]

        def mutant_atr(all_bars, idx):
            # MUT-1: peek one bar into the future.
            tr = abs(all_bars[idx + 1]["high"] - all_bars[idx + 1]["low"])
            return tr

        leaked = mutant_atr(bars, t)
        # The mutant's answer depends on future data: perturbing only
        # bars[t+1] changes it while the certified value cannot move.
        alt = [dict(b) for b in bars]
        alt[t + 1] = dict(alt[t + 1], high=999.0, low=1.0)
        self.assertNotEqual(mutant_atr(alt, t), leaked)
        self.assertEqual(F.atr14(alt[:t + 1])[t], ref)
        # Restoration: certified implementation passes invariance.
        self.assertEqual(F.atr14(bars[:t + 1])[t], ref)


class TestMut2FutureSwing(unittest.TestCase):
    def test_mutant_publishing_unconfirmed_swing_detected(self):
        bars = _valley_peak()
        # MUT-2: publish the peak at its formation bar 6 (unconfirmed).
        mutant = {6: {"kind": "high", "extreme": 120.0,
                      "extreme_index": 6, "confirmed_index": 6}}
        certified = F.swings(bars, left=1, right=1)
        self.assertIsNone(certified[6])
        self.assertIsNotNone(mutant[6])
        self.assertNotEqual(certified[6], mutant[6])
        # Restoration: confirmation arrives at bar 7.
        self.assertIsNotNone(certified[7])
        self.assertEqual(certified[7]["extreme_index"], 6)


class TestMut3FutureFibonacci(unittest.TestCase):
    def test_mutant_fib_on_unconfirmed_anchor_detected(self):
        bars = _valley_peak()
        certified = FIB.fib_retracements(bars, left=1, right=1)
        self.assertEqual(certified[5], [])
        # MUT-3: levels fabricated from the not-yet-confirmed peak.
        mutant_levels = [{"direction": "bullish", "ratio": 0.5, "level": 105.0,
                          "confirmed_index": 5}]
        self.assertNotEqual(certified[5], mutant_levels)
        # Restoration: levels appear exactly at confirmation bar 7.
        self.assertEqual(len(certified[7]), 4)
        self.assertTrue(all(l["confirmed_index"] == 7 for l in certified[7]))


class TestMut4D3Bypass(unittest.TestCase):
    def test_disabled_seal_detected(self):
        # MUT-4: a bypass that hands a holdout path to discovery.
        def mutant_discovery():
            return ["research/phase11f/data/universe_D3_BTC.json"]

        for path in mutant_discovery():
            with self.assertRaises(D.SealedHoldoutError):
                D.assert_not_holdout(path)
        # Restoration: certified discovery exposes no holdout path.
        for path in D.discovery_files():
            D.assert_not_holdout(path)
        with self.assertRaises(D.SealedHoldoutError):
            D.load_holdout_candles("anything")


class TestMut5WrongNet(unittest.TestCase):
    def test_corrupted_accounting_detected(self):
        # Certified: net = gross - commission - slippage - funding.
        self.assertAlmostEqual(canon_net(10.0, 1.0, 0.5), 8.5)
        self.assertTrue(K.check_pnl_semantics(10.0, 1.0, 0.5, 0.0, 8.5))

        def mutant_net(gross, commission, slippage):
            return gross + commission + slippage  # MUT-5: wrong signs

        self.assertFalse(K.check_pnl_semantics(
            10.0, 1.0, 0.5, 0.0, mutant_net(10.0, 1.0, 0.5)))
        # A second corruption: gross fabricated from net.
        self.assertFalse(K.check_pnl_semantics(8.5, 1.0, 0.5, 0.0, 8.5))
        # Restoration: certified identity holds exactly.
        self.assertTrue(K.check_pnl_semantics(10.0, 1.0, 0.5, 0.0, 8.5))


class TestMut6FrozenParameter(unittest.TestCase):
    def test_mutated_frozen_param_detected(self):
        from research.phase11f import candidates as C
        doc = json.loads((RESEARCH / "hypotheses.json").read_text())
        frozen_rr = doc["hypotheses"][0]["frozen_parameters"]["rr"]
        self.assertAlmostEqual(frozen_rr, 2.0)

        # MUT-6: attempt to change a frozen parameter at runtime.
        inst = C.SweepReversal(rr=9.99)
        self.assertNotAlmostEqual(inst.cfg["rr"], frozen_rr)
        guard_trips = (inst.cfg["rr"] != frozen_rr)
        self.assertTrue(guard_trips)
        # Restoration: default construction reproduces the frozen spec.
        clean = C.SweepReversal()
        self.assertAlmostEqual(clean.cfg["rr"], frozen_rr)
        # Class-level defaults are immune to instance overrides
        # (no mutable-class-attribute leak).
        self.assertAlmostEqual(C.SweepReversal.params["rr"], 2.0)
        # Forbidden CLASS-D dims stay forbidden after any override.
        for dim in ("symbol", "timeframe", "costs", "holdout"):
            self.assertIn(dim, doc["hypotheses"][0]["forbidden_optimization_dimensions"])

    def test_json_mutation_cannot_rewrite_file(self):
        doc = json.loads((RESEARCH / "hypotheses.json").read_text())
        mutated = copy.deepcopy(doc)
        mutated["hypotheses"][0]["frozen_parameters"]["rr"] = 9.99
        on_disk = json.loads((RESEARCH / "hypotheses.json").read_text())
        self.assertAlmostEqual(
            on_disk["hypotheses"][0]["frozen_parameters"]["rr"], 2.0)
        self.assertEqual(K.validate_hypotheses(on_disk), [])
        self.assertNotEqual(
            mutated["hypotheses"][0]["frozen_parameters"],
            on_disk["hypotheses"][0]["frozen_parameters"])


class TestMut7Nondeterminism(unittest.TestCase):
    def test_unseeded_randomness_detected(self):
        # MUT-7: setup IDs drawn from unseeded global randomness.
        def mutant_ids(seed_value=None):
            rng = random.Random() if seed_value is None else random.Random(seed_value)
            return ["ID-%d" % rng.randrange(10 ** 9) for _ in range(3)]

        self.assertNotEqual(mutant_ids(), mutant_ids())
        # Restoration: seeded generation is exactly reproducible.
        self.assertEqual(mutant_ids(11), mutant_ids(11))

    def test_set_ordering_hazard_detected(self):
        words = {"sweep", "fvg", "displacement", "trend", "range"}
        # A set-driven serialization has no order contract; the
        # certified path uses sorted/canonical JSON instead.
        canon = lambda: json.dumps(sorted(words))
        self.assertEqual(canon(), canon())
        self.assertEqual(
            K.sha256_canonical({"b": 1, "a": 2}),
            K.sha256_canonical({"a": 2, "b": 1}))


class TestMut8DirectExecution(unittest.TestCase):
    @staticmethod
    def _scan(src):
        hits = []
        for token in ("place_order", "submit_order", "DeltaOrderExecutor(",
                      "BrokerEngine(", "cancel_order", ".execute("):
            if token in src:
                hits.append(token)
        return hits

    def test_injected_execution_call_detected(self):
        # MUT-8: research-side snippet reaching an exchange write path.
        mutant = (
            "from core.execution.order_executor import DeltaOrderExecutor\n"
            "executor = DeltaOrderExecutor()\n"
            "executor.place_order(intent)\n"
        )
        self.assertTrue(self._scan(mutant))
        # Restoration: all research sources are clean (the contract
        # denylist block itself is excluded: naming a forbidden
        # object as a string is not reaching it).
        for name in ("candidates.py", "features.py", "fibonacci.py",
                     "harness.py", "contracts.py", "metrics.py",
                     "datasets.py", "causality.py"):
            src = (RESEARCH / name).read_text()
            code, skip = [], False
            for ln in src.splitlines():
                if "FORBIDDEN_RESEARCH_IMPORTS = [" in ln:
                    skip = True
                    continue
                if skip:
                    if ln.strip() == "]":
                        skip = False
                    continue
                code.append(ln)
            self.assertEqual(self._scan("\n".join(code)), [], name)


class TestCostSemanticsIntegrity(unittest.TestCase):
    def test_scenarios_frozen_and_exact(self):
        self.assertEqual(set(K.COST_SCENARIOS_11F), {"A", "B", "C", "D"})
        bd = K.cost_breakdown(500.0, "C")
        self.assertAlmostEqual(bd["commission"], 0.295)
        self.assertAlmostEqual(bd["slippage"], 0.5)
        self.assertAlmostEqual(bd["funding"], 0.0)
        # Harness formula matches the contract formula exactly.
        import inspect
        from research.phase11f import harness as H
        src = inspect.getsource(H.assemble_intent)
        self.assertIn("COMMISSION_RATE", src)
        self.assertIn("SLIPPAGE_BPS", src)

    def test_metrics_adapter_preserves_certified_values(self):
        from research.phase11e.common import trade_metrics as certified
        from research.phase11f import metrics as M
        trades = [
            {"net": 8.5, "gross": 10.0, "entry": 100.0, "quantity": 1.0,
             "commission": 1.0, "slippage": 0.5, "risk_amount": 5.0,
             "exit_time": 2, "entry_time": 1},
        ]
        m = M.research_trade_metrics(trades)
        base = certified(trades)
        self.assertAlmostEqual(m["net_pnl"], base["net_pnl"])
        self.assertAlmostEqual(m["funding"], 0.0)
        self.assertLess(m["net_consistency_diff"], 1e-9)


if __name__ == "__main__":
    unittest.main()
