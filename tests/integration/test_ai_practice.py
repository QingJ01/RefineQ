"""End-to-end API contract for grounded AI practice and idempotent grading."""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event

import pytest
from fastapi.testclient import TestClient

from refineq.agent.settings import ModelSettings
from refineq.api.app import create_app
from refineq.config import Settings
from refineq.learning.evidence import stable_id
from refineq.learning.service import PlanSessionCreate, SeedRequest, TopicSeed
from refineq.operations.admin import ensure_admin


def _add_workspace_material(
    app,
    owner_id: str,
    workspace_id: str,
    *,
    text: str | None = None,
) -> None:
    if text is None:
        workspace = app.state.workspaces.get(owner_id, workspace_id)
        text = f"{' '.join(workspace.topics)} study material and worked examples."
    app.state.knowledge.add_document(
        owner_id=owner_id,
        project_id=workspace_id,
        material_id=f"fixture-{workspace_id[:16]}",
        filename="fixture.txt",
        text=text,
    )


class FakeLearningModel:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def complete(self, *, settings, messages, response_model):
        del settings
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
        if response_model.__name__ == "TrustedAnswerKeyOutput":
            return response_model.model_validate(
                {
                    "supported": True,
                    "expected_answer": "函数极限是函数值趋近的目标。",
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
        learner_answer = (
            messages[-1]["content"]
            .split("<learner_answer>\n", 1)[1]
            .split("\n</learner_answer>", 1)[0]
        )
        return response_model.model_validate(
            {
                "score": 88,
                "strengths": ["准确说明趋近"],
                "gaps": ["可以补充形式化定义"],
                "misconceptions": [],
                "feedback": "回答正确，下一步练习形式化定义。",
                "citations": [],
                "sufficient_evidence": True,
                "evidence_spans": [learner_answer],
            }
        )


class BlockingQuestionModel(FakeLearningModel):
    def __init__(self) -> None:
        super().__init__()
        self.started = Event()
        self.release = Event()
        self.transaction_active: bool | None = None
        self.inspect_transaction = lambda: False

    def complete(self, *, settings, messages, response_model):
        if response_model.__name__ == "QuestionModelOutput":
            self.transaction_active = self.inspect_transaction()
            self.started.set()
            self.release.wait(timeout=3)
        return super().complete(
            settings=settings,
            messages=messages,
            response_model=response_model,
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


class SequencedGradingLearningModel(FakeLearningModel):
    def __init__(self, scores: list[int]) -> None:
        super().__init__()
        self.scores = iter(scores)

    def complete(self, *, settings, messages, response_model):
        if response_model.__name__ in {"QuestionModelOutput", "TrustedAnswerKeyOutput"}:
            return super().complete(
                settings=settings,
                messages=messages,
                response_model=response_model,
            )
        del settings
        self.calls.append(response_model.__name__)
        score = next(self.scores)
        learner_answer = (
            messages[-1]["content"]
            .split("<learner_answer>\n", 1)[1]
            .split("\n</learner_answer>", 1)[0]
        )
        return response_model.model_validate(
            {
                "score": score,
                "strengths": ["包含可判断的解释"],
                "gaps": [] if score >= 70 else ["仍需修正结论"],
                "misconceptions": [],
                "feedback": "已记录这次独立作答。",
                "citations": [],
                "sufficient_evidence": True,
                "evidence_spans": [learner_answer],
            }
        )


class NominalAcademicLearningModel:
    def __init__(self) -> None:
        self.message_batches: list[list[dict[str, str]]] = []

    def complete(self, *, settings, messages, response_model):
        del settings
        self.message_batches.append(messages)
        prompt = "\n".join(message["content"] for message in messages).casefold()
        if "feedback control" in prompt:
            question = "Explain how feedback control changes system output."
            answer = (
                "Feedback control compares output with a reference and uses the error "
                "to adjust the system input."
            )
        elif "compound interest" in prompt:
            question = "Explain how compound interest changes an investment return."
            answer = (
                "Compound interest earns interest on principal and accumulated interest, "
                "increasing investment returns over time."
            )
        else:
            raise AssertionError(prompt)
        if response_model.__name__ == "QuestionModelOutput":
            return response_model.model_validate(
                {
                    "prompt": question,
                    "expected_answer": answer,
                    "rubric": [{"criterion": "Explain the core relationship", "max_points": 100}],
                    "explanation": "The task checks the named academic relationship.",
                    "citations": ["nominal-notes#0"],
                }
            )
        if response_model.__name__ == "TrustedAnswerKeyOutput":
            return response_model.model_validate({"supported": True, "expected_answer": answer})
        learner_answer = (
            messages[-1]["content"]
            .split("<learner_answer>\n", 1)[1]
            .split("\n</learner_answer>", 1)[0]
        )
        return response_model.model_validate(
            {
                "score": 90,
                "strengths": ["Explains the core relationship."],
                "gaps": [],
                "misconceptions": [],
                "feedback": "The answer demonstrates the requested concept.",
                "citations": [],
                "sufficient_evidence": True,
                "evidence_spans": [learner_answer],
            }
        )


class ComposedMaterialLearningModel(NominalAcademicLearningModel):
    def complete(self, *, settings, messages, response_model):
        content = "\n".join(message["content"] for message in messages)
        if response_model.__name__ == "MaterialAnalysisModelOutput":
            self.message_batches.append(messages)
            citation = re.search(r"\[([^\]\n]+#\d+)\]", content)
            assert citation is not None
            return response_model.model_validate(
                {
                    "material_type": "lecture_notes",
                    "title": "Feedback control notes",
                    "summary": "Explains output regulation using a feedback loop.",
                    "sections": [
                        {
                            "title": "Output with feedback control",
                            "topics": ["Output with feedback control"],
                            "citation_ids": [citation.group(1)],
                        }
                    ],
                    "topics": ["Output with feedback control"],
                    "confidence": 0.95,
                }
            )
        if response_model.__name__ == "TargetedPlanOutput":
            self.message_batches.append(messages)
            planned_at = (datetime.now(UTC) + timedelta(days=1)).replace(
                hour=19,
                minute=0,
                second=0,
                microsecond=0,
            )
            return response_model.model_validate(
                {
                    "sessions": [
                        {
                            "topic": "Output with feedback control",
                            "planned_at": planned_at.isoformat(),
                            "minutes": 30,
                            "activity": "practice",
                        }
                    ]
                }
            )
        if response_model.__name__ == "QuestionModelOutput":
            self.message_batches.append(messages)
            citation = re.search(r"\[([^\]\n]+#\d+)\]", content)
            assert citation is not None
            return response_model.model_validate(
                {
                    "prompt": "Explain how feedback control changes system output.",
                    "expected_answer": "A feedback loop adjusts the system input.",
                    "rubric": [{"criterion": "Explain the feedback loop", "max_points": 100}],
                    "explanation": "Checks the core closed-loop relationship.",
                    "citations": [citation.group(1)],
                }
            )
        return super().complete(
            settings=settings,
            messages=messages,
            response_model=response_model,
        )


def test_nominal_control_word_topics_persist_mastery_and_plan_progress(
    tmp_path: Path,
) -> None:
    model = NominalAcademicLearningModel()
    app = create_app(
        Settings(data_root=tmp_path / "data", _env_file=None),
        learning_model_transport=model,
    )

    with TestClient(app) as client:
        auth = client.post(
            "/auth/register",
            json={
                "email": "nominal-topics@example.com",
                "password": "correct-horse-battery-staple",
                "display_name": "Nominal Topic Learner",
            },
        ).json()
        owner_id = auth["user"]["id"]
        headers = {"Authorization": f"Bearer {auth['access_token']}"}
        workspace_id = client.post(
            "/workspaces/resolve",
            headers=headers,
            json={"intent": "Study feedback systems and investment returns"},
        ).json()["workspace"]["id"]
        topics = [
            TopicSeed(id="feedback-control", name="Output with feedback control"),
            TopicSeed(id="compound-interest", name="Return with compound interest"),
        ]
        app.state.workspace_learning_service.seed(
            owner_id,
            workspace_id,
            SeedRequest(
                goal="Master feedback control and compound interest",
                exam_at=datetime.now(UTC) + timedelta(days=14),
                daily_minutes=30,
                topics=topics,
            ),
            answer_key_subjects={
                "feedback-control": "feedback control",
                "compound-interest": "compound interest",
            },
        )
        plan = app.state.workspace_learning_service.create_plan(
            owner_id,
            workspace_id,
            start_at=datetime.now(UTC),
        )
        app.state.knowledge.add_document(
            owner_id=owner_id,
            project_id=workspace_id,
            material_id="nominal-notes",
            filename="nominal-topics.md",
            text=(
                "Output with feedback control uses measured output and a reference to adjust "
                "system input. Return with compound interest includes growth on principal and "
                "previously accumulated interest."
            ),
        )
        admin = ensure_admin(
            app.state.identity,
            email="nominal-topic-admin@example.com",
            password="correct-horse-battery-staple",
            display_name="Nominal Topic Admin",
        ).user
        app.state.model_settings.save(
            admin.id,
            ModelSettings(
                base_url="https://api.openai.com/v1",
                model="study-model",
                api_key="secret-key-1234",
            ),
        )

        completed_sessions: dict[str, str] = {}
        for topic in topics:
            plan_session = next(
                session
                for session in plan.sessions
                if session.topic_id == topic.id and session.status == "planned"
            )
            question = client.post(
                f"/workspaces/{workspace_id}/learning/question",
                headers=headers,
                json={
                    "request_id": f"{topic.id}-question",
                    "topic_id": topic.id,
                    "plan_session_id": plan_session.id,
                },
            )
            assert question.status_code == 200
            expected_answer = (
                "Feedback control compares output with a reference and uses the error to "
                "adjust the system input."
                if topic.id == "feedback-control"
                else (
                    "Compound interest earns interest on principal and accumulated interest, "
                    "increasing investment returns over time."
                )
            )
            answer = client.post(
                f"/workspaces/{workspace_id}/learning/answer",
                headers=headers,
                json={
                    "attempt_id": f"{topic.id}-attempt",
                    "question_id": question.json()["id"],
                    "answer": expected_answer,
                },
            )
            assert answer.status_code == 200
            assert answer.json()["mastery_updated"] is True
            assert answer.json()["completed_plan_session_id"] == plan_session.id
            completed_sessions[topic.id] = plan_session.id

        stored = app.state.learning.get(owner_id, workspace_id).data["progress"]

    assert all(stored["bkt_states"][topic.id]["p_mastery"] > 0.0 for topic in topics)
    statuses = {session["id"]: session["status"] for session in stored["plan"]["sessions"]}
    assert all(statuses[session_id] == "completed" for session_id in completed_sessions.values())
    grading_prompts = [
        batch[-1]["content"]
        for batch in model.message_batches
        if "<learner_answer>" in batch[-1]["content"]
    ]
    assert len(grading_prompts) == 2
    assert all("Trusted answer key" not in prompt for prompt in grading_prompts)
    assert all("untrusted_study_materials" not in prompt for prompt in grading_prompts)
    assert all("Output with feedback control" not in prompt for prompt in grading_prompts)
    assert all("Return with compound interest" not in prompt for prompt in grading_prompts)


def test_material_analysis_registry_targeted_plan_completes_mastery_journey(
    tmp_path: Path,
) -> None:
    model = ComposedMaterialLearningModel()
    app = create_app(
        Settings(data_root=tmp_path / "data", _env_file=None),
        learning_model_transport=model,
    )

    with TestClient(app) as client:
        auth = client.post(
            "/auth/register",
            json={
                "email": "material-registry-journey@example.com",
                "password": "correct-horse-battery-staple",
                "display_name": "Material Registry Learner",
            },
        ).json()
        owner_id = auth["user"]["id"]
        headers = {"Authorization": f"Bearer {auth['access_token']}"}
        workspace_id = client.post(
            "/workspaces/resolve",
            headers=headers,
            json={"intent": "Study feedback control"},
        ).json()["workspace"]["id"]
        material = client.post(
            "/materials/library",
            headers=headers,
            files={
                "files": (
                    "feedback-control.txt",
                    (
                        b"Output with feedback control compares measured output with a reference "
                        b"and uses the error to adjust system input."
                    ),
                    "text/plain",
                )
            },
        ).json()[0]
        attach = client.post(
            f"/materials/library/library/{material['id']}/attach/{workspace_id}",
            headers=headers,
        )
        assert attach.status_code == 201
        admin = ensure_admin(
            app.state.identity,
            email="material-registry-admin@example.com",
            password="correct-horse-battery-staple",
            display_name="Material Registry Admin",
        ).user
        app.state.model_settings.save(
            admin.id,
            ModelSettings(
                base_url="https://api.openai.com/v1",
                model="study-model",
                api_key="secret-key-1234",
            ),
        )
        analysis = client.post(
            f"/workspaces/{workspace_id}/materials/{material['id']}/analysis",
            headers=headers,
        )
        assert analysis.status_code == 200
        plan = client.post(
            f"/workspaces/{workspace_id}/learning/plan/targeted",
            headers=headers,
            json={
                "idempotency_key": "material-registry-plan-1",
                "material_id": material["id"],
                "focus_topics": ["Output with feedback control"],
                "exam_at": (datetime.now(UTC) + timedelta(days=14)).isoformat(),
                "daily_minutes": 30,
                "study_weekdays": [0, 1, 2, 3, 4, 5, 6],
                "preferred_hour": 19,
                "timezone_offset_minutes": 0,
                "routine_notes": "",
            },
        )
        assert plan.status_code == 200
        session = plan.json()["sessions"][0]
        question = client.post(
            f"/workspaces/{workspace_id}/learning/question",
            headers=headers,
            json={
                "request_id": "material-registry-question",
                "topic_id": session["topic_id"],
                "plan_session_id": session["id"],
            },
        )
        assert question.status_code == 200
        answer = client.post(
            f"/workspaces/{workspace_id}/learning/answer",
            headers=headers,
            json={
                "attempt_id": "material-registry-answer",
                "question_id": question.json()["id"],
                "answer": (
                    "Feedback control compares output with a reference and uses the resulting "
                    "error to adjust system input, for example by correcting a measured deviation."
                ),
            },
        )
        stored = app.state.learning.get(owner_id, workspace_id).data["progress"]

    assert answer.status_code == 200
    assert answer.json()["mastery_updated"] is True
    assert answer.json()["completed_plan_session_id"] == session["id"]
    topic = stored["topics"][session["topic_id"]]
    assert topic["answer_key_subject"] == "feedback control"
    assert stored["bkt_states"][session["topic_id"]]["p_mastery"] > 0.0


def test_explicit_topic_actions_reauthorize_existing_topics_without_a_subject(
    tmp_path: Path,
) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))

    with TestClient(app) as client:
        auth = client.post(
            "/auth/register",
            json={
                "email": "legacy-topic-actions@example.com",
                "password": "correct-horse-battery-staple",
                "display_name": "Legacy Topic Learner",
            },
        ).json()
        owner_id = auth["user"]["id"]
        headers = {"Authorization": f"Bearer {auth['access_token']}"}
        workspace_id = client.post(
            "/workspaces/resolve",
            headers=headers,
            json={"intent": "Study legacy topics"},
        ).json()["workspace"]["id"]
        plan_topic_name = "Legacy plan topic"
        plan_topic_id = stable_id("topic", workspace_id, plan_topic_name)
        app.state.workspace_learning_service.seed(
            owner_id,
            workspace_id,
            SeedRequest(
                goal="Restore explicit mastery authority",
                exam_at=datetime.now(UTC) + timedelta(days=14),
                daily_minutes=30,
                topics=[
                    TopicSeed(id="legacy-add-topic", name="Legacy add topic"),
                    TopicSeed(id=plan_topic_id, name=plan_topic_name),
                ],
            ),
            answer_key_subjects={},
        )
        app.state.workspace_learning_service.create_plan(
            owner_id,
            workspace_id,
            start_at=datetime.now(UTC),
        )

        app.state.workspace_learning_service.add_topic(
            owner_id,
            workspace_id,
            TopicSeed(id="legacy-add-topic", name="Legacy add topic"),
        )
        app.state.workspace_learning_service.add_plan_session(
            owner_id,
            workspace_id,
            PlanSessionCreate(
                topic_name=plan_topic_name,
                # The generated plan fills each day to the daily budget; use a
                # later empty day so the added session stays within budget.
                planned_at=datetime.now(UTC) + timedelta(days=30),
                minutes=20,
                activity="practice",
            ),
        )
        topics = app.state.learning.get(owner_id, workspace_id).data["progress"]["topics"]

    assert topics["legacy-add-topic"]["answer_key_subject"] == "Legacy add topic"
    assert topics[plan_topic_id]["answer_key_subject"] == plan_topic_name


@pytest.mark.parametrize("restore_from_history", [False, True])
def test_legacy_trusted_question_without_current_subject_cannot_update_mastery(
    tmp_path: Path,
    restore_from_history: bool,
) -> None:
    app = create_app(
        Settings(data_root=tmp_path / "data", _env_file=None),
        learning_model_transport=FakeLearningModel(),
    )

    with TestClient(app) as client:
        auth = client.post(
            "/auth/register",
            json={
                "email": f"legacy-question-{restore_from_history}@example.com",
                "password": "correct-horse-battery-staple",
                "display_name": "Legacy Question Learner",
            },
        ).json()
        owner_id = auth["user"]["id"]
        headers = {"Authorization": f"Bearer {auth['access_token']}"}
        workspace_id = client.post(
            "/workspaces/resolve",
            headers=headers,
            json={"intent": "Study function limits"},
        ).json()["workspace"]["id"]
        app.state.workspace_learning_service.seed(
            owner_id,
            workspace_id,
            SeedRequest(
                goal="Master limits",
                exam_at=datetime.now(UTC) + timedelta(days=14),
                daily_minutes=30,
                topics=[TopicSeed(id="limits", name="函数极限")],
            ),
        )
        app.state.knowledge.add_document(
            owner_id=owner_id,
            project_id=workspace_id,
            material_id="material-1",
            filename="limits.md",
            text="函数极限是函数值趋近的目标，不要求函数在该点等于目标值。",
        )
        admin = ensure_admin(
            app.state.identity,
            email=f"legacy-admin-{restore_from_history}@example.com",
            password="correct-horse-battery-staple",
            display_name="Legacy Admin",
        ).user
        app.state.model_settings.save(
            admin.id,
            ModelSettings(
                base_url="https://api.openai.com/v1",
                model="study-model",
                api_key="secret-key-1234",
            ),
        )
        question = client.post(
            f"/workspaces/{workspace_id}/learning/question",
            headers=headers,
            json={"request_id": "legacy-question", "topic_id": "limits"},
        ).json()

        def simulate_legacy_record(data):
            progress = data["progress"]
            progress["topics"]["limits"].pop("answer_key_subject", None)
            for stored in progress["question_history"].values():
                stored["grading"].pop("answer_key_subject", None)
            if progress.get("pending_question") is not None:
                progress["pending_question"]["grading"].pop("answer_key_subject", None)
            if restore_from_history:
                progress["pending_question"] = None
            return data

        app.state.learning.mutate(owner_id, workspace_id, simulate_legacy_record)
        if restore_from_history:
            retry = client.post(
                f"/workspaces/{workspace_id}/learning/questions/{question['id']}/retry",
                headers=headers,
            )
            assert retry.status_code == 200

        answer = client.post(
            f"/workspaces/{workspace_id}/learning/answer",
            headers=headers,
            json={
                "attempt_id": f"legacy-attempt-{restore_from_history}",
                "question_id": question["id"],
                "answer": "函数极限是函数值趋近的目标，并且不要求在该点等于目标值。",
            },
        )
        stored = app.state.learning.get(owner_id, workspace_id).data["progress"]

    assert answer.status_code == 200
    assert answer.json()["mastery_updated"] is False
    assert stored["bkt_states"]["limits"]["p_mastery"] == 0.0


def test_question_model_work_runs_outside_database_transaction(tmp_path: Path) -> None:
    model = BlockingQuestionModel()
    app = create_app(
        Settings(data_root=tmp_path / "data", _env_file=None),
        learning_model_transport=model,
    )
    model.inspect_transaction = lambda: app.state.store._active_session.get() is not None

    with TestClient(app) as client:
        auth = client.post(
            "/auth/register",
            json={
                "email": "question-transaction@example.com",
                "password": "correct-horse-battery-staple",
                "display_name": "Learner",
            },
        ).json()
        headers = {"Authorization": f"Bearer {auth['access_token']}"}
        workspace_id = client.post(
            "/workspaces/resolve",
            headers=headers,
            json={"intent": "复习高数极限"},
        ).json()["workspace"]["id"]
        _add_workspace_material(
            app,
            auth["user"]["id"],
            workspace_id,
            text="函数极限描述自变量趋近某一点时函数值趋近的目标。",
        )
        admin = ensure_admin(
            app.state.identity,
            email="question-transaction-admin@example.com",
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
        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                first_pending = executor.submit(
                    client.post,
                    f"/workspaces/{workspace_id}/learning/question",
                    headers=headers,
                    json={"request_id": "outside-transaction"},
                )
                assert model.started.wait(timeout=2)
                second_pending = executor.submit(
                    client.post,
                    f"/workspaces/{workspace_id}/learning/question",
                    headers=headers,
                    json={"request_id": "outside-transaction"},
                )
                opened = client.get(
                    f"/workspaces/{workspace_id}/snapshot",
                    headers=headers,
                )
                snapshot = app.state.learning.get(auth["user"]["id"], workspace_id)
                assert snapshot.data["progress"]["seeded"] is True
                model.release.set()
                responses = [
                    first_pending.result(timeout=3),
                    second_pending.result(timeout=3),
                ]
        finally:
            model.release.set()

    assert [response.status_code for response in responses] == [200, 200]
    assert opened.status_code == 200
    assert responses[0].json() == responses[1].json()
    assert model.calls.count("QuestionModelOutput") == 1
    assert model.transaction_active is False


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
            "answer": (
                "极限描述函数值不断趋近的目标，例如自变量趋近零时，"
                "函数值可以趋近零，但不要求函数在该点等于零。"
            ),
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
        assert grade["mastery_updated"] is True
        assert grade["feedback"] == "回答正确，下一步练习形式化定义。"
        assert grade["strengths"] == ["准确说明趋近"]
        assert grade["gaps"] == ["可以补充形式化定义"]
        assert grade["grading_mode"] == "ai"
        assert grade["grounding"] == "material"
        assert grade["citations"] == ["material-1#0"]
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
    assert sorted(model.calls) == [
        "GradingModelOutput",
        "MaterialAnalysisModelOutput",
        "QuestionModelOutput",
        "TrustedAnswerKeyOutput",
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
        _add_workspace_material(app, auth["user"]["id"], workspace_id)
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


def test_retrying_one_question_cannot_update_mastery_or_difficulty_twice(
    tmp_path: Path,
) -> None:
    model = SequencedGradingLearningModel([40, 90])
    app = create_app(
        Settings(data_root=tmp_path / "data", _env_file=None),
        learning_model_transport=model,
    )

    with TestClient(app) as client:
        auth = client.post(
            "/auth/register",
            json={
                "email": "independent-evidence@example.com",
                "password": "correct-horse-battery-staple",
                "display_name": "Evidence Learner",
            },
        ).json()
        headers = {"Authorization": f"Bearer {auth['access_token']}"}
        owner_id = auth["user"]["id"]
        workspace_id = client.post(
            "/workspaces/resolve",
            headers=headers,
            json={"intent": "复习函数极限"},
        ).json()["workspace"]["id"]
        app.state.knowledge.add_document(
            owner_id=owner_id,
            project_id=workspace_id,
            material_id="material-1",
            filename="limits.txt",
            text="函数极限描述函数值趋近的目标，函数在该点不一定等于极限值。",
        )
        admin = ensure_admin(
            app.state.identity,
            email="evidence-admin@example.com",
            password="correct-horse-battery-staple",
            display_name="Evidence Admin",
        ).user
        app.state.model_settings.save(
            admin.id,
            ModelSettings(
                base_url="https://api.openai.com/v1",
                model="study-model",
                api_key="secret-key-1234",
            ),
        )
        question = client.post(
            f"/workspaces/{workspace_id}/learning/question",
            headers=headers,
            json={"request_id": "independent-question"},
        ).json()
        substantive_answer = (
            "函数极限描述函数值不断趋近的目标，例如自变量趋近零时，"
            "函数值可以趋近零，但不要求函数在该点等于零。"
        )
        first = client.post(
            f"/workspaces/{workspace_id}/learning/answer",
            headers=headers,
            json={
                "attempt_id": "independent-attempt-1",
                "question_id": question["id"],
                "answer": substantive_answer,
            },
        ).json()

        def evict_from_bounded_credit_cache(data):
            state = data["progress"]["bkt_states"][question["topic_id"]]
            state["credited_question_ids"] = [f"newer-question-{index}" for index in range(50)]
            return data

        app.state.learning.mutate(owner_id, workspace_id, evict_from_bounded_credit_cache)
        retried = client.post(
            f"/workspaces/{workspace_id}/learning/questions/{question['id']}/retry",
            headers=headers,
        ).json()
        second = client.post(
            f"/workspaces/{workspace_id}/learning/answer",
            headers=headers,
            json={
                "attempt_id": "independent-attempt-2",
                "question_id": retried["id"],
                "answer": substantive_answer,
            },
        ).json()

    assert first["mastery_updated"] is True
    assert second["mastery_updated"] is False
    assert second["mastery"] == first["mastery"]
    assert second["difficulty_level"] == first["difficulty_level"]


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
        _add_workspace_material(app, auth["user"]["id"], workspace_id)
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
        _add_workspace_material(app, auth["user"]["id"], workspace_id)
        response = client.post(
            f"/workspaces/{workspace_id}/learning/question",
            headers=headers,
            json={"request_id": "project-question-1", "mode": "project"},
        )

    assert response.status_code == 200
    assert response.json()["learning_mode"] == "project"


def test_workspace_case_task_without_matching_material_is_rejected(
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
        _add_workspace_material(
            app,
            auth["user"]["id"],
            workspace_id,
            text="Astronomy notes about stellar orbits and nebulae.",
        )
        response = client.post(
            f"/workspaces/{workspace_id}/learning/question",
            headers=headers,
            json={"request_id": "general-case-1", "mode": "case"},
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "material_insufficient"


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
        _add_workspace_material(
            app,
            auth["user"]["id"],
            workspace_id,
            text="Astronomy notes about stellar orbits and nebulae.",
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
            ),
        )
        response = client.post(
            f"/workspaces/{workspace_id}/learning/question",
            headers=headers,
            json={"request_id": "no-source-ai-1", "mode": "case"},
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "material_insufficient"
