"""
====================================================================

QuantEngine

Multi-Period Out-of-Sample Validation (Phase 9M) -- engine

The deterministic 9M re-validation conductor.

Protocol (locked, never optimized):
   1. Chronological partition of the time-ordered opportunity
      population: discovery = leading 50%; trailing region split into
      6 equal non-overlapping OOS periods. NO shuffle, NO
      randomization, NO split re-optimization (SPLIT_PROTOCOL_FROZEN).
   2. Every hypothesis (a CONSUMED 9J/9K/9L discovery, never a new
      experimental search) is replayed on each OOS period via the
      frozen 9C counterfactual machinery against the frozen
      BREAKOUT_CONTINUATION production baseline.
   3. Per-period settling gates (>= 30 eligible opportunities AND >=
      10 candidate trades); below-gate evidence is INCONCLUSIVE.
   4. Familywise multiple-testing accounting over the whole re-validated
      family (Sidak, corrected alpha reported with the family size);
      the robustness tier must satisfy the corrected total-trades gate.
   5. A seven_e_no_go hypothesis is BLOCKED -- the 7E boundary can
      never be resurrected by repeated OOS evidence.

Honesty contract: every settled / inconclusive / unavailable / rejected
period is retained and reported. A conditional hypothesis is evaluated
INSIDE its claimed regime cell and the non-target pool is surfaced
separately -- never merged into a universal claim. Per-symbol and
per-direction splits are surfaced when present.
====================================================================
"""

from core.research.conditional_ml.guards import required_min_n
from core.research.counterfactual.counterfactual_config import (
    CounterfactualConfig,
)
from core.research.oos.aggregator import (
    final_status,
    multiple_testing,
    summarize_periods,
)
from core.research.oos import constants as _c
from core.research.oos.oos_types import (
    HypothesisOosResult,
    HypothesisRecord,
)
from core.research.oos.period import (
    partition,
)
from core.research.oos.report import build_report
from core.research.oos.robustness import classify
from core.research.oos.validator import evaluate_period, evaluate_pool
from core.research.oos.intake import (
    DiscoveryBindingError,
    validate_9l_binding,
)
from core.research.regime.segmenter import segment_observations

_DIR_LOOKUP = {"LONG": "BULLISH", "SHORT": "BEARISH"}


def _rec_symbol(record):
    for attr in ("instrument_id", "symbol"):
        value = getattr(record, attr, None)
        if value:
            return str(value)
    return "UNKNOWN"


def _rec_direction(record):
    d = getattr(record, "direction", "") or ""
    return str(d).upper() if str(d) in ("BULLISH", "BEARISH") else ""


def _expiry(params):
    value = (params or {}).get("expiry")
    if value is None:
        return None
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        raise ValueError("hypothesis expiry must be an integer") from None


def _coerce(hypothesis):
    if isinstance(hypothesis, HypothesisRecord):
        return hypothesis
    if isinstance(hypothesis, dict):
        kwargs = dict(hypothesis)
        allowed = {
            "hypothesis_id", "origin", "statement", "symbol", "direction",
            "regime_dim", "regime_label", "params", "seven_e_no_go",
            "walk_forward_passed", "walk_forward_note",
            "expected_outcome", "evidence",
        }
        unknown = sorted(set(kwargs) - allowed)
        if unknown:
            raise ValueError(
                "unknown HypothesisRecord fields %s" % (unknown,))
        return HypothesisRecord(**kwargs)
    raise ValueError(
        "hypotheses must be HypothesisRecord or dict; got %r"
        % (type(hypothesis).__name__,)
    )


def _match(record, h, obs_map):
    """Scope test: does this opportunity belong to the hypothesis'
    claimed symbol / direction / regime cell?"""
    if h.is_conditional():
        cid = getattr(record, "canonical_id", "") or ""
        obs = obs_map.get(cid)
        if obs is None or not obs.in_regime(h.regime_dim, h.regime_label):
            return False
    if h.symbol and h.symbol != "UNKNOWN":
        if _rec_symbol(record) != h.symbol:
            return False
    if h.direction in _DIR_LOOKUP:
        if _rec_direction(record) != _DIR_LOOKUP[h.direction]:
            return False
    return True


def _match_out_of_cell(record, h, obs_map):
    """Almost-match: correct symbol/direction but OUTSIDE the claimed
    regime cell (the adversarial counterpart of a conditional claim)."""
    if h.symbol and h.symbol != "UNKNOWN":
        if _rec_symbol(record) != h.symbol:
            return False
    if h.direction in _DIR_LOOKUP:
        if _rec_direction(record) != _DIR_LOOKUP[h.direction]:
            return False
    cid = getattr(record, "canonical_id", "") or ""
    obs = obs_map.get(cid)
    return not (obs is not None
                and obs.in_regime(h.regime_dim, h.regime_label))


def _pool_summary(m):
    return {
        "n_opportunities": int(m["n_opportunities"]),
        "n_trades": int(m["n_trades"]),
        "n_candidate_filled": int(m.get("n_candidate_filled") or 0),
        "n_baseline_settled": int(m["n_baseline_settled"]),
        "n_settled": int(m["n_trades"]),
        "expectancy_delta": m["expectancy_delta"],
        "win_rate": m["win_rate"],
        "status": m["status"],
    }


class OosValidationEngine:
    """Deterministic 9M re-validation over consumed discoveries."""

    def __init__(self, gates=None):
        self.gates = dict(_DEFAULT_GATES)
        if gates:
            unknown = sorted(set(gates) - set(_DEFAULT_GATES))
            if unknown:
                raise ValueError(
                    "unknown gate keys %s; supported=%s"
                    % (unknown, sorted(_DEFAULT_GATES))
                )
            for key, value in gates.items():
                if key != "conclusive_only":
                    value = int(value)
                self.gates[key] = value

    # -------------------------------------------------------------

    def run(self, opportunities, candles, base_config, hypotheses,
            outcome_bars=None, lookback=40, atr_period=14,
            discovery_reports=None, require_discovery_provenance=False):
        candles = list(candles or ())
        hypotheses = tuple(_coerce(h) for h in hypotheses)

        if require_discovery_provenance:
            reports = dict(discovery_reports or {})
            for hypothesis in hypotheses:
                if hypothesis.origin == "9L":
                    report = reports.get(hypothesis.hypothesis_id)
                    if report is None:
                        raise DiscoveryBindingError(
                            "missing source 9L report for hypothesis %s"
                            % hypothesis.hypothesis_id)
                    validate_9l_binding(hypothesis, report)
                elif not hypothesis.evidence:
                    raise DiscoveryBindingError(
                        "hypothesis %s lacks discovery provenance tokens"
                        % hypothesis.hypothesis_id)

        if not hypotheses:
            return self._build_report(
                hypotheses=hypotheses, partition=None,
                familywise=None, aggregate=None, results=(),
            )

        # Eager, fail-loud validation of the BASE config (the frozen
        # production baseline must be materializable before any
        # evaluation begins).
        base_params = dict(base_config)
        base_params["entry_model"] = "BREAKOUT_CONTINUATION"
        CounterfactualConfig(
            params=base_params, outcome_bars=outcome_bars,
            baseline_id="baseline")

        oos_periods = int(self.gates["oos_periods"])
        partition_obj = partition(
            opportunities,
            oos_periods=oos_periods,
            discovery_fraction=float(self.gates["discovery_fraction"]),
            purge_bars=int(self.gates["purge_bars"]),
            embargo_bars=int(self.gates["embargo_bars"]),
            min_oos_opportunities_per_period=int(
                self.gates["min_oos_opportunities_per_period"]),
            outcome_bars=outcome_bars,
        )

        obs_map = None
        if any(h.is_conditional() for h in hypotheses):
            obs_map = {
                o.observation_id: o
                for o in segment_observations(
                    partition_obj.ordered, candles,
                    lookback=lookback, atr_period=atr_period)
            }

        family = [h for h in hypotheses if not h.seven_e_no_go]
        family_size = len(family)
        corrected_total = required_min_n(
            int(self.gates["min_total_oos_trades"]), family_size)

        eff_gates = dict(self.gates)
        eff_gates["min_total_oos_trades"] = corrected_total

        familywise = multiple_testing(
            family_size, alpha=float(self.gates.get("alpha", _c.ALPHA)))

        gen = self._evaluate_hypothesis
        results = tuple(
            gen(h, partition_obj, candles, base_config, outcome_bars,
                eff_gates, obs_map)
            for h in hypotheses
        )

        aggregate = self._aggregate(results)
        return self._build_report(
            hypotheses=hypotheses, partition=partition_obj,
            familywise=familywise, aggregate=aggregate, results=results,
        )

    # -------------------------------------------------------------

    def run_preregistered(self, *, preregistration, dataset_identity,
                          opportunities, candles, base_config,
                          outcome_bars=None, lookback=40, atr_period=14,
                          discovery_reports=None):
        """Execute 9M only from a verified immutable preregistration.

        This is the final frozen-execution seam: no hypothesis selection,
        protocol override, dataset substitution, or production promotion is
        permitted here.
        """
        from core.research.readiness.preregistration import FrozenPreregistration
        if not isinstance(preregistration, FrozenPreregistration):
            raise ValueError("preregistration must be FrozenPreregistration")
        if not preregistration.verify_identity():
            raise ValueError("preregistration identity verification failed")
        if preregistration.is_production_ready is not False:
            raise ValueError("preregistration cannot be production-ready")
        if dataset_identity != preregistration.dataset_identity:
            raise ValueError("dataset identity mismatch")
        if preregistration.required_period_count != self.gates["oos_periods"]:
            raise ValueError("OOS period protocol drift")
        if preregistration.minimum_trades_per_period != self.gates["min_oos_trades_per_period"]:
            raise ValueError("minimum trades/period protocol drift")
        if preregistration.minimum_total_trades != self.gates["min_total_oos_trades"]:
            raise ValueError("minimum total trades protocol drift")
        if tuple(h.hypothesis_id for h in preregistration.hypotheses) != tuple(preregistration.hypothesis_ids):
            raise ValueError("frozen hypothesis ordering mismatch")
        # A preregistration is itself the exact hypothesis authority.
        # Provenance is rechecked by run() before any evaluation.
        return self.run(
            opportunities=opportunities, candles=candles, base_config=base_config,
            hypotheses=preregistration.hypotheses, outcome_bars=outcome_bars,
            lookback=lookback, atr_period=atr_period,
            discovery_reports=discovery_reports, require_discovery_provenance=True)

    # -------------------------------------------------------------

    def _build_report(self, hypotheses, partition, familywise,
                      aggregate, results):
        return build_report(hypotheses, partition, familywise,
                            aggregate, results)

    def _evaluate_hypothesis(self, h, partition_obj, candles, base_config,
                             outcome_bars, eff_gates, obs_map):
        if h.seven_e_no_go:
            return HypothesisOosResult(
                hypothesis_id=h.hypothesis_id,
                origin=h.origin,
                statement=h.statement,
                symbol=h.symbol,
                direction=h.direction,
                regime_dim=h.regime_dim,
                regime_label=h.regime_label,
                seven_e=True,
                status=_c.OOS_STATUSES[0],
                reasons=(_c.SEVEN_E_NO_GO,),
                walk_forward_passed=h.walk_forward_passed,
                walk_forward_note=h.walk_forward_note,
            )

        period_evs = []
        n_periods = partition_obj.n_periods()
        for i in range(n_periods):
            records = [r for r in partition_obj.period_records(i)
                       if _match(r, h, obs_map)]
            period_evs.append(
                _evaluate_period(records, candles, base_config, h,
                                 outcome_bars, eff_gates,
                                 "OOS-%d" % (i + 1))
            )

        sub = self._subevals(h, partition_obj, candles, base_config,
                             outcome_bars, eff_gates, obs_map)

        status, reasons = final_status(
            h, tuple(period_evs), eff_gates)

        aggregate = summarize_periods(
            tuple(period_evs), eff_gates)
        aggregate["total_oos_trades"] = sum(
            p.n_trades for p in period_evs)
        aggregate["n_periods_checked"] = len(period_evs)

        robustness = classify(
            h, aggregate,
            regime=sub["regime"],
            symbols=sub["symbols"],
            directions=sub["directions"],
            gates=eff_gates,
        )

        return HypothesisOosResult(
            hypothesis_id=h.hypothesis_id,
            origin=h.origin,
            statement=h.statement,
            symbol=h.symbol,
            direction=h.direction,
            regime_dim=h.regime_dim,
            regime_label=h.regime_label,
            seven_e=h.seven_e_no_go,
            status=status,
            reasons=reasons,
            periods_tested=aggregate["periods_tested"],
            periods_available=aggregate["periods_available"],
            periods_survived=aggregate["periods_survived"],
            periods_rejected=aggregate["periods_rejected"],
            periods_inconclusive=aggregate["periods_inconclusive"],
            periods_unavailable=aggregate["periods_unavailable"],
            survival_ratio=aggregate["survival_ratio"],
            sign_consistent_periods=aggregate["sign_consistent_periods"],
            economic_consistent=aggregate["economic_consistent"],
            per_period=tuple(period_evs),
            economic_statistics=aggregate["economic_statistics"],
            regime=sub["regime"],
            symbols=sub["symbols"],
            directions=sub["directions"],
            walk_forward_passed=h.walk_forward_passed,
            walk_forward_note=h.walk_forward_note,
            survives_familywise=(
                status in (_c.OOS_STATUSES[-1], _c.OOS_STATUSES[-2])
            ),
            robustness=_robustness_dict(robustness),
        )

    # -------------------------------------------------------------

    def _subevals(self, h, partition_obj, candles, base_config,
                  outcome_bars, eff_gates, obs_map):
        oos_all = [r for period in partition_obj.oos_periods for r in period]
        outcomes = {"n_oos": len(oos_all)}

        regime = {"note": "not conditioned"}
        if h.is_conditional():
            target = [r for r in oos_all if _match(r, h, obs_map)]
            other = [r for r in oos_all if _match_out_of_cell(r, h, obs_map)]
            regime = {
                "dim": h.regime_dim,
                "label": h.regime_label,
                "target": _pool_summary(evaluate_pool(
                    target, candles, base_config, h, outcome_bars,
                    eff_gates)),
            }
            if other:
                regime["non_target"] = _pool_summary(evaluate_pool(
                    other, candles, base_config, h, outcome_bars,
                    eff_gates))

        symbols = {}
        for rec in oos_all:
            sym = _rec_symbol(rec)
            symbols.setdefault(sym, []).append(rec)
        symbols_summary = {
            sym: _pool_summary(evaluate_pool(
                recs, candles, base_config, h, outcome_bars, eff_gates))
            for sym, recs in sorted(symbols.items())
        }

        directions = {}
        for direction in ("BULLISH", "BEARISH"):
            recs = [r for r in oos_all
                    if _rec_direction(r) == direction]
            if not recs:
                continue
            directions[direction] = _pool_summary(evaluate_pool(
                recs, candles, base_config, h, outcome_bars, eff_gates))
        directions = {k: directions[k] for k in sorted(directions)}

        return {"outcomes": outcomes, "regime": regime,
                "symbols": symbols_summary, "directions": directions}

    # -------------------------------------------------------------

    def _aggregate(self, results):
        defensible = [
            r for r in results
            if r.status in (_c.OOS_STATUSES[-1], _c.OOS_STATUSES[-2])
        ]
        robust = [r for r in results if r.status == _c.OOS_STATUSES[-2]]
        validated = [r for r in results
                     if r.status == _c.OOS_STATUSES[-1]]
        blocked = [r for r in results
                   if r.status == _c.OOS_STATUSES[0]]
        unavailable = [r for r in results
                       if r.status in (_c.OOS_STATUSES[1],
                                       _c.OOS_STATUSES[2])]
        rejected = [r for r in results
                    if r.status == _c.OOS_STATUSES[3]]
        return {
            "n_hypotheses": len(results),
            "n_blocked": len(blocked),
            "n_unavailable_inconclusive": len(unavailable),
            "n_rejected": len(rejected),
            "n_partial_promising": len([
                r for r in results
                if r.status in (_c.OOS_STATUSES[4], _c.OOS_STATUSES[5])
            ]),
            "n_robust": len(robust),
            "n_validated_research_only": len(validated),
            "n_research_only_confirmed": len(defensible),
            "n_periods": 6,
        }


def _evaluate_period(records, candles, base_config, h, outcome_bars,
                     gates, period_label):
    """Per-period evidence via the frozen 9C replay (fixed label)."""
    return evaluate_period(period_label, records, candles, base_config,
                           h, outcome_bars, gates)


def _robustness_dict(robustness):
    return {
        "level": robustness["level"],
        "passed": dict(list(robustness["passed"].items())),
        "reasons": dict(list(robustness["reasons"].items())),
    }


# ------------------------------------------------------------------
# Effective gate defaults (locked protocol; overridable only by
# explicit caller configuration).
# ------------------------------------------------------------------

_DEFAULT_GATES = {
    "oos_periods": _c.OOS_PERIODS,
    "discovery_fraction": _c.DISCOVERY_FRACTION,
    "min_oos_opportunities_per_period": _c.MIN_OOS_OPPORTUNITIES_PER_PERIOD,
    "min_oos_trades_per_period": _c.MIN_OOS_TRADES_PER_PERIOD,
    "min_total_oos_trades": _c.MIN_TOTAL_OOS_TRADES,
    "min_surviving_periods": _c.MIN_SURVIVING_PERIODS,
    "required_sign_consistent_periods": _c.REQUIRED_SIGN_CONSISTENT_PERIODS,
    "purge_bars": _c.PURGE_BARS,
    "embargo_bars": _c.EMBARGO_BARS,
    "economic_delta_r": _c.ECONOMIC_DELTA_R,
    "loss_rate_expansion": _c.LOSS_RATE_EXPANSION,
    "alpha": _c.ALPHA,
    "conclusive_only": False,
}