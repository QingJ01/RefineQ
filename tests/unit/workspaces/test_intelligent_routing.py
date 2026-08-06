"""AI-assisted workspace routing with deterministic safety fallback."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from refineq.agent.settings import ModelSettings, ModelSettingsRepository
from refineq.workspaces.intelligence import WorkspaceRoutingIntelligence
from refineq.workspaces.models import LearningWorkspace

NOW = datetime(2026, 8, 6, 4, 0, tzinfo=UTC)


def _workspace(workspace_id: str, subject: str) -> LearningWorkspace:
    return LearningWorkspace(
        id=workspace_id,
        title=f"{subject} learning",
        subject=subject,
        goal=f"Learn {subject}",
        topics=[subject],
        keywords=[subject],
        routing_summary="test fixture",
        created_at=NOW,
        last_active_at=NOW,
    )


class RoutingTransport:
    def __init__(self, workspace_id: str) -> None:
        self.workspace_id = workspace_id
        self.calls = 0

    def complete(self, *, settings, messages, response_model):
        del settings, messages
        self.calls += 1
        return response_model.model_validate(
            {
                "action": "reused",
                "workspace_id": self.workspace_id,
                "title": "Calculus learning",
                "subject": "mathematics",
                "topics": ["limits"],
                "keywords": ["calculus", "limits"],
                "confidence": 0.94,
                "reason": "The intent continues the learner's calculus preparation.",
            }
        )


def _settings(tmp_path: Path, *, configured: bool) -> ModelSettingsRepository:
    repository = ModelSettingsRepository(tmp_path)
    if configured:
        repository.save(
            "owner",
            ModelSettings(
                base_url="https://api.openai.com/v1",
                model="routing-model",
                api_key="secret-key",
            ),
        )
    return repository


def test_configured_model_can_select_a_valid_existing_workspace(tmp_path: Path) -> None:
    transport = RoutingTransport("math")
    router = WorkspaceRoutingIntelligence(_settings(tmp_path, configured=True), transport)
    spaces = [_workspace("english", "language"), _workspace("math", "mathematics")]

    decision = router.route("I need to revisit epsilon-delta proofs", "owner", spaces)

    assert decision.workspace_id == "math"
    assert decision.action == "reused"
    assert decision.confidence == 0.94
    assert transport.calls == 1


def test_invented_workspace_id_falls_back_to_safe_routing(tmp_path: Path) -> None:
    transport = RoutingTransport("invented")
    router = WorkspaceRoutingIntelligence(_settings(tmp_path, configured=True), transport)
    spaces = [_workspace("math", "mathematics")]

    decision = router.route("Continue mathematics", "owner", spaces)

    assert decision.workspace_id != "invented"
    assert transport.calls == 1


def test_unconfigured_model_uses_fallback_without_transport_call(tmp_path: Path) -> None:
    transport = RoutingTransport("math")
    router = WorkspaceRoutingIntelligence(_settings(tmp_path, configured=False), transport)

    decision = router.route("Learn Rust ownership", "owner", [])

    assert decision.action == "created"
    assert decision.subject == "programming"
    assert transport.calls == 0
