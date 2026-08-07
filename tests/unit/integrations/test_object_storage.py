"""Local and S3-compatible object storage tests."""

from __future__ import annotations

from pydantic import SecretStr

from refineq.integrations.models import IntegrationKind, IntegrationSettings
from refineq.integrations.object_storage import LocalObjectStorage, S3ObjectStorage


class FakeS3Client:
    def __init__(self) -> None:
        self.puts: list[dict] = []
        self.deletes: list[dict] = []

    def put_object(self, **kwargs) -> None:
        self.puts.append(kwargs)

    def delete_object(self, **kwargs) -> None:
        self.deletes.append(kwargs)

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

    assert stored.key == "users/owner/workspaces/space/materials/material-1.pdf"
    assert (tmp_path / stored.key).read_bytes() == b"pdf bytes"
    storage.delete(stored.key)
    assert not (tmp_path / stored.key).exists()


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
    storage = S3ObjectStorage(settings, client_factory=lambda **_: client)

    stored = storage.put(
        owner_id="owner",
        workspace_id="space",
        material_id="material-1",
        filename="notes.docx",
        payload=b"document",
    )
    storage.delete(stored.key)

    assert client.puts == [
        {
            "Bucket": "refineq-private",
            "Key": stored.key,
            "Body": b"document",
            "ContentType": "application/octet-stream",
        }
    ]
    assert client.deletes == [{"Bucket": "refineq-private", "Key": stored.key}]
