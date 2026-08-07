"""API journey for automatically routed and recoverable learning spaces."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from refineq.api.app import create_app
from refineq.config import Settings
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
        assert body["plan"]["sessions"]
        assert body["materials"][0]["filename"] == "limits.md"


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
        assert client.get(
            f"/workspaces/{created['id']}/snapshot",
            headers=headers,
        ).status_code == 404


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
            json={"status": "planned", "planned_at": tomorrow.isoformat()},
        )
        assert rescheduled.status_code == 200
        assert rescheduled.json()["status"] == "planned"
        assert datetime.fromisoformat(rescheduled.json()["planned_at"]) >= tomorrow - timedelta(
            seconds=1
        )

        restored = client.get(
            f"/workspaces/{workspace_id}/snapshot",
            headers=headers,
        ).json()["plan"]["sessions"][0]
        assert restored == rescheduled.json()
