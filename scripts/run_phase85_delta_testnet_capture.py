#!/usr/bin/env python3
"""Phase 85 non-trading Delta Testnet evidence capture orchestrator.

Uses only fresh credentials supplied via environment. Never places orders. It
captures public L2, authenticated REST fills, and private WS fills where the
account/feed provides them. Empty fills are reported as unavailable evidence;
no synthetic rows are created.
"""
from __future__ import annotations
import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import socket
import time
from urllib.parse import urlencode, urlparse
import sys
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.economics.delta_environment import resolve_environment, validate_endpoints


def redact_error(exc: BaseException) -> str:
    """Return a safe, bounded error without request headers or secret values."""
    msg = f"{type(exc).__name__}: {exc}"
    for secret in (os.getenv("DELTA_INDIA_TESTNET_API_KEY", ""), os.getenv("DELTA_INDIA_TESTNET_API_SECRET", "")):
        if secret:
            msg = msg.replace(secret, "[REDACTED]")
    return msg[:500]


def dns_probe(hosts: list[str]) -> dict[str, dict[str, str]]:
    out = {}
    for host in hosts:
        try:
            infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
            out[host] = {"status": "RESOLVED", "address_count": str(len(infos))}
        except OSError as exc:
            out[host] = {"status": "BLOCKED", "error": redact_error(exc)}
    return out


class SignedDeltaREST:
    """Minimal signed REST client restricted to the selected Delta environment."""
    authenticated = True

    def __init__(self, base_url: str, api_key: str, api_secret: str, timeout: float = 15.0):
        if not api_key.strip() or not api_secret.strip():
            raise ValueError("fresh DELTA_INDIA_TESTNET_API_KEY and DELTA_INDIA_TESTNET_API_SECRET environment variables are required")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key.strip()
        self.api_secret = api_secret.strip()
        self.timeout = timeout

    def get(self, path: str, params: dict | None = None):
        import httpx
        # Canonicalize once: the exact query string below is both signed and
        # sent, so the prehash path+query always matches the wire request
        # (per docs: signature over method + timestamp + requestPath +
        # query params + body). Docs also mandate a User-Agent header to
        # avoid CDN 4XX rejections.
        sorted_params = sorted((str(k), str(v)) for k, v in dict(params or {}).items())
        query = urlencode(sorted_params)
        path_query = path + ("?" + query if query else "")
        timestamp = str(int(time.time()))
        signature = hmac.new(self.api_secret.encode(), ("GET" + timestamp + path_query).encode(), hashlib.sha256).hexdigest()
        headers = {"api-key": self.api_key, "timestamp": timestamp, "signature": signature,
                   "User-Agent": "quantengine-phase85-capture",
                   "Content-Type": "application/json", "Accept": "application/json"}
        url = self.base_url + path_query
        response = httpx.get(url, headers=headers, timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("success") is False:
            raise RuntimeError("Delta REST returned unsuccessful response")
        return payload


async def run(args):
    env = resolve_environment(args.environment)
    validate_endpoints(args.environment, rest_base_url=args.rest_url or env.rest_base_url,
                       private_ws_url=args.private_ws_url or env.private_ws_url)
    public_ws_url = args.public_ws_url or env.public_ws_url
    key, secret = os.getenv("DELTA_INDIA_TESTNET_API_KEY", ""), os.getenv("DELTA_INDIA_TESTNET_API_SECRET", "")
    report = {
        "phase": 85, "title": "Delta Testnet non-trading evidence capture and reconciliation",
        "started_at": datetime.now(timezone.utc).isoformat(), "environment": env.name,
        "symbol": args.symbol, "order_placement": "DISABLED",
        "credentials_source": "environment_only", "credentials_persisted": False,
        "real_public_l2": "NOT_EXECUTED", "authenticated_rest_fills": "NOT_EXECUTED",
        "private_ws_fills": "NOT_EXECUTED", "rest_ws_reconciliation": "BLOCKED",
        "economic_certification": "BLOCKED", "production_ready": False,
    }
    hosts = [urlparse(env.rest_base_url).hostname, urlparse(env.private_ws_url).hostname,
             urlparse(public_ws_url).hostname]
    report["dns_probe"] = dns_probe(list(dict.fromkeys(h for h in hosts if h)))
    if any(v["status"] != "RESOLVED" for v in report["dns_probe"].values()):
        report["status"] = "BLOCKED_NETWORK_DNS"
        report["blocker"] = "One or more required Delta Testnet hosts failed DNS resolution; no authenticated request or REAL evidence was attempted. Previously exposed credentials were not reused."
        return report
    has_creds = bool(key.strip() and secret.strip())
    if not has_creds:
        report["credentials_status"] = "BLOCKED_CREDENTIALS_NOT_CONFIGURED"
        report["credentials_note"] = (
            "Fresh rotated testnet credentials must be configured as environment "
            "variables for authenticated REST/private-WS steps; public L2 capture "
            "proceeds without credentials. Previously exposed credentials are not reused."
        )

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    rest = SignedDeltaREST(env.rest_base_url, key, secret) if has_creds else None
    rest_artifact = None
    if not has_creds:
        report["authenticated_rest_fills"] = "BLOCKED_CREDENTIALS_NOT_CONFIGURED"
        report["private_ws_fills"] = "BLOCKED_CREDENTIALS_NOT_CONFIGURED"
    else:
        try:
            from research.economics.delta_fill_evidence import (
                EmptySymbolWindowError, capture_authenticated_fills, write_artifact)
            rest_artifact = capture_authenticated_fills(
                rest, symbol=args.symbol, environment=env.name.upper(),
                source_endpoint=env.rest_base_url + "/v2/fills",
                request_params={"symbol": args.symbol, "page_size": args.page_size},
                captured_at=datetime.now(timezone.utc).isoformat(),
            )
            write_artifact(rest_artifact, out / "rest_fills.json")
            report["authenticated_rest_fills"] = "CAPTURED" if rest_artifact.fills else "EMPTY_RESPONSE"
            report["rest_fill_count"] = len(rest_artifact.fills)
            if not rest_artifact.fills:
                report["rest_fills_artifact"] = "NOT_WRITTEN_EMPTY"
        except Exception as exc:
            # ONLY the typed empty-window outcome is honest negative
            # evidence. Malformed rows, bad shapes, auth failures, and
            # unexpected errors report FAILED and fail closed.
            if isinstance(exc, EmptySymbolWindowError):
                report["authenticated_rest_fills"] = "EMPTY_RESPONSE"
                report["rest_fill_count"] = 0
                report["rest_fills_note"] = (
                    "Authenticated /v2/fills returned no rows for this symbol; "
                    "no fill artifact written."
                )
            else:
                report["authenticated_rest_fills"] = "FAILED"
                report["rest_error"] = redact_error(exc)
                report["status"] = "PARTIAL_CAPTURE_BLOCKED"

    try:
        from research.economics.delta_live_capture import CaptureIdentity, capture_live as capture_l2, process_frames, write_result
        identity = CaptureIdentity(venue="delta", environment="SANDBOX", symbol=args.symbol,
                                   source_endpoint=public_ws_url, transport="LIVE_CAPTURE", capture_id=args.capture_id)
        frames = await capture_l2(endpoint=public_ws_url, symbol=args.symbol,
                                  duration_seconds=args.duration, identity=identity,
                                  min_observations=args.min_observations)
        artifact, archive, manifest = process_frames(frames, identity=identity, min_observations=args.min_observations)
        write_result(output_dir=out / "l2", artifact=artifact, archive=archive, manifest=manifest)
        report["real_public_l2"] = "CAPTURED"
        report["l2_observation_count"] = manifest.get("observations_emitted")
    except Exception as exc:
        report["real_public_l2"] = "FAILED"
        report["l2_error"] = redact_error(exc)

    if not has_creds:
        pass
    else:
        try:
            from research.economics.delta_private_fill_capture import capture_live as capture_private, build_private_archive, verify_private_archive
            cap = await capture_private(endpoint=env.private_ws_url, api_key=key, api_secret=secret,
                                        symbol=args.symbol, duration_seconds=args.duration)
            archive = build_private_archive(cap)
            verify_private_archive(archive)
            (out / "private_ws_fills.json").write_text(json.dumps(archive, sort_keys=True, indent=2) + "\n", encoding="utf-8")
            report["private_ws_fills"] = "CAPTURED"
            report["private_ws_fill_count"] = len(cap.fills)
            if report.get("authenticated_rest_fills") == "CAPTURED":
                result = __import__("research.economics.delta_private_fill_capture", fromlist=["reconcile_with_rest"]).reconcile_with_rest(cap, rest_artifact)
                report["rest_ws_reconciliation"] = result["status"]
                report["reconciliation"] = result
        except Exception as exc:
            report["private_ws_fills"] = "FAILED_OR_NO_FILLS"
            report["private_ws_error"] = redact_error(exc)

    if report.get("real_public_l2") == "CAPTURED" and report.get("rest_ws_reconciliation") == "MATCHED":
        report["economic_certification"] = "PENDING_FEE_FUNDING_INTERVAL_BINDING"
    report["status"] = "CAPTURE_COMPLETED_WITH_GAPS" if any(
        report[k] not in {"CAPTURED", "MATCHED"} for k in ("real_public_l2", "authenticated_rest_fills", "private_ws_fills", "rest_ws_reconciliation")
    ) else "CAPTURED_RECONCILIATION_MATCHED_CERTIFICATION_PENDING"
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", default="india_testnet")
    parser.add_argument("--symbol", required=True, help="Explicit Delta Testnet symbol; no order will be placed")
    parser.add_argument("--duration", type=float, default=30.0)
    parser.add_argument("--min-observations", type=int, default=2)
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--capture-id", default="phase85-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    parser.add_argument("--output-dir", default="research/captures/phase85")
    parser.add_argument("--rest-url")
    parser.add_argument("--private-ws-url")
    parser.add_argument("--public-ws-url")
    args = parser.parse_args()
    report = asyncio.run(run(args))
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    path = out / "phase85_capture_report.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    print(f"report_path={path}")

if __name__ == "__main__":
    main()
