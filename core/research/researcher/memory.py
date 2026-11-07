"""
====================================================

QuantEngine

Autonomous AI Researcher -- research memory (Phase 9H)

A first-class journal of investigations: QUESTION -> hypothesis ids
-> executed experiment ids -> results -> rejected/validated outcome
-> OOS status -> next suggestion. It prevents the autonomous
researcher from re-discovering failed (or already-studied) ideas and
from repeating the same parameter sweep.

Determinism / reliability:
   * ids are sha1 fingerprints of the intrinsic content
   * in-memory by default (deterministic, no I/O)
   * optional JSON file persistence via `path=` (best effort; a
     missing/corrupt file degrades to a fresh journal and never
     crashes the researcher)
   * JSON writes are atomic (temp file + replace) and read-only
     loads never mutate the store
====================================================
"""

import hashlib
import json
import os


def _digest(payload):
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def params_fingerprint(params):
    """Deterministic fingerprint of a parameter overrides dict."""
    items = sorted(
        (str(k), sorted(str(v) for v in vals))
        for k, vals in (params or {}).items()
    )
    return json.dumps(items, sort_keys=True)


_CANONICAL_DIMS = (
    "rr",
    "entry_offset",
    "entry_offset_atr",
    "expiry",
    "entry_model",
)


class ResearchMemory:
    """Append-only documentation + dedup store for investigations."""

    def __init__(self, store=None, path=None):
        self._store = dict(store or {})
        self.path = path
        if path:
            self._load(path)

    # -------------------------------------------------

    def investigation_id_for(self, symbol, question, hypothesis_ids):
        return _digest(
            "investigation|%s|%s|%s" % (
                str(symbol or ""),
                str(question or ""),
                "|".join(sorted(hypothesis_ids)),
            )
        )

    def question_fingerprint(self, question):
        return _digest("question|%s" % (question or ""))

    def hypothesis_fingerprint(self, hypothesis):
        return _digest(
            "hypothesis|%s|%s" % (
                hypothesis.question,
                params_fingerprint(hypothesis.overrides),
            )
        )

    def contains_question(self, question):
        return self.question_fingerprint(question) in self._store

    def recall(self, question):
        """Return prior investigations for a question, deterministically."""
        fp = self.question_fingerprint(question)
        return tuple(self._store.get(fp, []))

    def probed_dims(self, question):
        """Union of parameter dimensions already probed for a question."""
        dims = set()
        for prior in self.recall(question):
            for d in (prior.get("probed_dims") or []):
                dims.add(d)
        return frozenset(dims)

    def heard_of_hypothesis(self, question, hypothesis):
        """Deterministic dedup against any earlier identical
        hypothesis (question + parameter fingerprint)."""
        fp = self.question_fingerprint(question)
        hypo_fp = params_fingerprint(hypothesis.overrides)
        for prior in self._store.get(fp, []):
            for h in (prior.get("hypotheses") or []):
                if h.get("fingerprint") == hypo_fp:
                    return True
        return False

    # -------------------------------------------------

    def record(self, investigation_id, question, hypotheses,
               experiment_ids, recommendation_statuses, oos_statuses,
               report_status):
        """Persist one investigation under its question fingerprint."""
        fp = self.question_fingerprint(question)
        entries = list(self._store.get(fp, []))
        entry = {
            "investigation_id": investigation_id,
            "question": question,
            "hypotheses": [
                {
                    "hypothesis_id": h.hypothesis_id,
                    "kind": h.kind,
                    "fingerprint": params_fingerprint(h.overrides),
                }
                for h in hypotheses
            ],
            "probed_dims": sorted({
                k for h in hypotheses for k in h.overrides
            }),
            "experiment_ids": sorted(experiment_ids),
            "recommendation_statuses": sorted(recommendation_statuses),
            "oos_statuses": sorted(oos_statuses),
            "report_status": report_status,
        }
        if investigation_id not in {e.get("investigation_id") for e in entries}:
            entries.append(entry)
        self._store[fp] = entries
        self._save()
        return entry

    # -------------------------------------------------

    def next_suggestion(self, question):
        """Next suggested experiment: the first canonical research
        dimension never yet probed for this question (deterministic)."""
        tried = self.probed_dims(question)
        return next(
            (dim for dim in _CANONICAL_DIMS if dim not in tried),
            "",
        )

    # -------------------------------------------------

    def _load(self, path):
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict) and data:
                self._store.update(data)
        except (OSError, ValueError):
            self._store = {}

    def _save(self):
        if not self.path:
            return
        try:
            tmp = "%s.tmp" % self.path
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._store, fh, sort_keys=True, indent=1)
            os.replace(tmp, self.path)
        except OSError:
            pass