"""End-to-end API contract for grounded AI practice and idempotent grading."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from refineq.api.app import create_app
from refineq.config import Settings


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
        return response_model.model_validate(
            {
                "score": 88,
                "strengths": ["准确说明趋近"],
                "gaps": ["可以补充形式化定义"],
                "misconceptions": [],
                "feedback": "回答正确，下一步练习形式化定义。",
                "citations": ["material-1#0"],
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
        client.put(
            "/settings/model",
            headers=headers,
            json={
                "base_url": "https://api.openai.com/v1",
                "model": "study-model",
                "api_key": "secret-key-1234",
                "temperature": 0.2,
            },
        )

        question_response = client.get(
            f"/workspaces/{workspace_id}/learning/question",
            headers=headers,
        )
        assert question_response.status_code == 200
        question = question_response.json()
        assert question["mode"] == "ai"
        assert question["citations"] == ["material-1#0"]
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

        replay = client.post(
            f"/workspaces/{workspace_id}/learning/answer",
            headers=headers,
            json={**payload, "answer": "完全不同的答案"},
        )

    assert replay.status_code == 200
    assert replay.json()["replayed"] is True
    assert replay.json()["score"] == 88
    assert model.calls == ["QuestionModelOutput", "GradingModelOutput"]


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
        question = client.get(
            f"/workspaces/{workspace_id}/learning/question", headers=headers
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
