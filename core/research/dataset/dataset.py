"""
====================================================

QuantEngine

Unified Research Dataset -- container (Phase 9I)

ResearchDataset: an append-only, deterministic, read-only container
of ResearchRow (the unified research fact model). It holds rows from
any of the frozen 9A-9H surfaces, de-duplicates by stable row_id, and
can be persisted to / loaded from a JSON file (atomic write, corrupt
file degrades to an empty dataset).

Pure data layer: no production imports, no ordering, no ledger, no
lookahead, no auto-promotion. All id derivation is deterministic
(sha1); persistence is deterministic (sorted serialization).
====================================================
"""

import json
import os
import tempfile

from core.research.dataset.row import (
    ResearchRow,
    row_from_dict,
    SOURCES,
    DatasetSource as S,
)


class ResearchDataset:
    """Unified research knowledge/data layer over 9A-9H rows."""

    def __init__(self, rows=None):
        self._rows = {}
        if rows:
            self.add_rows(rows)

    # ---- mutation (append-only) -----------------------------------
    def add_row(self, row):
        if not isinstance(row, ResearchRow):
            raise TypeError(
                "ResearchDataset accepts ResearchRow, got "
                f"{type(row).__name__}"
            )
        self._rows[row.row_id] = row
        return row.row_id

    def add_rows(self, rows):
        if hasattr(rows, "to_dict") or hasattr(rows, "snapshots"):
            rows = [rows]
        for row in rows:
            self.add_row(row)
        return self

    def extend(self, other):
        for row in other.rows():
            self.add_row(row)
        return self

    # ---- read surface ---------------------------------------------
    def rows(self, source=None):
        all_rows = list(self._rows.values())
        if source is None:
            return tuple(all_rows)
        if source not in SOURCES:
            raise ValueError(
                f"unknown dataset source {source!r}; "
                f"expected one of {SOURCES}"
            )
        return tuple(r for r in all_rows if r.source == source)

    def observation_ids(self, source=None):
        ids = set()
        for r in self.rows(source):
            if r.observation_id:
                ids.add(r.observation_id)
        return tuple(sorted(ids))

    def row_count(self):
        return len(self._rows)

    def empty(self):
        return len(self._rows) == 0

    # ---- serialization --------------------------------------------
    def to_dict(self):
        return {
            "phase": "9I",
            "row_count": self.row_count(),
            "rows": [
                self._rows[k].to_dict()
                for k in sorted(self._rows)
            ],
        }

    def persist(self, path):
        payload = json.dumps(
            self.to_dict(), default=str, separators=(",", ":"),
        )
        tmp_path = None
        try:
            fd, tmp_path = tempfile.mkstemp(
                prefix=os.path.basename(path) + "~",
                dir=os.path.dirname(os.path.abspath(path)),
            )
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
            os.replace(tmp_path, path)
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
        return path

    @classmethod
    def load(cls, path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return cls()
        rows = []
        for item in data.get("rows", []):
            try:
                rows.append(row_from_dict(item))
            except Exception:
                continue
        return cls(rows)
