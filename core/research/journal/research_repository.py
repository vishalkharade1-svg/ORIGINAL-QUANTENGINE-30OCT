"""
====================================================

QuantEngine

Research Journal -- repository (Phase 9A)

Append-safe, deterministic storage for OpportunityRecord /
ResearchEvent data. In-memory for this phase (fully
deterministic and test-friendly). All ordering is by
(exchange, instrument_id) then original append order, so the
event/record stream is reproducible given identical inputs.

No external DB. Serialisation helpers (to_dict / from_dict)
are standard-library compatible for a future append-only JSON
document store.
====================================================
"""

from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path

from core.research.journal.opportunity_record import OpportunityRecord
from core.research.journal.research_event import ResearchEvent


@dataclass
class ResearchRepository:
    """Append-only collection of opportunity records + events."""

    records: list = field(default_factory=list)
    events: list = field(default_factory=list)

    def append_record(self, record):
        if isinstance(record, OpportunityRecord):
            self.records.append(record)
            return record
        if isinstance(record, dict):
            self.records.append(OpportunityRecord(**record))
            return self.records[-1]
        raise TypeError("record must be OpportunityRecord or dict")

    def append_event(self, event):
        if isinstance(event, ResearchEvent):
            self.events.append(event)
            return event
        if isinstance(event, dict):
            self.events.append(ResearchEvent(**event))
            return self.events[-1]
        raise TypeError("event must be ResearchEvent or dict")

    # --------------------------------------------------

    def by_canonical(self, canonical_id):
        return [r for r in self.records if r.canonical_id == canonical_id]

    def by_symbol(
        self, exchange=None, instrument_id=None, timeframe=None
    ):
        def _match(r):
            if exchange is not None and r.exchange != exchange:
                return False
            if (
                instrument_id is not None
                and r.instrument_id != instrument_id
            ):
                return False
            if timeframe is not None and r.timeframe != timeframe:
                return False
            return True

        return [r for r in self.records if _match(r)]

    def by_provenance(self, provenance):
        return [
            r
            for r in self.records
            if str(r.provenance) == str(provenance)
        ]

    @property
    def count(self):
        return len(self.records)

    def clear(self):
        self.records = []
        self.events = []

    # --------------------------------------------------

    SCHEMA = "9A-journal-v1"

    def to_dict(self):
        return {
            "schema": self.SCHEMA,
            "records": [r.to_dict() for r in self.records],
            "events": [e.to_dict() for e in self.events],
        }

    @classmethod
    def from_dict(cls, payload):
        if not isinstance(payload, dict):
            raise ValueError("journal artifact must be an object")
        if payload.get("schema") != cls.SCHEMA:
            raise ValueError("unsupported journal schema")
        records = payload.get("records")
        events = payload.get("events")
        if not isinstance(records, list) or not isinstance(events, list):
            raise ValueError("journal records/events must be lists")
        repo = cls()
        for item in records:
            if not isinstance(item, dict):
                raise ValueError("journal record must be an object")
            repo.append_record(OpportunityRecord(**item))
        for item in events:
            if not isinstance(item, dict):
                raise ValueError("journal event must be an object")
            repo.append_event(ResearchEvent(**item))
        return repo

    def content_identity(self):
        canonical = json.dumps(
            self.to_dict(), sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, default=str,
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def persist(self, path):
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(self.to_dict())
        payload["content_identity"] = self.content_identity()
        canonical = json.dumps(
            payload, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, default=str,
        ) + "\n"
        tmp = target.with_name(target.name + ".tmp")
        tmp.write_text(canonical, encoding="utf-8")
        os.replace(tmp, target)
        return self.content_identity()

    @classmethod
    def load(cls, path):
        target = Path(path)
        payload = json.loads(target.read_text(encoding="utf-8"))
        recorded = payload.pop("content_identity", None)
        if not recorded:
            raise ValueError("missing content_identity")
        repo = cls.from_dict(payload)
        actual = repo.content_identity()
        if recorded != actual:
            raise ValueError("journal content identity mismatch")
        return repo
