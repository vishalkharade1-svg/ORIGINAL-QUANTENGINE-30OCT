"""
====================================================

QuantEngine - Secure Remote / Mobile Control Foundation

dashboard.py -- mobile-responsive PWA dashboard (Phase 9P-k-D).

A self-contained, stdlib-only, dependency-free PWA that the remote
gateway serves. It is the MOBILE CLIENT: a phone browser is enough
to monitor (VIEW) and control (CONTROL / EMERGENCY) the PAPER
runtime through the role-gated gateway.

Design rules the dashboard obeys:

  * VIEW + CONTROL only. It never places orders, never requests a
    strategy/risk/parameter change, never requests LIVE-mode: those
    routes do not exist on the remote surface at all, and the UI
    renders no control affordance the principal's role lacks.
  * It renders SERVER RESPONSES VERBATIM. It does NOT compute its
    own P&L / risk / exposure / position numbers -- the authoritative
    Control API is the only arithmetic source.
  * It shows PAPER / LIVE unmistakably and reflects the lifecycle
    state from /health.
  * It models connection state CONNECTED / DEGRADED / DISCONNECTED
    and a data-freshness age so stale data is unmistakable.
  * It never stores exchange credentials; the only credential is the
    per-role gateway token, kept in sessionStorage (cleared when the
    tab closes) and never written to disk or sent anywhere but the
    Authorization header.

This module only stores the static asset STRINGS; it performs no
I/O. The gateway binds these to routes (/, /index.html, /app.js,
/app.css, /manifest.json, /sw.js) so no separate static server or
build step is needed.

Stdlib only.
====================================================
"""

CSS = r"""
:root {
  --bg: #0e1117; --panel: #161b22; --line: #2a3038;
  --txt: #e6edf3; --mut: #8b949e; --ok: #3fb950;
  --warn: #d29922; --bad: #f85149; --accent: #58a6ff;
}
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; background: var(--bg);
  color: var(--txt); font-family: system-ui, -apple-system, sans-serif; }
body { padding: 12px; max-width: 720px; margin: 0 auto;
  padding-bottom: 84px; }
h1 { font-size: 20px; margin: 8px 0 4px; }
.sub { color: var(--mut); font-size: 13px; margin-bottom: 12px; }
.card { background: var(--panel); border: 1px solid var(--line);
  border-radius: 12px; padding: 14px; margin-bottom: 12px; }
.row { display: flex; justify-content: space-between; align-items: center;
  padding: 6px 0; border-bottom: 1px solid var(--line); font-size: 14px; }
.row:last-child { border-bottom: none; }
.row .k { color: var(--mut); }
.row .v { font-weight: 600; text-align: right; word-break: break-word; }
.badge { display: inline-block; padding: 2px 10px; border-radius: 999px;
  font-size: 13px; font-weight: 700; }
.badge.paper { background: rgba(63,185,80,.15); color: var(--ok); }
.badge.live { background: rgba(248,81,73,.2); color: var(--bad); }
.badge.state { background: rgba(88,166,255,.15); color: var(--accent); }
.badge.conn { background: rgba(139,148,158,.15); color: var(--mut); }
.badge.conn.ok { color: var(--ok); }
.badge.conn.deg { color: var(--warn); }
.badge.conn.bad { color: var(--bad); }
.bar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap;
  margin-bottom: 12px; }
button, .btn { background: var(--panel); color: var(--txt);
  border: 1px solid var(--line); border-radius: 8px; padding: 8px 14px;
  font-size: 14px; cursor: pointer; }
button.primary { background: var(--accent); color: #0b0f14;
  border-color: var(--accent); font-weight: 700; }
button.danger { background: var(--bad); color: #fff; border-color: var(--bad); }
button:disabled { opacity: .4; cursor: not-allowed; }
#token { width: 100%; padding: 10px; border-radius: 8px;
  border: 1px solid var(--line); background: var(--panel);
  color: var(--txt); font-size: 14px; }
.mono { font-family: ui-monospace, monospace; }
.mut { color: var(--mut); font-size: 13px; }
.tiles { display: grid; grid-template-columns: repeat(auto-fit,minmax(150px,1fr));
  gap: 10px; }
.tile { background: var(--panel); border: 1px solid var(--line);
  border-radius: 10px; padding: 12px; }
.tile .t { color: var(--mut); font-size: 12px; }
.tile .n { font-size: 18px; font-weight: 700; margin-top: 2px; word-break: break-word;}
.controls { display: flex; gap: 8px; flex-wrap: wrap; }
.spin { color: var(--mut); font-size: 13px; text-align: center;
  padding: 20px 0; }
.foot { position: fixed; left: 0; right: 0; bottom: 0; z-index: 5;
  background: rgba(14,17,23,.96); border-top: 1px solid var(--line);
  padding: 8px 12px; text-align: center; color: var(--mut); font-size: 12px; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { text-align: left; padding: 6px 4px; border-bottom: 1px solid var(--line); }
th { color: var(--mut); font-weight: 600; }
.notice { padding: 10px; border-radius: 8px; margin: 8px 0; font-size: 13px; }
.notice.warn { background: rgba(210,153,34,.12); color: var(--warn); }
.notice.bad { background: rgba(248,81,73,.12); color: var(--bad); }
"""

JS = r"""
(function () {
  "use strict";

  var API = {
    get: function (path, token) {
      return fetch(path, { headers: { "Authorization": "Bearer " + token } })
        .then(function (r) { return r.json().then(function (j) {
          return { status: r.status, body: j };
        }); });
    },
    post: function (path, body, token) {
      return fetch(path, {
        method: "POST",
        headers: {
          "Authorization": "Bearer " + token,
          "Content-Type": "application/json"
        },
        body: JSON.stringify(body)
      }).then(function (r) { return r.json().then(function (j) {
        return { status: r.status, body: j };
      }); });
    }
  };

  var state = {
    token: sessionStorage.getItem("qe_role_token") || "",
    role: null,
    conn: "disconnected",   // connected | degraded | disconnected
    lastOk: null,
    health: null,
    pollTimer: null
  };

  var $ = function (id) { return document.getElementById(id); };

  function setToken(t) {
    state.token = t;
    if (t) sessionStorage.setItem("qe_role_token", t);
    else sessionStorage.removeItem("qe_role_token");
  }

  function connLabel() {
    if (state.conn === "connected") return { c: "CONNECTED", k: "ok" };
    if (state.conn === "degraded") return { c: "DEGRADED", k: "deg" };
    return { c: "DISCONNECTED", k: "bad" };
  }

  function renderHeader() {
    var badge = $("modeBadge");
    // PAPER/LIVE is surfaced by the server (/health runtime_mode); the
    // remote surface can NEVER enable LIVE, so this reflects the
    // engine's own authoritative configured mode, unmistakably.
    var mode = state.health && state.health.runtime_mode === "LIVE" ? "LIVE" : "PAPER";
    badge.textContent = mode;
    badge.className = "badge " + (mode === "LIVE" ? "live" : "paper");

    var conn = connLabel();
    var c = $("connBadge");
    c.textContent = conn.c;
    c.className = "badge conn " + conn.k;

    $("lifecycleRow").textContent = (state.health && state.health.lifecycle_state) ||
      "Unavailable";

    var age = "Unavailable";
    if (state.lastOk) {
      var s = Math.floor((Date.now() - state.lastOk) / 1000);
      age = s < 60 ? s + "s ago" : Math.floor(s / 60) + "m ago";
    }
    $("freshRow").textContent = age;

    var role = $("roleBadge");
    role.textContent = state.role ? "ROLE:" + state.role : "no role";
    role.className = "badge state " + (state.role ? "" : "conn");
  }

  function showButtons() {
    var canControl = state.role === "CONTROL" || state.role === "EMERGENCY";
    var canEmergency = state.role === "EMERGENCY";
    $("btnStart").disabled = !canControl;
    $("btnStop").disabled = !canControl;
    $("btnRestart").disabled = !canControl;
    $("btnEmergency").disabled = !canEmergency;
  }

  function render(app) {
    renderHeader();
    showButtons();
    if (!app.health) { $("healthCard").innerHTML = "<div class='spin'>No data yet</div>"; }
    else {
      $("healthCard").innerHTML = tiles([
        ["Lifecycle", app.health.lifecycle_state || "Unavailable"],
        ["Engine", app.health.engine_started ? "Running" : "Stopped"],
        ["Runtimes", String(app.health.runtimes ?? "Unavailable")],
        ["Uptime (s)", fmtNum(app.health.uptime_seconds)],
        ["Polls", String(app.health.polls ?? "Unavailable")]
      ]);
    }
    $("universeCard").innerHTML = app.universe
      ? tiles([["Eligible", String(app.universe.eligible_count ?? "Unavailable")],
               ["Mode", app.universe.mode || "Unavailable"]])
      : "<div class='spin'>Unavailable</div>";
    renderAccount(app);
    renderPositions(app);
  }

  function tiles(rows) {
    var s = "<div class='tiles'>";
    rows.forEach(function (r) {
      s += "<div class='tile'><div class='t'>" + esc(r[0]) + "</div>" +
           "<div class='n mono'>" + esc(r[1]) + "</div></div>";
    });
    return s + "</div>";
  }

  function renderAccount(app) {
    var a = app.account;
    if (!a) { $("accountCard").innerHTML = "<div class='spin'>Unavailable</div>"; return; }
    $("accountCard").innerHTML = rows([
      ["Sum balance", fmtNum(a.sum_balance)],
      ["Sum equity", fmtNum(a.sum_equity)],
      ["Shared capital", fmtNum(a.shared_capital && a.shared_capital.equity)]
    ]);
  }

  function renderPositions(app) {
    var p = app.positions;
    if (!p) { $("positionsCard").innerHTML = "<div class='spin'>Unavailable</div>"; return; }
    var keys = Object.keys(p);
    if (!keys.length) { $("positionsCard").innerHTML = "<div class='mut'>No open positions</div>"; return; }
    var s = "<div class='notice warn'>Positions shown verbatim from the server.</div><table>" +
      "<tr><th>Symbol</th><th>Side</th><th>Qty</th><th>Entry</th></tr>";
    keys.forEach(function (k) {
      var t = p[k] && p[k].current_trade || {};
      // qty/entry are the runtime's own fields, rendered verbatim from
      // the server -- never computed client-side
      var qty = t.quantity !== undefined && t.quantity !== null ? t.quantity :
        (t.qty !== undefined ? t.qty : "Unavailable");
      var entry = t.entry_price !== undefined && t.entry_price !== null ?
        t.entry_price : "Unavailable";
      s += "<tr><td>" + esc(k) + "</td><td>" + esc(t.direction || "Unavailable") +
        "</td><td>" + esc(fmtNum(qty)) + "</td><td>" + esc(fmtNum(entry)) +
        "</td></tr>";
    });
    s += "</table>";
    $("positionsCard").innerHTML = s;
  }

  function esc(s) {
    if (s === null || s === undefined) return "Unavailable";
    return String(s).replace(/[&<>"']/g, function (m) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m];
    });
  }
  function fmtNum(v) {
    if (v === null || v === undefined || v === "") return "Unavailable";
    var n = Number(v);
    if (isNaN(n)) return esc(v);
    if (Math.abs(n) >= 1000) return String(n.toFixed(2));
    return String(n);
  }
  function rows(rs) {
    var s = "";
    rs.forEach(function (r) {
      s += "<div class='row'><span class='k'>" + esc(r[0]) + "</span>" +
           "<span class='v mono'>" + esc(r[1]) + "</span></div>";
    });
    return s;
  }

  function poll() {
    if (!state.token) return;
    var ok = false;
    API.get("/health", state.token)
      .then(function (r) {
        if (r.status === 200) {
          state.health = r.body;
          state.lastOk = Date.now();
          state.conn = "connected";
          ok = true;
        } else if (r.status === 401) {
          setToken("");
          state.role = null;
          show();
          return;
        } else {
          state.conn = "degraded";
        }
      })
      .catch(function () { state.conn = "disconnected"; })
      .then(function () {
        if (ok) {
          var calls = [
            API.get("/universe", state.token),
            API.get("/account", state.token),
            API.get("/positions", state.token)
          ];
          return Promise.all(calls.map(function (p) { return p.catch(function () { return null; }); }));
        }
        return [null, null, null];
      })
      .then(function (res) {
        if (ok && res) {
          render({
            health: state.health,
            universe: res[0] && res[0].status === 200 ? res[0].body : null,
            account: res[1] && res[1].status === 200 ? res[1].body : null,
            positions: res[2] && res[2].status === 200 ? res[2].body : null
          });
        } else {
          render({ health: state.health, universe: null, account: null, positions: null });
        }
      });
  }

  function startPolling() {
    if (state.pollTimer) clearInterval(state.pollTimer);
    poll();
    state.pollTimer = setInterval(poll, 5000);
  }

  function doControl(command, btn) {
    if (!state.token || !state.role) return;
    var wasDisabled = btn.disabled;
    btn.disabled = true;
    API.post("/control", { command: command }, state.token)
      .then(function (r) {
        if (r.status !== 200) {
          alert("Command rejected: " + (r.body && r.body.detail ? r.body.detail : "forbidden"));
          return;
        }
        poll();
      })
      .catch(function () { alert("Command failed (network/denied)"); })
      .finally(function () { if (!wasDisabled) btn.disabled = false; });
  }

  function show() {
    if (!state.token) {
      $("gate").style.display = "block";
      $("app").style.display = "none";
      $("connectBtn").focus();
      return;
    }
    $("gate").style.display = "none";
    $("app").style.display = "block";
    API.get("/api/me", state.token)
      .then(function (r) { state.role = r.status === 200 ? r.body.role : null; renderHeader(); })
      .catch(function () {});
    startPolling();
  }

  function bind() {
    $("connectBtn").addEventListener("click", function () {
      var t = $("token").value.trim();
      if (!t) return;
      setToken(t);
      show();
    });
    $("logout").addEventListener("click", function () {
      setToken("");
      if (state.pollTimer) clearInterval(state.pollTimer);
      state.role = null; state.health = null; state.lastOk = null; state.conn = "disconnected";
      show();
    });
    $("btnStart").addEventListener("click", function () { doControl("start", this); });
    $("btnStop").addEventListener("click", function () { doControl("stop", this); });
    $("btnRestart").addEventListener("click", function () { doControl("restart", this); });
    $("btnEmergency").addEventListener("click", function () { doControl("emergency_stop", this); });
  }

  document.addEventListener("DOMContentLoaded", function () {
    bind();
    show();
  });
})();
"""

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>QuantEngine Remote</title>
  <link rel="manifest" href="/manifest.json">
  <link rel="stylesheet" href="/app.css">
</head>
<body>
  <div id="gate">
    <h1>QuantEngine Remote</h1>
    <p class="sub">Enter your remote gateway token to continue.</p>
    <div class="card">
      <input id="token" type="password" placeholder="Role token" autocomplete="off">
      <p class="mut" style="margin-top:8px">VIEW and CONTROL only. Credentials stay in this tab and are
      never stored on disk.</p>
      <button id="connectBtn" class="primary" style="width:100%;margin-top:10px">Connect</button>
    </div>
  </div>

  <div id="app" style="display:none">
    <div class="bar">
      <div>
        <h1>QuantEngine</h1>
        <div class="bar">
          <span id="modeBadge" class="badge paper">PAPER</span>
          <span id="connBadge" class="badge conn">DISCONNECTED</span>
          <span id="roleBadge" class="badge state">no role</span>
        </div>
      </div>
      <button id="logout" class="btn">Disconnect</button>
    </div>

    <div class="card">
      <div class="row"><span class="k">Lifecycle</span><span id="lifecycleRow" class="v mono">Unavailable</span></div>
      <div class="row"><span class="k">Data age</span><span id="freshRow" class="v mono">Unavailable</span></div>
      <div class="notice warn" style="margin-top:8px">Server state only. The client never computes its own
      P&amp;L/risk/position figures.</div>
    </div>

    <div id="healthCard" class="card"><div class="spin">Loading…</div></div>
    <div id="universeCard" class="card"></div>
    <div id="accountCard" class="card"></div>
    <div id="positionsCard" class="card"></div>

    <div class="card">
      <div class="controls">
        <button id="btnStart" class="primary" disabled>Start</button>
        <button id="btnStop" disabled>Stop</button>
        <button id="btnRestart" disabled>Restart</button>
        <button id="btnEmergency" class="danger" disabled>Emergency Stop</button>
      </div>
      <p class="mut" style="margin-top:8px">Control requires the CONTROL role; Emergency Stop requires
      the EMERGENCY role. PAPER only.</p>
    </div>

    <div class="foot">QuantEngine remote dashboard — connection state and data are live from the server.</div>
  </div>

  <script src="/app.js"></script>
</body>
</html>
"""

MANIFEST = """{
  "name": "QuantEngine Remote",
  "short_name": "QuantEngine",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#0e1117",
  "theme_color": "#0e1117"
}
"""

SW = """self.addEventListener('install', function (e) { self.skipWaiting(); });
self.addEventListener('activate', function (e) { self.clients.claim(); });
"""


_ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.css": ("app.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "application/javascript; charset=utf-8"),
    "/manifest.json": ("manifest.json", "application/manifest+json"),
    "/sw.js": ("sw.js", "application/javascript; charset=utf-8"),
    "/favicon.ico": ("favicon.ico", "image/x-icon"),
}

_CONTENT = {
    "index.html": HTML,
    "app.css": CSS,
    "app.js": JS,
    "manifest.json": MANIFEST,
    "sw.js": SW,
    "favicon.ico": "",
}


def by_path(path):
    """Return the raw asset bytes for PATH, or None if unknown."""
    entry = _ASSETS.get(path)
    if entry is None:
        return None
    name, _ct = entry
    text = _CONTENT.get(name)
    if text is None:
        return None
    return text.encode("utf-8")


def content_type(path):
    entry = _ASSETS.get(path)
    return entry[1] if entry else "application/octet-stream"
