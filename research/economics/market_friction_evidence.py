"""Strict time-aligned historical market-friction evidence.

This module binds executable market-state observations to timestamps.  It does
not infer historical spread/slippage from a single snapshot or from trade tape
alone.  A valid sample requires a contemporaneous best bid/ask and, when
execution evidence is supplied, a contemporaneous fill with side/price.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = 1


def _d(value: object, name: str, *, positive: bool = False, nonnegative: bool = False) -> Decimal:
    try:
        v = Decimal(str(value))
    except Exception as exc:
        raise ValueError(f"{name} is not numeric") from exc
    if not v.is_finite() or (positive and v <= 0) or (nonnegative and v < 0):
        raise ValueError(f"{name} is invalid")
    return v


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _fingerprint(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical(payload)).hexdigest()


def normalize_samples(samples: Sequence[Mapping[str, Any]], *, symbol: str,
                      max_alignment_ms: int = 1000) -> list[dict[str, Any]]:
    if not samples:
        raise ValueError("friction samples must be non-empty")
    if max_alignment_ms < 0:
        raise ValueError("max_alignment_ms must be non-negative")
    out: list[dict[str, Any]] = []
    previous_ts = None
    for i, row in enumerate(samples):
        if not isinstance(row, Mapping):
            raise ValueError(f"sample {i} is malformed")
        if str(row.get("symbol")) != symbol:
            raise ValueError("sample symbol mismatch")
        ts = int(row["timestamp_ms"])
        if ts <= 0 or (previous_ts is not None and ts <= previous_ts):
            raise ValueError("friction timestamps must be strictly ascending")
        previous_ts = ts
        if "best_bid" not in row or "best_ask" not in row:
            raise ValueError("time-aligned best bid/ask evidence is required")
        bid = _d(row["best_bid"], "best_bid", positive=True)
        ask = _d(row["best_ask"], "best_ask", positive=True)
        if ask <= bid:
            raise ValueError("crossed or locked market")
        midpoint = (bid + ask) / Decimal("2")
        spread = ask - bid
        normalized: dict[str, Any] = {
            "symbol": symbol,
            "timestamp_ms": ts,
            "best_bid": str(bid),
            "best_ask": str(ask),
            "midpoint": str(midpoint),
            "spread": str(spread),
            "spread_bps": str(spread / midpoint * Decimal("10000")),
        }
        if "fill" in row and row["fill"] is not None:
            fill = row["fill"]
            if not isinstance(fill, Mapping):
                raise ValueError("fill is malformed")
            side = str(fill.get("side", "")).lower()
            if side not in {"buy", "sell"}:
                raise ValueError("fill side must be buy or sell")
            fill_ts = int(fill["timestamp_ms"])
            if abs(fill_ts - ts) > max_alignment_ms:
                raise ValueError("fill is outside market-state alignment window")
            fill_price = _d(fill["price"], "fill.price", positive=True)
            reference = ask if side == "buy" else bid
            executable_slippage = (fill_price - reference) if side == "buy" else (reference - fill_price)
            normalized["fill"] = {
                "timestamp_ms": fill_ts,
                "side": side,
                "price": str(fill_price),
                "reference_price": str(reference),
                "slippage": str(executable_slippage),
                "slippage_bps": str(executable_slippage / midpoint * Decimal("10000")),
            }
        out.append(normalized)
    return out


@dataclass(frozen=True, slots=True)
class MarketFrictionEvidenceArtifact:
    venue: str
    symbol: str
    source_endpoint: str
    captured_at: str
    alignment_ms: int
    samples: tuple[Mapping[str, Any], ...]
    evidence_sha256: str
    provenance_status: str = "REAL"

    @property
    def start_timestamp_ms(self) -> int:
        return int(self.samples[0]["timestamp_ms"])

    @property
    def end_timestamp_ms(self) -> int:
        return int(self.samples[-1]["timestamp_ms"])

    @property
    def has_realized_fill_evidence(self) -> bool:
        return any("fill" in s for s in self.samples)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "venue": self.venue,
            "symbol": self.symbol,
            "source_endpoint": self.source_endpoint,
            "captured_at": self.captured_at,
            "alignment_ms": self.alignment_ms,
            "provenance_status": self.provenance_status,
            "samples": [dict(s) for s in self.samples],
            "evidence_sha256": self.evidence_sha256,
        }


def build_artifact(*, samples: Sequence[Mapping[str, Any]], symbol: str,
                   captured_at: str, source_endpoint: str,
                   venue: str = "delta", alignment_ms: int = 1000,
                   provenance_status: str = "REAL") -> MarketFrictionEvidenceArtifact:
    normalized = normalize_samples(samples, symbol=symbol, max_alignment_ms=alignment_ms)
    payload = {
        "venue": venue,
        "symbol": symbol,
        "source_endpoint": source_endpoint,
        "alignment_ms": alignment_ms,
        "samples": normalized,
    }
    return MarketFrictionEvidenceArtifact(
        venue, symbol, source_endpoint, str(captured_at), alignment_ms,
        tuple(normalized), _fingerprint(payload), provenance_status,
    )


def write_artifact(artifact: MarketFrictionEvidenceArtifact, path: str | Path) -> None:
    Path(path).write_text(json.dumps(artifact.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_and_verify(path: str | Path) -> MarketFrictionEvidenceArtifact:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported market-friction evidence schema")
    symbol = str(raw.get("symbol", ""))
    alignment_ms = int(raw.get("alignment_ms", -1))
    samples = raw.get("samples")
    if not isinstance(samples, list):
        raise ValueError("market-friction samples missing")
    normalized = normalize_samples(samples, symbol=symbol, max_alignment_ms=alignment_ms)
    if normalized != samples:
        raise ValueError("market-friction normalization mismatch")
    payload = {
        "venue": str(raw.get("venue", "")),
        "symbol": symbol,
        "source_endpoint": str(raw.get("source_endpoint", "")),
        "alignment_ms": alignment_ms,
        "samples": normalized,
    }
    expected = _fingerprint(payload)
    if raw.get("evidence_sha256") != expected:
        raise ValueError("market-friction evidence fingerprint mismatch")
    return MarketFrictionEvidenceArtifact(
        payload["venue"], symbol, payload["source_endpoint"], str(raw["captured_at"]),
        alignment_ms, tuple(normalized), expected, str(raw.get("provenance_status", "UNKNOWN")),
    )
