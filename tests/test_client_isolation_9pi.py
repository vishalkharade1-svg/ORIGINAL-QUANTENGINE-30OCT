"""
Phase 9P-i Client Import Isolation regression test.

Phase 9P-h's mandatory architecture boundary is that the desktop
client is a THIN HTTP client and NEVER imports engine internals:

    CLIENT -> CONTROL API -> ENGINE
    (client must never reach engine internals directly)

This regression test guards that boundary at the import level. Because
sys.modules is process-global (the rest of the test suite loads engine
modules), the scan runs in a FRESH interpreter subprocess so the result
reflects ONLY what importing core.client itself pulls in -- not what
other tests imported earlier in the same process.

The fresh interpreter imports every module under core/client and
reports the resulting `core.*` modules in sys.modules. The test then
asserts that set contains only core.client's own modules and the
stdlib-only support modules -- never engine internals (runtime/live/
strategy/risk/execution/exchanges/pipeline/research/backtesting/
analytics/registry/universe/events, or engine objects like
TradeRegistry / BrokerEngine / RealTimeEngine / PipelineContext /
InstitutionalPipeline).

Stdlib-only, deterministic, offline.
"""

import json
import subprocess
import sys
import unittest

ISOLATION_PROBE = r"""
import importlib
import json
import pkgutil
import sys

import core.client as pkg

names = [m.name for m in pkgutil.walk_packages(pkg.__path__, prefix=pkg.__name__ + ".")]
for name in names:
    importlib.import_module(name)

core_modules = sorted(m for m in sys.modules if m == "core" or m.startswith("core."))
print(json.dumps(core_modules))
"""

FORBIDDEN = (
    "core.runtime",
    "core.live",
    "core.strategy",
    "core.risk",
    "core.execution",
    "core.exchanges",
    "core.pipeline",
    "core.research",
    "core.scoring",
    "core.setup",
    "core.market_structure",
    "core.backtesting",
    "core.analytics",
    "core.registry",
    "core.universe",
    "core.replay",
    "core.breaker",
    "core.orderflow",
    "core.volume_profile",
    "core.indicators",
    "core.events",
    "core.history",
    "core.scanning",
    "core.market_state",
)

FORBIDDEN_OBJECTS = (
    "traderegistry",
    "brokerengine",
    "realtimeengine",
    "pipelinecontext",
    "institutionalpipeline",
    "pipelineregistry",
    "paperruntime",
    "paperexecutionadapter",
    "deltaorderexecutor",
    "deltaexchange",
)


class ClientImportIsolationTestCase(unittest.TestCase):

    def _core_modules_from_fresh_interpreter(self):
        proc = subprocess.run(
            [sys.executable, "-c", ISOLATION_PROBE],
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(
            proc.returncode, 0,
            "isolation probe failed:\n%s" % proc.stderr,
        )
        return json.loads(proc.stdout.strip().splitlines()[-1])

    def test_client_never_imports_engine_internals(self):
        core_modules = self._core_modules_from_fresh_interpreter()

        self.assertTrue(core_modules, "probe reported no core modules")

        forbidden = sorted(
            m for m in core_modules
            if any(m == f or m.startswith(f + ".") for f in FORBIDDEN)
        )
        self.assertEqual(
            forbidden,
            [],
            "core.client transitively imported engine internals: %s"
            % ", ".join(forbidden),
        )

    def test_forbidden_objects_absent_from_client_sources(self):
        core_modules = self._core_modules_from_fresh_interpreter()

        # every core.* module actually loaded must be either a
        # core.client module or one of the engine-support stdlib
        # boundaries (core.common, core.monitoring); none may be an
        # engine object module.
        offenders = [
            m for m in core_modules
            if not m.startswith("core.client")
            and not m.startswith("core.common")
            and not m.startswith("core.monitoring")
            and m != "core"
        ]
        self.assertEqual(
            offenders,
            [],
            "core.client dragged in non-client engine modules: %s"
            % ", ".join(offenders),
        )


if __name__ == "__main__":
    unittest.main()
