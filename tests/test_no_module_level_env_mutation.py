"""Meta-test: tests/ files must not mutate process-global state at module level.

Tick #63 caught two test files (test_knn_advisor, test_knn_analytics)
that set `os.environ["TRINITY_HOME"] = tempfile.mkdtemp(...)` at module
top-level. Once pytest collected those modules, the env var leaked for
the entire process — every later test resolved `trinity_home()` to the
polluted tmp path, and the real-corpus depth tests silently skipped
with "0 embedded prompt nodes." Two real assertions disabled for an
unknown stretch of session history; meta-principle #14 calls this
"invisible armor."

This guard scans every `tests/test_*.py` file with the `ast` module
and fails if any module-level statement mutates `os.environ` or
`sys.path`. Mutations inside functions / fixtures / classes are fine —
those are scoped. Reading `os.environ[...]` is also fine — only
assignments / deletes / .update / .setdefault calls trip the gate.
"""
from __future__ import annotations

import ast
from pathlib import Path

TESTS_DIR = Path(__file__).parent


def _module_level_mutations(tree: ast.Module) -> list[str]:
    """Return descriptions of any module-level os.environ / sys.path mutations.

    Walks ONLY the top-level statements — anything inside a function,
    class, or fixture is correctly scoped and out of scope here.
    """
    findings: list[str] = []
    for node in tree.body:
        # Top-level assignment: os.environ["X"] = ...
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Subscript)
                    and isinstance(target.value, ast.Attribute)
                    and isinstance(target.value.value, ast.Name)
                    and target.value.value.id == "os"
                    and target.value.attr == "environ"
                ):
                    findings.append(
                        f"line {node.lineno}: module-level os.environ[...] = ..."
                    )
                if (
                    isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "sys"
                    and target.attr == "path"
                ):
                    findings.append(
                        f"line {node.lineno}: module-level sys.path = ..."
                    )
        # Top-level expr: os.environ.update(...), sys.path.append(...), etc.
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            func = node.value.func
            if (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Attribute)
                and isinstance(func.value.value, ast.Name)
                and func.value.value.id == "os"
                and func.value.attr == "environ"
                and func.attr in {"update", "setdefault", "pop", "clear"}
            ):
                findings.append(
                    f"line {node.lineno}: module-level os.environ.{func.attr}(...)"
                )
            if (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Attribute)
                and isinstance(func.value.value, ast.Name)
                and func.value.value.id == "sys"
                and func.value.attr == "path"
                and func.attr in {"append", "insert", "extend"}
            ):
                findings.append(
                    f"line {node.lineno}: module-level sys.path.{func.attr}(...)"
                )
        # Top-level delete: del os.environ["X"]
        if isinstance(node, ast.Delete):
            for target in node.targets:
                if (
                    isinstance(target, ast.Subscript)
                    and isinstance(target.value, ast.Attribute)
                    and isinstance(target.value.value, ast.Name)
                    and target.value.value.id == "os"
                    and target.value.attr == "environ"
                ):
                    findings.append(
                        f"line {node.lineno}: module-level del os.environ[...]"
                    )
    return findings


def test_no_module_level_env_mutations_in_tests():
    """Catch the tick #63 anti-pattern before it ships again."""
    violations: dict[str, list[str]] = {}
    for path in sorted(TESTS_DIR.glob("test_*.py")):
        # Skip self — this file talks about os.environ in docstrings + ast
        # AST node names, neither of which trip the actual walker, but it's
        # cleanest to exempt the guard from auditing itself.
        if path.name == Path(__file__).name:
            continue
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
        except (OSError, SyntaxError):
            continue
        findings = _module_level_mutations(tree)
        if findings:
            violations[path.name] = findings
    assert not violations, (
        "Found module-level process-state mutations in tests/. These leak "
        "into every subsequent test in the suite (pytest imports all modules "
        "at collection, before any test runs) and create invisible armor — "
        "guards that silently skip because shared state was poisoned. "
        "Scope state via a fixture (e.g., autouse + monkeypatch.setenv) "
        "instead. Violations:\n"
        + "\n".join(f"  {fname}: {', '.join(notes)}" for fname, notes in violations.items())
    )
