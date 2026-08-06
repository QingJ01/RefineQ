"""Tests for material-upload security and resource limits."""

from __future__ import annotations

import pytest

from refineq.knowledge.policy import (
    MaterialPolicy,
    MaterialPolicyError,
    UploadDescriptor,
)


def test_supported_extension_and_mime_are_accepted() -> None:
    policy = MaterialPolicy()

    policy.validate_batch(
        [UploadDescriptor(filename="calculus.pdf", content_type="application/pdf", size=20)]
    )


@pytest.mark.parametrize("filename", ["../secret.txt", "..\\secret.txt", "/tmp/a.txt"])
def test_path_like_filenames_are_rejected(filename: str) -> None:
    policy = MaterialPolicy()

    with pytest.raises(MaterialPolicyError, match="filename"):
        policy.validate_batch(
            [UploadDescriptor(filename=filename, content_type="text/plain", size=1)]
        )


def test_extension_must_match_the_declared_mime() -> None:
    policy = MaterialPolicy()

    with pytest.raises(MaterialPolicyError, match="MIME"):
        policy.validate_batch(
            [UploadDescriptor(filename="notes.pdf", content_type="text/plain", size=20)]
        )


def test_count_per_file_and_batch_limits_are_independent() -> None:
    policy = MaterialPolicy(max_files=2, max_file_bytes=5, max_batch_bytes=8)

    with pytest.raises(MaterialPolicyError, match="Too many"):
        policy.validate_batch(
            [
                UploadDescriptor(filename=f"{index}.txt", content_type="text/plain", size=1)
                for index in range(3)
            ]
        )
    with pytest.raises(MaterialPolicyError, match="per-file"):
        policy.validate_batch(
            [UploadDescriptor(filename="large.txt", content_type="text/plain", size=6)]
        )
    with pytest.raises(MaterialPolicyError, match="batch"):
        policy.validate_batch(
            [
                UploadDescriptor(filename="one.txt", content_type="text/plain", size=5),
                UploadDescriptor(filename="two.txt", content_type="text/plain", size=4),
            ]
        )
