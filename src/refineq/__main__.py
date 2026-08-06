"""Run the RefineQ API with its typed runtime configuration."""

from __future__ import annotations

import uvicorn

from refineq.config import Settings


def main() -> None:
    settings = Settings()
    uvicorn.run(
        "refineq.api.app:app",
        host=settings.host,
        port=settings.port,
        proxy_headers=True,
        forwarded_allow_ips=settings.forwarded_allow_ips,
    )


if __name__ == "__main__":
    main()
