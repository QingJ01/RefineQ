"""Authenticated API contract for the cross-workspace calendar."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from refineq.api.app import create_app
from refineq.config import Settings


def _register(client: TestClient, email: str) -> tuple[str, str]:
    response = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "correct-horse-battery-staple",
            "display_name": email.split("@", 1)[0],
        },
    )
    assert response.status_code == 201
    body = response.json()
    return body["access_token"], body["user"]["id"]


def _seed_task(
    app,
    *,
    owner_id: str,
    workspace_id: str,
    title: str,
    planned_at: datetime,
    archived: bool = False,
) -> None:
    app.state.workspaces.create(
        owner_id,
        workspace_id,
        title=title,
        subject="subject",
        goal=f"Learn {title}",
        topics=["Topic"],
        keywords=[title],
        routing_summary=f"Route to {title}",
        now=datetime(2026, 7, 1, tzinfo=UTC),
    )
    if archived:
        app.state.workspaces.update(owner_id, workspace_id, archived=True)

    def seed(data: dict) -> dict:
        data["progress"] = {
            "seeded": True,
            "topics": {"topic": f"{title} topic"},
            "plan": {
                "id": f"plan-{workspace_id}",
                "goal": f"Learn {title}",
                "exam_at": (planned_at + timedelta(days=20)).isoformat(),
                "daily_minutes": 45,
                "sessions": [
                    {
                        "id": f"session-{workspace_id}",
                        "topic_id": "topic",
                        "planned_at": planned_at.isoformat(),
                        "minutes": 45,
                        "activity": "apply",
                        "status": "planned",
                    }
                ],
            },
        }
        return data

    app.state.learning.mutate(owner_id, workspace_id, seed)


def test_calendar_requires_authentication_and_never_crosses_owner_scope(
    tmp_path: Path,
) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))
    starts_at = datetime(2026, 8, 1, tzinfo=UTC)
    ends_at = datetime(2026, 9, 1, tzinfo=UTC)

    with TestClient(app) as client:
        alice_token, alice_id = _register(client, "alice-calendar@example.com")
        _, bob_id = _register(client, "bob-calendar@example.com")
        _seed_task(
            app,
            owner_id=alice_id,
            workspace_id="alice-active",
            title="Alice active",
            planned_at=starts_at + timedelta(days=1),
        )
        _seed_task(
            app,
            owner_id=alice_id,
            workspace_id="alice-archived",
            title="Alice archived",
            planned_at=starts_at + timedelta(days=2),
            archived=True,
        )
        _seed_task(
            app,
            owner_id=bob_id,
            workspace_id="bob-private",
            title="Bob private",
            planned_at=starts_at + timedelta(days=3),
        )
        query = {"starts_at": starts_at.isoformat(), "ends_at": ends_at.isoformat()}

        unauthorized = client.get("/calendar", params=query)
        visible = client.get(
            "/calendar",
            params=query,
            headers={"Authorization": f"Bearer {alice_token}"},
        )
        with_archived = client.get(
            "/calendar",
            params={**query, "include_archived": "true"},
            headers={"Authorization": f"Bearer {alice_token}"},
        )

    assert unauthorized.status_code == 401
    assert visible.status_code == 200
    assert [task["workspace_id"] for task in visible.json()["tasks"]] == ["alice-active"]
    assert [task["workspace_id"] for task in with_archived.json()["tasks"]] == [
        "alice-active",
        "alice-archived",
    ]
    assert all(task["workspace_id"] != "bob-private" for task in with_archived.json()["tasks"])


def test_calendar_rejects_naive_reversed_and_excessive_ranges(tmp_path: Path) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))
    with TestClient(app) as client:
        token, _ = _register(client, "range-calendar@example.com")
        headers = {"Authorization": f"Bearer {token}"}
        responses = [
            client.get(
                "/calendar",
                params={
                    "starts_at": "2026-08-01T00:00:00",
                    "ends_at": "2026-09-01T00:00:00Z",
                },
                headers=headers,
            ),
            client.get(
                "/calendar",
                params={
                    "starts_at": "2026-09-01T00:00:00Z",
                    "ends_at": "2026-08-01T00:00:00Z",
                },
                headers=headers,
            ),
            client.get(
                "/calendar",
                params={
                    "starts_at": "2026-01-01T00:00:00Z",
                    "ends_at": "2027-01-07T00:00:00Z",
                },
                headers=headers,
            ),
        ]

    assert [response.status_code for response in responses] == [422, 422, 422]
    assert {
        response.json()["error"]["code"] for response in responses
    } == {"invalid_calendar_range"}
