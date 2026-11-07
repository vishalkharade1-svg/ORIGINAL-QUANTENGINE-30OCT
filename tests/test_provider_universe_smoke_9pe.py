"""
====================================================

QuantEngine

Provider-Universe Smoke Harness (Phase 9P-e) offline tests

Validates the Phase 9P-e smoke harness OFFLINE (mocked Delta
responses + fake transports, zero network) against the EXACT
canonical path it drives:

    harness -> build_provider_universe_manager ->
    build_paper_engine -> engine.refresh (discovery ->
    eligibility -> reconcile -> subscriptions) -> report ->
    clean shutdown.

Uses the REAL 9P-d providers (DeltaLiquidityProvider /
DeltaHistoryProvider) with mocked transports so the real
provider code is exercised, not a stand-in.

Covers the 15 required verification points: provider-mode
selection, no accidental explicit mode, real-provider
construction, live-data-success representation, network/API/
history failure classification, empty eligible universe,
eligible-cut propagation to the runtime, PAPER-only guard,
bounded shutdown, no dangling resources, structured report
generation, and deterministic report structure for identical
fixtures.

Stdlib only.

====================================================
"""

import unittest

from core.registry.instrument import Instrument
from core.registry.instrument_registry import InstrumentRegistry
from core.registry.product_types import PRODUCT_STATE_NEWLY_LISTED
from core.universe.liquidity_provider import DeltaLiquidityProvider
from core.universe.history_provider import DeltaHistoryProvider
from core.runtime.provider_universe_smoke import (
    ProviderUniverseSmoke,
    ProviderUniverseSmokeError,
    classify_reason,
    DATA_AVAILABLE,
    DATA_UNAVAILABLE,
    CAT_INIT,
    CAT_NETWORK,
)


# ---------------------------------------------------------------------------
# Fakes (offline, no network)
# ---------------------------------------------------------------------------


class FakeTickerTransport:
    """Mirrors DeltaREST.get(endpoint, params=None) for the providers."""

    def __init__(self, tickers=None, error=None):
        self.tickers = tickers or {}
        self.error = error
        self.calls = []

    def get(self, endpoint, params=None, headers=None):
        self.calls.append(endpoint)
        if self.error is not None:
            raise self.error
        rows = [
            {"symbol": sym, "turnover_usd": str(val)}
            for sym, val in self.tickers.items()
        ]
        return {"result": rows}


class FakeHistory:
    """Mirrors DeltaHistory.candles(symbol, resolution, days=...)."""

    def __init__(self, counts=None, error=None):
        self.counts = counts or {}
        self.error = error
        self.calls = []

    def candles(self, symbol, resolution="1m", days=None, **kwargs):
        self.calls.append((symbol, resolution, days))
        if self.error is not None:
            raise self.error
        count = self.counts.get(symbol, 0)
        return [None] * count


class FakeTransport:
    """Mirrors the Phase 6D transport contract: subscribe /
    unsubscribe / close. Records calls so the test can assert
    clean, bounded shutdown."""

    def __init__(self):
        self._routes = {}
        self.subscribe_calls = {}
        self.unsubscribed = []
        self.closed = False

    def subscribe(self, symbol, on_candle, on_down):
        self.subscribe_calls[symbol] = self.subscribe_calls.get(symbol, 0) + 1
        self._routes[symbol] = (on_candle, on_down)

    def unsubscribe(self, symbol):
        self._routes.pop(symbol, None)
        self.unsubscribed.append(symbol)

    def close(self):
        self.closed = True
        self._routes.clear()


class FakeClock:
    def __init__(self, now=0.0):
        self.now = float(now)

    def __call__(self):
        return self.now

    def advance(self, delta):
        self.now += delta


class ScriptedWorld:
    """Minimal pipeline-compatible world (BrokerEngine contract:
    .context / .on_candle / .reset)."""

    def __init__(self, context):
        self.context = context
        self.on_candle_calls = 0

    def reset(self):
        self.on_candle_calls = 0

    def on_candle(self, event):
        self.on_candle_calls += 1
        if event is not None and getattr(event, "candle", None) is not None:
            self.context.add_candle(event.candle)


# ---------------------------------------------------------------------------
# Product / instrument helpers (mirror the 6B discovery fixtures)
# ---------------------------------------------------------------------------


def product_row(product_id, symbol, contract_type="perpetual_futures"):
    return {
        "id": product_id,
        "symbol": symbol,
        "contract_type": contract_type,
        "underlying_asset": {"id": 1, "symbol": symbol[:3]},
        "quoting_asset": {"id": 2, "symbol": "USDT"},
        "tick_size": 0.5,
        "contract_value": 1.0,
        "minimum_order_size": 0.001,
        "price_precision": 2,
        "contract_value_precision": 3,
        "is_delisted": False,
        "is_disabled": False,
        "is_unlisted": False,
        "state": "live",
    }


def make_instrument(symbol, instrument_id=None):
    return Instrument(
        instrument_id=instrument_id or symbol,
        symbol=symbol,
        exchange="DELTA",
        product_type="PERPETUAL",
        underlying_asset=symbol,
        quote_asset="USDT",
        tick_size=0.5,
        quantity_step=1.0,
        minimum_quantity=0.001,
        trading_enabled=True,
        state=PRODUCT_STATE_NEWLY_LISTED,
    )


def promote_to_active(registry, *instruments):
    for inst in instruments:
        registry.upsert(inst)
    keys = [i.key for i in instruments]
    registry.mark_present(keys)
    registry.mark_present(keys)


class _FakeDiscoveryClient:
    """Mirrors ProductClient.fetch() -> list of raw product rows."""

    def __init__(self, rows, error=None):
        self.rows = rows
        self.error = error
        self.calls = 0

    def fetch(self):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return list(self.rows)


# ---------------------------------------------------------------------------
# Shared harness builder
# ---------------------------------------------------------------------------


def build_harness(
    symbols=("BTCUSDT", "ETHUSDT"),
    tickers=None,
    history=None,
    policy=None,
    discovery_error=None,
    ticker_error=None,
    history_error=None,
    live_mode=False,
    policy_overrides=None,
):
    """Assemble an offline ProviderUniverseSmoke over real providers
    with fake transports/history, a pre-populated ACTIVE registry, and
    a fake discovery client. Returns (harness, fakes_dict)."""
    from core.universe.universe_policy import UniversePolicy

    policy = policy or UniversePolicy(
        min_quote_volume_24h=1_000_000.0,
        min_history_bars=300,
    )
    policy_overrides = policy_overrides or {}

    instruments = [make_instrument(s) for s in symbols]
    rows = [product_row(i + 1, s) for i, s in enumerate(symbols)]
    registry = InstrumentRegistry()
    promote_to_active(registry, *instruments)

    default_tickers = {s: 5_000_000.0 for s in symbols}
    default_history = {s: 1440 for s in symbols}
    tickers = tickers if tickers is not None else default_tickers
    history = history if history is not None else default_history

    ticker_transport = FakeTickerTransport(
        tickers=tickers, error=ticker_error,
    )
    liquidity = DeltaLiquidityProvider(transport=ticker_transport)

    fake_history = FakeHistory(counts=history, error=history_error)
    history_provider = DeltaHistoryProvider(history=fake_history)

    discovery_client = _FakeDiscoveryClient(rows, error=discovery_error)

    ws_transport = FakeTransport()
    clock = FakeClock(now=1000.0)

    harness = ProviderUniverseSmoke(
        universe_mode="provider",
        registry=registry,
        policy=policy,
        liquidity_provider=liquidity,
        history_provider=history_provider,
        transport_factory=lambda: ws_transport,
        world_factory=ScriptedWorld,
        clock=clock,
        timeframe="1m",
        refresh_interval_seconds=0,
    )
    return harness, {
        "registry": registry,
        "liquidity": liquidity,
        "history": history_provider,
        "fake_history": fake_history,
        "discovery": discovery_client,
        "ws": ws_transport,
        "clock": clock,
        "saved": {
            "LIVE_MODE": __import__(
                "config.settings", fromlist=["settings"]
            ).settings.LIVE_MODE,
            "PAPER_MODE": __import__(
                "config.settings", fromlist=["settings"]
            ).settings.PAPER_MODE,
        },
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestModeSelection(unittest.TestCase):

    def test_provider_mode_required(self):
        with self.assertRaises(ProviderUniverseSmokeError) as ctx:
            ProviderUniverseSmoke(universe_mode="explicit")
        self.assertEqual(ctx.exception.category, CAT_INIT)

    def test_provider_mode_selected_not_explicit(self):
        harness, fakes = build_harness()
        report = harness.run(
            client=fakes["discovery"], poll_steps=0,
        )
        self.assertEqual(report.runtime["mode_selected"], "provider")
        self.assertNotEqual(report.runtime["mode_selected"], "explicit")


class TestRealProviderConstruction(unittest.TestCase):

    def test_real_providers_used(self):
        harness, fakes = build_harness()
        self.assertIsInstance(harness.liquidity, DeltaLiquidityProvider)
        self.assertIsInstance(harness.history, DeltaHistoryProvider)
        self.assertIs(harness.liquidity, fakes["liquidity"])
        self.assertIs(harness.history, fakes["history"])


class TestLiveDataSuccess(unittest.TestCase):

    def test_eligible_cut_propates_to_runtime(self):
        harness, fakes = build_harness(symbols=("BTCUSDT", "ETHUSDT"))
        report = harness.run(client=fakes["discovery"], poll_steps=0)

        self.assertTrue(report.eligibility["finalized"])
        self.assertEqual(
            set(report.eligibility["eligible_symbols"]),
            {"BTCUSDT", "ETHUSDT"},
        )
        self.assertEqual(report.eligibility["eligible"], 2)
        # buckets AVAILABLE
        for sym in ("BTCUSDT", "ETHUSDT"):
            self.assertEqual(
                report.symbols[sym]["liquidity"], DATA_AVAILABLE,
            )
            self.assertEqual(
                report.symbols[sym]["history"], DATA_AVAILABLE,
            )
            self.assertEqual(report.symbols[sym]["eligibility"], "ELIGIBLE")
        # runtime receives the cut
        self.assertEqual(report.runtime["runtimes"], 2)
        self.assertEqual(set(report.runtime["subscribed"]),
                         {"BTCUSDT", "ETHUSDT"})
        self.assertEqual(report.runtime["eligible_symbols"], ["BTCUSDT", "ETHUSDT"])
        # both subscriptions were started on the fake transport
        self.assertEqual(
            set(fakes["ws"].subscribe_calls.keys()),
            {"BTCUSDT", "ETHUSDT"},
        )


class TestFailureClassification(unittest.TestCase):

    def test_network_unavailable_discovery(self):
        harness, fakes = build_harness(
            discovery_error=RuntimeError("connection refused"),
        )
        report = harness.run(client=fakes["discovery"], poll_steps=0)
        cats = {e["category"] for e in report.errors}
        self.assertTrue(
            cats & {CAT_NETWORK, CAT_INIT, "API_ERROR"},
            msg=f"unexpected cats {cats}",
        )

    def test_ticker_api_failure_classified(self):
        harness, fakes = build_harness(
            ticker_error=RuntimeError("ticker 429"),
        )
        report = harness.run(client=fakes["discovery"], poll_steps=0)
        # liquidity refresh failed; symbols bucket UNAVAILABLE (not eligible)
        self.assertEqual(report.liquidity["refresh_prime"], "failed")
        for sym in ("BTCUSDT", "ETHUSDT"):
            self.assertEqual(report.symbols[sym]["liquidity"], DATA_UNAVAILABLE)
            self.assertNotEqual(report.symbols[sym]["eligibility"], "ELIGIBLE")

    def test_history_failure_classified(self):
        harness, fakes = build_harness(
            history_error=RuntimeError("history timeout"),
        )
        report = harness.run(client=fakes["discovery"], poll_steps=0)
        self.assertTrue(report.history["provider_errors"])
        for sym in ("BTCUSDT", "ETHUSDT"):
            self.assertEqual(report.symbols[sym]["history"], DATA_UNAVAILABLE)


class TestEmptyEligibleUniverse(unittest.TestCase):

    def test_empty_universe_reported_not_hidden(self):
        # all volumes below the threshold -> genuinely 0 eligible
        harness, fakes = build_harness(
            tickers={"BTCUSDT": 100.0, "ETHUSDT": 50.0},
        )
        report = harness.run(client=fakes["discovery"], poll_steps=0)
        self.assertTrue(report.eligibility["finalized"])
        self.assertEqual(report.eligibility["eligible"], 0)
        self.assertEqual(report.eligibility["eligible_symbols"], [])
        # rejection reason visible, not collapsed to "no data"
        self.assertIn("BTCUSDT", report.symbols)
        self.assertNotEqual(report.symbols["BTCUSDT"]["eligibility"], "ELIGIBLE")


class TestClassificationHelper(unittest.TestCase):

    def test_data_vs_eligibility_not_collapsed(self):
        bucket, reason = classify_reason("NO_LIQUIDITY_DATA")
        self.assertEqual(bucket, DATA_UNAVAILABLE)
        bucket, reason = classify_reason("INSUFFICIENT_HISTORY")
        self.assertEqual(bucket, DATA_AVAILABLE)
        bucket, reason = classify_reason("NOT_CONFIRMED")
        self.assertEqual(bucket, "NOT_REQUESTED")


class TestRuntimeSafety(unittest.TestCase):

    def test_paper_only_guard(self):
        import config.settings as cs

        original = (
            cs.settings.LIVE_MODE, cs.settings.PAPER_MODE,
        )
        try:
            cs.settings.LIVE_MODE = True
            cs.settings.PAPER_MODE = False
            harness, fakes = build_harness(live_mode=True)
            with self.assertRaises(ProviderUniverseSmokeError):
                harness.run(client=fakes["discovery"], poll_steps=0)
        finally:
            cs.settings.LIVE_MODE, cs.settings.PAPER_MODE = original

    def test_paper_confirmed_true(self):
        harness, fakes = build_harness()
        report = harness.run(client=fakes["discovery"], poll_steps=0)
        self.assertTrue(report.runtime["paper_only"])


class TestShutdown(unittest.TestCase):

    def test_clean_bounded_shutdown(self):
        harness, fakes = build_harness()
        report = harness.run(client=fakes["discovery"], poll_steps=0)
        self.assertTrue(fakes["ws"].closed)
        self.assertEqual(report.runtime["universe_refresh"], "ok")

    def test_no_dangling_workers_after_shutdown(self):
        harness, fakes = build_harness()
        harness.run(client=fakes["discovery"], poll_steps=0)
        # engine stopped => subscription manager has no workers left
        self.assertEqual(len(harness.engine.subscriptions._workers), 0)


class TestConfirmationPasses(unittest.TestCase):
    """A FRESH (empty) registry needs >= 2 discovery passes for the
    Phase 6A state machine to graduate NEWLY_LISTED -> ACTIVE before
    eligibility. This mirrors the real bounded CLI smoke path."""

    def test_fresh_registry_graduates_and_eligible_with_two_passes(self):
        from core.runtime.provider_universe_smoke import (
            ProviderUniverseSmoke,
        )

        symbols = ("BTCUSDT", "ETHUSDT")
        rows = [product_row(i + 1, s) for i, s in enumerate(symbols)]
        discovery_client = _FakeDiscoveryClient(rows)
        registry = InstrumentRegistry()  # fresh, empty

        ticker_transport = FakeTickerTransport(
            tickers={s: 5_000_000.0 for s in symbols},
        )
        liquidity = DeltaLiquidityProvider(transport=ticker_transport)
        fake_history = FakeHistory(counts={s: 1440 for s in symbols})
        history_provider = DeltaHistoryProvider(history=fake_history)
        ws_transport = FakeTransport()

        harness = ProviderUniverseSmoke(
            universe_mode="provider",
            registry=registry,
            liquidity_provider=liquidity,
            history_provider=history_provider,
            transport_factory=lambda: ws_transport,
            world_factory=ScriptedWorld,
            clock=FakeClock(now=1000.0),
            timeframe="1m",
        )
        report = harness.run(
            client=discovery_client,
            poll_steps=0,
            discovery_passes=2,
        )
        self.assertEqual(
            set(report.eligibility["eligible_symbols"]), set(symbols),
        )
        self.assertEqual(report.eligibility["eligible"], 2)
        # final pass universe propagated to the runtime
        self.assertEqual(report.runtime["runtimes"], 2)
        self.assertTrue(ws_transport.closed)

    def test_single_pass_on_fresh_registry_yields_zero_eligible(self):
        from core.runtime.provider_universe_smoke import (
            ProviderUniverseSmoke,
        )

        symbols = ("BTCUSDT",)
        rows = [product_row(1, "BTCUSDT")]
        discovery_client = _FakeDiscoveryClient(rows)
        registry = InstrumentRegistry()
        liquidity = DeltaLiquidityProvider(
            transport=FakeTickerTransport(tickers={"BTCUSDT": 5e6}),
        )
        history_provider = DeltaHistoryProvider(
            history=FakeHistory(counts={"BTCUSDT": 1440}),
        )
        harness = ProviderUniverseSmoke(
            universe_mode="provider",
            registry=registry,
            liquidity_provider=liquidity,
            history_provider=history_provider,
            transport_factory=lambda: FakeTransport(),
            world_factory=ScriptedWorld,
            clock=FakeClock(now=1000.0),
            timeframe="1m",
        )
        report = harness.run(
            client=discovery_client, poll_steps=0, discovery_passes=1,
        )
        # first sighting is NEWLY_LISTED -> NOT_CONFIRMED -> 0 eligible
        self.assertEqual(report.eligibility["eligible"], 0)
        self.assertIn(
            "NOT_CONFIRMED",
            {v["eligibility"] for v in report.symbols.values()},
        )


class TestReport(unittest.TestCase):

    def test_structured_report_generation(self):
        harness, fakes = build_harness()
        report = harness.run(client=fakes["discovery"], poll_steps=0)
        d = report.to_dict()
        for key in (
            "started_at_utc", "mode", "timeframe", "policy",
            "discovery", "liquidity", "history", "eligibility",
            "runtime", "symbols", "errors",
        ):
            self.assertIn(key, d)
        self.assertTrue(d["started_at_utc"])
        self.assertTrue(d["finished_at_utc"])

    def test_deterministic_report_structure(self):
        # identical fixtures -> identical structure (ignore timestamps)
        r1 = build_harness()
        rep1 = r1[0].run(client=r1[1]["discovery"], poll_steps=0).to_dict()
        r2 = build_harness()
        rep2 = r2[0].run(client=r2[1]["discovery"], poll_steps=0).to_dict()
        for key in ("mode", "timeframe", "policy", "discovery",
                    "liquidity", "history", "eligibility", "runtime",
                    "symbols", "errors"):
            self.assertEqual(rep1[key], rep2[key], msg=key)


if __name__ == "__main__":
    unittest.main()
