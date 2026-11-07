"""Deterministic release-manifest generation and verification (Phase 154).

Contract: the manifest covers EVERY regular file in the release tree
EXCEPT itself (self-referential hashes are undefined: the manifest cannot
contain its own hash). The final archive SHA-256 is recorded separately
in a detached release record, never inside the hashed set.

Exclusions (explicit, narrow):
  * BUILD_MANIFEST.sha256 (self)
  * __pycache__, *.pyc/*.pyo, .pytest_cache, .venv/venv, .git, logs
  * .env, .env.*, env/.env.py and other credential-bearing paths
  * QuantEngine_*.zip (prior build artifacts, not source; research
    evidence ZIPs under research/ ARE covered)
  * _phase154_extract/ (forensic working copy, not source)

Output is always UTF-8 with "\n" line endings, on the file and on stdout, on
every platform: the manifest's bytes must equal a fresh generation
byte-for-byte for any recipient to reproduce them.  (A text-mode write used to
translate newlines on Windows, so the shipped bytes differed from an LF
generation elsewhere -- the Phase158 post-audit repair found and removed that.)

Usage:
  python scripts/generate_manifest.py --root <tree> [--write BUILD_MANIFEST.sha256]
  python scripts/generate_manifest.py --root <tree> --verify
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

MANIFEST_NAME = "BUILD_MANIFEST.sha256"
_HEX64 = re.compile(r"[0-9a-f]{64}")
_SKIP_ROOT_PROMPT = re.compile(r"phase\d+_prompt(_dump)?\.txt\Z", re.IGNORECASE)
SKIP_PARTS = {"__pycache__", ".pytest_cache", ".venv", "venv", ".git", "logs",
              "_phase154_extract", "EVIDENCE", "REFERENCE", "SCRIPTS_AUDIT_ROUND2",
              "SCRIPTS_PHASE161", "SEALED_TREE_KEY_FILES", "QuantEngine_PHASE161_POST_BUILD",
              "QuantEngine_PHASE162_POST_BUILD", ".kilo"}
SKIP_SUFFIXES = {".pyc", ".pyo"}
SECRET_NAMES = {".env", ".env.test", ".env.local"}
SKIP_ROOT_NAMES = {"HANDOVER.md", "MANIFEST_OF_HANDOVER.txt"}
# Phase193B policy: root-level operator prompt dumps (``phase192_prompt.txt``,
# ``phase192_prompt_dump.txt``) are operator session artifacts, exactly the
# HANDOVER.md class: they stay on disk for the operator, but they are not
# release source and are excluded from manifest coverage (files under
# ``docs/CLAUDE_*INDEPENDENT_AUDIT_PROMPT.md`` remain the covered canonicals).
# Phase193B: the prohibition is a *rule*, not a name list.  Any credential-
# bearing file must be refused by packaging regardless of where it lives or
# what it is named; only the placeholders template (``.env.example``) and a
# constructor-provisioned env module are allowed to carry env syntax.
PROHIBITED_NAME_BASES = {".env", ".env.local", ".env.test", ".env.prod",
                         ".env.backup", ".env.private", "credentials"}
PROHIBITED_SUFFIXES = {".pem", ".key", ".secret", ".secrets", ".p12",
                       ".pfx", ".keystore"}
ALLOWED_SECRET_NAMES = {".env.example"}


def package_files(root: Path):
    out = []
    for path in root.rglob("*"):
        rel = path.relative_to(root)
        if any(part in SKIP_PARTS for part in rel.parts):
            continue
        if len(rel.parts) == 1 and (rel.name in SKIP_ROOT_NAMES
                                    or rel.name.startswith("RELEASE_HASH_")
                                    or _SKIP_ROOT_PROMPT.fullmatch(rel.name)):
            continue
        if path.is_dir():
            continue
        if path.suffix.lower() in SKIP_SUFFIXES:
            continue
        # Phase193B: exclusion from coverage follows the full secret-bearing
        # name/suffix rule; the manifest never covers one of these files.
        if is_secret_bearing_name(rel.as_posix()):
            continue
        if path.name == MANIFEST_NAME and len(rel.parts) == 1:
            continue  # self-hash exclusion (documented above)
        if rel.as_posix() == "env/.env.py":
            continue
        if path.name.startswith("QuantEngine_") and path.suffix.lower() == ".zip":
            continue  # build artifacts of prior candidates, not source
        out.append(rel.as_posix())
    return sorted(out)


def is_secret_bearing_name(rel: str) -> bool:
    """True when *rel* names a file that must never ship in a release tree.

    Phase193B: suffix/name based, case-insensitive, applicable to any depth.
    ``secret.key.txt`` is not confused with a key (only true suffixes match);
    ``server.key`` and ``api.secrets`` (case-insensitive forms of the suffix
    set) are refused.
    """
    path = Path(rel)
    name = path.name.lower()
    if path.suffix.lower() in PROHIBITED_SUFFIXES:
        return True
    if name in {n.lower() for n in PROHIBITED_NAME_BASES}:
        return True
    if name.startswith(".env"):
        return name not in {n.lower() for n in ALLOWED_SECRET_NAMES}
    if "credentials" in name and name.endswith(
            tuple(PROHIBITED_SUFFIXES | {".json", ".txt"})):
        return True
    return False


def prohibited_members(root: Path) -> list[str]:
    """Secret-bearing files present in *root* that must never be packaged."""
    bad = []
    for path in root.rglob("*"):
        if any(part in SKIP_PARTS for part in path.relative_to(root).parts):
            continue
        if len(path.relative_to(root).parts) == 1 and (
                path.name in SKIP_ROOT_NAMES
                or path.name.startswith("RELEASE_HASH_")
                or _SKIP_ROOT_PROMPT.fullmatch(path.name)):
            continue
        if path.is_dir():
            continue
        rel = path.relative_to(root).as_posix()
        if is_secret_bearing_name(rel):
            bad.append(rel)
    return sorted(bad)


def digest(root: Path, rel: str) -> str:
    return hashlib.sha256((root / rel).read_bytes()).hexdigest()


def generate(root: Path) -> str:
    lines = ["%s  %s" % (digest(root, rel), rel) for rel in package_files(root)]
    return "".join(line + "\n" for line in lines)


def verify(root: Path, manifest_path: Path, strict: bool = False) -> list[str]:
    """Report every way the manifest and the tree disagree.

    Phase158 hardening: a duplicate path used to silently overwrite its
    earlier entry in ``expected`` (so a corrupt manifest could still verify),
    and a malformed line raised ``ValueError`` instead of being reported as a
    problem.  Both are now explicit problems, so the verifier can never
    silently accept a manifest it did not actually check.

    Phase159 hardening (r2 self-audit observation): a file listed by the
    manifest but absent from disk used to be reported with the inverted label
    ``manifest-extra:``.  It is now reported as ``missing:``, which states
    exactly what happened; the name ``uncovered:`` keeps meaning "present on
    disk but not covered by the manifest".  Detection is unchanged.
    """
    expected: dict[str, str] = {}
    problems: list[str] = []
    for number, line in enumerate(
            manifest_path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) != 2 or not _HEX64.fullmatch(parts[0]):
            problems.append("malformed:line%d" % number)
            continue
        h, p = parts
        rel = p.strip()
        if rel in expected:
            problems.append("duplicate:" + rel)
            continue
        expected[rel] = h
    actual = set(package_files(root))
    if set(expected) != actual:
        for rel in sorted(set(expected) - actual):
            problems.append("missing:" + rel)
        for rel in sorted(actual - set(expected)):
            problems.append("uncovered:" + rel)
    for rel, h in sorted(expected.items()):
        fp = root / rel
        if fp.exists() and digest(root, rel) != h:
            problems.append("mismatch:" + rel)
    # Phase193B: strict verification is for release trees -- any credential-
    # bearing member (``.env``, ``*.pem``, ``*.key``, ...) present in the tree
    # is a refusal, not merely an omission from coverage.
    if strict:
        for rel in prohibited_members(root):
            problems.append("prohibited:" + rel)
    return problems


def _write_buffer_robust(buffer, blob: bytes) -> None:
    """Robustly write all bytes to buffer, handling partial writes and BlockingIOError."""
    view = memoryview(blob)
    total_written = 0
    total_len = len(blob)
    while total_written < total_len:
        try:
            # Chunking to 64KB prevents OS pipe buffer saturation and BlockingIOError
            chunk = view[total_written:total_written + 65536]
            written = buffer.write(chunk)
            if written is None:
                import time
                time.sleep(0.001)
                continue
            total_written += written
        except BlockingIOError:
            import time
            time.sleep(0.005)
            continue
    buffer.flush()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--write", type=str, default=None)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--strict", action="store_true",
                        help="verify: refuse any credential-bearing member in the tree")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    bad = prohibited_members(root)
    if bad and args.strict and not args.verify:
        for rel in bad:
            print("PROHIBITED_REFUSE:" + rel)
        print("MANIFEST_FAIL (release tree refuses credential-bearing members)")
        return 1
    if bad and not args.strict:
        for rel in bad:
            # Phase193B: the non-fatal exclusion notice goes to stderr --
            # stdout carries the byte-identical manifest stream, and a
            # worktree that contains the operator's .env must still be
            # able to reproduce `generate > file` byte for byte.
            print("PROHIBITED_EXCLUDED_FROM_COVERAGE:" + rel,
                  file=sys.stderr)
    if args.verify:
        problems = verify(root, root / MANIFEST_NAME, strict=args.strict)
        for item in problems:
            print(item)
        print("MANIFEST_%s (%d problems)" % ("PASS" if not problems else "FAIL", len(problems)))
        return 0 if not problems else 1
    text = generate(root)
    if args.write:
        # newline="\n" is deliberate: the file's bytes must equal a fresh
        # generation on every platform.  A text-mode write translated "\n" to
        # CRLF on Windows, so a byte-for-byte regeneration on a platform with
        # LF conventions disagreed with the shipped bytes (the audit's F-03).
        (root / args.write).write_text(text, encoding="utf-8", newline="\n")
        print("wrote %s (%d entries)" % (args.write, text.count("\n")))
    else:
        # Write UTF-8 bytes, not text: text-mode stdout would translate "\n"
        # to CRLF on Windows and break `generate > file` byte reproduction.
        blob = text.encode("utf-8")
        buffer = getattr(sys.stdout, "buffer", None)
        if buffer is not None:
            _write_buffer_robust(buffer, blob)
        else:  # pragma: no cover - exotic stdout replacements
            sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
