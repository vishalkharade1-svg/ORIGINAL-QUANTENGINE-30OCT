"""Strict authenticated Delta realized-fill evidence.

Only an authenticated venue response may produce REAL fill evidence.  Fixtures,
replays, or caller-supplied rows are never promoted to REAL by this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = 1


class EmptySymbolWindowError(ValueError):
    """Authenticated response contained zero rows for the requested symbol.

    Distinct from malformed evidence: the venue answered successfully and
    the rows parsed, but none belonged to this symbol (the venue ignores
    the symbol request parameter). Callers may record honest negative
    evidence for this outcome ONLY; every other ValueError means the
    evidence itself is invalid and must fail closed.
    """


def _row_symbol(row: Mapping[str, Any]) -> str:
    """Venue symbol for a fill row.

    Observed Delta `/v2/fills` rows carry ``product_symbol`` (not
    ``symbol``); accept ``symbol`` first, then ``product_symbol``,
    then a nested ``product`` mapping's symbol. Empty when absent.
    """
    sid = str(row.get("symbol", "") or "")
    if sid:
        return sid
    sid = str(row.get("product_symbol", "") or "")
    if sid:
        return sid
    product = row.get("product")
    if isinstance(product, Mapping):
        sid = str(product.get("symbol", "") or product.get("product_symbol", "") or "")
        if sid:
            return sid
    return ""


def _row_timestamp_ms(created: object) -> int:
    """Millisecond epoch for a fill timestamp.

    Legacy integer epochs pass through unchanged (existing fixtures
    and unit behavior preserved). ISO-8601 strings (the observed
    venue format, e.g. ``2026-10-11T08:13:04.391968Z``) parse to
    epoch milliseconds to align with friction ``timestamp_ms``.
    Anything else is invalid -- never guessed.
    """
    if isinstance(created, bool):
        raise ValueError("fill timestamp is invalid")
    if isinstance(created, int):
        timestamp = created
    else:
        try:
            timestamp = int(created)  # type: ignore[arg-type]
        except (TypeError, ValueError, OverflowError):
            timestamp = None
        if timestamp is None:
            text = str(created or "").strip()
            if not text:
                raise ValueError("fill timestamp is required")
            try:
                from datetime import datetime, timezone
                parsed = datetime.fromisoformat(
                    text.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                timestamp = int(parsed.timestamp() * 1000)
            except (ValueError, OverflowError, OSError) as exc:
                raise ValueError("fill timestamp is invalid") from exc
    if timestamp <= 0:
        raise ValueError("fill timestamp is invalid")
    return timestamp


def _d(value: object, name: str, *, positive=False, nonnegative=False) -> Decimal:
    try:
        v = Decimal(str(value))
    except Exception as exc:
        raise ValueError(f"{name} is not numeric") from exc
    if not v.is_finite() or (positive and v <= 0) or (nonnegative and v < 0):
        raise ValueError(f"{name} is invalid")
    return v


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def fingerprint(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical(payload)).hexdigest()


def normalize_fills(fills: Sequence[Mapping[str, Any]], *, symbol: str | None = None) -> list[dict[str, Any]]:
    if not fills:
        raise ValueError("fill evidence must be non-empty")
    out = []
    seen = set()
    previous = None
    for i, row in enumerate(fills):
        if not isinstance(row, Mapping):
            raise ValueError(f"fill {i} malformed")
        sid = _row_symbol(row)
        if not sid or (symbol is not None and sid != symbol):
            raise ValueError("fill symbol mismatch")
        fill_id = str(row.get("id") or row.get("fill_id") or row.get("uuid") or "")
        order_id = str(row.get("order_id") or "")
        if not fill_id or not order_id:
            raise ValueError("fill id and order_id are required")
        if fill_id in seen:
            raise ValueError("duplicate fill id")
        seen.add(fill_id)
        side = str(row.get("side", "")).lower()
        role = str(row.get("role", "")).lower()
        if side not in {"buy", "sell"}:
            raise ValueError("fill side must be buy or sell")
        if role not in {"maker", "taker"}:
            raise ValueError("fill role must be maker or taker")
        size = _d(row.get("size"), "size", positive=True)
        price = _d(row.get("price"), "price", positive=True)
        commission = _d(row.get("commission"), "commission", nonnegative=True)
        created = row.get("created_at") or row.get("timestamp") or row.get("created_at_ms")
        if created is None:
            raise ValueError("fill timestamp is required")
        timestamp = _row_timestamp_ms(created)
        if previous is not None and timestamp < previous:
            raise ValueError("fills must be ordered by timestamp")
        previous = timestamp
        out.append({
            "fill_id": fill_id,
            "order_id": order_id,
            "symbol": sid,
            "side": side,
            "role": role,
            "size": str(size),
            "price": str(price),
            "commission": str(commission),
            "timestamp": timestamp,
            "fill_type": str(row.get("fill_type") or row.get("fill_type_name") or "normal"),
        })
    return out


@dataclass(frozen=True, slots=True)
class DeltaFillEvidenceArtifact:
    venue: str
    environment: str
    symbol: str
    source_endpoint: str
    captured_at: str
    request_params: Mapping[str, Any]
    fills: tuple[Mapping[str, Any], ...]
    evidence_sha256: str
    provenance_status: str = "REAL"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "venue": self.venue,
            "environment": self.environment,
            "symbol": self.symbol,
            "source_endpoint": self.source_endpoint,
            "captured_at": self.captured_at,
            "request_params": dict(self.request_params),
            "fills": [dict(x) for x in self.fills],
            "evidence_sha256": self.evidence_sha256,
            "provenance_status": self.provenance_status,
        }


def build_artifact(*, fills: Sequence[Mapping[str, Any]], symbol: str,
                   captured_at: str, request_params: Mapping[str, Any],
                   source_endpoint: str,
                   environment: str = "PRODUCTION",
                   provenance_status: str = "REAL") -> DeltaFillEvidenceArtifact:
    if provenance_status != "REAL":
        raise ValueError("realized-fill artifact requires REAL venue provenance")
    normalized = normalize_fills(fills, symbol=symbol)
    payload = {
        "venue": "delta", "environment": environment, "symbol": symbol,
        "source_endpoint": source_endpoint, "request_params": dict(request_params),
        "fills": normalized,
    }
    return DeltaFillEvidenceArtifact(
        "delta", environment, symbol, source_endpoint, str(captured_at),
        dict(request_params), tuple(normalized), fingerprint(payload), "REAL"
    )


def write_artifact(artifact: DeltaFillEvidenceArtifact, path: str | Path) -> None:
    Path(path).write_text(json.dumps(artifact.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_and_verify(path: str | Path) -> DeltaFillEvidenceArtifact:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported fill evidence schema")
    if raw.get("provenance_status") != "REAL":
        raise ValueError("fill evidence is not REAL")
    symbol = str(raw.get("symbol", ""))
    fills = normalize_fills(raw.get("fills") or [], symbol=symbol)
    payload = {
        "venue": str(raw.get("venue", "")),
        "environment": str(raw.get("environment", "")),
        "symbol": symbol,
        "source_endpoint": str(raw.get("source_endpoint", "")),
        "request_params": dict(raw.get("request_params") or {}),
        "fills": fills,
    }
    expected = fingerprint(payload)
    if raw.get("evidence_sha256") != expected:
        raise ValueError("fill evidence fingerprint mismatch")
    return DeltaFillEvidenceArtifact(
        payload["venue"], payload["environment"], symbol,
        payload["source_endpoint"], str(raw["captured_at"]),
        payload["request_params"], tuple(fills), expected, "REAL"
    )


def capture_authenticated_fills(rest, *, symbol: str, environment: str = "PRODUCTION",
                                 source_endpoint: str, request_params: Mapping[str, Any] | None = None,
                                 captured_at: str) -> DeltaFillEvidenceArtifact:
    """Fetch /v2/fills through an authenticated REST client.

    The response itself is the provenance boundary.  This function accepts no
    caller-supplied fill rows and refuses unauthenticated clients.
    """
    if not getattr(rest, "authenticated", False):
        raise RuntimeError("authenticated Delta REST client is required")
    params = dict(request_params or {})
    if symbol:
        params.setdefault("symbol", symbol)
    response = rest.get("/v2/fills", params=params)
    if not isinstance(response, Mapping) or response.get("success") is False:
        raise RuntimeError("Delta fills response was unsuccessful")
    rows = response.get("result")
    if not isinstance(rows, list):
        raise ValueError("Delta fills response result is not a list")
    if symbol:
        # The venue ignores the symbol request parameter (observed:
        # multi-symbol rows despite symbol=BTCUSD). Filter client-side
        # to the requested symbol and record the accounting -- rows
        # for other symbols belong to their own per-symbol captures,
        # never to this artifact.
        seen_count = len(rows)
        rows = [r for r in rows
                if isinstance(r, Mapping) and _row_symbol(r) == symbol]
        kept_count = len(rows)
        params = dict(params)
        params["symbol_rows_seen"] = seen_count
        params["symbol_rows_kept"] = kept_count
        if not rows:
            raise EmptySymbolWindowError(
                "fill evidence must be non-empty "
                "(0 of %d rows matched symbol %s)"
                % (seen_count, symbol))
    # Venue row order is recency, not canonical: sort ascending by
    # parsed timestamp for the artifact's chronological invariant.
    # Rows are preserved verbatim; only their sequence is ordered.
    rows = sorted(rows, key=lambda r: _row_timestamp_ms(
        r.get("created_at") or r.get("timestamp")
        or r.get("created_at_ms") or 0))
    return build_artifact(
        fills=rows, symbol=symbol, captured_at=captured_at,
        request_params=params, source_endpoint=source_endpoint,
        environment=environment, provenance_status="REAL",
    )


def bind_to_market_friction(fill_artifact: DeltaFillEvidenceArtifact, friction_artifact) -> dict[str, Any]:
    """Bind authenticated fills to genuine contemporaneous best bid/ask samples.

    A fill is usable for realized slippage only when a same-symbol friction
    observation exists within the friction artifact's declared alignment window.
    No interpolation or nearest-bar fabrication is performed.
    """
    if fill_artifact.provenance_status != "REAL":
        raise ValueError("fill artifact is not REAL")
    if getattr(friction_artifact, "provenance_status", "UNKNOWN") != "REAL":
        raise ValueError("friction artifact is not REAL")
    if fill_artifact.symbol != friction_artifact.symbol:
        raise ValueError("fill/friction symbol mismatch")
    samples = list(friction_artifact.samples)
    if not samples:
        raise ValueError("friction artifact has no samples")
    bindings = []
    max_ms = int(friction_artifact.alignment_ms)
    for fill in fill_artifact.fills:
        ts = int(fill["timestamp"])
        candidates = [s for s in samples if abs(int(s["timestamp_ms"]) - ts) <= max_ms]
        if not candidates:
            raise ValueError(f"no aligned market-friction observation for fill {fill['fill_id']}")
        sample = min(candidates, key=lambda s: abs(int(s["timestamp_ms"]) - ts))
        bid = Decimal(str(sample["best_bid"]))
        ask = Decimal(str(sample["best_ask"]))
        price = Decimal(str(fill["price"]))
        reference = ask if fill["side"] == "buy" else bid
        slippage = (price - reference) if fill["side"] == "buy" else (reference - price)
        midpoint = Decimal(str(sample["midpoint"]))
        bindings.append({
            "fill_id": fill["fill_id"],
            "fill_timestamp": ts,
            "friction_timestamp": int(sample["timestamp_ms"]),
            "alignment_delta_ms": abs(int(sample["timestamp_ms"]) - ts),
            "reference_price": str(reference),
            "fill_price": str(price),
            "slippage": str(slippage),
            "slippage_bps": str(slippage / midpoint * Decimal("10000")),
        })
    payload = {
        "fill_evidence_sha256": fill_artifact.evidence_sha256,
        "friction_evidence_sha256": friction_artifact.evidence_sha256,
        "bindings": bindings,
    }
    return {**payload, "binding_sha256": fingerprint(payload)}
