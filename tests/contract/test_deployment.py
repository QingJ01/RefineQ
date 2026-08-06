"""Static deployment contracts that do not require a local container daemon."""

from __future__ import annotations

import re
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
INFRASTRUCTURE_FILES = {
    "requirements.lock",
    "requirements-dev.lock",
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
    assert "request_body" in _read("infra/Caddyfile")
    assert "max_size {$REFINEQ_MATERIAL_MAX_REQUEST_BYTES" in _read("infra/Caddyfile")


def test_containers_are_unprivileged_and_runtime_state_is_mounted() -> None:
    api_image = _read("infra/Dockerfile.api")
    web_image = _read("infra/Dockerfile.web")
    compose = _read("infra/compose.yml")

    assert "USER refineq" in api_image
    assert "chown refineq:refineq /data" in api_image
    assert "USER nextjs" in web_image
    assert 'output: "standalone"' in _read("apps/web/next.config.ts")
    assert "refineq-data:/data" in compose
    assert compose.count("read_only: true") >= 2


def test_custom_deployment_environment_is_namespaced() -> None:
    deployment_text = "\n".join(
        _read(path) for path in ["infra/compose.yml", "infra/Caddyfile", ".env.example"]
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
        "ruff format --check",
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


def test_python_dependencies_are_locked_and_reused_by_ci_and_container() -> None:
    runtime_lock = _read("requirements.lock")
    development_lock = _read("requirements-dev.lock")
    workflow = _read(".github/workflows/tests.yml")
    api_image = _read("infra/Dockerfile.api")

    assert "--hash=sha256:" in runtime_lock
    assert "--hash=sha256:" in development_lock
    assert "pyjwt==" in runtime_lock.lower()
    assert "python-jose==" not in runtime_lock.lower()
    assert "ecdsa==" not in runtime_lock.lower()
    assert "httpx2==" in development_lock
    assert "pytest==" in development_lock
    assert "ruff==" in development_lock
    assert workflow.count("pip install --require-hashes -r requirements-dev.lock") >= 2
    assert "cache-dependency-path: requirements-dev.lock" in workflow
    assert "pip install --require-hashes -r requirements.lock" in api_image
    assert "pip install --no-deps ." in api_image


def test_public_deployment_exposes_security_and_resource_boundaries() -> None:
    example = _read(".env.example")
    compose = _read("infra/compose.yml")

    required_names = {
        "REFINEQ_MODEL_ENCRYPTION_KEY",
        "REFINEQ_MODEL_ENDPOINT_ALLOWED_HOSTS",
        "REFINEQ_MATERIAL_MAX_COUNT_PER_USER",
        "REFINEQ_MATERIAL_MAX_BYTES_PER_USER",
        "REFINEQ_MATERIAL_MAX_REQUEST_BYTES",
        "REFINEQ_MATERIAL_MAX_PDF_PAGES",
        "REFINEQ_MATERIAL_MAX_DOCX_ENTRIES",
        "REFINEQ_MATERIAL_MAX_DOCX_EXPANDED_BYTES",
        "REFINEQ_MATERIAL_MAX_DOCX_COMPRESSION_RATIO",
        "REFINEQ_MATERIAL_MAX_EXTRACTED_CHARS",
        "REFINEQ_MATERIAL_EXTRACTION_TIMEOUT_SECONDS",
        "REFINEQ_MAX_WORKSPACES_PER_USER",
        "REFINEQ_MAX_PROJECTS_PER_USER",
        "REFINEQ_MAX_AGENT_SESSIONS_PER_USER",
        "REFINEQ_AUTH_RATE_LIMIT_REQUESTS",
        "REFINEQ_MUTATION_RATE_LIMIT_REQUESTS",
        "REFINEQ_RATE_LIMIT_WINDOW_SECONDS",
        "REFINEQ_FORWARDED_ALLOW_IPS",
    }

    for name in required_names:
        assert name in example
        assert name in compose
