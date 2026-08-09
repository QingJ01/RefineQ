"""Short-lived HMAC tokens for stateless home confirmations and clarifications."""

from __future__ import annotations

import base64
import hmac
import json
import os
import secrets
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator


class HomeTokenError(ValueError):
    """Raised when a home action token is invalid, expired, or bound elsewhere."""


class HomeTokenClaims(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    owner_id: str
    operation: str
    target: str | None = None
    proposal_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    state_hash: str
    expires_at: datetime
    nonce: str

    @field_validator("expires_at", mode="after")
    @classmethod
    def normalize_expiry(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("expires_at must be timezone-aware")
        return value.astimezone(UTC)


def proposal_hash(value: object) -> str:
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(serialized.encode()).hexdigest()


def _encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode(raw: str) -> bytes:
    return base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))


class HomeTokenSigner:
    def __init__(
        self,
        *,
        key_path: Path | None = None,
        secret: bytes | None = None,
        ttl: timedelta = timedelta(minutes=10),
    ) -> None:
        if secret is None and key_path is None:
            raise ValueError("key_path or secret is required")
        if ttl.total_seconds() <= 0:
            raise ValueError("ttl must be positive")
        self._secret = secret or self._load_or_create_key(key_path)
        self._ttl = ttl

    @staticmethod
    def _load_or_create_key(key_path: Path | None) -> bytes:
        if key_path is None:
            raise ValueError("key_path is required")
        resolved = key_path.expanduser().resolve()
        resolved.parent.mkdir(parents=True, exist_ok=True)
        try:
            value = resolved.read_bytes()
        except FileNotFoundError:
            value = secrets.token_bytes(32)
            try:
                descriptor = os.open(resolved, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                value = resolved.read_bytes()
            else:
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(value)
                    stream.flush()
                    os.fsync(stream.fileno())
        if len(value) < 32:
            raise ValueError("home action signing key must contain at least 32 bytes")
        return value

    def issue(
        self,
        *,
        owner_id: str,
        operation: str,
        proposal: object,
        state_hash: str,
        target: str | None = None,
        now: datetime | None = None,
    ) -> tuple[str, datetime]:
        observed_at = (now or datetime.now(UTC)).astimezone(UTC)
        expires_at = observed_at + self._ttl
        claims = HomeTokenClaims(
            owner_id=owner_id,
            operation=operation,
            target=target,
            proposal_hash=proposal_hash(proposal),
            state_hash=state_hash,
            expires_at=expires_at,
            nonce=secrets.token_urlsafe(16),
        )
        body = json.dumps(
            claims.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        encoded = _encode(body)
        signature = _encode(hmac.new(self._secret, encoded.encode(), sha256).digest())
        return f"{encoded}.{signature}", expires_at

    def verify(
        self,
        token: str,
        *,
        owner_id: str,
        operation: str | None = None,
        now: datetime | None = None,
    ) -> HomeTokenClaims:
        try:
            encoded, supplied_signature = token.split(".", 1)
            expected_signature = _encode(hmac.new(self._secret, encoded.encode(), sha256).digest())
            if not hmac.compare_digest(supplied_signature, expected_signature):
                raise HomeTokenError("Confirmation token signature is invalid")
            claims = HomeTokenClaims.model_validate_json(_decode(encoded))
        except HomeTokenError:
            raise
        except Exception as error:
            raise HomeTokenError("Confirmation token is malformed") from error
        observed_at = (now or datetime.now(UTC)).astimezone(UTC)
        if claims.expires_at <= observed_at:
            raise HomeTokenError("Confirmation token has expired")
        if not hmac.compare_digest(claims.owner_id, owner_id):
            raise HomeTokenError("Confirmation token belongs to another user")
        if operation is not None and claims.operation != operation:
            raise HomeTokenError("Confirmation token operation does not match")
        return claims
