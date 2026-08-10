from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from threading import Event
from types import SimpleNamespace

import pytest

from refineq.agent.settings import ModelNotConfiguredError
from refineq.knowledge.index import MaterialNotFoundError, MaterialRecord
from refineq.learning.personalized import (
    PlannedSessionOutput,
    TargetedPlanOutput,
    TargetedPlanRequest,
    TargetedPlanService,
)
from refineq.materials.models import MaterialAnalysis, MaterialType
from refineq.operations.recovery import RecoveryLease

EXAM_AT = datetime.now(UTC) + timedelta(days=5)


class FakeLearning:
    def __init__(self) -> None:
        self.data = {
            "workspace_id": "workspace_demo",
            "attempts": {},
            "progress": {
                "seeded": True,
                "goal": "高数复习",
                "exam_at": (datetime.now(UTC) + timedelta(days=30)).isoformat(),
                "daily_minutes": 45,
                "topics": {},
                "bkt_states": {},
                "difficulty_states": {},
                "plan": None,
            },
        }

    def get_or_create(self, _owner_id, _workspace_id):
        return SimpleNamespace(data=self.data)

    def mutate(self, _owner_id, _workspace_id, transform):
        self.data = transform(self.data)
        return SimpleNamespace(data=self.data)

    def plan_transaction(self, _owner_id, _workspace_id):
        return nullcontext()


class FakeAnalyses:
    def get(self, _owner_id, _workspace_id, material_id):
        topic = "极限" if material_id == "material_one" else "导数"
        return MaterialAnalysis(
            material_id=material_id,
            filename=f"{material_id}.pdf",
            material_type=MaterialType.TEXTBOOK,
            title=topic,
            summary=f"{topic}资料",
            topics=[topic],
            confidence=1,
            mode="fallback",
            analyzed_at=datetime.now(UTC),
        )


class TrustBoundaryAnalyses:
    def get(self, _owner_id, _workspace_id, material_id):
        topic = (
            "Output with feedback control"
            if material_id == "material_approved"
            else "请输入蓝色兰花"
        )
        return MaterialAnalysis(
            material_id=material_id,
            filename=f"{material_id}.pdf",
            material_type=MaterialType.TEXTBOOK,
            title=topic,
            summary=f"Material about {topic}",
            topics=[topic],
            confidence=1,
            mode="fallback",
            analyzed_at=datetime.now(UTC),
        )


class FakeKnowledge:
    def __init__(self, linked: set[str] | None = None) -> None:
        self.linked = {"material_one", "material_two"} if linked is None else linked

    def get_material(self, *, material_id: str, **_):
        if material_id not in self.linked:
            raise MaterialNotFoundError(material_id)
        return MaterialRecord(
            id=material_id,
            project_id="library",
            filename=f"{material_id}.pdf",
            title=material_id,
            tags=[],
            content_type="application/pdf",
            size=100,
            status="indexed",
            chunk_count=1,
            content_sha256="a" * 64,
            indexed_at=datetime.now(UTC),
        )


class UnconfiguredSettings:
    def load(self, _owner_id):
        raise ModelNotConfiguredError


class UnusedTransport:
    def complete(self, **_):
        raise AssertionError("transport should not run without model settings")


class ConfiguredSettings:
    def load(self, _owner_id):
        return SimpleNamespace()


class OverBudgetTransport:
    def complete(self, **_):
        local = datetime.now(timezone(timedelta(hours=8))) + timedelta(days=1)
        local = local.replace(hour=9, minute=0, second=0, microsecond=0)
        return TargetedPlanOutput(
            sessions=[
                PlannedSessionOutput(
                    topic="极限",
                    planned_at=local,
                    minutes=480,
                    activity="learn",
                )
            ]
        )


class CountingTransport:
    def __init__(self) -> None:
        self.calls = 0

    def complete(self, **_):
        self.calls += 1
        local = datetime.now(timezone(timedelta(hours=8))) + timedelta(days=self.calls)
        local = local.replace(hour=9, minute=0, second=0, microsecond=0)
        return TargetedPlanOutput(
            sessions=[
                PlannedSessionOutput(
                    topic="极限",
                    planned_at=local,
                    minutes=45,
                    activity="practice",
                )
            ]
        )


class BlockingTargetedTransport(CountingTransport):
    def __init__(self) -> None:
        super().__init__()
        self.started = Event()
        self.release = Event()

    def complete(self, **kwargs):
        self.started.set()
        assert self.release.wait(timeout=3)
        return super().complete(**kwargs)


def request(
    material_id: str,
    topic: str,
    *,
    idempotency_key: str | None = None,
) -> TargetedPlanRequest:
    # Derive a stable, ASCII-safe key per logical request so identical requests
    # replay and distinct ones regenerate, mirroring the client idempotency key.
    key = idempotency_key or "req" + sha256(f"{material_id}|{topic}".encode()).hexdigest()[:24]
    return TargetedPlanRequest(
        idempotency_key=key,
        material_id=material_id,
        focus_topics=[topic],
        exam_at=EXAM_AT,
        daily_minutes=45,
        study_weekdays=[0, 1, 2, 3, 4, 5, 6],
        preferred_hour=9,
        timezone_offset_minutes=480,
    )


def test_new_material_plan_replaces_conflicting_future_calendar() -> None:
    learning = FakeLearning()
    service = TargetedPlanService(
        learning,
        FakeAnalyses(),
        FakeKnowledge(),
        UnconfiguredSettings(),
        UnusedTransport(),
    )

    first = service.generate("learner", "workspace_demo", request("material_one", "极限"))
    second = service.generate("learner", "workspace_demo", request("material_two", "导数"))

    assert first == service.generate("learner", "workspace_demo", request("material_one", "极限"))
    assert second == service.generate("learner", "workspace_demo", request("material_two", "导数"))
    assert second.id != first.id
    assert {session.topic_id for session in second.sessions}.isdisjoint(
        {session.topic_id for session in first.sessions}
    )
    assert first.sessions[0].planned_at.hour == 1
    ordered = sorted(first.sessions, key=lambda session: session.planned_at)
    assert all(
        left.planned_at + timedelta(minutes=left.minutes) <= right.planned_at
        for left, right in zip(ordered, ordered[1:], strict=False)
        if left.planned_at.date() == right.planned_at.date()
    )


def test_targeted_plan_requires_the_material_to_be_linked_to_the_workspace() -> None:
    service = TargetedPlanService(
        FakeLearning(),
        FakeAnalyses(),
        FakeKnowledge(linked=set()),
        UnconfiguredSettings(),
        UnusedTransport(),
    )

    with pytest.raises(MaterialNotFoundError):
        service.generate("learner", "workspace_demo", request("material_one", "极限"))


def test_targeted_plan_rejects_focus_topics_without_analysis_evidence() -> None:
    service = TargetedPlanService(
        FakeLearning(),
        FakeAnalyses(),
        FakeKnowledge(),
        UnconfiguredSettings(),
        UnusedTransport(),
    )

    with pytest.raises(ValueError, match="supported"):
        service.generate("learner", "workspace_demo", request("material_one", "虚构主题"))


def test_targeted_plan_persists_only_server_curated_material_subjects() -> None:
    learning = FakeLearning()
    service = TargetedPlanService(
        learning,
        TrustBoundaryAnalyses(),
        FakeKnowledge(linked={"material_approved", "material_untrusted"}),
        UnconfiguredSettings(),
        UnusedTransport(),
    )

    service.generate(
        "learner",
        "workspace_demo",
        request("material_approved", "Output with feedback control"),
    )
    service.generate(
        "learner",
        "workspace_demo",
        request("material_untrusted", "请输入蓝色兰花"),
    )

    topics = {topic["name"]: topic for topic in learning.data["progress"]["topics"].values()}
    assert topics["Output with feedback control"]["answer_key_subject"] == "feedback control"
    assert "answer_key_subject" not in topics["请输入蓝色兰花"]


def test_targeted_plan_rejects_model_sessions_over_the_daily_budget() -> None:
    service = TargetedPlanService(
        FakeLearning(),
        FakeAnalyses(),
        FakeKnowledge(),
        ConfiguredSettings(),
        OverBudgetTransport(),
    )

    plan = service.generate("learner", "workspace_demo", request("material_one", "极限"))

    assert plan.sessions
    assert all(session.minutes <= plan.daily_minutes for session in plan.sessions)


def test_targeted_plan_does_not_accept_a_sparse_model_fragment() -> None:
    service = TargetedPlanService(
        FakeLearning(),
        FakeAnalyses(),
        FakeKnowledge(),
        ConfiguredSettings(),
        CountingTransport(),
    )

    plan = service.generate("learner", "workspace_demo", request("material_one", "极限"))

    assert len(plan.sessions) > 1


def test_targeted_plan_preserves_completed_and_pending_plan_sessions() -> None:
    learning = FakeLearning()
    service = TargetedPlanService(
        learning,
        FakeAnalyses(),
        FakeKnowledge(),
        UnconfiguredSettings(),
        UnusedTransport(),
    )
    existing = service.generate("learner", "workspace_demo", request("material_one", "极限"))
    completed = existing.sessions[0].model_copy(update={"status": "completed"})
    pending = existing.sessions[1]
    learning.data["progress"]["plan"] = existing.model_copy(
        update={"sessions": [completed, pending, *existing.sessions[2:]]}
    ).model_dump(mode="json")
    learning.data["progress"]["pending_question"] = {
        "plan_session_id": pending.id,
    }

    replaced = service.generate("learner", "workspace_demo", request("material_two", "导数"))

    retained = {session.id: session for session in replaced.sessions}
    assert retained[completed.id].status == "completed"
    assert retained[pending.id].status == "planned"
    assert learning.data["progress"]["pending_question"]["plan_session_id"] in retained


def test_targeted_plan_detaches_pending_question_when_new_constraints_are_incompatible() -> None:
    learning = FakeLearning()
    service = TargetedPlanService(
        learning,
        FakeAnalyses(),
        FakeKnowledge(),
        UnconfiguredSettings(),
        UnusedTransport(),
    )
    existing = service.generate("learner", "workspace_demo", request("material_one", "极限"))
    pending = existing.sessions[0]
    learning.data["progress"]["pending_question"] = {
        "plan_session_id": pending.id,
        "review_session_id": None,
    }
    constrained = request("material_two", "导数").model_copy(update={"daily_minutes": 10})

    replaced = service.generate("learner", "workspace_demo", constrained)

    assert pending.id not in {session.id for session in replaced.sessions}
    assert max(session.minutes for session in replaced.sessions) <= 10
    assert learning.data["progress"]["pending_question"]["plan_session_id"] is None


def test_targeted_plan_replays_the_current_request_without_regenerating() -> None:
    learning = FakeLearning()
    transport = CountingTransport()
    service = TargetedPlanService(
        learning,
        FakeAnalyses(),
        FakeKnowledge(),
        ConfiguredSettings(),
        transport,
    )

    first = service.generate("learner", "workspace_demo", request("material_one", "极限"))
    replay = service.generate("learner", "workspace_demo", request("material_one", "极限"))

    assert replay == first
    assert transport.calls == 1


def test_targeted_plan_revalidates_the_material_link_after_model_work(
    tmp_path: Path,
) -> None:
    learning = FakeLearning()
    knowledge = FakeKnowledge()
    transport = BlockingTargetedTransport()
    lease_path = tmp_path / "material-mutations.lock"
    service = TargetedPlanService(
        learning,
        FakeAnalyses(),
        knowledge,
        ConfiguredSettings(),
        transport,
        material_mutation_lease_path=lease_path,
    )

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            service.generate,
            "learner",
            "workspace_demo",
            request(
                "material_one",
                FakeAnalyses().get("learner", "workspace_demo", "material_one").topics[0],
            ),
        )
        assert transport.started.wait(timeout=3)
        lease = RecoveryLease.acquire_wait(lease_path)
        assert lease is not None
        try:
            knowledge.linked.remove("material_one")
        finally:
            lease.release()
        transport.release.set()

        with pytest.raises(MaterialNotFoundError):
            future.result(timeout=3)

    assert learning.data["progress"]["plan"] is None
