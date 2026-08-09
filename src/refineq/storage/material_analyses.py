"""Owner- and workspace-scoped persistence for material analyses."""

from __future__ import annotations

from refineq.materials.models import MaterialAnalysis
from refineq.storage.json_store import AtomicJsonStore, RecordNotFoundError

MATERIAL_ANALYSIS_SCHEMA_VERSION = 1


class MaterialAnalysisRepository:
    def __init__(self, store: AtomicJsonStore) -> None:
        self._store = store

    @staticmethod
    def _record_id(workspace_id: str, material_id: str) -> str:
        return f"{workspace_id}__{material_id}"

    def save(
        self,
        owner_id: str,
        workspace_id: str,
        analysis: MaterialAnalysis,
    ) -> MaterialAnalysis:
        record_id = self._record_id(workspace_id, analysis.material_id)
        payload = analysis.model_dump(mode="json")
        try:
            current = self._store.read(owner_id, "material-analyses", record_id)
        except RecordNotFoundError:
            self._store.create(
                owner_id,
                "material-analyses",
                record_id,
                payload,
                schema_version=MATERIAL_ANALYSIS_SCHEMA_VERSION,
            )
        else:
            self._store.save(
                owner_id,
                "material-analyses",
                record_id,
                payload,
                expected_version=current.version,
            )
        return analysis

    def get(self, owner_id: str, workspace_id: str, material_id: str) -> MaterialAnalysis:
        try:
            record = self._store.read(
                owner_id,
                "material-analyses",
                self._record_id(workspace_id, material_id),
            )
        except RecordNotFoundError:
            record = self._store.read(
                owner_id,
                "material-analyses",
                self._record_id("library", material_id),
            )
        return MaterialAnalysis.model_validate(record.data)

    def delete(self, owner_id: str, workspace_id: str, material_id: str) -> None:
        try:
            self._store.delete(
                owner_id,
                "material-analyses",
                self._record_id(workspace_id, material_id),
            )
        except RecordNotFoundError:
            return
