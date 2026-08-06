"""API journey for automatically routed and recoverable learning spaces."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from refineq.api.app import create_app
from refineq.config import Settings


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

        app.state.knowledge.add_document(
            owner_id=owner_id,
            project_id=math_id,
            material_id="limits-notes",
            filename="limits.md",
            text="A limit is the value approached by a function.",
        )

        spaces = client.get("/workspaces", headers=headers)
        assert spaces.status_code == 200
        assert len(spaces.json()) == 2
        assert spaces.json()[0]["title"] == "英语四级"

        snapshot = client.get(f"/workspaces/{math_id}/snapshot", headers=headers)
        assert snapshot.status_code == 200
        body = snapshot.json()
        assert body["workspace"]["id"] == math_id
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

