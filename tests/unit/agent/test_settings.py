"""Tests for persisted OpenAI-compatible model settings."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from refineq.agent.settings import ModelSettings, ModelSettingsRepository


def test_model_settings_round_trip_without_exposing_the_api_key(tmp_path: Path) -> None:
    repository = ModelSettingsRepository(tmp_path)
    saved = repository.save(
        "owner-1",
        ModelSettings(
            base_url="https://api.openai.com/v1",
            model="exam-tutor",
            api_key="sk-secret-value-1234",
        )
    )

    loaded = repository.load("owner-1")
    public = repository.public("owner-1")

    assert saved.model == "exam-tutor"
    assert loaded.api_key.get_secret_value() == "sk-secret-value-1234"
    assert public.configured is True
    assert public.api_key_hint.endswith("1234")
    assert "sk-secret-value-1234" not in public.model_dump_json()
    settings_path = tmp_path / "users" / "owner-1" / "settings" / "model.json"
    assert settings_path.is_file()
    assert "sk-secret-value-1234" not in settings_path.read_text(encoding="utf-8")
    assert json.loads(settings_path.read_text(encoding="utf-8"))["schema_version"] == 2


def test_model_settings_are_isolated_by_owner(tmp_path: Path) -> None:
    repository = ModelSettingsRepository(tmp_path)
    repository.save(
        "alice",
        ModelSettings(
            base_url="https://api.openai.com/v1",
            model="alice-model",
            api_key="alice-secret-1234",
        ),
    )

    assert repository.public("alice").configured is True
    assert repository.public("bob").configured is False


@pytest.mark.parametrize(
    "base_url",
    [
        "http://api.openai.com/v1",
        "https://127.0.0.1/v1",
        "https://10.1.2.3/v1",
        "https://169.254.169.254/latest/",
        "https://[::1]/v1",
    ],
)
def test_model_settings_reject_insecure_or_non_public_literal_endpoints(
    base_url: str,
) -> None:
    with pytest.raises(ValidationError):
        ModelSettings(base_url=base_url, model="exam-tutor", api_key="secret")


def test_model_settings_repository_rejects_hosts_outside_server_allowlist(
    tmp_path: Path,
) -> None:
    repository = ModelSettingsRepository(tmp_path)

    with pytest.raises(ValueError, match="allowlist"):
        repository.save(
            "owner-1",
            ModelSettings(
                base_url="https://models.example.com/v1",
                model="exam-tutor",
                api_key="secret",
            ),
        )


def test_model_settings_repository_accepts_explicitly_allowlisted_gateway(
    tmp_path: Path,
) -> None:
    repository = ModelSettingsRepository(tmp_path, allowed_hosts={"gateway.internal"})
    settings = ModelSettings(
        base_url="https://gateway.internal/v1",
        model="exam-tutor",
        api_key="secret",
    )

    repository.save("owner-1", settings)

    assert repository.load("owner-1").model == "exam-tutor"


def test_legacy_plaintext_model_settings_are_migrated_after_load(tmp_path: Path) -> None:
    path = tmp_path / "users" / "owner-1" / "settings" / "model.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "base_url": "https://api.openai.com/v1",
                "model": "exam-tutor",
                "api_key": "legacy-secret",
                "temperature": 0.2,
            }
        ),
        encoding="utf-8",
    )
    repository = ModelSettingsRepository(tmp_path)

    loaded = repository.load("owner-1")

    assert loaded.api_key.get_secret_value() == "legacy-secret"
    migrated = path.read_text(encoding="utf-8")
    assert "legacy-secret" not in migrated
    assert json.loads(migrated)["schema_version"] == 2
