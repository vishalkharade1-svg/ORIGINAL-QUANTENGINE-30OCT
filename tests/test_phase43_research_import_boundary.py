import ast
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
TARGETS = (
    ROOT / "core" / "research" / "oos",
    ROOT / "core" / "research" / "readiness",
    ROOT / "core" / "research" / "conditional_ml",
)
FORBIDDEN_PREFIXES = (
    "core.execution", "core.live", "core.paper_trading", "core.trading",
    "core.orders", "core.ledger", "core.runtime",
)


class TestPhase43ResearchImportBoundary(unittest.TestCase):
    def test_research_modules_do_not_import_production_runtime(self):
        violations=[]
        for root in TARGETS:
            for path in sorted(root.rglob("*.py")):
                tree=ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
                for node in ast.walk(tree):
                    names=[]
                    if isinstance(node, ast.Import):
                        names=[a.name for a in node.names]
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        names=[node.module]
                    for name in names:
                        if any(name == p or name.startswith(p + ".") for p in FORBIDDEN_PREFIXES):
                            violations.append((str(path.relative_to(ROOT)), name))
        self.assertEqual(violations, [])

    def test_no_dynamic_production_import_strings_in_research_sources(self):
        violations=[]
        for root in TARGETS:
            for path in sorted(root.rglob("*.py")):
                text=path.read_text(encoding="utf-8")
                for prefix in FORBIDDEN_PREFIXES:
                    if prefix in text:
                        violations.append((str(path.relative_to(ROOT)), prefix))
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
