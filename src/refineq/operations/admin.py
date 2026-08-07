"""Idempotent administrator bootstrap workflow."""

from __future__ import annotations

from dataclasses import dataclass

from refineq.identity.models import User
from refineq.identity.service import IdentityService


@dataclass(frozen=True, slots=True)
class AdminBootstrapResult:
    user: User
    created: bool


def ensure_admin(
    identity: IdentityService,
    *,
    email: str,
    password: str,
    display_name: str,
) -> AdminBootstrapResult:
    """Create an administrator or promote and reset an existing account."""

    user, created = identity.create_or_update_admin(
        email=email,
        password=password,
        display_name=display_name,
    )
    return AdminBootstrapResult(user=user, created=created)
