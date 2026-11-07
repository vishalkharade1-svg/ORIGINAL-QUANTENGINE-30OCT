"""
====================================================

QuantEngine

Phase 9C -- Counterfactual Opportunity Simulator tests

Proves the deterministic research-only simulator:

   * canonical entry-model routing (production deciders, NOT a
     reimplementation) for LIMIT_RETEST / MARKET_CONFIRMATION /
     BREAKOUT_CONTINUATION
   * no lookahead (decision -> canonical decision -> fill ->
     future candles only)
   * stop-before-target parity with TradeSimulator.update
   * MAE / MFE / R / PnL parity (R from ACTUAL fill, matching the
     canonical _r_multiple contract)
   * explicit outcome horizon (outcome_bars) -- default None ==
     production TradeSimulator holding horizon
   * explicit / strict source extraction (a present 0.0 is not
     "missing")
   * entry expiry bounding
   * COUNTERFACTUAL provenance; NO production ledger mutation
   * original OpportunityRecord never mutated
   * deterministic experiment ids; grid isolation (no blending)
   * opportunity recovery: rejected / unfilled opportunities CAN be
     recovered under an explicitly-specified alternative config

Stdlib only; offline; deterministic.
====================================================
"""

import copy
import unittest

from core.research.counterfactual import (
    CounterfactualConfig,
    OpportunitySimulator,
    CounterfactualRunner,
    classify_opportunity,
    FILLED,
    REJECTED,
    MISSED_CONTINUATION,
    INVALIDATED,
    ENTRY_NOT_REACHED,
    NON_EVALUABLE,
    COUNTERFACTUAL,
)
from core.research.journal import OpportunityRecord


# ==========================================================
# Fixtures
# ==========================================================


class Candle:
    __slots__ = ("open", "high", "low", "close", "timestamp")

    def __init__(self, o, h, l, c, ts):
        self.open = o
        self.high = h
        self.low = l
        self.close = c
        self.timestamp = ts


def record(canonical, bar=0, direction="BULLISH", terminal="ORDER_NOT_CREATED",
           entry=100.0, stop=98.0, target=104.0, rr=2.0, reasons=None,
           order=None):
    return OpportunityRecord(
        canonical_id=canonical,
        exchange="TESTEX",
        instrument_id=canonical,
        timeframe="1m",
        direction=direction,
        strategy="BREAKOUT_CONTINUATION",
        setup_id=canonical,
        setup={
            "entry": entry, "stop_loss": stop, "take_profit": target,
            "risk_reward": rr, "bar": bar, "atr": 4.0,
            "rejection_reasons": (reasons or []),
        },
        order=order or {},
        terminal_outcome=terminal,
    )


def cfg(**params):
    defaults = {
        "entry_model": "BREAKOUT_CONTINUATION",
        "rr": 2.0,
        "expiry": None,
        "stop_mode": "EXISTING_STOP",
        "target_mode": "FIXED_RR",
    }
    defaults.update(params)
    outcome = defaults.pop("outcome_bars", None)
    baseline = defaults.pop("baseline_id", "baseline")
    return CounterfactualConfig(params=defaults, outcome_bars=outcome,
                                baseline_id=baseline)


# BREAKOUT WIN (trigger bar1, fill bar2 open, target hit on bar2)
BREAKOUT_WIN = [
    Candle(100.0, 101.0, 99.0, 100.0, 0),
    Candle(100.0, 101.0, 99.0, 101.0, 1),   # trigger: high>E close>E
    Candle(101.0, 105.0, 100.0, 104.0, 2),  # open 101 fill; target 104
]

# BREAKOUT LOSS (fill bar2 open, same-bar stop)
BREAKOUT_LOSS = [
    Candle(100.0, 101.0, 99.0, 100.0, 0),
    Candle(100.0, 101.0, 99.0, 101.0, 1),   # trigger
    Candle(101.0, 102.0, 97.0, 98.0, 2),    # open 101 fill; low <= 98
]

# BREAKOUT WIN with a multi-bar hold
BREAKOUT_WIN_HOLD = [
    Candle(100.0, 101.0, 99.0, 100.0, 0),
    Candle(100.0, 102.0, 99.0, 101.0, 1),   # trigger
    Candle(101.0, 102.0, 100.0, 101.0, 2),  # open 101 fill; no exit yet
    Candle(102.0, 106.0, 101.0, 105.0, 3),  # hits target 104
]

# BREAKOUT trigger on last candle -> NO_EXECUTABLE_BAR
BREAKOUT_NO_EXEC = [
    Candle(100.0, 101.0, 99.0, 100.0, 0),
    Candle(100.0, 101.0, 99.0, 101.0, 1),   # trigger; entry_bar=2 >= len
]

# LIMIT WIN (fill bar1 at 100, target on bar2)
LIMIT_WIN = [
    Candle(100.0, 101.0, 99.0, 100.0, 0),   # decision bar
    Candle(100.0, 101.0, 99.0, 101.0, 1),   # touch: low<=100<=high
    Candle(101.0, 105.0, 100.0, 104.0, 2),
]

# LIMIT same-candle stop/target collision -> STOP wins
LIMIT_COLLISION = [
    Candle(100.0, 101.0, 99.0, 100.0, 0),
    Candle(100.0, 101.0, 99.0, 101.0, 1),   # fill at 100 (no exit)
    Candle(100.0, 106.0, 97.0, 105.0, 2),   # low<=98 AND high>=104
]

# MARKET WIN (fill at trigger close, target on next bar)
MARKET_WIN = [
    Candle(100.0, 101.0, 99.0, 100.0, 0),   # decision bar
    Candle(99.0, 101.0, 99.0, 101.0, 1),    # reached + closed beyond -> fill 101
    Candle(101.0, 105.0, 100.0, 104.0, 2),
]

# Outcome-horizon sequence: LIMIT fill at bar1; no exit bar2; target bar3
HORIZON = [
    Candle(100.0, 101.0, 99.0, 100.0, 0),   # decision bar
    Candle(100.0, 101.0, 99.0, 101.0, 1),   # fill 100; no exit
    Candle(101.0, 103.0, 100.0, 102.0, 2),  # low100>98 high103<104
    Candle(102.0, 106.0, 101.0, 105.0, 3),  # target 104 hit
]

# Entry-expiry sequence: LIMIT touch only at bar2 (never bar1)
EXPIRY = [
    Candle(100.0, 101.0, 99.0, 100.0, 0),   # decision bar
    Candle(100.0, 102.0, 101.0, 101.0, 1),  # no touch (low 101 > 100)
    Candle(99.0, 101.0, 99.0, 100.0, 2),    # touch: low<=100<=high (low>98)
    Candle(100.0, 105.0, 100.0, 104.0, 3),
]

# Recovery: LIMIT never touches (all lows > 100); BREAKOUT triggers
RECOVERY = [
    Candle(100.0, 101.0, 99.0, 100.0, 0),   # decision bar
    Candle(101.0, 102.0, 100.5, 101.5, 1),  # low100.5>100 (no limit touch);
                                            # high>100 close>100 (breakout)
    Candle(101.5, 105.0, 101.0, 104.0, 2),  # open 101.5 fill; target 104
]


def simulate(rec, config, candles=None):
    return OpportunitySimulator().simulate(rec, config, candles or BREAKOUT_WIN)


# ==========================================================
# Configuration contract
# ==========================================================


class TestCounterfactualConfig(unittest.TestCase):

    def test_unknown_param_fails_loudly(self):
        with self.assertRaises(ValueError):
            CounterfactualConfig(params={"entry_model": "LIMIT_RETEST",
                                         "not_a_real_field": 1})

    def test_unsupported_entry_model_fails_loudly(self):
        with self.assertRaises(ValueError):
            CounterfactualConfig(
                params={"entry_model": "FVG_RETRACE"}
            )
        with self.assertRaises(ValueError):
            CounterfactualConfig(
                params={"entry_model": "DISPLACEMENT_RETEST"}
            )

    def test_outcome_bars_validation(self):
        self.assertIsNone(cfg().outcome_bars)
        self.assertEqual(cfg(outcome_bars=5).outcome_bars, 5)
        for bad in (0, -1, "5", 2.5):
            with self.assertRaises(ValueError):
                cfg(outcome_bars=bad)

    def test_experiment_id_deterministic_and_distinct(self):
        a1 = cfg(rr=2.0, expiry=10).experiment_id()
        a2 = cfg(rr=2.0, expiry=10).experiment_id()
        b = cfg(rr=2.0, expiry=20).experiment_id()
        c = cfg(rr=3.0, expiry=10).experiment_id()
        d = cfg(rr=3.0, expiry=20).experiment_id()
        self.assertEqual(a1, a2)
        self.assertEqual(len({a1, b, c, d}), 4)

    def test_outcome_bars_in_identity(self):
        self.assertNotEqual(
            cfg(rr=2.0).experiment_id(),
            cfg(rr=2.0, outcome_bars=10).experiment_id(),
        )

    def test_config_preserved_after_simulation(self):
        config = cfg(entry_model="LIMIT_RETEST", rr=2.0, expiry=5)
        before = config.to_dict()
        simulate(record("a"), config, LIMIT_WIN)
        self.assertEqual(config.to_dict(), before)


# ==========================================================
# Strict source extraction -- an explicit zero is NOT missing
# ==========================================================


class TestStrictSourceExtraction(unittest.TestCase):

    def test_explicit_zero_value_is_present(self):
        rec = OpportunityRecord(
            canonical_id="z", direction="BULLISH",
            setup={"entry": 0.0, "stop_loss": 0.5, "take_profit": 1.5,
                   "bar": 0, "atr": 0.0},
            order={"entry_price": 0.0},
            terminal_outcome="EXPIRED",
        )
        src = OpportunitySimulator()._source(rec)
        self.assertEqual(src["entry"], 0.0)      # not treated as missing
        self.assertEqual(src["atr"], 0.0)        # present, zero
        self.assertEqual(src["decision_bar"], 0)

    def test_missing_fields_fall_through(self):
        rec = OpportunityRecord(
            canonical_id="m", direction="BULLISH",
            setup={"entry": 10.0, "bar": 0},
        )
        src = OpportunitySimulator()._source(rec)
        self.assertEqual(src["entry"], 10.0)
        self.assertIsNone(src["stop"])           # genuinely absent
        self.assertIsNone(src["target"])


# ==========================================================
# Canonical entry-model routing (production deciders)
# ==========================================================


class TestCanonicalEntryRouting(unittest.TestCase):

    def test_limit_retest_fills_at_resting_entry(self):
        out = simulate(record("l"), cfg(entry_model="LIMIT_RETEST"), LIMIT_WIN)
        self.assertTrue(out.filled)
        self.assertEqual(out.entry_price, 100.0)   # resting limit fill
        self.assertEqual(out.fill_bar, 1)
        self.assertEqual(out.exit_bar, 2)
        self.assertEqual(out.result, "WIN")
        self.assertEqual(out.exit_price, 104.0)

    def test_market_confirmation_fills_at_close(self):
        out = simulate(record("m"), cfg(entry_model="MARKET_CONFIRMATION"),
                       MARKET_WIN)
        self.assertTrue(out.filled)
        self.assertEqual(out.entry_price, 101.0)  # trigger close
        self.assertEqual(out.result, "WIN")

    def test_breakout_fills_next_bar_open(self):
        out = simulate(record("b"), cfg(entry_model="BREAKOUT_CONTINUATION"),
                       BREAKOUT_WIN)
        self.assertTrue(out.filled)
        self.assertEqual(out.fill_bar, 2)       # trigger bar1 -> bar2
        self.assertEqual(out.entry_price, 101.0)  # open of bar2
        self.assertEqual(out.bars_to_entry, 2)

    def test_breakout_no_executable_bar_distinct(self):
        out = simulate(record("n"), cfg(entry_model="BREAKOUT_CONTINUATION"),
                       BREAKOUT_NO_EXEC)
        self.assertFalse(out.filled)
        self.assertFalse(out.entry_reached)
        self.assertEqual(out.exit_reason, "NO_EXECUTABLE_BAR")

    def test_no_entry_is_entry_not_reached(self):
        rec = OpportunityRecord(
            canonical_id="x", direction="BULLISH",
            setup={"entry": 50.0, "bar": 0},
            terminal_outcome="EXPIRED",
        )
        out = simulate(rec, cfg(entry_model="LIMIT_RETEST"), LIMIT_WIN)
        self.assertFalse(out.filled)
        self.assertFalse(out.entry_reached)
        self.assertEqual(out.exit_reason, "ENTRY_NOT_REACHED")

    def test_unsupported_mode_defensive_non_evaluable(self):
        # Config rejects FVG_RETRACE at construction; the simulator ALSO
        # defends (never invents behavior) if handed one directly.
        from core.research.lab.experiment_config import ExperimentConfig

        class StubConfig:
            outcome_bars = None

            def to_config(self):
                return ExperimentConfig(entry_model="FVG_RETRACE")

            def experiment_id(self):
                return "exp-fake"

        out = OpportunitySimulator().simulate(
            record("u"), StubConfig(), BREAKOUT_WIN
        )
        self.assertEqual(out.category, NON_EVALUABLE)
        self.assertTrue(any("no canonical decider" in w for w in out.warnings))


# ==========================================================
# No lookahead / causality
# ==========================================================


class TestNoLookahead(unittest.TestCase):

    def test_entry_decision_uses_only_decision_candle_chain(self):
        # Sweeping the FUTURE candles after the fill bar must NOT change
        # the entry decision (fill bar / fill price / bars_to_entry).
        base = [
            Candle(100.0, 101.0, 99.0, 100.0, 0),
            Candle(100.0, 101.0, 99.0, 101.0, 1),
            Candle(101.0, 105.0, 100.0, 104.0, 2),
        ]
        mild = simulate(record("a"), cfg(), base)
        wild = [
            Candle(100.0, 101.0, 99.0, 100.0, 0),
            Candle(100.0, 101.0, 99.0, 101.0, 1),
            Candle(101.0, 200.0, 1.0, 199.0, 2),   # radical future
        ]
        out = simulate(record("a"), cfg(), wild)
        self.assertEqual(out.fill_bar, mild.fill_bar)
        self.assertEqual(out.entry_price, mild.entry_price)
        self.assertEqual(out.bars_to_entry, mild.bars_to_entry)

    def test_breakout_fill_never_uses_trigger_candle_future(self):
        out = simulate(record("c"), cfg(), BREAKOUT_WIN)
        # fill price must be the OPEN of the bar AFTER the trigger
        self.assertEqual(out.entry_price, 101.0)
        self.assertEqual(out.fill_bar, 2)


# ==========================================================
# Outcome parity (stop-before-target; MAE/MFE/R/PnL)
# ==========================================================


class TestOutcomeParity(unittest.TestCase):

    def test_same_candle_collision_stop_wins(self):
        out = simulate(
            record("c"), cfg(entry_model="LIMIT_RETEST"), LIMIT_COLLISION
        )
        self.assertEqual(out.result, "LOSS")
        self.assertEqual(out.exit_price, 98.0)   # stop, not target
        self.assertEqual(out.exit_reason, "STOP")
        self.assertEqual(out.r, -1.0)

    def test_victory_math_fill_based_r(self):
        out = simulate(record("w"), cfg(entry_model="LIMIT_RETEST"), LIMIT_WIN)
        # fill 100, target 104, risk |100-98| = 2
        self.assertEqual(out.pnl, 4.0)
        self.assertEqual(out.r, 2.0)
        self.assertEqual(out.mfe, 5.0)  # 105 - 100 across bars
        self.assertEqual(out.mae, 1.0)  # fill bar low 99 -> 100 - 99

    def test_loss_math_fill_based_r(self):
        out = simulate(record("L"), cfg(entry_model="BREAKOUT_CONTINUATION"),
                       BREAKOUT_LOSS)
        # fill 101, stop 98 => pnl -3, risk 3, R -1, MAE 4 (101-97)
        self.assertEqual(out.pnl, -3.0)
        self.assertEqual(out.r, -1.0)
        self.assertEqual(out.exit_price, 98.0)
        self.assertEqual(out.mae, 4.0)

    def test_mae_mfe_multibar_hold(self):
        out = simulate(record("h"), cfg(), BREAKOUT_WIN_HOLD)
        self.assertEqual(out.result, "WIN")
        self.assertEqual(out.exit_bar, 3)
        self.assertEqual(out.bars_in_trade, 2)   # fill bar + exit bar
        self.assertEqual(out.mae, 1.0)           # 101 - 100
        self.assertEqual(out.mfe, 5.0)           # 106 - 101
        self.assertEqual(out.pnl, 3.0)           # 104 - 101
        self.assertEqual(out.r, 1.0)             # 3 / |101 - 98|

    def test_bars_in_trade_counts_fill_bar(self):
        out = simulate(record("h"), cfg(), BREAKOUT_WIN_HOLD)
        self.assertEqual(out.bars_in_trade, out.exit_bar - out.fill_bar + 1)


# ==========================================================
# Entry expiry + explicit outcome horizon
# ==========================================================


class TestHorizons(unittest.TestCase):

    def test_entry_expiry_bounds_the_window(self):
        # touch exists at bar2 but window is capped at bar1
        out = simulate(record("e"), cfg(entry_model="LIMIT_RETEST",
                                        expiry=1), EXPIRY)
        self.assertFalse(out.filled)
        self.assertEqual(out.exit_reason, "ENTRY_NOT_REACHED")

    def test_no_expiry_finds_trigger_outside_bounded_window(self):
        out = simulate(record("e"), cfg(entry_model="LIMIT_RETEST",
                                        expiry=None), EXPIRY)
        self.assertTrue(out.filled)
        self.assertEqual(out.fill_bar, 2)

    def test_outcome_bars_caps_walk(self):
        rec = record("o")
        full = simulate(rec, cfg(entry_model="LIMIT_RETEST", outcome_bars=None),
                        HORIZON)
        self.assertEqual(full.result, "WIN")
        self.assertEqual(full.exit_bar, 3)
        self.assertEqual(full.bars_in_trade, 3)

        capped = simulate(rec, cfg(entry_model="LIMIT_RETEST", outcome_bars=1),
                          HORIZON)
        self.assertTrue(capped.filled)
        self.assertEqual(capped.exit_reason, "UNSETTLED_END_OF_SERIES")
        self.assertEqual(capped.bars_in_trade, 1)

        capped2 = simulate(rec, cfg(entry_model="LIMIT_RETEST", outcome_bars=2),
                           HORIZON)
        self.assertEqual(capped2.exit_reason, "UNSETTLED_END_OF_SERIES")
        self.assertEqual(capped2.bars_in_trade, 2)


# ==========================================================
# Validation / fail-safe gates
# ==========================================================


class TestFailSafeGates(unittest.TestCase):

    def test_invalid_direction_non_evaluable(self):
        rec = record("d", direction="SIDEWAYS")
        out = simulate(rec, cfg(), BREAKOUT_WIN)
        self.assertEqual(out.category, NON_EVALUABLE)
        self.assertTrue(any("invalid direction" in w for w in out.warnings))

    def test_zero_risk_geometry_non_evaluable(self):
        rec = record("z", entry=100.0, stop=100.0, target=104.0)
        out = simulate(rec, cfg(), BREAKOUT_WIN)
        self.assertEqual(out.category, NON_EVALUABLE)
        self.assertTrue(any("geometry" in w for w in out.warnings))

    def test_invalid_stop_target_geometry_non_evaluable(self):
        rec = record("g", entry=100.0, stop=101.0, target=104.0)  # stop>entry
        out = simulate(rec, cfg(), BREAKOUT_WIN)
        self.assertEqual(out.category, NON_EVALUABLE)
        self.assertTrue(any("geometry" in w for w in out.warnings))

    def test_decision_bar_outside_series(self):
        rec = record("ob", bar=99)
        out = simulate(rec, cfg(), BREAKOUT_WIN)
        self.assertEqual(out.category, NON_EVALUABLE)
        self.assertTrue(any("decision bar outside" in w for w in out.warnings))

    def test_malformed_record_fail_safe(self):
        rec = OpportunityRecord(canonical_id="bad", setup={})
        out = simulate(rec, cfg(), BREAKOUT_WIN)
        self.assertEqual(out.category, NON_EVALUABLE)  # no direction

    def test_market_confirmation_never_fills_on_no_confirmation(self):
        rec = OpportunityRecord(
            canonical_id="q", direction="BEARISH",
            setup={"entry": 100.0, "stop_loss": 105.0, "take_profit": 90.0,
                   "bar": 0, "atr": 4.0},
            terminal_outcome="EXPIRED",
        )
        candles = [
            Candle(100.0, 102.0, 98.0, 101.0, 0),
            Candle(100.0, 102.0, 99.0, 101.0, 1),  # never closes below entry
            Candle(101.0, 103.0, 100.0, 102.0, 2),
        ]
        out = simulate(rec, cfg(entry_model="MARKET_CONFIRMATION"), candles)
        self.assertFalse(out.filled)
        self.assertEqual(out.exit_reason, "ENTRY_NOT_REACHED")


# ==========================================================
# Determinism / independence / immutability
# ==========================================================


class TestDeterminismAndImmutability(unittest.TestCase):

    def test_repeated_simulation_identical(self):
        rec = record("d1")
        config = cfg(entry_model="BREAKOUT_CONTINUATION", rr=2.0, expiry=10)
        a = simulate(rec, config, BREAKOUT_WIN)
        b = simulate(rec, config, BREAKOUT_WIN)
        self.assertEqual(a.to_dict(), b.to_dict())

    def test_config_independence_no_blending(self):
        rec = record("d2")
        c1 = cfg(rr=2.0)
        c2 = cfg(rr=3.0)
        o1 = simulate(rec, c1, BREAKOUT_WIN)
        o2 = simulate(rec, c2, BREAKOUT_WIN)
        self.assertEqual(o1.experimental_rr, 2.0)
        self.assertEqual(o2.experimental_rr, 3.0)
        self.assertNotEqual(o1.experimental_target, o2.experimental_target)
        self.assertEqual(c1.to_dict(), cfg(rr=2.0).to_dict())
        self.assertEqual(c2.to_dict(), cfg(rr=3.0).to_dict())

    def test_original_record_unchanged_after_one_and_many(self):
        rec = record("imm")
        snapshot = rec.to_dict()
        simulate(rec, cfg(), BREAKOUT_WIN)
        for _ in range(5):
            for cc in (cfg(rr=2.0), cfg(rr=3.0), cfg(entry_model="LIMIT_RETEST")):
                simulate(rec, cc, BREAKOUT_WIN)
                simulate(rec, cc, LIMIT_WIN)
        self.assertEqual(rec.to_dict(), snapshot)


# ==========================================================
# Provenance + ledger isolation
# ==========================================================


class TestLedgerIsolation(unittest.TestCase):

    def test_trade_provenance_is_counterfactual(self):
        out = simulate(record("p"), cfg(), BREAKOUT_WIN)
        trade = out.to_trade()
        self.assertTrue(trade.is_counterfactual)
        self.assertEqual(trade.provenance, "COUNTERFACTUAL")
        self.assertEqual(COUNTERFACTUAL, "COUNTERFACTUAL")

    def test_simulation_never_touches_production_ledger(self):
        from core.backtesting.trade_registry import TradeRegistry
        from core.risk.account import Account
        from core.risk.portfolio_state import PortfolioState
        from core.risk.capital import SharedCapital

        registry = TradeRegistry()
        account = Account()
        portfolio = PortfolioState()
        capital = SharedCapital()

        before_registry = registry.count()
        before_account = str(account)
        before_portfolio = str(portfolio)
        before_capital = str(capital)

        rec = record("ledger")
        for cc in (cfg(), cfg(rr=3.0), cfg(entry_model="LIMIT_RETEST")):
            out = simulate(rec, cc, BREAKOUT_WIN)
            out.to_trade()
            simulate(rec, cfg(rr=4.0), LIMIT_WIN).to_trade()

        self.assertEqual(registry.count(), before_registry)
        self.assertEqual(str(account), before_account)
        self.assertEqual(str(portfolio), before_portfolio)
        self.assertEqual(str(capital), before_capital)


# ==========================================================
# Runner + ParameterGrid integration (isolation, ids)
# ==========================================================


class TestRunner(unittest.TestCase):

    def setUp(self):
        self.rec = record("r1")
        self.runner = CounterfactualRunner(BREAKOUT_WIN)

    def test_run_config_one_per_opportunity(self):
        outs = self.runner.run_config([self.rec], cfg(rr=2.0, expiry=10))
        self.assertEqual(len(outs), 1)
        o = outs[0]
        self.assertEqual(o.experiment_id, cfg(rr=2.0, expiry=10).experiment_id())
        self.assertTrue(o.filled)
        self.assertEqual(o.result, "WIN")

    def test_run_configs_dict_keyed_by_id_no_overwrite(self):
        configs = [cfg(rr=2.0, expiry=10), cfg(rr=2.0, expiry=20),
                   cfg(rr=3.0, expiry=10), cfg(rr=3.0, expiry=20)]
        results = self.runner.run_configs([self.rec], configs)
        self.assertEqual(len(results), 4)
        for cc in configs:
            self.assertIn(cc.experiment_id(), results)
            self.assertEqual(
                results[cc.experiment_id()][0].experiment_id,
                cc.experiment_id(),
            )

    def test_grid_cartesian_order_and_ids(self):
        base = CounterfactualConfig(
            params={"entry_model": "BREAKOUT_CONTINUATION"},
            outcome_bars=None, baseline_id="baseline",
        )
        results = self.runner.grid([self.rec], base,
                                   rr=[2.0, 3.0], expiry_bars=[10, 20])
        self.assertEqual(len(results), 4)
        self.assertEqual(
            [(tuple((cc.params.get("rr"), cc.params.get("expiry"))))
             for cc, _ in results],
            [(2.0, 10), (2.0, 20), (3.0, 10), (3.0, 20)],
        )
        ids = [cc.experiment_id() for cc, _ in results]
        self.assertEqual(len(set(ids)), 4)

    def test_grid_confirms_each_id_distinct_no_collision(self):
        base = CounterfactualConfig(
            params={"entry_model": "BREAKOUT_CONTINUATION"},
            outcome_bars=None, baseline_id="baseline",
        )
        results = self.runner.grid([self.rec], base,
                                   rr=[2.0, 3.0], expiry_bars=[10, 20])
        ids = [cc.experiment_id() for cc, _ in results]
        self.assertEqual(len(set(ids)), 4)
        # deterministic across identical re-runs
        again = self.runner.grid([self.rec], base,
                                 rr=[2.0, 3.0], expiry_bars=[10, 20])
        self.assertEqual(ids, [cc.experiment_id() for cc, _ in again])

    def test_grid_preserves_base_config_and_no_sharing(self):
        base = CounterfactualConfig(
            params={"entry_model": "BREAKOUT_CONTINUATION", "rr": 2.0},
            outcome_bars=7, baseline_id="baseline",
        )
        before = base.to_dict()
        results = self.runner.grid([self.rec], base,
                                   rr=[2.0, 3.0], expiry_bars=[10, 20])
        self.assertEqual(base.to_dict(), before)  # base untouched
        for cc, outs in results:
            self.assertEqual(cc.outcome_bars, 7)
            self.assertEqual(outs[0].experiment_id, cc.experiment_id())
            self.assertEqual(outs[0].config.to_params(), cc.to_config().to_params())

    def test_grid_results_reflect_their_own_config(self):
        # RR change moves the derived target -> different realized R even
        # on the same candles.
        base = CounterfactualConfig(params={"entry_model": "BREAKOUT_CONTINUATION",
                                            "stop_mode": "EXISTING_STOP",
                                            "target_mode": "FIXED_RR"})
        results = self.runner.grid([self.rec], base, rr=[1.0, 2.0, 3.0])
        self.assertEqual(len(results), 3)
        targets = {cc.params.get("rr"): outs[0].experimental_target
                   for cc, outs in results}
        self.assertEqual(targets[1.0], 102.0)   # 100 + 1*2
        self.assertEqual(targets[2.0], 104.0)   # 100 + 2*2
        self.assertEqual(targets[3.0], 106.0)   # 100 + 3*2


# ==========================================================
# Opportunity recovery (the research questions)
# ==========================================================


class TestOpportunityRecovery(unittest.TestCase):

    def test_rejected_due_too_far_from_market_recovers(self):
        rec = record("tf", terminal="REJECTED", reasons=["TOO_FAR_FROM_MARKET"],
                     entry=100.0, stop=98.0, target=104.0)
        out = simulate(rec, cfg(), RECOVERY)
        self.assertEqual(out.category, REJECTED)     # baseline fact kept
        self.assertTrue(out.filled)
        self.assertEqual(out.result, "WIN")
        self.assertGreater(out.r, 0.0)
        self.assertEqual(out.to_trade().provenance, "COUNTERFACTUAL")
        self.assertEqual(rec.terminal_outcome, "REJECTED")  # record untouched

    def test_rejected_insufficient_risk_width_recovers(self):
        rec = record("irw", terminal="REJECTED",
                     reasons=["INSUFFICIENT_RISK_WIDTH"],
                     entry=100.0, stop=98.0, target=104.0)
        out = simulate(rec, cfg(), RECOVERY)
        self.assertEqual(out.category, REJECTED)
        self.assertTrue(out.filled)
        self.assertEqual(out.result, "WIN")

    def test_rejected_stale_zone_recovers(self):
        rec = record("sz", terminal="REJECTED", reasons=["STALE_ZONE"],
                     entry=100.0, stop=98.0, target=104.0)
        out = simulate(rec, cfg(), RECOVERY)
        self.assertEqual(out.category, REJECTED)
        self.assertTrue(out.filled)
        self.assertEqual(out.result, "WIN")

    def test_unfilled_limit_can_be_recovered_by_switching_entry_model(self):
        # Baseline LIMIT_RETEST never touches (all lows above entry);
        # BREAKOUT_CONTINUATION triggers and wins.
        base_rec = record("um", terminal="EXPIRED",
                          entry=100.0, stop=98.0, target=104.0)
        limit_out = simulate(
            base_rec, cfg(entry_model="LIMIT_RETEST"), RECOVERY
        )
        self.assertFalse(limit_out.filled)
        self.assertEqual(limit_out.exit_reason, "ENTRY_NOT_REACHED")

        breakout_out = simulate(
            base_rec, cfg(entry_model="BREAKOUT_CONTINUATION"), RECOVERY
        )
        self.assertTrue(breakout_out.filled)
        self.assertEqual(breakout_out.result, "WIN")
        self.assertEqual(breakout_out.entry_price, 101.5)  # next open
        self.assertGreater(breakout_out.r, 0.0)
        # both came from the SAME, untouched original record
        self.assertEqual(base_rec.terminal_outcome, "EXPIRED")

    def test_missed_continuation_recovered_by_extended_expiry(self):
        # Baseline has expiry=1 (window capped), so the expiration is
        # "missed"; extending expiry lets the same trigger fill.
        base_rec = record("mc", terminal="EXPIRED",
                          entry=100.0, stop=98.0, target=104.0)
        capped = simulate(base_rec, cfg(entry_model="LIMIT_RETEST", expiry=1),
                          EXPIRY)
        self.assertFalse(capped.filled)
        extended = simulate(base_rec, cfg(entry_model="LIMIT_RETEST",
                                          expiry=None), EXPIRY)
        self.assertTrue(extended.filled)
        self.assertEqual(extended.result, "WIN")

    def test_classification_vocabulary(self):
        filled = record("f", terminal="FILLED_CLOSED")
        self.assertEqual(classify_opportunity(filled), FILLED)
        rej = record("r", terminal="REJECTED", reasons=["TOO_FAR_FROM_MARKET"])
        self.assertEqual(classify_opportunity(rej), REJECTED)
        exp = record("x", terminal="EXPIRED")
        self.assertEqual(classify_opportunity(exp), MISSED_CONTINUATION)
        inv = record("i", terminal="INVALIDATED")
        self.assertEqual(classify_opportunity(inv), INVALIDATED)
        enr = record("n", terminal="ORDER_NOT_CREATED")
        self.assertEqual(classify_opportunity(enr), ENTRY_NOT_REACHED)
        # unknown terminal with no evidence -> NON_EVALUABLE
        rec = OpportunityRecord(canonical_id="q", terminal_outcome="WEIRD")
        self.assertEqual(classify_opportunity(rec), NON_EVALUABLE)


if __name__ == "__main__":
    unittest.main()