"""Privacy scan for the release tree (Phase 158; Phase160 content decoding).

The secret scanner (``scripts/security/scan_secrets.py``) answers *"are there
credentials here?"*.  It does not answer *"are there account identifiers or
private venue payloads here?"*, and the Phase158 audit found that the release
ships raw private captures that carry the operator's account id and venue order
ids inside the evidence of record.  This scanner draws that line explicitly.

Phase160 note: every content rule now reads members whose encoding is decided
by their *bytes*, not by a suffix allowlist (``scripts/security/text_decode.py``):
UTF-8 with an optional BOM, UTF-16 LE/BE with or without a BOM, UTF-32 with a
BOM.  This closes the scanner-model boundary the Phase159 vendor-audit handoff
declared (UTF-16 members, and members outside the old suffix set, were invisible
to every content rule).  Binary members are not "unscanned": rule E below
requires every one of them to match an explicitly declared opaque class or the
scan fails.

Rules
-----
A. **Account identifier confinement.**  The account identifier value may appear
   only inside the enumerated raw restricted captures.  Anywhere else -- source,
   report, fixture or aggregate artifact -- is a violation.  The value itself is
   assembled at run time rather than written literally here, so this module's own
   source is not a carrier of it.
B. **Raw order ids stay raw.**  Numeric venue order ids found in the raw captures
   are classified against the input archive's inventory
   (``reports/PHASE158_INPUT_INVENTORY.sha256``):

   * *new leakage* -- the id appears in an aggregate artifact that is **not**
     byte-identical to its input-archive member (or is new in this phase).  This
     fails the scan.  It is the machine check behind "raw restricted, reports
     aggregate-only" for everything this phase writes.
   * *historical baseline* -- the id appears in an aggregate artifact that is
     byte-identical to the input archive's member.  Those are sealed historical
     records (experiment journals that quote the order they document) and are
     **reported, not rewritten**: Phase158 does not edit sealed evidence, and a
     distributable would have to sanitise them, which is exactly why this tree is
     a restricted evidence package rather than a distribution.

C. **No credential material.**  Delegated to the value-redacting secret scanner.
D. **No secret-bearing paths.**  No ``.env``/``.pem``/``.key``/``.secret`` file
   may be present in the packaged tree.
E. **Content coverage.**  Every member is either content-inspected (its bytes
   decode as text) or a member of a declared opaque class
   (``DECLARED_OPAQUE_PATTERNS``).  A binary member outside every declared
   class is a violation: it must be declared deliberately rather than left
   silently uninspected.

Like the secret scanner, this module reports only rule, path, line and a
non-revealing detail string.  It never prints a matched value.
"""

from __future__ import annotations

import argparse
import dataclasses
import fnmatch
import hashlib
import json
import pathlib
import re
import sys

try:  # imported as ``scripts.security.scan_privacy`` (namespace package)
    from scripts.security.text_decode import read_text_file  # type: ignore
except ImportError:  # direct execution or spec_from_file_location loading
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    from text_decode import read_text_file  # type: ignore


# ---------------------------------------------------------------- rule data
#: Assembled rather than written as a literal: a rule parameter that appears in
#: this file's bytes would itself be a carrier, and rule A could then never pass.
ACCOUNT_IDENTIFIER_VALUE = "".join(("812", "32", "122"))

#: The raw restricted captures that ARE the private evidence of record.  These
#: files are expected to carry the account identifier; every other file is not.
RESTRICTED_EVIDENCE_PATHS = {
    "research/captures/phase146_recon/private_ws_archive.json":
        "archived private websocket frames for the Phase146 reconciled experiment",
    "research/captures/phase146_recon/private_ws_frames.json":
        "private websocket fill frames (v2/user_trades) for Phase146",
    "research/captures/phase147_ledger/wallet_100.json":
        "raw wallet ledger pull backing the Phase147 fee/commission totals",
    "research/captures/phase152_recon2/private_ws_archive.json":
        "archived private websocket frames for the Phase152 reconciled experiment",
    "research/captures/phase152_recon2/private_ws_frames.json":
        "private websocket fill frames (v2/user_trades) for Phase152",
    "research/captures/phase153_ledger/wallet_100.json":
        "raw wallet ledger pull backing the Phase153 fee/commission totals",
    "research/captures/phase162_recon/private_ws_archive.json":
        "archived private websocket frames for the Phase162 reconciled experiment",
    "research/captures/phase162_recon/private_ws_frames.json":
        "private websocket fill frames (v2/user_trades) for Phase162",
    "research/captures/phase167_recon/private_ws_archive.json":
        "archived private websocket frames for the Phase167 reconciled experiment",
    "research/captures/phase167_recon/private_ws_frames.json":
        "private websocket fill frames (v2/user_trades) for Phase167",
    "research/captures/phase168_ledger/balances.json":
        "authoritative wallet balances backing the Phase168 equity reconciliation",
    "research/captures/phase168_ledger/wallet_100.json":
        "authoritative wallet ledger pull backing the Phase168 fee, cashflow, and balance reconciliation",
}

RAW_CAPTURE_ROOT = "research/captures/"
AGGREGATE_ROOTS = ("reports/", "docs/", "research/results/")
INPUT_INVENTORY = "reports/PHASE158_INPUT_INVENTORY.sha256"

SKIP_PARTS = {"__pycache__", ".pytest_cache", ".venv", "venv", ".git", "logs",
              "_phase154_extract", ".kilo"}

#: Binary members are accepted only inside an explicitly declared opaque class
#: (rule E).  These classes are containers whose bytes stay integrity-covered
#: by BUILD_MANIFEST.sha256: the ten retained acquisition archives and the one
#: acquisition parquet.  Anything binary outside them fails the scan, so a new
#: opaque artifact cannot ride along unread by accident.
DECLARED_OPAQUE_PATTERNS = ("*.zip", "*.parquet")

SECRET_PATH_NAMES = {".env", ".env.test", ".env.local"}
SECRET_PATH_SUFFIXES = {".pem", ".key", ".secret"}

_ORDER_ID = re.compile(r'"(?:order_id|client_order_id)"\s*:\s*"?(\d{6,})')
_ACCOUNT_KEY = re.compile(r'"(?:user_id|account_id)"\s*:\s*(\d{4,})')


@dataclasses.dataclass(frozen=True)
class Violation:
    rule: str
    path: str
    line: int
    detail: str


def _relative(root: pathlib.Path, path: pathlib.Path) -> str:
    return path.relative_to(root).as_posix()


def _iter_members(root: pathlib.Path):
    """Every regular member outside the skipped parts, in sorted order."""
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part in SKIP_PARTS for part in rel.parts):
            continue
        yield path


def _iter_text_files(root: pathlib.Path):
    """Members whose bytes decode as text (Phase160: decided by content).

    Yields ``(path, text)``; a member whose bytes are binary is not yielded
    and is classified by the content-coverage rule instead (rule E), never
    left silently uninspected.  Decoding handles UTF-8 with an optional BOM,
    UTF-16 LE/BE with or without a BOM, and UTF-32 with a BOM
    (``scripts/security/text_decode.py``).
    """
    for path in _iter_members(root):
        decoded = read_text_file(path)
        if decoded is None or decoded.binary:
            continue
        yield path, decoded.text


def scan_account_identifier(root: pathlib.Path,
                            allowlist: dict[str, str] | None = None) -> tuple[list[Violation], list[str]]:
    """Rule A. Returns (violations, files that carry the identifier)."""
    allowlist = RESTRICTED_EVIDENCE_PATHS if allowlist is None else allowlist
    violations: list[Violation] = []
    carriers: list[str] = []
    for path, text in _iter_text_files(root):
        rel = _relative(root, path)
        matched_line = 0
        for number, line in enumerate(text.splitlines(), start=1):
            if ACCOUNT_IDENTIFIER_VALUE in line:
                matched_line = number
                break
        if not matched_line:
            continue
        carriers.append(rel)
        if rel not in allowlist:
            violations.append(Violation(
                "account_identifier_outside_restricted_capture", rel, matched_line,
                "the account identifier appears outside the enumerated raw "
                "restricted captures"))
    return violations, carriers


def capture_order_ids(root: pathlib.Path) -> dict[str, str]:
    """Numeric venue order ids found in the raw captures: value -> first path."""
    found: dict[str, str] = {}
    capture_root = root / RAW_CAPTURE_ROOT
    if not capture_root.exists():  # pragma: no cover
        return found
    for path, text in _iter_text_files(capture_root):
        rel = _relative(root, path)
        for line in text.splitlines():
            for value in _ORDER_ID.findall(line):
                found.setdefault(value, rel)
    return found


def scan_order_id_leakage(root: pathlib.Path, ids: dict[str, str]) -> list[Violation]:
    """Rule B detector. Aggregate artifacts that carry raw venue order ids."""
    if not ids:
        return []
    violations: list[Violation] = []
    for prefix in AGGREGATE_ROOTS:
        base = root / prefix
        if not base.exists():
            continue
        for path, text in _iter_text_files(base):
            rel = _relative(root, path)
            for number, line in enumerate(text.splitlines(), start=1):
                leaked = [value for value in ids if value in line]
                if leaked:
                    violations.append(Violation(
                        "raw_order_id_in_aggregate_artifact", rel, number,
                        "an aggregate artifact carries a raw venue order id "
                        "(%d id(s) on this line)" % len(leaked)))
    return violations


def load_input_inventory(root: pathlib.Path) -> dict[str, str]:
    """rel path -> sha256 of the input archive's members (Phase158 inventory)."""
    path = root / INPUT_INVENTORY
    inventory: dict[str, str] = {}
    if not path.exists():
        return inventory
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        digest, rel = parts
        rel = rel.strip().lstrip("*").strip()
        if len(digest) == 64:
            inventory[rel] = digest
    return inventory


def classify_leakage(root: pathlib.Path, violations: list[Violation],
                     inventory: dict[str, str] | None = None
                     ) -> tuple[list[Violation], list[Violation]]:
    """Split rule-B findings into (new leakage, historical baseline).

    A finding is historical only when the file is byte-identical to the input
    archive's member of the same path.  A modified or newly written file is new
    leakage, whatever its provenance story.
    """
    inventory = load_input_inventory(root) if inventory is None else inventory
    new: list[Violation] = []
    historical: list[Violation] = []
    for violation in violations:
        path = root / violation.path
        recorded = inventory.get(violation.path)
        if recorded and path.exists():
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual == recorded:
                historical.append(violation)
                continue
        new.append(violation)
    return new, historical


def scan_secret_material(root: pathlib.Path) -> tuple[list[Violation], list[str], list[str]]:
    """Rule C. Delegates to the value-redacting secret scanner.

    Phase193B: the hard-coded ``.env`` exemption is closed.  Findings on
    operator-local runtime configuration (the root ``.env``; the same
    packaged-out set ``scripts/generate_manifest.py`` applies) are returned in
    the third element instead, so a worktree verdict can still state that a
    local credential file exists while the *packaged-tree* claim set stays
    precise.  Nothing is silently invisible: the caller must surface the
    operator-local list.
    """
    try:
        from scripts.security import scan_secrets  # type: ignore
    except ImportError:
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
        import scan_secrets  # type: ignore
    scoped, local = scan_secrets.scan_worktree_with_local_policy(root)
    violations = [Violation("credential_material", f.path, f.line, "rule=%s" % f.rule)
                  for f in scoped]
    rules = [f.rule for f in scoped]
    local_paths = sorted({f.path for f in local})
    return violations, rules, local_paths


def scan_secret_paths(root: pathlib.Path) -> tuple[list[Violation], list[str]]:
    """Rule D. No secret-bearing paths in the packaged tree.

    Phase193B: the root ``.env`` skip is replaced by the shared operator-local
    policy; an operator-local ``.env`` is reported in the second element (it is
    excluded from release packaging by policy) while every other secret-bearing
    path -- including any nested ``.env.*`` -- remains a hard violation.
    """
    try:
        from scripts.security import scan_secrets as _scan_secrets  # type: ignore
    except ImportError:
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
        import scan_secrets as _scan_secrets  # type: ignore
    local = _scan_secrets.operator_local_files(root)
    violations: list[Violation] = []
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if any(part in SKIP_PARTS for part in rel.parts):
            continue
        if not path.is_file():
            continue
        if rel.as_posix() in local:
            continue
        if path.name in SECRET_PATH_NAMES or path.suffix.lower() in SECRET_PATH_SUFFIXES:
            violations.append(Violation(
                "secret_bearing_path", _relative(root, path), 0,
                "a credential-bearing file must not be present in the release tree"))
    return violations, sorted(local)


def scan_content_coverage(root: pathlib.Path
                          ) -> tuple[int, list[str], list[Violation]]:
    """Rule E. Every member is content-inspected or a declared opaque class.

    Returns ``(inspected, declared_opaque, undeclared_violations)``.  The
    split is decided by each member's *bytes* through the shared decoder, so
    it no longer depends on a filename allowlist: a member that decodes as
    text is content-inspected whatever its suffix, and a binary member must
    match a declared opaque pattern.  A binary member outside every declared
    class fails the scan -- it must be declared deliberately rather than left
    silently uninspected.
    """
    inspected = 0
    declared: list[str] = []
    undeclared: list[Violation] = []
    for path in _iter_members(root):
        rel = _relative(root, path)
        decoded = read_text_file(path)
        if decoded is None:  # pragma: no cover - unreadable member
            continue
        if not decoded.binary:
            inspected += 1
            continue
        if any(fnmatch.fnmatch(rel, pattern)
               for pattern in DECLARED_OPAQUE_PATTERNS):
            declared.append(rel)
            continue
        undeclared.append(Violation(
            "opaque_member_not_declared", rel, 0,
            "a binary member matches no declared opaque class (%s); declare "
            "it deliberately or make it text"
            % ", ".join(DECLARED_OPAQUE_PATTERNS)))
    return inspected, sorted(declared), undeclared


def run(root: pathlib.Path) -> dict:
    """Full privacy scan; the verdict is scoped to a restricted package.

    ``PRIVACY_SCAN_PASS`` states that the confinement rules hold inside this
    restricted evidence package.  It is never a publication clearance: the
    sealed historical records ship raw venue order ids by design and would
    have to be sanitised for a wider distribution.  The report says so
    explicitly (``publication_clearance``), so a green verdict cannot be read
    as permission to redistribute.
    """
    account_violations, carriers = scan_account_identifier(root)
    ids = capture_order_ids(root)
    leakage = scan_order_id_leakage(root, ids)
    new_leakage, historical_leakage = classify_leakage(root, leakage)
    secret_violations, secret_rules, operator_local = scan_secret_material(root)
    path_violations, path_operator_local = scan_secret_paths(root)
    inspected, declared_opaque, coverage_violations = scan_content_coverage(root)
    violations = (account_violations + new_leakage + secret_violations
                  + path_violations + coverage_violations)
    return {
        "schema": "quantengine.privacy-scan.v2",
        "root": str(root),
        "operator_local_files_present": sorted(
            set(operator_local) | set(path_operator_local)),
        "restricted_evidence_allowlist": RESTRICTED_EVIDENCE_PATHS,
        "account_identifier_carriers": sorted(carriers),
        "allowlist_is_exhaustive": sorted(carriers) == sorted(RESTRICTED_EVIDENCE_PATHS),
        "raw_order_ids_found": len(ids),
        "raw_order_id_new_leakage": [dataclasses.asdict(v) for v in new_leakage],
        "raw_order_id_historical_baseline": sorted(
            {v.path for v in historical_leakage}),
        "raw_order_id_historical_findings": len(historical_leakage),
        "content_coverage": {
            "content_inspected_members": inspected,
            "declared_opaque": declared_opaque,
            "declared_opaque_patterns": list(DECLARED_OPAQUE_PATTERNS),
            "decoding": ("content-based (scripts/security/text_decode.py): "
                         "UTF-8 with optional BOM, UTF-16 LE/BE with or "
                         "without BOM, UTF-32 BOM; anything else is binary"),
        },
        "secret_rules_triggered": sorted(set(secret_rules)),
        "violations": [dataclasses.asdict(v) for v in violations],
        "publication_clearance": "NOT_CLEARED",
        "publication_clearance_reason": (
            "restricted evidence package: the sealed historical records it "
            "ships by design enumerate raw venue order ids, so the package is "
            "not sanitised for redistribution. PRIVACY_SCAN_PASS states that "
            "the confinement rules hold inside the restricted package; it is "
            "never a publication clearance."),
        "verdict": "PRIVACY_SCAN_PASS" if (
            not violations and sorted(carriers) == sorted(RESTRICTED_EVIDENCE_PATHS)
        ) else "PRIVACY_SCAN_FAIL",
    }


def _emit(report: dict) -> None:
    for path in report["raw_order_id_historical_baseline"]:
        print("PRIVACY_SCAN_NOTE historical_raw_order_id path=%s "
              "(byte-identical to its input-archive member; sealed record, not "
              "rewritten by this phase)" % path)
    coverage = report["content_coverage"]
    for path in coverage["declared_opaque"]:
        print("PRIVACY_SCAN_NOTE declared_opaque path=%s (binary member of a "
              "declared opaque class; integrity-covered by "
              "BUILD_MANIFEST.sha256)" % path)
    print("PRIVACY_SCAN_COVERAGE inspected=%d declared_opaque=%d patterns=%s"
          % (coverage["content_inspected_members"],
             len(coverage["declared_opaque"]),
             ",".join(coverage["declared_opaque_patterns"])))
    for violation in report["violations"]:
        print("PRIVACY_SCAN_FAIL path=%s line=%s rule=%s detail=%s"
              % (violation["path"], violation["line"], violation["rule"],
                 violation["detail"]))
    print("PRIVACY_SCAN_CLEARANCE %s (restricted evidence package; not sanitised "
          "for redistribution -- PRIVACY_SCAN_PASS is not a publication "
          "clearance)" % report["publication_clearance"])
    print(report["verdict"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path,
                        default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--json", type=pathlib.Path, default=None)
    args = parser.parse_args(argv)
    report = run(args.root.resolve())
    if args.json:
        args.json.write_text(json.dumps(report, indent=1, sort_keys=True),
                             encoding="utf-8")
    _emit(report)
    return 0 if report["verdict"] == "PRIVACY_SCAN_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
