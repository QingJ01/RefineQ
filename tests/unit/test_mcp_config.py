from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from refineq.config import Settings


def test_mcp_is_disabled_by_default(tmp_path: Path) -> None:
    settings = Settings(data_root=tmp_path / "data", _env_file=None)

    assert settings.mcp_enabled is False
    assert settings.mcp_evaluation_secret is None
    assert settings.mcp_run_ttl_seconds == 300
    assert settings.mcp_idempotency_ttl_seconds == 86_400


@pytest.mark.parametrize(
    ("secret", "hosts"),
    [
        (None, "localhost"),
        (SecretStr("too-short"), "localhost"),
        (SecretStr("x" * 48), ""),
    ],
)
def test_enabled_mcp_fails_closed_without_strong_configuration(
    tmp_path: Path,
    secret: SecretStr | None,
    hosts: str,
) -> None:
    with pytest.raises(ValidationError):
        Settings(
            data_root=tmp_path / "data",
            mcp_enabled=True,
            mcp_evaluation_secret=secret,
            mcp_allowed_hosts=hosts,
            _env_file=None,
        )


def test_mcp_secret_does_not_leak_from_settings_repr(tmp_path: Path) -> None:
    secret = "mcp-evaluation-secret-that-is-long-enough-123456"
    settings = Settings(
        data_root=tmp_path / "data",
        mcp_enabled=True,
        mcp_evaluation_secret=SecretStr(secret),
        mcp_allowed_hosts="localhost,refineq.example",
        _env_file=None,
    )

    assert secret not in repr(settings)
    assert settings.allowed_mcp_hosts == {"localhost", "refineq.example"}


@pytest.mark.parametrize(
    ("secret", "hosts"),
    [
        ("x" * 48, "localhost"),
        ("change-me-with-a-real-random-secret-123456789", "localhost"),
        ("example-evaluation-token-1234567890-abcdef", "localhost"),
        ("mcp-evaluation-secret-that-is-long-enough-123456", "https://example.com"),
        ("mcp-evaluation-secret-that-is-long-enough-123456", "*.example.com"),
    ],
)
def test_mcp_rejects_low_entropy_secrets_and_broad_host_patterns(
    tmp_path: Path,
    secret: str,
    hosts: str,
) -> None:
    with pytest.raises(ValidationError):
        Settings(
            data_root=tmp_path / "data",
            mcp_enabled=True,
            mcp_evaluation_secret=SecretStr(secret),
            mcp_allowed_hosts=hosts,
            _env_file=None,
        )
