"""
====================================================

QuantEngine

Provider-Universe Smoke Harness (Phase 9P-e)

A reproducible, read-only / PAPER-only verification harness
for the provider-universe operational path. It drives the
EXISTING canonical architecture -- the SAME
UniverseManager + InstrumentRegistry + eligibility cascade
+ DeltaLiquidityProvider + DeltaHistoryProvider +
RealTimeEngine -> SymbolPipeline -> PAPER runtime stack that
production uses -- against real exchange data, and produces a
structured report. It does NOT introduce any new universe /
eligibility / pipeline / subscription / execution component.

Verified path:

    Harness
      -> build_provider_universe_manager  (canonical 9P-d)
      -> build_paper_engine              (canonical 9P-a)
      -> engine.refresh                  (canonical driver)
         -> RefreshScheduler.refresh
            -> manager.refresh_discovery  (real /v2/products)
            -> manager.build_universe     (eligibility cascade)
               -> DeltaLiquidityProvider  (real /v2/tickers)
               -> DeltaHistoryProvider    (real /v2/history/candles)
         -> RealTimeEngine._reconcile
            -> PipelineRegistry           (SymbolPipelines)
            -> MultiSymbolSubscriptionManager.sync
      -> observe eligible cut / statuses
      -> clean bounded shutdown           (PAPER, no live orders)

By default the harness TERMINATES after one discovery ->
universe -> runtime-init -> (optional bounded polls) ->
report pass, with no indefinite loop and no lingering
WebSocket tasks. Every collaborator is injectable so offline
tests drive the exact same code with mocked transports and
zero network.

PROVIDER MODE ONLY: the harness REQUIRES UNIVERSE="provider";
it is not a general runner. It refuses to assemble an explicit
universe (that path is exercised elsewhere) so a test can prove
provider mode was selected and explicit mode was NOT.

LIVE SAFETY (fail closed): the harness never constructs a
live-order execution path. It runs the canonical PaperRuntime
(BrokerEngine dry_run=True) and refuses to run when the
process configuration enables LIVE mode. No Delta API keys are
required (the REST data endpoints are public); none are read
or stored.

Run from the repository root:

    python -m core.runtime.provider_universe_smoke

====================================================
"""

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from config.settings import settings

from core.runtime.paper_main import build_paper_engine
from core.runtime.paper_main import build_provider_universe_manager

# ---------------------------------------------------------------------------
# Error categories (network / API / parse vs. genuine empty eligibility)
# ---------------------------------------------------------------------------

CAT_NETWORK = "NETWORK_UNAVAILABLE"
CAT_API = "API_ERROR"
CAT_PARSE = "PARSE_ERROR"
CAT_NO_INSTRUMENTS = "NO_INSTRUMENTS"
CAT_NO_LIQUIDITY = "NO_LIQUIDITY_DATA"
CAT_NO_HISTORY = "NO_HISTORY_DATA"
CAT_NO_ELIGIBLE = "NO_ELIGIBLE_INSTRUMENTS"
CAT_INIT = "RUNTIME_INITIALIZATION_FAILURE"

DATA_AVAILABLE = "AVAILABLE"
DATA_UNAVAILABLE = "UNAVAILABLE"
DATA_NOT_REQUESTED = "NOT_REQUESTED"


def classify_reason(reason):
    """Classify an eligibility reason into a data-availability bucket so
    a missing-data deny (DATA_UNAVAILABLE) is NEVER collapsed into a
    mere eligibility rejection.

    Returns (bucket, reason) where bucket is one of DATA_AVAILABLE /
    DATA_UNAVAILABLE / DATA_NOT_REQUESTED."""
    if reason in ("ELIGIBLE", None, ""):
        return DATA_AVAILABLE, reason
    if reason == "NO_LIQUIDITY_DATA":
        return DATA_UNAVAILABLE, "NO_LIQUIDITY_DATA"
    if reason == "LOW_LIQUIDITY":
        return DATA_AVAILABLE, "LOW_LIQUIDITY"
    if reason == "NO_HISTORY_DATA":
        return DATA_UNAVAILABLE, "NO_HISTORY_DATA"
    if reason == "INSUFFICIENT_HISTORY":
        return DATA_AVAILABLE, "INSUFFICIENT_HISTORY"
    # NOT_CONFIRMED / NOT_ENABLED / UNKNOWN_TYPE / UNSUPPORTED_TYPE /
    # NO_PRECISION -- lifecycle / gate rejects, not data absence.
    return DATA_NOT_REQUESTED, reason


# ---------------------------------------------------------------------------
# Structured report
# ---------------------------------------------------------------------------


@dataclass
class ProviderUniverseSmokeReport:
    """Deterministic report schema. `to_dict()` is JSON-serializable
    (UTC timestamps, counts, per-symbol buckets, error categories)."""

    started_at: float = 0.0
    finished_at: float = 0.0
    mode: str = "provider"
    timeframe: str = "1m"
    exchange: str = "DELTA"
    policy: Dict[str, Any] = field(default_factory=dict)

    discovery: Dict[str, Any] = field(default_factory=dict)
    liquidity: Dict[str, Any] = field(default_factory=dict)
    history: Dict[str, Any] = field(default_factory=dict)
    eligibility: Dict[str, Any] = field(default_factory=dict)
    runtime: Dict[str, Any] = field(default_factory=dict)
    symbols: Dict[str, Any] = field(default_factory=dict)
    errors: List[Dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "started_at_utc": self._utc(self.started_at),
            "finished_at_utc": self._utc(self.finished_at),
            "mode": self.mode,
            "timeframe": self.timeframe,
            "exchange": self.exchange,
            "policy": self.policy,
            "discovery": self.discovery,
            "liquidity": self.liquidity,
            "history": self.history,
            "eligibility": self.eligibility,
            "runtime": self.runtime,
            "symbols": self.symbols,
            "errors": self.errors,
        }

    @staticmethod
    def _utc(epoch: float) -> Optional[str]:
        if not epoch:
            return None
        try:
            import datetime

            return (
                datetime.datetime.fromtimestamp(
                    epoch, tz=datetime.timezone.utc
                )
                .isoformat()
                .replace("+00:00", "Z")
            )
        except (OverflowError, OSError, ValueError):
            return str(epoch)


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


class ProviderUniverseSmoke:
    """Drives the canonical provider-universe path once and records the
    structural report. Read-only / PAPER-only by construction, and
    provider-mode-only by contract."""

    def __init__(
        self,
        *,
        universe_mode="provider",
        timeframe=None,
        registry=None,
        policy=None,
        liquidity_provider=None,
        history_provider=None,
        transport_factory=None,
        world_factory=None,
        clock=None,
        refresh_interval_seconds=60,
        starting_balance=None,
        prime_liquidity=True,
    ):
        if universe_mode != "provider":
            raise ProviderUniverseSmokeError(
                CAT_INIT,
                "ProviderUniverseSmoke requires universe_mode='provider'; "
                "explicit mode is intentionally not routed here."
            )

        self.universe_mode = universe_mode
        self.timeframe = timeframe or settings.TIMEFRAME
        self.prime_liquidity = prime_liquidity
        self._clock = clock or time.time

        now = self._clock()
        self.report = ProviderUniverseSmokeReport(
            mode=universe_mode,
            timeframe=self.timeframe,
            exchange="DELTA",
            started_at=now,
        )

        # Build the canonical provider-backed manager (9P-d). When no
        # registry/providers are injected the REAL Delta providers are
        # used; the harness holds references for observability.
        self.manager, self.registry, self.liquidity, self.history = (
            build_provider_universe_manager(
                registry=registry,
                policy=policy,
                liquidity_provider=liquidity_provider,
                history_provider=history_provider,
                timeframe=self.timeframe,
            )
        )

        self.transport_factory = transport_factory
        self.world_factory = world_factory
        self.refresh_interval_seconds = refresh_interval_seconds
        self.starting_balance = starting_balance
        self.engine = None

    # ------------------------------------------------------------------

    def run(
        self,
        *,
        client=None,
        normalizer=None,
        poll_steps=0,
        poll_interval_seconds=0.0,
        discovery_passes=1,
    ) -> ProviderUniverseSmokeReport:
        """Execute the bounded verification sequence: prime liquidity ->
        assemble the PAPER engine -> discovery/eligibility/reconcile
        pass(es) (plus optional bounded polls) -> structural report ->
        clean shutdown (always).

        discovery_passes: number of engine.refresh() passes. Default 1
        suits an already-confirmed (ACTIVE) registry; a FRESH registry
        needs >= 2 passes so the Phase 6A confirmation state machine can
        graduate NEWLY_LISTED products to ACTIVE before eligibility).
        The last pass's universe is the one reported."""
        try:
            self._prime_liquidity()
            self._assemble_engine()
            self._run_operational_pass(
                client=client,
                normalizer=normalizer,
                poll_steps=poll_steps,
                poll_interval_seconds=poll_interval_seconds,
                discovery_passes=discovery_passes,
            )
            self._build_report()
            return self.report
        finally:
            self._shutdown()

    # ------------------------------------------------------------------

    def _prime_liquidity(self):
        if not self.prime_liquidity:
            self.report.liquidity["refresh_prime"] = "skipped"
            return
        try:
            ok = self.liquidity.refresh()
        except Exception as error:
            self._record_error(CAT_NETWORK, "liquidity.refresh", error)
            self.report.liquidity["refresh_prime"] = "failed"
            return
        self.report.liquidity["refresh_prime"] = "ok" if ok else "failed"

    # ------------------------------------------------------------------

    def _assemble_engine(self):
        try:
            engine, _manager = build_paper_engine(
                universe_manager=self.manager,
                transport_factory=self.transport_factory,
                world_factory=self.world_factory,
                clock=self._clock,
                timeframe=self.timeframe,
                starting_balance=self.starting_balance,
                refresh_interval_seconds=self.refresh_interval_seconds,
            )
        except Exception as error:
            self._record_error(CAT_INIT, "assemble_engine", error)
            raise ProviderUniverseSmokeError(CAT_INIT, str(error))

        self.engine = engine
        self.report.runtime["mode_selected"] = "provider"

    # ------------------------------------------------------------------

    def _run_operational_pass(self, client, normalizer, poll_steps,
                              poll_interval_seconds, discovery_passes=1):
        if self.engine is None:
            return

        # PAPER-only guard: refuse to run when the process is configured
        # for LIVE execution. Fail closed on any ambiguity.
        if settings.LIVE_MODE and not settings.PAPER_MODE:
            raise ProviderUniverseSmokeError(
                CAT_INIT,
                "LIVE mode detected; harness is PAPER-only and refuses "
                "to run against a live execution configuration.",
            )

        passes = max(1, int(discovery_passes))
        universe = None
        for _ in range(passes):
            universe = self.engine.refresh(
                client=client, normalizer=normalizer,
            )
        self.report.runtime["universe_refresh"] = (
            "ok" if universe is not None else "fail"
        )

        for _ in range(max(0, int(poll_steps))):
            self.engine.poll(client=client, normalizer=normalizer)
            if poll_interval_seconds > 0:
                time.sleep(poll_interval_seconds)

    # ------------------------------------------------------------------

    def _build_report(self):
        report = self.report
        report.policy = self._policy_dict()

        candidates = list(self.registry.discoverable()) if self.registry else []

        # ---- Discovery ----
        report.discovery = {
            "mode": "provider",
            "discovered_total": len(self.registry) if self.registry else 0,
            "considered": len(candidates),
        }
        if not candidates:
            self._record_error(
                CAT_NO_INSTRUMENTS, "discovery", "no instruments discovered"
            )

        universe = (
            getattr(self.engine, "refresh_scheduler", None)
            and getattr(self.engine.refresh_scheduler, "last_universe", None)
        )

        # Surface failures the RefreshScheduler recorded (it catches
        # discovery/build exceptions so the loop survives) so a
        # network/API failure is never misread as "0 eligible".
        scheduler = getattr(self.engine, "refresh_scheduler", None)
        if scheduler is not None:
            report.runtime["discovery_summary"] = getattr(
                scheduler, "last_summary", None
            )
            for error in list(getattr(scheduler, "errors", []) or []):
                self._record_error(
                    CAT_API if not self._is_network_error(error) else CAT_NETWORK,
                    "refresh_scheduler",
                    error,
                )

        # ---- Eligibility ----
        if universe is None or not getattr(universe, "eligible_instruments", None):
            report.eligibility = {
                "finalized": False,
                "eligible": 0,
                "rejected": 0,
                "eligible_symbols": [],
                "reasons": {},
            }
        else:
            reasons = dict(universe.reasons or {})
            eligible_symbols = list(universe.symbols)
            eligible_set = set(eligible_symbols)
            rejected = {
                sym: reason
                for sym, reason in reasons.items()
                if sym not in eligible_set
            }
            report.eligibility = {
                "finalized": True,
                "eligible": len(eligible_symbols),
                "rejected": len(rejected),
                "eligible_symbols": eligible_symbols,
                "reasons": reasons,
            }
            report.runtime["eligible_symbols"] = eligible_symbols

            if not eligible_symbols and candidates:
                # Genuinely empty eligible set is reported, not hidden.
                pass

        eligible_set = set(
            report.runtime.get("eligible_symbols", [])
        )

        # ---- Per-symbol buckets (data vs. eligibility) ----
        for instrument in candidates:
            symbol = getattr(instrument, "symbol", "") or ""
            if not symbol:
                continue
            reason = (universe.reasons or {}).get(symbol) if universe else None
            if symbol in eligible_set:
                bucket, _ = classify_reason("ELIGIBLE")
            elif reason is not None:
                bucket, reason = classify_reason(reason)
            else:
                bucket = DATA_NOT_REQUESTED
            report.symbols[symbol] = {
                "liquidity": self._liquidity_bucket(symbol),
                "history": self._history_bucket(symbol),
                "eligibility": "ELIGIBLE" if symbol in eligible_set else reason,
                "bucket": bucket,
            }

        # ---- Liquidity summary ----
        report.liquidity["provider"] = type(self.liquidity).__name__
        valid = [s for s in report.symbols
                 if report.symbols[s]["liquidity"] == DATA_AVAILABLE]
        report.liquidity["symbols_with_valid_turnover"] = len(valid)
        report.liquidity["symbols_unavailable"] = [
            s for s in report.symbols
            if report.symbols[s]["liquidity"] == DATA_UNAVAILABLE
        ]

        # ---- History summary ----
        report.history["provider"] = type(self.history).__name__
        report.history["timeframe"] = self.timeframe
        report.history["required_bars"] = (
            self.manager.policy.min_history_bars
            if getattr(self.manager, "policy", None) is not None
            else None
        )
        report.history["lookback_days"] = getattr(
            self.history, "lookback_days", None
        )
        report.history["symbols_sufficient"] = [
            s for s in report.symbols
            if report.symbols[s]["history"] == DATA_AVAILABLE
        ]
        report.history["provider_errors"] = [
            str(e) for e in list(getattr(self.history, "errors", []))
        ]

        # ---- Runtime integration ----
        statuses = self.engine.statuses() if self.engine is not None else {}
        report.runtime["runtimes"] = (
            len(self.engine.runtimes) if self.engine else 0
        )
        report.runtime["pipelines"] = (
            len(self.engine.registry._pipelines) if self.engine else 0
        )
        report.runtime["subscribed"] = sorted(statuses.keys())
        report.runtime["paper_only"] = self._paper_confirmed()

        report.finished_at = self._clock()

    # ------------------------------------------------------------------

    def _policy_dict(self):
        policy = getattr(self.manager, "policy", None)
        if policy is None:
            return {}
        return {
            "min_quote_volume_24h": getattr(
                policy, "min_quote_volume_24h", None
            ),
            "min_history_bars": getattr(policy, "min_history_bars", None),
        }

    # ------------------------------------------------------------------

    def _liquidity_bucket(self, symbol):
        try:
            value = self.liquidity.quote_volume_24h(symbol)
        except Exception:
            return DATA_UNAVAILABLE
        return DATA_AVAILABLE if value is not None else DATA_UNAVAILABLE

    # ------------------------------------------------------------------

    def _history_bucket(self, symbol):
        try:
            count = self.history.history_bars(symbol, self.timeframe)
        except Exception:
            count = None
        return DATA_AVAILABLE if count is not None else DATA_UNAVAILABLE

    # ------------------------------------------------------------------

    def _paper_confirmed(self):
        """Conservative PAPER confirmation: every runtime's BrokerEngine
        runs dry_run=True. No eligible instruments is not a PAPER
        failure; a live-order executor is."""
        if self.engine is None:
            return False
        runtimes = list(self.engine.runtimes.values())
        if not runtimes:
            return True
        return all(
            getattr(getattr(rt, "engine", None), "dry_run", True)
            is True
            for rt in runtimes
        )

    # ------------------------------------------------------------------

    def _record_error(self, category, stage, error):
        self.report.errors.append(
            {
                "category": category,
                "stage": stage,
                "detail": str(error),
            }
        )

    # ------------------------------------------------------------------

    @staticmethod
    def _is_network_error(error):
        text = str(error).lower()
        return any(
            token in text
            for token in (
                "connection", "timeout", "timed out", "network",
                "refused", "unreachable", "reset",
            )
        )

    # ------------------------------------------------------------------

    def _shutdown(self):
        if self.engine is not None:
            try:
                self.engine.stop()
            except Exception as error:
                self._record_error(CAT_INIT, "engine.stop", error)


class ProviderUniverseSmokeError(Exception):
    """Raised when the harness itself cannot proceed (config / runtime
    assembly failure). Carries a machine-readable category."""

    def __init__(self, category, detail):
        super().__init__(detail)
        self.category = category


# ---------------------------------------------------------------------------
# Runnable entry point (bounded, terminating)
# ---------------------------------------------------------------------------


def main(argv=None):
    """CLI entry: `python -m core.runtime.provider_universe_smoke`.

    BOUNDED live smoke: filters real Delta product discovery to
    `--symbols` (default settings.SYMBOLS) so the run exercises the
    REAL providers against a small, reproducible symbol set instead of
    the full ~300-product catalog (avoiding a per-symbol history REST
    explosion). Runs discovery_passes (default 2) so the Phase 6A
    confirmation state machine can graduate products to ACTIVE, then a
    report pass with the REAL web socket transport and clean shutdown.

    Never places live orders; read-only / PAPER-only. Exits 0 on
    success, 2 on a harness-error category, 3 on NO_ELIGIBLE (a
    genuinely empty eligible universe -- reported, not a harness fault)."""
    import argparse
    import json

    from core.registry.instrument_registry import InstrumentRegistry
    from data.delta.product_client import ProductClient

    parser = argparse.ArgumentParser(
        description="Phase 9P-e provider-universe smoke harness (PAPER-only)."
    )
    parser.add_argument(
        "--timeframe", default=None,
        help="timeframe e.g. 1m, 5m, 1h (default: settings.TIMEFRAME)",
    )
    parser.add_argument(
        "--polls", type=int, default=0,
        help="bounded number of extra poll steps (0 = none)",
    )
    parser.add_argument(
        "--interval", type=int, default=60,
        help="RefreshScheduler interval seconds (default 60)",
    )
    parser.add_argument(
        "--passes", type=int, default=2,
        help="discovery passes (fresh registry needs >= 2 to ACTIVE)",
    )
    parser.add_argument(
        "--symbols", default=None,
        help="comma-separated symbol filter for a bounded smoke "
             "(default: settings.SYMBOLS)",
    )
    parser.add_argument(
        "--min-volume", default=None,
        help="optional MIN_QUOTE_VOLUME_24H override (float)",
    )
    parser.add_argument(
        "--min-bars", default=None,
        help="optional MIN_HISTORY_BARS override (int)",
    )
    args = parser.parse_args(argv)

    if args.min_volume is not None:
        settings.MIN_QUOTE_VOLUME_24H = args.min_volume
    if args.min_bars is not None:
        settings.MIN_HISTORY_BARS = args.min_bars

    symbols = [
        s.strip()
        for s in (args.symbols or ",".join(settings.SYMBOLS)).split(",")
        if s and s.strip()
    ]

    # Bounded real discovery: one real /v2/products call, filtered to the
    # chosen symbols in-memory (reproducible, avoids the full catalog).
    class _BoundedDiscoveryClient:
        def __init__(self, inner, keep):
            self.inner = inner
            self.keep = set(keep)

        def fetch(self):
            rows = self.inner.fetch()
            return [r for r in rows if r.get("symbol") in self.keep]

    discovery_client = _BoundedDiscoveryClient(ProductClient(), symbols)

    harness = ProviderUniverseSmoke(
        universe_mode="provider",
        timeframe=args.timeframe,
        registry=InstrumentRegistry(),
        refresh_interval_seconds=args.interval,
    )
    report = harness.run(
        client=discovery_client,
        poll_steps=args.polls,
        discovery_passes=args.passes,
    )
    print(json.dumps(report.to_dict(), indent=2, default=str))

    if report.errors and any(
        e["category"] in (CAT_INIT, CAT_NETWORK, CAT_API, CAT_PARSE)
        for e in report.errors
    ):
        return 2
    if report.eligibility.get("eligible", 0) == 0 and report.runtime.get(
        "universe_refresh"
    ) == "ok":
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
