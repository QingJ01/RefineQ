"""Owner-scoped persistence for canonical material analyses."""

from __future__ import annotations

from refineq.materials.models import MaterialAnalysis
from refineq.storage.json_store import AtomicJsonStore, RecordNotFoundError, StoredRecord

MATERIAL_ANALYSIS_SCHEMA_VERSION = 1


class MaterialAnalysisRepository:
    def __init__(self, store: AtomicJsonStore) -> None:
        self._store = store

    @staticmethod
    def _record_id(material_id: str) -> str:
        return f"library__{material_id}"

    def snapshot(self, owner_id: str, material_id: str) -> dict[str, StoredRecord]:
        return {
            record_id: record
            for record_id, record in self._store.list_items(
                owner_id, "material-analyses"
            ).items()
            if record.data.get("material_id") == material_id
        }

    def restore(self, owner_id: str, snapshot: dict[str, StoredRecord]) -> None:
        for record_id, record in snapshot.items():
            self._store.restore(owner_id, "material-analyses", record_id, record)

    def _legacy_records(self, owner_id: str, material_id: str) -> dict[str, MaterialAnalysis]:
        canonical_id = self._record_id(material_id)
        return {
            record_id: MaterialAnalysis.model_validate(record.data)
            for record_id, record in self.snapshot(owner_id, material_id).items()
            if record_id != canonical_id
        }

    def _delete_legacy_records(self, owner_id: str, material_id: str) -> None:
        for record_id in self._legacy_records(owner_id, material_id):
            self._store.delete(owner_id, "material-analyses", record_id)

    def save(
        self,
        owner_id: str,
        workspace_id: str,
        analysis: MaterialAnalysis,
    ) -> MaterialAnalysis:
        del workspace_id
        with self._store.owner_transaction(owner_id, "material-analyses"):
            record_id = self._record_id(analysis.material_id)
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
            self._delete_legacy_records(owner_id, analysis.material_id)
        return analysis

    def get(self, owner_id: str, workspace_id: str, material_id: str) -> MaterialAnalysis:
        with self._store.owner_transaction(owner_id, "material-analyses"):
            try:
                record = self._store.read(
                    owner_id,
                    "material-analyses",
                    self._record_id(material_id),
                )
            except RecordNotFoundError:
                legacy = self._legacy_records(owner_id, material_id)
                if not legacy:
                    raise
                analysis = next(iter(legacy.values()))
                return self.save(owner_id, workspace_id, analysis)
            return MaterialAnalysis.model_validate(record.data)

    def delete(self, owner_id: str, workspace_id: str, material_id: str) -> None:
        del workspace_id
        with self._store.owner_transaction(owner_id, "material-analyses"):
            self._store.delete(
                owner_id,
                "material-analyses",
                self._record_id(material_id),
            )
            self._delete_legacy_records(owner_id, material_id)
