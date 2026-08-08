from __future__ import annotations

from email.message import EmailMessage
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from refineq.config import Settings
from refineq.identity.password_reset import (
    DisabledPasswordResetDelivery,
    SmtpPasswordResetDelivery,
    build_password_reset_delivery,
)


class RecordingSmtp:
    def __init__(self) -> None:
        self.started_tls = False
        self.login_credentials: tuple[str, str] | None = None
        self.messages: list[EmailMessage] = []

    def __enter__(self) -> RecordingSmtp:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def starttls(self, *, context: Any) -> None:
        assert context is not None
        self.started_tls = True

    def login(self, username: str, password: str) -> None:
        self.login_credentials = (username, password)

    def send_message(self, message: EmailMessage) -> None:
        self.messages.append(message)


def test_password_reset_delivery_is_disabled_without_smtp(tmp_path: Path) -> None:
    settings = Settings(data_root=tmp_path / "data", _env_file=None)

    delivery = build_password_reset_delivery(settings)

    assert isinstance(delivery, DisabledPasswordResetDelivery)
    assert delivery.enabled is False


@pytest.mark.parametrize(
    "overrides",
    [
        {"smtp_host": "smtp.example.com"},
        {"smtp_from_email": "no-reply@example.com"},
        {
            "smtp_host": "smtp.example.com",
            "smtp_from_email": "no-reply@example.com",
            "smtp_username": "user",
        },
        {
            "smtp_host": "smtp.example.com",
            "smtp_from_email": "no-reply@example.com",
            "smtp_starttls": True,
            "smtp_use_ssl": True,
        },
    ],
)
def test_settings_reject_partial_or_conflicting_smtp_configuration(
    tmp_path: Path,
    overrides: dict[str, object],
) -> None:
    with pytest.raises(ValidationError, match="SMTP|smtp"):
        Settings(data_root=tmp_path / "data", _env_file=None, **overrides)


def test_settings_reject_public_site_url_without_a_host(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="public site URL"):
        Settings(
            data_root=tmp_path / "data",
            public_site_url="https:///reset",
            _env_file=None,
        )


def test_smtp_delivery_treats_empty_runtime_credentials_as_unauthenticated(
    tmp_path: Path,
) -> None:
    settings = Settings(
        data_root=tmp_path / "data",
        smtp_host="smtp.example.com",
        smtp_from_email="no-reply@example.com",
        smtp_username="",
        smtp_password="",
        _env_file=None,
    )
    connection = RecordingSmtp()
    delivery = SmtpPasswordResetDelivery.from_settings(
        settings,
        connection_factory=lambda *_: connection,
    )

    delivery.send("learner@example.com", "a-valid-reset-token-12345")

    assert connection.login_credentials is None


def test_smtp_delivery_sends_fragment_link_without_exposing_credentials(
    tmp_path: Path,
) -> None:
    settings = Settings(
        data_root=tmp_path / "data",
        public_site_url="https://learn.example.com/app",
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_from_email="RefineQ <no-reply@example.com>",
        smtp_username="smtp-user",
        smtp_password="smtp-secret",
        _env_file=None,
    )
    connection = RecordingSmtp()
    opened: list[tuple[str, int, float, bool]] = []

    def factory(host: str, port: int, timeout: float, use_ssl: bool) -> RecordingSmtp:
        opened.append((host, port, timeout, use_ssl))
        return connection

    delivery = SmtpPasswordResetDelivery.from_settings(settings, connection_factory=factory)

    delivery.send("learner@example.com", "token/with unsafe+characters")

    assert delivery.enabled is True
    assert opened == [("smtp.example.com", 587, 10.0, False)]
    assert connection.started_tls is True
    assert connection.login_credentials == ("smtp-user", "smtp-secret")
    assert len(connection.messages) == 1
    message = connection.messages[0]
    assert message["To"] == "learner@example.com"
    assert message["From"] == "RefineQ <no-reply@example.com>"
    body = message.get_content()
    assert "https://learn.example.com/app/#reset-token=token%2Fwith%20unsafe%2Bcharacters" in body
    assert "smtp-secret" not in body
