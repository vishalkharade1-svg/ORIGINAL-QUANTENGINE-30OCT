"""
====================================================

QuantEngine

Lightweight Desktop Control Client - controller

Phase 9P-h.

Pure presentation/control logic with NO GUI and NO engine
imports. It consumes CycleResult snapshots (the poller's
mirror of the Control API read endpoints) and renders them as
display-friendly rows for the UI to show. It also owns the
ONLY write action the client may take: the four allowlisted
lifecycle commands via the existing POST /control contract.

Critical rules:
  * The client never computes strategy/risk/position/order/
    performance numbers -- it renders server results verbatim.
  * The only POST allowed is /control with the allowlisted
    command body. It conveys operator intent to the runtime; it
    never constructs orders, never touches an exchange, and
    never changes strategy/risk parameters.
  * Formatting here is cosmetic only; unavailable fields render
    as "Unavailable", never as fabricated values.

Stdlib only: time, dataclasses.
====================================================
"""

import time

from core.client.http_client import ClientError

CONTROL_COMMANDS = ("start", "stop", "restart", "emergency_stop")


def _fmt_ts(value):
    if value in (None, ""):
        return "Unavailable"
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(float(value)))
    except (TypeError, ValueError, OSError):
        return "Unavailable"


def _label(value, default="Unavailable"):
    if value is None:
        return default
    text = str(value)
    return text if text.strip() else default


def _maybe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class ControlPath:
    """The single write path: POST /control {"command": ...}.

    Matches core.monitoring.api_server exactly (allowlisted
    PAPER-only verbs). Raises ClientError subclasses on failure.
    """

    def __init__(self, api):
        self.api = api

    def start(self):
        return self._send("start")

    def stop(self):
        return self._send("stop")

    def restart(self):
        return self._send("restart")

    def emergency_stop(self):
        return self._send("emergency_stop")

    def _send(self, command):
        if command not in CONTROL_COMMANDS:
            raise ClientError("unsupported command: %s" % command)
        return self.api.post("/control", {"command": command})


def _health_rows(payload):
    if not isinstance(payload, dict):
        return []
    return [
        ("Lifecycle", _label(payload.get("lifecycle_state"))),
        ("Engine started", _label(payload.get("started"))),
        ("PAPER / exchange", _label(payload.get("exchange"))),
        ("Timeframe", _label(payload.get("timeframe"))),
        ("Runtimes", _label(payload.get("runtimes"))),
        ("Uptime (s)", _label(payload.get("uptime"))),
    ]


def render_dashboard(cycle):
    """Dashboard summary rows from a CycleResult (or None data)."""

    rows = []
    health = cycle.data("health") if cycle is not None else None
    runtimes = cycle.data("runtimes") if cycle is not None else None
    universe = cycle.data("universe") if cycle is not None else None
    errors = cycle.data("errors") if cycle is not None else None

    if health is not None:
        rows.extend(_health_rows(health))
    else:
        rows.append(("Lifecycle", "Unavailable"))

    if universe is not None:
        rows.append(("Eligible symbols", _label(universe.get("eligible_count"))))
        rows.append(("Universe mode", _label(universe.get("mode"))))
    else:
        rows.append(("Eligible symbols", "Unavailable"))

    if runtimes is not None and isinstance(runtimes, dict):
        rows.append(("Runtime count", _label(len(runtimes))))
    else:
        rows.append(("Runtime count", "Unavailable"))

    error_count = 0
    if errors is not None and isinstance(errors, dict):
        error_count = len(errors.get("errors") or [])
    rows.append(("Errors", _label(error_count)))

    return rows


def render_universe(cycle):
    universe = cycle.data("universe") if cycle is not None else None
    if universe is None:
        return _error_rows("universe"), []
    symbols = universe.get("eligible_symbols") or []
    return [], symbols


def render_market(cycle):
    market = cycle.data("market") if cycle is not None else None
    if not isinstance(market, dict) or not market:
        return _error_rows("market"), []
    rows = []
    for symbol in sorted(market.keys()):
        state = market[symbol]
        if not isinstance(state, dict):
            continue
        row = [
            _label(symbol),
            _label(
                state.get("symbol") or state.get("instrument")
                or state.get("symbol_id")
            ),
        ]
        rows.append(row)
    return [], rows


def render_signals(cycle):
    signals = cycle.data("signals") if cycle is not None else None
    if not isinstance(signals, dict) or not signals:
        return _error_rows("signals"), []
    rows = []
    for symbol in sorted(signals.keys()):
        entry = signals[symbol]
        if not isinstance(entry, dict):
            continue
        signal = entry.get("signal")
        rows.append([_label(symbol), _label(signal)])
    return [], rows


def render_positions(cycle):
    positions = cycle.data("positions") if cycle is not None else None
    if not isinstance(positions, dict) or not positions:
        return _error_rows("positions"), []
    rows = []
    for symbol in sorted(positions.keys()):
        entry = positions[symbol]
        if not isinstance(entry, dict):
            continue
        trade = entry.get("current_trade")
        rows.append(
            [
                _label(symbol),
                _label((trade or {}).get("side")),
                _label((trade or {}).get("quantity")),
                _label((trade or {}).get("entry_price")),
            ]
        )
    return [], rows


def render_orders(cycle):
    orders = cycle.data("orders") if cycle is not None else None
    if not isinstance(orders, dict) or not orders:
        return _error_rows("orders"), []
    rows = []
    for symbol in sorted(orders.keys()):
        entry = orders[symbol]
        if not isinstance(entry, dict):
            continue
        rows.append([_label(symbol), _label(entry.get("count"))])
    return [], rows


def render_account(cycle):
    account = cycle.data("account") if cycle is not None else None
    if not isinstance(account, dict):
        return _error_rows("account"), []
    return [
        ("Sum balance", _label(account.get("sum_balance"))),
        ("Sum equity", _label(account.get("sum_equity"))),
        ("Runtimes", _label(len(account.get("per_runtime") or []))),
    ], None


def render_risk(cycle):
    risk = cycle.data("risk") if cycle is not None else None
    if not isinstance(risk, dict):
        return _error_rows("risk"), []
    rows = [("Portfolio", _label(risk.get("portfolio")))]
    per = risk.get("per_symbol") or {}
    for symbol in sorted(per.keys()):
        state = per[symbol]
        if not isinstance(state, dict):
            continue
        rows.append(
            (
                "Risk[%s]" % symbol,
                "dd=%s exp=%s risk=%s"
                % (
                    _label(state.get("drawdown_percent")),
                    _label(state.get("exposure")),
                    _label(state.get("current_risk")),
                ),
            )
        )
    return rows, None


def render_performance(cycle):
    perf = cycle.data("performance") if cycle is not None else None
    if not isinstance(perf, dict):
        return _error_rows("performance"), []
    aggregate = perf.get("aggregate")
    rows = []
    if isinstance(aggregate, dict):
        for key in (
            "completed_trades",
            "wins",
            "losses",
            "breakevens",
            "net_pnl",
            "gross_profit",
            "gross_loss",
            "profit_factor",
            "expectancy",
            "drawdown",
            "max_drawdown",
        ):
            rows.append((key.replace("_", " ").title(), _label(aggregate.get(key))))
    else:
        rows.append(("Aggregate", "Unavailable"))
    return rows, None


def render_errors(cycle):
    errors = cycle.data("errors") if cycle is not None else None
    if not isinstance(errors, dict):
        return _error_rows("errors"), []
    entries = errors.get("errors") or []
    rows = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        source = entry.get("source", "")
        symbol = entry.get("symbol", "")
        operation = entry.get("operation", "")
        message = entry.get("error", "")
        rows.append(
            "[%s] %s%s: %s"
            % (
                _label(source),
                _label(symbol) + " " if symbol else "",
                _label(operation) if operation else "",
                _label(message),
            )
        )
    return [], rows


def _error_rows(endpoint):
    return [("%s" % endpoint.title(), "Unavailable")]
