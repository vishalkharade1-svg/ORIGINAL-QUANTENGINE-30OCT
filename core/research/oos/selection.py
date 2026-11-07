"""Explicit 9L -> 9M hypothesis admission boundary.

Research-only: no automatic selection, ranking, promotion, or execution.
"""
from dataclasses import dataclass, field

from core.research.conditional_ml.types import (
    ENTRY_SELECTION_SUPPORTED, RECOVERY_SUPPORTED,
)
from core.research.oos.oos_types import HypothesisRecord
from core.research.oos.intake import validate_9l_binding, DiscoveryBindingError

SUPPORTED_SURFACES = ("entry_selection", "recovery")

class NineLSelectionError(ValueError):
    pass

@dataclass(frozen=True)
class NineLSelection:
    report_id: str
    surface: str
    finding_key: str
    statement: str
    symbol: str = ""
    direction: str = ""
    regime_dim: object = None
    regime_label: object = None
    params: dict = field(default_factory=dict)
    expected_outcome: str = ""
    walk_forward_passed: bool = False
    walk_forward_note: str = ""
    seven_e_no_go: bool = False

def _data(report):
    if not hasattr(report, "to_dict"):
        raise NineLSelectionError("report must expose to_dict()")
    data=report.to_dict()
    if data.get("phase") != "9L" or data.get("research_only") is not True or data.get("is_production_ready") is not False:
        raise NineLSelectionError("source report is not a frozen research-only 9L report")
    return data

def _find(data, surface, key):
    for item in data.get(surface) or ():
        if not isinstance(item, dict): continue
        if key in (str(item.get("finding_id","")), str(item.get("cell_id",""))):
            return item
    raise NineLSelectionError("finding %s not found on %s" % (key, surface))

def admit_9l_selection(selection, report):
    if not isinstance(selection, NineLSelection):
        raise NineLSelectionError("selection must be NineLSelection")
    data=_data(report)
    if selection.report_id != data.get("report_id"):
        raise NineLSelectionError("selection report_id mismatch")
    if selection.surface not in SUPPORTED_SURFACES:
        raise NineLSelectionError("unsupported 9L surface %r" % selection.surface)
    if selection.seven_e_no_go:
        raise NineLSelectionError("7E NO-GO hypotheses cannot be admitted")
    if not isinstance(selection.params, dict) or not selection.params:
        raise NineLSelectionError("selection params must be explicit and non-empty")
    if not selection.params.get("entry_model"):
        raise NineLSelectionError("selection must freeze an explicit entry_model")
    finding=_find(data, selection.surface, selection.finding_key)
    if not bool(finding.get("survives_familywise", False)):
        raise NineLSelectionError("finding does not survive familywise correction")
    if selection.surface == "entry_selection":
        if finding.get("status") != ENTRY_SELECTION_SUPPORTED:
            raise NineLSelectionError("entry-selection finding is not supported")
        if selection.params["entry_model"] != finding.get("selected"):
            raise NineLSelectionError("entry_model does not match selected alternative")
        if selection.regime_label is not None and selection.regime_label != finding.get("regime"):
            raise NineLSelectionError("regime constraint mismatch")
        if selection.direction and selection.direction != finding.get("direction"):
            raise NineLSelectionError("direction constraint mismatch")
    else:
        if finding.get("status") != RECOVERY_SUPPORTED:
            raise NineLSelectionError("recovery finding is not supported")
        if selection.params["entry_model"] != finding.get("alternative"):
            raise NineLSelectionError("entry_model does not match recovery alternative")
        if selection.regime_label is not None and selection.regime_label != finding.get("regime"):
            raise NineLSelectionError("regime constraint mismatch")
    h=HypothesisRecord(
        origin="9L", statement=selection.statement, symbol=selection.symbol,
        direction=selection.direction, regime_dim=selection.regime_dim,
        regime_label=selection.regime_label, params=dict(selection.params),
        seven_e_no_go=False, walk_forward_passed=selection.walk_forward_passed,
        walk_forward_note=selection.walk_forward_note, expected_outcome=selection.expected_outcome,
        evidence=("9L:%s:%s:%s" % (selection.report_id, selection.surface, selection.finding_key),),
    )
    try:
        validate_9l_binding(h, report)
    except DiscoveryBindingError as exc:
        raise NineLSelectionError(str(exc)) from exc
    return h
