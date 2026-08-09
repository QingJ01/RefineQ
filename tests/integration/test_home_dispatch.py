from pathlib import Path

from fastapi.testclient import TestClient

from refineq.agent.settings import ModelSettings
from refineq.api.app import create_app
from refineq.config import Settings
from refineq.operations.admin import ensure_admin


class HomeTransport:
    def __init__(self) -> None:
        self.calls = []

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        name = kwargs["response_model"].__name__
        if name == "WorkspaceRoutingDecision":
            return kwargs["response_model"].model_validate(
                {
                    "action": "created",
                    "workspace_id": None,
                    "title": "高数期末",
                    "subject": "mathematics",
                    "topics": ["极限"],
                    "keywords": ["高数", "极限"],
                    "confidence": 0.95,
                    "reason": "新的长期目标",
                }
            )
        if name == "HomeAnswerDraft":
            return kwargs["response_model"].model_validate(
                {
                    "content": "边际效用是多消费一单位商品带来的额外效用。",
                    "basis": "general_knowledge",
                    "convertible_goal": "理解边际效用及常见例子",
                }
            )
        return kwargs["response_model"].model_validate(
            {
                "kind": "direct_answer",
                "workspace_id": None,
                "reason": "一次性概念解释",
                "confidence": 0.9,
            }
        )


def app_with_model(tmp_path: Path):
    transport = HomeTransport()
    app = create_app(
        Settings(data_root=tmp_path / "data", _env_file=None),
        learning_model_transport=transport,
        home_classifier_transport=transport,
        home_answer_transport=transport,
    )
    admin = ensure_admin(
        app.state.identity,
        email="admin@example.com",
        password="correct-horse-battery-staple",
        display_name="Admin",
    ).user
    app.state.model_settings.save(
        admin.id,
        ModelSettings(
            base_url="https://api.openai.com/v1",
            model="test",
            api_key="secret",
        ),
    )
    return app, transport


def register(client: TestClient, email: str = "learner@example.com") -> dict:
    response = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "correct-horse-battery-staple",
            "display_name": "Learner",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_direct_answer_does_not_mutate_learning_domains(tmp_path: Path) -> None:
    app, transport = app_with_model(tmp_path)
    with TestClient(app) as client:
        auth = register(client)
        headers = {"Authorization": f"Bearer {auth['access_token']}"}
        owner = auth["user"]["id"]
        before = {
            collection: app.state.store.list(owner, collection)
            for collection in ("workspaces", "learning", "sessions", "journey_events")
        }
        response = client.post(
            "/home/dispatch",
            headers=headers,
            json={"request_id": "direct-1", "text": "解释一下边际效用是什么"},
        )
        after = {
            collection: app.state.store.list(owner, collection)
            for collection in before
        }
    assert response.status_code == 200, response.json()
    assert response.json()["kind"] == "direct_answer"
    assert before == after
    assert len(app.state.home_events.list(owner)) == 1
    answer_call = next(
        call
        for call in transport.calls
        if call["response_model"].__name__ == "HomeAnswerDraft"
    )
    assert "workspaces" not in str(answer_call["messages"])


def test_strong_signal_creates_and_routes_without_preview(tmp_path: Path) -> None:
    app, _ = app_with_model(tmp_path)
    with TestClient(app) as client:
        auth = register(client)
        headers = {"Authorization": f"Bearer {auth['access_token']}"}
        response = client.post(
            "/home/dispatch",
            headers=headers,
            json={
                "request_id": "strong-1",
                "text": "我要准备9月1日的高数考试，每天45分钟",
                "timezone_offset_minutes": 480,
            },
        )
        workspaces = client.get("/workspaces", headers=headers).json()
    assert response.status_code == 200, response.json()
    assert response.json()["kind"] == "open_workspace"
    assert response.json()["workspace_target"]["auto_navigate"] is True
    assert len(workspaces) == 1


def test_ambiguous_signal_requires_confirmation_and_is_idempotent(tmp_path: Path) -> None:
    app, _ = app_with_model(tmp_path)
    with TestClient(app) as client:
        auth = register(client)
        headers = {"Authorization": f"Bearer {auth['access_token']}"}
        proposed = client.post(
            "/home/dispatch",
            headers=headers,
            json={"request_id": "proposal-1", "text": "我想系统学习高数"},
        )
        proposal = proposed.json()["workspace_proposal"]
        assert client.get("/workspaces", headers=headers).json() == []
        confirmation = {
            "request_id": "proposal-1",
            "confirmation_token": proposal["confirmation_token"],
            "proposal": proposal,
            "idempotency_key": proposal["idempotency_key"],
        }
        first = client.post("/home/actions/confirm", headers=headers, json=confirmation)
        replay = client.post("/home/actions/confirm", headers=headers, json=confirmation)
        workspaces = client.get("/workspaces", headers=headers).json()
    assert proposed.status_code == 200, proposed.json()
    assert proposed.json()["kind"] == "propose_workspace"
    assert first.status_code == 200, first.json()
    assert replay.status_code == 200, replay.json()
    assert replay.json()["replayed"] is True
    assert len(workspaces) == 1


def test_confirmation_token_is_owner_bound(tmp_path: Path) -> None:
    app, _ = app_with_model(tmp_path)
    with TestClient(app) as client:
        first_auth = register(client, "first@example.com")
        second_auth = register(client, "second@example.com")
        first_headers = {"Authorization": f"Bearer {first_auth['access_token']}"}
        second_headers = {"Authorization": f"Bearer {second_auth['access_token']}"}
        proposed = client.post(
            "/home/dispatch",
            headers=first_headers,
            json={"request_id": "owner-bound", "text": "我想系统学习高数"},
        ).json()["workspace_proposal"]
        response = client.post(
            "/home/actions/confirm",
            headers=second_headers,
            json={
                "request_id": "owner-bound",
                "confirmation_token": proposed["confirmation_token"],
                "proposal": proposed,
                "idempotency_key": proposed["idempotency_key"],
            },
        )
    assert response.status_code == 422


def test_unconfigured_model_keeps_a_recoverable_learner_path(tmp_path: Path) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))
    with TestClient(app) as client:
        auth = register(client)
        response = client.post(
            "/home/dispatch",
            headers={"Authorization": f"Bearer {auth['access_token']}"},
            json={"request_id": "no-model", "text": "解释一下边际效用是什么"},
        )
    assert response.status_code == 200
    assert response.json()["kind"] == "out_of_scope"
    assert "学习空间" in response.json()["limitations"][0]


def test_dispatch_rejects_oversized_text_and_requires_auth(tmp_path: Path) -> None:
    app, _ = app_with_model(tmp_path)
    with TestClient(app) as client:
        unauthorized = client.post(
            "/home/dispatch", json={"request_id": "x", "text": "解释边际效用"}
        )
        auth = register(client)
        oversized = client.post(
            "/home/dispatch",
            headers={"Authorization": f"Bearer {auth['access_token']}"},
            json={"request_id": "x", "text": "x" * 12_001},
        )
    assert unauthorized.status_code == 401
    assert oversized.status_code == 422
