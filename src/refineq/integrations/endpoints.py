"""Runtime policy for outbound integration endpoints."""

from __future__ import annotations

import socket
from collections.abc import Callable, Iterable
from ipaddress import IPv4Address, IPv6Address, ip_address, ip_network
from urllib.parse import urlsplit


class EndpointSecurityError(ValueError):
    """Raised when an outbound endpoint could reach an unapproved network."""


Address = IPv4Address | IPv6Address
Resolver = Callable[..., Iterable[tuple]]
_PROXY_FAKE_IPV4 = ip_network("198.18.0.0/15")
_PRIVATE_IPV6 = ip_network("fc00::/7")


def _allow_address(address: Address, *, allow_private_network: bool) -> bool:
    if address.is_unspecified or address.is_multicast or address.is_reserved:
        return False
    if allow_private_network:
        return True
    return address.is_global


def assert_safe_endpoint(
    url: str,
    *,
    allow_private_network: bool = False,
    allow_transparent_proxy: bool = False,
    resolver: Resolver = socket.getaddrinfo,
) -> None:
    """Resolve every current address and reject non-public destinations by default."""

    parsed = urlsplit(url)
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise EndpointSecurityError("integration endpoint must be an absolute HTTPS URL")
    host = parsed.hostname.lower().rstrip(".")
    if host == "localhost" or host.endswith(".localhost"):
        if not allow_private_network:
            raise EndpointSecurityError("integration endpoint resolved to a non-public address")
        return
    try:
        literal = ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        if not _allow_address(literal, allow_private_network=allow_private_network):
            raise EndpointSecurityError("integration endpoint resolved to a non-public address")
        return

    try:
        answers = list(
            resolver(
                host,
                parsed.port or 443,
                type=socket.SOCK_STREAM,
            )
        )
    except OSError as error:
        raise EndpointSecurityError(
            "integration endpoint hostname could not be resolved"
        ) from error
    if not answers:
        raise EndpointSecurityError("integration endpoint hostname could not be resolved")
    try:
        addresses = {ip_address(str(answer[4][0]).split("%", 1)[0]) for answer in answers}
    except (IndexError, TypeError, ValueError) as error:
        raise EndpointSecurityError(
            "integration endpoint returned an invalid DNS answer"
        ) from error
    unsafe = [
        address
        for address in addresses
        if not _allow_address(address, allow_private_network=allow_private_network)
    ]
    proxy_pair = (
        allow_transparent_proxy
        and any(
            isinstance(address, IPv4Address) and address in _PROXY_FAKE_IPV4
            for address in addresses
        )
        and all(
            (isinstance(address, IPv4Address) and address in _PROXY_FAKE_IPV4)
            or (isinstance(address, IPv6Address) and address in _PRIVATE_IPV6)
            for address in addresses
        )
    )
    if unsafe and not proxy_pair:
        raise EndpointSecurityError("integration endpoint resolved to a non-public address")
