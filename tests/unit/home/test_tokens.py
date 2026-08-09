from datetime import UTC, datetime, timedelta

import pytest

from refineq.home.tokens import HomeTokenError, HomeTokenSigner, proposal_hash

NOW = datetime(2026, 8, 9, 12, tzinfo=UTC)


def test_token_binds_owner_operation_payload_and_expiry() -> None:
    signer = HomeTokenSigner(secret=b"x" * 32, ttl=timedelta(minutes=10))
    token, expires_at = signer.issue(
        owner_id="owner-a",
        operation="create_workspace",
        target=None,
        proposal={"goal": "math"},
        state_hash="snapshot",
        now=NOW,
    )
    claims = signer.verify(
        token,
        owner_id="owner-a",
        operation="create_workspace",
        now=NOW,
    )
    assert expires_at == NOW + timedelta(minutes=10)
    assert claims.proposal_hash == proposal_hash({"goal": "math"})
    with pytest.raises(HomeTokenError):
        signer.verify(token, owner_id="owner-b", now=NOW)
    with pytest.raises(HomeTokenError):
        signer.verify(token, owner_id="owner-a", operation="delete_workspace", now=NOW)
    with pytest.raises(HomeTokenError):
        signer.verify(token, owner_id="owner-a", now=expires_at)


def test_token_rejects_tampering() -> None:
    signer = HomeTokenSigner(secret=b"x" * 32)
    token, _ = signer.issue(
        owner_id="owner-a",
        operation="clarify",
        proposal={},
        state_hash="snapshot",
        now=NOW,
    )
    with pytest.raises(HomeTokenError):
        signer.verify(f"a{token}", owner_id="owner-a", now=NOW)

