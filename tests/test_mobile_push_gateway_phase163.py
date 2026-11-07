"""Unit tests for MobilePushGateway and telemetry sanitization (Phase 163)."""

from __future__ import annotations

import json
import unittest
from core.monitoring.mobile_push_gateway import (
    MobilePushGateway,
    sanitize_telemetry_payload,
)


class TestMobilePushGateway(unittest.TestCase):
    def setUp(self):
        self.secret_token = "valid_mobile_token_xyz_123"
        self.gateway = MobilePushGateway(self.secret_token, max_client_queue_size=3)

    def test_handshake_authentication(self):
        self.assertTrue(self.gateway.authenticate_handshake("valid_mobile_token_xyz_123"))
        self.assertFalse(self.gateway.authenticate_handshake("wrong_token"))
        self.assertFalse(self.gateway.authenticate_handshake(""))
        self.assertFalse(self.gateway.authenticate_handshake(None))

        # Register client with bad token raises PermissionError
        with self.assertRaises(PermissionError):
            self.gateway.register_client("client_bad", "wrong_token")

    def test_secret_redaction(self):
        raw_payload = {
            "account_status": "FLAT",
            "api_key": "sensitive_testnet_key",
            "nested": {
                "credential_hash": "abc123secret",
                "delta_token": "bearer_456",
                "balance_usd": 10000.0,
            },
            "unrelated": "normal_data",
        }
        sanitized = sanitize_telemetry_payload(raw_payload)
        self.assertEqual(sanitized["api_key"], "[REDACTED]")
        self.assertEqual(sanitized["nested"]["credential_hash"], "[REDACTED]")
        self.assertEqual(sanitized["nested"]["delta_token"], "[REDACTED]")
        self.assertEqual(sanitized["nested"]["balance_usd"], 10000.0)
        self.assertEqual(sanitized["unrelated"], "normal_data")

    def test_broadcast_and_provenance_labeling(self):
        sub = self.gateway.register_client("client_01", self.secret_token)
        self.assertEqual(self.gateway.active_subscribers_count, 1)

        payload = {"symbol": "BTCUSD", "mark_price": 81050.0, "position_size": 0}
        delivered = self.gateway.broadcast("MARKET_TICK", payload, source="OBSERVED")
        self.assertEqual(delivered, 1)

        frame_str = sub.poll(timeout=0.1)
        self.assertIsNotNone(frame_str)
        frame = json.loads(frame_str)

        self.assertEqual(frame["event"], "MARKET_TICK")
        self.assertEqual(frame["source"], "OBSERVED")
        self.assertEqual(frame["data"]["mark_price"], 81050.0)
        self.assertIn("timestamp_ms", frame)

    def test_slow_client_queue_drop_does_not_block_engine(self):
        sub = self.gateway.register_client("slow_client", self.secret_token)
        # Gateway queue size is 3
        # Send 5 messages without polling
        for i in range(5):
            self.gateway.broadcast("EVENT", {"index": i})

        # Queue should hold exactly 3, and 2 should have been dropped
        self.assertEqual(sub.dropped_frames_count, 2)
        self.assertEqual(self.gateway.total_broadcast_frames, 5)

        # Ensure engine broadcast was non-blocking and successful
        m1 = json.loads(sub.poll(timeout=0.1))
        self.assertEqual(m1["data"]["index"], 0)

    def test_client_unregistration(self):
        self.gateway.register_client("client_temp", self.secret_token)
        self.assertEqual(self.gateway.active_subscribers_count, 1)

        self.gateway.unregister_client("client_temp")
        self.assertEqual(self.gateway.active_subscribers_count, 0)


if __name__ == "__main__":
    unittest.main()
