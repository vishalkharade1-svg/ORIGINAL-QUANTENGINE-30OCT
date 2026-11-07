"""Deterministic release builder (Phase155).

Frozen ordering rule, enforced here so it cannot be got wrong by hand:

    1. regenerate BUILD_MANIFEST.sha256 over the quiesced tree
    2. verify the manifest
    3. pack the tree (manifest included; exclusions = manifest contract)
    4. assert member coverage: members == manifest paths + the manifest
    5. print the final SHA-256 (to be recorded in a DETACHED record only)

An archive cannot contain a truthful hash of itself, so the builder never
writes the output hash anywhere inside the tree. Exclusions mirror
``scripts/generate_manifest.py`` exactly.

Usage:
    python scripts/build_release.py --root . --output ../out.zip
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import sys
import zipfile
from pathlib import Path

MANIFEST_NAME = "BUILD_MANIFEST.sha256"


def _load_manifest_module():
    spec = importlib.util.spec_from_file_location(
        "qe_manifest", Path(__file__).resolve().parent / "generate_manifest.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def build(root: Path, output: Path) -> dict:
    mod = _load_manifest_module()

    # 1. regenerate + 2. verify
    # newline="\n" is deliberate: the packed manifest's bytes must equal a
    # fresh generation on every platform.  Text-mode here translated "\n" to
    # CRLF on Windows, so the revision-1 archive shipped a manifest that a
    # platform using LF conventions could not reproduce byte-for-byte (the
    # audit's F-03).
    (root / MANIFEST_NAME).write_text(mod.generate(root), encoding="utf-8",
                                      newline="\n")
    problems = mod.verify(root, root / MANIFEST_NAME)
    if problems:
        raise SystemExit("manifest verify failed: %s" % problems)

    # 3. pack
    covered = set(mod.package_files(root))
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in sorted(covered):
            z.write(root / rel, rel)
        z.write(root / MANIFEST_NAME, MANIFEST_NAME)

    # 4. coverage assert
    members = set(zipfile.ZipFile(output).namelist())
    extra = members - covered - {MANIFEST_NAME}
    missing = covered - members
    if extra or missing:
        raise SystemExit("coverage mismatch extra=%s missing=%s"
                         % (sorted(extra), sorted(missing)))

    # 5. detached hash (never written into the tree)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    return {"output": str(output), "sha256": digest,
            "members": len(members), "manifest_entries": len(covered),
            "bytes": output.stat().st_size}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=Path("."))
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(argv)
    info = build(args.root.resolve(), args.output.resolve())
    for k, v in info.items():
        print("%s: %s" % (k, v))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
