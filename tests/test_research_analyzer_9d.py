"""
====================================================

QuantEngine

Phase 9D -- Experiment Matrix + Research Analyzer tests

Proves the deterministic research-analyzer layer:

   * baseline metrics from frozen OpportunityRecord facts
   * experiment metrics over 9C CounterfactualOutcome facts
   * like-for-like baseline vs counterfactual comparison
   * recovery classification (REJECTED / ENTRY_NOT_REACHED /
     MISSED_CONTINUATION -> WIN / LOSS / STILL_*)
   * rejected-reason recovery grouping (verbatim reasons)
   * missed-continuation isolation
   * bullish / bearish and symbol grouping
   * deterministic experiment matrix (ids, order, empty ranges,
     outcome-bars dimension, unknown-key rejection, no mutation)
   * zero-denominator metrics
   * small-sample / directional-imbalance / loss-expansion warnings
   * experiment isolation; source immutability
   * malformed-opportunity fail-tolerance
   * empty experiment / opportunity sets
   * multiple independent experiments; exact config provenance
   * incremental R / profitable recovery / recovery raising losses
   * no production ledger mutation (static import boundary)

Reuses ONLY real 9C simulation to produce experiment facts (the
analyzer itself never simulates). Stdlib only; offline;
deterministic.
====================================================
"""

import copy
import re
import unittest

from core.research.journal import OpportunityRecord
from core.research.counterfactual import (
    CounterfactualConfig,
    OpportunitySimulator,
)
from core.research.analyzer import (
    ResearchAnalyzer,
    ExperimentMatrix,
    baseline_view,
    category_distribution,
    metrics_for,
    group_metrics,
    group_sizes,
    RecoveryReport,
    transition_for,
    result_quality_for,
    compare_experiments,
    robustness_assess,
)


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


def make_record(canonical, direction="BULLISH", terminal="ORDER_NOT_CREATED",
                reasons=None, trade=None, instrument=None, bar=0):
    stop = 98.0 if direction == "BULLISH" else 102.0
    target = 104.0 if direction == "BULLISH" else 96.0
    return OpportunityRecord(
        canonical_id=canonical,
        exchange="TESTEX",
        instrument_id=instrument or canonical,
        timeframe="1m",
        direction=direction,
        strategy="BREAKOUT_CONTINUATION",
        setup_id=canonical,
        setup={
            "entry": 100.0, "stop_loss": stop, "take_profit": target,
            "risk_reward": 2.0, "bar": bar, "atr": 4.0,
            "rejection_reasons": list(reasons or []),
        },
        order={} if terminal == "ORDER_NOT_CREATED" else {"created_bar": bar},
        trade=trade or {},
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
    outcome_bars = defaults.pop("outcome_bars", None)
    baseline = defaults.pop("baseline_id", "baseline")
    return CounterfactualConfig(
        params=defaults, outcome_bars=outcome_bars, baseline_id=baseline
    )


def sim(rec, config, candles):
    return OpportunitySimulator().simulate(rec, config, candles)


def bundle(config, pairs):
    """(CounterfactualConfig, [outcome]) from (record, series) pairs."""
    return config, [sim(rec, config, series) for rec, series in pairs]


def analyze(records, *bundles):
    return ResearchAnalyzer().analyze(records, list(bundles))


# ----------------------------------------------------------
# Candle series. BREAKOUT_CONTINUATION fills the NEXT bar OPEN,
# so every array shapes bar2 to open exactly at the config entry
# level (100) -> risk = |100 - 98| = 2, FIXED_RR target = 104,
# and a WIN exits at 104 -> R = +2, a LOSS at stop 98 -> R = -1.
# This keeps the like-for-like recovery arithmetic (fill-based R)
# clean and directly verifiable.
# ----------------------------------------------------------

# BULLISH BREAKOUT WIN: trigger bar1 (high>100, close>100); fill
# bar2 open=100; target 104 reached on bar3.
BULL_RECOVERY = [
    Candle(100.0, 101.0, 99.0, 100.0, 0),
    Candle(100.0, 101.0, 99.0, 101.0, 1),
    Candle(100.0, 100.5, 99.5, 100.0, 2),
    Candle(100.0, 106.0, 100.0, 105.0, 3),
]

# BULLISH BREAKOUT LOSS: fill bar2 open=100, same-bar stop (low<=98).
BULL_LOSS = [
    Candle(100.0, 101.0, 99.0, 100.0, 0),
    Candle(100.0, 101.0, 99.0, 101.0, 1),
    Candle(100.0, 102.0, 97.0, 98.0, 2),
]

# BEARISH BREAKOUT WIN: trigger bar1 (low<100, close<100); fill bar2
# open=100; target 96 reached on bar3. R = (100-96)/2 = +2.
BEAR_RECOVERY = [
    Candle(100.0, 101.0, 99.0, 100.0, 0),
    Candle(100.0, 100.0, 99.0, 99.0, 1),
    Candle(100.0, 100.5, 99.5, 100.0, 2),
    Candle(100.0, 101.0, 94.0, 95.0, 3),
]

# BEARISH BREAKOUT LOSS: fill bar2 open=100, same-bar stop (high>=102).
BEAR_LOSS = [
    Candle(100.0, 101.0, 99.0, 100.0, 0),
    Candle(100.0, 100.0, 99.0, 99.0, 1),
    Candle(100.0, 103.0, 99.5, 99.0, 2),
]

# LIMIT retest: touch at entry 100 only on bar2 (bar1 low 101 > 100,
# so expiry=1 never touches); fill 100, target 104 hit on bar3.
# expiry=10 reaches the fill on bar2 -> WIN (+2R).
EXPIRY = [
    Candle(100.0, 101.0, 99.0, 100.0, 0),
    Candle(100.0, 102.0, 101.0, 101.0, 1),
    Candle(99.0, 101.0, 99.0, 100.0, 2),
    Candle(100.0, 106.0, 100.0, 105.0, 3),
]

# ----------------------------------------------------------
# Baseline records
# ----------------------------------------------------------

R_FILL_WIN = make_record(
    "filled-win", terminal="FILLED_CLOSED",
    trade={"result": "WIN", "pnl": 3.0, "risk_amount": 3.0, "r": 1.0,
           "entry_bar": 2, "exit_bar": 2, "bars_held": 1, "mae": 1.0,
           "mfe": 4.0, "exit_price": 104.0},
)
R_FILL_LOSS = make_record(
    "filled-loss", terminal="FILLED_CLOSED",
    trade={"result": "LOSS", "pnl": -2.0, "risk_amount": 2.0, "r": -1.0,
           "entry_bar": 2, "exit_bar": 2, "bars_held": 1, "mae": 2.0,
           "mfe": 0.0, "exit_price": 98.0},
)
R_FAR = make_record("rej-far", reasons=["TOO_FAR_FROM_MARKET"],
                    instrument="BTCUSDT")
R_WIDTH = make_record("rej-width", reasons=["INSUFFICIENT_RISK_WIDTH"],
                      instrument="BTCUSDT")
R_STALE = make_record("rej-stale", reasons=["STALE_ZONE"],
                      instrument="ETHUSDT")
R_FAR_LOSS = make_record("rej-far-loss", reasons=["TOO_FAR_FROM_MARKET"],
                         instrument="SOLUSDT")
R_ENR = make_record("enr-1", instrument="BTCUSDT")
R_MISSED = make_record("missed-1", terminal="EXPIRED", instrument="BTCUSDT")
R_BEAR_WIN = make_record("bear-win", direction="BEARISH",
                         reasons=["TOO_FAR_FROM_MARKET"], instrument="ETHUSDT")
R_BEAR_LOSS = make_record("bear-loss", direction="BEARISH",
                          reasons=["INSUFFICIENT_RISK_WIDTH"],
                          instrument="ETHUSDT")

ALL_RECORDS = [
    R_FILL_WIN, R_FILL_LOSS, R_FAR, R_WIDTH, R_STALE, R_FAR_LOSS,
    R_ENR, R_MISSED, R_BEAR_WIN, R_BEAR_LOSS,
]

# Experiment bundles used across tests.
EXP_BREAKOUT = bundle(cfg(entry_model="BREAKOUT_CONTINUATION", rr=2), [
    (R_FAR, BULL_RECOVERY),
    (R_WIDTH, BULL_RECOVERY),
    (R_STALE, BULL_RECOVERY),
    (R_FAR_LOSS, BULL_LOSS),
])
EXP_LIMIT1 = bundle(cfg(entry_model="LIMIT_RETEST", rr=2, expiry=1), [
    (R_ENR, EXPIRY),
    (R_MISSED, EXPIRY),
])
EXP_EXPIRY = bundle(cfg(entry_model="LIMIT_RETEST", rr=2, expiry=10), [
    (R_ENR, EXPIRY),
    (R_MISSED, EXPIRY),
])
EXP_BEAR = bundle(cfg(entry_model="BREAKOUT_CONTINUATION", rr=1), [
    (R_BEAR_WIN, BEAR_RECOVERY),
    (R_BEAR_LOSS, BEAR_LOSS),
])


# ==========================================================
# Baseline metrics
# ==========================================================


class TestBaselineMetrics(unittest.TestCase):

    def test_baseline_metrics_from_record_facts(self):
        report = analyze(ALL_RECORDS)
        bm = report.baseline_metrics
        self.assertEqual(bm["opportunities"], 10)
        self.assertEqual(bm["filled"], 2)            # only the two FILLED_CLOSED
        self.assertEqual(bm["settled"], 2)
        self.assertEqual(bm["wins"], 1)
        self.assertEqual(bm["losses"], 1)
        self.assertAlmostEqual(bm["win_rate"], 50.0)
        self.assertAlmostEqual(bm["profit_factor"], 1.5)   # 3.0 / 2.0
        self.assertAlmostEqual(bm["expectancy"], 0.5)      # (3 - 2) / 2
        self.assertAlmostEqual(bm["total_R"], 0.0)         # 1 + (-1)
        self.assertAlmostEqual(bm["avg_MAE"], 1.5)
        self.assertAlmostEqual(bm["avg_MFE"], 2.0)
        self.assertAlmostEqual(bm["avg_bars_to_entry"], 2.0)


# ==========================================================
# Experiment metrics
# ==========================================================


class TestExperimentMetrics(unittest.TestCase):

    def test_experiment_metrics_over_outcomes(self):
        report = analyze(ALL_RECORDS, EXP_BREAKOUT)
        exp = report.experiments[0]
        m = exp.metrics
        self.assertEqual(m["evaluated"], 4)
        self.assertEqual(m["filled"], 4)
        self.assertEqual(m["wins"], 3)
        self.assertEqual(m["losses"], 1)
        self.assertAlmostEqual(m["win_rate"], 75.0)
        self.assertAlmostEqual(m["total_R"], 5.0)      # 3*2 + (-1)
        self.assertAlmostEqual(m["net_pnl"], 10.0)     # 3*4 - 2
        self.assertAlmostEqual(m["expectancy"], 2.5)

    def test_group_metrics_by_direction(self):
        _, outcomes = EXP_BEAR
        grouped = group_metrics(outcomes, "direction")
        self.assertEqual(list(grouped["direction"].keys()), ["BEARISH"])
        self.assertEqual(grouped["direction"]["BEARISH"]["filled"], 2)

    def test_group_sizes(self):
        _, outcomes = EXP_BEAR
        self.assertEqual(group_sizes(outcomes, "direction"),
                         {"BEARISH": 2})


# ==========================================================
# Comparison
# ==========================================================


class TestComparison(unittest.TestCase):

    def test_baseline_vs_experiment_like_for_like(self):
        report = analyze(ALL_RECORDS, EXP_BREAKOUT)
        cmp_ = report.experiments[0].comparison.to_dict()
        self.assertEqual(cmp_["kind"], "BASELINE_VS_EXPERIMENT")
        # restricted baseline = the 4 rejected records (0 baseline fills)
        self.assertEqual(cmp_["baseline_sample"], 0)
        self.assertEqual(cmp_["incremental_fills"], 4)
        self.assertEqual(cmp_["incremental_wins"], 3)
        self.assertEqual(cmp_["incremental_losses"], 1)
        self.assertAlmostEqual(cmp_["incremental_R"], 5.0)
        self.assertAlmostEqual(cmp_["incremental_pnl"], 10.0)  # 3*4 - 2
        self.assertAlmostEqual(cmp_["delta_expectancy"], 2.5)

    def test_comparison_vs_experiment_deltas(self):
        cmp_ = compare_experiments(
            {"filled": 1, "wins": 1, "losses": 0, "total_R": 2.0,
             "net_pnl": 7.0, "expectancy": 7.0},
            {"filled": 4, "wins": 3, "losses": 1, "total_R": 5.0,
             "net_pnl": 18.0, "expectancy": 4.5},
            id_a="exp-a", id_b="exp-b", config_a=None, config_b=None,
            baseline_id="baseline",
        )
        d = cmp_.to_dict()
        self.assertEqual(d["kind"], "EXPERIMENT_VS_EXPERIMENT")
        self.assertEqual(d["incremental_fills"], 3)
        self.assertEqual(d["incremental_wins"], 2)
        self.assertEqual(d["incremental_losses"], 1)
        self.assertAlmostEqual(d["incremental_R"], 3.0)
        self.assertEqual(d["incremental_fills"], 3)


# ==========================================================
# Recovery classification
# ==========================================================


class TestRecovery(unittest.TestCase):

    def test_recovery_transitions_rejected(self):
        report = analyze(ALL_RECORDS, EXP_BREAKOUT)
        rec = report.experiments[0].recovery.to_dict()
        self.assertEqual(rec["transitions"]["REJECTED -> WIN"], 3)
        self.assertEqual(rec["transitions"]["REJECTED -> LOSS"], 1)
        self.assertEqual(rec["recovered"], 4)
        self.assertEqual(rec["recovered_wins"], 3)
        self.assertEqual(rec["recovered_losses"], 1)
        self.assertAlmostEqual(rec["recovery_rate"], 1.0)
        self.assertAlmostEqual(rec["profitable_recovery_rate"], 0.75)

    def test_rejected_reason_grouping_verbatim(self):
        report = analyze(ALL_RECORDS, EXP_BREAKOUT)
        rr = report.experiments[0].recovery.to_dict()[
            "rejected_reason_recovery"
        ]
        self.assertEqual(rr["TOO_FAR_FROM_MARKET"],
                         {"recovered": 2, "wins": 1, "losses": 1})
        self.assertEqual(rr["INSUFFICIENT_RISK_WIDTH"],
                         {"recovered": 1, "wins": 1, "losses": 0})
        self.assertEqual(rr["STALE_ZONE"],
                         {"recovered": 1, "wins": 1, "losses": 0})

    def test_entry_not_reached_and_missed_continuation(self):
        report = analyze(ALL_RECORDS, EXP_LIMIT1, EXP_EXPIRY)
        limit = report.experiments[0].recovery.to_dict()
        self.assertEqual(limit["transitions"]["ENTRY_NOT_REACHED -> STILL_NOT_REACHED"], 1)
        self.assertEqual(limit["transitions"]["MISSED_CONTINUATION -> STILL_MISSED"], 1)
        self.assertEqual(limit["recovered"], 0)

        expiry = report.experiments[1].recovery.to_dict()
        self.assertEqual(expiry["transitions"]["ENTRY_NOT_REACHED -> WIN"], 1)
        self.assertEqual(expiry["transitions"]["MISSED_CONTINUATION -> WIN"], 1)
        self.assertEqual(expiry["recovered"], 2)
        mc = expiry["missed_continuation"]
        self.assertEqual(mc["missed_continuation_recovered"], 1)
        self.assertEqual(mc["recovered_wins"], 1)

    def test_missed_continuation_isolated_not_mixed(self):
        report = analyze(ALL_RECORDS, EXP_EXPIRY)
        rec = report.experiments[0].recovery
        self.assertEqual(rec.missed_continuation()["recovered_wins"], 1)
        # the ENTRY_NOT_REACHED recovery must not leak into the
        # missed-continuation bucket
        self.assertEqual(rec.missed_continuation()["missed_continuation_recovered"], 1)
        self.assertEqual(rec.to_dict()["recovered"], 2)

    def test_result_quality_better_worse(self):
        better = bundle(cfg(entry_model="BREAKOUT_CONTINUATION", rr=2), [
            (R_FILL_WIN, BULL_RECOVERY),
            (R_FILL_LOSS, BULL_RECOVERY),
        ])
        worse = bundle(cfg(entry_model="BREAKOUT_CONTINUATION", rr=2), [
            (R_FILL_WIN, BULL_LOSS),
        ])
        report = analyze(ALL_RECORDS, better, worse)
        self.assertEqual(report.experiments[0].recovery.to_dict()["quality"],
                         {"BETTER_RESULT": 2})
        self.assertEqual(report.experiments[1].recovery.to_dict()["quality"],
                         {"WORSE_RESULT": 1})

    def test_transition_mappers_unit(self):
        o = sim(R_FAR, cfg(entry_model="BREAKOUT_CONTINUATION"), BULL_RECOVERY)
        self.assertEqual(transition_for(R_FAR, o), "REJECTED -> WIN")
        self.assertEqual(result_quality_for(R_FAR, o), "N/A")


# ==========================================================
# Grouping
# ==========================================================


class TestGrouping(unittest.TestCase):

    def test_bullish_bearish_breakdown(self):
        report = analyze(ALL_RECORDS, EXP_BEAR)
        dir_ = report.experiments[0].directional
        self.assertIn("ALL", dir_)
        self.assertIn("BEARISH", dir_)
        self.assertEqual(dir_["BEARISH"]["filled"], 2)
        self.assertNotIn("BULLISH", dir_)

    def test_symbol_grouping(self):
        _, outcomes = EXP_BREAKOUT
        grouped = group_metrics(outcomes, "instrument_id")
        keys = grouped["instrument_id"]
        self.assertEqual(sorted(keys), ["BTCUSDT", "ETHUSDT", "SOLUSDT"])
        # two of the four experiments instruments is BTCUSDT
        self.assertEqual(keys["BTCUSDT"]["filled"], 2)

    def test_category_distribution_reuses_9c_categories(self):
        dist = category_distribution(ALL_RECORDS)
        self.assertEqual(dist.get("FILLED"), 2)
        self.assertEqual(dist.get("REJECTED"), 6)
        self.assertEqual(dist.get("ENTRY_NOT_REACHED"), 1)
        self.assertEqual(dist.get("MISSED_CONTINUATION"), 1)


# ==========================================================
# Experiment matrix
# ==========================================================


class TestExperimentMatrix(unittest.TestCase):

    def setUp(self):
        self.matrix = ExperimentMatrix([], baseline_id="baseline")

    def test_deterministic_ids_and_insertion_order(self):
        spec = self.matrix.spec(cfg(rr=2.0), rr=[2.0, 3.0], expiry=[10, 20])
        self.assertEqual(len(spec), 4)
        self.assertEqual(
            [(c.params["rr"], c.params["expiry"]) for c in spec],
            [(2.0, 10), (2.0, 20), (3.0, 10), (3.0, 20)],
        )
        ids = [c.experiment_id() for c in spec]
        self.assertEqual(len(set(ids)), 4)
        repeat = self.matrix.spec(cfg(rr=2.0), rr=[2.0, 3.0], expiry=[10, 20])
        self.assertEqual([c.experiment_id() for c in repeat], ids)

    def test_outcome_bars_dimension(self):
        spec = self.matrix.spec(cfg(rr=2.0), outcome_bars=[None, 10])
        self.assertEqual(len(spec), 2)
        self.assertEqual({c.outcome_bars for c in spec}, {None, 10})
        self.assertEqual(
            len({c.experiment_id() for c in spec}), 2,
            "outcome horizon must participate in the experiment id",
        )

    def test_empty_range_yields_no_combos(self):
        self.assertEqual(self.matrix.spec(cfg(rr=2.0), rr=[]), [])

    def test_baseline_config_only(self):
        base = cfg(rr=2.0)
        spec = self.matrix.spec(base)
        self.assertEqual(len(spec), 1)
        self.assertEqual(spec[0].to_dict()["params"]["rr"], 2.0)

    def test_unknown_key_fails_loudly(self):
        with self.assertRaises(KeyError):
            self.matrix.spec(cfg(rr=2.0), not_a_field=[1])

    def test_base_config_never_mutated(self):
        base = cfg(rr=2.0)
        before = base.to_dict()
        self.matrix.spec(base, rr=[2.0, 3.0], expiry=[10, 20])
        self.assertEqual(base.to_dict(), before)


# ==========================================================
# Zero denominators
# ==========================================================


class TestZeroDenominators(unittest.TestCase):

    def test_empty_metrics_all_zeros(self):
        m = metrics_for([])
        self.assertEqual(m["filled"], 0)
        self.assertEqual(m["win_rate"], 0.0)
        self.assertEqual(m["profit_factor"], 0.0)
        self.assertEqual(m["expectancy"], 0.0)
        self.assertEqual(m["total_R"], 0.0)
        self.assertEqual(m["avg_MAE"], 0.0)
        self.assertEqual(m["median_bars_to_entry"], 0.0)
        self.assertNotIn("nan", str(m.values()).lower())

    def test_empty_recovery_all_zeros(self):
        rec = RecoveryReport([], []).to_dict()
        self.assertEqual(rec["previously_unfilled"], 0)
        self.assertEqual(rec["recovered"], 0)
        self.assertEqual(rec["recovery_rate"], 0.0)
        self.assertEqual(rec["profitable_recovery_rate"], 0.0)


# ==========================================================
# Robustness
# ==========================================================


class TestRobustness(unittest.TestCase):

    def test_small_sample_warnings(self):
        tiny = bundle(cfg(entry_model="BREAKOUT_CONTINUATION"), [
            (R_FAR, BULL_RECOVERY),
        ])
        report = analyze(ALL_RECORDS, tiny)
        joined = " | ".join(report.experiments[0].robustness)
        self.assertIn("insufficient sample", joined)
        self.assertIn("no statistical significance is claimed", joined)
        self.assertIn("in-sample research only", joined)

    def test_loss_expansion_warning(self):
        losses = bundle(cfg(entry_model="BREAKOUT_CONTINUATION"), [
            (R_FAR_LOSS, BULL_LOSS),
            (R_BEAR_LOSS, BEAR_LOSS),
        ])
        report = analyze(ALL_RECORDS, losses)
        joined = " | ".join(report.experiments[0].robustness)
        self.assertIn("recovery increases losses", joined)
        self.assertIn("+2", joined)
        rec = report.experiments[0].recovery.to_dict()
        self.assertEqual(rec["recovered_losses"], 2)
        self.assertEqual(rec["recovered_wins"], 0)

    def test_directional_imbalance_warning(self):
        warnings = robustness_assess(
            None,
            directional_sizes={"BULLISH": 10, "BEARISH": 1},
        )
        joined = " | ".join(warnings)
        self.assertIn("directional imbalance", joined)

    def test_balance_direction_no_warning(self):
        warnings = robustness_assess(
            None,
            directional_sizes={"BULLISH": 6, "BEARISH": 5},
        )
        joined = " | ".join(warnings)
        self.assertNotIn("directional imbalance", joined)


# ==========================================================
# Isolation / determinism / purity
# ==========================================================


class TestIsolationAndPurity(unittest.TestCase):

    def test_experiment_isolation_no_blending(self):
        report = analyze(ALL_RECORDS, EXP_BREAKOUT, EXP_EXPIRY)
        self.assertEqual(len(report.experiments), 2)
        ids = [e.experiment_id for e in report.experiments]
        self.assertEqual(len(set(ids)), 2)
        # every experiment's metrics reflect ONLY its own population
        self.assertEqual(report.experiments[0].metrics["filled"], 4)
        self.assertEqual(report.experiments[1].metrics["filled"], 2)
        # entry-model comparison exists (two distinct models)
        emc = report.entry_model_comparison
        self.assertEqual(sorted(emc), ["BREAKOUT_CONTINUATION", "LIMIT_RETEST"])

    def test_deterministic_across_runs(self):
        a = analyze(ALL_RECORDS, EXP_BREAKOUT, EXP_EXPIRY).to_dict()
        b = analyze(ALL_RECORDS, EXP_BREAKOUT, EXP_EXPIRY).to_dict()
        self.assertEqual(a, b)

    def test_no_production_ledger_import_boundary(self):
        analyzer_files = [
            "core/research/analyzer/baseline.py",
            "core/research/analyzer/experiment_metrics.py",
            "core/research/analyzer/opportunity_analysis.py",
            "core/research/analyzer/recovery_analysis.py",
            "core/research/analyzer/comparison.py",
            "core/research/analyzer/robustness.py",
            "core/research/analyzer/experiment_matrix.py",
            "core/research/analyzer/research_report.py",
            "core/research/analyzer/research_analyzer.py",
        ]
        forbidden = re.compile(
            r"^\s*(from core\.|import core\.).*(backtesting|paper_trading"
            r"|trading|portfolio|risk_engine|account|shared_capital)"
        )
        for path in analyzer_files:
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    assert not forbidden.match(line), (
                        f"{path} must not touch production internals: {line.strip()}"
                    )

    def test_counterfactual_provenance_preserved(self):
        _, outcomes = EXP_BREAKOUT
        for o in outcomes:
            self.assertEqual(o.experiment_id, EXP_BREAKOUT[0].experiment_id())
            self.assertTrue(o.experiment_id)


# ==========================================================
# Immutability
# ==========================================================


class TestImmutability(unittest.TestCase):

    def test_source_records_and_configs_never_mutated(self):
        records_snapshot = copy.deepcopy(ALL_RECORDS)
        cfg_snapshot = EXP_BREAKOUT[0].to_dict()
        analyze(ALL_RECORDS, EXP_BREAKOUT)
        for got, want in zip(ALL_RECORDS, records_snapshot):
            self.assertEqual(got.to_dict(), want.to_dict())
        self.assertEqual(EXP_BREAKOUT[0].to_dict(), cfg_snapshot)

    def test_outcome_list_not_aliased_between_bundles(self):
        _, outcomes = EXP_BREAKOUT
        _, other = EXP_EXPIRY
        self.assertFalse(any(
            id(a) == id(b) for a in outcomes for b in other
        ))


# ==========================================================
# Fail tolerance / empty sets
# ==========================================================


class TestFailTolerance(unittest.TestCase):

    def test_malformed_opportunity_tolerated(self):
        bad = OpportunityRecord(
            canonical_id="bad-1", exchange="TESTEX", instrument_id="bad-1",
            timeframe="1m", direction="BULLISH", strategy="BREAKOUT_CONTINUATION",
            setup_id="bad-1", setup={}, order={}, terminal_outcome=None,
        )
        config = cfg(entry_model="BREAKOUT_CONTINUATION")
        outcomes = [sim(bad, config, BULL_RECOVERY)]
        report = analyze(ALL_RECORDS + [bad], (config, outcomes))
        self.assertTrue(report.experiments[0].recovery.to_dict()[
            "transitions"].get("ENTRY_NOT_REACHED -> NOT_EVALUABLE", 0))
        self.assertTrue(
            report.experiments[0].metrics["filled"] == 0
        )

    def test_empty_experiment_set(self):
        report = analyze(ALL_RECORDS)
        self.assertEqual(report.experiments, [])
        self.assertTrue(any("no experiments" in w for w in report.warnings))

    def test_empty_opportunity_set(self):
        report = analyze([], EXP_BREAKOUT)
        self.assertEqual(report.baseline_metrics["opportunities"], 0)
        self.assertTrue(any("empty opportunity set" in w for w in report.warnings))

    def test_full_empty(self):
        report = analyze([])
        self.assertEqual(report.experiments, [])
        self.assertEqual(report.baseline_metrics["filled"], 0)
        self.assertTrue(report.warnings)


# ==========================================================
# Analyzer orchestration
# ==========================================================


class TestAnalyzerIntegration(unittest.TestCase):

    def test_multiple_independent_experiments(self):
        report = analyze(ALL_RECORDS, EXP_BREAKOUT, EXP_EXPIRY, EXP_BEAR)
        self.assertEqual(len(report.experiments), 3)
        self.assertEqual(len({e.experiment_id for e in report.experiments}), 3)
        # exp_bear is 100% recovered on the bearish side
        self.assertEqual(report.experiments[2].metrics["filled"], 2)

    def test_exact_config_provenance_preserved(self):
        report = analyze(ALL_RECORDS, EXP_EXPIRY)
        d = report.experiments[0].to_dict()
        self.assertEqual(d["config"]["params"]["entry_model"], "LIMIT_RETEST")
        self.assertEqual(d["config"]["params"]["rr"], 2.0)
        self.assertEqual(d["config"]["params"]["expiry"], 10)
        self.assertEqual(d["config"]["outcome_bars"], None)

    def test_analyze_results_requires_exact_config(self):
        _, outcomes = EXP_BREAKOUT
        with self.assertRaises(ValueError):
            ResearchAnalyzer().analyze_results(
                ALL_RECORDS,
                outcomes_by_experiment={EXP_BREAKOUT[0].experiment_id(): outcomes},
                configs_by_experiment={},
            )

    def test_analyze_results_accepts_9c_style_dict(self):
        _, outcomes = EXP_BREAKOUT
        config = EXP_BREAKOUT[0]
        report = ResearchAnalyzer().analyze_results(
            ALL_RECORDS,
            outcomes_by_experiment={config.experiment_id(): outcomes},
            configs_by_experiment={config.experiment_id(): config},
        )
        self.assertEqual(len(report.experiments), 1)
        self.assertEqual(report.experiments[0].metrics["filled"], 4)

    def test_run_and_analyze_end_to_end(self):
        # bar3 reaches 104 (rr=2 target) but not 106 (rr=3 target),
        # so rr=2 wins while rr=3 stays unsettled -- proven with the
        # real 9C simulator, not assumed.
        series = list(BULL_RECOVERY)
        series[3] = Candle(100.0, 105.5, 100.0, 105.0, 3)
        report = ResearchAnalyzer().run_and_analyze(
            [R_FAR],
            series,
            cfg(entry_model="BREAKOUT_CONTINUATION", rr=2.0),
            rr=[2.0, 3.0],
        )
        self.assertEqual(len(report.experiments), 2)
        self.assertEqual(len({e.experiment_id for e in report.experiments}), 2)
        first, second = report.experiments
        self.assertEqual(first.metrics["wins"], 1)
        self.assertEqual(second.metrics["wins"], 0)
        self.assertEqual(second.metrics["unsettled"], 1)


# ==========================================================
# Required behaviors: incremental R / profitable recovery /
# cost of recovery surfaced in report
# ==========================================================


class TestReportFacts(unittest.TestCase):

    def test_incremental_r_and_cost_of_recovery_surfaced(self):
        report = analyze(ALL_RECORDS, EXP_BREAKOUT)
        d = report.to_dict()
        exp = d["experiments"][0]
        # incremental R == 3 wins at +2R minus 1 loss at -1R
        self.assertAlmostEqual(exp["comparison"]["incremental_R"], 5.0)
        self.assertAlmostEqual(exp["recovery"]["incremental_R"], 5.0)
        self.assertAlmostEqual(exp["recovery"]["incremental_pnl"], 10.0)
        self.assertEqual(exp["recovery"]["additional_wins"], 3)
        self.assertEqual(exp["recovery"]["additional_losses"], 1)

    def test_report_sections_and_statement(self):
        report = analyze(ALL_RECORDS, EXP_BREAKOUT)
        d = report.to_dict()
        for key in ("baseline_metrics", "experiments", "rejected",
                    "entry_model_comparison", "directional",
                    "robustness_warnings", "statement"):
            self.assertIn(key, d)
        self.assertIn("no configuration is promoted", d["statement"].lower())
        exp = d["experiments"][0]
        for key in ("metrics", "recovery", "comparison",
                    "robustness", "directional", "config"):
            self.assertIn(key, exp)
        text = report.render()
        self.assertIn("PHASE 9D RESEARCH REPORT", text)
        self.assertIn(EXP_BREAKOUT[0].experiment_id(), text)

    def test_rejected_opportunity_report(self):
        from core.research.analyzer import rejected_by_reason
        info = rejected_by_reason(ALL_RECORDS)
        self.assertEqual(info["records_rejected"], 6)
        self.assertEqual(info["by_reason"]["TOO_FAR_FROM_MARKET"], 3)
        self.assertEqual(info["by_reason"]["INSUFFICIENT_RISK_WIDTH"], 2)
        self.assertEqual(info["by_reason"]["STALE_ZONE"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)