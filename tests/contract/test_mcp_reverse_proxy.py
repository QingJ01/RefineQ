from pathlib import Path


def test_caddy_preserves_the_exact_mcp_path_and_streaming() -> None:
    caddy = Path("infra/Caddyfile").read_text(encoding="utf-8")
    block = caddy.split("handle /mcp {", 1)[1].split("\n    }", 1)[0]

    assert "handle_path /mcp" not in caddy
    assert "reverse_proxy api:8000" in block
    assert "flush_interval -1" in block
    assert "dial_timeout 5s" in block
    assert "response_header_timeout 25s" in block
    assert "max_size 131072" in block
    assert caddy.index("handle /mcp {") < caddy.index("handle_path /api/*")


def test_caddy_proxies_exact_api_prefixed_mcp_without_path_stripping() -> None:
    caddy = Path("infra/Caddyfile").read_text(encoding="utf-8")

    child_rejection = 'handle /api/mcp/* {\n        respond "Not Found" 404\n    }'
    api_block = caddy.split("handle /api/mcp {", 1)[1].split("\n    }", 1)[0]
    assert "reverse_proxy api:8000" in api_block
    assert "flush_interval -1" in api_block
    assert "max_size 131072" in api_block
    assert child_rejection in caddy
    assert caddy.index("handle /api/mcp {") < caddy.index("handle_path /api/*")
    assert caddy.index(child_rejection) < caddy.index("handle_path /api/*")


def test_compose_passes_only_namespaced_mcp_configuration() -> None:
    compose = Path("infra/compose.yml").read_text(encoding="utf-8")
    example = Path(".env.example").read_text(encoding="utf-8")
    for name in (
        "REFINEQ_MCP_ENABLED",
        "REFINEQ_MCP_INTERNAL_SECRET",
        "REFINEQ_MCP_ACCOUNT_EMAIL",
        "REFINEQ_MCP_ALLOWED_HOSTS",
        "REFINEQ_MCP_RUN_TTL_SECONDS",
        "REFINEQ_MCP_IDEMPOTENCY_TTL_SECONDS",
        "REFINEQ_MCP_READ_RATE_LIMIT",
        "REFINEQ_MCP_WRITE_RATE_LIMIT",
    ):
        assert name in compose
        assert f"{name}=" in example
