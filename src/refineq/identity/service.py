"""Durable local accounts, password hashing, and signed access tokens."""

from __future__ import annotations

import json
import os
import re
import secrets
import tempfile
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from threading import Lock, RLock
from typing import Any

import bcrypt
from jose import JWTError, jwt

from refineq.identity.models import User

AUTH_SCHEMA_VERSION = 1
_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class IdentityError(RuntimeError):
    """Base class for expected identity failures."""


class AccountExistsError(IdentityError):
    """Raised when an email has already been registered."""


class InvalidCredentialsError(IdentityError):
    """Raised without revealing whether an account exists."""


class InvalidTokenError(IdentityError):
    """Raised when a token is malformed, unsigned, or refers to no user."""


class TokenExpiredError(InvalidTokenError):
    """Raised when a correctly signed token is no longer valid."""


class IdentityService:
    _locks_guard = Lock()
    _locks: dict[str, RLock] = {}

    def __init__(
        self,
        data_root: Path,
        *,
        token_ttl: timedelta = timedelta(hours=12),
    ) -> None:
        if token_ttl <= timedelta(0):
            raise ValueError("token_ttl must be positive")
        self._path = data_root.expanduser().resolve() / "system" / "auth.json"
        self._token_ttl = token_ttl

    @classmethod
    def _lock_for(cls, path: Path) -> RLock:
        key = os.path.normcase(str(path))
        with cls._locks_guard:
            return cls._locks.setdefault(key, RLock())

    @staticmethod
    def _canonical_email(email: str) -> str:
        canonical = email.strip().lower()
        if len(canonical) > 254 or not _EMAIL.fullmatch(canonical):
            raise ValueError("email must be a valid address")
        return canonical

    @staticmethod
    def _new_document() -> dict[str, Any]:
        return {
            "schema_version": AUTH_SCHEMA_VERSION,
            "signing_secret": secrets.token_urlsafe(48),
            "users": {},
        }

    def _load_unlocked(self) -> dict[str, Any]:
        if not self._path.exists():
            return self._new_document()
        try:
            document = json.loads(self._path.read_text(encoding="utf-8"))
            if (
                document["schema_version"] != AUTH_SCHEMA_VERSION
                or not isinstance(document["signing_secret"], str)
                or not isinstance(document["users"], dict)
            ):
                raise ValueError("invalid identity document")
            return document
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise IdentityError("Identity data is invalid") from error

    def _write_unlocked(self, document: dict[str, Any]) -> None:
        payload = json.dumps(
            document,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".auth-",
            suffix=".tmp",
            dir=self._path.parent,
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as temporary_file:
                temporary_file.write(payload)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.replace(temporary_path, self._path)
        finally:
            temporary_path.unlink(missing_ok=True)

    @staticmethod
    def _public_user(record: dict[str, Any]) -> User:
        return User.model_validate(
            {
                "id": record["id"],
                "email": record["email"],
                "display_name": record["display_name"],
                "created_at": record["created_at"],
            }
        )

    def register(self, *, email: str, password: str, display_name: str) -> User:
        email = self._canonical_email(email)
        display_name = display_name.strip()
        password_bytes = password.encode("utf-8")
        if not display_name:
            raise ValueError("display_name must not be blank")
        if len(password) < 12 or len(password_bytes) > 72:
            raise ValueError("password must contain 12 to 72 bytes")

        with self._lock_for(self._path):
            document = self._load_unlocked()
            if email in document["users"]:
                raise AccountExistsError("Account already exists")
            created_at = datetime.now(UTC)
            record = {
                "id": f"user_{sha256(email.encode()).hexdigest()[:20]}",
                "email": email,
                "display_name": display_name,
                "created_at": created_at.isoformat(),
                "password_hash": bcrypt.hashpw(
                    password_bytes,
                    bcrypt.gensalt(rounds=12),
                ).decode("ascii"),
            }
            document["users"][email] = record
            self._write_unlocked(document)
            return self._public_user(record)

    def authenticate(self, *, email: str, password: str) -> User:
        try:
            email = self._canonical_email(email)
        except ValueError as error:
            raise InvalidCredentialsError("Invalid email or password") from error

        with self._lock_for(self._path):
            document = self._load_unlocked()
            record = document["users"].get(email)
            valid = record is not None and bcrypt.checkpw(
                password.encode("utf-8"),
                record["password_hash"].encode("ascii"),
            )
            if not valid:
                raise InvalidCredentialsError("Invalid email or password")
            return self._public_user(record)

    def issue_token(self, user: User, *, now: datetime | None = None) -> str:
        now = (now or datetime.now(UTC)).astimezone(UTC)
        expires_at = now + self._token_ttl
        with self._lock_for(self._path):
            document = self._load_unlocked()
            secret = document["signing_secret"]
        return jwt.encode(
            {
                "sub": user.id,
                "email": user.email,
                "iat": int(now.timestamp()),
                "exp": int(expires_at.timestamp()),
            },
            secret,
            algorithm="HS256",
        )

    def verify_token(self, token: str, *, now: datetime | None = None) -> User:
        now = (now or datetime.now(UTC)).astimezone(UTC)
        with self._lock_for(self._path):
            document = self._load_unlocked()
            try:
                payload = jwt.decode(
                    token,
                    document["signing_secret"],
                    algorithms=["HS256"],
                    options={"verify_exp": False},
                )
            except JWTError as error:
                raise InvalidTokenError("Invalid access token") from error

            expires_at = payload.get("exp")
            if not isinstance(expires_at, int) or expires_at <= int(now.timestamp()):
                raise TokenExpiredError("Access token has expired")
            email = payload.get("email")
            subject = payload.get("sub")
            record = document["users"].get(email)
            if record is None or record.get("id") != subject:
                raise InvalidTokenError("Invalid access token")
            return self._public_user(record)
