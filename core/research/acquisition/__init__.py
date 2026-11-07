"""Phase-17 data-acquisition feasibility (research-only)."""

from core.research.acquisition.feasibility import (
    budget_periods,
    recalculate_requirements,
)
from core.research.acquisition.provenance import (
    ProvenanceManifest,
    manifest_id,
)
from core.research.acquisition.quality import (
    audit_quality,
)

__all__ = [
    "ProvenanceManifest",
    "audit_quality",
    "budget_periods",
    "manifest_id",
    "recalculate_requirements",
    "AccumulationError",
    "accumulate",
    "batch_identity",
    "validate_batch",
]

from core.research.acquisition.accumulator import (
    AccumulationError,
    accumulate,
    batch_identity,
    validate_batch,
)
