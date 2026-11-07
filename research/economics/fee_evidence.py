"""Strict venue fee evidence for Delta products.

Product fee fields are venue evidence of the published/configured fee rate at
capture time. They are not evidence of a user's actual charged commission;
actual fills remain the authority for realized commission.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

SCHEMA_VERSION = 1


def _d(value: object, name: str) -> Decimal:
    try:
        v = Decimal(str(value))
    except Exception as exc:
        raise ValueError(f"{name} is not numeric") from exc
    if not v.is_finite() or v < 0:
        raise ValueError(f"{name} is invalid")
    return v


def _canonical(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def fee_fingerprint(*, symbol: str, maker_rate: str, taker_rate: str,
                    source_endpoint: str) -> str:
    payload = {
        "symbol": symbol,
        "maker_commission_rate": maker_rate,
        "taker_commission_rate": taker_rate,
        "source_endpoint": source_endpoint,
    }
    return hashlib.sha256(_canonical(payload)).hexdigest()


def normalize_product_fee(response: Mapping[str, Any], *, symbol: str) -> dict[str, str]:
    if not isinstance(response, Mapping):
        raise ValueError("product response must be an object")
    result = response.get("result", response)
    if isinstance(result, list):
        matches = [p for p in result if isinstance(p, Mapping) and str(p.get("symbol")) == symbol]
        if len(matches) != 1:
            raise ValueError("product fee response must contain exactly one matching symbol")
        result = matches[0]
    if not isinstance(result, Mapping):
        raise ValueError("product response has no product object")
    if str(result.get("symbol")) != symbol:
        raise ValueError("product symbol mismatch")
    maker = _d(result.get("maker_commission_rate"), "maker_commission_rate")
    taker = _d(result.get("taker_commission_rate"), "taker_commission_rate")
    return {
        "symbol": symbol,
        "maker_commission_rate": str(maker),
        "taker_commission_rate": str(taker),
    }


@dataclass(frozen=True, slots=True)
class FeeEvidenceArtifact:
    venue: str
    symbol: str
    source_endpoint: str
    captured_at: str
    result: Mapping[str, str]
    evidence_sha256: str
    provenance_status: str = "REAL"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "venue": self.venue,
            "symbol": self.symbol,
            "source_endpoint": self.source_endpoint,
            "captured_at": self.captured_at,
            "provenance_status": self.provenance_status,
            "result": dict(self.result),
            "evidence_sha256": self.evidence_sha256,
        }


def build_artifact(*, response: Mapping[str, Any], symbol: str,
                   captured_at: str,
                   source_endpoint: str = "/v2/products") -> FeeEvidenceArtifact:
    normalized = normalize_product_fee(response, symbol=symbol)
    fp = fee_fingerprint(
        symbol=symbol,
        maker_rate=normalized["maker_commission_rate"],
        taker_rate=normalized["taker_commission_rate"],
        source_endpoint=source_endpoint,
    )
    return FeeEvidenceArtifact("delta", symbol, source_endpoint, str(captured_at), normalized, fp)


def write_artifact(artifact: FeeEvidenceArtifact, path: str | Path) -> None:
    Path(path).write_text(json.dumps(artifact.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_and_verify(path: str | Path) -> FeeEvidenceArtifact:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported fee evidence schema")
    result = raw.get("result")
    if not isinstance(result, Mapping):
        raise ValueError("fee artifact has no result")
    symbol = str(raw.get("symbol", ""))
    normalized = normalize_product_fee({"result": dict(result)}, symbol=symbol)
    if dict(result) != normalized:
        raise ValueError("fee evidence normalization mismatch")
    expected = fee_fingerprint(
        symbol=symbol,
        maker_rate=normalized["maker_commission_rate"],
        taker_rate=normalized["taker_commission_rate"],
        source_endpoint=str(raw.get("source_endpoint", "")),
    )
    if raw.get("evidence_sha256") != expected:
        raise ValueError("fee evidence fingerprint mismatch")
    return FeeEvidenceArtifact(
        "delta", symbol, str(raw["source_endpoint"]), str(raw["captured_at"]),
        normalized, expected, str(raw.get("provenance_status", "UNKNOWN")),
    )


def to_cost_spec(artifact: FeeEvidenceArtifact, *, role: str):
    """Convert verified venue fee evidence to the canonical CostSpec.

    This intentionally supplies commission only. Spread/slippage are separate
    evidence domains and must never be synthesized from a fee artifact.
    """
    if artifact.provenance_status != "REAL":
        raise ValueError("fee evidence is not genuine venue evidence")
    role = str(role).lower()
    if role not in {"maker", "taker"}:
        raise ValueError("role must be maker or taker")
    from core.risk.costs import CostSpec
    rate = artifact.result[f"{role}_commission_rate"]
    return CostSpec(rate=float(rate), venue_source=f"delta:{artifact.source_endpoint}#{artifact.evidence_sha256}")
