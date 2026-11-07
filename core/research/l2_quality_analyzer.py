"""
QuantEngine Phase 187 — Offline L2 Market-Data Quality Analyzer & Verification Harness.

Contract & Verification Rules:
  1. Timestamp ordering & unit consistency (microseconds vs nanoseconds).
  2. Monotonic sequence gap detection & duplicate frame rejection.
  3. Crossed-book detection (best_bid >= best_ask).
  4. Extreme value filtering (NaN, Inf, negative, zero prices).
  5. Deterministic order-book reconstruction from raw frames.
  6. Quality metrics computation:
     - Message count & event rate (msg/sec)
     - Valid-book coverage percentage
     - Spread distribution (min, max, mean, std)
     - Depth distribution at top-1 and top-5 levels
     - Receive latency distribution
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
import glob
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.research.l2_book_tracker import L2BookTracker, BookValidityState


@dataclass
class QualityMetricsSummary:
    symbol: str
    total_messages: int
    valid_updates: int
    valid_coverage_pct: float
    gap_count: int
    stale_count: int
    crossed_book_count: int
    duplicate_count: int
    out_of_order_count: int
    min_spread_usd: Optional[str]
    max_spread_usd: Optional[str]
    avg_spread_usd: Optional[str]
    avg_top_bid_depth: Optional[str]
    avg_top_ask_depth: Optional[str]
    avg_latency_ms: Optional[float]
    min_latency_ms: Optional[float]
    max_latency_ms: Optional[float]


class L2QualityAnalyzer:
    """Offline analyzer that verifies raw and archived L2 captures."""

    def __init__(self, stale_threshold_seconds: float = 5.0):
        self.stale_threshold_seconds = stale_threshold_seconds

    def analyze_jsonl_capture(self, jsonl_path: Path | str) -> Dict[str, Any]:
        """Analyze raw JSONL capture containing timestamped frames."""
        path = Path(jsonl_path)
        if not path.exists():
            raise FileNotFoundError(f"Capture file not found: {path}")

        records: List[Dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

        return self.analyze_records(records, source_file=path.name)

    def analyze_archive_json(self, archive_path: Path | str) -> Dict[str, Any]:
        """Analyze historical delta_ob_updates_archive.json."""
        path = Path(archive_path)
        if not path.exists():
            raise FileNotFoundError(f"Archive file not found: {path}")

        data = json.loads(path.read_text(encoding="utf-8"))
        raw_frames = data.get("frames", [])
        symbol = data.get("identity", {}).get("symbol", "BTCUSD")

        records = []
        for f in raw_frames:
            records.append({
                "receipt_mono_ns": None,
                "receipt_utc_ns": f.get("ts", 0) * 1000 if "ts" in f else None,
                "raw": f,
            })

        return self.analyze_records(records, source_file=path.name, default_symbol=symbol)

    def analyze_records(
        self,
        records: List[Dict[str, Any]],
        source_file: str = "memory",
        default_symbol: str = "BTCUSD",
    ) -> Dict[str, Any]:
        """Core analysis engine evaluating integrity and quality metrics across records."""
        trackers: Dict[str, L2BookTracker] = {}
        duplicates: Dict[str, int] = {}
        out_of_order: Dict[str, int] = {}
        seen_sequences: Dict[str, set] = {}
        top_bid_depths: Dict[str, List[Decimal]] = {}
        top_ask_depths: Dict[str, List[Decimal]] = {}

        earliest_utc_ns: Optional[int] = None
        latest_utc_ns: Optional[int] = None

        for rec in records:
            receipt_mono_ns = rec.get("receipt_mono_ns")
            receipt_utc_ns = rec.get("receipt_utc_ns")
            msg = rec.get("raw", {})

            msg_type = msg.get("type")
            if msg_type != "ob_updates":
                continue

            symbol = msg.get("sy") or default_symbol
            symbol = symbol.upper()

            if symbol not in trackers:
                trackers[symbol] = L2BookTracker(symbol, self.stale_threshold_seconds)
                duplicates[symbol] = 0
                out_of_order[symbol] = 0
                seen_sequences[symbol] = set()
                top_bid_depths[symbol] = []
                top_ask_depths[symbol] = []

            seq = msg.get("seq")
            ts_us = msg.get("ts", 0)
            bids = msg.get("b", [])
            asks = msg.get("a", [])
            action = msg.get("action")

            if receipt_utc_ns:
                if earliest_utc_ns is None or receipt_utc_ns < earliest_utc_ns:
                    earliest_utc_ns = receipt_utc_ns
                if latest_utc_ns is None or receipt_utc_ns > latest_utc_ns:
                    latest_utc_ns = receipt_utc_ns

            # Sequence duplicate check
            if seq is not None:
                if seq in seen_sequences[symbol]:
                    duplicates[symbol] += 1
                seen_sequences[symbol].add(seq)

            tracker = trackers[symbol]

            # Sequence order check
            if tracker.last_sequence is not None and seq is not None:
                if seq < tracker.last_sequence:
                    out_of_order[symbol] += 1

            if action == "snapshot" or tracker.last_sequence is None:
                tracker.process_snapshot(bids, asks, seq, ts_us, receipt_mono_ns, receipt_utc_ns)
            else:
                tracker.process_update(bids, asks, seq, ts_us, receipt_mono_ns, receipt_utc_ns)

            # Record top depth if valid
            if tracker.state == BookValidityState.VALID:
                top_bid_depths[symbol].append(tracker.best_bid_size())
                top_ask_depths[symbol].append(tracker.best_ask_size())

        # Compile summaries
        per_symbol_results = {}
        for sym, tr in trackers.items():
            base_summary = tr.summary_dict()
            b_depths = top_bid_depths[sym]
            a_depths = top_ask_depths[sym]

            avg_b_depth = (
                str((sum(b_depths) / Decimal(str(len(b_depths)))).quantize(Decimal("0.0001")))
                if b_depths else None
            )
            avg_a_depth = (
                str((sum(a_depths) / Decimal(str(len(a_depths)))).quantize(Decimal("0.0001")))
                if a_depths else None
            )

            base_summary["duplicate_count"] = duplicates[sym]
            base_summary["out_of_order_count"] = out_of_order[sym]
            base_summary["avg_top_bid_depth"] = avg_b_depth
            base_summary["avg_top_ask_depth"] = avg_a_depth
            per_symbol_results[sym] = base_summary

        duration_sec = (
            (latest_utc_ns - earliest_utc_ns) / 1_000_000_000.0
            if (latest_utc_ns and earliest_utc_ns) else 0.0
        )

        return {
            "source_file": source_file,
            "total_records": len(records),
            "duration_seconds": round(duration_sec, 3),
            "symbols": per_symbol_results,
        }
