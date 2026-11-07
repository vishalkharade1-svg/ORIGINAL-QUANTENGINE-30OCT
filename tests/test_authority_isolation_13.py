"""Phase-13 P1: production-isolation + local-track boundary pins.

Static caller analysis (mirroring the test_authoritative_path_phase7
method): proves on the ACTUAL tree that

  * no strategy-side module can reach execution (no Strategy ->
    Broker bypass);
  * research/validation contain no execution usage (only
    never-import rejection guards);
  * paper-side modules contain no live-write tokens;
  * local-track safety modules have no production callers and so
    cannot silently become authoritative.

Deterministic, offline, stdlib only.
"""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Local-track safety symbols: DEFINED + unit-tested, NOT WIRED.
# (apply_costs / require_realistic / verify_contract_spec are
# additionally pinned in test_authoritative_path_phase7; the
# economics delegate recheck_rr and the conservative/contract
# gates are pinned here.)
LOCAL_TRACK_SYMBOLS = (
    "recheck_rr",
    "check_confidence",
    "check_leverage",
    "check_margin",
    "BalanceDivergenceHalt",
    "PortfolioExposure",
    "size_quantity",
)

STRATEGY_DIRS = (
    "core/setup",
    "core/scoring",
    "core/confluence",
    "core/pipeline",
    "core/order_blocks",
    "core/regime",
    "core/market_structure",
    "core/volume_profile",
    "core/orderflow",
)

EXECUTION_TOKENS = (
    "BrokerEngine",
    "DeltaOrderExecutor",
    "place_order",
    "submit_order",
    "cancel_order",
    "ALLOW_LIVE",
)


def _code_lines(path: Path):
    for line in path.read_text(encoding="utf-8").splitlines():
        yield line.split("#", 1)[0]


def _callers(name: str) -> list[str]:
    """Non-test, non-doc runtime call sites of ``name(`` under core/.

    Mirrors the authoritative-path filter: docstring-code spans
    (double-backtick references) and definitions/imports are not
    call sites.
    """
    hits = []
    for path in (ROOT / "core").rglob("*.py"):
        for number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1):
            code = line.split("#", 1)[0]
            if "``" in code or '"""' in line.strip()[:3]:
                continue
            if name + "(" not in code:
                continue
            if ("def " + name) in code or "import" in code:
                continue
            hits.append("%s:%d" % (path.relative_to(ROOT), number))
    return hits


class TestLocalTrackBoundaries(unittest.TestCase):
    def test_local_track_has_no_production_callers(self):
        for symbol in LOCAL_TRACK_SYMBOLS:
            with self.subTest(symbol=symbol):
                self.assertEqual(_callers(symbol), [])

    def test_balance_divergence_halt_explicitly_unwired(self):
        # §16 adjudication: the ONE mandatory divergence authority
        # is BrokerEngine -> Reconciler. BalanceDivergenceHalt must
        # stay LOCAL-TRACK/UNWIRED (see its class docstring).
        self.assertEqual(_callers("BalanceDivergenceHalt"), [])
        self.assertEqual(_callers("note_divergence"), [])


class TestStrategyExecutionSeparation(unittest.TestCase):
    def test_no_strategy_side_execution_tokens(self):
        hits = []
        for dirname in STRATEGY_DIRS:
            directory = ROOT / dirname
            if not directory.exists():
                continue
            for path in sorted(directory.rglob("*.py")):
                for number, code in enumerate(_code_lines(path),
                                             start=1):
                    for token in EXECUTION_TOKENS:
                        if token in code:
                            hits.append("%s:%d:[%s]"
                                        % (path.relative_to(ROOT),
                                           number, token))
        self.assertEqual(hits, [])


class TestResearchExecutionSeparation(unittest.TestCase):
    def test_research_has_no_execution_usage(self):
        # Tokenize-based (same method as
        # test_profiles_never_read_by_production): docstring and
        # comment text is blanked, so only real CODE usage can hit.
        # The package-docstring never-import guards are documentation,
        # not usage, and are correctly invisible here.
        import io
        import tokenize

        hits = []
        for dirname in ("core/research", "core/validation"):
            directory = ROOT / dirname
            if not directory.exists():
                continue
            for path in sorted(directory.rglob("*.py")):
                src = path.read_text(encoding="utf-8", errors="replace")
                code = "".join(
                    " " * (t.end[1] - t.start[1])
                    if t.type in (tokenize.STRING, tokenize.COMMENT)
                    else t.string
                    for t in tokenize.generate_tokens(
                        io.StringIO(src).readline))
                for token in EXECUTION_TOKENS:
                    if token in code:
                        hits.append("%s:[%s]"
                                    % (path.relative_to(ROOT), token))
        self.assertEqual(hits, [])


class TestPaperLiveSeparation(unittest.TestCase):
    def test_paper_side_has_no_live_write_tokens(self):
        hits = []
        for dirname in ("core/paper_trading", "core/runtime"):
            for path in sorted((ROOT / dirname).rglob("*.py")):
                for number, code in enumerate(_code_lines(path),
                                             start=1):
                    for token in ("dry_run=False",
                                  "DeltaOrderExecutor(",
                                  "_require_auth", "ALLOW_LIVE"):
                        if token in code:
                            hits.append("%s:%d:[%s]"
                                        % (path.relative_to(ROOT),
                                           number, token))
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
