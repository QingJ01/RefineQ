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
from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError

from refineq.database.engine import Database
from refineq.database.schema import password_reset_tokens, system_settings, users, utc_now
from refineq.identity.models import User

_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_SIGNING_SECRET_KEY = "jwt_signing_secret"


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
            password_hash = session.scalar(
                select(users.c.password_hash).where(
                    users.c.id == user.id,
                    users.c.email == user.email,
                )
            )
        if not password_hash:
            raise InvalidTokenError("Invalid access token")
        return jwt.encode(
            {
                "sub": user.id,
                "email": user.email,
                "credential": sha256(str(password_hash).encode("utf-8")).hexdigest(),
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
        if not isinstance(credential, str):
            raise InvalidTokenError("Invalid access token")
        with self.database.session() as session:
            row = session.execute(
                select(users).where(users.c.id == subject, users.c.email == email)
            ).one_or_none()
        if row is None or not secrets.compare_digest(
            credential,
            sha256(row.password_hash.encode("utf-8")).hexdigest(),
        ):
            raise InvalidTokenError("Invalid access token")
        return self._public_user(row)

    def count_users(self) -> int:
        from sqlalchemy import func

        with self.database.session() as session:
            return int(session.scalar(select(func.count()).select_from(users)) or 0)
