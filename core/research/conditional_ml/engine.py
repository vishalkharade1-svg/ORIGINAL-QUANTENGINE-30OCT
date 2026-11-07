"""
====================================================

QuantEngine

Conditional ML / Opportunity Discovery (Phase 9L) -- engine

Advanced conditional ML that fuses the frozen 9G stats/ML machinery
with the frozen 9K regime framework into one evidence pipeline:

   CONTEXT BUILD
       opportunity -> OpportunityContext (regime at decision + fill,
       decision-time 9F features, baseline entry state)
   GRID (fixed, bounded)
       exactly the FIXED supported alternatives
       (LIMIT_RETEST / MARKET_CONFIRMATION / BREAKOUT_CONTINUATION)
       replayed independently by 9C -- never an unbounded optimizer
   PIPELINE (in order, mirroring the 9L contract)
       generate -> filter -> temporal split (TRAIN|VALIDATION|OOS)
       -> conditional outcome probabilities -> recovery probability
       -> entry-model selection -> regime-conditional feature
       interactions -> regime transition detection -> symbol
       segmentation -> OOS confidence/calibration -> GLOBAL strict
       multiple-testing correction -> robustness -> economic
       significance -> minimum sample -> limitations -> research
       finding (frozen ConditionalMlReport, production_ready=False)

Guardrails enforced here:
   * determinism (no random / uuid / datetime),
   * no lookahead (decision-time data only; fills read 9C facts),
   * research-only imports (core.research.*),
   * report is FROZEN and is_production_ready is permanently False;
     the report can never be an execution directive.
====================================================
"""

from types import SimpleNamespace

from core.research.ml.split import temporal_split
from core.research.conditional_ml.types import (
    CANDIDATE_ALTERNATIVES,
    ENTRY_STATE_NOT_FILLED,
    UNAVAILABLE,
    MAX_INTERACTION_TESTS,
)
from core.research.conditional_ml.contexts import build_contexts
from core.research.conditional_ml.guards import (
    familywise_alpha,
    required_min_n,
    holm_survives,
)
from core.research.conditional_ml.recovery import recovery_probabilities
from core.research.conditional_ml.entries import entry_selection
from core.research.conditional_ml.interactions import interaction_analysis
from core.research.conditional_ml.transitions import transitions
from core.research.conditional_ml.symbols import symbol_behaviour
from core.research.conditional_ml.calibration import calibration_summary
from core.research.conditional_ml.report import ConditionalMlReport

DEFAULT_GATES = {
    "min_recovery_n": 6,
    "min_entries_n": 5,
    "min_interaction_n": 5,
    "min_symbol_n": 12,
    "min_transition_n": 3,
    "min_calibration_n": 10,
    "economic_delta_r": 0.5,
    "alpha": 0.05,
    "validation_fraction": 0.2,
    "oos_fraction": 0.2,
    "lookback": 20,
}


def _result_ok(outcome):
    return getattr(outcome, "result", "").upper() in ("WIN", "LOSS")


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


class ConditionalMlEngine:
    """Deterministic advanced-conditional-ML research orchestrator."""

    def __init__(self, gates=None):
        merged = dict(DEFAULT_GATES)
        if gates:
            merged.update({k: v for k, v in gates.items()
                           if k in DEFAULT_GATES})
        self.gates = merged

    # -------------------------------------------------

    def run(self, opportunities, candles, config=None, baseline_outcomes=None,
            detail=True):
        """Produce a frozen ConditionalMlReport.

        opportunities:      iterable of 9A OpportunityRecord.
        candles:            decision-time candle series.
        config:             optional experiment params dict used to
                            build the FIXED alternative grid (e.g.
                            {"rr": 3.0, "expiry": 12}). entry_model
                            is always overridden per alternative.
        baseline_outcomes:  optional {opportunity_id: 9C baseline
                            CounterfactualOutcome}. When omitted the
                            engine measures the frozen production
                            baseline (BREAKOUT_CONTINUATION) with the
                            same deterministic counterfactual machinery
                            used for the alternatives.
        """
        gates = self.gates
        opportunities = list(opportunities)
        candles = list(candles)

        from core.research.counterfactual.counterfactual_runner import \
            CounterfactualRunner
        from core.research.counterfactual.counterfactual_config import \
            CounterfactualConfig

        base_params = dict(config or {})
        alternatives = list(CANDIDATE_ALTERNATIVES)
        runner = CounterfactualRunner(candles, baseline_id="baseline")
        outcomes_by_alt = {}
        for alt in alternatives:
            cf_config = CounterfactualConfig(
                params=dict(base_params, entry_model=alt),
                outcome_bars=base_params.get("outcome_bars"),
                baseline_id="baseline",
            )
            outcomes_by_alt[alt] = runner.run_config(
                opportunities, cf_config, experiment_id=cf_config.experiment_id(),
            )

        baseline_outcomes = dict(baseline_outcomes or {})
        if not baseline_outcomes:
            # No 9C baseline map supplied: the frozen production
            # baseline (BREAKOUT_CONTINUATION) is measured by the same
            # deterministic counterfactual machinery (reused, not
            # re-simulated).
            baseline_outcomes = {
                getattr(o, "opportunity_id", ""): o
                for o in outcomes_by_alt["BREAKOUT_CONTINUATION"]
            }

        contexts = build_contexts(
            opportunities, candles, baseline_outcomes=baseline_outcomes,
            lookback=int(gates.get("lookback", 20)),
        )

        # ---- opportunity rows: one per context, joined with the
        # ---- counterfactual outcomes (decision-bar ordered) ----
        orows, _ = _build_orows(
            contexts, opportunities, baseline_outcomes, outcomes_by_alt)

        # ---- chronological TRAIN | VALIDATION | OOS (no shuffle) ----
        split = temporal_split(
            orows,
            validation_fraction=float(gates["validation_fraction"]),
            oos_fraction=float(gates["oos_fraction"]),
        )
        oos_idx = set(split.oos.indices)

        # ---- enumeration of the TOTAL hypothesis family (fixed grid) ----
        cells = _cells(orows)
        n_entry_h = max(1, len(cells) * len(alternatives))
        n_inter_h = max(1, len(cells) * MAX_INTERACTION_TESTS)
        n_recovery_h = max(1, len(alternatives) * 2)
        n_trans_h = 9
        n_symbol_h = max(1, len(set((r.ctx.symbol or "UNKNOWN")
                                    for r in orows)))
        total_hypotheses = (n_entry_h + n_inter_h + n_recovery_h
                            + n_trans_h + n_symbol_h)
        alpha = float(gates["alpha"])
        corrected_alpha = familywise_alpha(alpha, total_hypotheses)

        # ---- 1. recovery probability (missed/rejected baselines) ----
        rec_findings = recovery_probabilities(
            orows, alternatives,
            min_n=int(gates["min_recovery_n"]),
            n_hypotheses=total_hypotheses,
        )

        # ---- 2. conditional entry-model selection ----
        sel_findings = entry_selection(
            orows, split, alternatives, cells, gates,
            n_hypotheses=total_hypotheses,
        )

        # ---- 3. regime-conditional feature interactions ----
        inter_findings = interaction_analysis(
            orows, split, [r for r, _ in cells], gates,
            n_hypotheses=total_hypotheses,
        )

        # ---- 4. regime transition detection (generated vs fill) ----
        trans_findings = transitions(
            orows,
            min_n=int(gates["min_transition_n"]),
            delta_r=float(gates["economic_delta_r"]),
        )

        # ---- 5. symbol-specific behaviour ----
        sym_findings = symbol_behaviour(
            orows,
            min_n=int(gates["min_symbol_n"]),
            delta_r=float(gates["economic_delta_r"]),
            n_hypotheses=total_hypotheses,
        )

        # ---- 6. OOS confidence / calibration per probability surface ----
        calibration = self._calibrate_oos(
            orows, split, alternatives, gates)

        # ---- 7. GLOBAL multiple-testing guard ----
        mt = _global_multiple_testing(
            gates, total_hypotheses, corrected_alpha, alpha,
            sel_findings, rec_findings, inter_findings, trans_findings,
            sym_findings,
        )

        # ---- inject familywise survival flags (frozen-safe replace) ----
        from dataclasses import replace

        sel_findings = tuple(
            replace(f, survives_familywise=mt["per_finding"].get(
                "entry:%s" % f.cell_id, {}).get("survives", False))
            for f in sel_findings
        )
        rec_findings = tuple(
            replace(f, survives_familywise=mt["per_finding"].get(
                "recovery:%s" % f.finding_id, {}).get("survives", False))
            for f in rec_findings
        )
        inter_findings = tuple(
            replace(f, survives_familywise=mt["per_finding"].get(
                "interaction:%s" % _inter_key(f), {}).get("survives", False))
            for f in inter_findings
        )
        trans_findings = tuple(
            replace(f)
            for f in trans_findings
        )
        sym_findings = tuple(
            replace(f, justified=mt["per_finding"].get(
                "symbol:%s:%s" % (f.symbol, f.regime), {}).get("justified", f.justified))
            for f in sym_findings
        )

        # ---- robustness / limitations ----
        robustness = {
            "pipeline": (
                "generate", "filter", "temporal_split", "conditional_probability",
                "recovery", "entry_selection", "interactions", "transitions",
                "symbols", "calibration", "multiple_testing", "robustness",
                "economic_significance", "minimum_sample", "limitations",
            ),
            "chronological_split": split.to_dict(),
            "alternatives_grid": list(alternatives),
            "fixed_grid": True,
            "combinatorial_cap": MAX_INTERACTION_TESTS,
            "survives_global_familywise": mt["n_survive"],
            "min_oos_n_gate": required_min_n(
                int(gates["min_entries_n"]), total_hypotheses),
        }

        limitations = (
            "research-only evidence; ALWAYS anchor before any prospective use",
            "order-flow / footprint features are UNAVAILABLE without a real "
            "order-flow data stream (OHLCV-only fixture)",
            "OOS observations are the trailing chronological block; small "
            "samples cap every surface",
            "candidate alternatives fixed to the production-supported "
            "entry models only",
            "model is a fixed-form additive-logit evidence aggregator; "
            "no hyper-parameter search",
            "confidence/calibration reported per surface -- a gap is a "
            "finding, not a failure to report",
            "is_production_ready is permanently False",
        )

        report = ConditionalMlReport(
            symbol="UNKNOWN",
            dataset_shape={
                "opportunities": len(orows),
                "contexts": len(contexts),
                "split": split.to_dict(),
                "cells": len(cells),
                "by_entry_state": _entry_state_counts(orows),
            },
            recovery=rec_findings,
            entry_selection=sel_findings,
            interactions=inter_findings,
            transitions=trans_findings,
            symbols=sym_findings,
            calibration=calibration,
            multiple_testing=mt,
            robustness=robustness,
            limitations=limitations,
            research_only=True,
            is_production_ready=False,
        )
        return report

    # -------------------------------------------------

    def _calibrate_oos(self, orows, split, alternatives, gates):
        """Honest calibration: models fit on TRAIN, probabilities
        predicted on OOS, compared to realised outcomes."""
        from core.research.conditional_ml.probabilities import OutcomeModel

        min_n = int(gates["min_calibration_n"])
        train_idx = list(split.train.indices)
        oos_idx = list(split.oos.indices)
        summaries = []

        # WIN surface per alternative (filled attempts)
        for alt in alternatives:
            train_rows = [_CalRow(orows[i].ctx.tokens(),
                                  orows[i].labels[alt],
                                  orows[i].rs.get(alt))
                          for i in train_idx
                          if orows[i].alt_filled.get(alt)
                          and orows[i].labels.get(alt) is not None]
            model = OutcomeModel().fit(train_rows)
            if not model.fitted():
                continue
            pairs = []
            for i in oos_idx:
                r = orows[i]
                if r.alt_filled.get(alt) and r.labels.get(alt) is not None:
                    pairs.append((model.predict_p(r.ctx.tokens()),
                                  int(r.labels[alt])))
            summaries.append(calibration_summary(
                pairs, surface="WIN:%s" % alt,
                min_n_gate=max(min_n, 2),
            ))

        # RECOVERY surface per alternative (missed baselines only)
        for alt in alternatives:
            train_rows = [_CalRow(orows[i].ctx.tokens(),
                                  orows[i].recovery[alt], None)
                          for i in train_idx
                          if orows[i].ctx.entry_state == ENTRY_STATE_NOT_FILLED
                          and orows[i].recovery.get(alt) is not None]
            model = OutcomeModel().fit(train_rows)
            if not model.fitted():
                continue
            pairs = []
            for i in oos_idx:
                r = orows[i]
                if r.ctx.entry_state == ENTRY_STATE_NOT_FILLED \
                        and r.recovery.get(alt) is not None:
                    pairs.append((model.predict_p(r.ctx.tokens()),
                                  int(r.recovery[alt])))
            summaries.append(calibration_summary(
                pairs, surface="RECOVERY:%s" % alt,
                min_n_gate=max(min_n, 2),
            ))

        return tuple(summaries)


class _CalRow:
    __slots__ = ("tokens", "label", "r")

    def __init__(self, tokens, label, r):
        self.tokens = tokens
        self.label = label
        self.r = r

    # -------------------------------------------------

def _global_multiple_testing(gates, total_hypotheses, corrected_alpha,
                             alpha, sel_findings, rec_findings,
                             inter_findings, trans_findings,
                             sym_findings):
        per_finding = {}

        # entry selection: p-value based survival vs global alpha
        for f in sel_findings:
            p = None
            row = f.alternatives
            if f.selected is not None:
                for a in row:
                    if a.alternative == f.selected:
                        p = a.p_two_sided
            n = None
            if f.selected is not None:
                for a in row:
                    if a.alternative == f.selected:
                        n = a.n_oos
            gate = f.min_oos_n_gate
            ok = (f.status == "ENTRY_SELECTION_SUPPORTED"
                  and n is not None and n >= gate
                  and p is not None and p <= corrected_alpha)
            per_finding["entry:%s" % f.cell_id] = {
                "survives": bool(ok),
                "p": p,
                "n": n,
                "family": "entry_selection",
            }

        # recovery: binomial z p-value vs global alpha
        for f in rec_findings:
            p = None
            if f.n and f.recovered is not None and f.n > 0:
                p = _binom_z(f.recovered, f.n)
            ok = (f.status == "RECOVERY_SUPPORTED"
                  and p is not None and p <= corrected_alpha)
            per_finding["recovery:%s" % f.finding_id] = {
                "survives": bool(ok),
                "p": p,
                "n": f.n,
                "family": "recovery",
            }

        # interactions: HOLM within the interaction family plus the
        # global sidak alpha as an additional hard floor
        inter_ps = [_inter_p(f) for f in inter_findings]
        inter_flags, _ = holm_survives(inter_ps, alpha=alpha)
        for f, flag in zip(inter_findings, inter_flags):
            p = _inter_p(f)
            ok = bool(flag) and (p is None or p <= corrected_alpha)
            per_finding["interaction:%s" % _inter_key(f)] = {
                "survives": ok,
                "p": p,
                "n": f.n_oos,
                "family": "interactions",
            }

        # transitions: status-based (already stable/changed) + note;
        # survival additionally requires a non-negative expectancy so a
        # worse-filling transition is never counted as a discovery.
        for f in trans_findings:
            key = "transition:%s:%s" % (f.generated_regime, f.filled_regime)
            per_finding[key] = {
                "survives": f.status == "CHANGED"
                and (f.avg_r is None or f.avg_r >= float(gates["economic_delta_r"])),
                "p": None,
                "n": f.n,
                "family": "transitions",
            }

        # symbols: expectancy delta vs global + plant the survival flag
        for f in sym_findings:
            p = None
            if f.n and f.avg_r is not None and f.global_avg_r is not None:
                p = _mean_z(f.avg_r, f.n, f.delta_expectancy)
            ok = f.justified and f.delta_expectancy is not None \
                and f.delta_expectancy >= float(gates["economic_delta_r"]) \
                and (p is None or p <= corrected_alpha)
            per_finding["symbol:%s:%s" % (f.symbol, f.regime)] = {
                "survives": bool(ok),
                "justified": bool(ok),
                "p": p,
                "n": f.n,
                "family": "symbols",
            }

        n_survive = sum(1 for d in per_finding.values() if d["survives"])
        return {
            "total_hypotheses": total_hypotheses,
            "alpha": alpha,
            "corrected_alpha": round(corrected_alpha, 6),
            "n_survive": n_survive,
            "per_finding": per_finding,
            "method": "sidak_global + holm_within_interaction_family",
        }


def _inter_p(f):
    return f.p_value


def _inter_key(f):
    return "%s:%s" % (f.regime, "|".join(sorted(f.features)))


def _binom_z(k, n):
    """deterministic binomial p-value (win-rate vs 0.5, two-sided)."""
    import math

    if n <= 0:
        return None
    p = k / n
    se = math.sqrt(p * (1 - p) / n)
    if se <= 0:
        return None
    # two-sided tail probability P(|Z| > z)
    return float(1.0 - math.erf(abs(p - 0.5) / se / math.sqrt(2.0)))


def _mean_z(mean, n, delta):
    """crude deterministic z for a mean-difference p-value."""
    import math

    if n <= 1:
        return None
    # two-sided tail probability P(|Z| > z)
    return min(1.0, max(0.0, float(
        1.0 - math.erf(abs(delta) * math.sqrt(n / 1.0) / math.sqrt(2.0)))))


def _cells(orows):
    seen = {}
    for r in orows:
        key = (r.ctx.primary_generated() or UNAVAILABLE,
               (r.ctx.direction or "").upper())
        seen[key] = None
    return sorted(seen.keys(), key=lambda x: (str(x[0]), str(x[1])))


def _entry_state_counts(orows):
    from collections import Counter

    counter = Counter(getattr(r, "entry_state", "UNKNOWN") for r in orows)
    return {str(k): int(v) for k, v in sorted(counter.items())}


def _build_orows(contexts, opportunities, baseline_outcomes, outcomes_by_alt):
    from collections import OrderedDict

    pool = OrderedDict((c.opportunity_id, c) for c in contexts)
    by_id = {}
    orows = []
    for o in opportunities:
        cid = getattr(o, "canonical_id", "") or ""
        ctx = pool.get(cid)
        if ctx is None:
            continue
        baseline = baseline_outcomes.get(cid)
        labels = {}
        rs = {}
        maes = {}
        alt_filled = {}
        alt_outcomes = {}
        for alt, outcomes in outcomes_by_alt.items():
            out = None
            for oo in outcomes:
                if getattr(oo, "opportunity_id", "") == cid:
                    out = oo
                    break
            alt_outcomes[alt] = out
            alt_filled[alt] = bool(getattr(out, "filled", False))
            labels[alt] = None
            rs[alt] = None
            maes[alt] = None
            if out is not None:
                result = getattr(out, "result", "").upper()
                if getattr(out, "filled", False) and result in ("WIN", "LOSS"):
                    labels[alt] = 1 if result == "WIN" else 0
                    rs[alt] = _num(getattr(out, "r", None))
                    maes[alt] = _num(getattr(out, "mae", None))
        recovery = {}
        is_miss = False
        if baseline is not None:
            is_miss = not bool(getattr(baseline, "filled", False))
        if is_miss:
            for alt in outcomes_by_alt:
                out = alt_outcomes[alt]
                recovery[alt] = int(
                    out is not None
                    and bool(getattr(out, "filled", False))
                    and getattr(out, "result", "").upper() == "WIN"
                )
        baseline_filled = bool(getattr(baseline, "filled", False)) \
            if baseline is not None else ctx.baseline_filled
        baseline_r = _num(getattr(baseline, "r", None)) \
            if baseline is not None else ctx.baseline_r
        by_id[cid] = SimpleNamespace(
            ctx=ctx,
            baseline_filled=baseline_filled,
            baseline_r=baseline_r,
            labels=labels,
            rs=rs,
            maes=maes,
            alt_filled=alt_filled,
            alt_outcomes=alt_outcomes,
            recovery=recovery,
            entry_state=ctx.entry_state,
            decision_bar=ctx.decision_bar,
            known=is_miss,
        )
        orows.append(by_id[cid])
    return orows, by_id