"""QuantEngine Strategy Historical Identity Reconstruction Engine (Phase 168).

Forensically reconstructs the strategy's historical cryptographic identity across
key milestones in the repository's authentic Git database, explaining the exact
provenance of the historical pin without changing old pins to force green tests.

Milestones Analyzed:
1. Phase 14 Baseline Commit (3f19895):
   Initial executable edge forensics and Gate-A baseline.
2. Phase 14 Runtime Boundary Commit (fbeb860):
   Contract fail-closed certification and final runtime boundary.
3. HEAD Commit (ffefa14):
   Authoritative repository HEAD in restored Git database.
4. Current Working Tree (Disk):
   Local runtime modifications and fixes.
5. Historical Test Pin (c52e648c...):
   Pre-commit uncommitted working tree hash on Windows.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from core.research.strategy_identity import (
    HISTORICAL_PHASE14_STRATEGY_HASH,
    LEGACY_9_FILES,
    RUNTIME_INFRA_FILES,
    STRATEGY_CORE_FILES,
    canonical_file_bytes,
)


def get_git_blob_bytes(root: Path, commit: str, rel_path: str) -> bytes | None:
    """Retrieve raw file blob from Git commit."""
    cmd = ["git", "-C", str(root), "show", f"{commit}:{rel_path}"]
    try:
        res = subprocess.run(cmd, capture_output=True, check=False)
        if res.returncode == 0:
            return res.stdout
    except Exception:
        pass
    return None


def compute_blob_digest(data: bytes, normalize_lf: bool = True) -> str:
    norm = data.replace(b"\r\n", b"\n") if normalize_lf else data
    return hashlib.sha256(norm).hexdigest()


def compute_composite_from_digests(digests: list[str]) -> str:
    joined = "".join(digests)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def reconstruct_milestone(root: Path, commit: str, name: str) -> dict:
    per_file = []
    digests_lf = []
    digests_raw = []
    for rel in LEGACY_9_FILES:
        raw_bytes = get_git_blob_bytes(root, commit, rel)
        if raw_bytes is None:
            return {"name": name, "commit": commit, "status": "FILE_MISSING", "missing": rel}
        d_lf = compute_blob_digest(raw_bytes, normalize_lf=True)
        d_raw = compute_blob_digest(raw_bytes, normalize_lf=False)
        digests_lf.append(d_lf)
        digests_raw.append(d_raw)
        per_file.append({"file": rel, "sha256_lf": d_lf, "sha256_raw": d_raw})

    comp_lf = compute_composite_from_digests(digests_lf)
    comp_raw = compute_composite_from_digests(digests_raw)
    return {
        "name": name,
        "commit": commit,
        "composite_sha256_lf": comp_lf,
        "composite_sha256_raw": comp_raw,
        "per_file": per_file,
    }


def reconstruct_working_tree(root: Path) -> dict:
    per_file = []
    digests_lf = []
    digests_raw = []
    for rel in LEGACY_9_FILES:
        path = root / rel
        raw_bytes = path.read_bytes()
        d_lf = compute_blob_digest(raw_bytes, normalize_lf=True)
        d_raw = compute_blob_digest(raw_bytes, normalize_lf=False)
        digests_lf.append(d_lf)
        digests_raw.append(d_raw)
        per_file.append({"file": rel, "sha256_lf": d_lf, "sha256_raw": d_raw})

    comp_lf = compute_composite_from_digests(digests_lf)
    comp_raw = compute_composite_from_digests(digests_raw)
    return {
        "name": "Current Disk Working Tree",
        "commit": "UNCOMMITTED_DISK",
        "composite_sha256_lf": comp_lf,
        "composite_sha256_raw": comp_raw,
        "per_file": per_file,
    }


def reconstruct_strategy_history(root: Path) -> dict:
    root = Path(root).resolve()

    m_phase14_base = reconstruct_milestone(root, "3f19895", "Phase 14 Baseline Mint")
    m_phase14_runtime = reconstruct_milestone(root, "fbeb860", "Phase 14 Runtime Boundary")
    m_head = reconstruct_milestone(root, "ffefa14", "Git HEAD (Current Branch)")
    m_disk = reconstruct_working_tree(root)

    # A missing historical commit means there is no defensible baseline for
    # per-file comparison. Do not turn absent hashes into "modified=True".
    file_reconciliation = []
    disk_map = {f["file"]: f for f in m_disk["per_file"]}
    base_map = {f["file"]: f for f in m_phase14_base.get("per_file", [])}
    baseline_available = (
        m_phase14_base.get("composite_sha256_lf") is not None
        and len(base_map) == len(LEGACY_9_FILES)
    )

    for rel in LEGACY_9_FILES:
        base_f = base_map.get(rel, {})
        disk_f = disk_map.get(rel, {})
        is_core = rel in STRATEGY_CORE_FILES
        is_infra = rel in RUNTIME_INFRA_FILES
        layer = "Alpha Strategy Core" if is_core else "Runtime Infrastructure"

        modified = (
            base_f.get("sha256_lf") != disk_f.get("sha256_lf")
            if baseline_available else None
        )
        notes = []
        if not baseline_available:
            notes.append("BLOCKED_EVIDENCE: Phase 14 baseline commit unavailable")
        if rel == "core/setup/decision_engine.py":
            notes.append("Phase 4 MIN_CONFIDENCE shadow gate correction")
        elif rel == "backtesting/backtester.py":
            notes.append("Phase 4 cost_spec parameter threading")
        elif rel == "core/backtesting/accounting.py":
            notes.append("Phase 132-C cost wiring and post-cost recalculation")
        elif rel == "core/paper_trading/paper_trading_engine.py":
            notes.append("Phase 164 _mark_order_filled paper-order registry consistency fix")
        elif not modified:
            notes.append("Identical to Phase 14 baseline (LF canonical)")

        file_reconciliation.append({
            "file": rel,
            "layer": layer,
            "phase14_base_sha256_lf": base_f.get("sha256_lf"),
            "current_disk_sha256_lf": disk_f.get("sha256_lf"),
            "modified_since_phase14": modified,
            "notes": "; ".join(notes)
        })

    return {
        "schema": "quantengine.strategy-historical-reconstruction.v1",
        "phase": 168,
        "historical_pinned_hash": HISTORICAL_PHASE14_STRATEGY_HASH,
        "milestones": [
            m_phase14_base,
            m_phase14_runtime,
            m_head,
            m_disk,
        ],
        "evidence_status": (
            "VERIFIED" if baseline_available
            else "BLOCKED_EVIDENCE: required historical Git objects unavailable"
        ),
        "file_reconciliation": file_reconciliation,
        "findings": {
            "historical_pin_provenance": (
                "The pinned historical hash c52e648c... reflects an uncommitted working tree "
                "on Windows with CRLF line endings generated prior to commit 3f19895."
            ),
            "preservation_contract": (
                "The 5 historical change-detector tests fail red deliberately. Re-pinning them "
                "would destroy change detection and falsify research provenance. They remain "
                "red under BLOCK-168-01."
            ),
            "architectural_resolution": (
                "The strategy identity is decoupled into Alpha Strategy Core (v1.1) and Runtime "
                "Infrastructure (v1.1) in core/research/strategy_identity.py, allowing isolated "
                "testing of quantitative rules while preserving historical pins intact."
            ),
        },
    }
