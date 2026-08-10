from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from scripts import mcp_smoke


def test_smoke_fails_when_the_reported_learning_loop_did_not_succeed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def invalid_result(_url: str, _secret: str, *, trust_env: bool = True):
        del trust_env
        return {
            "protocol_versions": ["2026-07-28"],
            "tools": sorted(mcp_smoke.EXPECTED_TOOLS),
            "material_count": 0,
            "search_results": 0,
            "task_citations": 0,
            "grade_citations": 0,
            "grounding": "general",
            "passed": False,
            "mastery_changed": False,
            "final_status": "active",
            "idempotency_replay": True,
            "second_run_reset": True,
            "mode": "ai",
            "grading_mode": "ai",
        }

    monkeypatch.setattr(mcp_smoke, "_run", invalid_result)
    monkeypatch.setenv("REFINEQ_MCP_EVALUATION_SECRET", "not-printed")
    monkeypatch.setattr(sys, "argv", ["mcp_smoke.py", "--url", "https://mcp.example.test/mcp"])

    with pytest.raises(RuntimeError, match="material_count"):
        mcp_smoke.main()


def test_smoke_can_require_the_deterministic_fallback_path() -> None:
    report = {
        "protocol_versions": ["2026-07-28"],
        "tools": sorted(mcp_smoke.EXPECTED_TOOLS),
        "material_count": 1,
        "search_results": 1,
        "task_citations": 1,
        "grade_citations": 1,
        "grounding": "material",
        "passed": True,
        "mastery_changed": True,
        "final_status": "completed",
        "idempotency_replay": True,
        "second_run_reset": True,
        "mode": "ai",
        "grading_mode": "ai",
    }

    with pytest.raises(RuntimeError, match="required_mode"):
        mcp_smoke._validate_report(report, required_mode="fallback")


def test_payload_is_validated_against_the_published_output_schema() -> None:
    result = SimpleNamespace(
        is_error=False,
        structured_content={"schema_version": "1"},
    )
    schema = {
        "type": "object",
        "required": ["schema_version", "run_id"],
        "properties": {
            "schema_version": {"const": "1"},
            "run_id": {"type": "string"},
        },
    }

    with pytest.raises(RuntimeError, match="outputSchema"):
        mcp_smoke._payload(result, output_schema=schema)
