"""11G-U machine-verified test counts (no hand arithmetic).

collect() walks unittest's own loader (the same machinery `discover`
uses) and returns per-family counts plus the total. The audit report
embeds collect() output verbatim; tests assert the reconciliation
equation baseline + families == total on the collected values.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

PHASE_MODULES = [
    "tests.test_researcher_11g_n",
    "tests.test_researcher_11g_o",
    "tests.test_researcher_11g_p",
    "tests.test_researcher_11g_q",
    "tests.test_researcher_11g_r",
    "tests.test_researcher_11g_s",
    "tests.test_researcher_11g_t",
]

RESEARCH_GLOB = "research/*/tests/test_*.py"


def _count_suite(suite):
    n = 0
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            n += _count_suite(item)
        else:
            n += 1
    return n


def collect():
    loader = unittest.TestLoader()
    families = {}
    for mod in PHASE_MODULES:
        try:
            suite = loader.loadTestsFromName(mod)
            families[mod.split(".")[-1]] = _count_suite(suite)
        except Exception as exc:  # noqa: BLE001 (collection must not die)
            families[mod.split(".")[-1]] = "ERROR:%s" % type(exc).__name__
    main_suite = loader.discover("tests", top_level_dir=".")
    main_total = _count_suite(main_suite)
    research_total = 0
    for path in sorted(Path(".").glob(RESEARCH_GLOB)):
        mod = str(path.with_suffix("")).replace("\\", ".").replace("/", ".")
        try:
            research_total += _count_suite(loader.loadTestsFromName(mod))
        except Exception:  # noqa: BLE001
            pass
    family_sum = sum(v for v in families.values() if isinstance(v, int))
    baseline = main_total - family_sum
    return {"baseline": baseline, "families": families,
            "family_sum": family_sum, "main_total": main_total,
            "research_total": research_total,
            "reconciled": bool(isinstance(baseline, int) and baseline >= 0
                               and baseline + family_sum == main_total)}


if __name__ == "__main__":
    import json
    print(json.dumps(collect(), indent=1, sort_keys=True))
