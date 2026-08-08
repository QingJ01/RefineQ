"""Crash-recoverable account deletion across SQL metadata and object storage."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from refineq.identity.service import IdentityService
from refineq.integrations.object_storage import ObjectStorage
from refineq.operations.recovery import (
    RecoveryLease,
    durable_atomic_bytes,
    durable_mkdir,
    durable_remove_tree,
)


@dataclass(frozen=True, slots=True)
class PendingAccountDeletion:
    deletion_id: str
    user_id: str
    directory: Path
    entries: tuple[dict[str, str], ...]


class AccountDeletionCoordinator:
    """Persist a compensating transaction until account deletion is complete."""

    def __init__(
        self,
        *,
        data_root: Path,
        identity: IdentityService,
        object_storage: ObjectStorage,
    ) -> None:
        recovery_root = data_root.resolve() / "recovery"
        self.root = recovery_root / "account-deletions"
        self.lease_path = recovery_root / ".material-object-mutations.lock"
        self.identity = identity
        self.object_storage = object_storage
        self._leases: dict[str, RecoveryLease] = {}

    def _write_manifest(
        self,
        directory: Path,
        *,
        deletion_id: str,
        user_id: str,
        entries: list[dict[str, str]],
    ) -> None:
        payload = json.dumps(
            {
                "deletion_id": deletion_id,
                "user_id": user_id,
                "entries": entries,
            },
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8")
        durable_atomic_bytes(directory / "manifest.json", payload)

    def prepare(
        self,
        user_id: str,
        *,
        current_password: str,
    ) -> PendingAccountDeletion:
        """Fence writes, revoke tokens, and durably stage every material object."""

        self.identity.preflight_account_deletion(
            user_id,
            current_password=current_password,
        )
        deletion_id = uuid4().hex
        durable_mkdir(self.root)
        lease = RecoveryLease.acquire(self.lease_path)
        if lease is None:
            raise RuntimeError("Another material object mutation is already active")
        directory = self.root / deletion_id
        self._leases[deletion_id] = lease
        entries: list[dict[str, str]] = []
        began = False
        try:
            durable_mkdir(directory)
            self._write_manifest(
                directory,
                deletion_id=deletion_id,
                user_id=user_id,
                entries=entries,
            )
            self.identity.begin_account_deletion(
                user_id,
                current_password=current_password,
                deletion_id=deletion_id,
            )
            began = True
            for index, source in enumerate(self.identity.account_storage_objects(user_id)):
                blob_name = f"{index:06d}.bin"
                durable_atomic_bytes(
                    directory / blob_name,
                    self.object_storage.get(source["key"]),
                )
                entry = {**source, "blob": blob_name}
                entries.append(entry)
                self._write_manifest(
                    directory,
                    deletion_id=deletion_id,
                    user_id=user_id,
                    entries=entries,
                )
        except Exception:
            try:
                if began:
                    self.identity.cancel_account_deletion(user_id, deletion_id=deletion_id)
                if directory.exists():
                    durable_remove_tree(directory)
            finally:
                self._release(deletion_id)
            raise
        return PendingAccountDeletion(
            deletion_id=deletion_id,
            user_id=user_id,
            directory=directory,
            entries=tuple(entries),
        )

    def _restore(self, pending: PendingAccountDeletion) -> None:
        for entry in pending.entries:
            blob_path = (pending.directory / entry["blob"]).resolve()
            blob_path.relative_to(pending.directory.resolve())
            self.object_storage.put(
                owner_id=pending.user_id,
                workspace_id=entry["workspace_id"],
                material_id=entry["material_id"],
                filename=entry["filename"],
                payload=blob_path.read_bytes(),
            )

    def rollback(self, pending: PendingAccountDeletion) -> None:
        try:
            self._restore(pending)
            self.identity.cancel_account_deletion(
                pending.user_id,
                deletion_id=pending.deletion_id,
            )
            durable_remove_tree(pending.directory)
        finally:
            self._release(pending.deletion_id)

    def complete(
        self,
        pending: PendingAccountDeletion,
        *,
        current_password: str,
    ) -> None:
        try:
            for entry in pending.entries:
                self.object_storage.delete(entry["key"])
            self.identity.delete_account(
                pending.user_id,
                current_password=current_password,
                deletion_id=pending.deletion_id,
            )
        except Exception:
            self.rollback(pending)
            raise
        try:
            durable_remove_tree(pending.directory)
        finally:
            self._release(pending.deletion_id)

    def _release(self, deletion_id: str) -> None:
        lease = self._leases.pop(deletion_id, None)
        if lease is not None:
            lease.release()

    def _load(self, directory: Path) -> PendingAccountDeletion:
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        deletion_id = str(manifest["deletion_id"])
        user_id = str(manifest["user_id"])
        if deletion_id != directory.name or not isinstance(manifest["entries"], list):
            raise RuntimeError("Invalid account deletion recovery manifest")
        entries: list[dict[str, str]] = []
        for raw_entry in manifest["entries"]:
            entry = {
                key: str(raw_entry[key])
                for key in (
                    "key",
                    "workspace_id",
                    "material_id",
                    "filename",
                    "blob",
                )
            }
            entries.append(entry)
        return PendingAccountDeletion(
            deletion_id=deletion_id,
            user_id=user_id,
            directory=directory,
            entries=tuple(entries),
        )

    def recover_pending(self) -> None:
        """Restore interrupted deletions or purge residue from completed ones."""

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
                exists, current_deletion_id = self.identity.account_deletion_state(pending.user_id)
                if exists and current_deletion_id == pending.deletion_id:
                    self._restore(pending)
                    self.identity.cancel_account_deletion(
                        pending.user_id,
                        deletion_id=pending.deletion_id,
                    )
                durable_remove_tree(directory)
        finally:
            lease.release()

    def close(self) -> None:
        """Release process leases; incomplete journals remain for the next process."""

        for deletion_id in list(self._leases):
            self._release(deletion_id)
