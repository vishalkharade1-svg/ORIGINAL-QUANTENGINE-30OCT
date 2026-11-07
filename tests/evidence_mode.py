"""Evidence-mode contract for Git-dependent facts (Phase 158).

A source archive carries no ``.git`` directory, so facts about branch names,
commit ancestry, tracked-file state and ``git grep`` results cannot be
established from it.  Two failure modes are possible and this module closes
both:

* **Loud failure** -- ``git merge-base``/``git branch`` return a non-zero
  status and the test fails.  That is not a property of the code under test
  and it buries real failures in noise.
* **Silent vacuous pass** -- ``git status``/``git grep``/``git diff`` fail and
  produce *empty* output, so an assertion of the form ``assertEqual(out, "")``
  or ``assertEqual(hits, [])`` passes while verifying nothing at all.  A
  freeze-integrity check or a credential scan that silently verifies nothing
  is worse than one that fails.

Both are wrong for the same reason: a Git fact is either established against a
genuine checkout, or it is *declared blocked*.  It is never quietly assumed.

Contract
--------
* In a genuine checkout (``MODE_GIT_CHECKOUT``) ``require_git_fact`` returns
  immediately, so the test's own assertions run unchanged.  Those assertions
  are never removed or weakened by this module.
* In a source archive (``MODE_SOURCE_ARCHIVE``) it raises ``SkipTest`` carrying
  ``BLOCKED_EVIDENCE`` and the fact id.  A skip is not a pass: pytest reports
  it as skipped, and the release gate for ancestry stays blocked.

``reports/PHASE161_GIT_EVIDENCE_STATUS.json`` is the machine-readable record of
which facts were blocked, why, and in which mode.  ``tests/
test_git_evidence_mode_contract.py`` checks this module, the record, and the
gated tests against each other -- including a positive test, against a
throwaway repository created in a temporary directory, that the guard really
does step aside in a genuine checkout.  Without that positive test the guard
would be an unchecked loophole.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATUS_FILE = ROOT / "reports" / "PHASE161_GIT_EVIDENCE_STATUS.json"

MODE_GIT_CHECKOUT = "GIT_CHECKOUT"
MODE_SOURCE_ARCHIVE = "SOURCE_ARCHIVE"

STATUS_BLOCKED = "BLOCKED_EVIDENCE"
STATUS_VERIFIED = "VERIFIED"

SKIP_PREFIX = "BLOCKED_EVIDENCE"


def _git(args: list[str], cwd: Path | None = None, timeout: int = 30):
    return subprocess.run(["git", *args], capture_output=True, text=True,
                          cwd=str(cwd or ROOT), timeout=timeout)


def git_available() -> bool:
    """True when a ``git`` executable can be invoked at all."""
    try:
        probe = _git(["--version"], timeout=15)
    except (OSError, subprocess.SubprocessError):
        return False
    return probe.returncode == 0


def detect_mode(root: Path | None = None) -> tuple[str, dict]:
    """Return ``(mode, evidence)`` for ``root``.

    ``GIT_CHECKOUT`` requires a working ``git``, a work tree that answers
    ``rev-parse --is-inside-work-tree`` with ``true``, *and* a resolvable
    ``HEAD`` commit.  A ``.git`` directory alone is not enough -- an empty
    repository cannot establish ancestry either.
    """
    root = Path(root) if root is not None else ROOT
    evidence: dict = {"root": str(root), "git_dir_present": (root / ".git").exists()}
    if not git_available():
        evidence["git_executable"] = "unavailable"
        return MODE_SOURCE_ARCHIVE, evidence
    evidence["git_executable"] = "available"
    try:
        probe = _git(["rev-parse", "--is-inside-work-tree"], root)
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover
        evidence["probe_error"] = "%s: %s" % (type(exc).__name__, exc)
        return MODE_SOURCE_ARCHIVE, evidence
    evidence["rev_parse_is_inside_work_tree"] = {
        "returncode": probe.returncode,
        "stdout": probe.stdout.strip(),
        "stderr": probe.stderr.strip(),
    }
    if probe.returncode != 0 or probe.stdout.strip() != "true":
        return MODE_SOURCE_ARCHIVE, evidence
    try:
        head = _git(["rev-parse", "--verify", "HEAD"], root)
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover
        evidence["head_error"] = "%s: %s" % (type(exc).__name__, exc)
        return MODE_SOURCE_ARCHIVE, evidence
    evidence["head"] = {
        "returncode": head.returncode,
        "stdout": head.stdout.strip(),
        "stderr": head.stderr.strip(),
    }
    if head.returncode != 0:
        return MODE_SOURCE_ARCHIVE, evidence
    return MODE_GIT_CHECKOUT, evidence


def require_git_fact(case, fact_id: str, detail: str = "") -> None:
    """Enforce the contract for one Git-dependent test method.

    In a genuine checkout this returns and the caller's own assertions run.
    In a source archive this skips the test with an explicit
    ``BLOCKED_EVIDENCE`` reason naming the fact, so the fact is neither
    silently assumed nor reported as verified.
    """
    mode, evidence = detect_mode()
    if mode == MODE_GIT_CHECKOUT:
        return
    reason = (
        "%s: git fact %s cannot be established from a source archive "
        "(mode=%s; rev-parse --is-inside-work-tree returned %s). "
        "The fact is recorded as blocked, not verified, in reports/%s."
        % (SKIP_PREFIX, fact_id, mode,
           evidence.get("rev_parse_is_inside_work_tree", {}).get("returncode", "n/a"),
           STATUS_FILE.name)
    )
    if detail:
        reason += " Required: %s." % detail
    case.skipTest(reason)


def status_document() -> dict | None:
    """The packaged machine-readable record, or ``None`` when absent."""
    if not STATUS_FILE.exists():
        return None
    return json.loads(STATUS_FILE.read_text(encoding="utf-8"))
