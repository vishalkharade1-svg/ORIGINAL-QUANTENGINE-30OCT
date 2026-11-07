"""11E step 1: dataset inventory + integrity + D1 fingerprint check."""
import hashlib
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from research.phase11e.common import load_raw_bars, run_backtest, validate_bars


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    out = {"datasets": {}}
    specs = {
        "D1_gatea": "docs/audit/baseline_9s_delta_5000_raw.json",
        "D2_phase7": "data/history/BTCUSDT_1m_oos.json",
        "D3_fresh": "research/phase11e/data/oos_fresh.json",
    }
    store = {}
    for name, rel in specs.items():
        path = BASE_DIR / rel
        doc = json.loads(path.read_text())
        bars, meta = load_raw_bars(doc)
        rep = validate_bars(bars)
        rep["sha256"] = sha256_file(path)
        rep["meta"] = meta
        out["datasets"][name] = rep
        store[name] = bars
        print(name, "n=%d gaps=%d dups=%d ooo=%d invalid=%d nonfinite=%d range=%s..%s" % (
            rep["n"], rep["gaps"], rep["duplicates"], rep["out_of_order"],
            rep["invalid_ohlc"], rep["non_finite"], rep["first"], rep["last"]))

    # D1 fingerprint through the research harness (must match spec).
    res = run_backtest(store["D1_gatea"])
    nets = [t["net"] for t in res["trades"]]
    fp = {
        "orders": len(res["orders"]),
        "fills": len(res["trades"]),
        "wins": sum(1 for x in nets if x > 0),
        "losses": sum(1 for x in nets if x < 0),
        "breakevens": sum(1 for x in nets if x == 0),
        "net": round(sum(nets), 6),
    }
    out["D1_fingerprint"] = fp
    print("D1 fingerprint:", fp)
    expected = {"orders": 27, "fills": 11, "wins": 6, "losses": 5,
                "breakevens": 0, "net": 0.117534}
    out["fingerprint_match"] = (fp == expected)
    print("MATCHES SPEC:", fp == expected)
    Path("research/phase11e/data/step1_integrity.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
