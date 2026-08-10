from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from refineq.config import Settings


def test_mcp_is_disabled_by_default(tmp_path: Path) -> None:
    settings = Settings(data_root=tmp_path / "data", _env_file=None)

    assert settings.mcp_enabled is False
    assert settings.mcp_internal_secret is None
    assert settings.mcp_account_email is None
    assert settings.mcp_run_ttl_seconds == 300
    assert settings.mcp_idempotency_ttl_seconds == 86_400


@pytest.mark.parametrize(
    ("secret", "email", "hosts"),
    [
        (None, "qingj1314@163.com", "localhost"),
        (SecretStr("too-short"), "qingj1314@163.com", "localhost"),
        (SecretStr("secure-internal-signing-key-1234567890"), None, "localhost"),
        (SecretStr("secure-internal-signing-key-1234567890"), "qingj1314@163.com", ""),
    ],
)
def test_enabled_mcp_fails_closed_without_strong_configuration(
    tmp_path: Path,
    secret: SecretStr | None,
    email: str | None,
    hosts: str,
) -> None:
    with pytest.raises(ValidationError):
        Settings(
            data_root=tmp_path / "data",
            mcp_enabled=True,
            mcp_internal_secret=secret,
            mcp_account_email=email,
            mcp_allowed_hosts=hosts,
            _env_file=None,
        )


def test_mcp_internal_secret_does_not_leak_and_account_is_normalized(tmp_path: Path) -> None:
    secret = "mcp-internal-secret-that-is-long-enough-123456"
    settings = Settings(
        data_root=tmp_path / "data",
        mcp_enabled=True,
        mcp_internal_secret=SecretStr(secret),
        mcp_account_email=" QingJ1314@163.COM ",
        mcp_allowed_hosts="localhost,refineq.example",
        _env_file=None,
    )

    assert secret not in repr(settings)
    assert settings.mcp_account_email == "qingj1314@163.com"
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
            mcp_internal_secret=SecretStr(secret),
            mcp_account_email="qingj1314@163.com",
            mcp_allowed_hosts=hosts,
            _env_file=None,
        )
