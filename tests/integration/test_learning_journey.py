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


def test_workspace_question_requires_an_indexed_material(tmp_path: Path) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))

    with TestClient(app) as client:
        learner = _register(client, "material-gate@example.com")
        headers = _authorization(learner["token"])
        workspace_id = client.post(
            "/workspaces/resolve",
            headers=headers,
            json={"intent": "Study function limits"},
        ).json()["workspace"]["id"]
        assert (
            client.get(f"/workspaces/{workspace_id}/snapshot", headers=headers).status_code == 200
        )

        blocked = client.post(
            f"/workspaces/{workspace_id}/learning/question",
            headers=headers,
            json={"request_id": "question-without-material"},
        )

        assert blocked.status_code == 409
        assert blocked.json()["error"]["code"] == "material_required"
        record = app.state.learning.get(learner["user_id"], workspace_id)
        assert record.data["progress"]["pending_question"] is None

        uploaded = client.post(
            f"/workspaces/{workspace_id}/materials",
            headers=headers,
            files={
                "files": (
                    "limits.txt",
                    (
                        b"Study function limits. A limit is the value a function approaches "
                        b"as its input approaches a point."
                    ),
                    "text/plain",
                )
            },
        )
        assert uploaded.status_code == 201

        created = client.post(
            f"/workspaces/{workspace_id}/learning/question",
            headers=headers,
            json={"request_id": "question-with-material"},
        )

        graded = client.post(
            f"/workspaces/{workspace_id}/learning/answer",
            headers=headers,
            json={
                "attempt_id": "material-gate-attempt",
                "question_id": created.json()["id"],
                "answer": (
                    "A limit describes the value approached by a function, with a concrete example."
                ),
            },
        )
        shown = client.post(
            f"/workspaces/{workspace_id}/learning/attempts/material-gate-attempt/shown",
            headers=headers,
        )
        version_after_shown = app.state.learning.get(learner["user_id"], workspace_id).version
        shown_replay = client.post(
            f"/workspaces/{workspace_id}/learning/attempts/material-gate-attempt/shown",
            headers=headers,
        )
        stored = app.state.learning.get(learner["user_id"], workspace_id)

    assert created.status_code == 200
    assert created.json()["grounding"] == "material"
    assert created.json()["sources"]
    assert graded.status_code == 200
    assert shown.status_code == 200
    assert shown.json() == shown_replay.json()
    assert stored.version == version_after_shown
    names = [
        event.name for event in app.state.journey_events.list(learner["user_id"], workspace_id)
    ]
    assert {
        "intent_submitted",
        "workspace_ready",
        "workspace_opened",
        "material_searchable",
        "question_started",
        "grounded_grade_created",
        "grounded_grade_shown",
    }.issubset(names)
    assert names.count("grounded_grade_shown") == 1


def test_workspace_question_rejects_indexed_but_irrelevant_material(
    tmp_path: Path,
) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))

    with TestClient(app) as client:
        learner = _register(client, "irrelevant-material@example.com")
        headers = _authorization(learner["token"])
        workspace_id = client.post(
            "/workspaces/resolve",
            headers=headers,
            json={"intent": "Study function limits"},
        ).json()["workspace"]["id"]
        uploaded = client.post(
            f"/workspaces/{workspace_id}/materials",
            headers=headers,
            files={
                "files": (
                    "botany.txt",
                    b"Photosynthesis uses chlorophyll and sunlight to produce glucose.",
                    "text/plain",
                )
            },
        )
        created = client.post(
            f"/workspaces/{workspace_id}/learning/question",
            headers=headers,
            json={"request_id": "irrelevant-source"},
        )

    assert uploaded.status_code == 201
    assert created.status_code == 409
    assert created.json()["error"]["code"] == "material_insufficient"
    assert (
        app.state.learning.get(learner["user_id"], workspace_id).data["progress"][
            "pending_question"
        ]
        is None
    )


def test_workspace_hides_and_rejects_a_legacy_general_pending_question(
    tmp_path: Path,
) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))

    with TestClient(app) as client:
        learner = _register(client, "legacy-general-pending@example.com")
        headers = _authorization(learner["token"])
        workspace_id = client.post(
            "/workspaces/resolve",
            headers=headers,
            json={"intent": "Study function limits"},
        ).json()["workspace"]["id"]
        legacy = app.state.workspace_learning_service.next_question(
            learner["user_id"],
            workspace_id,
            request_id="legacy-general-request",
        )

        rejected = client.post(
            f"/workspaces/{workspace_id}/learning/answer",
            headers=headers,
            json={
                "attempt_id": "legacy-general-attempt",
                "question_id": legacy.id,
                "answer": "A generic answer that must not be graded.",
            },
        )
        snapshot = client.get(
            f"/workspaces/{workspace_id}/snapshot",
            headers=headers,
        )
        retry = client.post(
            f"/workspaces/{workspace_id}/learning/questions/{legacy.id}/retry",
            headers=headers,
        )

    assert legacy.grounding.value == "general"
    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "material_insufficient"
    assert snapshot.status_code == 200
    assert snapshot.json()["active_question"] is None
    assert retry.status_code == 409
    assert retry.json()["error"]["code"] == "material_insufficient"
    record = app.state.learning.get(learner["user_id"], workspace_id)
    assert record.data["progress"]["pending_question"] is None
    assert "legacy-general-attempt" not in record.data["attempts"]


def test_workspace_replaces_legacy_general_request_with_a_grounded_question(
    tmp_path: Path,
) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))

    with TestClient(app) as client:
        learner = _register(client, "legacy-general-replacement@example.com")
        headers = _authorization(learner["token"])
        workspace = client.post(
            "/workspaces/resolve",
            headers=headers,
            json={"intent": "Study function limits"},
        ).json()["workspace"]
        workspace_id = workspace["id"]
        legacy = app.state.workspace_learning_service.next_question(
            learner["user_id"],
            workspace_id,
            request_id="legacy-reused-request",
        )
        topic = workspace["topics"][0]
        uploaded = client.post(
            f"/workspaces/{workspace_id}/materials",
            headers=headers,
            files={
                "files": (
                    "relevant.txt",
                    f"{topic} is explained in this study source with examples.".encode(),
                    "text/plain",
                )
            },
        )

        replacement = client.post(
            f"/workspaces/{workspace_id}/learning/question",
            headers=headers,
            json={"request_id": "legacy-reused-request"},
        )
        replay = client.post(
            f"/workspaces/{workspace_id}/learning/question",
            headers=headers,
            json={"request_id": "legacy-reused-request"},
        )

    assert legacy.grounding.value == "general"
    assert uploaded.status_code == 201
    assert replacement.status_code == 200, replacement.json()
    assert replacement.json()["id"] != legacy.id
    assert replacement.json()["grounding"] == "material"
    assert replacement.json()["sources"]
    assert replay.json()["id"] == replacement.json()["id"]


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
        assert question["grounding"] == "general"
        assert question["sources"] == []
        assert "expected_answer" not in question

        raw_learning = app.state.learning.get(alice["user_id"], project_id)
        assert raw_learning.data["progress"]["pending_question"]["expected_answer"] == ""

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
        assert answer.json()["grounding"] == "general"
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


def test_plan_sessions_control_practice_mode_and_complete_only_on_evidence(
    tmp_path: Path,
) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))
    exam_at = datetime.now(UTC) + timedelta(days=5)

    with TestClient(app) as client:
        learner = _register(client, "plan-loop@example.com")
        headers = _authorization(learner["token"])
        project_id = client.post(
            "/projects",
            headers=headers,
            json={"name": "Systems"},
        ).json()["id"]
        client.post(
            f"/projects/{project_id}/learning/seed",
            headers=headers,
            json={
                "goal": "Understand cache coherence",
                "exam_at": exam_at.isoformat(),
                "daily_minutes": 30,
                "topics": [{"id": "cache", "name": "Cache coherence"}],
            },
        )
        plan = client.post(
            f"/projects/{project_id}/learning/plan",
            headers=headers,
        ).json()
        app.state.knowledge.add_document(
            owner_id=learner["user_id"],
            project_id=project_id,
            material_id="cache-notes",
            filename="cache.txt",
            text=(
                "A cache coherence protocol keeps processor copies consistent by "
                "invalidating stale copies after writes and measuring propagation latency."
            ),
        )
        sessions = {session["activity"]: session for session in plan["sessions"][:4]}
        expected_modes = {
            "learn": "concept",
            "practice": "case",
            "apply": "project",
            "review": "exam",
        }

        for activity, expected_mode in expected_modes.items():
            question = client.post(
                f"/projects/{project_id}/learning/question",
                headers=headers,
                json={
                    "request_id": f"plan-mode-{activity}",
                    "plan_session_id": sessions[activity]["id"],
                    "mode": "concept",
                    "replace": True,
                },
            )
            assert question.status_code == 200
            assert question.json()["topic_id"] == sessions[activity]["topic_id"]
            assert question.json()["learning_mode"] == expected_mode

        insufficient_question = client.post(
            f"/projects/{project_id}/learning/question",
            headers=headers,
            json={
                "request_id": "plan-insufficient",
                "plan_session_id": sessions["learn"]["id"],
                "replace": True,
            },
        ).json()
        insufficient = client.post(
            f"/projects/{project_id}/learning/answer",
            headers=headers,
            json={
                "attempt_id": "plan-insufficient-attempt",
                "question_id": insufficient_question["id"],
                "answer": "cache",
            },
        )
        assert insufficient.status_code == 200
        assert insufficient.json()["mastery_updated"] is False

        evidence_question = client.post(
            f"/projects/{project_id}/learning/question",
            headers=headers,
            json={
                "request_id": "plan-evidence",
                "plan_session_id": sessions["practice"]["id"],
                "replace": True,
            },
        ).json()
        evidence = client.post(
            f"/projects/{project_id}/learning/answer",
            headers=headers,
            json={
                "attempt_id": "plan-evidence-attempt",
                "question_id": evidence_question["id"],
                "answer": (
                    "A cache coherence protocol keeps processor copies consistent. "
                    "For example, after a write it invalidates stale copies and measures "
                    "propagation latency before relying on the new value."
                ),
            },
        )
        snapshot = client.get(
            f"/projects/{project_id}/learning/progress",
            headers=headers,
        )
        stored_plan = app.state.learning.get(learner["user_id"], project_id).data["progress"][
            "plan"
        ]
        statuses = {session["id"]: session["status"] for session in stored_plan["sessions"]}

    assert snapshot.status_code == 200
    assert evidence.status_code == 200
    assert evidence.json()["mastery_updated"] is False
    assert evidence.json()["completed_plan_session_id"] is None
    assert statuses[sessions["learn"]["id"]] == "planned"
    assert statuses[sessions["practice"]["id"]] == "planned"


def test_targeted_plan_requires_a_linked_and_analyzed_material(tmp_path: Path) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))
    with TestClient(app, raise_server_exceptions=False) as client:
        learner = _register(client, "targeted-plan-boundary@example.com")
        headers = _authorization(learner["token"])
        workspace_id = client.post(
            "/workspaces/resolve",
            headers=headers,
            json={"intent": "Study linear algebra"},
        ).json()["workspace"]["id"]
        material = client.post(
            "/materials/library",
            headers=headers,
            files={
                "files": (
                    "linear-algebra.txt",
                    b"Chapter 1 Eigenvalues\nEigenvalues describe invariant directions.",
                    "text/plain",
                )
            },
        ).json()[0]
        payload = {
            "material_id": material["id"],
            "focus_topics": ["Eigenvalues"],
            "exam_at": (datetime.now(UTC) + timedelta(days=14)).isoformat(),
            "daily_minutes": 45,
            "study_weekdays": [0, 1, 2, 3, 4],
            "preferred_hour": 19,
            "timezone_offset_minutes": 480,
            "routine_notes": "",
        }
        missing_workspace = client.post(
            "/workspaces/missing-workspace/learning/plan/targeted",
            headers=headers,
            json=payload,
        )

        unlinked = client.post(
            f"/workspaces/{workspace_id}/learning/plan/targeted",
            headers=headers,
            json=payload,
        )
        client.post(
            f"/materials/library/library/{material['id']}/attach/{workspace_id}",
            headers=headers,
        )
        unanalyzed = client.post(
            f"/workspaces/{workspace_id}/learning/plan/targeted",
            headers=headers,
            json=payload,
        )

    assert missing_workspace.status_code == 404
    assert missing_workspace.json()["error"]["code"] == "workspace_not_found"
    assert unlinked.status_code == 404
    assert unlinked.json()["error"]["code"] == "material_not_found"
    assert unanalyzed.status_code == 409
    assert unanalyzed.json()["error"]["code"] == "material_analysis_required"


def test_workspace_initial_diagnostic_is_reachable_and_owner_scoped(tmp_path: Path) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))

    with TestClient(app) as client:
        alice = _register(client, "diagnostic-alice@example.com")
        bob = _register(client, "diagnostic-bob@example.com")
        alice_headers = _authorization(alice["token"])
        workspace_id = client.post(
            "/workspaces/resolve",
            headers=alice_headers,
            json={"intent": "Learn calculus limits"},
        ).json()["workspace"]["id"]
        snapshot = client.get(
            f"/workspaces/{workspace_id}/snapshot",
            headers=alice_headers,
        ).json()
        topic_ids = list(snapshot["progress"]["topics"])

        diagnosed = client.post(
            f"/workspaces/{workspace_id}/learning/diagnostic",
            headers=alice_headers,
            json={
                "diagnostic_id": "initial",
                "results": [
                    {"topic_id": topic_id, "is_correct": index % 2 == 0}
                    for index, topic_id in enumerate(topic_ids)
                ],
            },
        )
        mastery_after_initial = diagnosed.json()["mastery"]
        repeated_with_new_id = client.post(
            f"/workspaces/{workspace_id}/learning/diagnostic",
            headers=alice_headers,
            json={
                "diagnostic_id": "second-pass",
                "results": [{"topic_id": topic_id, "is_correct": True} for topic_id in topic_ids],
            },
        )
        mastery_after_rejected_repeat = client.get(
            f"/workspaces/{workspace_id}/snapshot",
            headers=alice_headers,
        ).json()["progress"]["mastery"]
        forbidden = client.post(
            f"/workspaces/{workspace_id}/learning/diagnostic",
            headers=_authorization(bob["token"]),
            json={
                "diagnostic_id": "initial",
                "results": [{"topic_id": topic_ids[0], "is_correct": True}],
            },
        )

    assert diagnosed.status_code == 200
    assert diagnosed.json()["diagnostic_count"] == 1
    assert repeated_with_new_id.status_code == 422
    assert mastery_after_rejected_repeat == mastery_after_initial
    assert forbidden.status_code == 404


def test_workspace_insights_feedback_and_question_retry_are_owner_scoped(
    tmp_path: Path,
) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))

    with TestClient(app) as client:
        alice = _register(client, "insights-alice@example.com")
        bob = _register(client, "insights-bob@example.com")
        alice_headers = _authorization(alice["token"])
        bob_headers = _authorization(bob["token"])
        workspace_id = client.post(
            "/workspaces/resolve",
            headers=alice_headers,
            json={
                "intent": "Prepare calculus with limits and derivatives",
                "exam_at": (datetime.now(UTC) + timedelta(days=6)).isoformat(),
            },
        ).json()["workspace"]["id"]
        app.state.knowledge.add_document(
            owner_id=alice["user_id"],
            project_id=workspace_id,
            material_id="insights-material",
            filename="calculus.txt",
            text="Prepare calculus with limits and derivatives using worked examples.",
        )
        initial = client.get(
            f"/workspaces/{workspace_id}/snapshot",
            headers=alice_headers,
        ).json()
        generated = client.put(
            f"/workspaces/{workspace_id}/learning/plan",
            headers=alice_headers,
            json={
                "goal": initial["progress"]["goal"],
                "exam_at": (datetime.now(UTC) + timedelta(days=6)).isoformat(),
                "daily_minutes": 45,
                "topic_order": initial["progress"]["topic_order"],
                "regenerate": True,
            },
        )
        assert generated.status_code == 200

        question = client.post(
            f"/workspaces/{workspace_id}/learning/question",
            headers=alice_headers,
            json={"request_id": "insight-question-1"},
        ).json()
        first_answer_text = (
            "I would explain the definition, show each reasoning step, and verify it "
            "with a concrete counterexample before applying the result."
        )
        first = client.post(
            f"/workspaces/{workspace_id}/learning/answer",
            headers=alice_headers,
            json={
                "attempt_id": "insight-attempt-1",
                "question_id": question["id"],
                "answer": first_answer_text,
            },
        )
        assert first.status_code == 200

        retried = client.post(
            f"/workspaces/{workspace_id}/learning/questions/{question['id']}/retry",
            headers=alice_headers,
        )
        assert retried.status_code == 200
        assert retried.json()["id"] == question["id"]
        assert retried.json()["prompt"] == question["prompt"]
        second = client.post(
            f"/workspaces/{workspace_id}/learning/answer",
            headers=alice_headers,
            json={
                "attempt_id": "insight-attempt-2",
                "question_id": question["id"],
                "answer": "A shorter retry that still explains the central idea clearly.",
            },
        )
        assert second.status_code == 200

        manual_review = client.post(
            f"/workspaces/{workspace_id}/learning/plan/sessions",
            headers=alice_headers,
            json={
                "topic_name": initial["progress"]["topics"][question["topic_id"]],
                # Generated days are already full at the daily budget; add on a
                # later empty day to stay within budget.
                "planned_at": (datetime.now(UTC) + timedelta(days=30)).isoformat(),
                "minutes": 20,
                "activity": "review",
            },
        )
        assert manual_review.status_code == 200

        snapshot = client.get(
            f"/workspaces/{workspace_id}/snapshot",
            headers=alice_headers,
        ).json()
        reviews = [
            session for session in snapshot["plan"]["sessions"] if session["activity"] == "review"
        ]
        assert len(reviews) >= 1
        for index, review in enumerate(reversed(reviews[-2:])):
            response = client.patch(
                f"/workspaces/{workspace_id}/learning/plan/sessions/{review['id']}",
                headers=alice_headers,
                # Empty past days keep the review overdue without overloading the
                # already-full generated days.
                json={
                    "planned_at": (datetime.now(UTC) - timedelta(days=index + 1)).isoformat(),
                },
            )
            assert response.status_code == 200

        feedback = client.patch(
            f"/workspaces/{workspace_id}/learning/attempts/insight-attempt-1/feedback",
            headers=alice_headers,
            json={"learner_note": "Please review the second rubric item.", "appealed": True},
        )
        assert feedback.status_code == 200
        assert feedback.json() == {
            "attempt_id": "insight-attempt-1",
            "learner_note": "Please review the second rubric item.",
            "appealed": True,
        }
        feedback_replay = client.post(
            f"/workspaces/{workspace_id}/learning/answer",
            headers=alice_headers,
            json={
                "attempt_id": "insight-attempt-1",
                "question_id": question["id"],
                "answer": "This payload must not replace the stored answer.",
            },
        )
        assert feedback_replay.status_code == 200
        assert feedback_replay.json()["replayed"] is True
        assert feedback_replay.json()["learner_note"] == "Please review the second rubric item."

        insights = client.get(
            f"/workspaces/{workspace_id}/learning/insights",
            headers=alice_headers,
        )
        assert insights.status_code == 200
        body = insights.json()
        assert body["workspace_id"] == workspace_id
        assert [item["attempt_id"] for item in body["mastery_history"]] == [
            "insight-attempt-1",
            "insight-attempt-2",
        ]
        assert [item["attempt_id"] for item in body["attempts"]] == [
            "insight-attempt-2",
            "insight-attempt-1",
        ]
        first_insight = body["attempts"][1]
        assert first_insight["question_prompt"] == question["prompt"]
        assert first_insight["answer"] == first_answer_text
        assert first_insight["learner_note"] == "Please review the second rubric item."
        assert first_insight["appealed"] is True
        assert isinstance(first_insight["strengths"], list)
        assert isinstance(first_insight["gaps"], list)
        assert isinstance(first_insight["misconceptions"], list)
        assert isinstance(first_insight["sources"], list)
        assert [item["due_at"] for item in body["due_reviews"]] == sorted(
            item["due_at"] for item in body["due_reviews"]
        )
        assert sum(item["error_count"] for item in body["topics"]) == sum(
            not item["is_correct"] for item in body["attempts"]
        )

        due_review = body["due_reviews"][0]
        review_question = client.post(
            f"/workspaces/{workspace_id}/learning/question",
            headers=alice_headers,
            json={
                "request_id": "due-review-question",
                "topic_id": due_review["topic_id"],
                "review_session_id": due_review["session_id"],
                "replace": True,
            },
        )
        assert review_question.status_code == 200
        completed_review = client.post(
            f"/workspaces/{workspace_id}/learning/answer",
            headers=alice_headers,
            json={
                "attempt_id": "due-review-attempt",
                "question_id": review_question.json()["id"],
                "answer": "A review answer with enough explanation to evaluate the concept.",
            },
        )
        assert completed_review.status_code == 200
        regenerated = client.put(
            f"/workspaces/{workspace_id}/learning/plan",
            headers=alice_headers,
            json={
                "goal": snapshot["workspace"]["goal"],
                "exam_at": (datetime.now(UTC) + timedelta(days=5)).isoformat(),
                "daily_minutes": 30,
                "topic_order": list(snapshot["progress"]["topics"]),
                "regenerate": True,
            },
        )
        assert regenerated.status_code == 200
        retried_review = client.post(
            f"/workspaces/{workspace_id}/learning/questions/{review_question.json()['id']}/retry",
            headers=alice_headers,
        )
        assert retried_review.status_code == 200
        resubmitted_review = client.post(
            f"/workspaces/{workspace_id}/learning/answer",
            headers=alice_headers,
            json={
                "attempt_id": "retried-review-attempt",
                "question_id": retried_review.json()["id"],
                "answer": "A fresh answer should not depend on the old review schedule entry.",
            },
        )
        assert resubmitted_review.status_code == 200
        after_review = client.get(
            f"/workspaces/{workspace_id}/learning/insights",
            headers=alice_headers,
        ).json()
        assert due_review["session_id"] not in {
            item["session_id"] for item in after_review["due_reviews"]
        }

        forbidden_insights = client.get(
            f"/workspaces/{workspace_id}/learning/insights",
            headers=bob_headers,
        )
        forbidden_feedback = client.patch(
            f"/workspaces/{workspace_id}/learning/attempts/insight-attempt-1/feedback",
            headers=bob_headers,
            json={"appealed": True},
        )
        forbidden_retry = client.post(
            f"/workspaces/{workspace_id}/learning/questions/{question['id']}/retry",
            headers=bob_headers,
        )

    assert forbidden_insights.status_code == 404
    assert forbidden_feedback.status_code == 404
    assert forbidden_retry.status_code == 404


def test_attempt_question_snapshot_survives_history_pruning(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr("refineq.learning.service.MAX_QUESTION_HISTORY", 2)
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))

    with TestClient(app) as client:
        learner = _register(client, "history-learner@example.com")
        headers = _authorization(learner["token"])
        workspace_id = client.post(
            "/workspaces/resolve",
            headers=headers,
            json={"intent": "Prepare calculus"},
        ).json()["workspace"]["id"]
        app.state.knowledge.add_document(
            owner_id=learner["user_id"],
            project_id=workspace_id,
            material_id="history-material",
            filename="calculus.txt",
            text="Prepare calculus through definitions, examples, and reasoning.",
        )
        first_question: dict | None = None
        for index in range(3):
            question = client.post(
                f"/workspaces/{workspace_id}/learning/question",
                headers=headers,
                json={"request_id": f"history-question-{index}"},
            ).json()
            first_question = first_question or question
            answer = client.post(
                f"/workspaces/{workspace_id}/learning/answer",
                headers=headers,
                json={
                    "attempt_id": f"history-attempt-{index}",
                    "question_id": question["id"],
                    "answer": "A complete explanation with an example and a clear reasoning chain.",
                },
            )
            assert answer.status_code == 200
            assert "question_snapshot" not in answer.json()
            assert "expected_answer" not in answer.text

        assert first_question is not None
        stored = app.state.learning.get(learner["user_id"], workspace_id).data
        assert first_question["id"] not in stored["progress"]["question_history"]
        history_size = len(stored["progress"]["question_history"])
        insights = client.get(
            f"/workspaces/{workspace_id}/learning/insights",
            headers=headers,
        )
        restored_attempt = next(
            item
            for item in insights.json()["attempts"]
            if item["question_id"] == first_question["id"]
        )
        retried = client.post(
            f"/workspaces/{workspace_id}/learning/questions/{first_question['id']}/retry",
            headers=headers,
        )

    assert restored_attempt["question_prompt"] == first_question["prompt"]
    assert retried.status_code == 200
    assert retried.json()["prompt"] == first_question["prompt"]
    stored_after_retry = app.state.learning.get(learner["user_id"], workspace_id).data
    assert len(stored_after_retry["progress"]["question_history"]) == history_size
