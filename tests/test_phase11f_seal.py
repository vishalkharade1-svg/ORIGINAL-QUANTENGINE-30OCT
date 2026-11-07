"""Phase 11F-2 seal tests (D3 isolation, log immutability, safety).

D3 candle arrays are never opened here — not even for hashes. Only
tier metadata, path strings, and the seal exception are exercised.
Research log must show zero executed variants. Exchange-write
methods are monkeypatched to raise, proving the harness never
reaches them. Synthetic bars only.
"""

import glob
import json
import unittest
from pathlib import Path

from research.phase11f import causality as Q
from research.phase11f import datasets as D

RESEARCH = Path("research/phase11f")


def _bars(n=30, start=1787000000, base=100.0):
    return [{"time": start + 60 * i, "open": base, "high": base + 0.5,
             "low": base - 0.5, "close": base + 0.1, "volume": 10.0}
            for i in range(n)]


class TestD3Isolation(unittest.TestCase):
    def test_discovery_exposes_no_holdout(self):
        for path in D.discovery_files():
            self.assertNotIn("D3", path)
            D.assert_not_holdout(path)

    def test_loader_seal_intact(self):
        with self.assertRaises(D.SealedHoldoutError):
            D.load_holdout_candles("research/phase11f/data/universe_D3_BTC.json")
        with self.assertRaises(D.SealedHoldoutError):
            D.load_holdout_candles()

    def test_generic_and_wildcard_paths_blocked(self):
        for path in ("research/phase11f/data/universe_D3_ETH.json",
                     "research/phase11f/data/universe_D3_BTC.json",
                     "./research/phase11f/data/universe_D3_BTC.json"):
            self.assertTrue(D.is_sealed_holdout(path))
            with self.assertRaises(D.SealedHoldoutError):
                D.assert_not_holdout(path)
        # A wildcard sweep over the data directory must classify D3
        # files as sealed without opening them.
        for found in glob.glob("research/phase11f/data/*.json"):
            if "D3" in found:
                self.assertTrue(D.is_sealed_holdout(found))

    def test_harness_and_candidates_never_reference_d3(self):
        for name in ("harness.py", "candidates.py", "features.py",
                     "fibonacci.py", "metrics.py", "causality.py"):
            src = (RESEARCH / name).read_text()
            self.assertNotIn("universe_D3_", src, name)
            self.assertNotIn("oos_fresh", src, name)

    def test_lineage_validator_clean(self):
        self.assertEqual(D.validate_lineage(), [])

    def test_no_d3_file_opened_by_this_suite(self):
        # Meta-guard: path STRINGS may appear (seal assertions), but
        # no line may READ a D3 file's contents.
        for line in Path("tests/test_phase11f_seal.py").read_text().splitlines():
            if "D3" in line:
                self.assertNotIn("open(", line)
                self.assertNotIn("read_text", line)
                self.assertNotIn("read_bytes", line)
                self.assertNotIn("load(", line)


class TestResearchLogImmutability(unittest.TestCase):
    def test_all_eight_preregistered(self):
        # 11F-4 authorized update: statuses are now recorded verdicts
        # (PASS/FAIL/INSUFFICIENT_EVIDENCE); registration history
        # (ids, timestamps, hashes) is immutable and verified here.
        log = json.loads((RESEARCH / "research_log.json").read_text())
        self.assertEqual([e["id"] for e in log["entries"]],
                         ["H11F-%03d" % i for i in range(1, 9)])
        for entry in log["entries"]:
            self.assertIn(entry["status"],
                          ("REGISTERED", "PASS", "FAIL", "INSUFFICIENT_EVIDENCE"))
            self.assertEqual(entry["registration_timestamp"], "2026-09-07T00:00:00Z")
            self.assertIn("hypothesis_hash", entry)
            self.assertIn("parameter_spec_hash", entry)

    def test_transition_guard_trips_on_mutant(self):
        log = json.loads((RESEARCH / "research_log.json").read_text())
        import copy
        # The preregistered-state guard still rejects unregistered
        # transitions (e.g. PROMISING) on any ledger content.
        pre = {"entries": [{"id": "H11F-001", "status": "REGISTERED",
                            "variants_tested": 0, "result": None}]}
        Q.assert_preregistered_state(pre)
        mutant = copy.deepcopy(pre)
        mutant["entries"][0]["variants_tested"] = 1
        mutant["entries"][0]["status"] = "PROMISING"
        mutant["entries"][0]["result"] = {"net": 123.0}
        with self.assertRaises(AssertionError):
            Q.assert_preregistered_state(mutant)
        # Lawful 11F-4 ledger matches recorded artifacts (see
        # tests/test_phase11f_results.py for the full check).
        hypo = json.loads((RESEARCH / "results" / "hypothesis_results.json").read_text())
        for entry in log["entries"]:
            self.assertEqual(entry["status"], hypo[entry["id"]]["verdict"])


class TestD3AccessAudit(unittest.TestCase):
    def test_zero_read_hash_load(self):
        # No code path reads, hashes, or loads D3 candle arrays.
        self.assertEqual(D.D3_ACCESS["read"], 0)
        self.assertEqual(D.D3_ACCESS["hash"], 0)
        self.assertEqual(D.D3_ACCESS["load"], 0)

    def test_no_d3_read_path_exists(self):
        from pathlib import Path as _P
        for name in ("harness.py", "candidates.py", "features.py",
                     "fibonacci.py", "metrics.py", "datasets.py",
                     "causality.py", "validation.py", "run_research.py"):
            for line in (_P("research/phase11f") / name).read_text().splitlines():
                if "D3" in line:
                    self.assertNotIn("open(", line, name)
                    self.assertNotIn("read_text", line, name)
                    self.assertNotIn("read_bytes", line, name)
                    self.assertNotIn("json.load", line, name)
                    self.assertNotIn("sha256", line.lower(), name)


class TestExecutionSafetyMonkeypatched(unittest.TestCase):
    def test_exchange_writes_raise_if_reached(self):
        from unittest import mock
        from research.phase11f import harness as H

        class _OneShot:
            id = "H11F-SEAL"

            def signals(self, idx, bars, ctx):
                if idx == 8:
                    entry = float(bars[idx]["close"])
                    return [{"direction": "BULLISH", "entry": entry,
                             "stop": entry - 1.0, "take_profit": entry + 2.0,
                             "setup_id": "SEAL-8", "confidence": 80.0}]
                return []

        calls = []
        with mock.patch("core.execution.order_executor.DeltaOrderExecutor.execute",
                        side_effect=AssertionError("live write reached")) as m_exec, \
             mock.patch("core.live.broker_engine.BrokerEngine.__init__",
                        side_effect=AssertionError("broker reached")) as m_broker:
            res = H.run_candidate(_bars(), _OneShot(), "BTCUSDT", cost_key="A")
        m_exec.assert_not_called()
        m_broker.assert_not_called()
        self.assertIn("orders", res)
        self.assertNotIn("live", json.dumps(res).lower())

    def test_safety_gate_untouched(self):
        from config.settings import settings
        self.assertFalse(settings.ALLOW_LIVE)
        self.assertFalse(settings.LIVE_EXECUTE)
        src = Path("core/execution/live_safety_gate.py").read_text()
        self.assertIn("ALLOW_LIVE", src)


if __name__ == "__main__":
    unittest.main()
