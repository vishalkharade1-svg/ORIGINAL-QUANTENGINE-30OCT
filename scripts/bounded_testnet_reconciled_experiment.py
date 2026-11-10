"""Reconciled Testnet order experiment: private WS listens DURING placement.

Runs the bounded 2-leg flow (see bounded_testnet_order_experiment.py for
the safety contract, unchanged here) while a private v2/user_trades
socket session records live fill frames. Afterwards:
  * REST fills -> REAL artifact,
  * WS frames (credential-scrubbed) -> hash-chained archive,
  * REST <-> WS reconciliation.

Secret safety: every received WS frame is scrubbed of api-key/signature
material (any depth) BEFORE archiving or persisting; scrub hits are
counted and reported. Redaction uses exact configured values only.

Usage:
  ... --dry-run    # pre-checks only, zero writes (as before)
  ... --execute    # authorized run only
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import bounded_testnet_order_experiment as exp
from research.economics import delta_private_fill_capture as priv
from research.economics.delta_fill_evidence import (
    capture_authenticated_fills, write_artifact,
)

WS_LISTEN_S = 75.0
PLACE_AT_S = 8.0


def scrub(value, secrets: tuple, hits: list):
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if (isinstance(key, str)
                    and key.replace("-", "").replace("_", "").lower()
                    in ("apikey", "apisecret", "signature", "token")):
                hits.append(key)
                continue
            out[key] = scrub(item, secrets, hits)
        return out
    if isinstance(value, list):
        return [scrub(item, secrets, hits) for item in value]
    if isinstance(value, str) and value:
        for secret in secrets:
            if secret and secret in value:
                hits.append("value")
                return "[REDACTED]"
    return value


async def listen_private(endpoint, key, secret, symbol, duration):
    import websockets
    frames = []
    deadline = time.monotonic() + duration
    started = time.monotonic()
    async with websockets.connect(
            endpoint, ping_interval=20, ping_timeout=5,
            close_timeout=5, max_size=8 * 1024 * 1024) as ws:
        await ws.send(json.dumps(priv.key_auth_message(key, secret),
                                 separators=(",", ":")))
        authenticated = False
        while time.monotonic() < deadline:
            timeout = max(0.1, deadline - time.monotonic())
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
            except asyncio.TimeoutError:
                break
            frame = priv.decode_frame(raw)
            frames.append(frame)
            if frame.get("type") == "key-auth":
                if frame.get("success") is not True:
                    raise RuntimeError(
                        "private WS authentication failed")
                authenticated = True
                await ws.send(json.dumps(priv.subscription(symbol),
                                         separators=(",", ":")))
    return frames, authenticated, time.monotonic() - started


def run_blocking(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--auth-doc", default=str(exp.AUTH_DOC_PATH),
                        help="authorization document of record (default: "
                             "reports/PHASE193A_TESTNET_AUTHORIZATION.md)")
    parser.add_argument("--ledger-path", default=None,
                        help="persistent experiment ledger (tests only)")
    parser.add_argument("--output-dir",
                        default="research/captures/phase115_recon")
    args = parser.parse_args(argv)
    execute = bool(args.execute)
    if execute and args.dry_run:
        print("EXPERIMENT_REFUSED: pass exactly one mode")
        return 2

    gate = None
    record = None
    if execute:
        from core.execution.testnet_authorization_gate import TestnetAuthorizationGate
        gate = TestnetAuthorizationGate(
            ledger_path=Path(args.ledger_path) if args.ledger_path else None)
        auth_doc = Path(args.auth_doc)
        try:
            record = gate.parse_authorization_document(auth_doc)
        except Exception as exc:
            print(f"EXPERIMENT_REFUSED: Authorization document {auth_doc.name} unreadable: {type(exc).__name__}: {exc}")
            return 2
        if not record.is_currently_valid():
            print(f"EXPERIMENT_REFUSED: Authorization document {auth_doc.name} is not operator-approved: {record.state.value}")
            return 2

    try:
        from research.economics.delta_environment import validate_endpoints
        validate_endpoints("india_testnet", rest_base_url=exp.TESTNET_REST,
                           private_ws_url=exp.TESTNET_PRIVATE_WS)
    except Exception:
        print("EXPERIMENT_REFUSED: India Testnet endpoint/environment mismatch")
        return 2
    key = os.getenv("DELTA_INDIA_TESTNET_API_KEY", "")
    secret = os.getenv("DELTA_INDIA_TESTNET_API_SECRET", "")
    if execute and (not key.strip() or not secret.strip()):
        print("EXPERIMENT_REFUSED: dedicated India Testnet credentials required")
        return 2
    secrets = tuple(v for v in (key.strip(), secret.strip()) if v)

    from core.exchanges.delta.delta_auth import DeltaSignedREST
    rest = DeltaSignedREST(api_key=key.strip(), api_secret=secret.strip(),
                           base_url=exp.TESTNET_REST)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    evidence: dict = {
        "schema": "quantengine.testnet-reconciled-experiment.v1",
        "environment": "india_testnet", "symbol": exp.SYMBOL,
        "mode": "execute" if execute else "dry-run",
        "capture_id": exp.CAPTURE_ID, "production_ready": False,
    }

    # Pre-checks mirror the bounded experiment (product/flat/touch).
    # Reuse its pieces by running its dry-run core inline is complex;
    # instead require a fresh dry-run artifact to exist is overkill:
    # run the same calls directly and cheaply here.
    try:
        catalog = rest.get("/v2/products").get("result", [])
        match = [r for r in catalog if r.get("symbol") == exp.SYMBOL]
        assert len(match) == 1
        product = match[0]
        product_id = int(product["id"])
        assert (
            product.get("contract_type") == "perpetual_futures"
            and product.get("state") == "live"
            and product.get("trading_status") == "operational"
        ), "BTCUSD product is not live and operational"
        contract_value = Decimal(str(
            product.get("contract_size") or product.get("contract_value") or "0"
        ))
        assert contract_value.is_finite() and contract_value > 0, (
            "BTCUSD contract value unavailable"
        )
        if gate is not None:
            assert contract_value == gate.scope.contract_size_btc, (
                "live BTCUSD contract value differs from signed authorization scope"
            )
        presp = rest.get("/v2/positions",
                         params={"product_id": product_id})
        pres = presp.get("result", {})
        recs = ([pres] if isinstance(pres, dict) else list(pres or []))
        assert all(abs(float(r.get("size", 0) or 0)) == 0 for r in recs
                   if isinstance(r, dict)
                   ), "account not flat"
        orders = rest.get("/v2/orders",
                          params={"product_id": product_id})
        live = [o for o in orders.get("result", []) or []
                if isinstance(o, dict) and str(o.get("state", "")).lower()
                in ("open", "pending", "working", "untriggered")]
        assert not live, "open orders exist"
        import httpx
        book = httpx.get(exp.TESTNET_REST + "/v2/l2orderbook/%s" % exp.SYMBOL,
                         params={"depth": 1}, timeout=20).json()
        result = book.get("result", {})
        ask = float(result["sell"][0]["price"])
        bid = float(result["buy"][0]["price"])
        assert bid > 0 and ask > bid, f"insane touch prices (crossed or locked book: bid={bid} >= ask={ask})"
    except Exception as exc:
        print("EXPERIMENT_REFUSED: pre-check failed: %s: %s"
              % (type(exc).__name__, exc))
        return 2
    evidence["prechecks"] = {"product_id": product_id, "flat": True,
                             "bid": bid, "ask": ask}
    print("prechecks ok bid=%s ask=%s" % (bid, ask))
    if not execute:
        (out / "recon_experiment_report.json").write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")
        print("dry-run complete, zero writes")
        return 0

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    listen_task = loop.create_task(listen_private(
        exp.TESTNET_PRIVATE_WS, key.strip(), secret.strip(),
        exp.SYMBOL, WS_LISTEN_S))

    # Concurrent public L2 capture over the same window, so fills can
    # later be bound to contemporaneous market friction. Non-fatal:
    # a thin book must not abort the fill evidence.
    from research.economics.delta_environment import resolve_environment
    from research.economics.delta_live_capture import (
        capture_live as capture_l2,
    )
    from research.economics.market_friction_capture import CaptureIdentity
    public_ws_url = resolve_environment("india_testnet").public_ws_url
    l2_identity = CaptureIdentity(
        venue="delta", environment="SANDBOX", symbol=exp.SYMBOL,
        source_endpoint=public_ws_url, transport="LIVE_CAPTURE",
        capture_id=exp.CAPTURE_ID + "-l2")
    l2_task = loop.create_task(capture_l2(
        endpoint=public_ws_url, symbol=exp.SYMBOL,
        duration_seconds=WS_LISTEN_S, identity=l2_identity,
        min_observations=2))

    # Mutable ownership journal is populated immediately after each
    # acknowledged placement, even if a later leg fails. Cleanup must
    # never infer ownership from a broad open-orders query alone.
    placed_records: list[dict] = []

    async def place_legs():
        await asyncio.sleep(PLACE_AT_S)
        return await loop.run_in_executor(
            None, do_legs, rest, gate, record, product_id, bid, ask,
            placed_records)

    legs = []
    placement_error = None
    frames = []
    authenticated = False
    listen_s = 0.0
    l2_frames: list = []
    try:
        try:
            legs = loop.run_until_complete(place_legs())
        except Exception as exc:
            # Preserve the failure as evidence and continue to the
            # bounded cleanup/reconciliation path. Do not retry a write.
            placement_error = "%s: %s" % (type(exc).__name__, exc)
            evidence["placement_error"] = placement_error
        try:
            frames, authenticated, listen_s = loop.run_until_complete(
                listen_task)
        except Exception as exc:
            frames, authenticated, listen_s = [], False, 0.0
            evidence["private_ws_error"] = "%s: %s" % (
                type(exc).__name__, exc)
        try:
            l2_frames = loop.run_until_complete(l2_task)
        except Exception as exc:
            l2_frames = []
            evidence["l2"] = {"status": "FAILED",
                              "error": "%s: %s" % (type(exc).__name__, exc)}
    finally:
        if not listen_task.done():
            listen_task.cancel()
        if not l2_task.done():
            l2_task.cancel()
    evidence["legs"] = legs
    evidence["placed_order_ids_observed"] = [
        str(item.get("order_id", "")) for item in placed_records]
    evidence["ws"] = {"frames": len(frames),
                      "authenticated": authenticated,
                      "listen_s": round(listen_s, 1)}
    print("legs=%s ws_frames=%d auth=%s" % (legs, len(frames),
                                            authenticated))

    # Cleanup is deliberately before secondary evidence processing: a
    # later parser/archive/write failure must not skip the safety action.
    cleanup = exp._cleanup(rest, product_id, placed_records)
    evidence["cleanup"] = cleanup
    if placement_error:
        evidence["experiment_status"] = "PLACEMENT_FAILED_CLEANUP_ATTEMPTED"
    if cleanup.get("cancel_unconfirmed") or cleanup.get("ownership_unverified"):
        evidence["experiment_status"] = "RECONCILIATION_REQUIRED"

    # Scrub BEFORE anything is persisted or archived.
    hits: list = []
    clean = [scrub(dict(f), secrets, hits) for f in frames]
    evidence["scrub_hits"] = len(hits)
    (out / "private_ws_frames.json").write_text(
        json.dumps(clean, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")

    # REST artifact: ONLY a typed empty window is negative evidence.
    # Malformed rows, bad shapes, auth failures, and unexpected errors
    # fail closed (FAILED) and are never mislabeled as "no fills".
    from research.economics.delta_fill_evidence import EmptySymbolWindowError
    try:
        rest_artifact = capture_authenticated_fills(
            _RestAdapter(rest), symbol=exp.SYMBOL,
            environment="INDIA_TESTNET",
            source_endpoint=exp.TESTNET_REST + "/v2/fills",
            request_params={"symbol": exp.SYMBOL, "page_size": 100},
            captured_at=datetime.now(timezone.utc).isoformat())
        write_artifact(rest_artifact, out / "rest_fills.json")
        evidence["rest_fills"] = len(rest_artifact.fills)
    except EmptySymbolWindowError as exc:
        rest_artifact = None
        evidence["rest_fills"] = 0
        evidence["rest_fills_note"] = "no %s fills in window: %s" % (exp.SYMBOL, exc)
    except (ValueError, RuntimeError) as exc:
        rest_artifact = None
        evidence["rest_fills"] = "FAILED"
        evidence["rest_error"] = "%s" % type(exc).__name__

    # WS archive + reconciliation (honest outcomes, never forced).
    try:
        cap = priv.capture_from_frames(clean, symbol=exp.SYMBOL,
                                       authenticated=authenticated)
        archive = priv.build_private_archive(cap)
        priv.verify_private_archive(archive)
        (out / "private_ws_archive.json").write_text(
            json.dumps(archive, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")
        try:
            result = priv.reconcile_with_rest(cap, rest_artifact)
            evidence["reconciliation"] = result
        except Exception as exc:
            strict_error = "%s: %s" % (type(exc).__name__, exc)
            try:
                result = priv.reconcile_with_rest_windowed(cap, rest_artifact)
                result["strict_reconciliation_attempt"] = {
                    "status": "FAILED_STRICT",
                    "error": strict_error
                }
                evidence["reconciliation"] = result
            except Exception as w_exc:
                evidence["reconciliation"] = {
                    "status": "BLOCKED",
                    "strict_error": strict_error,
                    "windowed_error": "%s: %s" % (type(w_exc).__name__, w_exc)}
    except Exception as exc:
        evidence["reconciliation"] = {
            "status": "BLOCKED",
            "reason": "%s: %s" % (type(exc).__name__, exc)}
    print("reconciliation=%s" %
          json.dumps(evidence["reconciliation"], sort_keys=True)[:400])

    # Fill/friction binding against the concurrent L2 window.
    if l2_frames:
        try:
            from research.economics.delta_live_capture import (
                process_frames, write_result)
            from research.economics.delta_fill_evidence import (
                bind_to_market_friction)
            from decimal import Decimal
            friction_artifact, friction_archive, manifest = process_frames(
                l2_frames, identity=l2_identity, min_observations=2)
            write_result(output_dir=out / "l2", artifact=friction_artifact,
                         archive=friction_archive, manifest=manifest)
            evidence["l2"] = {
                "status": "CAPTURED",
                "observations": manifest.get("observations_emitted"),
                "range_ms": [manifest.get("start_timestamp_ms"),
                             manifest.get("end_timestamp_ms")],
                "evidence_sha256":
                    getattr(friction_artifact, "evidence_sha256", ""),
            }
            try:
                binding = bind_to_market_friction(rest_artifact,
                                                  friction_artifact)
                evidence["fill_friction_binding"] = binding
            except Exception as exc:
                # Whole-artifact binding requires EVERY fill aligned;
                # pre-window fills cannot align by construction. Fall
                # back to a per-fill analysis with the module's exact
                # nearest-sample rule (analysis, not a module
                # certificate).
                windowed = []
                samples = list(
                    getattr(friction_artifact, "samples", ()))
                max_ms = int(getattr(friction_artifact,
                                     "alignment_ms", 1000))
                for fill in rest_artifact.fills:
                    ts = int(fill["timestamp"])
                    cands = [s for s in samples
                             if abs(int(s["timestamp_ms"]) - ts) <= max_ms]
                    if not cands:
                        windowed.append(
                            {"fill_id": fill["fill_id"],
                             "status": "NO_ALIGNED_SAMPLE"})
                        continue
                    sample = min(cands, key=lambda s: abs(
                        int(s["timestamp_ms"]) - ts))
                    bid = Decimal(str(sample["best_bid"]))
                    ask = Decimal(str(sample["best_ask"]))
                    price = Decimal(str(fill["price"]))
                    reference = ask if fill["side"] == "buy" else bid
                    slippage = ((price - reference)
                                if fill["side"] == "buy"
                                else (reference - price))
                    midpoint = Decimal(str(sample["midpoint"]))
                    windowed.append({
                        "fill_id": fill["fill_id"],
                        "status": "BOUND",
                        "reference_price": str(reference),
                        "slippage": str(slippage),
                        "slippage_bps": str(
                            slippage / midpoint * Decimal("10000")),
                        "alignment_delta_ms": abs(
                            int(sample["timestamp_ms"]) - ts),
                    })
                evidence["fill_friction_binding"] = {
                    "status": "WINDOWED_ANALYSIS",
                    "module_error": "%s: %s" % (type(exc).__name__, exc),
                    "bindings": windowed,
                }
        except Exception as exc:
            evidence["fill_friction_binding"] = {
                "status": "FAILED",
                "reason": "%s: %s" % (type(exc).__name__, exc)}
    else:
        evidence.setdefault("l2", {"status": "NO_FRAMES"})
        evidence["fill_friction_binding"] = {
            "status": "BLOCKED", "reason": "no concurrent L2 frames"}
    print("binding=%s" %
          json.dumps(evidence["fill_friction_binding"], sort_keys=True)[:400])

    (out / "recon_experiment_report.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    print("report_path=%s" % (out / "recon_experiment_report.json"))
    return 0


class _RestAdapter:
    """Adapter exposing .authenticated for the fill capturer."""
    authenticated = True

    def __init__(self, rest):
        self._rest = rest

    def get(self, path, params=None):
        return self._rest.get(path, params=params)


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(str(ROOT / ".env"), override=True)
    raise SystemExit(main())



def do_legs(rest_client, gate, record, pid, bid_px, ask_px,
            placed_records=None):
    """Place the bounded 2-leg flow under per-leg authorization.

    Hoisted to module scope (Phase193B/B) so deterministic offline tests
    can drive it directly; ``main`` passes the parsed gate/record.

    Phase193B/B contract:
      * every leg is atomically reserved via the gate
        (check_and_reserve_order) immediately before its transport call,
        and the reservation decision mints the transport authority bound
        to the experiment endpoint.  A refused preflight raises BEFORE
        the write (zero transport writes for that leg).
      * a failed fresh touch read FAILS CLOSED: no fallback to the
        startup snapshot; no leg is placed on an incomplete or stale book.
      * a post whose outcome is unknown (exception, missing order id,
        unconfirmed cancel) latches the order RECONCILIATION_REQUIRED on
        the gate ledger and is never resubmitted or assumed cancelled.
    """
    from decimal import Decimal
    from core.exchanges.delta.write_authority import token_for_testnet_experiment
    from core.execution.testnet_authorization_gate import OrderLifecycleState
    import httpx
    authority = None
    legs = []
    if placed_records is None:
        placed_records = []
    for n, side in enumerate(("buy", "sell"), 1):
        cl_ord = "QE-%s-R%d" % (exp.CAPTURE_ID, n)
        try:
            b = httpx.get(exp.TESTNET_REST + "/v2/l2orderbook/%s" % exp.SYMBOL,
                          params={"depth": 1}, timeout=20).json().get("result", {})
            live_ask = float(b["sell"][0]["price"])
            live_bid = float(b["buy"][0]["price"])
        except Exception as exc:
            raise RuntimeError(
                "fresh touch read failed before leg %d; refusing to "
                "place on a stale or incomplete book (%s: %s)"
                % (n, type(exc).__name__, exc))
        buy_px, sell_px = exp.derive_maker_leg_prices(
            live_bid, live_ask, exp.TICK)
        px = buy_px if side == "buy" else sell_px
        payload = {"product_id": pid, "order_type": "limit_order",
                   "size": exp.SIZE_CONTRACTS, "side": side,
                   "limit_price": str(px), "time_in_force": "gtc",
                   "post_only": True,
                   "client_order_id": cl_ord}
        if gate is not None:
            decision = gate.check_and_reserve_order(
                auth_record=record,
                rest_url=exp.TESTNET_REST,
                symbol=exp.SYMBOL,
                product_id=pid,
                order_size_contracts=Decimal(exp.SIZE_CONTRACTS),
                cl_ord_id=cl_ord,
                order_details={"side": side, "limit_price": str(px),
                               "post_only": True},
                post_only=True,
                lock_timeout_seconds=5.0,
            )
            if not decision.is_armed():
                raise RuntimeError(
                    "leg %d preflight refused: %s"
                    % (n, "; ".join(decision.reasons)))
            authority = token_for_testnet_experiment(
                decision, base_url=exp.TESTNET_REST, payload=payload)
            gate.register_order_submitted(cl_ord, details={
                "rest_path": "/v2/orders",
                "limit_price": str(px)})
        try:
            resp = rest_client.post("/v2/orders", payload=payload,
                                    authority=authority)
        except Exception:
            if gate is not None:
                gate.register_ack_timeout(cl_ord)
            raise
        oid = str(resp.get("result", resp).get("id", ""))
        if not oid:
            if gate is not None:
                gate.register_ack_timeout(cl_ord)
            raise RuntimeError("no order id for leg %d" % n)
        # Record the exchange ID and the exact per-order authorization
        # immediately after acknowledgement. This survives a later-leg
        # exception so cleanup can target only this experiment's orders.
        placed_records.append({
            "order_id": oid,
            "client_order_id": cl_ord,
            "product_id": int(pid),
            "decision": decision if gate is not None else None,
            "side": side,
            "state": "ACKNOWLEDGED",
        })
        if gate is not None:
            gate.register_order_acknowledged(cl_ord, oid)
        legs.append({"n": n, "side": side, "price": px,
                     "order_id": oid, "client_order_id": cl_ord})
        if not exp._wait_fill(rest_client, oid):
            cancel_authority = token_for_testnet_experiment(
                decision, base_url=exp.TESTNET_REST,
                payload={"id": int(oid), "product_id": pid})
            confirmed = exp._cancel(rest_client, oid, pid,
                                    authority=cancel_authority)
            legs[-1]["filled"] = False
            legs[-1]["cancel_confirmed"] = confirmed
            if gate is not None:
                if confirmed:
                    gate.register_order_terminal(
                        cl_ord, OrderLifecycleState.CANCELLED_CONFIRMED)
                else:
                    gate.register_ack_timeout(cl_ord)
            break
        legs[-1]["filled"] = True
        if gate is not None:
            gate.register_order_terminal(cl_ord,
                                         OrderLifecycleState.FILLED)
    return legs


