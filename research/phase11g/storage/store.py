"""11G-E lightweight research store (desktop-scale).

RAW: immutable files (never modified in place; writes refuse existing
paths unless explicit overwrite).
NORMALIZED: Parquet when pyarrow is importable, else canonical JSON.
METADATA: JSON sidecars with content hashes.
RESULTS: versioned JSON.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def _sha(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def write_raw(directory, name, payload: bytes, overwrite=False):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    if path.exists() and not overwrite:
        raise FileExistsError("raw store is immutable: %s" % path)
    path.write_bytes(payload)
    meta = {"name": name, "bytes": len(payload),
            "sha256": _sha(payload), "mutable": False}
    path.with_suffix(path.suffix + ".meta.json").write_text(json.dumps(meta, indent=1))
    return meta


def write_normalized(directory, name, rows):
    """rows: list of plain dicts. Returns metadata with content hash."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    blob = json.dumps(rows, sort_keys=True).encode()
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
        table = pa.Table.from_pylist([{k: str(v) if not isinstance(v, (int, float, bool, type(None))) else v
                                       for k, v in r.items()} for r in rows])
        path = directory / (name + ".parquet")
        pq.write_table(table, path)
        fmt = "parquet"
    except ImportError:
        path = directory / (name + ".json")
        path.write_bytes(blob)
        fmt = "json"
    meta = {"name": path.name, "rows": len(rows), "format": fmt,
            "sha256": _sha(blob)}
    path.with_suffix(path.suffix + ".meta.json").write_text(json.dumps(meta, indent=1))
    return meta


def read_normalized(directory, name):
    directory = Path(directory)
    pq_path = directory / (name + ".parquet")
    if pq_path.exists():
        import pyarrow.parquet as pq
        return pq.read_table(pq_path).to_pylist()
    js_path = directory / (name + ".json")
    return json.loads(js_path.read_text())
