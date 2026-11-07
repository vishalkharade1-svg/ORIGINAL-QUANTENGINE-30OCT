#!/usr/bin/env python3
"""Build a deterministic Phase-48 9A discovery-capture artifact.

Research-only: reuses the canonical Backtester + ResearchJournal path from the
existing 9A test fixture. No second execution engine, no network, no promotion.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.test_research_journal_9a import (
    Candle,
    break_candle,
    open_above_candle,
    win_after_candle,
    run_world,
)
from core.research.journal import ResearchJournal


OUT = ROOT / "research" / "results" / "phase48_discovery_capture.json"


def canonical(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def main():
    # Deterministic canonical 9A fixture: discovery -> order -> fill -> close.
    candles = [
        break_candle(1),
        open_above_candle(2),
        win_after_candle(3),
        Candle(170.0, 170.0, 169.0, 169.5, 4),
    ]
    journal = ResearchJournal()
    _, _, _, _ = run_world(candles, journal=journal)
    journal.finalize()
    repo = journal.repository
    payload = {
        "schema": "phase48-discovery-capture-v1",
        "source": "Backtester + ResearchJournal",
        "provenance": "BACKTEST",
        "record_count": repo.count,
        "event_count": len(repo.events),
        "records": [r.to_dict() for r in repo.records],
        "events": [e.to_dict() for e in repo.events],
        "production_ready": False,
    }
    payload["content_identity"] = hashlib.sha256(canonical(payload)).hexdigest()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"artifact": str(OUT), "content_identity": payload["content_identity"], "records": repo.count, "events": len(repo.events), "production_ready": False}, sort_keys=True))


if __name__ == "__main__":
    main()
