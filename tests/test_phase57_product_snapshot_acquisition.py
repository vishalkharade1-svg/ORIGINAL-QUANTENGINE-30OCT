import hashlib
import json
import pathlib
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "acquire_phase17_product_snapshot.py"


class TestPhase57ProductSnapshotAcquisition(unittest.TestCase):
    def test_explicit_label_and_no_wall_clock(self):
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("--observed-label", text)
        self.assertNotIn("datetime.now", text)
        self.assertNotIn("time.time", text)
        self.assertNotIn("uuid", text.lower())

    def test_reuses_existing_delta_adapter_and_no_credentials(self):
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("core.exchanges.delta.delta_products", text)
        for token in ("API_KEY", "API_SECRET", "api_secret", "private_key"):
            self.assertNotIn(token, text)

    def test_mocked_acquisition_is_deterministic_and_atomic(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("phase57", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        catalog = {"result": [{"symbol": "BTCUSDT", "tick_size": "0.5"}]}
        out = ROOT / "data" / "history" / "_phase57_test_snapshot.json"
        try:
            with patch.object(mod.DeltaProducts, "download", return_value=catalog):
                a = mod.acquire("TEST_LABEL", output=out)
                first = out.read_bytes()
                b = mod.acquire("TEST_LABEL", output=out)
                second = out.read_bytes()
            self.assertEqual(a, b)
            self.assertEqual(first, second)
            self.assertEqual(a["observed_label"], "TEST_LABEL")
            self.assertFalse(a["is_production_ready"])
            self.assertEqual(
                a["catalog_sha256"],
                hashlib.sha256(json.dumps(catalog["result"], sort_keys=True,
                                           separators=(",", ":"), default=str).encode()).hexdigest(),
            )
        finally:
            out.unlink(missing_ok=True)

    def test_missing_symbol_fails_closed(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("phase57b", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        with patch.object(mod.DeltaProducts, "download", return_value={"result": []}):
            with self.assertRaisesRegex(RuntimeError, "BTCUSDT_NOT_LISTED"):
                mod.acquire("TEST_LABEL", output=ROOT / "data" / "history" / "_phase57_missing.json")


if __name__ == "__main__":
    unittest.main()
