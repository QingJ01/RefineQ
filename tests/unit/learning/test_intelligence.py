"""Unit contracts for grounded question generation and explainable grading."""

from __future__ import annotations

from pathlib import Path

from refineq.agent.settings import ModelSettings, ModelSettingsRepository
from refineq.knowledge.index import KnowledgeIndex, SearchResult
from refineq.learning.intelligence import (
    GeneratedQuestion,
    GradingResult,
    LearningIntelligenceService,
    fallback_grade,
    fallback_question,
)
from refineq.learning.models import LearningMode


class FakeStructuredTransport:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def complete(self, *, settings, messages, response_model):
        del settings, messages
        self.calls.append(response_model.__name__)
        if response_model.__name__ == "QuestionModelOutput":
            return response_model.model_validate(
                {
                    "prompt": "解释函数极限，并说明趋近与等于的区别。",
                    "expected_answer": "极限描述函数值趋近的目标，不要求在该点取到目标值。",
                    "rubric": [
                        {"criterion": "解释趋近", "max_points": 60},
                        {"criterion": "区分等于", "max_points": 40},
                    ],
                    "explanation": "题目检查概念边界。",
                    "citations": ["limits-notes#0", "invented#9"],
                }
            )
        return response_model.model_validate(
            {
                "score": 82,
                "strengths": ["说明了趋近"],
                "gaps": ["没有明确讨论函数在该点的取值"],
                "misconceptions": [],
                "feedback": "概念基本正确，再补充函数值与极限值可以不同。",
                "citations": ["limits-notes#0", "invented#9"],
            }
        )


def _service(tmp_path: Path, *, configured: bool = True):
    knowledge = KnowledgeIndex(tmp_path)
    knowledge.add_document(
        owner_id="owner",
        project_id="calculus",
        material_id="limits-notes",
        filename="limits.md",
        text="函数极限描述自变量趋近某点时函数值所趋近的值，不要求函数在该点取到该值。",
    )
    settings = ModelSettingsRepository(tmp_path)
    if configured:
        settings.save(
            "owner",
            ModelSettings(
                base_url="https://api.openai.com/v1",
                model="study-model",
                api_key="secret-key-1234",
            ),
        )
    transport = FakeStructuredTransport()
    return LearningIntelligenceService(knowledge, settings, transport), transport


def test_generated_question_is_grounded_and_filters_invented_citations(
    tmp_path: Path,
) -> None:
    service, transport = _service(tmp_path)

    question = service.generate_question(
        owner_id="owner",
        workspace_id="calculus",
        topic_id="limits",
        topic_name="函数极限",
        mastery=0.25,
        difficulty_level=2,
    )

    assert isinstance(question, GeneratedQuestion)
    assert question.mode == "ai"
    assert question.citations == ["limits-notes#0"]
    assert question.expected_answer
    assert sum(item.max_points for item in question.rubric) == 100
    assert transport.calls == ["QuestionModelOutput"]


def test_generated_task_preserves_a_domain_neutral_learning_mode(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)

    task = service.generate_question(
        owner_id="owner",
        workspace_id="calculus",
        topic_id="discovery",
        topic_name="用户需求验证",
        mastery=0.25,
        difficulty_level=2,
        learning_mode=LearningMode.CASE,
    )

    assert task.learning_mode is LearningMode.CASE


def test_fallback_tasks_change_with_the_selected_learning_mode() -> None:
    source = SearchResult(
        citation_id="interview#0",
        material_id="interview",
        filename="interview.txt",
        chunk_index=0,
        text="用户反复要求导出，但真实目标是稳定完成每周汇报。",
        score=1.0,
    )

    case = fallback_question(
        topic_id="needs",
        topic_name="用户需求验证",
        difficulty_level=2,
        sources=[source],
        learning_mode=LearningMode.CASE,
    )
    project = fallback_question(
        topic_id="needs",
        topic_name="用户需求验证",
        difficulty_level=2,
        sources=[source],
        learning_mode=LearningMode.PROJECT,
    )

    assert "场景" in case.prompt
    assert "表面诉求" in case.prompt
    assert "最小方案" in project.prompt
    assert "验证标准" in project.prompt
    assert case.prompt != project.prompt


def test_question_generation_falls_back_when_model_is_not_configured(
    tmp_path: Path,
) -> None:
    service, transport = _service(tmp_path, configured=False)

    question = service.generate_question(
        owner_id="owner",
        workspace_id="calculus",
        topic_id="limits",
        topic_name="函数极限",
        mastery=0.25,
        difficulty_level=2,
    )

    assert question.mode == "fallback"
    assert question.prompt
    assert question.expected_answer
    assert transport.calls == []


def test_ai_grading_returns_explainable_feedback_and_valid_citations(
    tmp_path: Path,
) -> None:
    service, transport = _service(tmp_path)
    question = service.generate_question(
        owner_id="owner",
        workspace_id="calculus",
        topic_id="limits",
        topic_name="函数极限",
        mastery=0.25,
        difficulty_level=2,
    )

    result = service.grade_answer(
        owner_id="owner",
        question=question,
        answer="极限是函数值不断趋近的目标，但函数在该点不一定等于极限。",
    )

    assert isinstance(result, GradingResult)
    assert result.mode == "ai"
    assert result.score == 82
    assert result.passed is True
    assert result.strengths == ["说明了趋近"]
    assert result.citations == ["limits-notes#0"]
    assert transport.calls == ["QuestionModelOutput", "GradingModelOutput"]


def test_fallback_grading_rejects_topic_echo_and_generic_filler() -> None:
    question = fallback_question(
        topic_id="limits",
        topic_name="Limits",
        difficulty_level=2,
        sources=[],
    )

    echo = fallback_grade(question, "Limits")
    filler = fallback_grade(
        question,
        "For example this topic is very important and I think it has many useful applications.",
    )

    assert echo.passed is False
    assert echo.score < question.pass_score
    assert echo.mastery_evidence is False
    assert filler.passed is False
    assert filler.mastery_evidence is False


def test_fallback_grading_can_pass_substantive_grounded_explanation() -> None:
    question = fallback_question(
        topic_id="limits",
        topic_name="Limits",
        difficulty_level=2,
        sources=[
            SearchResult(
                citation_id="notes#0",
                material_id="notes",
                filename="notes.txt",
                chunk_index=0,
                text="A limit describes the value a function approaches near a point.",
                score=1.0,
            )
        ],
    )

    result = fallback_grade(
        question,
        "A limit describes the value a function approaches near a point. "
        "For example, as x approaches zero, x squared approaches zero.",
    )

    assert result.passed is True
    assert result.score >= question.pass_score
    assert result.mastery_evidence is True
