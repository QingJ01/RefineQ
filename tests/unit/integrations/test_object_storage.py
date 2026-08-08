"""Local and S3-compatible object storage tests."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from threading import Barrier

import pytest
from botocore.exceptions import ClientError
from cryptography.fernet import Fernet
from pydantic import SecretStr

from refineq.database.engine import Database
from refineq.identity.service import IdentityService
from refineq.integrations.models import IntegrationKind, IntegrationSettings, IntegrationUpdate
from refineq.integrations.object_storage import (
    ConfiguredObjectStorage,
    LocalObjectStorage,
    S3ObjectStorage,
)
from refineq.integrations.repository import (
    IntegrationConfigurationError,
    IntegrationRepository,
)
from refineq.operations.admin import ensure_admin


class FakeS3Client:
    def __init__(self) -> None:
        self.puts: list[dict] = []
        self.deletes: list[dict] = []
        self.objects: dict[str, dict] = {}

    def put_object(self, **kwargs) -> None:
        self.puts.append(kwargs)
        key = kwargs["Key"]
        if kwargs.get("IfNoneMatch") == "*" and key in self.objects:
            raise ClientError(
                {
                    "Error": {"Code": "PreconditionFailed", "Message": "already exists"},
                    "ResponseMetadata": {"HTTPStatusCode": 412},
                },
                "PutObject",
            )
        self.objects[key] = kwargs

    def head_object(self, **kwargs) -> dict:
        stored = self.objects[kwargs["Key"]]
        return {
            "Metadata": stored.get("Metadata", {}),
            "ContentLength": len(stored["Body"]),
        }

    def delete_object(self, **kwargs) -> None:
        self.deletes.append(kwargs)
        self.objects.pop(kwargs["Key"], None)

    def head_bucket(self, **kwargs) -> None:
        self.bucket = kwargs["Bucket"]


def test_local_objects_are_scoped_by_owner_and_workspace(tmp_path) -> None:
    storage = LocalObjectStorage(tmp_path)

    stored = storage.put(
        owner_id="owner",
        workspace_id="space",
        material_id="material-1",
        filename="notes.pdf",
        payload=b"pdf bytes",
    )

    assert stored.key == "users/owner/workspaces/space/materials/material-1"
    assert (tmp_path / stored.key).read_bytes() == b"pdf bytes"
    stored.rollback()
    assert not (tmp_path / stored.key).exists()


def test_concurrent_local_duplicate_has_only_one_rollback_owner(tmp_path, monkeypatch) -> None:
    storage = LocalObjectStorage(tmp_path)
    barrier = Barrier(2)
    original_replace = os.replace

    def synchronized_replace(source, destination) -> None:
        barrier.wait(timeout=5)
        original_replace(source, destination)

    monkeypatch.setattr("refineq.integrations.object_storage.os.replace", synchronized_replace)
    arguments = {
        "owner_id": "owner",
        "workspace_id": "space",
        "material_id": "material-1",
        "filename": "notes.txt",
        "payload": b"same document",
    }
    with ThreadPoolExecutor(max_workers=2) as executor:
        stored = list(executor.map(lambda _: storage.put(**arguments), range(2)))

    assert sorted(item.created for item in stored) == [False, True]
    duplicate = next(item for item in stored if not item.created)
    duplicate.rollback()
    assert (tmp_path / duplicate.key).read_bytes() == b"same document"


def test_s3_storage_uses_configured_bucket_and_private_object_key() -> None:
    client = FakeS3Client()
    settings = IntegrationSettings(
        kind=IntegrationKind.OBJECT_STORAGE,
        enabled=True,
        config={
            "endpoint_url": "https://storage.example.com",
            "bucket": "refineq-private",
            "region": "auto",
            "addressing_style": "path",
        },
        secrets={
            "access_key_id": SecretStr("access-key"),
            "secret_access_key": SecretStr("secret-key"),
        },
    )
    storage = S3ObjectStorage(
        settings,
        client_factory=lambda **_: client,
        endpoint_validator=lambda *_: None,
    )

    stored = storage.put(
        owner_id="owner",
        workspace_id="space",
        material_id="material-1",
        filename="notes.docx",
        payload=b"document",
    )
    stored.rollback()

    assert client.puts == [
        {
            "Bucket": "refineq-private",
            "Key": stored.key,
            "Body": b"document",
            "ContentType": "application/octet-stream",
            "IfNoneMatch": "*",
            "Metadata": {"sha256": sha256(b"document").hexdigest()},
        }
    ]
    assert client.deletes == [{"Bucket": "refineq-private", "Key": stored.key}]


def test_s3_duplicate_is_not_created_and_rollback_preserves_existing_object() -> None:
    client = FakeS3Client()
    settings = IntegrationSettings(
        kind=IntegrationKind.OBJECT_STORAGE,
        enabled=True,
        config={
            "endpoint_url": "https://storage.example.com",
            "bucket": "refineq-private",
            "region": "auto",
            "addressing_style": "path",
        },
        secrets={
            "access_key_id": SecretStr("access-key"),
            "secret_access_key": SecretStr("secret-key"),
        },
    )
    storage = S3ObjectStorage(
        settings,
        client_factory=lambda **_: client,
        endpoint_validator=lambda *_: None,
    )
    arguments = {
        "owner_id": "owner",
        "workspace_id": "space",
        "material_id": "material-1",
        "filename": "notes.txt",
        "payload": b"same document",
    }

    first = storage.put(**arguments)
    duplicate = storage.put(**{**arguments, "filename": "renamed.md"})
    duplicate.rollback()

    assert first.created is True
    assert duplicate.created is False
    assert first.key == duplicate.key
    assert first.key in client.objects
    assert client.deletes == []


def test_corrupt_storage_secrets_fail_closed_instead_of_using_local_storage(tmp_path) -> None:
    database = Database(f"sqlite+pysqlite:///{(tmp_path / 'settings.sqlite3').as_posix()}")
    database.initialize()
    admin = ensure_admin(
        IdentityService(database),
        email="admin@example.com",
        password="correct-horse-battery-staple",
        display_name="Admin",
    ).user
    repository = IntegrationRepository(
        database,
        encryption_key=Fernet.generate_key(),
        allowed_object_storage_hosts={"storage.example.com"},
    )
    repository.save(
        IntegrationKind.OBJECT_STORAGE,
        IntegrationUpdate(
            enabled=True,
            config={
                "endpoint_url": "https://storage.example.com",
                "bucket": "refineq-private",
                "region": "auto",
                "addressing_style": "path",
            },
            secrets={"access_key_id": "access", "secret_access_key": "secret"},
        ),
        actor_id=admin.id,
    )
    unreadable = IntegrationRepository(database, encryption_key=Fernet.generate_key())
    storage = ConfiguredObjectStorage(unreadable, data_root=tmp_path / "local")

    with pytest.raises(IntegrationConfigurationError, match="secrets"):
        storage._active()
    with pytest.raises(IntegrationConfigurationError, match="secrets"):
        storage.put(
            owner_id="owner",
            workspace_id="space",
            material_id="material-1",
            filename="notes.txt",
            payload=b"must roll back",
        )
    assert not (
        tmp_path / "local" / "users" / "owner" / "workspaces" / "space" / "materials" / "material-1"
    ).exists()

    database.close()


def test_configured_storage_keeps_a_local_canonical_copy_when_backend_changes(
    tmp_path,
    monkeypatch,
) -> None:
    class RemoteStorage:
        def __init__(self) -> None:
            self.payloads: dict[str, bytes] = {}

        def put(self, **kwargs):
            key = f"remote/{kwargs['material_id']}"
            self.payloads[key] = kwargs["payload"]
            return type(
                "RemoteObject",
                (),
                {"key": key, "created": True, "rollback": lambda value: None},
            )()

        def get(self, key: str) -> bytes:
            return self.payloads[key]

        def delete(self, key: str) -> None:
            self.payloads.pop(key, None)

    remote = RemoteStorage()
    storage = ConfiguredObjectStorage(object(), data_root=tmp_path / "local")
    monkeypatch.setattr(storage, "_active", lambda: remote)

    stored = storage.put(
        owner_id="owner",
        workspace_id="space",
        material_id="material-1",
        filename="notes.txt",
        payload=b"durable notes",
    )
    monkeypatch.setattr(storage, "_active", lambda: storage.local)

    assert storage.get(stored.key) == b"durable notes"
