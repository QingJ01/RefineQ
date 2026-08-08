"""Optional password-reset delivery without exposing account existence."""

from __future__ import annotations

import smtplib
import ssl
from collections.abc import Callable
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Any, Protocol
from urllib.parse import quote

from refineq.config import Settings


class PasswordResetDelivery(Protocol):
    """Delivery boundary used by the public authentication API."""

    @property
    def enabled(self) -> bool: ...

    def send(self, email: str, token: str) -> None: ...


@dataclass(frozen=True, slots=True)
class DisabledPasswordResetDelivery:
    """Explicitly unavailable delivery for installations without SMTP."""

    enabled: bool = False

    def send(self, email: str, token: str) -> None:
        del email, token


ConnectionFactory = Callable[[str, int, float, bool], Any]


def _open_smtp_connection(host: str, port: int, timeout: float, use_ssl: bool) -> Any:
    if use_ssl:
        return smtplib.SMTP_SSL(
            host,
            port,
            timeout=timeout,
            context=ssl.create_default_context(),
        )
    return smtplib.SMTP(host, port, timeout=timeout)


@dataclass(frozen=True, slots=True)
class SmtpPasswordResetDelivery:
    """Send one-time reset links through an operator-owned SMTP server."""

    host: str
    port: int
    from_email: str
    public_site_url: str
    username: str | None = None
    password: str | None = field(default=None, repr=False)
    starttls: bool = True
    use_ssl: bool = False
    timeout_seconds: float = 10.0
    connection_factory: ConnectionFactory = field(
        default=_open_smtp_connection,
        repr=False,
        compare=False,
    )
    enabled: bool = True

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        connection_factory: ConnectionFactory = _open_smtp_connection,
    ) -> SmtpPasswordResetDelivery:
        if not settings.smtp_enabled:
            raise ValueError("SMTP password reset delivery is not configured")
        return cls(
            host=settings.smtp_host or "",
            port=settings.smtp_port,
            from_email=settings.smtp_from_email or "",
            public_site_url=settings.public_site_url,
            username=settings.smtp_username,
            password=(
                settings.smtp_password.get_secret_value()
                if settings.smtp_password is not None
                else None
            ),
            starttls=settings.smtp_starttls,
            use_ssl=settings.smtp_use_ssl,
            timeout_seconds=settings.smtp_timeout_seconds,
            connection_factory=connection_factory,
        )

    def send(self, email: str, token: str) -> None:
        encoded_token = quote(token, safe="")
        reset_url = f"{self.public_site_url.rstrip('/')}/#reset-token={encoded_token}"
        message = EmailMessage()
        message["Subject"] = "Reset your RefineQ password"
        message["From"] = self.from_email
        message["To"] = email
        message.set_content(
            "Use this one-time link to reset your RefineQ password. "
            "If you did not request this, you can ignore this email.\n\n"
            f"{reset_url}\n"
        )

        with self.connection_factory(
            self.host,
            self.port,
            self.timeout_seconds,
            self.use_ssl,
        ) as connection:
            if self.starttls:
                connection.starttls(context=ssl.create_default_context())
            if self.username is not None and self.password is not None:
                connection.login(self.username, self.password)
            connection.send_message(message)


def build_password_reset_delivery(settings: Settings) -> PasswordResetDelivery:
    if not settings.smtp_enabled:
        return DisabledPasswordResetDelivery()
    return SmtpPasswordResetDelivery.from_settings(settings)
