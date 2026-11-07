"""Explicit 9L selection -> frozen preregistration handoff."""
from core.research.oos.oos_types import HypothesisRecord
from core.research.oos.intake import validate_9l_binding, DiscoveryBindingError
from core.research.readiness.preregistration import FrozenPreregistration

class SelectionPreregistrationError(ValueError):
    pass

def create_9l_preregistration(*, selections, report, dataset_identity, discovery_boundary, oos_boundary,
                               minimum_contiguous_bars, minimum_fresh_bars, economics_requirements,
                               multiple_testing_family, regime_constraints=(), symbol_constraints=(),
                               directional_constraints=(), frozen_execution_semantics, limitations=()):
    if not isinstance(selections, (list, tuple)) or not selections:
        raise SelectionPreregistrationError("explicit non-empty hypothesis list is required")
    if not hasattr(report, "to_dict") or not hasattr(type(report), "from_dict"):
        raise SelectionPreregistrationError("source report must support canonical reload")
    try:
        canonical_report=type(report).from_dict(report.to_dict())
    except Exception as exc:
        raise SelectionPreregistrationError("source 9L report failed canonical reload: %s" % exc) from exc
    if canonical_report.to_dict() != report.to_dict():
        raise SelectionPreregistrationError("source 9L report changed during canonical reload")
    hs=[]
    for h in selections:
        if not isinstance(h, HypothesisRecord):
            raise SelectionPreregistrationError("all selections must be HypothesisRecord")
        if h.origin != "9L" or h.seven_e_no_go:
            raise SelectionPreregistrationError("only non-NO-GO 9L hypotheses may be preregistered")
        try: validate_9l_binding(h, canonical_report)
        except DiscoveryBindingError as exc: raise SelectionPreregistrationError(str(exc)) from exc
        hs.append(h)
    ids=[h.hypothesis_id for h in hs]
    if len(set(ids)) != len(ids):
        raise SelectionPreregistrationError("hypothesis IDs must be unique")
    pre=FrozenPreregistration.create(
        hypotheses=tuple(hs), dataset_identity=dataset_identity,
        discovery_boundary=discovery_boundary, oos_boundary=oos_boundary,
        minimum_contiguous_bars=minimum_contiguous_bars, minimum_fresh_bars=minimum_fresh_bars,
        economics_requirements=tuple(economics_requirements),
        multiple_testing_family=multiple_testing_family, regime_constraints=tuple(regime_constraints),
        symbol_constraints=tuple(symbol_constraints), directional_constraints=tuple(directional_constraints),
        frozen_execution_semantics=frozen_execution_semantics, limitations=tuple(limitations))
    if pre.is_production_ready is not False: raise SelectionPreregistrationError("production readiness must remain false")
    return pre
