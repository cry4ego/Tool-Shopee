"""Smoke test: các module import được và dùng logging thay cho print()."""
import ast
import importlib
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

PROJECT_DIR = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("name", ["config", "logging_setup", "login", "poster", "scheduler"])
def test_module_imports(name: str) -> None:
    importlib.import_module(name)


@pytest.mark.parametrize("name", ["login", "poster", "scheduler"])
def test_module_has_no_print_calls(name: str) -> None:
    tree = ast.parse((PROJECT_DIR / f"{name}.py").read_text(encoding="utf-8"))
    lines = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print"
    ]
    assert lines == [], f"{name}.py còn print() ở dòng {lines}"
