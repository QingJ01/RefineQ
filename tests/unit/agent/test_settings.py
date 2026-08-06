"""Tests for persisted OpenAI-compatible model settings."""

from __future__ import annotations

from pathlib import Path

from refineq.agent.settings import ModelSettings, ModelSettingsRepository


def test_model_settings_round_trip_without_exposing_the_api_key(tmp_path: Path) -> None:
    repository = ModelSettingsRepository(tmp_path)
    saved = repository.save(
        "owner-1",
        ModelSettings(
            base_url="https://models.example.test/v1",
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
    assert (tmp_path / "users" / "owner-1" / "settings" / "model.json").is_file()


def test_model_settings_are_isolated_by_owner(tmp_path: Path) -> None:
    repository = ModelSettingsRepository(tmp_path)
    repository.save(
        "alice",
        ModelSettings(
            base_url="https://models.example.test/v1",
            model="alice-model",
            api_key="alice-secret-1234",
        ),
    )

    assert repository.public("alice").configured is True
    assert repository.public("bob").configured is False
