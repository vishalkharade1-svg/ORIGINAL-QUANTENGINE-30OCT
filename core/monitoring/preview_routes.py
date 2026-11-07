"""
====================================================

QuantEngine

Paper-preview read-only routes (EXTEND, never duplicate)

Additional GET routes for the local paper preview, merged into
ControlApiServer via the extra_routes seam. Every route is
read-only and serves JSON (plus one static HTML dashboard page);
no route creates, mutates, or cancels anything, and none can
reach the live executor. Authentication stays the server's
bearer-token gate; binding stays 127.0.0.1.

Routes (all GET):

    /preview    static preview identity + provenance labels
                (PAPER_ONLY, data source, symbol, timeframe).
    /candles    recent closed candles per symbol (oldest-first)
                from the preview transport ring buffer, with
                per-symbol poll/delivery stats.
    /evidence   aggregate over EXISTING authorities only:
                broker placed intents, ledger open/closed trades,
                account state, reconciler halt flags, latest
                DecisionEngine rejections, engine route counters.
                No new evidence system; labels are LOCAL/PAPER,
                never exchange/live.
    /dashboard  the static read-only browser dashboard (HTML).

Provenance contract: every payload carries explicit source
labels (OBSERVED / PAPER-MODELLED / UNAVAILABLE) so the
browser can never mistake paper state for venue truth.

====================================================
"""

from __future__ import annotations


PREVIEW_MODE = "PAPER_ONLY"
DATA_SOURCE = "DELTA_PUBLIC_REST_CLOSED_CANDLES"
LIVE_EXECUTION = False


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _runtimes(engine):
    runtimes = getattr(engine, "runtimes", None) or {}
    if isinstance(runtimes, dict):
        return runtimes
    return {}


def _broker_of(runtime):
    return getattr(runtime, "engine", None)


def _world_engines(runtime):
    """InstitutionalPipeline engines for one runtime (best effort)."""
    try:
        pipeline = getattr(runtime, "pipeline", None)
        world = getattr(pipeline, "world", pipeline)
        engines = getattr(world, "engines", None) or []
        return list(engines)
    except Exception:  # noqa: BLE001 (observability only)
        return []


def _decision_rejections(runtime, limit=25):
    """Latest-candle rejections with actual reasons.

    DecisionEngine clears per analyze(), so this is the most
    recent evaluation — labeled as such, never a full history.
    """
    out = []
    for eng in _world_engines(runtime):
        if type(eng).__name__ != "DecisionEngine":
            continue
        for rejection in list(getattr(eng, "rejected", None) or []):
            candidate = getattr(rejection, "candidate", None)
            out.append({
                "direction": str(
                    getattr(rejection, "direction", "") or ""),
                "reasons": [str(r) for r in (
                    getattr(rejection, "reasons", None) or [])],
                "entry": _safe_float(
                    getattr(candidate, "entry", 0.0)),
                "stop_loss": _safe_float(
                    getattr(candidate, "stop_loss", 0.0)),
                "take_profit": _safe_float(
                    getattr(candidate, "take_profit", 0.0)),
                "risk_reward": _safe_float(
                    getattr(candidate, "risk_reward", 0.0)),
                "confidence": _safe_float(
                    getattr(candidate, "confidence", 0.0)),
            })
            if len(out) >= limit:
                return out
    return out


def _trade_view(trade):
    return {
        "direction": str(getattr(trade, "direction", "") or ""),
        "entry": _safe_float(getattr(trade, "entry", 0.0)),
        "stop_loss": _safe_float(
            getattr(trade, "stop_loss", 0.0)),
        "take_profit": _safe_float(
            getattr(trade, "take_profit", 0.0)),
        "quantity": _safe_float(getattr(trade, "quantity", 0.0)),
        "exit_price": _safe_float(
            getattr(trade, "exit_price", 0.0)),
        "commission": _safe_float(
            getattr(trade, "commission", 0.0)),
        "slippage": _safe_float(
            getattr(trade, "slippage", 0.0)),
        "pnl": _safe_float(getattr(trade, "pnl", 0.0)),
        "result": str(getattr(trade, "result", "") or ""),
        "status": str(getattr(trade, "status", "") or ""),
        "setup_id": str(getattr(trade, "setup_id", "") or ""),
        "order_id": str(getattr(trade, "order_id", "") or ""),
        "entry_time": getattr(trade, "entry_time", None),
        "exit_time": getattr(trade, "exit_time", None),
    }


def _intent_view(intent):
    return {
        "direction": str(getattr(intent, "direction", "") or ""),
        "entry": _safe_float(getattr(intent, "entry", 0.0)),
        "stop_loss": _safe_float(
            getattr(intent, "stop_loss", 0.0)),
        "take_profit": _safe_float(
            getattr(intent, "take_profit", 0.0)),
        "quantity": _safe_float(getattr(intent, "quantity", 0.0)),
        "risk_reward": _safe_float(
            getattr(intent, "risk_reward", 0.0)),
        "actual_risk_reward": _safe_float(
            getattr(intent, "actual_risk_reward", 0.0)),
        "commission": _safe_float(
            getattr(intent, "commission", 0.0)),
        "slippage": _safe_float(
            getattr(intent, "slippage", 0.0)),
        "confidence": _safe_float(
            getattr(intent, "confidence", 0.0)),
        "symbol": str(getattr(intent, "symbol", "") or ""),
        "setup_id": str(getattr(intent, "setup_id", "") or ""),
        "order_id": str(getattr(intent, "order_id", "") or ""),
        "status": str(getattr(intent, "status", "") or ""),
        "kind": "PAPER",
    }


def preview_routes(engine, transport):
    """Build {(method, path): handler} for the preview API."""

    def preview_meta():
        symbols = []
        try:
            runtimes = _runtimes(engine)
            symbols = sorted({
                str(getattr(rt, "symbol", "") or "")
                for rt in runtimes.values()} - {""})
        except Exception:  # noqa: BLE001 (observability only)
            symbols = []
        return {
            "mode": PREVIEW_MODE,
            "data_source": DATA_SOURCE,
            "live_execution": LIVE_EXECUTION,
            "is_production_ready": False,
            "symbols": symbols,
            "timeframe": str(
                getattr(engine, "timeframe", "") or ""),
            "provenance": {
                "market_data": "OBSERVED",
                "fills": "PAPER-MODELLED",
                "account": "PAPER-MODELLED",
                "evidence": "LOCAL",
            },
        }

    def candles_snapshot():
        out = {}
        try:
            stats = transport.stats()
        except Exception:  # noqa: BLE001 (observability only)
            stats = {}
        for name in sorted(stats.keys()):
            try:
                bars = transport.recent_closed(name, limit=120)
            except Exception:  # noqa: BLE001 (observability only)
                bars = []
            out[name] = {
                "candles": [{
                    "timestamp": int(getattr(bar, "timestamp", 0)
                                     or 0),
                    "open": _safe_float(getattr(bar, "open", 0.0)),
                    "high": _safe_float(getattr(bar, "high", 0.0)),
                    "low": _safe_float(getattr(bar, "low", 0.0)),
                    "close": _safe_float(
                        getattr(bar, "close", 0.0)),
                    "volume": _safe_float(
                        getattr(bar, "volume", 0.0)),
                    "closed": True,
                    "provenance": "OBSERVED",
                } for bar in bars],
                "transport": stats.get(name, {}),
            }
        return out

    def evidence_snapshot():
        per_symbol = {}
        totals = {"intents": 0, "open_trades": 0,
                  "closed_trades": 0, "rejections": 0,
                  "net_pnl": 0.0}
        halts = []
        for key, runtime in _runtimes(engine).items():
            symbol = (str(getattr(runtime, "symbol", "") or "")
                      or str(key))
            broker = _broker_of(runtime)
            intents = []
            open_trades = []
            closed_trades = []
            net = 0.0
            halted = False
            halt_reason = ""
            if broker is not None:
                try:
                    intents = [_intent_view(i) for i in
                               list(getattr(broker, "placed", None)
                                    or []) if not isinstance(i, dict)]
                except Exception:  # noqa: BLE001
                    intents = []
                try:
                    registry = getattr(broker, "registry", None)
                    all_trades = (list(registry.all())
                                  if registry is not None
                                  and hasattr(registry, "all")
                                  else [])
                except Exception:  # noqa: BLE001
                    all_trades = []
                for trade in all_trades:
                    view = _trade_view(trade)
                    status = str(
                        getattr(trade, "status", "") or "")
                    if status == "CLOSED":
                        closed_trades.append(view)
                        net += view["pnl"]
                    else:
                        open_trades.append(view)
                try:
                    reconciler = getattr(broker, "reconciler",
                                         None)
                    halted = bool(getattr(reconciler,
                                          "halt_new_orders", False))
                    halt_reason = str(getattr(reconciler,
                                              "halt_reason", "")
                                      or "")
                except Exception:  # noqa: BLE001
                    halted = False
            rejections = []
            try:
                rejections = _decision_rejections(runtime)
            except Exception:  # noqa: BLE001
                rejections = []
            if halted:
                halts.append({"symbol": symbol,
                              "reason": halt_reason})
            totals["intents"] += len(intents)
            totals["open_trades"] += len(open_trades)
            totals["closed_trades"] += len(closed_trades)
            totals["rejections"] += len(rejections)
            totals["net_pnl"] += net
            per_symbol[symbol] = {
                "intents": intents[-25:],
                "open_trades": open_trades,
                "closed_trades": closed_trades[-50:],
                "rejections": rejections,
                "reconciler_halted": halted,
                "reconciler_reason": halt_reason,
                "provenance": "PAPER-MODELLED",
            }
        return {
            "totals": totals,
            "halts": halts,
            "per_symbol": per_symbol,
            "reconciliation": "LOCAL",
            "engine_routed": int(
                getattr(engine, "routed", 0) or 0),
            "engine_unrouted": int(
                getattr(engine, "unrouted", 0) or 0),
            "route_errors": int(
                getattr(engine, "route_errors", 0) or 0),
        }

    def dashboard_page():
        from pathlib import Path

        path = (Path(__file__).resolve().parent
                / "dashboard.html")
        try:
            return {"__html__": path.read_text(encoding="utf-8")}
        except OSError:
            return {"__html__": "<html><body>dashboard "
                                "UNAVAILABLE</body></html>"}

    return {
        ("GET", "/preview"): lambda: preview_meta(),
        ("GET", "/candles"): candles_snapshot,
        ("GET", "/evidence"): lambda: evidence_snapshot(),
        ("GET", "/dashboard"): dashboard_page,
    }
