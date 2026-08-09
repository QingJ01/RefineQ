from datetime import UTC, datetime

from refineq.home.events import HomeDispatchEvent, HomeEventRepository
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
