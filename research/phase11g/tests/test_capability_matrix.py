"""11G-A capability matrix tests (honest data classification)."""

import json
import unittest
from pathlib import Path

MATRIX = json.loads((Path("research/phase11g/data_capability_matrix.json")).read_text())

REQUIRED_KEYS = {"field", "available", "historical", "source",
                 "measurement_type", "timestamp_precision", "causal",
                 "research_ready", "notes"}


class TestCapabilityMatrix(unittest.TestCase):
    def test_all_fields_present_with_schema(self):
        fields = [f["field"] for f in MATRIX["fields"]]
        for required in ("OHLCV", "trades", "trade side", "bid", "ask",
                         "order book", "liquidations", "funding",
                         "open interest", "volume-at-price", "footprint data",
                         "multiple historical timeframes"):
            self.assertIn(required, fields)
        for f in MATRIX["fields"]:
            self.assertTrue(REQUIRED_KEYS <= set(f))

    def test_ohlcv_real_only(self):
        ohlcv = next(f for f in MATRIX["fields"] if f["field"] == "OHLCV")
        self.assertTrue(ohlcv["available"] and ohlcv["historical"])
        self.assertEqual(ohlcv["measurement_type"], "REAL")
        self.assertTrue(ohlcv["research_ready"])

    def test_orderflow_unavailable(self):
        for name in ("trades", "trade side", "bid", "ask", "order book",
                     "footprint data", "volume-at-price"):
            f = next(x for x in MATRIX["fields"] if x["field"] == name)
            self.assertFalse(f["available"], name)
            self.assertFalse(f["research_ready"], name)
            self.assertEqual(f["measurement_type"], "UNAVAILABLE", name)

    def test_no_real_orderflow_anywhere(self):
        for f in MATRIX["fields"]:
            if "delta" in f["field"].lower() or "cvd" in f["field"].lower() \
                    or "imbalance" in f["field"].lower() or "absorption" in f["field"].lower():
                self.assertNotEqual(f["measurement_type"], "REAL", f["field"])

    def test_explicit_rule_recorded(self):
        self.assertIn("UNAVAILABLE", MATRIX["orderflow_rule"])
        self.assertIn("PROXY", MATRIX["orderflow_rule"])


if __name__ == "__main__":
    unittest.main()
