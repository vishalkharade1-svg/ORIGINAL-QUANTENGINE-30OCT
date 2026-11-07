"""11G-A determinism + prefix-invariance tests (separate files below share builders)."""

import hashlib
import json
import unittest

from research.phase11g.features import mitigation as M
from research.phase11g.features import mtf as T
from research.phase11g.features import structure as S
from research.phase11g.tests.test_feature_contracts import ALL_SERIES, bars


def _freeze(obj):
    return json.dumps(obj, sort_keys=True, default=str)


class TestDeterminism(unittest.TestCase):
    def test_double_run_identical(self):
        first = _freeze([r for s in ALL_SERIES(bars()) for r in s])
        second = _freeze([r for s in ALL_SERIES(bars()) for r in s])
        self.assertEqual(first, second)
        self.assertEqual(hashlib.sha256(first.encode()).hexdigest(),
                         hashlib.sha256(second.encode()).hexdigest())

    def test_mtf_double_run_identical(self):
        b = bars(200)
        self.assertEqual(T.resample_15m(b), T.resample_15m(list(b)))

    def test_no_wall_clock_or_random(self):
        import pathlib
        for name in ("structure.py", "liquidity.py", "displacement.py",
                     "fvg.py", "orderblock.py", "breaker.py", "mitigation.py",
                     "volume.py", "wyckoff.py", "fibonacci.py", "mtf.py",
                     "confluence.py"):
            src = (pathlib.Path("research/phase11g/features") / name).read_text()
            for token in ("random.", "datetime.now", "time.time()", "uuid",
                          "os.urandom", "requests.", "urlopen"):
                self.assertNotIn(token, src, name)


if __name__ == "__main__":
    unittest.main()
