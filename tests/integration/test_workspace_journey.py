"""API journey for automatically routed and recoverable learning spaces."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event

import pytest
from fastapi.testclient import TestClient

from refineq.agent.settings import ModelSettings
from refineq.api.app import create_app
from refineq.config import Settings
from refineq.learning.service import AnswerRequest, PlanUpdateRequest
from refineq.operations.admin import ensure_admin
from refineq.storage.json_store import RecordNotFoundError
from refineq.workspaces.service import WorkspaceQuotaError, WorkspaceResolveRequest


def _register(client: TestClient) -> tuple[str, str]:
    response = client.post(
        "/auth/register",
        json={
            "email": "workspace-learner@example.com",
            "password": "correct-horse-battery-staple",
            "display_name": "Workspace Learner",
        },
    )
    body = response.json()
    return body["access_token"], body["user"]["id"]


def test_workspace_snapshot_and_refresh_expose_material_gated_next_action(
    tmp_path: Path,
) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))

    with TestClient(app) as client:
        token, _ = _register(client)
        headers = {"Authorization": f"Bearer {token}"}
        workspace_id = client.post(
            "/workspaces/resolve",
            headers=headers,
            json={"intent": "每天 30 分钟复习函数极限"},
        ).json()["workspace"]["id"]

        snapshot = client.get(
            f"/workspaces/{workspace_id}/snapshot",
            params={"timezone_offset_minutes": 480},
            headers=headers,
        )
        refreshed = client.get(
            f"/workspaces/{workspace_id}/next-action",
            params={"timezone_offset_minutes": 480},
            headers=headers,
        )

        assert snapshot.status_code == 200
        assert snapshot.json()["next_action"] == refreshed.json()
        assert refreshed.json()["action_type"] == "upload_material"
        assert refreshed.json()["trigger"] == "material_missing"
        assert refreshed.json()["preconditions"] == {"has_searchable_material": False}

        uploaded = client.post(
            f"/workspaces/{workspace_id}/materials",
            headers=headers,
            files={
                "files": (
                    "limits.txt",
                    b"A limit describes the value a function approaches near an input.",
                    "text/plain",
                )
            },
        )
        assert uploaded.status_code == 201

        ready = client.get(
            f"/workspaces/{workspace_id}/next-action",
            params={"timezone_offset_minutes": 480},
            headers=headers,
        )

    assert ready.status_code == 200
    assert ready.json()["action_type"] != "upload_material"
    assert ready.json()["preconditions"] == {"has_searchable_material": True}


class BlockingRoutingTransport:
    def __init__(self) -> None:
        self.started = Event()
        self.release = Event()
        self.transaction_active: bool | None = None
        self.inspect_transaction = lambda: False

    def complete(self, *, settings, messages, response_model):
        del settings, messages
        self.transaction_active = self.inspect_transaction()
        self.started.set()
        self.release.wait(timeout=3)
        return response_model.model_validate(
            {
                "action": "created",
                "workspace_id": None,
                "title": "Calculus learning",
                "subject": "mathematics",
                "topics": ["limits"],
                "keywords": ["calculus", "limits"],
                "confidence": 0.93,
                "reason": "The learner requested a new calculus capability.",
            }
        )


def test_workspace_routing_model_runs_outside_database_transaction(tmp_path: Path) -> None:
    transport = BlockingRoutingTransport()
    app = create_app(
        Settings(data_root=tmp_path / "data", _env_file=None),
        learning_model_transport=transport,
    )
    transport.inspect_transaction = lambda: app.state.store._active_session.get() is not None

    with TestClient(app) as client:
        token, owner_id = _register(client)
        headers = {"Authorization": f"Bearer {token}"}
        admin = ensure_admin(
            app.state.identity,
            email="routing-transaction-admin@example.com",
            password="correct-horse-battery-staple",
            display_name="Platform Admin",
        ).user
        app.state.model_settings.save(
            admin.id,
            ModelSettings(
                base_url="https://api.openai.com/v1",
                model="routing-model",
                api_key="secret-key",
            ),
        )
        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                pending = executor.submit(
                    client.post,
                    "/workspaces/resolve",
                    headers=headers,
                    json={"intent": "学习函数极限"},
                )
                assert transport.started.wait(timeout=2)
                assert app.state.workspaces.list(owner_id) == []
                transport.release.set()
                response = pending.result(timeout=3)
        finally:
            transport.release.set()

    assert response.status_code == 200
    assert transport.transaction_active is False


def test_workspace_routing_rejects_a_stale_metadata_snapshot(tmp_path: Path) -> None:
    transport = BlockingRoutingTransport()
    app = create_app(
        Settings(data_root=tmp_path / "data", _env_file=None),
        learning_model_transport=transport,
    )

    with TestClient(app) as client:
        token, _ = _register(client)
        headers = {"Authorization": f"Bearer {token}"}
        workspace_id = client.post(
            "/workspaces/resolve",
            headers=headers,
            json={"intent": "学习函数极限"},
        ).json()["workspace"]["id"]
        admin = ensure_admin(
            app.state.identity,
            email="routing-snapshot-admin@example.com",
            password="correct-horse-battery-staple",
            display_name="Platform Admin",
        ).user
        app.state.model_settings.save(
            admin.id,
            ModelSettings(
                base_url="https://api.openai.com/v1",
                model="routing-model",
                api_key="secret-key",
            ),
        )
        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                pending = executor.submit(
                    client.post,
                    "/workspaces/resolve",
                    headers=headers,
                    json={"intent": "继续学习函数极限"},
                )
                assert transport.started.wait(timeout=2)
                renamed = client.patch(
                    f"/workspaces/{workspace_id}",
                    headers=headers,
                    json={"title": "并发更新后的标题"},
                )
                assert renamed.status_code == 200
                transport.release.set()
                response = pending.result(timeout=3)
        finally:
            transport.release.set()

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "workspace_conflict"


def test_concurrent_workspace_resolves_cannot_cross_owner_quota(
    tmp_path: Path, monkeypatch
) -> None:
    app = create_app(
        Settings(data_root=tmp_path / "data", max_workspaces_per_user=1, _env_file=None)
    )
    owner = app.state.identity.register(
        email="workspace-quota@example.com",
        password="correct-horse-battery-staple",
        display_name="Learner",
    )
    original_create = app.state.workspaces.create

    def slow_create(*args, **kwargs):
        time.sleep(0.05)
        return original_create(*args, **kwargs)

    monkeypatch.setattr(app.state.workspaces, "create", slow_create)

    def resolve(intent: str) -> str:
        try:
            return app.state.workspace_service.resolve(
                owner.id,
                WorkspaceResolveRequest(intent=intent),
                now=datetime(2026, 8, 6, tzinfo=UTC),
            ).action
        except WorkspaceQuotaError:
            return "quota"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = sorted(executor.map(resolve, ["学习高等数学", "学习英语语法"]))

    assert outcomes == ["created", "quota"]
    assert len(app.state.workspaces.list(owner.id)) == 1


def test_intents_create_reuse_switch_and_restore_learning_spaces(
    tmp_path: Path,
) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))

    with TestClient(app) as client:
        token, owner_id = _register(client)
        headers = {"Authorization": f"Bearer {token}"}

        first = client.post(
            "/workspaces/resolve",
            headers=headers,
            json={"intent": "我要在两周内复习高数极限"},
        )
        assert first.status_code == 200
        assert first.json()["action"] == "created"
        math_id = first.json()["workspace"]["id"]

        reused = client.post(
            "/workspaces/resolve",
            headers=headers,
            json={"intent": "继续复习高数导数"},
        )
        assert reused.status_code == 200
        assert reused.json()["workspace"]["id"] == math_id
        assert reused.json()["action"] == "reused"

        english = client.post(
            "/workspaces/resolve",
            headers=headers,
            json={"intent": "我要准备英语四级单词"},
        )
        assert english.status_code == 200
        assert english.json()["action"] == "created"
        assert english.json()["workspace"]["id"] != math_id

        upload = client.post(
            f"/workspaces/{math_id}/materials",
            headers=headers,
            files=[
                (
                    "files",
                    (
                        "limits.md",
                        b"A limit is the value approached by a function.",
                        "text/markdown",
                    ),
                )
            ],
        )
        assert upload.status_code == 201

        spaces = client.get("/workspaces", headers=headers)
        assert spaces.status_code == 200
        assert len(spaces.json()) == 2
        assert spaces.json()[0]["title"] == "英语四级"

        snapshot = client.get(f"/workspaces/{math_id}/snapshot", headers=headers)
        assert snapshot.status_code == 200
        body = snapshot.json()
        assert body["workspace"]["id"] == math_id
        assert body["progress"]["workspace_id"] == math_id
        assert "project_id" not in body["progress"]
        assert body["progress"]["goal"] == "我要在两周内复习高数极限"
        assert body["progress"]["stable"] == {
            topic_id: False for topic_id in body["progress"]["mastery"]
        }
        assert body["plan"]["sessions"]
        assert body["materials"][0]["filename"] == "limits.md"


def test_material_topic_suggestions_require_owner_confirmation_and_ignore_body(
    tmp_path: Path,
) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))

    with TestClient(app) as client:
        token, _ = _register(client)
        headers = {"Authorization": f"Bearer {token}"}
        workspace_id = client.post(
            "/workspaces/resolve",
            headers=headers,
            json={"intent": "学习高等数学极限"},
        ).json()["workspace"]["id"]
        before = client.get(f"/workspaces/{workspace_id}/snapshot", headers=headers).json()
        uploaded = client.post(
            f"/workspaces/{workspace_id}/materials",
            headers=headers,
            files=[
                (
                    "files",
                    (
                        "opaque.md",
                        b"SECRET_BODY_TOPIC must never become a learning topic.",
                        "text/markdown",
                    ),
                )
            ],
        ).json()[0]
        updated = client.patch(
            f"/workspaces/{workspace_id}/materials/{uploaded['id']}",
            headers=headers,
            json={"title": "Continuity guide", "tags": ["epsilon-delta"]},
        )
        bob = client.post(
            "/auth/register",
            json={
                "email": "topic-suggestion-bob@example.com",
                "password": "correct-horse-battery-staple",
                "display_name": "Bob",
            },
        ).json()

        suggestions = client.get(
            f"/workspaces/{workspace_id}/topic-suggestions",
            headers=headers,
        )
        forbidden = client.get(
            f"/workspaces/{workspace_id}/topic-suggestions",
            headers={"Authorization": f"Bearer {bob['access_token']}"},
        )
        unchanged = client.get(
            f"/workspaces/{workspace_id}/snapshot",
            headers=headers,
        ).json()

        assert updated.status_code == 200
        assert suggestions.status_code == 200
        by_name = {item["name"]: item for item in suggestions.json()}
        assert {"Continuity guide", "epsilon-delta"} <= set(by_name)
        assert "SECRET_BODY_TOPIC" not in " ".join(by_name)
        assert forbidden.status_code == 404
        assert unchanged["workspace"]["topics"] == before["workspace"]["topics"]
        assert unchanged["progress"]["topics"] == before["progress"]["topics"]

        forbidden_accept = client.post(
            f"/workspaces/{workspace_id}/topic-suggestions/{by_name['epsilon-delta']['id']}/accept",
            headers={"Authorization": f"Bearer {bob['access_token']}"},
        )

        accepted = client.post(
            f"/workspaces/{workspace_id}/topic-suggestions/{by_name['epsilon-delta']['id']}/accept",
            headers=headers,
        )
        replayed = client.post(
            f"/workspaces/{workspace_id}/topic-suggestions/{by_name['epsilon-delta']['id']}/accept",
            headers=headers,
        )

    assert accepted.status_code == 200
    assert replayed.status_code == 200
    assert forbidden_accept.status_code == 404
    accepted_body = accepted.json()
    assert "epsilon-delta" in accepted_body["workspace"]["topics"]
    accepted_topic_id = by_name["epsilon-delta"]["id"]
    assert accepted_body["progress"]["topics"][accepted_topic_id] == "epsilon-delta"
    assert any(
        session["topic_id"] == accepted_topic_id for session in accepted_body["plan"]["sessions"]
    )
    assert all(item["id"] != accepted_topic_id for item in accepted_body["topic_suggestions"])
    assert replayed.json()["workspace"]["topics"].count("epsilon-delta") == 1


def test_material_topic_acceptance_rolls_back_both_records_on_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))
    owner = app.state.identity.register(
        email="topic-rollback@example.com",
        password="correct-horse-battery-staple",
        display_name="Rollback Learner",
    )
    workspace = app.state.workspace_service.resolve(
        owner.id,
        WorkspaceResolveRequest(intent="学习高等数学极限"),
        now=datetime(2026, 8, 8, tzinfo=UTC),
    ).workspace
    app.state.knowledge.add_document(
        owner_id=owner.id,
        project_id=workspace.id,
        material_id="continuity-material",
        filename="continuity.md",
        text="material body",
        content_type="text/markdown",
    )
    app.state.knowledge.update_material_metadata(
        owner_id=owner.id,
        project_id=workspace.id,
        material_id="continuity-material",
        tags=[f"tag-{index}" for index in range(12)],
    )
    suggestions = app.state.workspace_service.topic_suggestions(owner.id, workspace.id)
    suggestion = next(item for item in suggestions if item.name == "continuity.md")
    assert len(suggestions) == 12
    workspace_before = app.state.workspaces.snapshot(owner.id, workspace.id)
    learning_before = app.state.learning.get(owner.id, workspace.id)
    original_add_topic = app.state.workspace_learning_service.add_topic

    def fail_after_learning_write(*args, **kwargs):
        original_add_topic(*args, **kwargs)
        raise RuntimeError("simulated second-record failure")

    monkeypatch.setattr(
        app.state.workspace_learning_service,
        "add_topic",
        fail_after_learning_write,
    )

    with pytest.raises(RuntimeError, match="second-record failure"):
        app.state.workspace_service.accept_topic_suggestion(
            owner.id,
            workspace.id,
            suggestion.id,
            now=datetime(2026, 8, 8, 1, tzinfo=UTC),
        )

    assert (
        app.state.workspaces.get(owner.id, workspace.id).model_dump(mode="json")
        == workspace_before.data
    )
    assert app.state.learning.get(owner.id, workspace.id).data == learning_before.data


def test_workspace_snapshot_is_owner_scoped(tmp_path: Path) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))

    with TestClient(app) as client:
        alice_token, _ = _register(client)
        alice_headers = {"Authorization": f"Bearer {alice_token}"}
        workspace_id = client.post(
            "/workspaces/resolve",
            headers=alice_headers,
            json={"intent": "学习线性代数"},
        ).json()["workspace"]["id"]
        bob = client.post(
            "/auth/register",
            json={
                "email": "another-learner@example.com",
                "password": "correct-horse-battery-staple",
                "display_name": "Another Learner",
            },
        ).json()

        response = client.get(
            f"/workspaces/{workspace_id}/snapshot",
            headers={"Authorization": f"Bearer {bob['access_token']}"},
        )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "workspace_not_found"


def test_natural_language_exam_and_daily_time_shape_the_created_plan(
    tmp_path: Path,
) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))

    with TestClient(app) as client:
        token, _ = _register(client)
        headers = {"Authorization": f"Bearer {token}"}
        created = client.post(
            "/workspaces/resolve",
            headers=headers,
            json={"intent": "Calculus exam in two weeks, study 20 minutes daily"},
        )
        workspace_id = created.json()["workspace"]["id"]
        snapshot = client.get(f"/workspaces/{workspace_id}/snapshot", headers=headers)

    assert created.status_code == 200
    assert snapshot.status_code == 200
    plan = snapshot.json()["plan"]
    assert plan["daily_minutes"] == 20
    assert 13 <= len(plan["sessions"]) <= 14


def test_flexible_capability_goal_uses_a_focused_seven_day_path(tmp_path: Path) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))

    with TestClient(app) as client:
        token, _ = _register(client)
        headers = {"Authorization": f"Bearer {token}"}
        created = client.post(
            "/workspaces/resolve",
            headers=headers,
            json={
                "intent": "Learn product thinking by validating a real user need",
            },
        )
        workspace_id = created.json()["workspace"]["id"]
        snapshot = client.get(f"/workspaces/{workspace_id}/snapshot", headers=headers)

    assert created.status_code == 200
    assert snapshot.status_code == 200
    plan = snapshot.json()["plan"]
    assert len(plan["sessions"]) == 7
    assert [session["activity"] for session in plan["sessions"]] == [
        "learn",
        "practice",
        "apply",
        "review",
        "learn",
        "practice",
        "apply",
    ]


def test_explicit_plan_constraints_override_values_in_intent(tmp_path: Path) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))
    exam_at = datetime.now(UTC) + timedelta(days=4)

    with TestClient(app) as client:
        token, _ = _register(client)
        headers = {"Authorization": f"Bearer {token}"}
        created = client.post(
            "/workspaces/resolve",
            headers=headers,
            json={
                "intent": "Calculus exam in two weeks, study 20 minutes daily",
                "exam_at": exam_at.isoformat(),
                "daily_minutes": 30,
            },
        )
        workspace_id = created.json()["workspace"]["id"]
        plan = client.get(f"/workspaces/{workspace_id}/snapshot", headers=headers).json()["plan"]

    assert plan["daily_minutes"] == 30
    assert 3 <= len(plan["sessions"]) <= 4


def test_invalid_plan_constraints_do_not_persist_an_orphan_workspace(
    tmp_path: Path,
) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))

    with TestClient(app, raise_server_exceptions=False) as client:
        token, _ = _register(client)
        headers = {"Authorization": f"Bearer {token}"}
        response = client.post(
            "/workspaces/resolve",
            headers=headers,
            json={
                "intent": "Prepare calculus",
                "exam_at": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
            },
        )
        workspaces = client.get("/workspaces", headers=headers)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_learning_constraints"
    assert workspaces.json() == []


def test_extreme_plan_horizon_is_rejected_before_persistence(tmp_path: Path) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))

    with TestClient(app, raise_server_exceptions=False) as client:
        token, _ = _register(client)
        headers = {"Authorization": f"Bearer {token}"}
        response = client.post(
            "/workspaces/resolve",
            headers=headers,
            json={"intent": "Prepare calculus", "exam_at": "9999-01-01T00:00:00Z"},
        )
        workspaces = client.get("/workspaces", headers=headers)

    assert response.status_code == 422
    assert workspaces.json() == []


def test_unexpected_provisioning_failure_rolls_back_workspace_and_learning_state(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))

    def fail_seed(*args, **kwargs):
        del args, kwargs
        raise RuntimeError("simulated storage failure")

    monkeypatch.setattr(app.state.workspace_service._learning_service, "seed", fail_seed)
    with TestClient(app, raise_server_exceptions=False) as client:
        token, owner_id = _register(client)
        headers = {"Authorization": f"Bearer {token}"}
        response = client.post(
            "/workspaces/resolve",
            headers=headers,
            json={"intent": "Prepare calculus"},
        )
        workspaces = client.get("/workspaces", headers=headers)

    assert response.status_code == 500
    assert workspaces.json() == []
    learning_dir = tmp_path / "data" / "users" / owner_id / "learning"
    assert not learning_dir.exists() or list(learning_dir.glob("*.json")) == []


def test_workspace_count_quota_rejects_a_new_subject_without_mutation(
    tmp_path: Path,
) -> None:
    app = create_app(
        Settings(data_root=tmp_path / "data", max_workspaces_per_user=1, _env_file=None)
    )

    with TestClient(app) as client:
        token, _ = _register(client)
        headers = {"Authorization": f"Bearer {token}"}
        first = client.post(
            "/workspaces/resolve", headers=headers, json={"intent": "Learn calculus"}
        )
        second = client.post(
            "/workspaces/resolve", headers=headers, json={"intent": "Learn Rust ownership"}
        )
        workspaces = client.get("/workspaces", headers=headers)

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "workspace_quota"
    assert len(workspaces.json()) == 1


def test_unsafe_workspace_identifier_returns_validation_error(tmp_path: Path) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))

    with TestClient(app, raise_server_exceptions=False) as client:
        token, _ = _register(client)
        response = client.get(
            "/workspaces/bad%20identifier/snapshot",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_identifier"


def test_workspace_can_be_renamed_archived_restored_and_deleted(tmp_path: Path) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))

    with TestClient(app) as client:
        token, _ = _register(client)
        headers = {"Authorization": f"Bearer {token}"}
        created = client.post(
            "/workspaces/resolve",
            headers=headers,
            json={"intent": "学习高数极限"},
        ).json()["workspace"]

        renamed = client.patch(
            f"/workspaces/{created['id']}",
            headers=headers,
            json={"title": "高数冲刺", "goal": "七天掌握极限"},
        )
        assert renamed.status_code == 200
        assert renamed.json()["title"] == "高数冲刺"
        assert renamed.json()["goal"] == "七天掌握极限"

        archived = client.patch(
            f"/workspaces/{created['id']}",
            headers=headers,
            json={"archived": True},
        )
        assert archived.status_code == 200
        assert archived.json()["archived"] is True
        assert client.get("/workspaces", headers=headers).json() == []
        archived_list = client.get(
            "/workspaces?include_archived=true",
            headers=headers,
        )
        assert [item["id"] for item in archived_list.json()] == [created["id"]]

        restored = client.patch(
            f"/workspaces/{created['id']}",
            headers=headers,
            json={"archived": False},
        )
        assert restored.status_code == 200
        assert restored.json()["archived"] is False

        deleted = client.delete(f"/workspaces/{created['id']}", headers=headers)
        assert deleted.status_code == 204
        assert client.get("/workspaces", headers=headers).json() == []
        assert (
            client.get(
                f"/workspaces/{created['id']}/snapshot",
                headers=headers,
            ).status_code
            == 404
        )


def test_workspace_lifecycle_is_owner_scoped(tmp_path: Path) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))

    with TestClient(app) as client:
        token, _ = _register(client)
        headers = {"Authorization": f"Bearer {token}"}
        workspace_id = client.post(
            "/workspaces/resolve",
            headers=headers,
            json={"intent": "学习线性代数"},
        ).json()["workspace"]["id"]
        bob = client.post(
            "/auth/register",
            json={
                "email": "workspace-bob@example.com",
                "password": "correct-horse-battery-staple",
                "display_name": "Bob",
            },
        ).json()
        bob_headers = {"Authorization": f"Bearer {bob['access_token']}"}

        updated = client.patch(
            f"/workspaces/{workspace_id}",
            headers=bob_headers,
            json={"title": "stolen"},
        )
        deleted = client.delete(
            f"/workspaces/{workspace_id}",
            headers=bob_headers,
        )

    assert updated.status_code == 404
    assert updated.json()["error"]["code"] == "workspace_not_found"
    assert deleted.status_code == 404
    assert deleted.json()["error"]["code"] == "workspace_not_found"


def test_workspace_plan_sessions_can_be_completed_and_rescheduled(tmp_path: Path) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))

    with TestClient(app) as client:
        token, _ = _register(client)
        headers = {"Authorization": f"Bearer {token}"}
        workspace_id = client.post(
            "/workspaces/resolve",
            headers=headers,
            json={"intent": "准备微积分考试"},
        ).json()["workspace"]["id"]
        original = client.get(
            f"/workspaces/{workspace_id}/snapshot",
            headers=headers,
        ).json()["plan"]
        session = original["sessions"][0]

        completed = client.patch(
            f"/workspaces/{workspace_id}/learning/plan/sessions/{session['id']}",
            headers=headers,
            json={"status": "completed"},
        )
        assert completed.status_code == 200
        assert completed.json()["status"] == "completed"

        tomorrow = datetime.now(UTC) + timedelta(days=1)
        rescheduled = client.patch(
            f"/workspaces/{workspace_id}/learning/plan/sessions/{session['id']}",
            headers=headers,
            json={"status": "planned", "planned_at": tomorrow.isoformat(), "minutes": 30},
        )
        assert rescheduled.status_code == 200
        assert rescheduled.json()["status"] == "planned"
        assert rescheduled.json()["minutes"] == 30
        assert datetime.fromisoformat(rescheduled.json()["planned_at"]) >= tomorrow - timedelta(
            seconds=1
        )

        restored = client.get(
            f"/workspaces/{workspace_id}/snapshot",
            headers=headers,
        ).json()["plan"]["sessions"][0]
        assert restored == rescheduled.json()


def test_workspace_plan_settings_save_without_regeneration_and_regenerate_on_request(
    tmp_path: Path,
) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))
    exam_at = datetime.now(UTC) + timedelta(days=8)

    with TestClient(app) as client:
        token, _ = _register(client)
        headers = {"Authorization": f"Bearer {token}"}
        created = client.post(
            "/workspaces/resolve",
            headers=headers,
            json={
                "intent": "Prepare for a calculus exam covering limits and derivatives",
                "exam_at": exam_at.isoformat(),
                "daily_minutes": 25,
            },
        ).json()["workspace"]
        workspace_id = created["id"]
        snapshot = client.get(
            f"/workspaces/{workspace_id}/snapshot",
            headers=headers,
        ).json()
        original_plan = snapshot["plan"]
        original_sessions = original_plan["sessions"]
        topic_order = list(reversed(list(snapshot["progress"]["topics"])))

        completed = client.patch(
            f"/workspaces/{workspace_id}/learning/plan/sessions/{original_sessions[0]['id']}",
            headers=headers,
            json={"status": "completed"},
        )
        assert completed.status_code == 200

        saved = client.put(
            f"/workspaces/{workspace_id}/learning/plan",
            headers=headers,
            json={
                "goal": "Pass the calculus final with confident problem solving",
                "exam_at": exam_at.isoformat(),
                "daily_minutes": 35,
                "topic_order": topic_order,
                "regenerate": False,
            },
        )
        assert saved.status_code == 200
        assert saved.json()["id"] == original_plan["id"]
        assert [item["id"] for item in saved.json()["sessions"]] == [
            item["id"] for item in original_sessions
        ]
        assert saved.json()["sessions"][0]["status"] == "completed"
        assert saved.json()["goal"] == "Pass the calculus final with confident problem solving"
        assert saved.json()["daily_minutes"] == 35

        regenerated = client.put(
            f"/workspaces/{workspace_id}/learning/plan",
            headers=headers,
            json={
                "goal": "Pass the calculus final with confident problem solving",
                "exam_at": exam_at.isoformat(),
                "daily_minutes": 35,
                "topic_order": topic_order,
                "regenerate": True,
            },
        )
        assert regenerated.status_code == 200
        assert regenerated.json()["id"] != original_plan["id"]
        assert [item["id"] for item in regenerated.json()["sessions"]] != [
            item["id"] for item in original_sessions
        ]
        assert sum(item["status"] == "completed" for item in regenerated.json()["sessions"]) == 1

        restored = client.get(
            f"/workspaces/{workspace_id}/snapshot",
            headers=headers,
        ).json()
        assert restored["workspace"]["goal"] == saved.json()["goal"]
        assert restored["progress"]["goal"] == saved.json()["goal"]
        assert restored["progress"]["topic_order"] == topic_order
        assert restored["plan"] == regenerated.json()

        bob = client.post(
            "/auth/register",
            json={
                "email": "plan-settings-bob@example.com",
                "password": "correct-horse-battery-staple",
                "display_name": "Bob",
            },
        ).json()
        forbidden = client.put(
            f"/workspaces/{workspace_id}/learning/plan",
            headers={"Authorization": f"Bearer {bob['access_token']}"},
            json={
                "goal": "Stolen plan",
                "exam_at": exam_at.isoformat(),
                "daily_minutes": 20,
                "topic_order": topic_order,
                "regenerate": True,
            },
        )

    assert forbidden.status_code == 404


def test_workspace_plan_update_rejects_invalid_topic_membership(tmp_path: Path) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))

    with TestClient(app) as client:
        token, _ = _register(client)
        headers = {"Authorization": f"Bearer {token}"}
        workspace_id = client.post(
            "/workspaces/resolve",
            headers=headers,
            json={"intent": "Prepare calculus"},
        ).json()["workspace"]["id"]
        response = client.put(
            f"/workspaces/{workspace_id}/learning/plan",
            headers=headers,
            json={
                "goal": "Prepare calculus",
                "exam_at": (datetime.now(UTC) + timedelta(days=5)).isoformat(),
                "daily_minutes": 30,
                "topic_order": ["not-a-workspace-topic"],
                "regenerate": True,
            },
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "learning_conflict"


def test_workspace_plan_update_rolls_back_when_goal_sync_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))

    with TestClient(app) as client:
        token, owner_id = _register(client)
        headers = {"Authorization": f"Bearer {token}"}
        workspace_id = client.post(
            "/workspaces/resolve",
            headers=headers,
            json={"intent": "Prepare calculus"},
        ).json()["workspace"]["id"]
        app.state.knowledge.add_document(
            owner_id=owner_id,
            project_id=workspace_id,
            material_id="rollback-material",
            filename="calculus.txt",
            text="Prepare calculus through definitions, examples, and reasoning.",
        )
        question = client.post(
            f"/workspaces/{workspace_id}/learning/question",
            headers=headers,
            json={"request_id": "rollback-question"},
        ).json()
        before = app.state.workspace_service.snapshot(owner_id, workspace_id)
        entered = Event()
        release = Event()

        def fail_update(*args, **kwargs):
            del args, kwargs
            entered.set()
            assert release.wait(timeout=5)
            raise RuntimeError("simulated workspace write failure")

        monkeypatch.setattr(app.state.workspaces, "update", fail_update)
        with ThreadPoolExecutor(max_workers=2) as executor:
            plan_future = executor.submit(
                app.state.workspace_service.update_plan,
                owner_id,
                workspace_id,
                PlanUpdateRequest(
                    goal="A goal that must roll back",
                    exam_at=datetime.now(UTC) + timedelta(days=5),
                    daily_minutes=30,
                    topic_order=list(before.progress.topics),
                    regenerate=True,
                ),
            )
            assert entered.wait(timeout=5)
            answer_future = executor.submit(
                app.state.workspace_learning_service.submit_answer,
                owner_id,
                workspace_id,
                AnswerRequest(
                    attempt_id="rollback-attempt",
                    question_id=question["id"],
                    answer="A complete explanation with a concrete example and reasoning.",
                ),
            )
            time.sleep(0.05)
            assert not answer_future.done()
            release.set()
            with pytest.raises(RuntimeError, match="simulated workspace write failure"):
                plan_future.result(timeout=5)
            answer_future.result(timeout=5)
        after = app.state.workspace_service.snapshot(owner_id, workspace_id)

    assert after.progress.attempt_count == before.progress.attempt_count + 1
    assert len(after.evidence) == len(before.evidence) + 1
    assert after.plan is not None and before.plan is not None
    assert after.plan.id == before.plan.id
    assert {session.id for session in before.plan.sessions}.issubset(
        {session.id for session in after.plan.sessions}
    )
    assert after.workspace == before.workspace


def test_workspace_delete_waits_for_plan_update_and_leaves_no_orphan(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))

    with TestClient(app):
        user = app.state.identity.register(
            email="delete-plan-race@example.com",
            password="correct-horse-battery-staple",
            display_name="Learner",
        )
        workspace = app.state.workspace_service.resolve(
            user.id,
            WorkspaceResolveRequest(intent="Prepare calculus"),
        ).workspace
        before = app.state.workspace_service.snapshot(user.id, workspace.id)
        entered = Event()
        release = Event()

        def fail_update(*args, **kwargs):
            del args, kwargs
            entered.set()
            assert release.wait(timeout=5)
            raise RuntimeError("simulated workspace write failure")

        monkeypatch.setattr(app.state.workspaces, "update", fail_update)
        with ThreadPoolExecutor(max_workers=2) as executor:
            plan_future = executor.submit(
                app.state.workspace_service.update_plan,
                user.id,
                workspace.id,
                PlanUpdateRequest(
                    goal="A concurrent plan update",
                    exam_at=datetime.now(UTC) + timedelta(days=5),
                    daily_minutes=30,
                    topic_order=list(before.progress.topics),
                    regenerate=True,
                ),
            )
            assert entered.wait(timeout=5)
            delete_future = executor.submit(
                app.state.workspace_service.delete,
                user.id,
                workspace.id,
            )
            time.sleep(0.05)
            assert not delete_future.done()
            release.set()
            with pytest.raises(RuntimeError, match="simulated workspace write failure"):
                plan_future.result(timeout=5)
            delete_future.result(timeout=5)

        with pytest.raises(RecordNotFoundError):
            app.state.learning.get(user.id, workspace.id)
        with pytest.raises(RecordNotFoundError):
            app.state.workspaces.get(user.id, workspace.id)


def test_saved_practice_questions_are_durable_and_owner_scoped(tmp_path: Path) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))

    with TestClient(app) as client:
        token, user_id = _register(client)
        headers = {"Authorization": f"Bearer {token}"}
        workspace_id = client.post(
            "/workspaces/resolve",
            headers=headers,
            json={"intent": "准备微积分考试"},
        ).json()["workspace"]["id"]
        app.state.knowledge.add_document(
            owner_id=user_id,
            project_id=workspace_id,
            material_id="saved-question-material",
            filename="calculus.txt",
            text="微积分考试复习资料，包含概念定义、例题与完整推理。",
        )
        question = client.post(
            f"/workspaces/{workspace_id}/learning/question",
            headers=headers,
            json={"request_id": "saved-question-1"},
        ).json()

        saved = client.put(
            f"/workspaces/{workspace_id}/learning/questions/{question['id']}/saved",
            headers=headers,
            json={"saved": True},
        )
        assert saved.status_code == 200
        assert saved.json()["id"] == question["id"]
        assert saved.json()["saved"] is True
        assert saved.json()["saved_at"]
        assert "expected_answer" not in saved.text

        answer = client.post(
            f"/workspaces/{workspace_id}/learning/answer",
            headers=headers,
            json={
                "attempt_id": "saved-attempt",
                "question_id": question["id"],
                "answer": "A detailed explanation with an example that is long enough to grade.",
            },
        )
        assert answer.status_code == 200
        assert answer.json()["next_review_at"]

        listed = client.get(
            f"/workspaces/{workspace_id}/learning/questions/saved",
            headers=headers,
        )
        snapshot = client.get(f"/workspaces/{workspace_id}/snapshot", headers=headers)
        assert [item["id"] for item in listed.json()] == [question["id"]]
        assert snapshot.json()["saved_questions"] == listed.json()
        assert snapshot.json()["active_question"]["id"] == question["id"]
        assert snapshot.json()["active_question"]["prompt"] == question["prompt"]
        assert snapshot.json()["last_answer"]["attempt_id"] == "saved-attempt"
        assert any(
            session["activity"] == "review"
            and session["planned_at"] == answer.json()["next_review_at"]
            for session in snapshot.json()["plan"]["sessions"]
        )

        bob = client.post(
            "/auth/register",
            json={
                "email": "saved-question-bob@example.com",
                "password": "correct-horse-battery-staple",
                "display_name": "Bob",
            },
        ).json()
        forbidden = client.get(
            f"/workspaces/{workspace_id}/learning/questions/saved",
            headers={"Authorization": f"Bearer {bob['access_token']}"},
        )
        unknown = client.put(
            f"/workspaces/{workspace_id}/learning/questions/not-a-question/saved",
            headers=headers,
            json={"saved": True},
        )
        unsaved = client.put(
            f"/workspaces/{workspace_id}/learning/questions/{question['id']}/saved",
            headers=headers,
            json={"saved": False},
        )
        after = client.get(
            f"/workspaces/{workspace_id}/learning/questions/saved",
            headers=headers,
        )

        def prune_answered_question(data: dict) -> dict:
            data["progress"]["question_history"].pop(question["id"], None)
            return data

        app.state.learning.mutate(user_id, workspace_id, prune_answered_question)
        recovered_snapshot = client.get(
            f"/workspaces/{workspace_id}/snapshot",
            headers=headers,
        )
        assert recovered_snapshot.json()["active_question"]["id"] == question["id"]
        assert recovered_snapshot.json()["active_question"]["prompt"] == question["prompt"]

    assert forbidden.status_code == 404
    assert unknown.status_code == 409
    assert unknown.json()["error"]["code"] == "learning_conflict"
    assert unsaved.status_code == 200
    assert unsaved.json()["saved"] is False
    assert unsaved.json()["saved_at"] is None
    assert after.json() == []
