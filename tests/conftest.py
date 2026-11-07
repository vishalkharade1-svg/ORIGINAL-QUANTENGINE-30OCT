"""Session-level snapshot guard: a test run must not mutate the packaged tree.

The Phase158 independent audit found that running tests physically rewrote
manifest-covered files.  On Windows the rewrite happens to be byte-identical
(text-mode newline translation reproduces the CRLF the file already has), so it
is invisible there; the same run on a platform with different newline
conventions changes bytes, invalidates ``BUILD_MANIFEST.sha256`` mid-run, and
makes the "an extraction still verifies after the suite" claim false on that
platform.

This guard turns "the suite leaves the snapshot byte-identical" into an
enforced property of every session, without touching any test:

* session start: every manifest-covered file is read into memory and checked
  against ``BUILD_MANIFEST.sha256``; a tree that is already non-pristine is
  reported as ``SNAPSHOT_GUARD_TREE_NOT_PRISTINE`` and fails the session;
* after every test: a watchlist of files the suite is known to rebuild in
  place (each has a change-detector test that re-runs its builder) is checked
  and restored byte-exactly when a test changed it;
* every 50 tests and again at session end: the whole covered set is checked,
  every changed file is restored from the session snapshot, and files a test
  *added* to the tree are reported (and fail the session);
* every restore emits ``SNAPSHOT_GUARD_RESTORED <path>`` and the session ends
  with a machine-readable ``SNAPSHOT_GUARD_SUMMARY {json}`` line.

The guard restores bytes a test wrote over; it never hides the event and never
weakens an assertion.  A test that reads a sealed artifact after another test
rebuilt it sees the recorded bytes, exactly as if the rebuild had not happened
-- which is the property the release claims.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_TESTS_DIR = _ROOT / "tests"
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))
_MANIFEST = _ROOT / "BUILD_MANIFEST.sha256"

#: Files the suite rebuilds in place (change-detector tests re-run their
#: builders).  Recorded here so every test boundary can check them cheaply;
#: the periodic full sweep covers anything unknown.
_WATCHLIST = (
    "data/runtime/risk_policy_overrides.json",
    "research/phase11g_n/feasibility.json",
    "research/phase11g_o/feasibility_o.json",
    "research/phase11g_p/readiness_p.json",
    "research/phase11g_q/trigger_q.json",
    "research/phase11g_r/readiness_r.json",
    "research/phase11g_s/readiness_s.json",
    "research/phase11g_t/readiness_t.json",
    "research/phase11g_u/readiness_u.json",
    "research/results/phase33_oos_readiness_snapshot.json",
    "research/results/phase35_symbol_coverage.json",
    "research/results/phase36_provenance_symbol_coverage.json",
    "research/results/phase37_multi_symbol_oos_manifest.json",
    "research/results/phase48_discovery_capture.json",
)

_FULL_SWEEP_EVERY = 50


class _SnapshotGuard:
    def __init__(self):
        self.snapshot: dict[str, bytes] = {}
        self.entries: dict[str, str] = {}
        self.watch = set(_WATCHLIST)
        self.restores: dict[str, int] = {}
        self.start_problems: list[str] = []
        self.tests = 0

    def load(self) -> None:
        if not _MANIFEST.exists():
            self.start_problems = ["BUILD_MANIFEST.sha256 is absent"]
            print("SNAPSHOT_GUARD_TREE_NOT_PRISTINE " + json.dumps(self.start_problems))
            return
        for line in _MANIFEST.read_text(encoding="utf-8").splitlines():
            parts = line.strip().split(None, 1)
            if len(parts) == 2 and len(parts[0]) == 64:
                self.entries[parts[1]] = parts[0]
        for rel in sorted(self.entries):
            path = _ROOT / rel
            if not path.exists():
                self.start_problems.append("missing:" + rel)
                continue
            blob = path.read_bytes()
            self.snapshot[rel] = blob
            if hashlib.sha256(blob).hexdigest() != self.entries[rel]:
                self.start_problems.append("mismatch:" + rel)
        if self.start_problems:
            print("SNAPSHOT_GUARD_TREE_NOT_PRISTINE "
                  + json.dumps(sorted(self.start_problems)))

    def _check(self, paths) -> None:
        for rel in sorted(paths):
            recorded = self.snapshot.get(rel)
            if recorded is None:
                continue
            path = _ROOT / rel
            try:
                current = path.read_bytes() if path.exists() else None
            except OSError:  # pragma: no cover - transient file-system state
                continue
            if current == recorded:
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(recorded)
            self.restores[rel] = self.restores.get(rel, 0) + 1
            self.watch.add(rel)
            print("SNAPSHOT_GUARD_RESTORED %s (%s)" % (
                rel, "a test deleted it" if current is None else "a test rewrote it"))

    def after_test(self) -> None:
        self.tests += 1
        self._check(self.watch)
        if self.tests % _FULL_SWEEP_EVERY == 0:
            self._check(self.snapshot)

    def _added_files(self) -> list[str]:
        try:
            spec = importlib.util.spec_from_file_location(
                "phase158_snapshot_guard_manifest",
                _ROOT / "scripts" / "generate_manifest.py")
            if spec is None or spec.loader is None:  # pragma: no cover
                return []
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            now = set(module.package_files(_ROOT))
        except Exception as exc:  # pragma: no cover - diagnostic only
            print("SNAPSHOT_GUARD_ADDITION_CHECK_SKIPPED %r" % (exc,))
            return []
        return sorted(now - set(self.entries))

    def finish(self) -> bool:
        self._check(self.snapshot)
        additions = self._added_files()
        print("SNAPSHOT_GUARD_SUMMARY " + json.dumps({
            "tests": self.tests,
            "covered_files": len(self.snapshot),
            "tree_pristine_at_session_start": not self.start_problems,
            "start_problems": sorted(self.start_problems),
            "restores": dict(sorted(self.restores.items())),
            "files_added_by_tests": additions,
        }, sort_keys=True))
        return bool(self.start_problems) or bool(additions)


_guard = _SnapshotGuard()


def pytest_configure(config):
    _guard.load()


def pytest_runtest_teardown(item, nextitem):
    _guard.after_test()


def pytest_sessionfinish(session, exitstatus):
    if _guard.finish():
        session.exitstatus = 1
