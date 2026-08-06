"""Integration contract for grounded, persistent project conversations."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from refineq.agent.service import ModelReply
from refineq.api.app import create_app
from refineq.config import Settings


class FakeModelTransport:
    def __init__(self) -> None:
        self.calls: list[list[dict[str, str]]] = []

    def complete(self, *, settings, messages):
        del settings
        self.calls.append(messages)
        return ModelReply(
            text="A derivative is a local rate of change [material-1#0].",
            citations=["material-1#0"],
        )


def _register(client: TestClient, email: str) -> dict[str, str]:
    response = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "correct-horse-battery-staple",
            "display_name": "Learner",
        },
    )
    assert response.status_code == 201
    body = response.json()
    return {"token": body["access_token"], "user_id": body["user"]["id"]}


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_agent_uses_grounded_context_citations_and_persistent_session(
    tmp_path: Path,
) -> None:
    transport = FakeModelTransport()
    app = create_app(
        Settings(data_root=tmp_path / "data", _env_file=None),
        model_transport=transport,
    )

    with TestClient(app) as client:
        user = _register(client, "learner@example.com")
        headers = _headers(user["token"])
        project = client.post(
            "/projects",
            headers=headers,
            json={"name": "Calculus"},
        ).json()
        project_id = project["id"]
        exam_at = datetime.now(UTC) + timedelta(days=3)
        seed = client.post(
            f"/projects/{project_id}/learning/seed",
            headers=headers,
            json={
                "goal": "Pass the calculus final",
                "exam_at": exam_at.isoformat(),
                "daily_minutes": 45,
                "topics": [
                    {
                        "id": "derivatives",
                        "name": "Derivatives",
                        "knowledge_type": "concept",
                    }
                ],
            },
        )
        assert seed.status_code == 200
        assert client.post(
            f"/projects/{project_id}/learning/plan",
            headers=headers,
        ).status_code == 200
        app.state.knowledge.add_document(
            owner_id=user["user_id"],
            project_id=project_id,
            material_id="material-1",
            filename="notes.txt",
            text="A derivative gives the local rate of change of a function.",
        )
        settings_response = client.put(
            "/settings/model",
            headers=headers,
            json={
                "base_url": "https://models.example.test/v1",
                "model": "exam-tutor",
                "api_key": "sk-secret-value-1234",
            },
        )
        assert settings_response.status_code == 200
        assert "sk-secret-value-1234" not in settings_response.text

        first = client.post(
            f"/projects/{project_id}/agent/chat",
            headers=headers,
            json={"message": "What is a derivative?"},
        )
        assert first.status_code == 200
        first_body = first.json()
        assert first_body["citations"] == ["material-1#0"]
        assert first_body["sources"][0]["citation_id"] == "material-1#0"

        second = client.post(
            f"/projects/{project_id}/agent/chat",
            headers=headers,
            json={
                "session_id": first_body["session_id"],
                "message": "Explain that more simply.",
            },
        )

    assert second.status_code == 200
    assert len(transport.calls) == 2
    system_prompt = transport.calls[0][0]["content"]
    assert "Pass the calculus final" in system_prompt
    assert "<untrusted_study_materials>" in system_prompt
    assert "A derivative gives the local rate" in system_prompt
    assert any(
        message["role"] == "assistant" and "local rate" in message["content"]
        for message in transport.calls[1]
    )
    session = app.state.sessions.get(user["user_id"], first_body["session_id"])
    assert len(session.data["messages"]) == 4


def test_agent_without_model_settings_returns_a_stable_error(tmp_path: Path) -> None:
    app = create_app(
        Settings(data_root=tmp_path / "data", _env_file=None),
        model_transport=FakeModelTransport(),
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        user = _register(client, "learner@example.com")
        headers = _headers(user["token"])
        project_id = client.post(
            "/projects",
            headers=headers,
            json={"name": "Calculus"},
        ).json()["id"]
        exam_at = datetime.now(UTC) + timedelta(days=3)
        client.post(
            f"/projects/{project_id}/learning/seed",
            headers=headers,
            json={
                "goal": "Pass the calculus final",
                "exam_at": exam_at.isoformat(),
                "daily_minutes": 45,
                "topics": [{"id": "limits", "name": "Limits"}],
            },
        )

        response = client.post(
            f"/projects/{project_id}/agent/chat",
            headers=headers,
            json={"message": "Help me revise limits."},
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "model_not_configured"


def test_agent_chat_works_through_an_implicit_workspace(tmp_path: Path) -> None:
    transport = FakeModelTransport()
    app = create_app(
        Settings(data_root=tmp_path / "data", _env_file=None),
        model_transport=transport,
    )

    with TestClient(app) as client:
        user = _register(client, "workspace-agent@example.com")
        headers = _headers(user["token"])
        workspace_id = client.post(
            "/workspaces/resolve",
            headers=headers,
            json={"intent": "复习高数导数"},
        ).json()["workspace"]["id"]
        app.state.knowledge.add_document(
            owner_id=user["user_id"],
            project_id=workspace_id,
            material_id="material-1",
            filename="notes.txt",
            text="A derivative gives the local rate of change of a function.",
        )
        client.put(
            "/settings/model",
            headers=headers,
            json={
                "base_url": "https://models.example.test/v1",
                "model": "exam-tutor",
                "api_key": "sk-secret-value-1234",
            },
        )

        response = client.post(
            f"/workspaces/{workspace_id}/agent/chat",
            headers=headers,
            json={"message": "What is a derivative?"},
        )

    assert response.status_code == 200
    assert response.json()["citations"] == ["material-1#0"]
    assert transport.calls
