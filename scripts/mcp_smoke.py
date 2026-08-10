"""Run the complete Phase A flow through an independent official MCP HTTP client."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from uuid import uuid4

import httpx2
from jsonschema.exceptions import SchemaError, ValidationError
from jsonschema.validators import validator_for
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

EXPECTED_TOOLS = {
    "refineq_begin_demo",
    "refineq_get_learning_context",
    "refineq_search_materials",
    "refineq_get_practice_task",
    "refineq_submit_answer",
}


def _validate_report(
    result: dict[str, object],
    *,
    required_mode: str | None = None,
    expected_account: str | None = None,
) -> None:
    checks = (
        ("protocol_versions", "2026-07-28" in result.get("protocol_versions", [])),
        ("tools", set(result.get("tools", [])) == EXPECTED_TOOLS),
        (
            "account_email",
            expected_account is None or result.get("account_email") == expected_account,
        ),
        ("material_count", int(result.get("material_count", 0)) >= 1),
        ("search_results", int(result.get("search_results", 0)) >= 1),
        ("task_citations", int(result.get("task_citations", 0)) >= 1),
        ("grade_citations", int(result.get("grade_citations", 0)) >= 1),
        ("grounding", result.get("grounding") == "material"),
        ("passed", result.get("passed") is True),
        ("mastery_changed", result.get("mastery_changed") is True),
        ("final_status", result.get("final_status") == "completed"),
        ("idempotency_replay", result.get("idempotency_replay") is True),
        ("second_run_reset", result.get("second_run_reset") is True),
        ("mode", result.get("mode") in {"ai", "fallback"}),
        ("grading_mode", result.get("grading_mode") in {"ai", "fallback"}),
        (
            "required_mode",
            required_mode is None
            or (
                result.get("mode") == required_mode and result.get("grading_mode") == required_mode
            ),
        ),
    )
    failed = [name for name, passed in checks if not passed]
    if failed:
        raise RuntimeError(f"MCP smoke success criteria failed: {', '.join(failed)}")


def _payload(result, *, output_schema: dict | None = None) -> dict:
    if getattr(result, "is_error", False):
        structured = result.structured_content or {}
        error = structured.get("error") or {}
        raise RuntimeError(f"MCP tool failed with {error.get('code', 'unknown_error')}")
    structured = dict(result.structured_content or {})
    if output_schema is not None:
        try:
            validator_type = validator_for(output_schema)
            validator_type.check_schema(output_schema)
            validator_type(output_schema).validate(structured)
        except (SchemaError, ValidationError) as error:
            message = "MCP structuredContent violates the published outputSchema"
            raise RuntimeError(message) from error
    return structured


async def _run(url: str, *, trust_env: bool = True) -> dict[str, object]:
    client_key = f"public-smoke-{uuid4().hex}"
    async with (
        httpx2.AsyncClient(timeout=30.0, trust_env=trust_env) as http_client,
        streamable_http_client(url, http_client=http_client) as (read, write),
        ClientSession(read, write) as session,
    ):
        discovery = await session.discover()
        listed = await session.list_tools()
        names = {tool.name for tool in listed.tools}
        if names != EXPECTED_TOOLS:
            raise RuntimeError(f"Unexpected tool surface: {sorted(names)}")
        if any(not tool.output_schema for tool in listed.tools):
            raise RuntimeError("Every MCP tool must publish an output schema")
        output_schemas = {tool.name: tool.output_schema for tool in listed.tools}

        async def call(name: str, arguments: dict) -> dict:
            result = await session.call_tool(name, arguments)
            return _payload(result, output_schema=output_schemas[name])

        begun = await call(
            "refineq_begin_demo",
            {"client_run_key": client_key},
        )
        run_id = begun["run_id"]
        context = await call(
            "refineq_get_learning_context",
            {"run_id": run_id},
        )
        search = await call(
            "refineq_search_materials",
            {"run_id": run_id, "query": "function limit continuity", "limit": 3},
        )
        request_id = f"question-{uuid4().hex}"
        task_arguments = {
            "run_id": run_id,
            "request_id": request_id,
            "difficulty": 3,
        }
        task = await call(
            "refineq_get_practice_task",
            task_arguments,
        )
        task_replay = await call(
            "refineq_get_practice_task",
            task_arguments,
        )
        if task_replay != task:
            raise RuntimeError("Practice-task idempotency replay changed the result")
        answer = '{"limit":2,"point_value":9,"equal":false}'
        attempt_id = f"attempt-{uuid4().hex}"
        answer_arguments = {
            "run_id": run_id,
            "question_id": task["question_id"],
            "answer": answer,
            "attempt_id": attempt_id,
            "expected_state_version": task["state_version"],
        }
        graded = await call(
            "refineq_submit_answer",
            answer_arguments,
        )
        graded_replay = await call("refineq_submit_answer", answer_arguments)
        if graded_replay != graded:
            raise RuntimeError("Answer idempotency replay changed the result")
        if task.get("mode") not in {"ai", "fallback"}:
            raise RuntimeError("Practice mode is missing or invalid")
        if graded.get("grading_mode") not in {"ai", "fallback"}:
            raise RuntimeError("Grading mode is missing or invalid")
        search_citations = {str(item.get("citation_id")) for item in search["results"]}
        task_citations = {str(item) for item in task.get("citations", [])}
        grade_citations = {str(item) for item in graded.get("citations", [])}
        if not task_citations or not task_citations <= search_citations:
            raise RuntimeError("Practice citations are missing or not present in search results")
        if not grade_citations or not grade_citations <= task_citations:
            raise RuntimeError("Grade citations are missing or not present in the practice task")

        second = await call(
            "refineq_begin_demo",
            {"client_run_key": f"public-smoke-{uuid4().hex}"},
        )
        second_context = await call(
            "refineq_get_learning_context",
            {"run_id": second["run_id"]},
        )
        if (
            second_context["topics"][0]["mastery"] != 0.0
            or second_context.get("pending_question") is not None
            or second_context["latest_evidence"]
        ):
            raise RuntimeError("The second evaluation run did not restore the baseline")
        second_task = await call(
            "refineq_get_practice_task",
            {
                "run_id": second["run_id"],
                "request_id": f"question-{uuid4().hex}",
                "difficulty": 3,
            },
        )
        await call(
            "refineq_submit_answer",
            {
                "run_id": second["run_id"],
                "question_id": second_task["question_id"],
                "answer": answer,
                "attempt_id": f"attempt-{uuid4().hex}",
                "expected_state_version": second_task["state_version"],
            },
        )
    return {
        "protocol_versions": discovery.supported_versions,
        "tools": sorted(names),
        "account_email": begun["account"]["email"],
        "material_count": context["materials"]["indexed_count"],
        "search_results": len(search["results"]),
        "task_citations": len(task_citations),
        "grade_citations": len(grade_citations),
        "grounding": task["grounding"],
        "passed": graded["passed"],
        "mastery_changed": graded["mastery_effect"]["changed"],
        "final_status": graded["final_state"]["status"],
        "idempotency_replay": True,
        "second_run_reset": True,
        "mode": task["mode"],
        "grading_mode": graded["grading_mode"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=os.environ.get("REFINEQ_MCP_URL", ""))
    parser.add_argument(
        "--allow-http",
        action="store_true",
        help="Allow plain HTTP only for an isolated local smoke test.",
    )
    parser.add_argument(
        "--require-mode",
        choices=("ai", "fallback"),
        help="Fail unless question generation and grading both use this runtime mode.",
    )
    parser.add_argument(
        "--expected-account",
        default=os.environ.get("REFINEQ_MCP_ACCOUNT_EMAIL", ""),
        help="Fail unless MCP reports this server-bound account email.",
    )
    args = parser.parse_args()
    if not args.url or not args.expected_account:
        parser.error("REFINEQ_MCP_URL/--url and --expected-account are required")
    if not args.allow_http and not args.url.lower().startswith("https://"):
        parser.error("public MCP smoke tests require HTTPS")
    result = asyncio.run(_run(args.url, trust_env=not args.allow_http))
    _validate_report(
        result,
        required_mode=args.require_mode,
        expected_account=args.expected_account.strip().lower(),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
