"""Integration contract for grounded, persistent project conversations."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from refineq.agent.service import ModelReply
from refineq.api.app import create_app
from refineq.config import Settings


class FakeModelTransport:
    def __init__(
        self,
        *,
        text: str = "A derivative is a local rate of change [material-1#0].",
        citations: list[str] | None = None,
    ) -> None:
        self.calls: list[list[dict[str, str]]] = []
        self.text = text
        self.citations = citations or ["material-1#0"]

    def complete(self, *, settings, messages):
        del settings
        self.calls.append(messages)
        return ModelReply(
            text=self.text,
            citations=self.citations,
        )


class FailingModelTransport:
    def complete(self, *, settings, messages):
        del settings, messages
        raise RuntimeError("model unavailable")


class SlowModelTransport(FakeModelTransport):
    def complete(self, *, settings, messages):
        time.sleep(0.05)
        return super().complete(settings=settings, messages=messages)


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
        assert (
            client.post(
                f"/projects/{project_id}/learning/plan",
                headers=headers,
            ).status_code
            == 200
        )
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
                "base_url": "https://api.openai.com/v1",
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


def test_model_settings_reject_endpoint_outside_server_allowlist(tmp_path: Path) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))

    with TestClient(app, raise_server_exceptions=False) as client:
        user = _register(client, "endpoint-policy@example.com")
        response = client.put(
            "/settings/model",
            headers=_headers(user["token"]),
            json={
                "base_url": "https://models.example.com/v1",
                "model": "exam-tutor",
                "api_key": "secret",
            },
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "model_endpoint_not_allowed"


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
                "base_url": "https://api.openai.com/v1",
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
    session = app.state.sessions.get(user["user_id"], response.json()["session_id"])
    assert session.data["workspace_id"] == workspace_id
    assert "project_id" not in session.data


def test_agent_bounds_history_and_removes_unavailable_citation_markers(
    tmp_path: Path,
) -> None:
    transport = FakeModelTransport(
        text="Grounded [material-1#0], invented [missing#99].",
        citations=["material-1#0", "missing#99"],
    )
    app = create_app(
        Settings(data_root=tmp_path / "data", _env_file=None),
        model_transport=transport,
    )

    with TestClient(app) as client:
        user = _register(client, "bounded-agent@example.com")
        headers = _headers(user["token"])
        project_id = client.post("/projects", headers=headers, json={"name": "Calculus"}).json()[
            "id"
        ]
        client.post(
            f"/projects/{project_id}/learning/seed",
            headers=headers,
            json={
                "goal": "Pass calculus",
                "exam_at": (datetime.now(UTC) + timedelta(days=3)).isoformat(),
                "daily_minutes": 45,
                "topics": [{"id": "limits", "name": "Limits"}],
            },
        )
        app.state.knowledge.add_document(
            owner_id=user["user_id"],
            project_id=project_id,
            material_id="material-1",
            filename="notes.txt",
            text="Limits describe function behavior near an input.",
        )
        client.put(
            "/settings/model",
            headers=headers,
            json={
                "base_url": "https://api.openai.com/v1",
                "model": "exam-tutor",
                "api_key": "secret",
            },
        )
        first = client.post(
            f"/projects/{project_id}/agent/chat",
            headers=headers,
            json={"message": "Explain limits"},
        )
        session_id = first.json()["session_id"]

        def add_oversized_history(data):
            data["messages"] = [
                {"role": "user" if index % 2 == 0 else "assistant", "content": "x" * 5_000}
                for index in range(30)
            ]
            return data

        app.state.sessions.mutate(user["user_id"], session_id, add_oversized_history)
        response = client.post(
            f"/projects/{project_id}/agent/chat",
            headers=headers,
            json={"session_id": session_id, "message": "Explain limits again"},
        )

    assert response.status_code == 200
    assert response.json()["citations"] == ["material-1#0"]
    assert "[missing#99]" not in response.json()["message"]
    sent_history = transport.calls[-1][1:-1]
    assert len(sent_history) <= 20
    assert sum(len(message["content"]) for message in sent_history) <= 40_000
    persisted = app.state.sessions.get(user["user_id"], session_id)
    assert len(persisted.data["messages"]) <= 20


def test_agent_session_count_quota_prevents_unbounded_session_files(tmp_path: Path) -> None:
    app = create_app(
        Settings(
            data_root=tmp_path / "data",
            max_agent_sessions_per_user=1,
            _env_file=None,
        ),
        model_transport=FakeModelTransport(),
    )

    with TestClient(app) as client:
        user = _register(client, "session-quota@example.com")
        headers = _headers(user["token"])
        project_id = client.post("/projects", headers=headers, json={"name": "Calculus"}).json()[
            "id"
        ]
        client.post(
            f"/projects/{project_id}/learning/seed",
            headers=headers,
            json={
                "goal": "Pass calculus",
                "exam_at": (datetime.now(UTC) + timedelta(days=3)).isoformat(),
                "daily_minutes": 45,
                "topics": [{"id": "limits", "name": "Limits"}],
            },
        )
        client.put(
            "/settings/model",
            headers=headers,
            json={
                "base_url": "https://api.openai.com/v1",
                "model": "exam-tutor",
                "api_key": "secret",
            },
        )

        first = client.post(
            f"/projects/{project_id}/agent/chat",
            headers=headers,
            json={"message": "First session"},
        )
        second = client.post(
            f"/projects/{project_id}/agent/chat",
            headers=headers,
            json={"message": "Second session"},
        )

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "agent_session_limit"


def test_failed_first_agent_call_does_not_persist_an_empty_session(tmp_path: Path) -> None:
    app = create_app(
        Settings(data_root=tmp_path / "data", _env_file=None),
        model_transport=FailingModelTransport(),
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        user = _register(client, "failed-session@example.com")
        headers = _headers(user["token"])
        project_id = client.post("/projects", headers=headers, json={"name": "Calculus"}).json()[
            "id"
        ]
        client.post(
            f"/projects/{project_id}/learning/seed",
            headers=headers,
            json={
                "goal": "Pass calculus",
                "exam_at": (datetime.now(UTC) + timedelta(days=3)).isoformat(),
                "daily_minutes": 45,
                "topics": [{"id": "limits", "name": "Limits"}],
            },
        )
        client.put(
            "/settings/model",
            headers=headers,
            json={
                "base_url": "https://api.openai.com/v1",
                "model": "exam-tutor",
                "api_key": "secret",
            },
        )
        response = client.post(
            f"/projects/{project_id}/agent/chat",
            headers=headers,
            json={"message": "Explain limits"},
        )

    assert response.status_code == 500
    assert app.state.sessions.count(user["user_id"]) == 0


def test_concurrent_first_agent_calls_cannot_cross_session_quota(tmp_path: Path) -> None:
    app = create_app(
        Settings(
            data_root=tmp_path / "data",
            max_agent_sessions_per_user=1,
            mutation_rate_limit_requests=100,
            _env_file=None,
        ),
        model_transport=SlowModelTransport(),
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        user = _register(client, "concurrent-session@example.com")
        headers = _headers(user["token"])
        project_id = client.post("/projects", headers=headers, json={"name": "Calculus"}).json()[
            "id"
        ]
        client.post(
            f"/projects/{project_id}/learning/seed",
            headers=headers,
            json={
                "goal": "Pass calculus",
                "exam_at": (datetime.now(UTC) + timedelta(days=3)).isoformat(),
                "daily_minutes": 45,
                "topics": [{"id": "limits", "name": "Limits"}],
            },
        )
        client.put(
            "/settings/model",
            headers=headers,
            json={
                "base_url": "https://api.openai.com/v1",
                "model": "exam-tutor",
                "api_key": "secret",
            },
        )

        def chat(index: int) -> int:
            return client.post(
                f"/projects/{project_id}/agent/chat",
                headers=headers,
                json={"message": f"Explain limits {index}"},
            ).status_code

        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = sorted(executor.map(chat, range(2)))

    assert statuses == [200, 409]
    assert app.state.sessions.count(user["user_id"]) == 1


def test_concurrent_retry_of_the_same_agent_turn_is_idempotent(tmp_path: Path) -> None:
    transport = SlowModelTransport()
    app = create_app(
        Settings(
            data_root=tmp_path / "data",
            mutation_rate_limit_requests=100,
            _env_file=None,
        ),
        model_transport=transport,
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        user = _register(client, "idempotent-turn@example.com")
        headers = _headers(user["token"])
        project_id = client.post("/projects", headers=headers, json={"name": "Calculus"}).json()[
            "id"
        ]
        client.post(
            f"/projects/{project_id}/learning/seed",
            headers=headers,
            json={
                "goal": "Pass calculus",
                "exam_at": (datetime.now(UTC) + timedelta(days=3)).isoformat(),
                "daily_minutes": 45,
                "topics": [{"id": "limits", "name": "Limits"}],
            },
        )
        client.put(
            "/settings/model",
            headers=headers,
            json={
                "base_url": "https://api.openai.com/v1",
                "model": "exam-tutor",
                "api_key": "secret",
            },
        )
        payload = {
            "session_id": "stable-session",
            "turn_id": "stable-turn",
            "message": "Explain limits",
        }

        def chat() -> tuple[int, dict]:
            response = client.post(
                f"/projects/{project_id}/agent/chat",
                headers=headers,
                json=payload,
            )
            return response.status_code, response.json()

        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(executor.map(lambda _: chat(), range(2)))

    assert [status for status, _ in responses] == [200, 200]
    assert responses[0][1] == responses[1][1]
    assert len(transport.calls) == 1
    session = app.state.sessions.get(user["user_id"], "stable-session")
    assert len(session.data["messages"]) == 2
    assert session.data["turns"]["stable-turn"]["message"] == responses[0][1]["message"]
