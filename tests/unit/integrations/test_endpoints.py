"""Outbound integration endpoint policy tests."""

from __future__ import annotations

import socket

import pytest

from refineq.integrations.endpoints import EndpointSecurityError, assert_safe_endpoint


def _resolver_for(*addresses: str):
    def resolve(host: str, port: int, *, type: int):
        del host, port
        return [
            (socket.AF_INET6 if ":" in address else socket.AF_INET, type, 6, "", (address, 443))
            for address in addresses
        ]

    return resolve


@pytest.mark.parametrize(
    "url",
    [
        "https://localhost/v1",
        "https://service.localhost/v1",
        "https://127.0.0.1/v1",
        "https://[::1]/v1",
    ],
)
def test_loopback_endpoints_are_rejected_without_resolution(url: str) -> None:
    with pytest.raises(EndpointSecurityError, match="non-public"):
        assert_safe_endpoint(url, resolver=lambda *_args, **_kwargs: [])


def test_hostname_resolving_to_private_address_is_rejected() -> None:
    with pytest.raises(EndpointSecurityError, match="non-public"):
        assert_safe_endpoint(
            "https://provider.example/v1",
            resolver=_resolver_for("10.20.30.40"),
        )


def test_any_private_address_rejects_a_mixed_dns_answer() -> None:
    with pytest.raises(EndpointSecurityError, match="non-public"):
        assert_safe_endpoint(
            "https://provider.example/v1",
            resolver=_resolver_for("203.0.113.10", "192.168.1.20"),
        )


def test_explicit_private_network_opt_in_allows_private_service_dns() -> None:
    assert_safe_endpoint(
        "https://minio.internal/v1",
        allow_private_network=True,
        resolver=_resolver_for("10.20.30.40"),
    )


def test_allowlisted_provider_can_use_a_transparent_proxy_fake_dns_pair() -> None:
    assert_safe_endpoint(
        "https://api.openai.com/v1",
        allow_transparent_proxy=True,
        resolver=_resolver_for("198.18.0.141", "fdfe:dcba:9876::6a"),
    )


def test_dns_resolution_failure_is_closed() -> None:
    def failing_resolver(*_args, **_kwargs):
        raise socket.gaierror("not found")

    with pytest.raises(EndpointSecurityError, match="could not be resolved"):
        assert_safe_endpoint("https://missing.example/v1", resolver=failing_resolver)
