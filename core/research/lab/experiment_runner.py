"""
====================================================

QuantEngine

Research Lab -- experiment runner (Phase 9B)

Runs an ExperimentConfig across many OpportunityRecords through
the OpportunityReplay engine, aggregates deterministic metrics and
the recovery report, and assembles an ExperimentResult.

Deterministic experiment id: a stable hash of the config params +
baseline id (never a random UUID), so identical config + identical
candles + identical journal yield an identical id and outcome.

Production isolation: the runner only reads OpportunityRecords and
candles. It never mutates production strategy / risk / portfolio
configuration and never writes to the production TradeRegistry.
====================================================
"""

import hashlib
import json

from core.research.lab.opportunity_replay import OpportunityReplay
from core.research.lab.metrics import metrics
from core.research.lab.recovery import OpportunityRecoveryReport
from core.research.lab.experiment_result import ExperimentResult


def experiment_id_for(config, baseline_id):
    payload = json.dumps(
        {
            "config": _jsonable(config.to_params()),
            "baseline_id": baseline_id,
        },
        sort_keys=True,
        default=str,
    ).encode("utf-8")
    return "exp-" + hashlib.sha1(payload).hexdigest()[:12]


def _jsonable(value):
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


class ExperimentRunner:
    """Runs a config over opportunities and assembles results."""

    def __init__(self, candles, baseline_id="baseline"):
        self.replay = OpportunityReplay(candles)
        self.baseline_id = baseline_id

    def run(self, opportunities, config, experiment_id=None):
        experiment_id = experiment_id or experiment_id_for(config, self.baseline_id)
        outcomes = []
        replay_errors = []
        for record in opportunities:
            # Fail-tolerant per opportunity (9A philosophy): one
            # malformed record must never abort the experiment nor
            # corrupt later runs. The error is recorded as a warning
            # and never fabricated into a WIN/LOSS.
            try:
                o = self.replay.replay(record, config, experiment_id=experiment_id)
            except Exception as exc:  # noqa: BLE001 - isolated research path
                replay_errors.append(
                    f"replay failed for {getattr(record, 'canonical_id', '?')}: {exc}"
                )
                continue
            outcomes.append(o)

        population = {
            "opportunities": len(outcomes),
            "eligible": sum(1 for o in outcomes if o.baseline_eligible),
            "rejected": sum(1 for o in outcomes if not o.baseline_eligible),
        }
        m = metrics(outcomes)
        population["simulated_fills"] = sum(1 for o in outcomes if o.filled)
        population["simulated_non_fills"] = sum(1 for o in outcomes if not o.filled)
        population["wins"] = m["wins"]
        population["losses"] = m["losses"]

        recovery = OpportunityRecoveryReport(outcomes).to_dict()
        attribution = {
            "direction_split": _split(outcomes, "direction"),
            "symbol_split": _split(outcomes, "instrument_id", key=lambda o: o.instrument_id),
            "regime_split": {},
        }

        warnings = []
        for o in outcomes:
            warnings.extend(o.warnings)
        warnings.extend(replay_errors)

        return ExperimentResult(
            experiment_id=experiment_id,
            baseline_id=self.baseline_id,
            config=config,
            population=population,
            metrics=m,
            recovery=recovery,
            attribution=attribution,
            warnings=list(dict.fromkeys(warnings)),
            outcomes=outcomes,
        )


def _split(outcomes, attr, key=None):
    result = {}
    for o in outcomes:
        k = key(o) if key else getattr(o, attr, "")
        bucket = result.setdefault(k or "UNKNOWN", {"wins": 0, "losses": 0, "total": 0})
        bucket["total"] += 1
        if o.result == "WIN":
            bucket["wins"] += 1
        elif o.result == "LOSS":
            bucket["losses"] += 1
    return result
