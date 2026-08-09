import logging
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import event

from refineq.agent.settings import ModelSettings
from refineq.api.app import create_app
from refineq.config import Settings
from refineq.operations.admin import ensure_admin
from refineq.workspaces.models import WorkspaceRoutingDecision
from refineq.workspaces.service import WorkspaceResolveRequest


class HomeTransport:
    def __init__(self) -> None:
        self.calls = []

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        name = kwargs["response_model"].__name__
        if name == "WorkspaceRoutingDecision":
            return kwargs["response_model"].model_validate(
                {
                    "action": "created",
                    "workspace_id": None,
                    "title": "高数期末",
                    "subject": "mathematics",
                    "topics": ["极限"],
                    "keywords": ["高数", "极限"],
                    "confidence": 0.95,
                    "reason": "新的长期目标",
                }
            )
        if name == "HomeAnswerDraft":
            return kwargs["response_model"].model_validate(
                {
                    "content": "边际效用是多消费一单位商品带来的额外效用。",
                    "basis": "general_knowledge",
                    "convertible_goal": "理解边际效用及常见例子",
                }
            )
        return kwargs["response_model"].model_validate(
            {
                "kind": "direct_answer",
                "workspace_id": None,
                "reason": "一次性概念解释",
                "confidence": 0.9,
            }
        )


class TimeoutAnswerTransport(HomeTransport):
    def complete(self, **kwargs):
        if kwargs["response_model"].__name__ == "HomeAnswerDraft":
            raise TimeoutError("answer timed out")
        return super().complete(**kwargs)


def app_with_model(tmp_path: Path, transport: HomeTransport | None = None):
    transport = transport or HomeTransport()
    app = create_app(
        Settings(data_root=tmp_path / "data", _env_file=None),
        learning_model_transport=transport,
        home_classifier_transport=transport,
        home_answer_transport=transport,
    )
    admin = ensure_admin(
        app.state.identity,
        email="admin@example.com",
        password="correct-horse-battery-staple",
        display_name="Admin",
    ).user
    app.state.model_settings.save(
        admin.id,
        ModelSettings(
            base_url="https://api.openai.com/v1",
            model="test",
            api_key="secret",
        ),
    )
    return app, transport


def register(client: TestClient, email: str = "learner@example.com") -> dict:
    response = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "correct-horse-battery-staple",
            "display_name": "Learner",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_direct_answer_does_not_mutate_learning_domains(tmp_path: Path) -> None:
    app, transport = app_with_model(tmp_path)
    with TestClient(app) as client:
        auth = register(client)
        headers = {"Authorization": f"Bearer {auth['access_token']}"}
        owner = auth["user"]["id"]
        before = {
            collection: app.state.store.list(owner, collection)
            for collection in ("workspaces", "learning", "sessions", "journey_events")
        }
        response = client.post(
            "/home/dispatch",
            headers=headers,
            json={"request_id": "direct-1", "text": "解释一下边际效用是什么"},
        )
        after = {collection: app.state.store.list(owner, collection) for collection in before}
    assert response.status_code == 200, response.json()
    assert response.json()["kind"] == "direct_answer"
    assert before == after
    assert len(app.state.home_events.list(owner)) == 1
    answer_call = next(
        call for call in transport.calls if call["response_model"].__name__ == "HomeAnswerDraft"
    )
    assert "workspaces" not in str(answer_call["messages"])


def test_answer_timeout_is_retryable_and_records_only_an_error_code(tmp_path: Path) -> None:
    app, _ = app_with_model(tmp_path, TimeoutAnswerTransport())
    with TestClient(app) as client:
        auth = register(client)
        owner = auth["user"]["id"]
        response = client.post(
            "/home/dispatch",
            headers={"Authorization": f"Bearer {auth['access_token']}"},
            json={"request_id": "answer-timeout", "text": "解释一下边际效用是什么"},
        )
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "home_model_unavailable"
    assert app.state.workspace_service.list(owner) == []
    events = app.state.home_events.list(owner)
    assert len(events) == 1
    assert events[0].error_code == "home_model_unavailable"


def test_event_storage_failure_does_not_fail_or_log_request_content(
    tmp_path: Path,
    monkeypatch,
    caplog,
) -> None:
    app, _ = app_with_model(tmp_path)

    def fail_event(*args, **kwargs):
        del args, kwargs
        raise RuntimeError("storage offline")

    monkeypatch.setattr(app.state.home_events, "record", fail_event)
    secret_text = "解释边际效用 secret-marker"
    with caplog.at_level(logging.WARNING), TestClient(app) as client:
        auth = register(client)
        response = client.post(
            "/home/dispatch",
            headers={"Authorization": f"Bearer {auth['access_token']}"},
            json={"request_id": "event-failure", "text": secret_text},
        )
    assert response.status_code == 200
    assert secret_text not in caplog.text
    assert "home_dispatch_event_write_failed" in caplog.text


def test_strong_signal_creates_and_routes_without_preview(tmp_path: Path) -> None:
    app, _ = app_with_model(tmp_path)
    with TestClient(app) as client:
        auth = register(client)
        headers = {"Authorization": f"Bearer {auth['access_token']}"}
        response = client.post(
            "/home/dispatch",
            headers=headers,
            json={
                "request_id": "strong-1",
                "text": "我要准备9月1日的高数考试，每天45分钟",
                "timezone_offset_minutes": 480,
            },
        )
        workspaces = client.get("/workspaces", headers=headers).json()
    assert response.status_code == 200, response.json()
    assert response.json()["kind"] == "open_workspace"
    assert response.json()["workspace_target"]["auto_navigate"] is True
    assert len(workspaces) == 1


def test_duplicate_named_spaces_return_real_choices_and_honor_the_selection(
    tmp_path: Path,
) -> None:
    app, _ = app_with_model(tmp_path)
    with TestClient(app) as client:
        auth = register(client)
        owner = auth["user"]["id"]
        headers = {"Authorization": f"Bearer {auth['access_token']}"}
        created_ids = []
        for topic in ("极限", "导数"):
            request = WorkspaceResolveRequest(
                intent=f"准备{topic}考试，每天45分钟",
                daily_minutes=45,
            )
            preview = app.state.workspace_service.preview_resolution(
                owner,
                request,
                use_model=False,
            )
            forced = preview.model_copy(
                update={
                    "decision": WorkspaceRoutingDecision(
                        action="created",
                        title="高数期末",
                        subject="mathematics",
                        topics=[topic],
                        keywords=[topic],
                        confidence=1,
                        reason="test fixture",
                    )
                }
            )
            created_ids.append(
                app.state.workspace_service.commit_resolution(owner, forced).workspace.id
            )
        initial = client.post(
            "/home/dispatch",
            headers=headers,
            json={"request_id": "duplicate-1", "text": "打开高数期末"},
        )
        clarification = initial.json()["clarification"]
        selected = client.post(
            "/home/dispatch",
            headers=headers,
            json={
                "request_id": "duplicate-2",
                "text": "打开高数期末",
                "clarification": {
                    "continuation_token": clarification["continuation_token"],
                    "option_id": f"workspace:{created_ids[1]}",
                },
            },
        )
        action_choice = client.post(
            "/home/dispatch",
            headers=headers,
            json={"request_id": "duplicate-action-1", "text": "把复习移到周六"},
        )
        action_clarification = action_choice.json()["clarification"]
        action = client.post(
            "/home/dispatch",
            headers=headers,
            json={
                "request_id": "duplicate-action-2",
                "text": "把复习移到周六",
                "clarification": {
                    "continuation_token": action_clarification["continuation_token"],
                    "option_id": f"action_workspace:{created_ids[1]}",
                },
            },
        )
    assert initial.status_code == 200
    assert initial.json()["kind"] == "clarify"
    assert {item["id"] for item in clarification["options"]} == {
        f"workspace:{item}" for item in created_ids
    }
    assert selected.status_code == 200
    assert selected.json()["workspace_target"]["workspace_id"] == created_ids[1]
    assert selected.json()["workspace_target"]["auto_navigate"] is True
    assert action_choice.status_code == 200
    assert action_choice.json()["kind"] == "clarify"
    assert all(
        item["id"].startswith("action_workspace:") for item in action_clarification["options"]
    )
    assert action.status_code == 200
    assert action.json()["kind"] == "workspace_action"
    assert action.json()["action_proposal"]["workspace_id"] == created_ids[1]


def test_ambiguous_signal_requires_confirmation_and_is_idempotent(tmp_path: Path) -> None:
    app, _ = app_with_model(tmp_path)
    with TestClient(app) as client:
        auth = register(client)
        headers = {"Authorization": f"Bearer {auth['access_token']}"}
        proposed = client.post(
            "/home/dispatch",
            headers=headers,
            json={"request_id": "proposal-1", "text": "我想系统学习高数"},
        )
        proposal = proposed.json()["workspace_proposal"]
        assert client.get("/workspaces", headers=headers).json() == []
        revised_response = client.post(
            "/home/actions/revise",
            headers=headers,
            json={
                "request_id": "proposal-1",
                "confirmation_token": proposal["confirmation_token"],
                "original_proposal": proposal,
                "changes": {"title": "我的高数计划", "daily_minutes": 60},
            },
        )
        assert revised_response.status_code == 200, revised_response.json()
        proposal = revised_response.json()
        confirmation = {
            "request_id": "proposal-1",
            "confirmation_token": proposal["confirmation_token"],
            "proposal": proposal,
            "idempotency_key": proposal["idempotency_key"],
        }
        first = client.post("/home/actions/confirm", headers=headers, json=confirmation)
        replay = client.post("/home/actions/confirm", headers=headers, json=confirmation)
        workspaces = client.get("/workspaces", headers=headers).json()
    assert proposed.status_code == 200, proposed.json()
    assert proposed.json()["kind"] == "propose_workspace"
    assert first.status_code == 200, first.json()
    assert replay.status_code == 200, replay.json()
    assert replay.json()["replayed"] is True
    assert len(workspaces) == 1
    assert workspaces[0]["title"] == "我的高数计划"
    assert app.state.home_events.list(auth["user"]["id"])[0].proposal_confirmed is True


def test_confirmation_token_is_owner_bound(tmp_path: Path) -> None:
    app, _ = app_with_model(tmp_path)
    with TestClient(app) as client:
        first_auth = register(client, "first@example.com")
        second_auth = register(client, "second@example.com")
        first_headers = {"Authorization": f"Bearer {first_auth['access_token']}"}
        second_headers = {"Authorization": f"Bearer {second_auth['access_token']}"}
        proposed = client.post(
            "/home/dispatch",
            headers=first_headers,
            json={"request_id": "owner-bound", "text": "我想系统学习高数"},
        ).json()["workspace_proposal"]
        response = client.post(
            "/home/actions/confirm",
            headers=second_headers,
            json={
                "request_id": "owner-bound",
                "confirmation_token": proposed["confirmation_token"],
                "proposal": proposed,
                "idempotency_key": proposed["idempotency_key"],
            },
        )
    assert response.status_code == 422


def test_cancelling_a_proposal_records_outcome_without_creating_state(tmp_path: Path) -> None:
    app, _ = app_with_model(tmp_path)
    with TestClient(app) as client:
        auth = register(client)
        owner = auth["user"]["id"]
        headers = {"Authorization": f"Bearer {auth['access_token']}"}
        proposed = client.post(
            "/home/dispatch",
            headers=headers,
            json={"request_id": "cancel-proposal", "text": "我想系统学习高数"},
        )
        cancelled = client.post(
            "/home/actions/cancel",
            headers=headers,
            json={"request_id": "cancel-proposal"},
        )
        workspaces = client.get("/workspaces", headers=headers).json()
    assert proposed.status_code == 200
    assert cancelled.status_code == 204
    assert workspaces == []
    assert app.state.home_events.list(owner)[0].proposal_confirmed is False


def test_unconfigured_model_keeps_a_recoverable_learner_path(tmp_path: Path) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))
    with TestClient(app) as client:
        auth = register(client)
        response = client.post(
            "/home/dispatch",
            headers={"Authorization": f"Bearer {auth['access_token']}"},
            json={"request_id": "no-model", "text": "解释一下边际效用是什么"},
        )
    assert response.status_code == 200
    assert response.json()["kind"] == "out_of_scope"
    assert "学习空间" in response.json()["limitations"][0]
    recovery = response.json()["manual_recovery"]
    assert recovery is not None
    assert recovery["options"][0]["id"] == "create_workspace"


def test_unconfigured_model_routes_a_learner_to_an_existing_space(tmp_path: Path) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))
    with TestClient(app) as client:
        auth = register(client)
        headers = {"Authorization": f"Bearer {auth['access_token']}"}
        created = client.post(
            "/home/dispatch",
            headers=headers,
            json={
                "request_id": "no-model-create",
                "text": "我要准备9月1日高数考试，每天45分钟",
            },
        )
        response = client.post(
            "/home/dispatch",
            headers=headers,
            json={"request_id": "no-model-answer", "text": "解释一下边际效用是什么"},
        )
    assert created.status_code == 200
    assert response.status_code == 200
    assert response.json()["kind"] == "open_workspace"
    assert (
        response.json()["workspace_target"]["workspace_id"]
        == created.json()["workspace_target"]["workspace_id"]
    )


def test_unconfigured_model_gives_admin_a_configuration_action(tmp_path: Path) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))
    ensure_admin(
        app.state.identity,
        email="admin@example.com",
        password="correct-horse-battery-staple",
        display_name="Admin",
    )
    with TestClient(app) as client:
        auth = client.post(
            "/auth/login",
            json={
                "email": "admin@example.com",
                "password": "correct-horse-battery-staple",
            },
        ).json()
        response = client.post(
            "/home/dispatch",
            headers={"Authorization": f"Bearer {auth['access_token']}"},
            json={"request_id": "admin-no-model", "text": "解释一下边际效用是什么"},
        )
    assert response.status_code == 200
    assert response.json()["kind"] == "out_of_scope"
    assert response.json()["manual_recovery"]["options"][0]["id"] == "configure_model"


def test_out_of_scope_learning_claim_opens_manual_choice_but_not_high_risk(
    tmp_path: Path,
) -> None:
    app, _ = app_with_model(tmp_path)
    with TestClient(app) as client:
        auth = register(client)
        headers = {"Authorization": f"Bearer {auth['access_token']}"}
        initial = client.post(
            "/home/dispatch",
            headers=headers,
            json={"request_id": "scope-1", "text": "帮我发一封销售邮件"},
        )
        recovery = initial.json()["manual_recovery"]
        reclaimed = client.post(
            "/home/dispatch",
            headers=headers,
            json={
                "request_id": "scope-2",
                "text": "帮我发一封销售邮件",
                "clarification": {
                    "continuation_token": recovery["continuation_token"],
                    "option_id": "recover_learning",
                },
            },
        )
        risky = client.post(
            "/home/dispatch",
            headers=headers,
            json={"request_id": "scope-3", "text": "给我医疗建议"},
        )
        risky_recovery = risky.json()["manual_recovery"]
        blocked = client.post(
            "/home/dispatch",
            headers=headers,
            json={
                "request_id": "scope-4",
                "text": "给我医疗建议",
                "clarification": {
                    "continuation_token": risky_recovery["continuation_token"],
                    "option_id": "recover_learning",
                },
            },
        )
    assert initial.status_code == 200
    assert recovery["options"][0]["id"] == "recover_learning"
    assert reclaimed.status_code == 200
    assert reclaimed.json()["kind"] == "clarify"
    assert reclaimed.json()["clarification"]["options"][0]["id"] == "direct_answer"
    assert blocked.status_code == 200
    assert blocked.json()["kind"] == "out_of_scope"
    assert blocked.json()["manual_recovery"] is None


def test_dispatch_rejects_oversized_text_and_requires_auth(tmp_path: Path) -> None:
    app, _ = app_with_model(tmp_path)
    with TestClient(app) as client:
        unauthorized = client.post(
            "/home/dispatch", json={"request_id": "x", "text": "解释边际效用"}
        )
        auth = register(client)
        oversized = client.post(
            "/home/dispatch",
            headers={"Authorization": f"Bearer {auth['access_token']}"},
            json={"request_id": "x", "text": "x" * 12_001},
        )
    assert unauthorized.status_code == 401
    assert oversized.status_code == 422


def test_workspace_action_requires_preview_and_confirmation(tmp_path: Path) -> None:
    app, _ = app_with_model(tmp_path)
    with TestClient(app) as client:
        auth = register(client)
        headers = {"Authorization": f"Bearer {auth['access_token']}"}
        created = client.post(
            "/home/dispatch",
            headers=headers,
            json={
                "request_id": "action-space",
                "text": "我要准备9月1日的高数考试，每天45分钟",
            },
        ).json()
        workspace_id = created["workspace_target"]["workspace_id"]
        owner_id = auth["user"]["id"]
        version_before = app.state.learning.get(owner_id, workspace_id).version
        proposed = client.post(
            "/home/dispatch",
            headers=headers,
            json={
                "request_id": "move-session",
                "text": "把高数期末的复习移到周六",
                "timezone_offset_minutes": 480,
            },
        )
        action = proposed.json()["action_proposal"]
        assert app.state.learning.get(owner_id, workspace_id).version == version_before
        confirmed = client.post(
            "/home/actions/confirm",
            headers=headers,
            json={
                "request_id": "move-session",
                "confirmation_token": action["confirmation_token"],
                "proposal": action,
                "idempotency_key": action["idempotency_key"],
            },
        )
    assert proposed.status_code == 200, proposed.json()
    assert proposed.json()["kind"] == "workspace_action"
    assert confirmed.status_code == 200, confirmed.json()
    assert confirmed.json()["before_version"] == version_before
    assert confirmed.json()["after_version"] == version_before + 1


def test_eight_workspace_projection_uses_two_database_reads(tmp_path: Path) -> None:
    app, _ = app_with_model(tmp_path)
    with TestClient(app) as client:
        auth = register(client)
        headers = {"Authorization": f"Bearer {auth['access_token']}"}
        for index in range(8):
            response = client.post(
                "/home/dispatch",
                headers=headers,
                json={
                    "request_id": f"projection-{index}",
                    "text": f"我要准备9月{index + 10}日的 Python{index} 考试，每天30分钟",
                },
            )
            assert response.status_code == 200, response.json()
        workspaces = app.state.workspace_service.list(auth["user"]["id"])
        statements: list[str] = []

        def count_reads(*args):
            statements.append(str(args[2]))

        event.listen(app.state.database.engine, "before_cursor_execute", count_reads)
        try:
            summaries = app.state.home_dispatch.load_dispatch_summaries(
                auth["user"]["id"],
                workspaces,
                now=datetime.now(UTC),
                timezone_offset_minutes=480,
            )
        finally:
            event.remove(app.state.database.engine, "before_cursor_execute", count_reads)
    assert len(summaries) == 8
    assert len(statements) <= 2


def test_home_metrics_are_independent_from_learning_metrics(tmp_path: Path) -> None:
    app, _ = app_with_model(tmp_path)
    with TestClient(app) as client:
        learner = register(client)
        client.post(
            "/home/dispatch",
            headers={"Authorization": f"Bearer {learner['access_token']}"},
            json={"request_id": "metric-answer", "text": "解释一下边际效用是什么"},
        )
        admin_auth = client.post(
            "/auth/login",
            json={
                "email": "admin@example.com",
                "password": "correct-horse-battery-staple",
            },
        ).json()
        headers = {"Authorization": f"Bearer {admin_auth['access_token']}"}
        params = {
            "starts_at": "2026-08-08T00:00:00Z",
            "ends_at": "2026-08-11T00:00:00Z",
        }
        home = client.get("/admin/metrics/home-dispatch", headers=headers, params=params)
        learning = client.get("/admin/metrics/learning", headers=headers, params=params)
    assert home.status_code == 200, home.json()
    assert home.json()["total_dispatches"] == 1
    assert home.json()["result_kind_counts"]["direct_answer"] == 1
    assert home.json()["proposal_confirmed_count"] == 0
    assert home.json()["candidate_truncation_count"] == 0
    assert learning.status_code == 200, learning.json()
    assert learning.json()["active_learners"] == 0
