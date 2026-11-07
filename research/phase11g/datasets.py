"""Phase 11G-A dataset descriptors (metadata only, D3 sealed).

Stage-A feature tests use synthetic bars exclusively so research data
stays pristine for Stage B. This module therefore exposes frozen
universe metadata WITHOUT reading candle arrays. content_hash() exists
for Stage-B provenance use; nothing in Stage A calls it (enforced by
test: the Stage-A suite never invokes content_hash).

D1/D2 carry prior 11F research exposure (lineage_status CONTAMINATED,
disclosed). D3 is SEALED: any access attempt raises before I/O and is
counted in D3_ACCESS (read/hash/load stay 0 by construction).
"""

from __future__ import annotations

D3_ACCESS = {"read": 0, "hash": 0, "load": 0, "blocked": 0}


class SealedHoldoutError(RuntimeError):
    pass


DATASETS = {
    "D1_BTC": {"dataset_id": "D1_BTC", "symbol": "BTCUSDT", "timeframe": "1m",
               "start_timestamp": 1787755440, "end_timestamp": 1787995440,
               "bar_count": 4001, "source": "research/phase11f/data/universe_D1_BTC.json",
               "data_fields": ["time", "open", "high", "low", "close", "volume"],
               "measurement_class": "REAL OHLCV",
               "lineage_status": "CONTAMINATED (11F hypothesis development, disclosed)"},
    "D1_ETH": {"dataset_id": "D1_ETH", "symbol": "ETHUSDT", "timeframe": "1m",
               "start_timestamp": 1787755440, "end_timestamp": 1787995440,
               "bar_count": 4001, "source": "research/phase11f/data/universe_D1_ETH.json",
               "data_fields": ["time", "open", "high", "low", "close", "volume"],
               "measurement_class": "REAL OHLCV",
               "lineage_status": "CONTAMINATED (11F hypothesis development, disclosed)"},
    "D2_BTC": {"dataset_id": "D2_BTC", "symbol": "BTCUSDT", "timeframe": "1m",
               "start_timestamp": 1787995500, "end_timestamp": 1788175440,
               "bar_count": 3000, "source": "research/phase11f/data/universe_D2_BTC.json",
               "data_fields": ["time", "open", "high", "low", "close", "volume"],
               "measurement_class": "REAL OHLCV",
               "lineage_status": "CONTAMINATED (11F validation, disclosed)"},
    "D2_ETH": {"dataset_id": "D2_ETH", "symbol": "ETHUSDT", "timeframe": "1m",
               "start_timestamp": 1787995500, "end_timestamp": 1788175440,
               "bar_count": 3000, "source": "research/phase11f/data/universe_D2_ETH.json",
               "data_fields": ["time", "open", "high", "low", "close", "volume"],
               "measurement_class": "REAL OHLCV",
               "lineage_status": "CONTAMINATED (11F validation, disclosed)"},
}


def describe(dataset_id):
    desc = dict(DATASETS[dataset_id])
    # Content hash is a Stage-B provenance input (requires candle reads);
    # Stage A records the slot explicitly as unfilled.
    desc["sha256"] = None
    return desc


def all_ids():
    return sorted(DATASETS)


def assert_not_holdout(path):
    s = str(path)
    if "D3" in s or "universe_D3_" in s or s.endswith("D3"):
        D3_ACCESS["blocked"] += 1
        raise SealedHoldoutError("D3 is SEALED: %s" % path)


def load_holdout(*args, **kwargs):  # pragma: no cover - seal enforcement
    D3_ACCESS["blocked"] += 1
    raise SealedHoldoutError("D3 is SEALED in 11G-A")


def content_hash(dataset_id):  # Stage-B provenance helper; NOT used in Stage A.
    import hashlib
    import json
    from pathlib import Path
    doc = json.loads((Path(__file__).resolve().parent.parent.parent
                      / DATASETS[dataset_id]["source"]).read_text())
    return hashlib.sha256(json.dumps(doc["candles"], sort_keys=True).encode()).hexdigest()
