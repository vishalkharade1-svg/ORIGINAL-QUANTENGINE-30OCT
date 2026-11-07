"""QuantEngine Deterministic Research & Code Hashing Engine.

Provides platform-independent, checkout-invariant cryptographic hashing for
research artifacts, source code generators, and evidence verification.

Core Design Principles:
1. Platform Invariance: Source code digests are identical across Windows (CRLF),
   Unix/Linux (LF), and legacy MacOS (CR) environments.
2. Content Integrity: Strict byte sensitivity to all semantic and non-line-ending
   syntactic changes (spaces, tabs, variable names, values, docstrings).
3. Canonical Serialization: JSON structures follow strict deterministic formatting
   (sorted keys, explicit separators, trailing newline, UTF-8).
4. No Strategy Mutation: Standalone utility providing deterministic verification
   without altering frozen historical strategy or research baselines.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Union


def normalize_line_endings(blob_or_text: Union[bytes, str]) -> bytes:
    """Normalize line endings to canonical Unix LF (b'\\n').

    Accepts raw bytes or Unicode strings. Converts all CRLF (b'\\r\\n') and
    isolated CR (b'\\r') into canonical LF (b'\\n'). Strips BOM if present.

    Args:
        blob_or_text: Raw file bytes or Python string.

    Returns:
        Canonical UTF-8 bytes with normalized LF line endings.
    """
    if isinstance(blob_or_text, str):
        # Normalize in Unicode text space then encode
        text = blob_or_text.replace("\r\n", "\n").replace("\r", "\n")
        return text.encode("utf-8")
    elif isinstance(blob_or_text, (bytes, bytearray)):
        data = bytes(blob_or_text)
        # Strip UTF-8 BOM if present
        if data.startswith(b"\xef\xbb\xbf"):
            data = data[3:]
        # Normalize CRLF and solitary CR
        data = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        return data
    else:
        raise TypeError(f"Expected bytes or str, got {type(blob_or_text).__name__}")


def compute_deterministic_source_hash(source: Union[bytes, str, Path]) -> str:
    """Compute deterministic SHA-256 digest of source code.

    Guaranteed to produce identical digests across operating systems regardless
    of Git autocrlf checkout configuration.

    Args:
        source: Path to source file, raw bytes, or text string.

    Returns:
        64-character lowercase hex SHA-256 digest.
    """
    if isinstance(source, (str, Path)) and isinstance(source, Path):
        raw_bytes = source.read_bytes()
    elif isinstance(source, str) and "\n" not in source and Path(source).is_file():
        # Passed path as string
        raw_bytes = Path(source).read_bytes()
    elif isinstance(source, (bytes, str)):
        raw_bytes = source
    else:
        raw_bytes = Path(source).read_bytes()

    canonical_bytes = normalize_line_endings(raw_bytes)
    return hashlib.sha256(canonical_bytes).hexdigest()


def canonical_code_hash(file_path: Union[str, Path]) -> str:
    """Convenience helper to compute deterministic code hash for a script file.

    Equivalent to compute_deterministic_source_hash(Path(file_path)).
    """
    return compute_deterministic_source_hash(Path(file_path))


def canonical_json_bytes(obj: Any) -> bytes:
    """Serialize Python data object to canonical deterministic JSON bytes.

    Specification:
    - Sorted keys (sort_keys=True)
    - 2-space indentation (indent=2)
    - Explicit separators (',', ': ')
    - Trailing newline ('\\n')
    - UTF-8 encoding
    """
    json_str = json.dumps(obj, indent=2, sort_keys=True, separators=(",", ": ")) + "\n"
    return json_str.encode("utf-8")


def compute_canonical_json_hash(obj: Any) -> str:
    """Compute SHA-256 digest of an object's canonical JSON representation."""
    return hashlib.sha256(canonical_json_bytes(obj)).hexdigest()


def verify_source_hash(source: Union[bytes, str, Path], expected_hash: str) -> bool:
    """Verify that source matches expected deterministic SHA-256 hash."""
    return compute_deterministic_source_hash(source).lower() == expected_hash.strip().lower()
