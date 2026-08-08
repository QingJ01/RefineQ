"""Crash-recoverable bulk deletion for material objects and their index rows."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from refineq.integrations.object_storage import ObjectStorage
from refineq.knowledge.index import KnowledgeIndex, MaterialNotFoundError, MaterialRecord
from refineq.operations.recovery import (
    RecoveryLease,
    durable_atomic_bytes,
    durable_mkdir,
    durable_remove_tree,
)


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
    ) -> None:
        self.root = data_root.resolve() / "recovery" / "material-deletions"
        self.knowledge = knowledge
        self.object_storage = object_storage
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
        material_ids: list[str],
    ) -> PendingMaterialDeletion:
        deletion_id = uuid4().hex
        durable_mkdir(self.root)
        lease = RecoveryLease.acquire(self.root / ".coordinator.lock")
        if lease is None:
            raise RuntimeError("Another material deletion is already active")
        directory = self.root / deletion_id
        durable_mkdir(directory)
        self._leases[deletion_id] = lease
        entries: list[dict[str, object]] = []
        try:
            for index, material_id in enumerate(material_ids):
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
                durable_remove_tree(directory)
            finally:
                self._release(deletion_id)
            raise

    def _restore(self, pending: PendingMaterialDeletion) -> None:
        for entry in pending.entries:
            record = MaterialRecord.model_validate(entry["material"])
            blob_path = (pending.directory / str(entry["blob"])).resolve()
            blob_path.relative_to(pending.directory.resolve())
            self.object_storage.put(
                owner_id=pending.owner_id,
                workspace_id=pending.project_id,
                material_id=record.id,
                filename=record.filename,
                payload=blob_path.read_bytes(),
            )

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
            self.knowledge.delete_materials(
                owner_id=pending.owner_id,
                project_id=pending.project_id,
                material_ids=[
                    MaterialRecord.model_validate(entry["material"]).id
                    for entry in pending.entries
                ],
            )
        except Exception:
            self.rollback(pending)
            raise
        try:
            durable_remove_tree(pending.directory)
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
        lease = RecoveryLease.acquire(self.root / ".coordinator.lock")
        if lease is None:
            return
        try:
            for directory in sorted(path for path in self.root.iterdir() if path.is_dir()):
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
                durable_remove_tree(directory)
        finally:
            lease.release()

    def close(self) -> None:
        for deletion_id in list(self._leases):
            self._release(deletion_id)
