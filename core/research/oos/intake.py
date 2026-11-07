"""Phase 9M discovery-provenance intake and binding checks.

This module never creates a HypothesisRecord from a 9L finding. It only
verifies that an already-created, frozen hypothesis explicitly names the
frozen research report/finding from which it was consumed.
"""

from core.research.oos.oos_types import HypothesisRecord


class DiscoveryBindingError(ValueError):
    pass


def _report_dict(report):
    if hasattr(report, "to_dict"):
        return report.to_dict()
    if isinstance(report, dict):
        return dict(report)
    raise DiscoveryBindingError("source report must expose to_dict() or be a dict")


def _finding_exists(data, surface, key):
    values = data.get(surface) or ()
    for item in values:
        if not isinstance(item, dict):
            continue
        candidates = {
            str(item.get("finding_id", "")),
            str(item.get("cell_id", "")),
            str(item.get("surface", "")),
        }
        if key in candidates:
            return True
    return False


def validate_9l_binding(hypothesis, report):
    """Validate an existing 9L-origin hypothesis against its source report.

    Expected provenance token format::

        9L:<report_id>:<surface>:<finding_key>

    No finding is created or selected here. The caller remains responsible
    for human/research-layer selection and preregistration.
    """
    if not isinstance(hypothesis, HypothesisRecord):
        raise DiscoveryBindingError("hypothesis must be HypothesisRecord")
    if hypothesis.origin != "9L":
        raise DiscoveryBindingError("hypothesis origin must be 9L")
    data = _report_dict(report)
    report_id = str(data.get("report_id") or "")
    if not report_id:
        raise DiscoveryBindingError("source 9L report_id is missing")

    tokens = []
    for token in hypothesis.evidence:
        parts = token.split(":", 3)
        if len(parts) == 4 and parts[0] == "9L":
            tokens.append(parts)

    if not tokens:
        raise DiscoveryBindingError(
            "9L hypothesis has no binding token; expected "
            "9L:<report_id>:<surface>:<finding_key>"
        )

    matches = []
    for _, rid, surface, key in tokens:
        if rid != report_id:
            continue
        if _finding_exists(data, surface, key):
            matches.append((surface, key))

    if not matches:
        raise DiscoveryBindingError(
            "9L hypothesis provenance does not match the supplied report"
        )

    return {
        "bound": True,
        "report_id": report_id,
        "matches": tuple(sorted(set(matches))),
        "hypothesis_id": hypothesis.hypothesis_id,
    }
