"""The core must not import the control plane or anything above it, and the control plane must not import the core."""
import ast
import unittest
from pathlib import Path

CORE = Path(__file__).resolve().parent.parent / "core"
CONTROL_PLANE = Path(__file__).resolve().parent.parent / "control_plane"
# Exam scripts that build a FakeModel; moving them to evaluation/ is a later ticket.
CORE_IMPORT_ALLOW = {"company_brain/agents/playbook/replay_exam.py"}
FORBIDDEN = {"control_plane", "agents", "lifecycle_kit", "web_console", "company_data"}


def imported_roots(path):
    """Top-level package names a file imports (relative imports stay inside core)."""
    roots = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            roots.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


class LayerBoundaryTests(unittest.TestCase):
    def test_core_has_files(self):
        self.assertTrue(list(CORE.glob("*.py")))

    def test_core_imports_no_upper_layer(self):
        bad = {p.name: sorted(imported_roots(p) & FORBIDDEN) for p in CORE.glob("*.py") if imported_roots(p) & FORBIDDEN}
        self.assertEqual(bad, {})

    def test_control_plane_does_not_import_core(self):
        bad = {str(p.relative_to(CONTROL_PLANE)): "core" for p in CONTROL_PLANE.rglob("*.py")
               if "core" in imported_roots(p) and str(p.relative_to(CONTROL_PLANE)) not in CORE_IMPORT_ALLOW}
        self.assertEqual(bad, {})

    def test_checker_catches_a_forbidden_import(self):
        tmp = Path(__file__).with_name("_boundary_probe.tmp")
        tmp.write_text("from control_plane.guardrails import x\nimport agents.y\n")
        try:
            self.assertEqual(imported_roots(tmp) & FORBIDDEN, {"control_plane", "agents"})
        finally:
            tmp.unlink()


if __name__ == "__main__":
    unittest.main()
