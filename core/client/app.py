"""
====================================================

QuantEngine

Lightweight Desktop Control Client - tkinter UI

Phase 9P-h.

A thin Tkinter/ttk desktop control & monitoring terminal over
the existing Control API. It renders whatever the API returns
and offers ONLY the four allowlisted lifecycle commands.

The UI is read-only except for those lifecycle controls. It
contains zero strategy / risk / position / order / performance
calculation and never imports engine internals -- every value
pictured comes from a GET response; every button issues one
POST /control.

Responsiveness model:
  Tkinter main thread  <-  after() drain  <-  worker queue
                                                `--  poller thread
                                                     -> Control API
HTTP never runs on the Tkinter thread. Closing the window
stops the poller but NEVER stops the engine (lifecycle is
independent -- the UI is not a control/stop).

Stdlib only: tkinter, ttk, queue, time, threading.
====================================================
"""

import queue
import threading
import time
from tkinter import ttk

from core.client import controller
from core.client.http_client import ClientError, ReconnectingClient
from core.client.poller import Poller

try:
    import tkinter as _tk
except ImportError:  # pragma: no cover - headless environments
    _tk = None


def _connected_color():
    return "#2e7d32"


def _disconnected_color():
    return "#c62828"


class DesktopClient:

    """Tkinter front-end. Construction requires a display; the
    surrounding modules (controller/poller/http_client/config) are
    display-free and independently testable."""

    def __init__(self, api, config, on_close=None):
        if _tk is None:  # pragma: no cover
            raise RuntimeError("tkinter is not available on this host")

        self.api = api
        self.config = config
        self.on_close = on_close

        self.poller = Poller(
            api,
            interval=config.poll_interval,
        )
        self.reconnecter = ReconnectingClient(api, interval=config.poll_interval)
        self.controls = controller.ControlPath(api)

        self.root = _tk.Tk()
        self.root.title("QuantEngine Control")
        self.root.geometry("980x640")
        self.root.minsize(860, 540)

        self._build_header()
        self._build_tabs()
        self._build_control_bar()
        self._build_statusbar()

        self._disconnect_hint = True

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # start the poller only after the UI loop is building
        self.poller.start()

        # schedule the first after() drain immediately
        self._schedule()

    # -----------------------------------------------------
    # Layout
    # -----------------------------------------------------

    def _build_header(self):
        header = ttk.Frame(self.root, padding=(10, 8))
        header.pack(fill="x")

        ttk.Label(header, text="QUANTENGINE",
                  font=("Segoe UI", 14, "bold")).pack(side="left")

        self.conn_label = ttk.Label(header, text="disconnected",
                                    foreground=_disconnected_color())
        self.conn_label.pack(side="right", padx=(0, 6))

        self.engine_label = ttk.Label(header, text="engine: ?",
                                      foreground="#555555")
        self.engine_label.pack(side="right", padx=(0, 16))

        self.connectivity_circle = ttk.Label(header, text="\u25cf",
                                             foreground=_disconnected_color())
        self.connectivity_circle.pack(side="right", padx=(0, 2))

        ttk.Separator(self.root).pack(fill="x")

    def _build_tabs(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=6)

        self.dashboard_frame = ttk.Frame(self.notebook)
        self.universe_frame = ttk.Frame(self.notebook)
        self.market_frame = ttk.Frame(self.notebook)
        self.trading_frame = ttk.Frame(self.notebook)
        self.performance_frame = ttk.Frame(self.notebook)
        self.logs_frame = ttk.Frame(self.notebook)

        self.notebook.add(self.dashboard_frame, text="Dashboard")
        self.notebook.add(self.universe_frame, text="Universe")
        self.notebook.add(self.market_frame, text="Market")
        self.notebook.add(self.trading_frame, text="Trading")
        self.notebook.add(self.performance_frame, text="Performance")
        self.notebook.add(self.logs_frame, text="Logs")

        self._build_dashboard_tab()
        self._build_universe_tab()
        self._build_market_tab()
        self._build_trading_tab()
        self._build_performance_tab()
        self._build_logs_tab()

    def _build_dashboard_tab(self):
        self.dash_tree = self._mk_tree(self.dashboard_frame, ("Field", "Value"))
        self.dash_tree.pack(fill="both", expand=True)

    def _build_universe_tab(self):
        self.universe_tree = self._mk_tree(
            self.universe_frame, ("Symbol",)
        )
        self.universe_tree.pack(fill="both", expand=True)

    def _build_market_tab(self):
        self.market_tree = self._mk_tree(
            self.market_frame, ("Symbol", "State")
        )
        self.market_tree.pack(fill="both", expand=True)

    def _build_trading_tab(self):
        self._trading_notebook = ttk.Notebook(self.trading_frame)
        self._trading_notebook.pack(fill="both", expand=True)

        self.signals_frame = ttk.Frame(self._trading_notebook)
        self.positions_frame = ttk.Frame(self._trading_notebook)
        self.orders_frame = ttk.Frame(self._trading_notebook)
        self.account_frame = ttk.Frame(self._trading_notebook)
        self.risk_frame = ttk.Frame(self._trading_notebook)

        self._trading_notebook.add(self.signals_frame, text="Signals")
        self._trading_notebook.add(self.positions_frame, text="Positions")
        self._trading_notebook.add(self.orders_frame, text="Orders")
        self._trading_notebook.add(self.account_frame, text="Account")
        self._trading_notebook.add(self.risk_frame, text="Risk")

        self.signals_tree = self._mk_tree(self.signals_frame, ("Symbol", "Signal"))
        self.signals_tree.pack(fill="both", expand=True)

        self.positions_tree = self._mk_tree(
            self.positions_frame, ("Symbol", "Side", "Qty", "Entry")
        )
        self.positions_tree.pack(fill="both", expand=True)

        self.orders_tree = self._mk_tree(self.orders_frame, ("Symbol", "Count"))
        self.orders_tree.pack(fill="both", expand=True)

        self.account_tree = self._mk_tree(self.account_frame, ("Field", "Value"))
        self.account_tree.pack(fill="both", expand=True)

        self.risk_tree = self._mk_tree(self.risk_frame, ("Field", "Value"))
        self.risk_tree.pack(fill="both", expand=True)

    def _build_performance_tab(self):
        self.performance_tree = self._mk_tree(
            self.performance_frame, ("Field", "Value")
        )
        self.performance_tree.pack(fill="both", expand=True)

    def _build_logs_tab(self):
        import tkinter.scrolledtext as _st

        self.logs_text = _st.ScrolledText(
            self.logs_frame,
            height=16,
            state="disabled",
            font=("Consolas", 9),
        )
        self.logs_text.pack(fill="both", expand=True)

    def _build_control_bar(self):
        bar = ttk.Frame(self.root, padding=(10, 6))
        bar.pack(fill="x")

        ttk.Label(bar, text="Controls:").pack(side="left", padx=(0, 8))

        ttk.Button(bar, text="Start", command=lambda: self._control("start")).pack(
            side="left", padx=3
        )
        ttk.Button(bar, text="Stop", command=lambda: self._control("stop")).pack(
            side="left", padx=3
        )
        ttk.Button(bar, text="Restart", command=lambda: self._control("restart")).pack(
            side="left", padx=3
        )
        ttk.Button(
            bar,
            text="EMERGENCY STOP",
            command=lambda: self._control("emergency_stop"),
        ).pack(side="left", padx=3)

    def _build_statusbar(self):
        self.status_var = _tk.StringVar(value="Ready")
        status = ttk.Label(
            self.root, textvariable=self.status_var, padding=(10, 4)
        )
        status.pack(fill="x", side="bottom")

    # -----------------------------------------------------
    # Posting logic (pure, testable)
    # -----------------------------------------------------

    def _control(self, command):
        confirmation = self._confirm(command)
        if not confirmation:
            return
        self._run_control_bg(command, confirmation)

    def _confirm(self, command):
        from tkinter import messagebox

        if command == "emergency_stop":
            return messagebox.askyesno(
                "Emergency Stop",
                "Are you sure you want to EMERGENCY STOP QuantEngine?\n"
                "This is the highest-priority immediate local shutdown.\n"
                "Continue?",
                icon="warning",
            )
        if command == "restart":
            return messagebox.askyesno(
                "Restart",
                "Restart the QuantEngine runtime?\nContinue?",
            )
        if command == "stop":
            return messagebox.askyesno(
                "Stop",
                "Gracefully stop the QuantEngine runtime?\nContinue?",
            )
        # start is non-destructive: no confirmation required
        return True

    def _run_control_bg(self, command, _confirmed):
        method = getattr(self.controls, command, None)

        if method is None:
            self.status_var.set("control %s unavailable" % command)
            return

        def work():
            try:
                result = method()
                status = (result or {}).get("lifecycle_state", "sent")
                message = "sent %s -> %s" % (command, status)
            except ClientError as exc:
                message = "control %s failed: %s" % (command, str(exc))
            except Exception as exc:  # noqa: BLE001
                message = "control %s error: %s" % (command, str(exc))

            def apply():
                self.status_var.set(message)

            self.root.after(0, apply)

        threading.Thread(target=work, daemon=True).start()

    # -----------------------------------------------------
    # Refresh pipeline (poll -> on UI thread)
    # -----------------------------------------------------

    def _schedule(self):
        self._drain_queue()
        self._refresh_connectivity()
        self.root.after(250, self._schedule)

    def _drain_queue(self):
        drained = False
        latest = None
        while True:
            try:
                latest = self.poller.queue.get_nowait()
                drained = True
            except queue.Empty:
                break
        if not drained and latest is None:
            return
        self._render(latest)

    def _refresh_connectivity(self):
        self.reconnecter.probe()
        if self.reconnecter.healthy():
            color = _connected_color()
            text = "connected"
        else:
            color = _disconnected_color()
            text = "disconnected"
        self.conn_label.config(text=text, foreground=color)
        self.connectivity_circle.config(foreground=color)

    def _render(self, cycle):
        self._render_dashboard(cycle)
        self._render_universe(cycle)
        self._render_market(cycle)
        self._render_signals(cycle)
        self._render_positions(cycle)
        self._render_orders(cycle)
        self._render_account(cycle)
        self._render_risk(cycle)
        self._render_performance(cycle)
        self._render_logs(cycle)

        engine = (
            cycle.data("health") or {}

            if cycle is not None
            else {}
        )
        state = engine.get("lifecycle_state")
        if cycle is None or not cycle.connected:
            state = "disconnected"
        self.engine_label.config(
            text="engine: %s" % (state or "?"),
            foreground=_connected_color()
            if state and state in ("RUNNING", "STARTING")
            else _disconnected_color(),
        )

        last_update = time.strftime("%H:%M:%S", time.localtime(cycle.at)) if cycle else "Unavailable"
        self.status_var.set(
            "API %s | Last update %s"
            % (
                "connected" if cycle and cycle.connected else "disconnected",
                last_update,
            )
        )

    def _render_dashboard(self, cycle):
        rows = controller.render_dashboard(cycle)
        self._fill_tree(self.dash_tree, rows, ("Field", "Value"))

    def _render_universe(self, cycle):
        _headers, symbols = controller.render_universe(cycle)
        self._fill_tree(self.universe_tree, [(s,) for s in symbols], ("Symbol",))

    def _render_market(self, cycle):
        _headers, rows = controller.render_market(cycle)
        self._fill_tree(self.market_tree, rows, ("Symbol", "State"))

    def _render_signals(self, cycle):
        _headers, rows = controller.render_signals(cycle)
        self._fill_tree(self.signals_tree, rows, ("Symbol", "Signal"))

    def _render_positions(self, cycle):
        _headers, rows = controller.render_positions(cycle)
        self._fill_tree(self.positions_tree, rows, ("Symbol", "Side", "Qty", "Entry"))

    def _render_orders(self, cycle):
        _headers, rows = controller.render_orders(cycle)
        self._fill_tree(self.orders_tree, rows, ("Symbol", "Count"))

    def _render_account(self, cycle):
        rows, _ = controller.render_account(cycle)
        self._fill_tree(self.account_tree, rows, ("Field", "Value"))

    def _render_risk(self, cycle):
        rows, _ = controller.render_risk(cycle)
        self._fill_tree(self.risk_tree, rows, ("Field", "Value"))

    def _render_performance(self, cycle):
        rows, _ = controller.render_performance(cycle)
        self._fill_tree(self.performance_tree, rows, ("Field", "Value"))

    def _render_logs(self, cycle):
        rows, _ = controller.render_errors(cycle)
        self.logs_text.configure(state="normal")
        self.logs_text.delete("1.0", "end")
        for line in rows:
            self.logs_text.insert("end", "%s\n" % line)
        self.logs_text.configure(state="disabled")

    # -----------------------------------------------------
    # tree helpers
    # -----------------------------------------------------

    def _mk_tree(self, parent, columns):
        tree = ttk.Treeview(parent, columns=columns, show="headings")
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=140, anchor="w")
        return tree

    def _fill_tree(self, tree, rows, columns):
        tree.delete(*tree.get_children())
        for row in rows:
            if not row:
                continue
            values = list(row) + [""] * (len(columns) - len(row))
            tree.insert("", "end", values=values[: len(columns)])

    # -----------------------------------------------------
    # lifecycle
    # -----------------------------------------------------

    def _on_close(self):
        self.poller.stop()
        self.poller.join(timeout=3.0)
        if self.on_close is not None:
            self.on_close()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    """Entry point: `python -m core.client.app`."""

    from core.client.config import ClientConfig
    from core.client.http_client import ApiClient

    config = ClientConfig.from_env()

    if not config.token:
        from tkinter import messagebox

        _root = _tk.Tk() if _tk else None
        if _root is not None:
            messagebox.showwarning(
                "Control API token missing",
                "No CONTROL_API_TOKEN / QENGINE_CLIENT_TOKEN found.\n"
                "The Control API fails closed without a token and the "
                "client cannot authenticate. Restart with the token set.",
            )
            _root.destroy()

    api = ApiClient(
        host=config.host,
        port=config.port,
        token=config.token,
        timeout=config.timeout,
    )

    app = DesktopClient(api, config)
    app.run()


if __name__ == "__main__":  # pragma: no cover
    main()
