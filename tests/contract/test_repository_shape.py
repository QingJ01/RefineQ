"""Final repository-shape and naming safeguards."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]

REQUIRED_PATHS = {
    "apps/web",
    "src/refineq",
    "infra",
    "scripts",
    "tests",
    "docs",
}
LEGACY_PRODUCT_ROOT = "deep" + "tutor"
FORBIDDEN_ROOTS = {
    "assets",
    LEGACY_PRODUCT_ROOT,
    f"{LEGACY_PRODUCT_ROOT}_cli",
    f"{LEGACY_PRODUCT_ROOT}_web",
    "deploy",
    "packaging",
    "requirements",
    "web",
}
FORBIDDEN_ROOT_FILES = {
    ".refineq-migration.json",
    "CITATION.cff",
    "Communication.md",
    "compose.codex-oauth.yaml",
    "compose.yaml",
    "CONTAINERIZATION.md",
    "docker-compose.dev.yml",
    "docker-compose.ghcr.yml",
    "docker-compose.yml",
    "Dockerfile",
    "Dockerfile.runner",
    "MANIFEST.in",
    "requirements.txt",
    "SKILL.md",
}
FORBIDDEN_PRODUCT_PATHS = {
    "apps/web/components/goal-wizard.tsx",
}
TEXT_SUFFIXES = {
    ".css",
    ".html",
    ".json",
    ".md",
    ".mjs",
    ".py",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}
LEGACY_BRAND_PATTERN = re.compile(r"deep[\s_-]?tutor|open[\s_-]?tutor", re.IGNORECASE)


def _tracked_files() -> list[Path]:
    completed = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
    )
    return [
        REPOSITORY_ROOT / path.decode("utf-8") for path in completed.stdout.split(b"\0") if path
    ]


def test_final_repository_roots_are_focused() -> None:
    for relative_path in REQUIRED_PATHS:
        assert (REPOSITORY_ROOT / relative_path).is_dir(), (
            f"Missing required repository path: {relative_path}"
        )
    for relative_path in FORBIDDEN_ROOTS:
        assert not (REPOSITORY_ROOT / relative_path).exists(), (
            f"Superseded application root still exists: {relative_path}"
        )
    for relative_path in FORBIDDEN_ROOT_FILES:
        assert not (REPOSITORY_ROOT / relative_path).exists(), (
            f"Superseded root file still exists: {relative_path}"
        )
    for relative_path in FORBIDDEN_PRODUCT_PATHS:
        assert not (REPOSITORY_ROOT / relative_path).exists(), (
            f"Superseded product path still exists: {relative_path}"
        )


def test_browser_client_uses_only_learning_workspace_routes() -> None:
    api_source = (REPOSITORY_ROOT / "apps" / "web" / "lib" / "api.ts").read_text(encoding="utf-8")

    assert "/projects/" not in api_source
    assert "createProject" not in api_source


def test_tracked_product_text_has_no_legacy_brand_names() -> None:
    violations = []
    for path in _tracked_files():
        if path.suffix.lower() not in TEXT_SUFFIXES or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if LEGACY_BRAND_PATTERN.search(text):
            violations.append(path.relative_to(REPOSITORY_ROOT).as_posix())

    assert violations == [], f"Legacy brand names remain in: {violations}"
