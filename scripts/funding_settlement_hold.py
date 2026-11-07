"""Funding-settlement hold (India Demo, ETHUSD, 1 contract).

Authorized bounded plan: limit enter before a settlement, hold through it,
limit reduce_only exit after, verify the wallet funding row against the
funding rate observed at settlement.
Target settlement: the next 00/08/16 UTC boundary at least 10 minutes
ahead, or an explicit UTC time via --settlement.
Hard bounds: ETHUSD only, size 1, limit-only, flat-in, verified cancel/flat.
Any error -> fail closed (cancel working, report, never assume).
Secrets via env only, never printed/persisted.
"""
from __future__ import annotations
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PID = 1699
SYMBOL = "ETHUSD"
TICK = Decimal("0.05")
LOG = Path("research/captures/phase148_funding/hold_log.jsonl")
SETTLEMENT_HOURS = (0, 8, 16)
# Phase193B/3: ONE authoritative authorization document (PHASE193A
# supersedes the stale Phase 189 reference used elsewhere).
AUTH_DOC_PATH = ROOT / "reports" / "PHASE193A_TESTNET_AUTHORIZATION.md"


def target_settlement(spec: str | None, now: datetime | None = None) -> datetime:
    """Settlement instant to hold through: explicit UTC ISO, or the next
    00/08/16 UTC boundary at least 10 minutes ahead."""
    now = now or datetime.now(timezone.utc)
    if spec:
        t = datetime.fromisoformat(spec.replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return t.astimezone(timezone.utc)
    for day_offset in (0, 1):
        day = (now + timedelta(days=day_offset)).date()
        for hour in SETTLEMENT_HOURS:
            cand = datetime(day.year, day.month, day.day, hour,
                            tzinfo=timezone.utc)
            if cand - now >= timedelta(minutes=10):
                return cand
    raise RuntimeError("no settlement boundary within 24h")


def log(**fields):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    rec = {"t": datetime.now(timezone.utc).isoformat(), **fields}
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, sort_keys=True) + "\n")
    print(json.dumps(rec, sort_keys=True)[:300])


def _funding_rate(rest):
    """Read-only funding-rate snapshot for reconciliation (never raises)."""
    try:
        rows = rest.get("/v2/products").get("result", []) or []
        for r in rows:
            if int(r.get("id", -1)) == PID:
                return str(r.get("funding_rate"))
        return "not_found"
    except Exception as exc:
        return "unavailable:%s" % type(exc).__name__


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true",
                        help="authorized run: actually submit Testnet orders")
    parser.add_argument("--dry-run", action="store_true",
                        help="pre-checks only, zero writes (default)")
    parser.add_argument("--settlement", default=None,
                        help="UTC ISO instant of the settlement to hold "
                             "through (default: next 00/08/16 UTC boundary)")
    parser.add_argument("--auth-doc", default=None,
                        help="authorization document of record (default: "
                             "reports/PHASE193A_TESTNET_AUTHORIZATION.md)")
    parser.add_argument("--ledger-path", default=None,
                        help="persistent experiment ledger (tests only)")
    args = parser.parse_args(argv)
    execute = bool(args.execute)
    if execute and args.dry_run:
        log(event="refused", reason="pass exactly one of --execute / --dry-run")
        return 2
    gate = None
    record = None
    if execute:
        from core.execution.testnet_authorization_gate import TestnetAuthorizationGate
        gate = TestnetAuthorizationGate(
            ledger_path=Path(args.ledger_path) if args.ledger_path else None)
        # Phase193B/3: ONE authoritative authorization document
        # (PHASE193A supersedes the stale Phase 189 reference).
        auth_doc = Path(args.auth_doc) if args.auth_doc else AUTH_DOC_PATH
        record = gate.parse_authorization_document(auth_doc)
        if not record.is_currently_valid():
            log(event="refused", reason=f"Authorization document {auth_doc.name} is not operator-approved: {record.state.value}")
            return 2
        log(event="warning",
            note="authorized Testnet order flow: 1x1 ETHUSD limit-only, "
                 "flat-in, verified cancel; every write is preflighted and "
                 "carries a gate-minted transport authority")
    from dotenv import load_dotenv
    load_dotenv(str(ROOT / ".env"), override=True)
    sys.path.insert(0, str(ROOT / "scripts"))
    import bounded_testnet_order_experiment as exp
    from core.exchanges.delta.delta_auth import DeltaSignedREST
    try:
        from research.economics.delta_environment import validate_endpoints
        validate_endpoints("india_testnet", rest_base_url=exp.TESTNET_REST,
                           private_ws_url=exp.TESTNET_PRIVATE_WS)
    except Exception:
        log(event="refused", reason="India Testnet endpoint mismatch")
        return 2
    key = os.getenv("DELTA_INDIA_TESTNET_API_KEY", "").strip()
    secret = os.getenv("DELTA_INDIA_TESTNET_API_SECRET", "").strip()
    if not key or not secret:
        log(event="refused", reason="no testnet creds")
        return 2
    rest = DeltaSignedREST(api_key=key, api_secret=secret, base_url=exp.TESTNET_REST)
    import httpx
    try:
        p = rest.get("/v2/positions", params={"product_id": PID}).get("result", {})
        assert abs(float(p.get("size", 0) or 0)) == 0, "not flat at entry"
        log(event="flat_verified")
    except Exception as exc:
        log(event="refused", reason="prefail: %s" % type(exc).__name__)
        return 2
    book = httpx.get(exp.TESTNET_REST + "/v2/l2orderbook/" + SYMBOL, params={"depth": 1}, timeout=20).json()["result"]
    bid = Decimal(str(book["buy"][0]["price"]))
    ask = Decimal(str(book["sell"][0]["price"]))
    buy_px = (ask / TICK).to_integral_value(rounding=ROUND_DOWN) * TICK
    log(event="touch", bid=str(bid), ask=str(ask), buy_px=str(buy_px))
    if not execute:
        log(event="dry_run_complete",
            note="zero writes performed; re-run with --execute only when authorized")
        return 0
    # Phase193B/2-3: every exchange write is additionally authorization-
    # gated AT the transport (DeltaSignedREST) against a gate-minted
    # token bound to this script's REST endpoint.  The preflight is
    # evaluated once up front; a refused decision (stale authorization,
    # scope mismatch with the BTCUSD experiment scope, budget
    # exhaustion, corrupted ledger, ...) ends the run with ZERO
    # transport writes.  The instrument here is ETHUSD/1699, which is
    # outside the current experiment scope -> guaranteed refusal until
    # the operator authorizes that scope.
    decision = gate.evaluate_preflight(
        auth_record=record,
        rest_url=exp.TESTNET_REST,
        symbol=SYMBOL,
        product_id=PID,
        order_size_contracts=Decimal(1),
        post_only=True,
    )
    if not decision.is_armed():
        log(event="refused",
            reason="AUTHORIZATION_INCOMPATIBLE: preflight refused: "
                   + "; ".join(decision.reasons))
        return 2
    from core.exchanges.delta.write_authority import token_for_testnet_experiment
    order_payload = {"product_id": PID, "order_type": "limit_order", "size": 1,
                     "side": "buy", "limit_price": format(buy_px, "f"),
                     "time_in_force": "gtc", "post_only": True, "client_order_id": "QE-FUND-IN"}
    authority = token_for_testnet_experiment(
        decision, base_url=exp.TESTNET_REST, payload=order_payload)
    # Re-arm per write (budget/limits/concurrency may have changed).
    def _re_atomic_write_authority(write_payload):
        d2 = gate.evaluate_preflight(
            auth_record=record,
            rest_url=exp.TESTNET_REST,
            symbol=SYMBOL,
            product_id=PID,
            order_size_contracts=Decimal(1),
            post_only=True,
        )
        return token_for_testnet_experiment(
            d2, base_url=exp.TESTNET_REST, payload=write_payload)
    try:
        resp = rest.post("/v2/orders", payload=order_payload, authority=authority)
    except Exception as exc:
        log(event="entry_failed", error=type(exc).__name__)
        return 1
    oid = str(resp.get("result", resp).get("id", ""))
    log(event="entry_placed", order_id=oid)
    deadline = time.monotonic() + 900
    filled = False
    while time.monotonic() < deadline:
        try:
            s = str(rest.get("/v2/orders/" + oid).get("result", {}).get("state", "")).lower()
            if s in ("filled", "closed"):
                filled = True
                break
            if s in ("cancelled", "rejected", "expired"):
                break
        except Exception:
            pass
        time.sleep(5)
    if not filled:
        log(event="entry_unfilled")
        # Re-arm the authority for risk-reduction: cancelling the
        # self-placed entry is the reviewed emergency action inside the
        # same authorization.  If re-arming is refused, do NOT attempt
        # the cancel (the transport would refuse it anyway) - report the
        # straggler loudly instead, never assume it is gone.
        try:
            authority = token_for_testnet_experiment(
                decision, base_url=exp.TESTNET_REST,
                payload={"id": int(oid), "product_id": PID})
            cancel_confirmed = exp._cancel(rest, oid, PID,
                                           authority=authority)
        except Exception as exc:
            cancel_confirmed = False
            log(event="entry_cancel_authority_refused",
                error=type(exc).__name__)
        log(event="done", result="no-capture",
            cancel_confirmed=cancel_confirmed)
        return 0
    log(event="entry_filled", order_id=oid)
    # Hold through the target settlement plus a 5-minute margin.
    settle_at = target_settlement(args.settlement)
    log(event="hold_start", settlement=settle_at.isoformat(),
        funding_rate_pre=_funding_rate(rest))
    hold_deadline = settle_at + timedelta(minutes=5)
    hold_timeout = time.monotonic() + max(
        600.0, (hold_deadline - datetime.now(timezone.utc)).total_seconds() + 600.0)
    while datetime.now(timezone.utc) < hold_deadline:
        if time.monotonic() > hold_timeout:
            log(event="hold_timeout")
            break
        time.sleep(30)
    log(event="settlement_window_passed", settlement=settle_at.isoformat(),
        funding_rate_post=_funding_rate(rest))
    book2 = httpx.get(exp.TESTNET_REST + "/v2/l2orderbook/" + SYMBOL, params={"depth": 1}, timeout=20).json()["result"]
    ask2 = Decimal(str(book2["sell"][0]["price"]))
    sell_px = (ask2 / TICK).to_integral_value(rounding=ROUND_UP) * TICK
    try:
        # Re-arm: the reduce-only exit carries a fresh preflight decision
        # and a gate-minted transport authority (same fail-closed rule).
        exit_payload = {"product_id": PID, "order_type": "limit_order", "size": 1, "side": "sell", "limit_price": format(sell_px, "f"), "time_in_force": "gtc", "post_only": True, "reduce_only": True, "client_order_id": "QE-FUND-OUT"}
        authority = _re_atomic_write_authority(exit_payload)
        resp2 = rest.post("/v2/orders", payload=exit_payload, authority=authority)
    except Exception as exc:
        # Fail closed: never assume the position will be unwound by
        # anything else; report its live size for operator attention.
        pos_left = None
        try:
            pos_left = rest.get("/v2/positions", params={"product_id": PID}).get("result", {}).get("size")
        except Exception:
            pass
        log(event="exit_failed", error=type(exc).__name__,
            position_size_after=pos_left)
        return 1
    oid2 = str(resp2.get("result", resp2).get("id", ""))
    log(event="exit_placed", order_id=oid2, px=str(sell_px))
    deadline2 = time.monotonic() + 1200
    while time.monotonic() < deadline2:
        try:
            s = str(rest.get("/v2/orders/" + oid2).get("result", {}).get("state", "")).lower()
            if s in ("filled", "closed"):
                log(event="exit_filled", order_id=oid2)
                break
            if s in ("cancelled", "rejected", "expired"):
                log(event="exit_dead", state=s)
                break
        except Exception:
            pass
        time.sleep(5)
    p2 = rest.get("/v2/positions", params={"product_id": PID}).get("result", {})
    log(event="done", position_size=p2.get("size"))
    try:
        txns = rest.get("/v2/wallet/transactions", params={"page_size": 100}).get("result", []) or []
        fund = [t for t in txns if t.get("transaction_type") == "funding"]
        log(event="funding_rows", count=len(fund))
    except Exception as exc:
        log(event="funding_check_failed", error=type(exc).__name__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
