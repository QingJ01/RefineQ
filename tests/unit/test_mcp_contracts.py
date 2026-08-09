from mcp import types

from refineq.mcp.contracts import BeginDemoOutput, LearningContextOutput, McpError
from refineq.mcp.errors import error_result, success_result


def test_success_result_has_structured_and_text_content() -> None:
    payload = BeginDemoOutput(
        run_id="run-token",
        expires_at="2026-08-09T12:00:00Z",
        simulation=True,
        space={"id": "space", "title": "极限与连续性", "material_count": 1},
        runtime={"observed_at": None, "stale": True},
        next_tool="refineq_get_learning_context",
    )

    result = success_result(payload, text="Evaluation sandbox is ready.")

    assert isinstance(result, types.CallToolResult)
    assert result.is_error is False
    assert result.structured_content == payload.model_dump(mode="json", exclude_none=True)
    assert result.content[0].text == "Evaluation sandbox is ready."


def test_error_result_is_structured_and_does_not_expose_exception_details() -> None:
    result = error_result(
        BeginDemoOutput,
        McpError(
            code="internal_error",
            message="The request could not be completed.",
            retryable=True,
        ),
        correlation_id="correlation-safe",
    )

    assert result.is_error is True
    assert result.structured_content == {
        "schema_version": "1",
        "error": {
            "code": "internal_error",
            "message": "The request could not be completed.",
            "retryable": True,
        },
        "warnings": [],
    }
    assert "correlation-safe" not in result.content[0].text


def test_success_result_keeps_required_nullable_fields_in_structured_content() -> None:
    payload = LearningContextOutput(
        run_id="run-token",
        workspace={"id": "sandbox"},
        topics=[],
        today_sessions=[],
        pending_question=None,
        materials={"indexed_count": 1, "items": []},
        latest_evidence=[],
        next_action={"tool": "refineq_get_practice_task"},
        state_version=3,
        simulation=True,
    )

    result = success_result(payload, text="Learning context loaded.")

    assert "pending_question" in result.structured_content
    assert result.structured_content["pending_question"] is None
