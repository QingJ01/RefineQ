"""Uvicorn entrypoint configuration tests."""

from __future__ import annotations

from refineq import __main__ as entrypoint


def test_entrypoint_passes_the_explicit_trusted_proxy_boundary(monkeypatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setenv("REFINEQ_FORWARDED_ALLOW_IPS", "10.0.0.0/8,127.0.0.1")
    monkeypatch.setattr(entrypoint.uvicorn, "run", lambda *args, **kwargs: captured.update(kwargs))

    entrypoint.main()

    assert captured["proxy_headers"] is True
    assert captured["forwarded_allow_ips"] == "10.0.0.0/8,127.0.0.1"
