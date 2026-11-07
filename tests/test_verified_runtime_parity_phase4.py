"""Phase-4 parity: paper and live share one verified architecture (offline).

Both runtimes consume the same evidence-gated multi-symbol verified
transport and differ ONLY at the execution sink.  The legacy
EventBus/ticker path is used by neither.
"""

import inspect
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from core.runtime.verified_runtime import (
    LiveNotAuthorized,
    VerifiedLiveRuntime,
    VerifiedPaperRuntime,
)


T = 1_775_814_834_000_000


class FakeSocket:
    def send(self, payload):
        pass

    def close(self):
        pass


def _evidence_path(test_case):
    candle_one = {"type": "candlestick_1m", "o": 100, "h": 101, "l": 99,
                  "c": 100, "v": 5, "res": "1m", "sy": "BTCUSDT",
                  "ts": T + 1_000_000, "cst": T}
    candle_two = dict(candle_one, h=102, c=101, v=7, ts=T + 2_000_000)
    candle_next = dict(candle_one, cst=T + 60_000_000,
                       ts=T + 60_000_001, c=103, h=103, v=9)
    trade = {"type": "trades", "p": "100", "s": "2", "r": "t",
             "sy": "BTCUSDT", "t": T, "ts": T + 500_000}
    echo = {"type": "subscriptions",
            "channels": [{"name": "candlestick_1m", "symbols": ["BTCUSDT"]}]}

    def record(frame, classification, ordinal):
        return {"receipt_ordinal": ordinal, "receipt_unix_ns": T,
                "frame": frame, "classification": classification}

    bundle = {
        "schema": "quantengine.delta-public-capture.v1",
        "endpoint": "wss://public-socket.delta.exchange",
        "symbol": "BTCUSDT",
        "started_unix": 1_775_814_834.0,
        "timeout_seconds": 130.0,
        "max_frames": 500,
        "requested_channels": ["trades", "candlestick_1m"],
        "include_control_frames": True,
        "frames": [
            record(trade, "requested_public_data", 1),
            record(candle_one, "requested_public_data", 2),
            record(candle_two, "requested_public_data", 3),
            record(candle_next, "requested_public_data", 4),
            record(echo, "control_or_unrequested", 5),
        ],
        "limitations": [],
    }
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8")
    try:
        tmp.write(json.dumps(bundle))
        tmp.flush()
        path = tmp.name
    finally:
        tmp.close()
    test_case.addCleanup(Path(path).unlink, True)
    return path


def _candle(cst, ts):
    return {"type": "candlestick_1m", "o": 100, "h": 101, "l": 99,
            "c": 100, "v": 5, "res": "1m", "sy": "BTCUSDT",
            "ts": ts, "cst": cst}


class ArmedSafety:
    armed = True


class UnarmedSafety:
    armed = False


class TestVerifiedRuntimeParity(unittest.TestCase):
    def test_paper_runtime_delivers_through_verified_transport_only(self):
        paper = VerifiedPaperRuntime(
            ["BTCUSDT"], evidence_bundle=_evidence_path(self),
            socket_factory=lambda endpoint: FakeSocket())
        paper.connect()
        paper.ingest(_candle(T, T + 1_000_000), receipt_timestamp=T + 1_000_001)
        paper.ingest(_candle(T, T + 2_000_000), receipt_timestamp=T + 2_000_001)
        paper.ingest(_candle(T + 60_000_000, T + 60_000_001),
                     receipt_timestamp=T + 60_000_002)
        self.assertEqual(len(paper.paper_sink.delivered), 1)
        # Paper fills are simulated and economics-tagged, never exchange writes.
        self.assertTrue(paper.paper_sink.fills[0]["simulated"])
        self.assertIn("economics_profile", paper.paper_sink.fills[0])

    def test_live_runtime_requires_armed_safety(self):
        with self.assertRaises(LiveNotAuthorized):
            VerifiedLiveRuntime(
                ["BTCUSDT"], lambda candle: None, safety=UnarmedSafety(),
                evidence_bundle=_evidence_path(self),
                socket_factory=lambda endpoint: FakeSocket())
        with self.assertRaises(LiveNotAuthorized):
            VerifiedLiveRuntime(
                ["BTCUSDT"], lambda candle: None, safety=None,
                evidence_bundle=_evidence_path(self),
                socket_factory=lambda endpoint: FakeSocket())

    def test_live_runtime_shares_feed_and_differs_only_at_sink(self):
        routed = []
        live = VerifiedLiveRuntime(
            ["BTCUSDT"], routed.append, safety=ArmedSafety(),
            evidence_bundle=_evidence_path(self),
            socket_factory=lambda endpoint: FakeSocket())
        live.connect()
        live.ingest(_candle(T, T + 1_000_000), receipt_timestamp=T + 1_000_001)
        live.ingest(_candle(T + 60_000_000, T + 60_000_001),
                    receipt_timestamp=T + 60_000_002)
        self.assertEqual(len(routed), 1)
        self.assertEqual(len(live.live_sink.routed), 1)
        # Same transport class, same endpoint, same resolution contract.
        self.assertEqual(live.transport.endpoint,
                         "wss://public-socket.delta.exchange")
        self.assertEqual(live.transport.resolution, "1m")

    def test_runtimes_take_explicit_symbols_not_symbols_index_zero(self):
        paper = VerifiedPaperRuntime(
            ["BTCUSDT", "ETHUSDT"], evidence_bundle=_evidence_path(self),
            socket_factory=lambda endpoint: FakeSocket())
        self.assertEqual(paper.symbols, ["BTCUSDT", "ETHUSDT"])
        with self.assertRaises(ValueError):
            VerifiedPaperRuntime(
                [], evidence_bundle=_evidence_path(self),
                socket_factory=lambda endpoint: FakeSocket())

    def test_no_legacy_ticker_or_eventbus_in_verified_runtime(self):
        import ast
        import core.runtime.verified_runtime as module
        source = inspect.getsource(module)
        # Strip documentation: the SYMBOLS[0] prohibition is documented in
        # the module docstring, so only executable code is inspected.
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef,
                                 ast.FunctionDef, ast.AsyncFunctionDef)):
                if (node.body and isinstance(node.body[0], ast.Expr)
                        and isinstance(node.body[0].value, ast.Constant)
                        and isinstance(node.body[0].value.value, str)):
                    node.body = node.body[1:]
        code = ast.unparse(tree)
        legacy_imports = [
            line.strip() for line in code.splitlines()
            if line.strip().startswith(("import ", "from "))
            and ("websocket_client" in line or "event_bus" in line
                 or "EventBus" in line or "DeltaSubscriptionStream" in line
                 or "ticker" in line)
        ]
        self.assertEqual(legacy_imports, [])
        self.assertNotIn("SYMBOLS[0]", code)
        self.assertNotIn("settings.SYMBOLS", code)
        self.assertNotIn("DeltaSubscriptionStream", code)

    def test_verified_runtime_wires_existing_delta_history_for_gap_recovery(self):
        calls = []

        class FakeHistory:
            def gap_candles(self, symbol, resolution, after_ts, before_ts):
                calls.append((symbol, resolution, after_ts, before_ts))
                return []

        with patch("core.exchanges.delta.delta_history.DeltaHistory", FakeHistory):
            paper = VerifiedPaperRuntime(
                ["BTCUSDT"], evidence_bundle=_evidence_path(self),
                socket_factory=lambda endpoint: FakeSocket())
            fetcher = paper.transport._history_fetcher
            self.assertIsNotNone(fetcher)
            self.assertEqual(fetcher("BTCUSDT", "1m", 100, 220), [])

        self.assertEqual(calls, [("BTCUSDT", "1m", 100, 220)])

    def test_verified_runtimes_inherit_evidence_gate(self):
        from data.delta.verified_socket_transport import GlobalEvidenceMissing
        paper = VerifiedPaperRuntime(
            ["BTCUSDT"], evidence_bundle="/nonexistent/bundle.json",
            socket_factory=lambda endpoint: FakeSocket())
        with self.assertRaises(GlobalEvidenceMissing):
            paper.connect()


if __name__ == "__main__":
    unittest.main()
