"""End-to-end API contract for grounded AI practice and idempotent grading."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from refineq.agent.settings import ModelSettings
from refineq.api.app import create_app
from refineq.config import Settings
from refineq.operations.admin import ensure_admin


class FakeLearningModel:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def complete(self, *, settings, messages, response_model):
        del settings, messages
        self.calls.append(response_model.__name__)
        if response_model.__name__ == "QuestionModelOutput":
            return response_model.model_validate(
                {
                    "prompt": "根据资料解释函数极限。",
                    "expected_answer": "极限是函数值趋近的目标。",
                    "rubric": [{"criterion": "准确解释极限", "max_points": 100}],
                    "explanation": "检查核心概念。",
                    "citations": ["material-1#0"],
                }
            )
        if response_model.__name__ == "MaterialAnalysisModelOutput":
            return response_model.model_validate(
                {
                    "material_type": "lecture_notes",
                    "title": "函数极限讲义",
                    "summary": "介绍函数极限的含义。",
                    "sections": [
                        {
                            "title": "函数极限",
                            "topics": ["函数极限"],
                            "citation_ids": ["material-1#0", "invalid#9"],
                        }
                    ],
                    "topics": ["函数极限"],
                    "confidence": 0.91,
                }
            )
        return response_model.model_validate(
            {
                "score": 88,
                "strengths": ["准确说明趋近"],
                "gaps": ["可以补充形式化定义"],
                "misconceptions": [],
                "feedback": "回答正确，下一步练习形式化定义。",
                "citations": [],
            }
        )


class MaterialClaimingLearningModel:
    def complete(self, *, settings, messages, response_model):
        del settings, messages
        assert response_model.__name__ == "QuestionModelOutput"
        return response_model.model_validate(
            {
                "prompt": "请根据上传材料中的访谈原文分析用户需求。",
                "expected_answer": "区分表面诉求和真实行为。",
                "rubric": [{"criterion": "识别真实需求", "max_points": 100}],
                "explanation": "检查案例分析能力。",
                "citations": [],
            }
        )


def test_workspace_practice_uses_ai_without_leaking_private_grading_data(
    tmp_path: Path,
) -> None:
    model = FakeLearningModel()
    app = create_app(
        Settings(data_root=tmp_path / "data", _env_file=None),
        learning_model_transport=model,
    )

    with TestClient(app) as client:
        auth = client.post(
            "/auth/register",
            json={
                "email": "ai-learner@example.com",
                "password": "correct-horse-battery-staple",
                "display_name": "AI Learner",
            },
        ).json()
        token = auth["access_token"]
        owner_id = auth["user"]["id"]
        headers = {"Authorization": f"Bearer {token}"}
        workspace_id = client.post(
            "/workspaces/resolve",
            headers=headers,
            json={"intent": "复习高数函数极限"},
        ).json()["workspace"]["id"]
        app.state.knowledge.add_document(
            owner_id=owner_id,
            project_id=workspace_id,
            material_id="material-1",
            filename="limits.txt",
            text="函数极限是自变量趋近某点时函数值趋近的目标。",
        )
        admin = ensure_admin(
            app.state.identity,
            email="platform-admin@example.com",
            password="correct-horse-battery-staple",
            display_name="Platform Admin",
        ).user
        app.state.model_settings.save(
            admin.id,
            ModelSettings(
                base_url="https://api.openai.com/v1",
                model="study-model",
                api_key="secret-key-1234",
                temperature=0.2,
            ),
        )

        analysis_response = client.post(
            f"/workspaces/{workspace_id}/materials/material-1/analysis",
            headers=headers,
        )
        assert analysis_response.status_code == 200
        analysis = analysis_response.json()
        assert analysis["mode"] == "ai"
        assert analysis["material_type"] == "lecture_notes"
        assert analysis["topics"] == ["函数极限"]
        assert analysis["sections"][0]["citation_ids"] == ["material-1#0"]

        persisted = client.get(
            f"/workspaces/{workspace_id}/materials/material-1/analysis",
            headers=headers,
        )
        assert persisted.status_code == 200
        assert persisted.json() == analysis

        question_response = client.post(
            f"/workspaces/{workspace_id}/learning/question",
            headers=headers,
            json={"request_id": "ai-question-1"},
        )
        assert question_response.status_code == 200
        question = question_response.json()
        assert question["mode"] == "ai"
        assert question["grounding"] == "material"
        assert question["explanation"] == "检查核心概念。"
        assert question["citations"] == ["material-1#0"]
        assert question["sources"] == [
            {
                "citation_id": "material-1#0",
                "material_id": "material-1",
                "filename": "limits.txt",
                "chunk_index": 0,
                "text": "函数极限是自变量趋近某点时函数值趋近的目标。",
                "score": question["sources"][0]["score"],
            }
        ]
        assert "expected_answer" not in question_response.text
        assert "rubric" not in question_response.text

        payload = {
            "attempt_id": "attempt-ai-1",
            "question_id": question["id"],
            "answer": "极限描述函数值不断趋近的目标。",
        }
        answer = client.post(
            f"/workspaces/{workspace_id}/learning/answer",
            headers=headers,
            json=payload,
        )
        assert answer.status_code == 200
        grade = answer.json()
        assert grade["score"] == 88
        assert grade["is_correct"] is True
        assert grade["feedback"] == "回答正确，下一步练习形式化定义。"
        assert grade["strengths"] == ["准确说明趋近"]
        assert grade["gaps"] == ["可以补充形式化定义"]
        assert grade["grading_mode"] == "ai"
        assert grade["grounding"] == "material"
        assert grade["citations"] == []
        assert grade["sources"][0]["citation_id"] == "material-1#0"
        assert "expected_answer" not in answer.text

        replay = client.post(
            f"/workspaces/{workspace_id}/learning/answer",
            headers=headers,
            json={**payload, "answer": "完全不同的答案"},
        )

    assert replay.status_code == 200
    assert replay.json()["replayed"] is True
    assert replay.json()["score"] == 88
    assert model.calls == [
        "MaterialAnalysisModelOutput",
        "QuestionModelOutput",
        "GradingModelOutput",
    ]


def test_low_confidence_fallback_answer_does_not_change_mastery(tmp_path: Path) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))

    with TestClient(app) as client:
        auth = client.post(
            "/auth/register",
            json={
                "email": "fallback-learner@example.com",
                "password": "correct-horse-battery-staple",
                "display_name": "Fallback Learner",
            },
        ).json()
        headers = {"Authorization": f"Bearer {auth['access_token']}"}
        workspace_id = client.post(
            "/workspaces/resolve",
            headers=headers,
            json={"intent": "Learn calculus limits"},
        ).json()["workspace"]["id"]
        before = client.get(f"/workspaces/{workspace_id}/snapshot", headers=headers).json()[
            "progress"
        ]["mastery"]
        question = client.post(
            f"/workspaces/{workspace_id}/learning/question",
            headers=headers,
            json={"request_id": "fallback-question-1"},
        ).json()
        answer = client.post(
            f"/workspaces/{workspace_id}/learning/answer",
            headers=headers,
            json={
                "attempt_id": "topic-echo",
                "question_id": question["id"],
                "answer": "limits",
            },
        )
        after = client.get(f"/workspaces/{workspace_id}/snapshot", headers=headers).json()[
            "progress"
        ]["mastery"]

    assert answer.status_code == 200
    assert answer.json()["is_correct"] is False
    assert answer.json()["mastery_updated"] is False
    assert after == before


def test_workspace_practice_can_replace_a_question_at_a_chosen_difficulty(
    tmp_path: Path,
) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))

    with TestClient(app) as client:
        auth = client.post(
            "/auth/register",
            json={
                "email": "targeted-practice@example.com",
                "password": "correct-horse-battery-staple",
                "display_name": "Targeted Learner",
            },
        ).json()
        headers = {"Authorization": f"Bearer {auth['access_token']}"}
        workspace_id = client.post(
            "/workspaces/resolve",
            headers=headers,
            json={"intent": "复习高数函数极限"},
        ).json()["workspace"]["id"]
        snapshot = client.get(
            f"/workspaces/{workspace_id}/snapshot",
            headers=headers,
        ).json()
        topic_id = next(iter(snapshot["progress"]["mastery"]))

        first = client.post(
            f"/workspaces/{workspace_id}/learning/question",
            headers=headers,
            json={
                "request_id": "targeted-question-1",
                "topic_id": topic_id,
                "difficulty": 1,
            },
        )
        replacement = client.post(
            f"/workspaces/{workspace_id}/learning/question",
            headers=headers,
            json={
                "request_id": "targeted-question-2",
                "topic_id": topic_id,
                "difficulty": 5,
                "replace": True,
            },
        )
        invalid_topic = client.post(
            f"/workspaces/{workspace_id}/learning/question",
            headers=headers,
            json={
                "request_id": "targeted-question-3",
                "topic_id": "unknown-topic",
                "replace": True,
            },
        )

    assert first.status_code == 200
    assert first.json()["topic_id"] == topic_id
    assert first.json()["difficulty_level"] == 1
    assert replacement.status_code == 200
    assert replacement.json()["topic_id"] == topic_id
    assert replacement.json()["difficulty_level"] == 5
    assert replacement.json()["id"] != first.json()["id"]
    assert invalid_topic.status_code == 409
    assert invalid_topic.json()["error"]["code"] == "learning_conflict"


def test_workspace_learning_task_accepts_project_mode(tmp_path: Path) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))

    with TestClient(app) as client:
        auth = client.post(
            "/auth/register",
            json={
                "email": "product-learner@example.com",
                "password": "correct-horse-battery-staple",
                "display_name": "Product Learner",
            },
        ).json()
        headers = {"Authorization": f"Bearer {auth['access_token']}"}
        workspace_id = client.post(
            "/workspaces/resolve",
            headers=headers,
            json={"intent": "学习产品思维，并练习验证真实用户需求"},
        ).json()["workspace"]["id"]
        response = client.post(
            f"/workspaces/{workspace_id}/learning/question",
            headers=headers,
            json={"request_id": "project-question-1", "mode": "project"},
        )

    assert response.status_code == 200
    assert response.json()["learning_mode"] == "project"


def test_workspace_case_task_without_matching_material_is_explicitly_general(
    tmp_path: Path,
) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))

    with TestClient(app) as client:
        auth = client.post(
            "/auth/register",
            json={
                "email": "general-case@example.com",
                "password": "correct-horse-battery-staple",
                "display_name": "General Case Learner",
            },
        ).json()
        headers = {"Authorization": f"Bearer {auth['access_token']}"}
        workspace_id = client.post(
            "/workspaces/resolve",
            headers=headers,
            json={"intent": "练习识别用户真实需求"},
        ).json()["workspace"]["id"]
        response = client.post(
            f"/workspaces/{workspace_id}/learning/question",
            headers=headers,
            json={"request_id": "general-case-1", "mode": "case"},
        )

    assert response.status_code == 200
    question = response.json()
    assert question["grounding"] == "general"
    assert question["sources"] == []
    assert "基于材料" not in question["prompt"]


def test_configured_model_cannot_claim_uploaded_material_when_retrieval_is_empty(
    tmp_path: Path,
) -> None:
    app = create_app(
        Settings(data_root=tmp_path / "data", _env_file=None),
        learning_model_transport=MaterialClaimingLearningModel(),
    )

    with TestClient(app) as client:
        auth = client.post(
            "/auth/register",
            json={
                "email": "no-source-ai@example.com",
                "password": "correct-horse-battery-staple",
                "display_name": "No Source AI Learner",
            },
        ).json()
        headers = {"Authorization": f"Bearer {auth['access_token']}"}
        workspace_id = client.post(
            "/workspaces/resolve",
            headers=headers,
            json={"intent": "练习用户需求分析"},
        ).json()["workspace"]["id"]
        admin = ensure_admin(
            app.state.identity,
            email="platform-admin@example.com",
            password="correct-horse-battery-staple",
            display_name="Platform Admin",
        ).user
        app.state.model_settings.save(
            admin.id,
            ModelSettings(
                base_url="https://api.openai.com/v1",
                model="study-model",
                api_key="secret-key-1234",
            ),
        )
        response = client.post(
            f"/workspaces/{workspace_id}/learning/question",
            headers=headers,
            json={"request_id": "no-source-ai-1", "mode": "case"},
        )

    assert response.status_code == 200
    question = response.json()
    assert question["grounding"] == "general"
    assert question["sources"] == []
    assert question["mode"] == "ai"
    assert "上传材料" not in question["prompt"]
    assert "访谈原文" not in question["prompt"]
