import ast
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_phase17_artifact.py"


class TestPhase56DeterministicOosBuilder(unittest.TestCase):
    def test_builder_has_no_network_import_or_urlopen(self):
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("urllib", text)
        self.assertNotIn("urlopen", text)
        self.assertNotIn("api.delta.exchange/v2/products", text)

    def test_product_snapshot_is_required(self):
        ns = {"__file__": str(SCRIPT), "__name__": "phase56_test_module"}
        exec(compile(SCRIPT.read_text(encoding="utf-8"), str(SCRIPT), "exec"), ns)
        snap = ns["PRODUCT_SNAP"]
        if snap.exists():
            self.skipTest("workspace contains optional git-ignored snapshot")
        with self.assertRaisesRegex(RuntimeError, "MISSING_PRODUCT_SNAPSHOT"):
            ns["product_snapshot"]()

    def test_product_snapshot_only_reads_existing_cache(self):
        text = SCRIPT.read_text(encoding="utf-8")
        tree = ast.parse(text)
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "product_snapshot")
        calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call)]
        names = []
        for call in calls:
            if isinstance(call.func, ast.Name):
                names.append(call.func.id)
            elif isinstance(call.func, ast.Attribute):
                names.append(call.func.attr)
        self.assertIn("exists", names)
        self.assertIn("load", names)
        self.assertNotIn("urlopen", names)


if __name__ == "__main__":
    unittest.main()
