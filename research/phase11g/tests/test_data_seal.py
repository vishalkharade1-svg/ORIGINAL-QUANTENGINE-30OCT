"""11G-E seal + determinism + synthetic-label tests."""

import unittest
from pathlib import Path

PHASE11G = Path("research/phase11g")
NEW_MODULES = ["events/canonical.py", "normalization/normalize.py",
               "validation/quality.py", "provenance/model.py",
               "orderflow/truth.py", "orderflow/book.py",
               "registry/registry.py", "adapters/exchange.py",
               "storage/store.py", "data/synthetic.py", "fresh.py"]


class TestD3Seal11GE(unittest.TestCase):
    def test_counters_zero(self):
        from research.phase11g import datasets as D11G
        from research.phase11g import fresh as FR
        from research.phase11g.registry import registry as RG
        self.assertEqual(D11G.D3_ACCESS, {"read": 0, "hash": 0, "load": 0,
                                          "blocked": D11G.D3_ACCESS["blocked"]})
        self.assertEqual(FR.D3_ACCESS_11GD, {"read": 0, "hash": 0, "load": 0})
        reg = RG.bootstrap_11g_registry()
        self.assertEqual(reg.summary()["d3"], {"read": 0, "hash": 0, "load": 0})

    def test_no_d3_io_in_new_modules(self):
        for rel in NEW_MODULES:
            for line in (PHASE11G / rel).read_text().splitlines():
                if "D3" in line:
                    self.assertNotIn("open(", line, rel)
                    self.assertNotIn("read_bytes", line, rel)
                    self.assertNotIn("read_text", line, rel)
                    self.assertNotIn("sha256", line.lower(), rel)
                    self.assertNotIn("load(", line, rel)


class TestDeterminism11GE(unittest.TestCase):
    def test_normalize_twice_identical(self):
        import json
        from research.phase11g.data import synthetic as SYN
        from research.phase11g.normalization import normalize as NZ
        rows = SYN.synthetic_trades(n=50)
        a = [e.to_dict() for e in NZ.normalize_trades(rows, "X", "s")]
        b = [e.to_dict() for e in NZ.normalize_trades(rows, "X", "s")]
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))

    def test_book_twice_identical(self):
        from research.phase11g.data import synthetic as SYN
        from research.phase11g.events import canonical as EV
        from research.phase11g.orderflow import book as BK

        def run():
            book = BK.BookState()
            for u in SYN.synthetic_book_updates():
                if u["kind"] == "snapshot":
                    book.apply(EV.BookSnapshotEvent(
                        symbol="X", event_timestamp=u["time"], sequence=u["sequence"],
                        bids=u["bids"], asks=u["asks"], source="syn"))
                else:
                    book.apply(EV.BookDeltaEvent(
                        symbol="X", event_timestamp=u["time"], sequence=u["sequence"],
                        side=u["side"], price=u["price"], quantity=u["quantity"],
                        source="syn"))
            return book.snapshot()

        self.assertEqual(run(), run())


class TestSyntheticLabel(unittest.TestCase):
    def test_all_fixtures_labeled(self):
        from research.phase11g.data import synthetic as SYN
        for row in SYN.synthetic_trades(n=10) + SYN.synthetic_quotes(n=10):
            self.assertTrue(row["synthetic"])
        for u in SYN.synthetic_book_updates():
            self.assertTrue(u["synthetic"])
        self.assertEqual(SYN.synthetic_trades(n=10), SYN.synthetic_trades(n=10))


if __name__ == "__main__":
    unittest.main()
