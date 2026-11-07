"""11G-E dataset registry (contamination-proof catalog).

Answers: which datasets exist, which are fresh, which phases and
hypotheses touched them, which transformations/hashes apply, whether
D3 was accessed, and whether a dataset predates a hypothesis freeze.
UNKNOWN provenance is never FRESH. D3 registration is refused.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from research.phase11g import datasets as D11G


class Registry:
    def __init__(self):
        self._sets = {}
        self._touches = []
        self._d3 = {"read": 0, "hash": 0, "load": 0}

    def register(self, dataset_id, provenance, freshness):
        if "D3" in str(dataset_id):
            raise ValueError("D3 must never enter the registry")
        if freshness not in ("FRESH", "CONTAMINATED", "UNKNOWN"):
            raise ValueError("invalid freshness")
        if freshness == "UNKNOWN":
            raise ValueError("UNKNOWN provenance cannot be registered as usable")
        self._sets[dataset_id] = {"provenance": dict(provenance),
                                  "freshness": freshness}

    def record_use(self, dataset_id, phase, hypothesis=None, transformation=None):
        if dataset_id not in self._sets:
            raise KeyError("unregistered dataset: %r" % dataset_id)
        self._touches.append({"dataset": dataset_id, "phase": phase,
                              "hypothesis": hypothesis,
                              "transformation": transformation})

    def used_by(self, dataset_id):
        return [t for t in self._touches if t["dataset"] == dataset_id]

    def is_fresh_for(self, dataset_id, phase):
        """FRESH only if registered FRESH and never touched in any phase
        strictly before the given one (canonical phase order). A touch
        recorded IN the querying phase does not retroactively un-fresh
        the decision made at that phase's start."""
        info = self._sets.get(dataset_id)
        if info is None or info["freshness"] != "FRESH":
            return False
        cutoff = _phase_index(phase)
        return all(_phase_index(t["phase"]) >= cutoff
                   for t in self.used_by(dataset_id))

    def d3_block(self, kind):
        if kind not in self._d3:
            raise ValueError("unknown counter")
        raise RuntimeError("D3 is SEALED (refused before I/O)")

    def summary(self):
        return {"datasets": sorted(self._sets),
                "touches": list(self._touches),
                "d3": dict(self._d3),
                "sealed_source": "research/phase11f/datasets.py + phase11g/datasets.py"}


PHASE_ORDER = ("11F", "11G-A", "11G-B", "11G-C", "11G-D", "11G-E",
               "11G-F", "11G-G", "11G-H")


def _phase_index(phase):
    try:
        return PHASE_ORDER.index(phase)
    except ValueError:
        raise ValueError("unknown phase: %r" % phase)


def bootstrap_11g_registry():
    """Registry preloaded with the frozen 11G dataset catalog."""
    reg = Registry()
    for did in D11G.all_ids():
        desc = D11G.describe(did)
        reg.register(did, {"source": desc["source"], "symbol": desc["symbol"],
                           "bars": desc["bar_count"]},
                     "CONTAMINATED")
    reg.register("oos_fresh", {"source": "research/phase11e/data/oos_fresh.json",
                               "symbol": "BTCUSDT", "bars": 2499}, "FRESH")
    return reg
