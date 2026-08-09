from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from refineq.agent.settings import ModelNotConfiguredError
from refineq.learning.personalized import TargetedPlanRequest, TargetedPlanService
from refineq.materials.models import MaterialAnalysis, MaterialType

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


class UnconfiguredSettings:
    def load(self, _owner_id):
        raise ModelNotConfiguredError


class UnusedTransport:
    def complete(self, **_):
        raise AssertionError("transport should not run without model settings")


def request(material_id: str, topic: str) -> TargetedPlanRequest:
    return TargetedPlanRequest(
        material_id=material_id,
        focus_topics=[topic],
        exam_at=EXAM_AT,
        daily_minutes=45,
        study_weekdays=[0, 1, 2, 3, 4, 5, 6],
        preferred_hour=9,
        timezone_offset_minutes=480,
    )


def test_new_material_plan_is_merged_into_existing_calendar() -> None:
    learning = FakeLearning()
    service = TargetedPlanService(
        learning, FakeAnalyses(), UnconfiguredSettings(), UnusedTransport()
    )

    first = service.generate("learner", "workspace_demo", request("material_one", "极限"))
    second = service.generate("learner", "workspace_demo", request("material_two", "导数"))

    assert len(second.sessions) == len(first.sessions) * 2
    assert {session.topic_id for session in first.sessions} < {
        session.topic_id for session in second.sessions
    }
    assert second == service.generate("learner", "workspace_demo", request("material_two", "导数"))
    assert first.sessions[0].planned_at.hour == 1
    ordered = sorted(second.sessions, key=lambda session: session.planned_at)
    assert all(
        left.planned_at + timedelta(minutes=left.minutes) <= right.planned_at
        for left, right in zip(ordered, ordered[1:], strict=False)
        if left.planned_at.date() == right.planned_at.date()
    )
