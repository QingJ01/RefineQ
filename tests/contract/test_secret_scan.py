"""High-confidence credentials must never enter the tracked source tree."""

from __future__ import annotations

from pathlib import Path

from scripts.scan_secrets import scan_paths, scan_repository

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_tracked_repository_has_no_high_confidence_secrets() -> None:
    assert scan_repository(REPOSITORY_ROOT) == []


def test_scanner_detects_a_generated_provider_token(tmp_path: Path) -> None:
    fixture = tmp_path / "unsafe.env"
    fixture.write_text("MODEL_KEY=" + "sk-" + ("a" * 32), encoding="utf-8")

    findings = scan_paths([fixture], root=tmp_path)

    assert len(findings) == 1
    assert findings[0].kind == "provider_token"
    assert findings[0].line == 1
