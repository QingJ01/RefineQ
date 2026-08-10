"""Server-authored intelligence used only by the resettable evaluation sandbox."""

from __future__ import annotations

import json
from typing import Any

from refineq.knowledge.index import KnowledgeIndex
from refineq.learning.intelligence import (
    GeneratedQuestion,
    GradingResult,
    LearningIntelligenceService,
    RubricCriterion,
)
from refineq.learning.models import Grounding, LearningMode

_VERIFIABLE_ANSWER = '{"limit":2,"point_value":9,"equal":false}'
_VERIFIABLE_INSTRUCTION = (
    "Use the cited removable-hole example. Answer with only one JSON object using "
    'exactly these keys: {"limit":<number>,"point_value":<number>,"equal":<boolean>}.'
)


def _is_verifiable_answer(answer: str) -> bool:
    try:
        structured = json.loads(answer)
    except (TypeError, ValueError):
        return False
    return (
        isinstance(structured, dict)
        and set(structured) == {"limit", "point_value", "equal"}
        and type(structured["limit"]) is int
        and structured["limit"] == 2
        and type(structured["point_value"]) is int
        and structured["point_value"] == 9
        and structured["equal"] is False
    )


class EvaluationLearningIntelligence:
    """Use the product model path when healthy and a server-authored safe fallback."""

    def __init__(
        self,
        knowledge: KnowledgeIndex,
        *,
        primary: LearningIntelligenceService | None = None,
        model_settings: Any | None = None,
    ) -> None:
        self._knowledge = knowledge
        self._primary = primary
        self._model_settings = model_settings

    def _model_configured(self, owner_id: str) -> bool:
        if self._model_settings is None:
            return False
        try:
            return bool(self._model_settings.public(owner_id).configured)
        except Exception:
            return False

    def generate_question(
        self,
        *,
        owner_id: str,
        workspace_id: str,
        topic_id: str,
        topic_name: str,
        trusted_topic_subject: str | None = None,
        mastery: float,
        difficulty_level: int,
        learning_mode: LearningMode = LearningMode.CONCEPT,
        prior_feedback=None,
        recent_question_prompts: list[str] | None = None,
        variation_index: int | None = None,
    ) -> GeneratedQuestion:
        if self._primary is not None and self._model_configured(owner_id):
            candidate = self._primary.generate_question(
                owner_id=owner_id,
                workspace_id=workspace_id,
                topic_id=topic_id,
                topic_name=topic_name,
                trusted_topic_subject=trusted_topic_subject,
                mastery=mastery,
                difficulty_level=difficulty_level,
                learning_mode=learning_mode,
                prior_feedback=prior_feedback,
                recent_question_prompts=recent_question_prompts,
                variation_index=variation_index,
            )
            if (
                candidate.mode == "ai"
                and candidate.grounding is Grounding.MATERIAL
                and candidate.sources
                and candidate.citations
            ):
                return candidate.model_copy(
                    update={
                        "prompt": f"{candidate.prompt}\n\n{_VERIFIABLE_INSTRUCTION}",
                        "expected_answer": _VERIFIABLE_ANSWER,
                        "answer_key_trusted": True,
                        "rubric": [
                            RubricCriterion(criterion="Identifies the limit", max_points=40),
                            RubricCriterion(criterion="Identifies the point value", max_points=40),
                            RubricCriterion(criterion="Compares the values", max_points=20),
                        ],
                    }
                )
        del mastery, prior_feedback, recent_question_prompts, variation_index
        sources = self._knowledge.search(
            owner_id=owner_id,
            project_id=workspace_id,
            query="function limit approaches point continuity",
            limit=3,
        )
        return GeneratedQuestion(
            topic_id=topic_id,
            topic_name=topic_name,
            difficulty_level=difficulty_level,
            prompt=_VERIFIABLE_INSTRUCTION,
            expected_answer=_VERIFIABLE_ANSWER,
            answer_key_trusted=True,
            answer_key_subject=trusted_topic_subject,
            rubric=[
                RubricCriterion(criterion="Identifies the limit", max_points=40),
                RubricCriterion(criterion="Identifies the point value", max_points=40),
                RubricCriterion(criterion="Compares the values", max_points=20),
            ],
            explanation=(
                "A limit describes nearby behavior, while the function value describes "
                "the value assigned exactly at the point."
            ),
            citations=[source.citation_id for source in sources],
            sources=sources,
            grounding=Grounding.MATERIAL if sources else Grounding.GENERAL,
            learning_mode=learning_mode,
            mode="fallback",
        )

    def grade_answer(
        self,
        *,
        owner_id: str,
        question: GeneratedQuestion,
        answer: str,
    ) -> GradingResult:
        verified = _is_verifiable_answer(answer)
        if not verified:
            gap = (
                "Return the three requested fields with the limit, assigned point value, "
                "and whether they are equal."
            )
            return GradingResult(
                score=35,
                passed=False,
                strengths=[],
                gaps=[gap],
                misconceptions=[],
                feedback=gap,
                citations=question.citations,
                mode="fallback",
                mastery_evidence=False,
            )
        if self._primary is not None and question.mode == "ai" and self._model_configured(owner_id):
            candidate = self._primary.grade_answer(
                owner_id=owner_id,
                question=question,
                answer=answer,
            )
            if candidate.mode == "ai":
                deterministic_feedback = (
                    "The typed response correctly identifies and compares both values."
                )
                model_citations = [
                    citation for citation in candidate.citations if citation in question.citations
                ]
                return GradingResult(
                    score=100,
                    passed=True,
                    strengths=(
                        candidate.strengths
                        if candidate.passed and candidate.strengths
                        else [deterministic_feedback]
                    ),
                    gaps=candidate.gaps if candidate.passed else [],
                    misconceptions=candidate.misconceptions if candidate.passed else [],
                    feedback=candidate.feedback if candidate.passed else deterministic_feedback,
                    citations=model_citations or question.citations,
                    mode="ai",
                    mastery_evidence=True,
                )
        del owner_id
        strengths = ["The response correctly identifies and compares both values."]
        return GradingResult(
            score=100,
            passed=True,
            strengths=strengths,
            gaps=[],
            misconceptions=[],
            feedback=" ".join(strengths),
            citations=question.citations,
            mode="fallback",
            mastery_evidence=True,
        )
