"""Helpers for checking content determinism without rewriting raw-byte-pinned evidence.

The manifest pins the exact historical bytes (including CRLF). Some deterministic
research generators emit canonical LF text on POSIX. Tests compare normalized
content after a rerun while independently verifying the original bytes against
BUILD_MANIFEST.sha256.
"""
from __future__ import annotations

import hashlib
from pathlib import Path


def normalize_line_endings(raw: bytes) -> bytes:
    return raw.replace(b"\r\n", b"\n")


def read_pinned_artifact(path: Path, root: Path) -> bytes:
    path = Path(path)
    root = Path(root)
    relative = path.resolve().relative_to(root.resolve()).as_posix()
    manifest = root / "BUILD_MANIFEST.sha256"
    for line in manifest.read_text(encoding="utf-8").splitlines():
        digest, separator, listed_path = line.partition("  ")
        if separator and listed_path == relative:
            raw = path.read_bytes()
            actual = hashlib.sha256(raw).hexdigest()
            if actual != digest:
                raise AssertionError(
                    f"raw artifact pin mismatch for {relative}: "
                    f"expected {digest}, got {actual}"
                )
            return raw
    raise AssertionError(f"artifact is not pinned in BUILD_MANIFEST.sha256: {relative}")
