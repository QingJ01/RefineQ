"""Evidence-based practice-difficulty policy."""

from __future__ import annotations

from refineq.learning.models import DifficultyState


def update_difficulty(
    state: DifficultyState,
    *,
    is_correct: bool,
    question_id: str,
) -> DifficultyState:
    """Adjust one level only after two independent pieces of evidence."""

    question_id = question_id.strip()
    if not question_id:
        raise ValueError("question_id must not be blank")

    if is_correct:
        correct_ids = list(state.recent_correct_question_ids)
        if question_id not in correct_ids:
            correct_ids.append(question_id)
        if len(correct_ids) >= 2:
            return DifficultyState(level=min(5, state.level + 1))
        return DifficultyState(
            level=state.level,
            recent_correct_question_ids=correct_ids,
        )

    wrong_ids = list(state.recent_wrong_question_ids)
    if question_id not in wrong_ids:
        wrong_ids.append(question_id)
    wrong_count = len(wrong_ids)
    if wrong_count >= 2:
        return DifficultyState(level=max(1, state.level - 1))
    return DifficultyState(
        level=state.level,
        consecutive_wrong=wrong_count,
        recent_wrong_question_ids=wrong_ids,
    )
