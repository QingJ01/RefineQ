"""Static package-boundary contracts for high-level dependency direction."""

from __future__ import annotations

import ast
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = REPOSITORY_ROOT / "src" / "refineq"


def _absolute_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.add(node.module)
    return imports


def test_mcp_transport_does_not_depend_on_the_http_api_package() -> None:
    violations = {
        path.relative_to(REPOSITORY_ROOT): sorted(
            module for module in _absolute_imports(path) if module.startswith("refineq.api")
        )
        for path in (SOURCE_ROOT / "mcp").glob("*.py")
        if any(module.startswith("refineq.api") for module in _absolute_imports(path))
    }

    assert violations == {}
