"""Local and S3-compatible storage for original uploaded materials."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol

import boto3
from botocore.config import Config

from refineq.integrations.models import IntegrationKind, IntegrationSettings
from refineq.integrations.repository import (
    IntegrationNotConfiguredError,
    IntegrationRepository,
)
from refineq.storage.json_store import validate_identifier


@dataclass(frozen=True, slots=True)
class StoredObject:
    key: str
    created: bool


class ObjectStorage(Protocol):
    def put(
        self,
        *,
        owner_id: str,
        workspace_id: str,
        material_id: str,
        filename: str,
        payload: bytes,
    ) -> StoredObject: ...

    def delete(self, key: str) -> None: ...


def material_object_key(
    *,
    owner_id: str,
    workspace_id: str,
    material_id: str,
    filename: str,
) -> str:
    owner_id = validate_identifier(owner_id, field="owner_id")
    workspace_id = validate_identifier(workspace_id, field="workspace_id")
    material_id = validate_identifier(material_id, field="material_id")
    extension = Path(filename).suffix.lower()
    return str(
        PurePosixPath(
            "users",
            owner_id,
            "workspaces",
            workspace_id,
            "materials",
            f"{material_id}{extension}",
        )
    )


class LocalObjectStorage:
    def __init__(self, data_root: Path) -> None:
        self.data_root = data_root.expanduser().resolve()

    def put(
        self,
        *,
        owner_id: str,
        workspace_id: str,
        material_id: str,
        filename: str,
        payload: bytes,
    ) -> StoredObject:
        key = material_object_key(
            owner_id=owner_id,
            workspace_id=workspace_id,
            material_id=material_id,
            filename=filename,
        )
        path = (self.data_root / Path(*PurePosixPath(key).parts)).resolve()
        path.relative_to(self.data_root)
        if path.exists():
            if path.read_bytes() != payload:
                raise RuntimeError("Stored material key already contains different content")
            return StoredObject(key=key, created=False)
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
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
        return StoredObject(key=key, created=True)

    def delete(self, key: str) -> None:
        path = (self.data_root / Path(*PurePosixPath(key).parts)).resolve()
        path.relative_to(self.data_root)
        path.unlink(missing_ok=True)


class S3ObjectStorage:
    def __init__(self, settings: IntegrationSettings, *, client_factory=None) -> None:
        if settings.kind is not IntegrationKind.OBJECT_STORAGE or not settings.enabled:
            raise IntegrationNotConfiguredError("object storage integration is not enabled")
        self.bucket = str(settings.config["bucket"])
        factory = client_factory or boto3.client
        self.client = factory(
            service_name="s3",
            endpoint_url=str(settings.config["endpoint_url"]),
            region_name=str(settings.config["region"]),
            aws_access_key_id=settings.secrets["access_key_id"].get_secret_value(),
            aws_secret_access_key=settings.secrets["secret_access_key"].get_secret_value(),
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": settings.config.get("addressing_style", "auto")},
            ),
        )

    def put(
        self,
        *,
        owner_id: str,
        workspace_id: str,
        material_id: str,
        filename: str,
        payload: bytes,
    ) -> StoredObject:
        key = material_object_key(
            owner_id=owner_id,
            workspace_id=workspace_id,
            material_id=material_id,
            filename=filename,
        )
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=payload,
            ContentType="application/octet-stream",
        )
        return StoredObject(key=key, created=True)

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def test_connection(self) -> None:
        self.client.head_bucket(Bucket=self.bucket)


class ConfiguredObjectStorage:
    """Resolve the current platform setting for every operation."""

    def __init__(self, integrations: IntegrationRepository, *, data_root: Path) -> None:
        self.integrations = integrations
        self.local = LocalObjectStorage(data_root)

    def _active(self) -> ObjectStorage:
        try:
            settings = self.integrations.load(IntegrationKind.OBJECT_STORAGE)
        except IntegrationNotConfiguredError:
            return self.local
        return S3ObjectStorage(settings) if settings.enabled else self.local

    def put(self, **kwargs) -> StoredObject:
        return self._active().put(**kwargs)

    def delete(self, key: str) -> None:
        self._active().delete(key)
