from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import pytest

from refineq.materials.models import MaterialAnalysis, MaterialSection, MaterialType
from refineq.storage.json_store import AtomicJsonStore, RecordNotFoundError
from refineq.storage.material_analyses import MaterialAnalysisRepository


def analysis() -> MaterialAnalysis:
    return MaterialAnalysis(
        material_id="material-1",
        filename="linear-algebra.txt",
        material_type=MaterialType.LECTURE_NOTES,
        title="Linear algebra",
        summary="Evidence-backed linear algebra notes.",
        sections=[
            MaterialSection(
                title="Eigenvalues",
                topics=["Eigenvalues"],
                citation_ids=["material-1#0"],
            )
        ],
        topics=["Eigenvalues"],
        confidence=0.9,
        mode="ai",
        analyzed_at=datetime.now(UTC),
    )


def test_canonical_material_analysis_is_shared_and_deleted_across_workspace_links(
    tmp_path: Path,
) -> None:
    repository = MaterialAnalysisRepository(AtomicJsonStore(tmp_path))
    saved = repository.save("owner", "workspace-a", analysis())

    assert repository.get("owner", "workspace-b", "material-1") == saved

    repository.delete("owner", "workspace-b", "material-1")

    with pytest.raises(RecordNotFoundError):
        repository.get("owner", "workspace-a", "material-1")


def test_legacy_workspace_analysis_is_migrated_and_cannot_survive_global_delete(
    tmp_path: Path,
) -> None:
    store = AtomicJsonStore(tmp_path)
    legacy = analysis()
    store.create(
        "owner",
        "material-analyses",
        "workspace-a__material-1",
        legacy.model_dump(mode="json"),
        schema_version=1,
    )
    repository = MaterialAnalysisRepository(store)

    assert repository.get("owner", "workspace-b", "material-1") == legacy
    repository.delete("owner", "library", "material-1")

    assert store.list("owner", "material-analyses") == []


def test_unrelated_corrupt_analysis_does_not_block_legacy_migration(tmp_path: Path) -> None:
    store = AtomicJsonStore(tmp_path)
    legacy = analysis()
    store.create(
        "owner",
        "material-analyses",
        "workspace-a__material-1",
        legacy.model_dump(mode="json"),
    )
    store.create(
        "owner",
        "material-analyses",
        "workspace-z__material-2",
        {"material_id": "material-2", "invalid": True},
    )

    migrated = MaterialAnalysisRepository(store).get(
        "owner", "workspace-b", "material-1"
    )

    assert migrated == legacy


def test_concurrent_legacy_reads_create_one_canonical_analysis(tmp_path: Path) -> None:
    store = AtomicJsonStore(tmp_path)
    legacy = analysis()
    store.create(
        "owner",
        "material-analyses",
        "workspace-a__material-1",
        legacy.model_dump(mode="json"),
    )
    repository = MaterialAnalysisRepository(store)

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(
            executor.map(
                lambda _: repository.get("owner", "workspace-b", "material-1"),
                range(8),
            )
        )

    assert results == [legacy] * 8
    assert set(store.list_items("owner", "material-analyses")) == {"library__material-1"}
