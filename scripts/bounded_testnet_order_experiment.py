"""Bounded Testnet-only order experiment (India Demo).

Purpose: manufacture a SMALL number of genuine fills so REST<->WS
reconciliation and fee/funding evidence can be exercised on real data.
This is the ONLY QuantEngine path that submits venue orders, and it runs
ONLY with explicit operator authorization per invocation.

Hard safety bounds (fail closed, no overrides):
  * Testnet hosts only; any other endpoint is refused before any call.
  * Symbol BTCUSD, product BTCUSD (id re-verified live; mismatch aborts).
  * Max 2 placed orders, size 1 contract each, max $100 notional per
    order (aborts above it; mirrors the authorized gate scope).
  * Starts ONLY from a verified-flat account (no BTCUSD position, no open
    orders); ends by cancelling stragglers and re-verifying flat.
  * Limit orders post-only AT the touch (buy at the bid, sell at the
    ask), tick-aligned; unfilled working order is cancelled after
    FILL_WAIT_S (never chased).
  * Every write leg is atomically reserved via the authorization gate
    (check_and_reserve_order) immediately before the transport call;
    ambiguous submissions latch RECONCILIATION_REQUIRED and are never
    resubmitted or assumed cancelled.
  * Any error aborts the sequence; cleanup (cancel + verify flat) still
    attempted and reported.
  * Credentials ONLY from DELTA_INDIA_TESTNET_API_KEY /
    DELTA_INDIA_TESTNET_API_SECRET. Generic/production credential names
    are never consulted. Never printed, logged, or persisted.

Usage:
  python scripts/bounded_testnet_order_experiment.py --dry-run   # plan + pre-checks, zero writes
  python scripts/bounded_testnet_order_experiment.py --execute   # authorized run only

Exit codes: 0 completed (fills or clean no-fill), 2 refused/aborted,
1 unexpected error.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Phase193B/3: ONE authoritative authorization document for the bounded
# experiment family.  The stale Phase 189 reference is superseded; the
# Phase193A template carries the same venue/scope boundaries plus the
# microstructural book-validity requirement, and is the doc of record.
AUTH_DOC_PATH = ROOT / "reports" / "PHASE193A_TESTNET_AUTHORIZATION.md"

TESTNET_REST = "https://cdn-ind.testnet.deltaex.org"
TESTNET_PRIVATE_WS = "wss://socket-ind.testnet.deltaex.org"
SYMBOL = "BTCUSD"
SIZE_CONTRACTS = 1
MAX_ORDERS = 2
# Authorized experiment scope clamps notional to the gate's
# max_order_notional_usd (currently $100); the script-level cap mirrors
# it so a misopened gate cannot loosen the bound.
MAX_NOTIONAL_USD = 100.0
TICK = 0.1
FILL_WAIT_S = 20.0
POLL_S = 2.0

CAPTURE_ID = "exp-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def fail(msg: str) -> int:
    print("EXPERIMENT_REFUSED: %s" % msg)
    return 2


def tick_floor(price: float) -> float:
    return float(int(price / TICK) * TICK)


def tick_ceil(price: float) -> float:
    import math
    return float(math.ceil(price / TICK) * TICK)


def derive_maker_leg_prices(bid: float, ask: float,
                            tick: float) -> tuple[float, float]:
    """Post-only maker leg prices AT the touch: buy at the bid, sell at
    the ask.

    Raises ValueError on crossed, locked, or non-positive book inputs or
    degenerate tick rounding, so callers fail closed instead of placing
    on an insane book.
    """
    if not (bid > 0 and ask > bid):
        raise ValueError("insane touch: crossed or locked book")
    if not (tick and tick > 0):
        raise ValueError("invalid tick")
    buy_px = float(math.floor(bid / tick) * tick)
    sell_px = float(math.ceil(ask / tick) * tick)
    if not (buy_px > 0 and sell_px > 0):
        raise ValueError("degenerate tick rounding")
    return buy_px, sell_px


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true",
                        help="authorized run: actually submit orders")
    parser.add_argument("--dry-run", action="store_true",
                        help="plan + pre-checks only (default)")
    parser.add_argument("--auth-doc", default=str(AUTH_DOC_PATH),
                        help="authorization document of record (default: "
                             "reports/PHASE193A_TESTNET_AUTHORIZATION.md)")
    parser.add_argument("--ledger-path", default=None,
                        help="persistent experiment ledger (tests only; "
                             "default is the repo-wide Phase 189 ledger)")
    parser.add_argument("--output-dir",
                        default="research/captures/phase114_exp")
    args = parser.parse_args(argv)
    execute = bool(args.execute)
    if execute and args.dry_run:
        return fail("pass exactly one of --execute / --dry-run")

    gate = None
    if execute:
        from core.execution.testnet_authorization_gate import TestnetAuthorizationGate
        gate = TestnetAuthorizationGate(
            ledger_path=Path(args.ledger_path) if args.ledger_path else None)
        auth_doc = Path(args.auth_doc)
        try:
            record = gate.parse_authorization_document(auth_doc)
        except Exception as exc:
            return fail(f"Authorization document {auth_doc.name} unreadable: "
                        f"{type(exc).__name__}: {exc}")
        if not record.is_currently_valid():
            return fail(f"Authorization document {auth_doc.name} is not operator-approved: {record.state.value}")

    # Resolve against the independent India Testnet environment authority;
    # do not compare a URL to itself after passing it to the constructor.
    try:
        from research.economics.delta_environment import validate_endpoints
        validate_endpoints("india_testnet", rest_base_url=TESTNET_REST,
                           private_ws_url=TESTNET_PRIVATE_WS)
    except Exception:
        return fail("India Testnet endpoint/environment mismatch")
    key = os.getenv("DELTA_INDIA_TESTNET_API_KEY", "")
    secret = os.getenv("DELTA_INDIA_TESTNET_API_SECRET", "")
    if execute and (not key.strip() or not secret.strip()):
        return fail("dedicated India Testnet credentials required for --execute")

    from core.exchanges.delta.delta_auth import DeltaSignedREST
    rest = DeltaSignedREST(api_key=key.strip(), api_secret=secret.strip(),
                           base_url=TESTNET_REST)
    if rest.base_url.rstrip("/") != TESTNET_REST:
        return fail("constructed endpoint mismatch")

    evidence: dict = {
        "schema": "quantengine.testnet-order-experiment.v1",
        "environment": "india_testnet",
        "symbol": SYMBOL,
        "capture_id": CAPTURE_ID,
        "mode": "execute" if execute else "dry-run",
        "order_placement": "DISABLED" if not execute else "BOUNDED_2x1",
        "steps": [],
        "production_ready": False,
    }

    def step(name: str, **fields):
        evidence["steps"].append({"t": datetime.now(timezone.utc).isoformat(),
                                  "step": name, **fields})
        print("%s %s" % (name, json.dumps(fields, sort_keys=True,
                                          default=str)[:300]))

    def authed_get(path, params=None):
        resp = rest.get(path, params=params)
        if isinstance(resp, dict) and resp.get("success") is False:
            raise RuntimeError("venue unsuccessful response for %s" % path)
        return resp

    # ---- pre-check 1: product identity (live) ----
    try:
        catalog = authed_get("/v2/products")
        rows = catalog.get("result", [])
        match = [r for r in rows if isinstance(r, dict)
                 and r.get("symbol") == SYMBOL]
        if len(match) != 1:
            return fail("BTCUSD product not uniquely listed")
        product = match[0]
        product_id = int(product["id"])
        tick = float(product.get("tick_size", TICK))
        if (product.get("contract_type") != "perpetual_futures"
                or product.get("state") != "live"
                or product.get("trading_status") != "operational"):
            return fail("BTCUSD product not live/operational: %r" % (
                {k: product.get(k) for k in
                 ("contract_type", "state", "trading_status")},))
        step("product_verified", product_id=product_id, tick=tick)
    except Exception as exc:
        step("product_check_failed", error="%s: %s" % (
            type(exc).__name__, exc))
        return fail("cannot verify product identity")

    # ---- pre-check 2: flat account (positions + open orders) ----
    # NOTE (observed): /v2/positions REQUIRES product_id (bare call is
    # bad_schema) and returns a single position OBJECT for the product,
    # not a list. Open orders are likewise product-scoped.
    try:
        presp = authed_get("/v2/positions",
                           params={"product_id": product_id})
        presult = presp.get("result", {})
        records = ([presult] if isinstance(presult, dict)
                   else list(presult or []))
        mine = [r for r in records
                if isinstance(r, dict)
                and abs(float(r.get("size", 0) or 0)) > 0]
        step("positions_checked", btcusd_open=len(mine))
        if mine:
            return fail("account not flat for BTCUSD; resolve first")
        orders = authed_get("/v2/orders", params={"product_id": product_id})
        orecs = orders.get("result", [])
        live_orders = [o for o in (orecs or []) if isinstance(o, dict)
                       and str(o.get("state", "")).lower() in
                       ("open", "pending", "working", "untriggered")]
        step("open_orders_checked", open=len(live_orders))
        if live_orders:
            return fail("open orders exist; resolve first")
    except Exception as exc:
        step("flat_check_failed", error="%s: %s" % (
            type(exc).__name__, exc))
        return fail("cannot verify flat account")

    # ---- pre-check 3: live touch (public L2) ----
    # Phase193B/9+A: the authorized scope REQUIRES post-only legs, and the
    # production leg prices are the touch itself: buy at the bid, sell at
    # the ask (both sides are post-only against an uncrossed book, so no
    # taker match and no market conversion is possible).  Notional sizing
    # uses the venue-verified contract size; an unverifiable contract
    # size fails closed instead of assuming 0.001 BTC.
    try:
        import httpx
        book = httpx.get(
            TESTNET_REST + "/v2/l2orderbook/%s" % SYMBOL,
            params={"depth": 1}, timeout=20).json()
        result = book.get("result", {})
        bid = float(result["buy"][0]["price"])
        ask = float(result["sell"][0]["price"])
        buy_px, sell_px = derive_maker_leg_prices(bid, ask, tick)
        contract_size = float(
            product.get("contract_size")
            or product.get("contract_value") or 0)
        if not contract_size > 0:
            return fail("BTCUSD contract_size unavailable; refusing to "
                        "bound notional")
        notional = SIZE_CONTRACTS * contract_size * ask
        step("touch", bid=bid, ask=ask, buy_px=buy_px, sell_px=sell_px,
             contract_size=contract_size, est_notional=round(notional, 2))
        if notional > MAX_NOTIONAL_USD:
            return fail("notional above hard cap")
        if gate is not None and \
                notional > float(gate.scope.max_order_notional_usd):
            return fail("notional above authorized experiment scope "
                        "%.2f" % float(gate.scope.max_order_notional_usd))
    except Exception as exc:
        step("touch_failed", error="%s: %s" % (type(exc).__name__, exc))
        return fail("cannot read touch")

    plan = [
        {"side": "buy", "price": buy_px},
        {"side": "sell", "price": sell_px},
    ]
    evidence["plan"] = {
        "max_orders": MAX_ORDERS, "size_contracts": SIZE_CONTRACTS,
        "legs": plan,
    }
    if not execute:
        step("dry_run_complete", note="no writes performed; re-run with "
                                      "--execute only when authorized")
        _write(args.output_dir, evidence)
        return 0

    # ---- execute (authorized only) ----
    # Phase193B/2-3+A: every exchange write is additionally authorization-
    # gated AT the transport (DeltaSignedREST) against a gate-minted
    # token bound to this experiment's REST endpoint, AND each write leg
    # is atomically reserved via the gate (check_and_reserve_order)
    # immediately before its transport call — a pending, malformed,
    # stale, out-of-scope, budget-exhausted, or single-open-order
    # condition reaches here as ZERO transport writes for that leg (and
    # the loop stops fail-closed).  A post whose outcome is unknown
    # (exception, missing order id, unconfirmed cancel) latches the
    # order RECONCILIATION_REQUIRED on the gate ledger and is NEVER
    # resubmitted or assumed cancelled.
    placed: list = []
    authority = None
    decision = None
    try:
        from core.exchanges.delta.write_authority import token_for_testnet_experiment
        from core.execution.testnet_authorization_gate import OrderLifecycleState
        for n, leg in enumerate(plan[:MAX_ORDERS], 1):
            cl_ord = "QE-%s-%d" % (CAPTURE_ID, n)
            if gate is not None:
                decision = gate.check_and_reserve_order(
                    auth_record=record,
                    rest_url=TESTNET_REST,
                    symbol=SYMBOL,
                    product_id=product_id,
                    order_size_contracts=Decimal(SIZE_CONTRACTS),
                    cl_ord_id=cl_ord,
                    order_details={"side": leg["side"],
                                   "limit_price": str(leg["price"]),
                                   "post_only": True},
                    post_only=True,
                    lock_timeout_seconds=5.0,
                )
                if not decision.is_armed():
                    step("leg_preflight_refused", leg=n,
                         reasons=decision.reasons)
                    break  # fail closed: this and later legs write nothing
            payload = {
                "product_id": product_id,
                "order_type": "limit_order",
                "size": SIZE_CONTRACTS,
                "side": leg["side"],
                "limit_price": str(leg["price"]),
                "time_in_force": "gtc",
                "post_only": True,
                "client_order_id": cl_ord,
            }
            if gate is not None:
                authority = token_for_testnet_experiment(
                    decision, base_url=TESTNET_REST, payload=payload)
            if gate is not None:
                # Submission attempt is registered BEFORE the transport
                # call: from here on an exception cannot produce a blind
                # resubmission (the reservation stays held).
                gate.register_order_submitted(cl_ord, details={
                    "rest_path": "/v2/orders",
                    "limit_price": str(leg["price"])})
            try:
                resp = rest.post("/v2/orders", payload=payload,
                                 authority=authority)
            except Exception:
                # The submission may or may not have reached the venue;
                # the state must remain ambiguous until reconciliation.
                if gate is not None:
                    gate.register_ack_timeout(cl_ord)
                raise
            result = resp.get("result", resp)
            oid = str(result.get("id", ""))
            step("order_placed", leg=n, side=leg["side"],
                 order_id=oid, state=result.get("state"))
            if not oid:
                # Submitted with no authoritative id: ambiguous, never
                # resubmit.
                if gate is not None:
                    gate.register_ack_timeout(cl_ord)
                raise RuntimeError("venue returned no order id")
            placed.append(oid)
            filled = _wait_fill(rest, oid)
            step("fill_wait_done", leg=n, order_id=oid, filled=filled)
            if filled:
                if gate is not None:
                    gate.register_order_terminal(
                        cl_ord, OrderLifecycleState.FILLED)
            else:
                cancel_authority = token_for_testnet_experiment(
                    decision, base_url=TESTNET_REST,
                    payload={"id": int(oid), "product_id": product_id})
                cancelled = _cancel(rest, oid, product_id,
                                    authority=cancel_authority)
                step("stale_leg_cancelled", leg=n, order_id=oid,
                     confirmed=cancelled)
                if gate is not None:
                    if cancelled:
                        gate.register_order_terminal(
                            cl_ord,
                            OrderLifecycleState.CANCELLED_CONFIRMED)
                    else:
                        # Cancel unconfirmed: the order may still be
                        # live; keep holding the risk/quota reservation.
                        gate.register_ack_timeout(cl_ord)
                        step("stale_leg_cancel_unconfirmed", leg=n,
                             order_id=oid)
                break
    except Exception as exc:
        step("sequence_aborted", error="%s: %s" % (
            type(exc).__name__, exc))
        # The armed authority (if any) survives for the cleanup path:
        # cancelling self-placed stragglers is the reviewed emergency
        # reduction within the same authorization.  Refused preflights
        # raise before any token exists, so cleanup writes nothing.
    finally:
        cleanup = _cleanup(rest, product_id, placed, decision=decision)
        step("cleanup", **cleanup)
        fills = _recent_fills(rest)
        evidence["fills_observed"] = fills
        step("fills_observed", count=len(fills))
    _write(args.output_dir, evidence)
    return 0


def _wait_fill(rest, order_id: str) -> bool:
    deadline = time.monotonic() + FILL_WAIT_S
    while time.monotonic() < deadline:
        try:
            resp = rest.get("/v2/orders/%s" % order_id)
            result = resp.get("result", resp)
            state = str(result.get("state", "")).lower()
            if state in ("filled", "closed"):
                return True
            if state in ("cancelled", "rejected", "expired"):
                return False
        except Exception:
            pass
        time.sleep(POLL_S)
    return False


def _cancel(rest, order_id: str, product_id: int,
            authority=None) -> bool:
    """Cancel one order via the venue-verified shape and VERIFY it.

    Returns True only when the order is confirmed non-working
    (cancelled/expired/closed/filled). Never raises; a False return
    means the order may STILL be live and must be reported, never
    assumed gone (the Phase-120 straggler was a swallowed 404).
    """
    try:
        rest.delete("/v2/orders",
                    payload={"id": int(order_id), "product_id": product_id},
                    authority=authority)
    except Exception:
        pass
    try:
        resp = rest.get("/v2/orders/%s" % order_id)
        state = str(resp.get("result", resp).get("state", "")).lower()
        return state in ("cancelled", "expired", "closed", "filled",
                         "rejected")
    except Exception:
        return False


def _cleanup(rest, product_id: int, placed: list, authority=None,
             decision=None) -> dict:
    """Cancel only acknowledged experiment-owned orders.

    ``placed`` must contain per-order records with exchange order ID,
    client_order_id, product_id and that order's armed decision. Bare IDs
    are intentionally insufficient: after a crash/restart they must be
    recovered from the durable authorization ledger and reconciled first.
    A fresh REST detail read must confirm the client ID and product before
    a cancellation write is authorized. Unknown ownership fails closed.
    """
    out: dict = {"cancelled": [], "positions_flat": None,
                 "open_orders": None, "ownership_unverified": [],
                 "cancel_authority_missing": [], "cancel_unconfirmed": []}
    owned = {}
    for item in placed or []:
        if not isinstance(item, dict):
            continue
        oid = str(item.get("order_id", "")).strip()
        clid = str(item.get("client_order_id", "")).strip()
        try:
            pid = int(item.get("product_id"))
        except (TypeError, ValueError):
            continue
        if oid and clid and pid == int(product_id):
            owned[oid] = item
    try:
        resp = rest.get("/v2/orders", params={"product_id": product_id})
        for o in resp.get("result", []) or []:
            if not isinstance(o, dict):
                continue
            if str(o.get("state", "")).lower() not in (
                    "open", "pending", "working", "untriggered"):
                continue
            oid = str(o.get("id", "")).strip()
            owner = owned.get(oid)
            if owner is None:
                out.setdefault("preexisting_orders_not_touched", []).append(oid)
                continue
            # Never trust the list row alone for ownership; verify the
            # canonical detail endpoint before issuing DELETE.
            try:
                detail_resp = rest.get("/v2/orders/%s" % oid)
                detail = detail_resp.get("result", detail_resp)
                detail_id = str(detail.get("id", "")).strip()
                detail_pid = int(detail.get("product_id"))
                detail_clid = str(detail.get("client_order_id", "")).strip()
            except Exception:
                out["ownership_unverified"].append(oid)
                continue
            if (detail_id != oid or detail_pid != int(product_id)
                    or detail_clid != owner["client_order_id"]):
                out["ownership_unverified"].append(oid)
                continue
            cancel_authority = None
            owner_decision = owner.get("decision")
            if owner_decision is not None:
                try:
                    from core.exchanges.delta.write_authority import token_for_testnet_experiment
                    cancel_authority = token_for_testnet_experiment(
                        owner_decision,
                        base_url=getattr(rest, "base_url", TESTNET_REST),
                        payload={"id": int(oid), "product_id": int(product_id)},
                        method="DELETE")
                except Exception:
                    cancel_authority = None
            elif authority is not None:
                # A caller-supplied token is allowed only when it is
                # already explicitly scoped to this exact cancellation.
                cancel_authority = authority
            if cancel_authority is None:
                out["cancel_authority_missing"].append(oid)
                continue
            if _cancel(rest, oid, int(product_id), authority=cancel_authority):
                out["cancelled"].append(oid)
            else:
                out["cancel_unconfirmed"].append(oid)
        try:
            recheck = rest.get("/v2/orders",
                               params={"product_id": product_id})
            out["open_orders"] = len([
                o for o in recheck.get("result", []) or []
                if isinstance(o, dict) and str(
                    o.get("state", "")).lower() in (
                        "open", "pending", "working", "untriggered")])
        except Exception as exc:
            out["open_orders"] = "unknown: %s" % type(exc).__name__
    except Exception as exc:
        out["open_orders"] = "unknown: %s" % type(exc).__name__
    try:
        presp = rest.get("/v2/positions",
                         params={"product_id": product_id})
        pres = presp.get("result", {})
        recs = [pres] if isinstance(pres, dict) else list(pres or [])
        out["positions_flat"] = all(
            abs(float(r.get("size", 0) or 0)) == 0
            for r in recs if isinstance(r, dict))
    except Exception as exc:
        out["positions_flat"] = "unknown: %s" % type(exc).__name__
    return out


def _recent_fills(rest) -> list:
    try:
        resp = rest.get("/v2/fills", params={"page_size": 20})
        rows = resp.get("result", []) or []
        return [{"fill_id": str(r.get("id", "")),
                 "symbol": str(r.get("product_symbol",
                                     r.get("symbol", ""))),
                 "side": str(r.get("side", "")),
                 "size": str(r.get("size", "")),
                 "price": str(r.get("price", ""))}
                for r in rows if isinstance(r, dict)]
    except Exception as exc:
        return [{"error": "%s" % type(exc).__name__}]


def _write(output_dir: str, evidence: dict) -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    blob = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
    evidence["evidence_sha256"] = hashlib.sha256(blob.encode()).hexdigest()
    blob = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
    (out / "order_experiment_report.json").write_text(blob, encoding="utf-8")
    print("report_path=%s" % (out / "order_experiment_report.json"))


if __name__ == "__main__":
    from dotenv import load_dotenv
    for p in (ROOT / ".env", ROOT.parent / ".env"):
        if p.exists():
            load_dotenv(str(p), override=True)
            break
    raise SystemExit(main())
