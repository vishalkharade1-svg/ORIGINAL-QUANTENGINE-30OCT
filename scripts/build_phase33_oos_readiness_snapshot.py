"""Phase 33 -- deterministic readiness snapshot for the current OOS cache.

Research-only. Reuses the existing readiness evaluator/monitor and the
existing acquisition quality audit. It never fetches data, executes a
strategy, changes hypotheses, or promotes anything.
"""
from __future__ import annotations

import hashlib
import io
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.research.acquisition.quality import audit_quality
from core.research.readiness import oos_execution_readiness as readiness
from core.research.readiness.monitor import run_monitor
from core.research.readiness.preregistration import FrozenPreregistration

CACHE = ROOT / "data" / "history" / "BTCUSDT_1m_oos_topup.json"
PROV = ROOT / "data" / "history" / "BTCUSDT_1m_oos_topup.provenance.json"
ROW_PROV = ROOT / "data" / "history" / "BTCUSDT_1m_oos_topup.row_provenance.json"
OUT = ROOT / "research" / "results" / "phase33_oos_readiness_snapshot.json"
BOUNDARY = 1788601440
OOS_START = 1788601500


def dataset_identity(rows):
    blob = json.dumps(sorted(rows, key=lambda r: r["time"]),
                      sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()


def main():
    if not CACHE.exists() or not PROV.exists() or not ROW_PROV.exists():
        raise SystemExit("required Phase-32 OOS cache/provenance is absent")
    env = json.loads(CACHE.read_text(encoding="utf-8"))
    provenance = json.loads(PROV.read_text(encoding="utf-8"))
    row_provenance = json.loads(ROW_PROV.read_text(encoding="utf-8"))
    rows = list(env.get("raw", ()))
    identity = dataset_identity(rows)
    if identity != env.get("dataset_identity"):
        raise SystemExit("DATASET_IDENTITY_MISMATCH")
    if row_provenance.get("row_count") != len(rows):
        raise SystemExit("ROW_PROVENANCE_COUNT_MISMATCH")
    if provenance.get("dataset_identity") != identity:
        raise SystemExit("PROVENANCE_DATASET_IDENTITY_MISMATCH")

    dataset = readiness.observe_dataset(rows, BOUNDARY, frozenset())
    prereg = FrozenPreregistration.create(
        hypotheses=(), dataset_identity=identity,
        discovery_boundary=BOUNDARY, oos_boundary=OOS_START,
        minimum_contiguous_bars=readiness.REQUIRED_CONTIGUOUS_CLEAN_BARS,
        minimum_fresh_bars=int(readiness.required_fresh_bars()),
        economics_requirements=tuple(readiness.ECONOMICS_FIELDS),
        multiple_testing_family="Sidak-9L",
        symbol_constraints=("BTCUSDT",),
        directional_constraints=(), regime_constraints=(),
        frozen_execution_semantics="run_frozen_oos/9M",
        limitations=("no current eligible preregistered hypothesis",
                     "readiness snapshot only; no OOS execution"))

    econ_source = json.loads((ROOT / "data" / "fixtures" / "delta" /
                              "delta_venue_economics_observation_20260925.json")
                             .read_text(encoding="utf-8"))
    economics = {}
    for field in readiness.ECONOMICS_FIELDS:
        item = econ_source.get(field, {})
        economics[field] = (item.get("status", "UNAVAILABLE"),
                            item.get("note", "no venue evidence"))

    snapshot = run_monitor(
        prereg, dataset=dataset, dataset_identity=identity,
        fills_observed=3, economics=economics,
        microstructure=("UNAVAILABLE", "OHLCV-only dataset; no depth/trades"),
        provenance=provenance, latest_stored_timestamp=max(
            r["time"] for r in rows) if rows else None,
        source_rows=[], repository_forensic_status="BLOCKED")
    quality = audit_quality(rows, step=60, requested=env.get("requested"))

    artifact = {
        "phase": 33,
        "name": "Deterministic current OOS readiness snapshot",
        "status": "IMPLEMENTED_TESTED",
        "purpose": "Bind current genuine OOS data, provenance, quality, and existing readiness gates into one deterministic research snapshot.",
        "snapshot": snapshot.to_dict(),
        "dataset": {
            "identity": identity,
            "rows": len(rows),
            "start": min(r["time"] for r in rows) if rows else None,
            "end": max(r["time"] for r in rows) if rows else None,
            "row_provenance_identity": row_provenance.get("provenance_identity"),
        },
        "quality": quality,
        "observed_execution": {"orders": 21, "completed_trades": 3,
                               "wins": 1, "losses": 2},
        "limitations": [
            "No current 9L hypothesis is preregistered; this snapshot does not execute or validate a hypothesis.",
            "Only 3 completed trades are available against the 60-trade 9M minimum.",
            "No new network data was used; source freshness remains an operator prerequisite.",
            "Microstructure evidence is unavailable from the current OHLCV dataset.",
            "Repository-wide certification remains unverified for the supplied ZIP because historical fixtures/ancestry are absent.",
        ],
        "production_ready": False,
        "is_production_ready": False,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8")
    print("phase33_status=BLOCKED")
    print("handoff=%s" % snapshot.handoff_state)
    print("bars=%d fills=%d/%d" % (len(rows), 3, snapshot.required_fills))
    print("snapshot_id=%s" % snapshot.snapshot_id)
    print("dataset_identity=%s" % identity)


if __name__ == "__main__":
    main()
