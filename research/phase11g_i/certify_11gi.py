"""11G-I dataset certification runner (no strategies, no economics).

Normalizes the acquired UM aggTrades to canonical TradeEvents,
validates (quality engine), cross-checks against klines OHLCV,
registers the dataset, and writes quality/provenance/manifest
artifacts. Deterministic: re-running yields identical hashes.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from research.phase11g import datasets as DG11G  # noqa: E402 (seal helpers)
from research.phase11g.events import canonical as EV  # noqa: E402
from research.phase11g.normalization import normalize as NZ  # noqa: E402
from research.phase11g.provenance import model as PM  # noqa: E402
from research.phase11g.registry import registry as RG  # noqa: E402
from research.phase11g.validation import quality as Q  # noqa: E402
from research.phase11g_i import normalize_binance as NB  # noqa: E402

PHASE_DIR = Path(__file__).resolve().parent
RAW = PHASE_DIR / "acquisition" / "raw" / "BTCUSDT" / "2026-09-05"
OUT = PHASE_DIR / "certified"
SYMBOL = "BTCUSDT"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    events, stats = NB.normalize_aggtrades_zip(
        RAW / "BTCUSDT-aggTrades-2026-09-05.zip",
        SYMBOL, source="binance-vision:um-aggTrades")
    print("trades:", stats["rows"])
    accepted, rejected = Q.validate_trades(list(events))
    print("accepted:", len(accepted), "rejected:", len(rejected))
    krows, _ = NB.read_klines_zip(RAW / "BTCUSDT-1m-2026-09-05.zip")
    xcheck = NB.cross_check_trades_vs_klines(accepted, krows)
    print("cross-check:", json.dumps(xcheck, indent=1)[:400])
    rep = Q.quality_report(accepted, rejected, symbol=SYMBOL, resolution="tick")
    rep["aggressor_sides"] = {
        "buy": sum(1 for t in accepted if t.side == "buy"),
        "sell": sum(1 for t in accepted if t.side == "sell")}
    rep["kline_cross_check"] = xcheck
    (OUT / "quality_report.json").write_text(json.dumps(rep, indent=1, sort_keys=True))
    canon = [e.to_dict() for e in accepted]
    chash = PM.content_hash(canon)
    (OUT / "normalized_hash.txt").write_text(chash + "\n")
    acq = json.loads((RAW / "acquisition_manifest.json").read_text())
    prov = PM.build_provenance(
        dataset_id="binance_um_aggtrades_BTCUSDT_2026-09-05",
        source="https://data.binance.vision/data/futures/um/daily/aggTrades/BTCUSDT/",
        provider="binance-vision", exchange="binance", instrument="BTCUSDT",
        market_type="USD-M perpetual", symbol=SYMBOL, timeframe="tick",
        start_timestamp=accepted[0].event_timestamp,
        end_timestamp=accepted[-1].event_timestamp,
        row_count=len(accepted), timezone="UTC",
        timestamp_convention="event-ms (source µs //1000)",
        ordering_convention="timestamp-then-trade-id",
        duplicate_policy="reject", gap_policy="enumerate",
        schema_version="11ge-v1", retrieval_timestamp=acq["acquired_at"],
        content_hash=chash,
        raw_file_hash=acq["files"]["aggTrades"]["local_sha256"],
        transformation_hash=PM.transformation_hash(
            "um-aggTrades-csv->canonical-TradeEvent v1", "11gi-v1"),
        transformation_description="CSV agg rows to TradeEvents; side from is_buyer_maker (True->sell); µs->ms",
        measurement_class="REAL", contamination_status="fresh-acquired, unused by any research",
        intended_phase="11G-I (substrate certification; future REAL family)",
        access_restrictions="none (public data)",
        freshness_verdict="FRESH")
    (OUT / "provenance.json").write_text(json.dumps(prov, indent=1, sort_keys=True))
    reg = RG.bootstrap_11g_registry()
    reg.register("binance_um_trades_BTCUSDT_2026-09-05",
                 {"source": prov["source"], "symbol": SYMBOL,
                  "trades": len(accepted)}, "FRESH")
    (OUT / "registry_snapshot.json").write_text(
        json.dumps(reg.summary(), indent=1, sort_keys=True))
    print("certified:", len(accepted), "hash:", chash[:16])


if __name__ == "__main__":
    main()
