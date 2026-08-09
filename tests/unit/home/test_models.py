from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from refineq.home.models import DirectAnswer, HomeDispatchRequest, HomeDispatchResult


def test_dispatch_request_strips_text_and_accepts_twelve_thousand_characters() -> None:
    request = HomeDispatchRequest(request_id="req", text=f"  {'a' * 12_000}  ")
    assert len(request.text) == 12_000


def test_dispatch_request_rejects_over_limit() -> None:
    with pytest.raises(ValidationError):
        HomeDispatchRequest(request_id="req", text="a" * 12_001)


def test_result_requires_payload_matching_kind() -> None:
    with pytest.raises(ValidationError):
        HomeDispatchResult(
            request_id="req",
            kind="open_workspace",
            reason="test",
            confidence=1,
            decided_by="rule",
            expires_at=datetime.now(UTC),
            answer=DirectAnswer(
                content="answer",
                basis="general_knowledge",
                convertible_goal="goal",
            ),
        )

