"""Deterministic routing tests for invisible personal learning spaces."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from refineq.workspaces.models import LearningWorkspace
from refineq.workspaces.routing import route_workspace

NOW = datetime(2026, 8, 6, 4, 0, tzinfo=UTC)


def _workspace(
    workspace_id: str,
    *,
    title: str,
    subject: str,
    keywords: list[str],
    minutes_ago: int,
) -> LearningWorkspace:
    return LearningWorkspace(
        id=workspace_id,
        title=title,
        subject=subject,
        goal=f"学习{title}",
        topics=[title],
        keywords=keywords,
        routing_summary=f"与{title}有关",
        created_at=NOW - timedelta(days=2),
        last_active_at=NOW - timedelta(minutes=minutes_ago),
    )


def test_same_subject_intent_reuses_the_matching_workspace() -> None:
    spaces = [
        _workspace(
            "math",
            title="高等数学",
            subject="mathematics",
            keywords=["高数", "极限", "导数"],
            minutes_ago=30,
        ),
        _workspace(
            "english",
            title="英语四级",
            subject="language",
            keywords=["英语", "四级", "单词"],
            minutes_ago=5,
        ),
    ]

    decision = route_workspace("继续复习高数极限", spaces)

    assert decision.action == "switched"
    assert decision.workspace_id == "math"
    assert decision.confidence >= 0.8


def test_unrelated_subject_creates_a_new_workspace() -> None:
    spaces = [
        _workspace(
            "math",
            title="高等数学",
            subject="mathematics",
            keywords=["高数", "极限"],
            minutes_ago=5,
        )
    ]

    decision = route_workspace("我要准备 Python 数据结构面试", spaces)

    assert decision.action == "created"
    assert decision.workspace_id is None
    assert decision.subject == "programming"
    assert "Python" in decision.title


def test_low_information_intent_reuses_the_latest_workspace() -> None:
    spaces = [
        _workspace(
            "math",
            title="高等数学",
            subject="mathematics",
            keywords=["高数"],
            minutes_ago=20,
        ),
        _workspace(
            "english",
            title="英语四级",
            subject="language",
            keywords=["英语"],
            minutes_ago=2,
        ),
    ]

    decision = route_workspace("继续学习", spaces)

    assert decision.action == "reused"
    assert decision.workspace_id == "english"
    assert decision.confidence < 0.7


def test_broad_programming_subject_does_not_merge_different_languages() -> None:
    spaces = [
        _workspace(
            "python",
            title="Python learning",
            subject="programming",
            keywords=["python", "functions", "typing"],
            minutes_ago=3,
        )
    ]

    decision = route_workspace("Learn Rust ownership and borrowing", spaces)

    assert decision.action == "created"
    assert decision.workspace_id is None
    assert decision.title.startswith("Rust")


def test_english_exam_goal_uses_meaningful_topics_instead_of_stopwords() -> None:
    decision = route_workspace(
        "I have a calculus exam in two weeks and want to review limits today",
        [],
    )

    assert decision.subject == "mathematics"
    assert decision.topics[0] == "limits"
    assert "and" not in decision.keywords
    assert "exam" not in decision.topics


def test_product_and_operations_goals_become_capability_workspaces() -> None:
    product = route_workspace("Learn product thinking and validate user needs", [])
    operations = route_workspace("Practice growth operations and campaign analysis", [])

    assert product.subject == "product"
    assert product.title == "产品思维"
    assert product.topics[0] == "用户需求验证"
    assert "thinking" not in product.topics
    assert operations.subject == "operations"
    assert operations.title == "运营思维"
    assert "增长实验" in operations.topics
    assert "活动复盘" in operations.topics


def test_writing_and_research_goals_are_first_class_capabilities() -> None:
    writing = route_workspace("Improve structured writing and argumentation", [])
    research = route_workspace("Learn research synthesis and literature review", [])

    assert writing.subject == "writing"
    assert writing.title == "写作能力"
    assert writing.topics[0] == "结构化表达"
    assert research.subject == "research"
    assert research.title == "研究能力"
    assert "证据检索与综合" in research.topics
