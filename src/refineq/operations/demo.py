"""Deterministic, idempotent demo data for the complete learning loop."""

from __future__ import annotations

import os
import tempfile
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from refineq.identity.service import AccountExistsError, IdentityService
from refineq.knowledge.index import KnowledgeIndex, MaterialNotFoundError
from refineq.learning.models import KnowledgeType
from refineq.learning.service import (
    AnswerRequest,
    DiagnosticRequest,
    DiagnosticResultInput,
    LearningService,
    SeedRequest,
    TopicSeed,
)
from refineq.storage.json_store import (
    AtomicJsonStore,
    RecordAlreadyExistsError,
    RecordNotFoundError,
)
from refineq.storage.learning import LearningRepository
from refineq.storage.projects import ProjectRepository

DEMO_EMAIL = "learner@refineq.local"
DEMO_PASSWORD = "learn-with-refineq"
DEMO_PROJECT_ID = "refineq-demo"
DEMO_MATERIAL_ID = "demo-material"


@dataclass(frozen=True, slots=True)
class DemoResult:
    owner_id: str
    project_id: str
    email: str
    password: str


def _write_once(path: Path, payload: bytes) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.stem}-",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        with suppress(FileExistsError):
            os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def seed_demo(data_root: Path) -> DemoResult:
    """Create one presentation-ready learner without resetting an existing run."""

    root = data_root.expanduser().resolve()
    identity = IdentityService(root)
    try:
        user = identity.register(
            email=DEMO_EMAIL,
            password=DEMO_PASSWORD,
            display_name="RefineQ Learner",
        )
    except AccountExistsError:
        user = identity.authenticate(email=DEMO_EMAIL, password=DEMO_PASSWORD)

    store = AtomicJsonStore(root)
    projects = ProjectRepository(store)
    learning = LearningRepository(store)
    service = LearningService(projects, learning)
    with suppress(RecordAlreadyExistsError):
        projects.create(user.id, DEMO_PROJECT_ID, name="Calculus Sprint")

    try:
        learning_record = learning.get(user.id, DEMO_PROJECT_ID)
        seeded = bool(learning_record.data.get("progress", {}).get("seeded"))
    except RecordNotFoundError:
        seeded = False

    if not seeded:
        service.seed(
            user.id,
            DEMO_PROJECT_ID,
            SeedRequest(
                goal="Master the calculus foundations for the final exam",
                exam_at=datetime.now(UTC) + timedelta(days=14),
                daily_minutes=45,
                topics=[
                    TopicSeed(
                        id="derivatives",
                        name="Derivative",
                        knowledge_type=KnowledgeType.CONCEPT,
                    ),
                    TopicSeed(
                        id="chain-rule",
                        name="Chain Rule",
                        knowledge_type=KnowledgeType.PROCEDURE,
                    ),
                    TopicSeed(
                        id="integrals",
                        name="Integral",
                        knowledge_type=KnowledgeType.CONCEPT,
                    ),
                ],
            ),
        )
        service.diagnose(
            user.id,
            DEMO_PROJECT_ID,
            DiagnosticRequest(
                diagnostic_id="demo-diagnostic",
                results=[
                    DiagnosticResultInput(topic_id="derivatives", is_correct=True),
                    DiagnosticResultInput(topic_id="chain-rule", is_correct=False),
                    DiagnosticResultInput(topic_id="integrals", is_correct=False),
                ],
            ),
        )
        service.create_plan(user.id, DEMO_PROJECT_ID)
        question = service.next_question(user.id, DEMO_PROJECT_ID)
        service.submit_answer(
            user.id,
            DEMO_PROJECT_ID,
            AnswerRequest(
                attempt_id="demo-attempt",
                question_id=question.id,
                answer="I need another example before I can explain this.",
            ),
        )

    knowledge = KnowledgeIndex(root)
    try:
        knowledge.get_material(
            owner_id=user.id,
            project_id=DEMO_PROJECT_ID,
            material_id=DEMO_MATERIAL_ID,
        )
    except MaterialNotFoundError:
        material_text = (
            "A derivative measures a local rate of change.\n"
            "The chain rule differentiates a composition of functions.\n"
            "A definite integral accumulates signed area over an interval."
        )
        material_path = (
            root
            / "users"
            / user.id
            / "knowledge"
            / "projects"
            / DEMO_PROJECT_ID
            / "materials"
            / f"{DEMO_MATERIAL_ID}.txt"
        )
        _write_once(material_path, material_text.encode("utf-8"))
        knowledge.add_document(
            owner_id=user.id,
            project_id=DEMO_PROJECT_ID,
            material_id=DEMO_MATERIAL_ID,
            filename="calculus-notes.txt",
            text=material_text,
        )

    return DemoResult(
        owner_id=user.id,
        project_id=DEMO_PROJECT_ID,
        email=DEMO_EMAIL,
        password=DEMO_PASSWORD,
    )
