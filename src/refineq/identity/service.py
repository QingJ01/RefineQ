"""Database-backed accounts, roles, password hashing, and signed access tokens."""

from __future__ import annotations

import base64
import binascii
import re
import secrets
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from threading import RLock

import bcrypt
import jwt
from jwt import InvalidTokenError as JWTInvalidTokenError
from sqlalchemy import delete, insert, select, update
from sqlalchemy.exc import IntegrityError

from refineq.database.engine import Database
from refineq.database.schema import (
    audit_logs,
    integration_settings,
    material_chunks,
    materials,
    password_reset_tokens,
    records,
    system_settings,
    users,
    utc_now,
)
from refineq.identity.models import AccountExportResponse, User

_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_SIGNING_SECRET_KEY = "jwt_signing_secret"
_SESSION_VERSION_PREFIX = "user_session_version:"


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


class InvalidResetTokenError(IdentityError, ValueError):
    """Raised for expired, used, or unknown password reset tokens."""


class AccountDeletionError(IdentityError):
    """Raised when an account cannot be safely removed."""


class IdentityService:
    """Keep authentication state in the shared application database."""

    def __init__(
        self,
        database: Database | Path,
        *,
        token_ttl: timedelta = timedelta(hours=12),
    ) -> None:
        if token_ttl <= timedelta(0):
            raise ValueError("token_ttl must be positive")
        if isinstance(database, Path):
            path = database.expanduser().resolve() / "system" / "refineq.sqlite3"
            database = Database(f"sqlite+pysqlite:///{path.as_posix()}")
            database.initialize()
        self.database = database
        self._token_ttl = token_ttl
        self._lock = RLock()

    @staticmethod
    def _canonical_email(email: str) -> str:
        canonical = email.strip().lower()
        if len(canonical) > 254 or not _EMAIL.fullmatch(canonical):
            raise ValueError("email must be a valid address")
        return canonical

    @staticmethod
    def _aware(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @classmethod
    def _public_user(cls, row) -> User:
        return User(
            id=row.id,
            email=row.email,
            display_name=row.display_name,
            role=row.role,
            created_at=cls._aware(row.created_at),
        )

    def _signing_secret(self) -> str:
        with self._lock, self.database.session() as session:
            value = session.scalar(
                select(system_settings.c.value).where(system_settings.c.key == _SIGNING_SECRET_KEY)
            )
            if value is not None:
                return str(value)
            value = secrets.token_urlsafe(48)
            session.execute(
                insert(system_settings).values(
                    key=_SIGNING_SECRET_KEY,
                    value=value,
                    updated_at=utc_now(),
                )
            )
            return value

    @staticmethod
    def _session_version_key(user_id: str) -> str:
        return f"{_SESSION_VERSION_PREFIX}{user_id}"

    def _session_version(self, session, user_id: str) -> int:
        value = session.scalar(
            select(system_settings.c.value).where(
                system_settings.c.key == self._session_version_key(user_id)
            )
        )
        return int(value or 0)

    @staticmethod
    def _validate_password(password: str, *, minimum: int) -> bytes:
        password_bytes = password.encode("utf-8")
        if not minimum <= len(password_bytes) <= 72:
            raise ValueError(f"password must contain {minimum} to 72 bytes")
        return password_bytes

    def register(self, *, email: str, password: str, display_name: str) -> User:
        email = self._canonical_email(email)
        display_name = display_name.strip()
        password_bytes = self._validate_password(password, minimum=12)
        if not display_name:
            raise ValueError("display_name must not be blank")

        created_at = datetime.now(UTC)
        user_id = f"user_{sha256(email.encode()).hexdigest()[:20]}"
        try:
            with self.database.session() as session:
                session.execute(
                    insert(users).values(
                        id=user_id,
                        email=email,
                        display_name=display_name,
                        password_hash=bcrypt.hashpw(
                            password_bytes,
                            bcrypt.gensalt(rounds=12),
                        ).decode("ascii"),
                        role="learner",
                        created_at=created_at,
                        updated_at=created_at,
                    )
                )
        except IntegrityError as error:
            raise AccountExistsError("Account already exists") from error
        return User(
            id=user_id,
            email=email,
            display_name=display_name,
            role="learner",
            created_at=created_at,
        )

    def authenticate(self, *, email: str, password: str) -> User:
        try:
            email = self._canonical_email(email)
            password_bytes = self._validate_password(password, minimum=1)
        except ValueError as error:
            raise InvalidCredentialsError("Invalid email or password") from error

        with self.database.session() as session:
            row = session.execute(select(users).where(users.c.email == email)).one_or_none()
        valid = row is not None and bcrypt.checkpw(
            password_bytes,
            row.password_hash.encode("ascii"),
        )
        if not valid:
            raise InvalidCredentialsError("Invalid email or password")
        return self._public_user(row)

    def verify_current_password(self, user_id: str, password: str) -> User:
        try:
            password_bytes = self._validate_password(password, minimum=1)
        except ValueError as error:
            raise InvalidCredentialsError("Invalid current password") from error
        with self.database.session() as session:
            row = session.execute(select(users).where(users.c.id == user_id)).one_or_none()
        if row is None or not bcrypt.checkpw(
            password_bytes,
            row.password_hash.encode("ascii"),
        ):
            raise InvalidCredentialsError("Invalid current password")
        return self._public_user(row)

    def update_profile(self, user_id: str, *, display_name: str) -> User:
        normalized = display_name.strip()
        if not normalized:
            raise ValueError("display_name must not be blank")
        with self._lock, self.database.session() as session:
            updated = session.execute(
                update(users)
                .where(users.c.id == user_id)
                .values(display_name=normalized, updated_at=utc_now())
            )
            if updated.rowcount != 1:
                raise InvalidTokenError("Invalid access token")
            row = session.execute(select(users).where(users.c.id == user_id)).one()
        return self._public_user(row)

    def change_password(
        self,
        user_id: str,
        *,
        current_password: str,
        new_password: str,
    ) -> None:
        current_bytes = self._validate_password(current_password, minimum=1)
        new_bytes = self._validate_password(new_password, minimum=12)
        with self._lock, self.database.session() as session:
            statement = select(users).where(users.c.id == user_id)
            if self.database.is_postgresql:
                statement = statement.with_for_update()
            row = session.execute(statement).one_or_none()
            if row is None or not bcrypt.checkpw(
                current_bytes,
                row.password_hash.encode("ascii"),
            ):
                raise InvalidCredentialsError("Invalid current password")
            session.execute(
                update(users)
                .where(users.c.id == user_id)
                .values(
                    password_hash=bcrypt.hashpw(
                        new_bytes,
                        bcrypt.gensalt(rounds=12),
                    ).decode("ascii"),
                    updated_at=utc_now(),
                )
            )

    def revoke_sessions(self, user_id: str) -> None:
        key = self._session_version_key(user_id)
        with self._lock, self.database.session() as session:
            if session.scalar(select(users.c.id).where(users.c.id == user_id)) is None:
                raise InvalidTokenError("Invalid access token")
            next_version = self._session_version(session, user_id) + 1
            changed = session.execute(
                update(system_settings)
                .where(system_settings.c.key == key)
                .values(value=str(next_version), updated_at=utc_now())
            )
            if changed.rowcount == 0:
                session.execute(
                    insert(system_settings).values(
                        key=key,
                        value=str(next_version),
                        updated_at=utc_now(),
                    )
                )

    def export_account(self, user: User) -> AccountExportResponse:
        with self.database.session() as session:
            owner_records = session.execute(
                select(records)
                .where(records.c.owner_id == user.id)
                .order_by(records.c.collection, records.c.record_id)
            ).all()
            owner_materials = session.execute(
                select(materials)
                .where(materials.c.owner_id == user.id)
                .order_by(materials.c.project_id, materials.c.material_id)
            ).all()
        return AccountExportResponse(
            exported_at=datetime.now(UTC),
            user=user,
            records=[
                {
                    "owner_id": row.owner_id,
                    "collection": row.collection,
                    "record_id": row.record_id,
                    "schema_version": row.schema_version,
                    "version": row.version,
                    "data": row.data,
                    "updated_at": self._aware(row.updated_at),
                }
                for row in owner_records
            ],
            materials=[
                {
                    "owner_id": row.owner_id,
                    "project_id": row.project_id,
                    "material_id": row.material_id,
                    "filename": row.filename,
                    "content_type": row.content_type,
                    "size": row.size,
                    "status": row.status,
                    "chunk_count": row.chunk_count,
                    "content_sha256": row.content_sha256,
                    "indexed_at": self._aware(row.indexed_at),
                }
                for row in owner_materials
            ],
        )

    def account_storage_keys(self, user_id: str) -> list[str]:
        with self.database.session() as session:
            return [
                str(value)
                for value in session.scalars(
                    select(materials.c.storage_key).where(
                        materials.c.owner_id == user_id,
                        materials.c.storage_key.is_not(None),
                    )
                )
                if value
            ]

    def delete_account(self, user_id: str, *, current_password: str) -> None:
        with self._lock:
            self.verify_current_password(user_id, current_password)
            with self.database.session() as session:
                if session.scalar(
                    select(integration_settings.c.kind).where(
                        integration_settings.c.updated_by == user_id
                    ).limit(1)
                ) is not None:
                    raise AccountDeletionError(
                        "Transfer platform integration ownership before deleting this account"
                    )
                session.execute(
                    delete(material_chunks).where(material_chunks.c.owner_id == user_id)
                )
                session.execute(delete(materials).where(materials.c.owner_id == user_id))
                session.execute(delete(records).where(records.c.owner_id == user_id))
                session.execute(
                    delete(password_reset_tokens).where(password_reset_tokens.c.user_id == user_id)
                )
                session.execute(delete(audit_logs).where(audit_logs.c.actor_id == user_id))
                session.execute(
                    delete(system_settings).where(
                        system_settings.c.key == self._session_version_key(user_id)
                    )
                )
                deleted = session.execute(delete(users).where(users.c.id == user_id))
                if deleted.rowcount != 1:
                    raise InvalidTokenError("Invalid access token")

    def request_password_reset(
        self,
        email: str,
        *,
        now: datetime | None = None,
        ttl: timedelta = timedelta(minutes=20),
    ) -> str | None:
        if ttl <= timedelta(0):
            raise ValueError("password reset ttl must be positive")
        try:
            email = self._canonical_email(email)
        except ValueError:
            return None
        observed_at = (now or datetime.now(UTC)).astimezone(UTC)
        with self._lock, self.database.session() as session:
            user_id = session.scalar(select(users.c.id).where(users.c.email == email))
            if user_id is None:
                return None
            token = secrets.token_urlsafe(32)
            session.execute(
                insert(password_reset_tokens).values(
                    token_hash=sha256(token.encode("utf-8")).hexdigest(),
                    user_id=user_id,
                    expires_at=observed_at + ttl,
                    used_at=None,
                    created_at=observed_at,
                )
            )
        return token

    def reset_password(
        self,
        token: str,
        password: str,
        *,
        now: datetime | None = None,
    ) -> None:
        observed_at = (now or datetime.now(UTC)).astimezone(UTC)
        password_bytes = self._validate_password(password, minimum=12)
        token_hash = sha256(token.encode("utf-8")).hexdigest()
        with self._lock, self.database.session() as session:
            statement = select(password_reset_tokens).where(
                password_reset_tokens.c.token_hash == token_hash
            )
            if self.database.is_postgresql:
                statement = statement.with_for_update()
            row = session.execute(statement).one_or_none()
            invalid = (
                row is None or row.used_at is not None or self._aware(row.expires_at) <= observed_at
            )
            if invalid:
                raise InvalidResetTokenError("Invalid or expired password reset token")
            session.execute(
                update(users)
                .where(users.c.id == row.user_id)
                .values(
                    password_hash=bcrypt.hashpw(
                        password_bytes,
                        bcrypt.gensalt(rounds=12),
                    ).decode("ascii"),
                    updated_at=observed_at,
                )
            )
            session.execute(
                update(password_reset_tokens)
                .where(
                    password_reset_tokens.c.user_id == row.user_id,
                    password_reset_tokens.c.used_at.is_(None),
                )
                .values(used_at=observed_at)
            )

    def create_or_update_admin(
        self,
        *,
        email: str,
        password: str,
        display_name: str,
    ) -> tuple[User, bool]:
        email = self._canonical_email(email)
        display_name = display_name.strip()
        password_bytes = self._validate_password(password, minimum=12)
        if not display_name:
            raise ValueError("display_name must not be blank")
        password_hash = bcrypt.hashpw(password_bytes, bcrypt.gensalt(rounds=12)).decode("ascii")

        with self._lock, self.database.session() as session:
            row = session.execute(select(users).where(users.c.email == email)).one_or_none()
            if row is None:
                created_at = datetime.now(UTC)
                user_id = f"user_{sha256(email.encode()).hexdigest()[:20]}"
                session.execute(
                    insert(users).values(
                        id=user_id,
                        email=email,
                        display_name=display_name,
                        password_hash=password_hash,
                        role="admin",
                        created_at=created_at,
                        updated_at=created_at,
                    )
                )
                return (
                    User(
                        id=user_id,
                        email=email,
                        display_name=display_name,
                        role="admin",
                        created_at=created_at,
                    ),
                    True,
                )
            session.execute(
                update(users)
                .where(users.c.id == row.id)
                .values(
                    display_name=display_name,
                    password_hash=password_hash,
                    role="admin",
                    updated_at=utc_now(),
                )
            )
            return (
                User(
                    id=row.id,
                    email=row.email,
                    display_name=display_name,
                    role="admin",
                    created_at=self._aware(row.created_at),
                ),
                False,
            )

    def issue_token(self, user: User, *, now: datetime | None = None) -> str:
        now = (now or datetime.now(UTC)).astimezone(UTC)
        expires_at = now + self._token_ttl
        with self.database.session() as session:
            row = session.execute(
                select(users.c.password_hash).where(
                    users.c.id == user.id,
                    users.c.email == user.email,
                )
            ).one_or_none()
            session_version = self._session_version(session, user.id)
        if row is None:
            raise InvalidTokenError("Invalid access token")
        password_hash = row.password_hash
        return jwt.encode(
            {
                "sub": user.id,
                "email": user.email,
                "credential": sha256(str(password_hash).encode("utf-8")).hexdigest(),
                "session_version": session_version,
                "iat": int(now.timestamp()),
                "exp": int(expires_at.timestamp()),
            },
            self._signing_secret(),
            algorithm="HS256",
        )

    @staticmethod
    def _require_canonical_token(token: str) -> None:
        """Reject alternate Base64URL spellings that decode to the same JWT bytes."""

        segments = token.split(".")
        if len(segments) != 3 or any(not segment for segment in segments):
            raise InvalidTokenError("Invalid access token")
        try:
            for segment in segments:
                decoded = base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))
                canonical = base64.urlsafe_b64encode(decoded).rstrip(b"=").decode("ascii")
                if canonical != segment:
                    raise InvalidTokenError("Invalid access token")
        except (binascii.Error, UnicodeError) as error:
            raise InvalidTokenError("Invalid access token") from error

    def verify_token(self, token: str, *, now: datetime | None = None) -> User:
        now = (now or datetime.now(UTC)).astimezone(UTC)
        self._require_canonical_token(token)
        try:
            payload = jwt.decode(
                token,
                self._signing_secret(),
                algorithms=["HS256"],
                options={"verify_exp": False, "verify_iat": False},
            )
        except JWTInvalidTokenError as error:
            raise InvalidTokenError("Invalid access token") from error

        issued_at = payload.get("iat")
        if (
            not isinstance(issued_at, int)
            or isinstance(issued_at, bool)
            or issued_at > int(now.timestamp())
        ):
            raise InvalidTokenError("Invalid access token")
        expires_at = payload.get("exp")
        if (
            not isinstance(expires_at, int)
            or isinstance(expires_at, bool)
            or expires_at <= int(now.timestamp())
        ):
            raise TokenExpiredError("Access token has expired")
        email = payload.get("email")
        subject = payload.get("sub")
        credential = payload.get("credential")
        session_version = payload.get("session_version", 0)
        if (
            not isinstance(credential, str)
            or not isinstance(session_version, int)
            or isinstance(session_version, bool)
        ):
            raise InvalidTokenError("Invalid access token")
        with self.database.session() as session:
            row = session.execute(
                select(users).where(users.c.id == subject, users.c.email == email)
            ).one_or_none()
            current_session_version = (
                self._session_version(session, str(subject)) if row is not None else 0
            )
        if row is None or not secrets.compare_digest(
            credential,
            sha256(row.password_hash.encode("utf-8")).hexdigest(),
        ) or session_version != current_session_version:
            raise InvalidTokenError("Invalid access token")
        return self._public_user(row)

    def count_users(self) -> int:
        from sqlalchemy import func

        with self.database.session() as session:
            return int(session.scalar(select(func.count()).select_from(users)) or 0)
