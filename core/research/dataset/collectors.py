"""
====================================================

QuantEngine

Unified Research Dataset -- collectors (Phase 9I)

Deterministic builders that normalize each frozen 9A-9H artifact
into a list of ResearchRow (the unified research fact model).

Each collector is READ-ONLY: it never mutates the input artifact,
never imports production internals, never orders, never looks ahead,
and never auto-promotes. The join key used to relate evidence across
surfaces is the opportunity/observation id:

   * JOURNAL / COUNTERFACTUAL / FEATURE rows key on the opportunity
     id of the underlying opportunity / counterfactual outcome /
     feature snapshot;
   * ANALYSIS / INTELLIGENCE / ML / RESEARCH rows key on the
     experiment / recommendation / investigation id where no single
     opportunity applies, and carry that as source_id.

All ids are derived deterministically (sha1); no UUIDs / timestamps.
====================================================
"""

from core.research.dataset.row import (
    ResearchRow,
    DatasetSource as S,
)
from core.research.counterfactual import classify_opportunity

_OBSERVED_RESULTS = ("WIN", "LOSS", "UNSETTLED")


def collect_journal(records):
    """Normalize 9A OpportunityRecords into JOURNAL research rows.

    One row per record. kv captures the observed setup/order facts;
    measured captures the observed trade outcome (pnl / R / MAE / MFE)
    plus the baseline economic fingerprint."""
    rows = []
    for rec in records:
        setup = rec.setup or {}
        trade = rec.trade or {}
        direction = rec.direction or ""
        outcome = rec.terminal_outcome or ""
        result = ""
        for cand in _OBSERVED_RESULTS:
            if str(trade.get("result", "")).upper() == cand or \
                    outcome.upper() == cand:
                result = cand
                break
        if not result:
            result = outcome or "UNSETTLED"

        measured = {
            "pnl": trade.get("pnl", 0.0),
            "r": trade.get("r", 0.0),
            "mae": trade.get("mae", 0.0),
            "mfe": trade.get("mfe", 0.0),
            "risk_amount": trade.get("risk_amount", 0.0),
            "bars_held": trade.get("bars_held", 0),
            "entry": setup.get("entry", setup.get("entry_price")),
            "stop": setup.get("stop_loss"),
            "take_profit": setup.get("take_profit"),
            "risk_reward": setup.get("risk_reward"),
            "atr": setup.get("atr"),
        }
        kv = {
            "provenance": str(rec.provenance),
            "exchange": rec.exchange or "",
            "terminal_outcome": outcome,
            "rejection_reasons": list(setup.get("rejection_reasons", [])),
            "order_state": str((rec.order or {}).get("state", "")),
            "strategy": rec.strategy or "",
        }
        rows.append(ResearchRow(
            source=S.JOURNAL,
            observation_id=rec.canonical_id or rec.setup_id,
            instrument_id=rec.instrument_id or "",
            direction=direction,
            timeframe=rec.timeframe or "",
            strategy=rec.strategy or "",
            decision_bar=setup.get("bar") or (rec.order or {}).get("created_bar"),
            category=classify_opportunity(rec),
            result=result,
            source_id=rec.canonical_id or rec.setup_id,
            kv=kv,
            measured=measured,
        ))
    return rows


def collect_counterfactual(outcomes):
    """Normalize 9B/9C CounterfactualOutcomes into COUNTERFACTUAL rows.

    kv captures the experiment-level parameters (entry model / offset /
    expiry / RR / stop / target / confirmation); measured captures the
    replayed result (filled / result / pnl / R / MAE / MFE / bars)."""
    rows = []
    for out in outcomes:
        config = getattr(out, "config", None)
        params = {}
        if config is not None:
            cand = getattr(config, "params", None)
            if cand:
                params = dict(cand)
            elif hasattr(config, "to_dict"):
                params = getattr(config, "to_dict", lambda: {})()
        ov = getattr(out, "outcome_bars", None)
        params_content = dict(params)
        if hasattr(out, "config"):
            inner = getattr(out.config, "outcome_bars", None)
            if inner is not None:
                params_content["outcome_bars"] = inner

        kv = {
            "entry_model": params.get("entry_model"),
            "entry_offset": params.get("entry_offset"),
            "entry_offset_atr": params.get("entry_offset_atr"),
            "expiry": params.get("expiry"),
            "rr": params.get("rr"),
            "stop_mode": params.get("stop_mode"),
            "target_mode": params.get("target_mode"),
            "baseline_terminal": getattr(out, "baseline_terminal", "") or "",
            "baseline_rejection": getattr(out, "baseline_rejection", "") or "",
            "exit_reason": getattr(out, "exit_reason", "") or "",
            "warnings": list(getattr(out, "warnings", []) or []),
        }
        if params_content.get("outcome_bars") is not None:
            kv["outcome_bars"] = params_content["outcome_bars"]

        measured = {
            "entry_reached": bool(getattr(out, "entry_reached", False)),
            "filled": bool(getattr(out, "filled", False)),
            "result": getattr(out, "result", "") or "",
            "pnl": getattr(out, "pnl", 0.0),
            "r": getattr(out, "r", 0.0),
            "mae": getattr(out, "mae", 0.0),
            "mfe": getattr(out, "mfe", 0.0),
            "bars_to_entry": getattr(out, "bars_to_entry", 0),
            "bars_in_trade": getattr(out, "bars_in_trade", 0),
            "decision_bar": getattr(out, "decision_bar"),
            "experimental_rr": getattr(out, "experimental_rr", 0.0),
        }
        op_id = getattr(out, "opportunity_id", "") or \
            getattr(out, "canonical_id", "") or ""
        direction = getattr(out, "direction", "") or ""
        rows.append(ResearchRow(
            source=S.COUNTERFACTUAL,
            observation_id=op_id,
            instrument_id=getattr(out, "instrument_id", "") or "",
            direction=direction,
            timeframe=getattr(out, "timeframe", "") or "",
            strategy=getattr(out, "strategy", "") or "",
            decision_bar=measured["decision_bar"],
            category=getattr(out, "category", "") or "",
            result=getattr(out, "result", "") or "",
            source_id=getattr(out, "experiment_id", "") or "",
            kv=kv,
            measured=measured,
        ))
    return rows


def collect_analysis(report):
    """Normalize a 9D ResearchReport into ANALYSIS rows.

    One row per experiment, plus one baseline row keyed on the report's
    baseline_id. kv carries the config; measured carries the aggregate
    experiment metrics + comparison deltas against baseline."""
    rows = []
    baseline_metrics = dict(getattr(report, "baseline_metrics", {}) or {})
    for exp in getattr(report, "experiments", []) or []:
        metrics = dict(getattr(exp, "metrics", {}) or {})
        config = getattr(exp, "config", None)

        kv = {}
        if config is not None and hasattr(config, "params"):
            kv["params"] = dict(config.params)
        if exp_id := getattr(exp, "experiment_id", ""):
            kv["experiment_id"] = exp_id
        if getattr(exp, "recovery", None) is not None:
            kv["recovered"] = getattr(exp.recovery, "recovered", None)

        measured = {
            "opportunities": metrics.get("opportunities", 0),
            "filled": metrics.get("filled", 0),
            "settled": metrics.get("settled", 0),
            "wins": metrics.get("wins", 0),
            "losses": metrics.get("losses", 0),
            "win_rate": metrics.get("win_rate"),
            "expectancy": metrics.get("expectancy"),
            "avg_R": metrics.get("avg_R"),
            "avg_MAE": metrics.get("avg_MAE"),
            "avg_MFE": metrics.get("avg_MFE"),
            "profit_factor": metrics.get("profit_factor"),
        }
        comparison = getattr(exp, "comparison", None)
        if comparison is not None and hasattr(comparison, "to_dict"):
            cd = comparison.to_dict()
            for k in ("delta_expectancy", "incremental_fills",
                      "incremental_R", "incremental_pnl"):
                measured[k] = cd.get(k)
        rows.append(ResearchRow(
            source=S.ANALYSIS,
            observation_id=exp_id,
            instrument_id="",
            direction="",
            timeframe="",
            strategy="",
            decision_bar=None,
            category="EXPERIMENT",
            result="",
            source_id=exp_id,
            kv=kv,
            measured=measured,
        ))
    if baseline_metrics:
        rows.append(ResearchRow(
            source=S.ANALYSIS,
            observation_id=getattr(report, "baseline_id", "baseline"),
            instrument_id="",
            direction="",
            timeframe="",
            strategy="",
            decision_bar=None,
            category="BASELINE",
            result="",
            source_id=getattr(report, "baseline_id", "baseline"),
            kv={},
            measured=dict(baseline_metrics),
        ))
    return rows


def collect_intelligence(report):
    """Normalize a 9E IntelligenceReport into INTELLIGENCE rows.

    One row per recommendation: kv captures the evidence strength,
    status, category, affected categories/directions/symbols and the
    changed parameters; measured captures the candidate/baseline
    metrics and recovery deltas."""
    rows = []
    for rec in getattr(report, "recommendations", []) or []:
        baseline_m = dict(getattr(rec, "baseline_metrics", {}) or {})
        candidate_m = dict(getattr(rec, "candidate_metrics", {}) or {})

        kv = {
            "category": getattr(rec, "category", "") or "",
            "status": getattr(rec, "status", "") or "",
            "evidence_strength": getattr(rec, "evidence_strength", "") or "",
            "affected_categories": list(
                getattr(rec, "affected_opportunity_categories", ()) or ()
            ),
            "affected_directions": list(
                getattr(rec, "affected_directions", ()) or ()
            ),
            "affected_symbols": list(
                getattr(rec, "affected_symbols", ()) or ()
            ),
            "parameters_changed": dict(
                getattr(rec, "parameters_changed", {}) or {}
            ),
            "hypothesis": getattr(rec, "hypothesis", "") or "",
        }
        measured = {
            "incremental_fills": getattr(rec, "incremental_fills", 0),
            "incremental_R": getattr(rec, "incremental_R", 0.0),
            "incremental_pnl": getattr(rec, "incremental_pnl", 0.0),
            "recovered_opportunities": getattr(rec, "recovered_opportunities", 0),
            "recovered_wins": getattr(rec, "recovered_wins", 0),
            "recovered_losses": getattr(rec, "recovered_losses", 0),
            "sample_size": getattr(rec, "sample_size", 0),
            "expectancy_delta": getattr(rec, "expectancy_delta", 0.0),
            "win_rate_delta": getattr(rec, "win_rate_delta", 0.0),
            "robustness_status": getattr(rec, "robustness_status", "") or "",
        }
        measured.update({
            "candidate_expectancy": candidate_m.get("expectancy"),
            "candidate_filled": candidate_m.get("filled"),
            "baseline_expectancy": baseline_m.get("expectancy"),
            "baseline_filled": baseline_m.get("filled"),
        })
        rows.append(ResearchRow(
            source=S.INTELLIGENCE,
            observation_id=getattr(rec, "recommendation_id", "") or "",
            instrument_id="",
            direction="",
            timeframe="",
            strategy="",
            decision_bar=None,
            category=getattr(rec, "category", "") or "",
            result=getattr(rec, "status", "") or "",
            source_id=getattr(rec, "recommendation_id", "") or "",
            kv=kv,
            measured=measured,
        ))
    return rows


def collect_features(snapshots):
    """Normalize 9F FeatureSnapshots into FEATURE rows.

    One row per snapshot; kv carries each decision-time feature value as
    a single flat bag (feature name -> value), measured carries the
    decision bar / window size / price levels."""
    snap_list = snapshots
    if hasattr(snapshots, "snapshots"):
        snap_list = getattr(snapshots, "snapshots", ()) or ()
    rows = []
    for snap in snap_list:
        features = dict(getattr(snap, "features", {}) or {})
        kv = {}
        for name, value in features.items():
            if value is not None:
                kv[name] = value
        measured = {
            "window_size": getattr(snap, "window_size", 0),
            "entry": getattr(snap, "entry"),
            "stop": getattr(snap, "stop"),
            "target": getattr(snap, "target"),
            "atr": getattr(snap, "atr"),
        }
        rows.append(ResearchRow(
            source=S.FEATURE,
            observation_id=getattr(snap, "opportunity_id", "") or "",
            instrument_id=getattr(snap, "instrument_id", "") or "",
            direction=getattr(snap, "direction", "") or "",
            timeframe=getattr(snap, "timeframe", "") or "",
            strategy="",
            decision_bar=getattr(snap, "decision_bar"),
            category="FEATURE",
            result="",
            source_id=getattr(snap, "opportunity_id", "") or "",
            kv=kv,
            measured=measured,
        ))
    return rows


def collect_ml(report):
    """Normalize a 9G MlResearchReport into ML rows.

    One row per ML target (ENTRY_REACHED / WIN / POSITIVE_R /
    EXPECTED_R / RECOVERY_SUCCESS) plus one row per interaction table
    entry. kv carries target / backend / status; measured carries the
    AUC validation & OOS (the ML evidence)."""
    rows = []
    ml_results = getattr(report, "ml_results", {}) or {}
    for target, res in ml_results.items():
        kv = {
            "target": str(target),
            "backend": res.get("backend") if isinstance(res, dict) else None,
            "status": res.get("status") if isinstance(res, dict) else None,
            "kind": (res.get("kind") if isinstance(res, dict) else None),
        }
        measured = {}
        if isinstance(res, dict):
            measured["auc_validation"] = res.get("auc_validation")
            measured["auc_oos"] = res.get("auc_oos")
        rows.append(ResearchRow(
            source=S.ML,
            observation_id="",
            instrument_id="",
            direction="",
            timeframe="",
            strategy="",
            decision_bar=None,
            category="ML_TARGET",
            result=str(target),
            source_id=str(target),
            kv=kv,
            measured=measured,
        ))
    interactions = getattr(report, "interaction", []) or []
    for table in interactions:
        if isinstance(table, dict):
            kv = {k: v for k, v in table.items()
                  if k not in ("n", "win_rate", "avg_R")}
            measured = {
                "n": table.get("n"),
                "win_rate": table.get("win_rate"),
                "avg_R": table.get("avg_R"),
            }
            rows.append(ResearchRow(
                source=S.ML,
                observation_id="",
                instrument_id="",
                direction="",
                timeframe="",
                strategy="",
                decision_bar=None,
                category="INTERACTION",
                result="",
                source_id="interaction",
                kv=kv,
                measured=measured,
            ))
    return rows


def collect_researcher(investigation):
    """Normalize a 9H InvestigationReport into RESEARCH rows.

    One row per hypothesis (kv = kind / question / features), one row
    per recommendation (kv = status / kind / question, measured = score),
    and one investigation-level row (kv = provider / status / symbol)."""
    rows = []
    inv_id = getattr(investigation, "investigation_id", "") or ""
    rows.append(ResearchRow(
        source=S.RESEARCH,
        observation_id=inv_id,
        instrument_id="",
        direction="",
        timeframe="",
        strategy="",
        decision_bar=None,
        category="INVESTIGATION",
        result=getattr(investigation, "status", "") or "",
        source_id=inv_id,
        kv={
            "provider": getattr(investigation, "provider", "") or "",
            "symbol": getattr(investigation, "symbol", "UNKNOWN"),
            "production_ready": bool(
                getattr(investigation, "production_ready", False)
            ),
        },
        measured={"phase": getattr(investigation, "phase", "9H")},
    ))
    for hyp in getattr(investigation, "hypotheses", ()) or ():
        rows.append(ResearchRow(
            source=S.RESEARCH,
            observation_id=inv_id,
            instrument_id="",
            direction="",
            timeframe="",
            strategy="",
            decision_bar=None,
            category="HYPOTHESIS",
            result=getattr(hyp, "kind", "") or "",
            source_id=getattr(hyp, "hypothesis_id", "") or "",
            kv={
                "kind": getattr(hyp, "kind", "") or "",
                "question": getattr(hyp, "question", "") or "",
                "features": list(getattr(hyp, "features", ()) or ()),
                "overrides": dict(getattr(hyp, "overrides", {}) or {}),
            },
            measured={},
        ))
    for rec in getattr(investigation, "recommendations", ()) or ():
        rows.append(ResearchRow(
            source=S.RESEARCH,
            observation_id=inv_id,
            instrument_id="",
            direction="",
            timeframe="",
            strategy="",
            decision_bar=None,
            category="RECOMMENDATION",
            result=getattr(rec, "status", "") or "",
            source_id=getattr(rec, "recommendation_id", "") or "",
            kv={
                "kind": getattr(rec, "kind", "") or "",
                "question": getattr(rec, "question", "") or "",
                "hypothesis_id": getattr(rec, "hypothesis_id", "") or "",
            },
            measured={"score": getattr(rec, "score", 0.0)},
        ))
    return rows
