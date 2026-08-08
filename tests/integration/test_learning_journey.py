"""End-to-end API contract for one evidence-driven learning journey."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from refineq.api.app import create_app
from refineq.config import Settings


def _register(client: TestClient, email: str) -> dict[str, str]:
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
    return {
        "token": body["access_token"],
        "user_id": body["user"]["id"],
    }


def _authorization(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_complete_learning_journey_is_owner_scoped_and_idempotent(
    tmp_path: Path,
) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))
    exam_at = datetime.now(UTC) + timedelta(days=4)

    with TestClient(app) as client:
        alice = _register(client, "alice@example.com")
        bob = _register(client, "bob@example.com")
        alice_headers = _authorization(alice["token"])
        bob_headers = _authorization(bob["token"])

        project_response = client.post(
            "/projects",
            headers=alice_headers,
            json={"name": "Calculus final"},
        )
        assert project_response.status_code == 201
        project = project_response.json()
        project_id = project["id"]

        seeded = client.post(
            f"/projects/{project_id}/learning/seed",
            headers=alice_headers,
            json={
                "goal": "Pass the calculus final",
                "exam_at": exam_at.isoformat(),
                "daily_minutes": 45,
                "topics": [
                    {
                        "id": "chain-rule",
                        "name": "Chain Rule",
                        "knowledge_type": "procedure",
                    }
                ],
            },
        )
        assert seeded.status_code == 200

        diagnostic = client.post(
            f"/projects/{project_id}/learning/diagnostic",
            headers=alice_headers,
            json={"results": [{"topic_id": "chain-rule", "is_correct": False}]},
        )
        assert diagnostic.status_code == 200
        assert diagnostic.json()["diagnostic_count"] == 1

        plan = client.post(
            f"/projects/{project_id}/learning/plan",
            headers=alice_headers,
        )
        assert plan.status_code == 200
        assert len(plan.json()["sessions"]) == 4

        question_response = client.post(
            f"/projects/{project_id}/learning/question",
            headers=alice_headers,
            json={"request_id": "journey-question-1"},
        )
        assert question_response.status_code == 200
        question = question_response.json()
        assert question["topic_id"] == "chain-rule"
        assert "expected_answer" not in question

        raw_learning = app.state.learning.get(alice["user_id"], project_id)
        assert raw_learning.data["progress"]["pending_question"]["expected_answer"]

        answer_payload = {
            "attempt_id": "attempt-1",
            "question_id": question["id"],
            "answer": "The Chain Rule",
        }
        answer = client.post(
            f"/projects/{project_id}/learning/answer",
            headers=alice_headers,
            json=answer_payload,
        )
        assert answer.status_code == 200
        assert answer.json()["is_correct"] is False
        assert answer.json()["mastery_updated"] is False
        assert answer.json()["replayed"] is False

        replay = client.post(
            f"/projects/{project_id}/learning/answer",
            headers=alice_headers,
            json={**answer_payload, "answer": "a deliberately different answer"},
        )
        assert replay.status_code == 200
        assert replay.json()["is_correct"] is False
        assert replay.json()["replayed"] is True

        progress = client.get(
            f"/projects/{project_id}/learning/progress",
            headers=alice_headers,
        )
        evidence = client.get(
            f"/projects/{project_id}/learning/evidence",
            headers=alice_headers,
        )
        assert progress.status_code == 200
        assert progress.json()["attempt_count"] == 1
        assert progress.json()["mastery"]["chain-rule"] > 0.0
        assert progress.json()["topics"] == {"chain-rule": "Chain Rule"}
        assert evidence.status_code == 200
        assert {item["kind"] for item in evidence.json()} == {"attempt", "diagnostic"}
        attempt_evidence = next(item for item in evidence.json() if item["kind"] == "attempt")
        assert "Chain Rule" in attempt_evidence["summary"]
        assert "chain-rule" not in attempt_evidence["summary"]

        forbidden = client.get(
            f"/projects/{project_id}/learning/progress",
            headers=bob_headers,
        )
        assert forbidden.status_code == 404
        assert forbidden.json()["error"]["code"] == "project_not_found"


def test_owner_identity_is_rejected_from_request_json(tmp_path: Path) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))

    with TestClient(app) as client:
        user = _register(client, "learner@example.com")
        response = client.post(
            "/projects",
            headers=_authorization(user["token"]),
            json={"name": "Calculus", "owner_id": "someone-else"},
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
