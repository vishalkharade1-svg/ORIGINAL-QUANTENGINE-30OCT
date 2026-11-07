"""Content-based text decoding for the release scanners (Phase160).

The Phase159 vendor-audit handoff declared the boundary this module closes:
the security scanners' content rules applied to a declared suffix set decoded
as UTF-8 (BOM-tolerant), so members written as UTF-16 -- the encoding Windows
PowerShell-era tools produce -- were invisible to every content rule, and
members outside the suffix set were never read at all.

Decoding is now decided by the bytes, not by the filename:

* UTF-8, with or without a BOM (``utf-8-sig``);
* UTF-16 LE/BE, with a BOM or sniffed from the NUL pattern of BOM-less output
  (Windows-tool text); a decode whose replacement-character ratio is too high
  is not treated as text;
* UTF-32 with a BOM -- checked first, because a UTF-32LE BOM begins with the
  UTF-16LE BOM bytes and a UTF-32 file misread as UTF-16 would present as
  NUL-interleaved text that no rule can match;
* anything else -- including ambiguous NUL patterns and strict-UTF-8 failures
  -- is *binary*: reported as ``binary=True`` rather than scanned as garbage.

Callers decide what to do with binary: the release scanners treat binary
members as explicitly declared opaque classes (see ``scan_privacy.py``), so a
member can never be silently uninspected.

This module reads only; it never writes.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Optional


@dataclasses.dataclass(frozen=True)
class Decoded:
    """One decoded text member, or a failed decode classified as binary."""

    text: str
    encoding: str  # "utf-8-sig" | "utf-16" | "utf-16-le" | "utf-16-be" | "utf-32"
    binary: bool = False


#: BOM -> codec, longest first: the UTF-32LE BOM begins with the UTF-16LE BOM.
_BOM_CODECS = (
    (b"\xff\xfe\x00\x00", "utf-32"),
    (b"\x00\x00\xfe\xff", "utf-32"),
    (b"\xff\xfe", "utf-16"),
    (b"\xfe\xff", "utf-16"),
)


def _too_many_replacements(text: str) -> bool:
    """A decode with more replacement characters than this is not text.

    Genuine UTF-16 text decodes with zero U+FFFD; binary misinterpreted as
    UTF-16 produces unpaired surrogates and therefore replacements.
    """
    return text.count("\ufffd") > max(2, len(text) // 100)


def _decode_checked(data: bytes, encoding: str) -> Optional[str]:
    try:
        text = data.decode(encoding, errors="replace")
    except (LookupError, UnicodeError):  # pragma: no cover - codecs are fixed
        return None
    return None if _too_many_replacements(text) else text


def looks_like_utf16(data: bytes) -> Optional[str]:
    """BOM-less UTF-16 sniff: NULs sit at one parity for ASCII-heavy text.

    Returning ``None`` for an ambiguous pattern is deliberate: ambiguity is
    classified binary (and must then be declared as opaque), never guessed.
    """
    sample = data[:512]
    if len(sample) < 4:
        return None
    odd_nuls = sum(1 for byte in sample[1::2] if byte == 0)
    even_nuls = sum(1 for byte in sample[0::2] if byte == 0)
    threshold = max(4, (len(sample) // 2) // 4)
    if odd_nuls >= threshold and odd_nuls > even_nuls * 4:
        return "utf-16-le"
    if even_nuls >= threshold and even_nuls > odd_nuls * 4:
        return "utf-16-be"
    return None


def decode_bytes(data: bytes) -> Decoded:
    """Decode *data* by content.  Binary input returns ``binary=True``."""
    for bom, codec in _BOM_CODECS:
        if data.startswith(bom):
            text = _decode_checked(data, codec)
            if text is None:
                return Decoded("", codec, binary=True)
            return Decoded(text, codec)
    if b"\x00" in data[:4096]:
        guessed = looks_like_utf16(data)
        if guessed is not None:
            text = _decode_checked(data, guessed)
            if text is not None:
                return Decoded(text, guessed)
        return Decoded("", "binary", binary=True)
    try:
        return Decoded(data.decode("utf-8-sig"), "utf-8-sig")
    except UnicodeDecodeError:
        return Decoded("", "binary", binary=True)


def read_text_file(path: Path) -> Optional[Decoded]:
    """Decode one member; ``None`` only when the file cannot be read at all."""
    try:
        data = path.read_bytes()
    except OSError:  # pragma: no cover - permission/race conditions
        return None
    return decode_bytes(data)
