"""Phase-7 authoritative-path + integration-boundary pins.

All pins are LOCAL/STATIC: they verify code boundaries and forensic
identity, never venue behavior. Deterministic, offline, stdlib only.

* No production entry point may opt into legacy ticker-derived
  strategy candles.
* Contract/economics gates are classified DEFINED vs WIRED vs
  CONSUMED from actual call sites (not docstrings).
* The historical LF-normalized nine-file strategy digest remains a
  forensic reference. A source archive without the historical checkout
  must report drift as BLOCKED rather than silently re-pin it.
* Reconciliation additions are LOCAL contract tests (fake executors).
"""

from __future__ import annotations

import hashlib
import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]

STRATEGY_FILES = [
    "core/execution/entry_model.py",
    "core/setup/trade_setup_builder.py",
    "core/setup/decision_engine.py",
    "core/execution/execution_engine.py",
    "core/risk/risk_engine.py",
    "core/backtesting/accounting.py",
    "backtesting/backtester.py",
    "core/paper_trading/paper_trading_engine.py",
    "config/risk_settings.py",
]

# Historical reference from the Phase-4-corrected tree. This source ZIP
# has no .git history, so it cannot independently prove ancestry or claim
# to be that tree. Keep the reference unchanged; drift must stay BLOCKED.
NORMALIZED_DIGEST = "9eff61b777846c7f5e2056c486c9c381872a93e154d35160e70f63051c8fd8a2"


class TestLegacyTickerFallbackUnreachable(unittest.TestCase):
    def test_main_never_opts_into_legacy_candles(self):
        lines = (ROOT / "main.py").read_text(encoding="utf-8").splitlines()
        code = "\n".join(line.split("#", 1)[0] for line in lines)
        self.assertNotIn("publish_candles=True", code)
        self.assertNotIn("publish_candles", code)
        self.assertNotIn("ALLOW_LEGACY_TICKER_CANDLES", code)
        # The prohibition itself must stay documented at the call site.
        self.assertIn("Do NOT", (ROOT / "main.py").read_text(encoding="utf-8"))

    def test_legacy_opt_in_stays_off_by_default(self):
        import inspect

        import data.websocket_client as ws_mod

        params = inspect.signature(ws_mod.start).parameters
        self.assertFalse(params["publish_candles"].default)

    def test_verified_runtimes_import_no_legacy_feed(self):
        for relative in (
            "core/runtime/verified_runtime.py",
            "core/runtime/paper_main.py",
        ):
            source = (ROOT / relative).read_text(encoding="utf-8")
            for line in source.splitlines():
                code = line.split("#", 1)[0]
                self.assertNotIn("data.websocket_client", code, relative)


class TestContractEconomicsBoundary(unittest.TestCase):
    @staticmethod
    def _callers(name: str) -> list[str]:
        hits = []
        for path in (ROOT / "core").rglob("*.py"):
            for number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                code = line.split("#", 1)[0]
                if "``" in code or '"""' in line.strip()[:3]:
                    continue
                if name + "(" not in code:
                    continue
                if ("def " + name) in code or "import" in code:
                    continue
                hits.append("%s:%d" % (path.relative_to(ROOT), number))
        return hits

    def test_verified_contract_gate_unwired(self):
        # DEFINED in core/registry/verified_contract.py, tested, but no
        # runtime caller: contract metadata cannot reach sizing.
        self.assertEqual(self._callers("verify_contract_spec"), [])

    def test_realistic_economics_gate_unwired(self):
        # DEFINED in core/execution/economics.py, tested, but no
        # runtime caller: unknown economics stay fail-closed by
        # absence instead of silent defaults.
        self.assertEqual(self._callers("require_realistic"), [])
        self.assertEqual(self._callers("apply_costs"), [])

    def test_settings_backed_costs_are_the_wired_leg(self):
        # The ONLY economics leg consumed at runtime: RiskEngine mints
        # commission/slippage from explicit settings (zero unless
        # configured; never realistic-by-default).
        source = (ROOT / "core" / "risk" / "risk_engine.py").read_text(
            encoding="utf-8")
        self.assertIn("from_settings", source)
        self.assertIn(".compute(", source)


class TestNormalizedStrategyDigest(unittest.TestCase):
    def test_digest_mismatch_remains_explicitly_uncertified(self):
        joined = ""
        for name in STRATEGY_FILES:
            raw = (ROOT / name).read_bytes().replace(b"\r\n", b"\n")
            joined += hashlib.sha256(raw).hexdigest()
        actual = hashlib.sha256(joined.encode()).hexdigest()
        # The archive does not contain the historical source checkout. Do
        # not re-pin the old forensic digest merely to make this test green.
        self.assertNotEqual(actual, NORMALIZED_DIGEST)
        import json
        report = subprocess.run(
            ["python", str(ROOT / "scripts" / "recertify_strategy_digest.py"),
             "--json"], capture_output=True, text=True, cwd=str(ROOT), timeout=60,
        )
        self.assertEqual(report.returncode, 0, report.stderr)
        obj = json.loads(report.stdout)
        self.assertEqual(obj["canonical_digest"], actual)
        self.assertEqual(obj["status"], "BLOCKED")
        self.assertFalse(obj["matches_recorded"])

    def test_only_phase4_files_differ_from_pre_phase4(self):
        probe = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            capture_output=True, text=True, cwd=str(ROOT), timeout=15,
        )
        if probe.returncode != 0 or probe.stdout.strip() != "true":
            self.skipTest("historical ancestry verification requires the original Git checkout")
        out = subprocess.run(
            ["git", "diff", "47fbecd", "HEAD", "--name-only", "--",
             *STRATEGY_FILES],
            capture_output=True, text=True, cwd=str(ROOT), timeout=60,
        )
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(
            sorted(out.stdout.split()),
            ["backtesting/backtester.py", "core/setup/decision_engine.py"],
        )


class TestReconciliationLocalAdditions(unittest.TestCase):
    def test_duplicate_remote_positions_halt(self):
        from core.live.reconciler import Reconciler

        feed = [
            {"side": "LONG", "quantity": 2.0, "entry": 100.0},
            {"side": "LONG", "quantity": 2.0, "entry": 100.0},
        ]
        rec = Reconciler(
            executor=SimpleNamespace(
                positions=lambda: feed))
        local = {"side": "LONG", "quantity": 2.0, "entry": 100.0}
        out = rec.runtime_check(1, 100, local, None)
        self.assertEqual(out["verdict"], "MISMATCH")
        self.assertTrue(rec.halt_new_orders)
        self.assertEqual(rec.drifts[-1]["kind"], "EXTRA_POSITIONS")

    def test_conflicting_snapshots_rederive_from_latest(self):
        import tempfile

        from core.live.reconciler import Reconciler

        with tempfile.TemporaryDirectory() as tmp:
            path = tmp + "/broker_state.json"
            first = Reconciler(executor=None, snapshot_path=path)
            trade = {"direction": "LONG", "entry": 100.0,
                     "stop_loss": 90.0, "take_profit": 160.0,
                     "quantity": 2.0, "entry_time": 1}
            state = first.snapshot_state(True, None, "BTCUSD",
                                         SimpleNamespace(**trade),
                                         1000, "ACKNOWLEDGED", 3)
            self.assertTrue(first.persist(state))
            # Reboot 1: exchange flat -> MISMATCH halts (LOCAL).
            gone = Reconciler(
                executor=SimpleNamespace(
                    positions=lambda: []),
                snapshot_path=path)
            self.assertEqual(
                gone.startup_check(dry_run=False)["verdict"], "MISMATCH")
            # Operator books the close locally (flat snapshot); reboot 2
            # with a flat exchange resumes WITHOUT carrying the old halt.
            flat = Reconciler(executor=None, snapshot_path=path)
            self.assertTrue(flat.persist(flat.snapshot_state(
                False, None, "BTCUSD", None, 2000, None, 4)))
            back = Reconciler(
                executor=SimpleNamespace(
                    positions=lambda: []),
                snapshot_path=path)
            out = back.startup_check(dry_run=False)
            self.assertEqual(out["verdict"], "MATCH")
            self.assertFalse(back.halt_new_orders)


if __name__ == "__main__":
    unittest.main()
