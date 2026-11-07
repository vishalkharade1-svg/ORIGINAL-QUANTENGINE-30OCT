"""Snapshot journal must fsync its complete record before atomic replacement."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.live.reconciler import Reconciler


class TestReconcilerSnapshotDurability(unittest.TestCase):
    def test_persist_fsyncs_and_restart_reader_sees_complete_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "broker.json"
            reconciler = Reconciler(snapshot_path=str(path))
            state = reconciler.snapshot_state(False, None, 1, None, 123)
            with patch("core.live.reconciler.os.fsync", wraps=os.fsync) as fsync:
                self.assertTrue(reconciler.persist(state))
            self.assertTrue(fsync.called)
            self.assertEqual(Reconciler(snapshot_path=str(path)).load_snapshot(), state)


if __name__ == "__main__":
    unittest.main()
