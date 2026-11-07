"""Windowed reconciliation for bounded private-fill captures.

Phase125 and Phase152 both ended with reconciliation BLOCKED for the same
reason: a bounded socket capture cannot contain fills that happened before the
socket was opened, so the strict all-fills comparison flags them as
``missing_from_ws`` and refuses. The refusal is honest, but it leaves repeat
matches uncertifiable -- the standing "repeat-match robustness" blocker.

These tests pin the windowed alternative: strictly less claimed than the strict
certificate, nothing silently dropped, and no relaxation inside the window.
"""
from __future__ import annotations

import json
import unittest

from research.economics.delta_fill_evidence import (
    DeltaFillEvidenceArtifact,
    build_artifact,
)
from research.economics.delta_private_fill_capture import (
    capture_from_frames,
    reconcile_with_rest,
    reconcile_with_rest_windowed,
)

SYMBOL = "ETHUSD"
CAPTURED_AT = "2026-10-16T12:00:00Z"


def ws_frame(fid, order, ts_us, *, side="buy", size="1", price="100",
             role="taker", symbol=SYMBOL):
    """A venue-shaped v2/user_trades frame: ``t`` is MICROSECONDS."""
    return {"type": "v2/user_trades", "sy": symbol, "f": fid, "o": order,
            "S": side, "s": size, "p": price, "r": role, "t": ts_us}


def capture(frames):
    return capture_from_frames(frames, symbol=SYMBOL, authenticated=True)


def rest_row(fid, order, ts_ms, *, side="buy", size="1", price="100",
             role="taker", symbol=SYMBOL):
    """A venue-shaped /v2/fills row: ``created_at`` is MILLISECONDS."""
    return {"id": fid, "order_id": order, "product_symbol": symbol,
            "side": side, "role": role, "size": size, "price": price,
            "commission": "0.01", "created_at": ts_ms}


def artifact(rows, *, symbol=SYMBOL, provenance="REAL"):
    if provenance != "REAL":
        # build_artifact refuses non-REAL by design, so construct directly:
        # this exercises the reconciler's own provenance gate.
        return DeltaFillEvidenceArtifact(
            "delta", "TESTNET", symbol, "/v2/fills", CAPTURED_AT, {},
            tuple(rows), "0" * 64, provenance)
    return build_artifact(fills=rows, symbol=symbol, captured_at=CAPTURED_AT,
                          request_params={}, source_endpoint="/v2/fills",
                          environment="TESTNET")


# Socket fills span ms 2000..3000; REST additionally holds one fill before
# (F1 @1000 ms) and one after (F4 @5000 ms) that window.
def bounded_capture():
    return capture([ws_frame("F2", "O1", 2_000_000),
                    ws_frame("F3", "O1", 3_000_000)])


def bounded_artifact():
    return artifact([rest_row("F1", "O0", 1000),
                     rest_row("F2", "O1", 2000),
                     rest_row("F3", "O1", 3000),
                     rest_row("F4", "O2", 5000)])


class TestWindowedReconciliation(unittest.TestCase):
    def test_strict_reconciler_refuses_the_bounded_case(self):
        """The blocker itself: pre/post-window fills make strict refuse."""
        with self.assertRaises(ValueError) as ctx:
            reconcile_with_rest(bounded_capture(), bounded_artifact())
        payload = json.loads(str(ctx.exception))
        self.assertEqual(payload["missing_from_ws"], ["F1", "F4"])
        self.assertEqual(payload["mismatches"], [])

    def test_windowed_matches_and_classifies_every_fill(self):
        record = reconcile_with_rest_windowed(bounded_capture(), bounded_artifact())
        self.assertEqual(record["status"], "MATCHED_WINDOWED")
        self.assertEqual(record["matched_fill_ids"], ["F2", "F3"])
        self.assertEqual(record["matched_fill_count"], 2)
        self.assertEqual(record["pre_window_fill_ids"], ["F1"])
        self.assertEqual(record["post_window_fill_ids"], ["F4"])
        self.assertEqual(record["window_ms"], {"start": 2000, "end": 3000})
        self.assertEqual(record["window_source"], "socket_fill_span")
        # It must not read as the strict certificate.
        self.assertNotEqual(record["status"], "MATCHED")
        self.assertIn("window-scoped only", record["claim"])

    def test_missing_in_window_fill_still_refuses(self):
        """No relaxation: an in-window REST fill with no socket frame fails.

        The socket-side fill (F3) is absent from the REST in-window set, which
        the reconciler reports as ``missing_from_rest`` -- the same direction
        the strict reconciler uses.
        """
        rows = [rest_row("F1", "O0", 1000), rest_row("F2", "O1", 2000),
                rest_row("F4", "O2", 5000)]
        with self.assertRaises(ValueError) as ctx:
            reconcile_with_rest_windowed(bounded_capture(), artifact(rows))
        payload = json.loads(str(ctx.exception))
        self.assertEqual(payload["missing_from_rest"], ["F3"])
        self.assertEqual(payload["missing_from_ws"], [])

    def test_extra_in_window_rest_fill_still_refuses(self):
        # Rows must be ascending: the artifact contract enforces it.
        rows = [rest_row("F1", "O0", 1000), rest_row("F2", "O1", 2000),
                rest_row("F9", "O3", 2500), rest_row("F3", "O1", 3000),
                rest_row("F4", "O2", 5000)]
        with self.assertRaises(ValueError) as ctx:
            reconcile_with_rest_windowed(bounded_capture(), artifact(rows))
        self.assertEqual(json.loads(str(ctx.exception))["missing_from_ws"], ["F9"])

    def test_field_mismatch_inside_window_refuses(self):
        rows = [rest_row("F1", "O0", 1000), rest_row("F2", "O1", 2000),
                rest_row("F3", "O1", 3000, price="101"),
                rest_row("F4", "O2", 5000)]
        with self.assertRaises(ValueError) as ctx:
            reconcile_with_rest_windowed(bounded_capture(), artifact(rows))
        mismatches = json.loads(str(ctx.exception))["mismatches"]
        self.assertEqual([(m["fill_id"], m["field"]) for m in mismatches],
                         [("F3", "price")])

    def test_socket_fill_absent_from_rest_refuses(self):
        """A phantom socket fill is never excused by windowing."""
        cap = capture([ws_frame("F2", "O1", 2_000_000),
                       ws_frame("F5", "O1", 2_500_000),
                       ws_frame("F3", "O1", 3_000_000)])
        with self.assertRaises(ValueError) as ctx:
            reconcile_with_rest_windowed(cap, bounded_artifact())
        self.assertEqual(json.loads(str(ctx.exception))["missing_from_rest"], ["F5"])

    def test_explicit_window_is_accepted_and_recorded(self):
        record = reconcile_with_rest_windowed(bounded_capture(), bounded_artifact(),
                                              window_ms=(2000, 3000))
        self.assertEqual(record["window_source"], "explicit")
        self.assertEqual(record["window_ms"], {"start": 2000, "end": 3000})
        self.assertEqual(record["matched_fill_ids"], ["F2", "F3"])

    def test_explicit_window_that_excludes_socket_fills_refuses(self):
        with self.assertRaises(ValueError) as ctx:
            reconcile_with_rest_windowed(bounded_capture(), bounded_artifact(),
                                         window_ms=(2500, 3000))
        self.assertEqual(
            json.loads(str(ctx.exception))["socket_fills_outside_window"], ["F2"])

    def test_window_start_after_end_refuses(self):
        with self.assertRaises(ValueError) as ctx:
            reconcile_with_rest_windowed(bounded_capture(), bounded_artifact(),
                                         window_ms=(3000, 2000))
        self.assertIn("after its end", str(ctx.exception))

    def test_unknown_timestamp_unit_is_refused_not_guessed(self):
        """A legacy frame has no venue 't', so its unit is unknown."""
        legacy = {"type": "v2/user_trades", "sy": SYMBOL, "f": "F2", "o": "O1",
                  "S": "buy", "s": "1", "p": "100", "r": "taker",
                  "timestamp": 2_000_000}
        with self.assertRaises(ValueError) as ctx:
            reconcile_with_rest_windowed(capture([legacy]), bounded_artifact())
        self.assertIn("timestamp unit", str(ctx.exception))

    def test_non_real_rest_artifact_refuses(self):
        rows = [rest_row("F2", "O1", 2000)]
        with self.assertRaises(ValueError) as ctx:
            reconcile_with_rest_windowed(bounded_capture(),
                                         artifact(rows, provenance="FIXTURE"))
        self.assertIn("not REAL", str(ctx.exception))

    def test_symbol_mismatch_refuses(self):
        other = artifact([rest_row("F2", "O1", 2000, symbol="BTCUSD")],
                         symbol="BTCUSD")
        with self.assertRaises(ValueError) as ctx:
            reconcile_with_rest_windowed(bounded_capture(), other)
        self.assertIn("symbol mismatch", str(ctx.exception))

    def test_fingerprint_binds_the_window(self):
        first = reconcile_with_rest_windowed(bounded_capture(), bounded_artifact())
        again = reconcile_with_rest_windowed(bounded_capture(), bounded_artifact())
        self.assertEqual(first["reconciliation_sha256"], again["reconciliation_sha256"])
        # A wider window pulls F4 in, so the fingerprint must move with it.
        wider = reconcile_with_rest_windowed(
            capture([ws_frame("F2", "O1", 2_000_000),
                     ws_frame("F3", "O1", 3_000_000),
                     ws_frame("F4", "O2", 5_000_000)]),
            bounded_artifact())
        self.assertNotEqual(first["reconciliation_sha256"],
                            wider["reconciliation_sha256"])


if __name__ == "__main__":
    unittest.main()
