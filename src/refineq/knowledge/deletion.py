"""Crash-recoverable bulk deletion for material objects and their index rows."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from uuid import uuid4

from refineq.integrations.object_storage import ObjectStorage
from refineq.knowledge.index import KnowledgeIndex, MaterialNotFoundError, MaterialRecord
from refineq.operations.recovery import (
    RecoveryLease,
    durable_atomic_bytes,
    durable_mkdir,
    durable_remove_tree,
)
from refineq.storage.json_store import StoredRecord
from refineq.storage.material_analyses import MaterialAnalysisRepository


class MaterialMutationBusyError(RuntimeError):
    """A material mutation could not acquire the shared recovery lease in time."""


@dataclass(frozen=True, slots=True)
class PendingMaterialDeletion:
    deletion_id: str
    owner_id: str
    project_id: str
    directory: Path
    entries: tuple[dict[str, object], ...]


class MaterialDeletionCoordinator:
    """Keep original objects until SQL index deletion is known to be durable."""

    def __init__(
        self,
        *,
        data_root: Path,
        knowledge: KnowledgeIndex,
        object_storage: ObjectStorage,
        analyses: MaterialAnalysisRepository,
    ) -> None:
        recovery_root = data_root.resolve() / "recovery"
        self.root = recovery_root / "material-deletions"
        self.lease_path = recovery_root / ".material-object-mutations.lock"
        self.knowledge = knowledge
        self.object_storage = object_storage
        self.analyses = analyses
        self._leases: dict[str, RecoveryLease] = {}

    def _write_manifest(self, pending: PendingMaterialDeletion) -> None:
        durable_atomic_bytes(
            pending.directory / "manifest.json",
            json.dumps(
                {
                    "deletion_id": pending.deletion_id,
                    "owner_id": pending.owner_id,
                    "project_id": pending.project_id,
                    "entries": list(pending.entries),
                },
                ensure_ascii=False,
                indent=2,
            ).encode("utf-8"),
        )

    def prepare(
        self,
        *,
        owner_id: str,
        project_id: str,
        material_ids: list[str] | None,
    ) -> PendingMaterialDeletion:
        deletion_id = uuid4().hex
        durable_mkdir(self.root)
        lease = RecoveryLease.acquire_wait(self.lease_path)
        if lease is None:
            raise MaterialMutationBusyError(
                "Another material object mutation is already active"
            )
        directory = self.root / deletion_id
        self._leases[deletion_id] = lease
        entries: list[dict[str, object]] = []
        try:
            selected_ids = material_ids
            if selected_ids is None:
                selected_ids = [
                    material.id
                    for material in self.knowledge.list_materials(
                        owner_id=owner_id,
                        project_id=project_id,
                    )
                ]
            durable_mkdir(directory)
            for index, material_id in enumerate(selected_ids):
                record = self.knowledge.get_material(
                    owner_id=owner_id,
                    project_id=project_id,
                    material_id=material_id,
                )
                storage_key = self.knowledge.get_material_storage_key(
                    owner_id=owner_id,
                    project_id=project_id,
                    material_id=material_id,
                )
                blob = f"{index:06d}.bin"
                durable_atomic_bytes(
                    directory / blob,
                    self.object_storage.get(storage_key),
                )
                entries.append(
                    {
                        "material": record.model_dump(mode="json"),
                        "storage_key": storage_key,
                        "blob": blob,
                        "analyses": {
                            record_id: {
                                "schema_version": stored.schema_version,
                                "version": stored.version,
                                "data": stored.data,
                            }
                            for record_id, stored in self.analyses.snapshot(
                                owner_id, material_id
                            ).items()
                        },
                    }
                )
            pending = PendingMaterialDeletion(
                deletion_id=deletion_id,
                owner_id=owner_id,
                project_id=project_id,
                directory=directory,
                entries=tuple(entries),
            )
            self._write_manifest(pending)
            return pending
        except Exception:
            try:
                if directory.exists():
                    durable_remove_tree(directory)
            finally:
                self._release(deletion_id)
            raise

    def _restore(self, pending: PendingMaterialDeletion) -> None:
        for entry in pending.entries:
            record = MaterialRecord.model_validate(entry["material"])
            storage_key = str(entry["storage_key"])
            parts = PurePosixPath(storage_key).parts
            if parts == ("users", pending.owner_id, "documents", record.id):
                storage_scope = "library"
            elif (
                len(parts) == 6
                and parts[0] == "users"
                and parts[1] == pending.owner_id
                and parts[2] == "workspaces"
                and parts[4] == "materials"
                and parts[5] == record.id
            ):
                storage_scope = parts[3]
            else:
                raise RuntimeError("Material recovery manifest contains an invalid storage key")
            blob_path = (pending.directory / str(entry["blob"])).resolve()
            blob_path.relative_to(pending.directory.resolve())
            restored = self.object_storage.put(
                owner_id=pending.owner_id,
                workspace_id=storage_scope,
                material_id=record.id,
                filename=record.filename,
                payload=blob_path.read_bytes(),
            )
            if restored.key != storage_key:
                restored.rollback()
                raise RuntimeError("Material recovery changed the original storage key")
            self.analyses.restore(
                pending.owner_id,
                self._analysis_snapshot(entry),
            )

    @staticmethod
    def _analysis_snapshot(entry: dict[str, object]) -> dict[str, StoredRecord]:
        raw_snapshot = entry.get("analyses", {})
        if not isinstance(raw_snapshot, dict):
            raise RuntimeError("Invalid material analysis recovery snapshot")
        snapshot: dict[str, StoredRecord] = {}
        for record_id, raw_record in raw_snapshot.items():
            if not isinstance(record_id, str) or not isinstance(raw_record, dict):
                raise RuntimeError("Invalid material analysis recovery snapshot")
            schema_version = raw_record.get("schema_version")
            version = raw_record.get("version")
            data = raw_record.get("data")
            if (
                not isinstance(schema_version, int)
                or not isinstance(version, int)
                or not isinstance(data, dict)
            ):
                raise RuntimeError("Invalid material analysis recovery snapshot")
            snapshot[record_id] = StoredRecord(
                schema_version=schema_version,
                version=version,
                data=data,
            )
        return snapshot

    def _release(self, deletion_id: str) -> None:
        lease = self._leases.pop(deletion_id, None)
        if lease is not None:
            lease.release()

    def rollback(self, pending: PendingMaterialDeletion) -> None:
        try:
            self._restore(pending)
            durable_remove_tree(pending.directory)
        finally:
            self._release(pending.deletion_id)

    def complete(self, pending: PendingMaterialDeletion) -> None:
        try:
            for entry in pending.entries:
                self.object_storage.delete(str(entry["storage_key"]))
            records = [
                MaterialRecord.model_validate(entry["material"]) for entry in pending.entries
            ]
            project_ids = {record.project_id for record in records}
            if records and len(project_ids) != 1:
                raise RuntimeError("A physical material deletion must use one storage scope")
            if records:
                for record in records:
                    self.analyses.delete(
                        pending.owner_id,
                        "library",
                        record.id,
                    )
                self.knowledge.delete_materials(
                    owner_id=pending.owner_id,
                    project_id=records[0].project_id,
                    material_ids=[record.id for record in records],
                )
        except Exception:
            self.rollback(pending)
            raise
        try:
            durable_remove_tree(pending.directory)
        except OSError:
            # Objects and SQL rows are already durably deleted. A leftover or
            # partially removed journal is safe for startup recovery to clean.
            pass
        finally:
            self._release(pending.deletion_id)

    def _load(self, directory: Path) -> PendingMaterialDeletion:
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("deletion_id") != directory.name:
            raise RuntimeError("Invalid material deletion recovery manifest")
        entries = manifest.get("entries")
        if not isinstance(entries, list):
            raise RuntimeError("Invalid material deletion recovery manifest")
        for entry in entries:
            if not isinstance(entry, dict):
                raise RuntimeError("Invalid material deletion recovery entry")
            MaterialRecord.model_validate(entry.get("material"))
            if not all(isinstance(entry.get(key), str) for key in ("storage_key", "blob")):
                raise RuntimeError("Invalid material deletion recovery entry")
            self._analysis_snapshot(entry)
        return PendingMaterialDeletion(
            deletion_id=directory.name,
            owner_id=str(manifest["owner_id"]),
            project_id=str(manifest["project_id"]),
            directory=directory,
            entries=tuple(entries),
        )

    def recover_pending(self) -> None:
        if not self.root.exists():
            return
        lease = RecoveryLease.acquire(self.lease_path)
        if lease is None:
            return
        try:
            for directory in sorted(path for path in self.root.iterdir() if path.is_dir()):
                if not (directory / "manifest.json").is_file():
                    durable_remove_tree(directory)
                    continue
                pending = self._load(directory)
                present = []
                for entry in pending.entries:
                    record = MaterialRecord.model_validate(entry["material"])
                    try:
                        self.knowledge.get_material(
                            owner_id=pending.owner_id,
                            project_id=pending.project_id,
                            material_id=record.id,
                        )
                    except MaterialNotFoundError:
                        present.append(False)
                    else:
                        present.append(True)
                if any(present) and not all(present):
                    raise RuntimeError("Material deletion recovery found partial SQL state")
                if all(present):
                    self._restore(pending)
                else:
                    for entry in pending.entries:
                        record = MaterialRecord.model_validate(entry["material"])
                        self.analyses.delete(
                            pending.owner_id,
                            "library",
                            record.id,
                        )
                durable_remove_tree(directory)
        finally:
            lease.release()

    def close(self) -> None:
        for deletion_id in list(self._leases):
            self._release(deletion_id)
