"""11G-A confluence representation tests (descriptive, scoreless)."""

import unittest

from research.phase11g.features import confluence as CF
from research.phase11g.tests.test_feature_contracts import bars
from research.phase11g.features import structure as S


class TestConfluence(unittest.TestCase):
    def test_compose_descriptive(self):
        b = bars(120)
        states = {"structure": S.trend_state(b)[-1],
                  "liquidity": {"status": "NO_EVENT"}}
        out = CF.compose(states)
        self.assertEqual(set(out), set(CF.CONFLUENCE_FIELDS))
        self.assertIn(out["structure"]["value"], ("UPTREND", "DOWNTREND", "RANGE"))
        self.assertIsNone(out["liquidity"])
        self.assertNotIn("score", json_blob(out))

    def test_score_rejected(self):
        with self.assertRaises(ValueError):
            CF.compose({"score": 9})
        with self.assertRaises(ValueError):
            CF.compose({"weights": {}})
        with self.assertRaises(ValueError):
            CF.compose({"unknown_thing": {}})

    def test_provenance_map(self):
        b = bars(120)
        states = {"structure": S.trend_state(b)[-1]}
        pm = CF.provenance_map(states)
        self.assertEqual(pm, {"structure": "REAL"})


def json_blob(out):
    import json
    return json.dumps(out, default=str)


if __name__ == "__main__":
    unittest.main()
