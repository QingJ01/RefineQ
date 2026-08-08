"""Deterministic, idempotent demo data for the complete learning loop."""

from __future__ import annotations

import os
import tempfile
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from refineq.database.engine import Database
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
from refineq.storage.json_store import RecordAlreadyExistsError, RecordNotFoundError
from refineq.storage.learning import LearningRepository
from refineq.storage.sql_store import SqlRecordStore
from refineq.storage.workspaces import WorkspaceRepository

DEMO_WORKSPACE_ID = "refineq-demo"
DEMO_MATERIAL_ID = "demo-material"


@dataclass(frozen=True, slots=True)
class DemoResult:
    owner_id: str
    workspace_id: str
    email: str


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


def seed_demo(
    database: Database,
    data_root: Path,
    *,
    email: str,
    password: str,
) -> DemoResult:
    """Create one presentation-ready learner without resetting an existing run."""

    root = data_root.expanduser().resolve()
    identity = IdentityService(database)
    try:
        user = identity.register(
            email=email,
            password=password,
            display_name="RefineQ Learner",
        )
    except AccountExistsError:
        user = identity.authenticate(email=email, password=password)

    store = SqlRecordStore(database)
    workspaces = WorkspaceRepository(store)
    learning = LearningRepository(store)
    service = LearningService(workspaces, learning)
    with suppress(RecordAlreadyExistsError):
        workspaces.create(
            user.id,
            DEMO_WORKSPACE_ID,
            title="计算机组成原理冲刺",
            subject="计算机组成原理",
            goal="准备 10 月 25 日的计算机组成原理期中考试",
            topics=["流水线", "缓存", "存储层次"],
            keywords=["计算机组成原理", "流水线", "缓存", "存储层次"],
            routing_summary="仅用于演示的预置学习空间，不代表真实用户或访谈证据。",
        )

    try:
        learning_record = learning.get(user.id, DEMO_WORKSPACE_ID)
        seeded = bool(learning_record.data.get("progress", {}).get("seeded"))
    except RecordNotFoundError:
        seeded = False

    if not seeded:
        now = datetime.now(UTC)
        exam_at = datetime(now.year, 10, 25, 12, tzinfo=UTC)
        if exam_at <= now:
            exam_at = exam_at.replace(year=now.year + 1)
        service.seed(
            user.id,
            DEMO_WORKSPACE_ID,
            SeedRequest(
                goal="准备 10 月 25 日的计算机组成原理期中考试",
                exam_at=exam_at,
                daily_minutes=90,
                topics=[
                    TopicSeed(
                        id="pipeline",
                        name="流水线",
                        knowledge_type=KnowledgeType.CONCEPT,
                    ),
                    TopicSeed(
                        id="cache",
                        name="缓存",
                        knowledge_type=KnowledgeType.PROCEDURE,
                    ),
                    TopicSeed(
                        id="memory-hierarchy",
                        name="存储层次",
                        knowledge_type=KnowledgeType.CONCEPT,
                    ),
                ],
            ),
        )
        service.diagnose(
            user.id,
            DEMO_WORKSPACE_ID,
            DiagnosticRequest(
                diagnostic_id="demo-diagnostic",
                results=[
                    DiagnosticResultInput(topic_id="pipeline", is_correct=True),
                    DiagnosticResultInput(topic_id="cache", is_correct=False),
                    DiagnosticResultInput(topic_id="memory-hierarchy", is_correct=False),
                ],
            ),
        )
        service.create_plan(user.id, DEMO_WORKSPACE_ID)
        question = service.next_question(user.id, DEMO_WORKSPACE_ID)
        service.submit_answer(
            user.id,
            DEMO_WORKSPACE_ID,
            AnswerRequest(
                attempt_id="demo-attempt",
                question_id=question.id,
                answer="I need another example before I can explain this.",
            ),
        )

    knowledge = KnowledgeIndex(database)
    try:
        knowledge.get_material(
            owner_id=user.id,
            project_id=DEMO_WORKSPACE_ID,
            material_id=DEMO_MATERIAL_ID,
        )
    except MaterialNotFoundError:
        material_text = (
            "流水线通过重叠执行多条指令的不同阶段提高吞吐量，但数据、结构和控制相关会造成冒险。\n"
            "缓存利用时间局部性与空间局部性缩短平均访存时间；命中率、命中时间和缺失代价共同决定性能。\n"
            "存储层次按速度、容量和成本组织寄存器、缓存、主存与外存。"
        )
        material_path = (
            root
            / "users"
            / user.id
            / "knowledge"
            / "workspaces"
            / DEMO_WORKSPACE_ID
            / "materials"
            / f"{DEMO_MATERIAL_ID}.txt"
        )
        _write_once(material_path, material_text.encode("utf-8"))
        knowledge.add_document(
            owner_id=user.id,
            project_id=DEMO_WORKSPACE_ID,
            material_id=DEMO_MATERIAL_ID,
            filename="computer-architecture-notes.txt",
            text=material_text,
        )

    result = DemoResult(
        owner_id=user.id,
        workspace_id=DEMO_WORKSPACE_ID,
        email=email,
    )
    return result
