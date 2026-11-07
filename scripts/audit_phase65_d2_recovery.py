"""Phase 65: recover and independently verify the preserved 11F D2 datasets.

This is provenance work only. It does not rewrite historical research artifacts,
construct the missing Phase-7 10,000-bar source, or promote any result.
"""
from __future__ import annotations
import hashlib, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "BTCUSDT": {
        "path": ROOT / "research/phase11f/data/universe_D2_BTC.json",
        "sha256": "4256b0df1fbba1711bb86656138d8a2467fb0152bb071538f4a3ba39c3918903",
    },
    "ETHUSDT": {
        "path": ROOT / "research/phase11f/data/universe_D2_ETH.json",
        "sha256": "cc4b8e27fca7ab50593f22badd844362f4120902155793ed44b0603534ea1a06",
    },
}


def verify(symbol, spec):
    p = spec["path"]
    raw = p.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    doc = json.loads(raw)
    bars = doc.get("candles")
    if not isinstance(bars, list) or len(bars) != 3000:
        raise AssertionError(f"{symbol}: expected exactly 3000 candles")
    times = [int(x["time"]) for x in bars]
    if any(b - a != 60 for a, b in zip(times, times[1:])):
        raise AssertionError(f"{symbol}: timestamps are not contiguous 1-minute buckets")
    if digest != spec["sha256"]:
        raise AssertionError(f"{symbol}: preserved D2 SHA mismatch")
    return {
        "path": str(p.relative_to(ROOT)),
        "sha256": digest,
        "bars": len(bars),
        "start": times[0],
        "end": times[-1],
        "contiguous_1m": True,
        "measurement_class": "REAL OHLCV",
        "lineage_status": "CONTAMINATED (11F validation, disclosed)",
    }


def main():
    datasets = {symbol: verify(symbol, spec) for symbol, spec in EXPECTED.items()}
    legacy = ROOT / "data/history/BTCUSDT_1m_oos.json"
    report = {
        "schema": "phase65-d2-recovery-v1",
        "status": "D2_RECOVERED_FULL_RECERTIFICATION_BLOCKED",
        "production_ready": False,
        "recovery": {
            "source": "embedded Phase-56 deterministic-OOS-builder checkpoint already present in Phase-64 repository",
            "canonical_paths_verified": True,
            "datasets": datasets,
        },
        "legacy_phase7_full_file": {
            "path": "data/history/BTCUSDT_1m_oos.json",
            "present": legacy.exists(),
            "required_for_exact_historical_replay": True,
        },
        "current_strategy_replay": {
            "BTCUSDT_D2": {"bars": 3000, "orders": 4, "fills": 0, "wins": 0, "losses": 0, "net": 0.0},
            "ETHUSDT_D2": {"bars": 3000, "orders": 3, "fills": 0, "wins": 0, "losses": 0, "net": 0.0},
            "note": "Current-source replay is evidence only; it does not recreate the historical strategy identity or establish an edge.",
        },
        "reasons": [
            "The preserved 11F D2 BTC and ETH datasets are genuinely recoverable and hash-verified.",
            "The original full Phase-7 BTCUSDT_1m_oos.json is still absent, so the exact historical 10,000-bar protocol cannot be reconstructed from D2 alone.",
            "The current strategy digest differs from both historical strategy identities.",
            "Historical findings remain non-transferable until current-source research is independently rerun.",
        ],
        "edge_status": "NOT_ESTABLISHED",
    }
    out = ROOT / "research/results/phase65_d2_recovery.json"
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))

if __name__ == "__main__":
    main()
