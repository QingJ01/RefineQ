"""Crash-recoverable account deletion across SQL metadata and object storage."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from refineq.identity.service import IdentityService
from refineq.integrations.object_storage import ObjectStorage


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
        self.root = data_root.resolve() / "recovery" / "account-deletions"
        self.identity = identity
        self.object_storage = object_storage

    @staticmethod
    def _atomic_bytes(path: Path, payload: bytes) -> None:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}-",
            suffix=".tmp",
            dir=path.parent,
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as output:
                output.write(payload)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

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
        self._atomic_bytes(directory / "manifest.json", payload)

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
        self.root.mkdir(parents=True, exist_ok=True)
        directory = self.root / deletion_id
        directory.mkdir()
        entries: list[dict[str, str]] = []
        self._write_manifest(
            directory,
            deletion_id=deletion_id,
            user_id=user_id,
            entries=entries,
        )
        began = False
        try:
            self.identity.begin_account_deletion(
                user_id,
                current_password=current_password,
                deletion_id=deletion_id,
            )
            began = True
            for index, source in enumerate(self.identity.account_storage_objects(user_id)):
                blob_name = f"{index:06d}.bin"
                self._atomic_bytes(
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
            if began:
                self.identity.cancel_account_deletion(user_id, deletion_id=deletion_id)
            shutil.rmtree(directory)
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
        self._restore(pending)
        self.identity.cancel_account_deletion(
            pending.user_id,
            deletion_id=pending.deletion_id,
        )
        shutil.rmtree(pending.directory)

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
        shutil.rmtree(pending.directory)

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
        for directory in sorted(path for path in self.root.iterdir() if path.is_dir()):
            pending = self._load(directory)
            exists, current_deletion_id = self.identity.account_deletion_state(
                pending.user_id
            )
            if exists and current_deletion_id == pending.deletion_id:
                self._restore(pending)
                self.identity.cancel_account_deletion(
                    pending.user_id,
                    deletion_id=pending.deletion_id,
                )
            shutil.rmtree(directory)
