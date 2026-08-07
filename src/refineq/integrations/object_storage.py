"""Local and S3-compatible storage for original uploaded materials."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Protocol

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from refineq.integrations.endpoints import assert_safe_endpoint
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
    _rollback_handler: Callable[[str], None] | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    def rollback(self) -> None:
        """Remove only an object created by the operation that returned this handle."""

        if self.created and self._rollback_handler is not None:
            self._rollback_handler(self.key)


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
    del filename
    return str(
        PurePosixPath(
            "users",
            owner_id,
            "workspaces",
            workspace_id,
            "materials",
            material_id,
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
            try:
                os.link(temporary, path)
            except FileExistsError as error:
                if path.read_bytes() != payload:
                    raise RuntimeError(
                        "Stored material key already contains different content"
                    ) from error
                return StoredObject(key=key, created=False)
        finally:
            temporary.unlink(missing_ok=True)
        return StoredObject(key=key, created=True, _rollback_handler=self.delete)

    def delete(self, key: str) -> None:
        path = (self.data_root / Path(*PurePosixPath(key).parts)).resolve()
        path.relative_to(self.data_root)
        path.unlink(missing_ok=True)


class S3ObjectStorage:
    def __init__(
        self,
        settings: IntegrationSettings,
        *,
        client_factory=None,
        endpoint_validator: Callable[[str, bool], None] | None = None,
    ) -> None:
        if settings.kind is not IntegrationKind.OBJECT_STORAGE or not settings.enabled:
            raise IntegrationNotConfiguredError("object storage integration is not enabled")
        self.bucket = str(settings.config["bucket"])
        self.endpoint_url = str(settings.config["endpoint_url"])
        self.allow_private_network = bool(settings.config.get("allow_private_network", False))
        self._endpoint_validator = endpoint_validator or (
            lambda url, allow_private: assert_safe_endpoint(
                url,
                allow_private_network=allow_private,
                allow_transparent_proxy=True,
            )
        )
        factory = client_factory or boto3.client
        self.client = factory(
            service_name="s3",
            endpoint_url=self.endpoint_url,
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
        digest = sha256(payload).hexdigest()
        self._endpoint_validator(self.endpoint_url, self.allow_private_network)
        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=payload,
                ContentType="application/octet-stream",
                IfNoneMatch="*",
                Metadata={"sha256": digest},
            )
        except ClientError as error:
            status_code = error.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            error_code = error.response.get("Error", {}).get("Code")
            if status_code != 412 and error_code not in {"PreconditionFailed", "412"}:
                raise
            existing = self.client.head_object(Bucket=self.bucket, Key=key)
            if existing.get("Metadata", {}).get("sha256") != digest:
                raise RuntimeError(
                    "Stored material key already contains different content"
                ) from error
            return StoredObject(key=key, created=False, _rollback_handler=self.delete)
        return StoredObject(key=key, created=True, _rollback_handler=self.delete)

    def delete(self, key: str) -> None:
        self._endpoint_validator(self.endpoint_url, self.allow_private_network)
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def test_connection(self) -> None:
        self._endpoint_validator(self.endpoint_url, self.allow_private_network)
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
