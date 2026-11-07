"""Phase 30 evidence artifact integrity and isolation tests."""
from __future__ import annotations

import ast
import hashlib
import io
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
ART = ROOT / "research" / "results" / "phase30_oos_evidence_accumulation.json"
CACHE = ROOT / "data" / "history" / "BTCUSDT_1m_oos_topup.json"
BOUNDARY = 1788601440


class TestPhase30Artifact(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ART.exists() or not CACHE.exists():
            raise unittest.SkipTest("phase30 real-data artifact/cache absent")
        cls.art = json.loads(ART.read_text(encoding="utf-8"))
        cls.cache = json.loads(CACHE.read_text(encoding="utf-8"))

    def test_real_evidence_remains_blocked(self):
        self.assertEqual(self.art["evidence_classification"],
                         "GENUINE_VENUE_HISTORICAL_OHLCV_REPLAY")
        self.assertEqual(self.art["nine_m_protocol"]["current_status"],
                         "OOS_BLOCKED")
        self.assertFalse(self.art["production_ready"])
        self.assertEqual(self.art["hypotheses_tested"], 0)
        self.assertEqual(self.art["totals"]["completed_trades"], 3)

    def test_dataset_identity_and_boundary(self):
        rows = sorted(self.cache["raw"], key=lambda r: r["time"])
        blob = json.dumps(rows, sort_keys=True,
                          separators=(",", ":")).encode()
        self.assertEqual(hashlib.sha256(blob).hexdigest(),
                         self.cache["dataset_identity"])
        self.assertTrue(all(r["time"] > BOUNDARY for r in rows))

    def test_six_periods_are_chronological_and_nonoverlapping(self):
        periods = self.art["periods"]
        self.assertEqual(len(periods), 6)
        for a, b in zip(periods, periods[1:]):
            self.assertLess(a["end"], b["start"])
        self.assertEqual(sum(p["fills"] for p in periods), 3)


class TestPhase30Isolation(unittest.TestCase):
    def test_script_has_no_production_imports_or_order_tokens(self):
        path = ROOT / "scripts" / "build_phase30_oos_evidence.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
        forbidden_imports = ("core.live", "core.execution", "core.paper_trading",
                             "core.broker", "core.strategies")
        for token in forbidden_imports:
            self.assertFalse(any(x == token or x.startswith(token + ".")
                                 for x in imports), token)
        text = path.read_text(encoding="utf-8")
        for token in ("place_order", "submit_order", "DeltaOrderExecutor",
                      "LIVE_EXECUTE", "DELTA_API_KEY", "DELTA_API_SECRET"):
            self.assertNotIn(token, text)
