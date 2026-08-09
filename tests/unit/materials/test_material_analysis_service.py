from datetime import UTC, datetime
from types import SimpleNamespace

from refineq.agent.settings import ModelNotConfiguredError
from refineq.integrations.endpoints import EndpointSecurityError
from refineq.knowledge.index import MaterialRecord, SearchResult
from refineq.materials.models import (
    MaterialAnalysisModelOutput,
    MaterialSection,
    MaterialType,
)
from refineq.materials.service import MaterialAnalysisService


class FakeKnowledge:
    def __init__(self, sources: list[SearchResult]) -> None:
        self.sources = sources

    def get_material(self, **_):
        return MaterialRecord(
            id="material_demo",
            project_id="workspace_demo",
            filename="高等数学教材.pdf",
            title="高等数学教材",
            tags=[],
            content_type="application/pdf",
            size=100,
            status="indexed",
            chunk_count=len(self.sources),
            content_sha256="a" * 64,
            indexed_at=datetime.now(UTC),
        )

    def material_chunks(self, **_):
        return self.sources

    def search(self, **_):
        return self.sources


class FakeAnalyses:
    def __init__(self) -> None:
        self.saved = None

    def save(self, _owner_id, _workspace_id, analysis):
        self.saved = analysis
        return analysis


class FakeSettings:
    def __init__(self, *, configured: bool) -> None:
        self.configured = configured

    def load(self, _owner_id):
        if not self.configured:
            raise ModelNotConfiguredError
        return SimpleNamespace()


class FakeTransport:
    def complete(self, **_):
        return MaterialAnalysisModelOutput(
            material_type=MaterialType.TEXTBOOK,
            title="高等数学",
            summary="覆盖极限与导数。",
            sections=[
                MaterialSection(
                    title="第一章 函数极限",
                    topics=["函数极限", "连续"],
                    citation_ids=["material_demo#0", "invented#9"],
                )
            ],
            topics=["函数极限"],
            confidence=0.94,
        )


class FailingTransport:
    def complete(self, **_):
        raise EndpointSecurityError("provider unavailable")


def sources() -> list[SearchResult]:
    return [
        SearchResult(
            citation_id="material_demo#0",
            material_id="material_demo",
            filename="高等数学教材.pdf",
            chunk_index=0,
            text="第一章 函数极限\n1.1 极限定义\n函数极限描述局部趋势。",
            score=1.0,
        )
    ]


def test_ai_analysis_extracts_type_sections_topics_and_valid_citations() -> None:
    repository = FakeAnalyses()
    service = MaterialAnalysisService(
        FakeKnowledge(sources()),
        repository,
        FakeSettings(configured=True),
        FakeTransport(),
    )

    result = service.analyze(
        owner_id="learner",
        workspace_id="workspace_demo",
        material_id="material_demo",
    )

    assert result.mode == "ai"
    assert result.material_type is MaterialType.TEXTBOOK
    assert result.topics == ["函数极限", "连续"]
    assert result.sections[0].citation_ids == ["material_demo#0"]
    assert repository.saved == result


def test_local_fallback_preserves_heading_candidates_without_model() -> None:
    service = MaterialAnalysisService(
        FakeKnowledge(sources()),
        FakeAnalyses(),
        FakeSettings(configured=False),
        FakeTransport(),
    )

    result = service.analyze(
        owner_id="learner",
        workspace_id="workspace_demo",
        material_id="material_demo",
    )

    assert result.mode == "fallback"
    assert result.material_type is MaterialType.TEXTBOOK
    assert result.sections[0].title == "第一章 函数极限"
    assert result.sections[0].citation_ids == ["material_demo#0"]


def test_provider_endpoint_failure_returns_fallback_instead_of_http_500() -> None:
    service = MaterialAnalysisService(
        FakeKnowledge(sources()),
        FakeAnalyses(),
        FakeSettings(configured=True),
        FailingTransport(),
    )

    result = service.analyze(
        owner_id="learner",
        workspace_id="workspace_demo",
        material_id="material_demo",
    )

    assert result.mode == "fallback"
    assert result.material_type is MaterialType.TEXTBOOK
