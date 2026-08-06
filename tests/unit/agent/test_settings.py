"""Tests for persisted OpenAI-compatible model settings."""

from __future__ import annotations

from pathlib import Path

from refineq.agent.settings import ModelSettings, ModelSettingsRepository


def test_model_settings_round_trip_without_exposing_the_api_key(tmp_path: Path) -> None:
    repository = ModelSettingsRepository(tmp_path)
    saved = repository.save(
        ModelSettings(
            base_url="https://models.example.test/v1",
            model="exam-tutor",
            api_key="sk-secret-value-1234",
        )
    )

    loaded = repository.load()
    public = repository.public()

    assert saved.model == "exam-tutor"
    assert loaded.api_key.get_secret_value() == "sk-secret-value-1234"
    assert public.configured is True
    assert public.api_key_hint.endswith("1234")
    assert "sk-secret-value-1234" not in public.model_dump_json()
    assert (tmp_path / "system" / "model.json").is_file()
