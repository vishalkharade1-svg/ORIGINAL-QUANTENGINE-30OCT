import hashlib, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "BTC": ("research/phase11f/data/universe_D2_BTC.json", "4256b0df1fbba1711bb86656138d8a2467fb0152bb071538f4a3ba39c3918903"),
    "ETH": ("research/phase11f/data/universe_D2_ETH.json", "cc4b8e27fca7ab50593f22badd844362f4120902155793ed44b0603534ea1a06"),
}

def test_preserved_d2_hashes_and_shape():
    for _, (rel, expected) in EXPECTED.items():
        p = ROOT / rel
        assert hashlib.sha256(p.read_bytes()).hexdigest() == expected
        bars = json.loads(p.read_text())["candles"]
        assert len(bars) == 3000
        ts = [int(x["time"]) for x in bars]
        assert all(b - a == 60 for a, b in zip(ts, ts[1:]))

def test_exact_phase7_full_file_is_not_claimed_recovered():
    assert not (ROOT / "data/history/BTCUSDT_1m_oos.json").exists()

def test_phase65_artifact_is_blocked_not_promoted():
    report = json.loads((ROOT / "research/results/phase65_d2_recovery.json").read_text())
    assert report["status"] == "D2_RECOVERED_FULL_RECERTIFICATION_BLOCKED"
    assert report["production_ready"] is False
