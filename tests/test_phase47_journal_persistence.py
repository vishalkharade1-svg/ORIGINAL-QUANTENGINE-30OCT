import json
import tempfile
import unittest
from pathlib import Path

from core.research.journal.research_repository import ResearchRepository
from core.research.journal.opportunity_record import OpportunityRecord
from core.research.journal.research_event import ResearchEvent


class TestPhase47JournalPersistence(unittest.TestCase):
    def make_repo(self):
        repo = ResearchRepository()
        repo.append_record(OpportunityRecord(
            canonical_id="BTCUSDT:10",
            exchange="DELTA", instrument_id="BTCUSDT", timeframe="1m",
            terminal_outcome="ORDER_NOT_CREATED", hub_timestamp=10,
        ))
        repo.append_event(ResearchEvent(
            event_id="evt-1-10-BACKTEST", provenance="BACKTEST",
            event_type="SETUP_DISCOVERED", bar=10, timestamp=1000,
            canonical_id="BTCUSDT:10", exchange="DELTA",
            instrument_id="BTCUSDT", timeframe="1m", strategy="BREAKOUT_CONTINUATION",
        ))
        return repo

    def test_roundtrip_and_identity(self):
        repo = self.make_repo()
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "journal.json"
            identity = repo.persist(path)
            loaded = ResearchRepository.load(path)
            self.assertEqual(identity, loaded.content_identity())
            self.assertEqual(repo.to_dict(), loaded.to_dict())

    def test_tamper_is_rejected(self):
        repo = self.make_repo()
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "journal.json"
            repo.persist(path)
            payload = json.loads(path.read_text())
            payload["records"][0]["instrument_id"] = "ETHUSDT"
            path.write_text(json.dumps(payload, sort_keys=True))
            with self.assertRaises(ValueError):
                ResearchRepository.load(path)

    def test_missing_identity_is_rejected(self):
        repo = self.make_repo()
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "journal.json"
            repo.persist(path)
            payload = json.loads(path.read_text())
            payload.pop("content_identity")
            path.write_text(json.dumps(payload, sort_keys=True))
            with self.assertRaises(ValueError):
                ResearchRepository.load(path)

    def test_repeated_persist_is_byte_identical(self):
        repo = self.make_repo()
        with tempfile.TemporaryDirectory() as td:
            p1 = Path(td) / "a.json"
            p2 = Path(td) / "b.json"
            repo.persist(p1)
            repo.persist(p2)
            self.assertEqual(p1.read_bytes(), p2.read_bytes())


if __name__ == "__main__":
    unittest.main()
