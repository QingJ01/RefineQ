from datetime import UTC, datetime, timedelta

from refineq.home.events import HomeDispatchEvent, HomeEventRepository, request_id_hash
from refineq.storage.json_store import AtomicJsonStore


def test_home_event_is_content_free_and_idempotent(tmp_path) -> None:
    repository = HomeEventRepository(AtomicJsonStore(tmp_path))
    event = HomeDispatchEvent(
        request_id_hash="a" * 32,
        result_kind="direct_answer",
        decided_by="hybrid",
        latency_bucket="lt_1s",
        latency_ms=20,
        candidate_count=2,
        occurred_at=datetime(2026, 8, 9, tzinfo=UTC),
    )
    repository.record("owner", event)
    repository.record("owner", event)
    raw = repository._store.list("owner", "home_dispatch_events")
    assert len(raw) == 1
    assert "text" not in raw[0].data
    assert "content" not in raw[0].data


def test_confirmation_updates_the_content_free_dispatch_event(tmp_path) -> None:
    repository = HomeEventRepository(AtomicJsonStore(tmp_path))
    request_id = "proposal-request"
    event = HomeDispatchEvent(
        request_id_hash=request_id_hash(request_id),
        result_kind="propose_workspace",
        decided_by="rule",
        latency_bucket="lt_1s",
        latency_ms=20,
        candidate_count=0,
        occurred_at=datetime(2026, 8, 9, tzinfo=UTC),
    )
    repository.record("owner", event)

    assert repository.mark_proposal_confirmed("owner", "different-id") is None
    updated = repository.mark_proposal_confirmed("owner", request_id)
    assert updated is not None
    assert updated.proposal_confirmed is True
    assert repository.list("owner")[0].proposal_confirmed is True
    cancelled = repository.mark_proposal_cancelled("owner", request_id)
    assert cancelled is not None
    assert cancelled.proposal_confirmed is False


def test_home_events_are_bounded_per_owner(tmp_path) -> None:
    repository = HomeEventRepository(AtomicJsonStore(tmp_path), max_events=2)
    observed_at = datetime(2026, 8, 9, tzinfo=UTC)
    for index in range(3):
        request_id = f"request-{index}"
        repository.record(
            "owner",
            HomeDispatchEvent(
                request_id_hash=request_id_hash(request_id),
                result_kind="direct_answer",
                decided_by="rule",
                latency_bucket="lt_1s",
                latency_ms=20,
                candidate_count=0,
                occurred_at=observed_at + timedelta(seconds=index),
            ),
        )

    assert {item.request_id_hash for item in repository.list("owner")} == {
        request_id_hash("request-1"),
        request_id_hash("request-2"),
    }
