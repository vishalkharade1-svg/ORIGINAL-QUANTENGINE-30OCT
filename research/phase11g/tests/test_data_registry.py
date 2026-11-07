"""11G-E registry + adapters + storage tests."""

import unittest

from research.phase11g.adapters import exchange as AD
from research.phase11g.registry import registry as RG
from research.phase11g.storage import store as ST


class TestRegistry(unittest.TestCase):
    def test_bootstrap_catalog(self):
        reg = RG.bootstrap_11g_registry()
        s = reg.summary()
        self.assertIn("D1_BTC", s["datasets"])
        self.assertIn("oos_fresh", s["datasets"])
        self.assertNotIn("D3_BTC", s["datasets"])
        self.assertEqual(reg._sets["oos_fresh"]["freshness"], "FRESH")

    def test_d3_refused(self):
        reg = RG.bootstrap_11g_registry()
        with self.assertRaises(ValueError):
            reg.register("D3_BTC", {}, "SEALED")
        with self.assertRaises(RuntimeError):
            reg.d3_block("read")
        self.assertEqual(reg.summary()["d3"], {"read": 0, "hash": 0, "load": 0})

    def test_unknown_never_fresh(self):
        reg = RG.Registry()
        with self.assertRaises(ValueError):
            reg.register("mystery", {}, "UNKNOWN")
        with self.assertRaises(KeyError):
            reg.record_use("ghost", "11G-E")

    def test_freshness_lifecycle(self):
        reg = RG.bootstrap_11g_registry()
        self.assertTrue(reg.is_fresh_for("oos_fresh", "11G-D"))
        self.assertFalse(reg.is_fresh_for("D1_BTC", "11G-D"))
        reg.record_use("oos_fresh", "11G-D", hypothesis=None)
        # Consumed in 11G-D: still qualified for that phase's decision,
        # but no longer fresh for any LATER phase.
        self.assertTrue(reg.is_fresh_for("oos_fresh", "11G-D"))
        self.assertFalse(reg.is_fresh_for("oos_fresh", "11G-E"))
        self.assertEqual(len(reg.used_by("oos_fresh")), 1)

    def test_unknown_phase_rejected(self):
        reg = RG.bootstrap_11g_registry()
        with self.assertRaises(ValueError):
            reg.is_fresh_for("oos_fresh", "PHASE-99")


class TestAdapters(unittest.TestCase):
    def test_urls_centralized(self):
        self.assertEqual(AD.DELTA_PUBLIC_BASE, "https://api.delta.exchange")
        self.assertEqual(AD.DELTA_CANDLES_PATH, "/v2/history/candles")

    def test_fake_client_shape(self):
        class Fake:
            def __init__(self):
                self.calls = []

            def get(self, url, params=None):
                self.calls.append((url, params))
                return {"ok": True}

        ad = AD.DeltaPublicCandlesAdapter(client=Fake())
        out = ad.candles("BTCUSDT", "1m", 1, 2)
        self.assertEqual(out, {"ok": True})
        url, params = ad._client.calls[0]
        self.assertEqual(url, "https://api.delta.exchange/v2/history/candles")
        self.assertEqual(params["symbol"], "BTCUSDT")

    def test_no_client_raises(self):
        ad = AD.DeltaPublicCandlesAdapter()
        with self.assertRaises(RuntimeError):
            ad.candles("X", "1m", 1, 2)

    def test_unimplemented_endpoints_raise(self):
        ad = AD.DeltaPublicCandlesAdapter(client=object())
        for meth in ("trades", "quotes", "book"):
            with self.assertRaises(NotImplementedError):
                getattr(ad, meth)("X", 1, 2)

    def test_registry(self):
        reg = AD.AdapterRegistry()
        reg.register(AD.DeltaPublicCandlesAdapter())
        self.assertEqual(reg.names(), ["delta-public-candles"])


class TestStorage(unittest.TestCase):
    def test_raw_immutable(self):
        import tempfile
        from pathlib import Path
        d = Path(tempfile.mkdtemp())
        meta = ST.write_raw(d, "a.bin", b"raw-bytes")
        self.assertEqual(len(meta["sha256"]), 64)
        with self.assertRaises(FileExistsError):
            ST.write_raw(d, "a.bin", b"other")
        meta2 = ST.write_raw(d, "a.bin", b"other", overwrite=True)
        self.assertNotEqual(meta["sha256"], meta2["sha256"])

    def test_normalized_round_trip(self):
        import tempfile
        from pathlib import Path
        d = Path(tempfile.mkdtemp())
        rows = [{"a": 1, "b": "x"}, {"a": 2, "b": "y"}]
        meta = ST.write_normalized(d, "t", rows)
        self.assertEqual(meta["rows"], 2)
        back = ST.read_normalized(d, "t")
        self.assertEqual(len(back), 2)
        self.assertEqual(back[0]["b"], "x")


if __name__ == "__main__":
    unittest.main()
