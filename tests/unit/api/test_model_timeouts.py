from pathlib import Path

from refineq.api import app as app_module
from refineq.config import Settings


def test_structured_model_operations_use_bounded_no_retry_policies(
    tmp_path: Path,
    monkeypatch,
) -> None:
    policies: list[tuple[float, int]] = []

    class CapturedTransport:
        def __init__(self, *, timeout: float, max_retries: int) -> None:
            policies.append((timeout, max_retries))

        def complete(self, **_):
            raise AssertionError("model transport should not run during app construction")

    monkeypatch.setattr(
        app_module,
        "OpenAICompatibleStructuredTransport",
        CapturedTransport,
    )

    app = app_module.create_app(Settings(data_root=tmp_path / "data", _env_file=None))
    try:
        assert policies
        assert all(8.0 <= timeout <= 20.0 for timeout, _ in policies)
        assert all(max_retries == 0 for _, max_retries in policies)
    finally:
        app.state.account_deletions.close()
        app.state.material_deletions.close()
        app.state.database.close()
