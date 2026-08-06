"""Static deployment contracts that do not require a local container daemon."""

from __future__ import annotations

import re
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
INFRASTRUCTURE_FILES = {
    "infra/Dockerfile.api",
    "infra/Dockerfile.web",
    "infra/compose.yml",
    "infra/Caddyfile",
    ".github/workflows/tests.yml",
    "docs/deployment.md",
}


def _read(relative: str) -> str:
    return (REPOSITORY_ROOT / relative).read_text(encoding="utf-8")


def test_deployment_has_one_explicit_entrypoint() -> None:
    missing = [path for path in INFRASTRUCTURE_FILES if not (REPOSITORY_ROOT / path).is_file()]

    assert missing == []
    compose = _read("infra/compose.yml")
    assert compose.count("\n    ports:") == 1
    assert "\n  caddy:" in compose
    caddy_block = compose.split("\n  caddy:", maxsplit=1)[1]
    assert "\n    ports:" in caddy_block
    assert "handle_path /api/*" in _read("infra/Caddyfile")


def test_containers_are_unprivileged_and_runtime_state_is_mounted() -> None:
    api_image = _read("infra/Dockerfile.api")
    web_image = _read("infra/Dockerfile.web")
    compose = _read("infra/compose.yml")

    assert "USER refineq" in api_image
    assert "chown refineq:refineq /data" in api_image
    assert "USER nextjs" in web_image
    assert "output: \"standalone\"" in _read("apps/web/next.config.ts")
    assert "refineq-data:/data" in compose
    assert compose.count("read_only: true") >= 2


def test_custom_deployment_environment_is_namespaced() -> None:
    deployment_text = "\n".join(
        _read(path)
        for path in ["infra/compose.yml", "infra/Caddyfile", ".env.example"]
    )
    interpolated = re.findall(r"\$\{?([A-Z][A-Z0-9_]+)", deployment_text)
    declared = re.findall(r"^\s{6}([A-Z][A-Z0-9_]+):", _read("infra/compose.yml"), re.MULTILINE)

    assert interpolated
    assert declared
    assert all(name.startswith("REFINEQ_") for name in interpolated + declared)


def test_ci_runs_python_web_browser_and_container_contracts() -> None:
    workflow = _read(".github/workflows/tests.yml")

    for command in [
        "ruff check",
        "pytest",
        "python scripts/scan_secrets.py",
        "npm test",
        "npm run lint",
        "npm run build",
        "playwright install --with-deps chromium",
        "npm run test:e2e",
        "docker compose -f infra/compose.yml config",
    ]:
        assert command in workflow
