"""11G-J dataset loader (raw zip -> RealTrade list, validated)."""

from __future__ import annotations

import csv
import io
import sys
import zipfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from research.phase11g_j.replay import engine as ENG  # noqa: E402
from research.phase11g_j.replay import events as REV  # noqa: E402

RAW_ZIP = (Path(__file__).resolve().parent.parent.parent / "phase11g_i" /
           "acquisition" / "raw" / "BTCUSDT" / "2026-09-05" /
           "BTCUSDT-aggTrades-2026-09-05.zip")
SYMBOL = "BTCUSDT"


def load_trades(zip_path=RAW_ZIP, symbol=SYMBOL):
    with zipfile.ZipFile(zip_path) as z:
        names = [n for n in z.namelist() if n.endswith(".csv")]
        assert len(names) == 1, names
        text = z.read(names[0]).decode()
    reader = csv.DictReader(io.StringIO(text))
    out = []
    for i, row in enumerate(reader):
        out.append(REV.from_csv_row(row, i, symbol=symbol))
    return ENG.TradeReplay(out)
