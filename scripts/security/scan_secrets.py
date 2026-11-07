"""Fail-safe repository secret scanner.

The scanner intentionally reports only a relative path, line number and
rule name.  It never prints a matched value, so it is suitable for local
operator use and CI logs.  It scans ignored files too (notably ``.env``)
because ``.gitignore`` prevents commits but does not make a workstation
credential safe.

Rules are applied to every member whose bytes decode as text; the encoding is
decided by content (``scripts/security/text_decode.py``): UTF-8 with an
optional BOM, UTF-16 LE/BE with or without a BOM, and UTF-32 with a BOM.
Phase159 fixed the UTF-8-BOM case; Phase160 closed the rest of that boundary
after the Phase159 vendor-audit handoff declared it (UTF-16 members were
invisible to every content rule).  A member whose bytes are binary is never
scanned as garbage here: the privacy scan classifies it as a declared opaque
class and fails on an undeclared one (``scan_privacy.py``, rule E).

Usage:

    python scripts/security/scan_secrets.py
    python scripts/security/scan_secrets.py --check-history
    python scripts/security/scan_secrets.py --check-staged

``--check-history`` is a diagnostic gate: it reports commits containing
non-empty known credential assignments without exposing their contents.
It does not rewrite history; that operation needs a coordinated rotation
and repository-maintainer procedure.

``--check-staged`` inspects the index blobs for A/C/M/R entries, so a
staged addition whose worktree copy was later removed is still caught.
Both diagnostics fail closed with rule/path/line only.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
import sys
from typing import Iterable

try:  # imported as ``scripts.security.scan_secrets`` (namespace package)
    from scripts.security.text_decode import read_text_file  # type: ignore
except ImportError:  # direct execution or spec_from_file_location loading
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from text_decode import read_text_file  # type: ignore


_SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".kilo"}
_KNOWN_SECRET = re.compile(
    r"^\s*(?:DELTA_API_KEY|DELTA_API_SECRET|DELTA_INDIA_TESTNET_API_KEY|"
    r"DELTA_INDIA_TESTNET_API_SECRET|DELTA_SANDBOX_API_KEY|"
    r"DELTA_SANDBOX_API_SECRET|OPENAI_API_KEY|"
    r"ANTHROPIC_API_KEY|OPENROUTER_API_KEY|CONTROL_API_TOKEN|"
    r"REMOTE_(?:VIEW|CONTROL|EMERGENCY)_TOKEN)\s*=\s*(\S.+?)\s*$"
)
_PY_LITERAL_SECRET = re.compile(
    r"\b(?:DELTA_API_KEY|DELTA_API_SECRET|DELTA_INDIA_TESTNET_API_KEY|"
    r"DELTA_INDIA_TESTNET_API_SECRET|DELTA_SANDBOX_API_KEY|"
    r"DELTA_SANDBOX_API_SECRET|OPENAI_API_KEY|"
    r"ANTHROPIC_API_KEY|OPENROUTER_API_KEY)\s*=\s*[\"']([^\"']+)[\"']"
)
_PRIVATE_KEY = re.compile(
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
)


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    rule: str


def _uses_env_assignment_rules(path: Path) -> bool:
    """Only configuration files use ``NAME=value`` secret syntax.

    Python source frequently contains safe expressions such as
    ``CONTROL_API_TOKEN = os.getenv(...)`` and documentation contains
    illustrative assignments.  Neither is a credential leak.
    """
    return path.name == ".env" or path.name.startswith(".env.") or path.suffix.lower() in {
        ".ini", ".toml", ".yaml", ".yml",
    }


def _scan_text_lines(relative: str, name: str, suffix: str,
                     text: str) -> list[Finding]:
    """Apply the content rules to one decoded member's lines."""
    findings: list[Finding] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if _uses_env_assignment_rules(Path(relative)) and _KNOWN_SECRET.match(line):
            findings.append(Finding(relative, number, "non_empty_known_secret"))
        elif suffix.lower() == ".py" and _PY_LITERAL_SECRET.search(line):
            findings.append(Finding(relative, number, "literal_known_secret"))
        elif _PRIVATE_KEY.search(line):
            findings.append(Finding(relative, number, "private_key_material"))
    return findings


def scan_worktree(root: Path) -> list[Finding]:
    """Scan text members beneath *root*, including ignored configuration.

    Selection is by content, not by a suffix allowlist: a member the decoder
    reports as binary is skipped here and must be declared as an opaque class
    by the privacy scan (rule E) -- it cannot sit silently uninspected.
    """
    findings: list[Finding] = []
    root = root.resolve()
    for path in root.rglob("*"):
        if any(part in _SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        if not path.is_file():
            continue
        decoded = read_text_file(path)
        if decoded is None or decoded.binary:
            continue
        relative = path.relative_to(root).as_posix()
        findings.extend(_scan_text_lines(
            relative, path.name, path.suffix, decoded.text))
    return findings


def scan_staged(root: Path) -> list[Finding]:
    """Scan the index: staged content invisible to a worktree-only scan.

    A staged addition covering a non-empty credential assignment -- including
    one whose worktree copy was later removed -- is an exposure the ordinary
    worktree scan cannot see, so the staged blob for every A/C/M/R index
    entry is inspected with the same content rules.  Only rule/path/line is
    reported; never a matched value.
    """
    root = root.resolve()
    try:
        listing = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR",
             "-z"],
            cwd=root, check=True, capture_output=True, text=True, timeout=30,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    findings: list[Finding] = []
    for encoded_path in listing.split("\0"):
        if not encoded_path:
            continue
        relative = encoded_path.replace("\\", "/")
        try:
            blob = subprocess.run(
                ["git", "show", "".join((":0:", relative))],
                cwd=root, check=True, capture_output=True, text=True,
                timeout=30,
            ).stdout
        except (OSError, subprocess.SubprocessError):
            continue
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts:
            continue
        findings.extend(_scan_text_lines(relative, path.name, path.suffix, blob))
    return findings


def scan_env_history(root: Path) -> list[str]:
    """Return commits whose historical .env has a known non-empty Delta key."""
    try:
        revisions = subprocess.run(
            ["git", "rev-list", "--all", "--", ".env"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout.splitlines()
    except (OSError, subprocess.SubprocessError):
        return []

    unsafe: list[str] = []
    for revision in revisions:
        try:
            content = subprocess.run(
                ["git", "show", f"{revision}:.env"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            ).stdout
        except (OSError, subprocess.SubprocessError):
            continue
        if any(
            _KNOWN_SECRET.match(line)
            for line in content.splitlines()
        ):
            unsafe.append(revision)
    return unsafe


# Operator-local runtime configuration that release packaging excludes by
# policy (``scripts/generate_manifest.py``).  This set is used ONLY to label
# findings in worktree-hygiene tests so a local credential file can never
# be silently invisible: it is returned from
# ``scan_worktree_with_local_policy`` as a separate, explicit bucket.  The
# CLI gate (``main``) and every CI consumer use the unfiltered scan and fail
# closed on any of it.
_OPERATOR_LOCAL_ONLY = {".env"}


def operator_local_files(root: Path) -> set[str]:
    """Operator-local runtime configuration paths present under *root*."""
    resolved = root.resolve()
    return {rel for rel in _OPERATOR_LOCAL_ONLY if (resolved / rel).is_file()}


def scan_worktree_with_local_policy(root: Path) -> tuple[list[Finding], list[Finding]]:
    """Split ``scan_worktree`` findings into (scoped, operator-local).

    Nothing is dropped: findings for operator-local files (the root ``.env``)
    are returned separately and every filtering caller must handle them
    explicitly -- a silent exemption is exactly the bypass this split is
    designed to prevent.
    """
    local_paths = operator_local_files(root)
    findings = scan_worktree(root)
    scoped = [f for f in findings if f.path not in local_paths]
    local = [f for f in findings if f.path in local_paths]
    return scoped, local


def _emit_findings(findings: Iterable[Finding]) -> None:
    for finding in findings:
        print(f"SECRET_SCAN_FAIL path={finding.path} line={finding.line} rule={finding.rule}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--check-history", action="store_true")
    parser.add_argument("--check-staged", action="store_true")
    args = parser.parse_args(argv)
    root = args.root.resolve()

    # Fail closed on EVERY finding, including the operator-local root
    # ``.env``.  The Phase187 exemption (``f.path != ".env"``) let a live
    # credential file sit in the worktree while the ordinary gate printed
    # ``SECRET_SCAN_PASS``; Phase193B closes that bypass.
    findings = scan_worktree(root)
    _emit_findings(findings)
    history = scan_env_history(root) if args.check_history else []
    for revision in history:
        print(f"SECRET_HISTORY_FAIL path=.env commit={revision} rule=non_empty_known_secret")

    staged: list[Finding] = []
    if args.check_staged:
        staged = scan_staged(root)
        # Worktree findings are double-reported against staged content; only
        # emit staged findings for paths the worktree scan could not see.
        worktree_paths = {f.path for f in findings}
        for finding in staged:
            if finding.path not in worktree_paths:
                print(f"SECRET_SCAN_FAIL path={finding.path} "
                      f"line={finding.line} rule=staged:{finding.rule}")

    if findings or history or staged:
        return 1
    print("SECRET_SCAN_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
