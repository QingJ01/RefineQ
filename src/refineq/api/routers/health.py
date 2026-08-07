"""Process and storage health checks."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, status

from refineq.config import Settings

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
def live() -> dict[str, str]:
    """Report that the API process can serve requests."""

    return {"status": "ok"}


def _prove_writable(data_root: Path) -> None:
    data_root.mkdir(parents=True, exist_ok=True)
    descriptor, probe_name = tempfile.mkstemp(prefix=".refineq-ready-", dir=data_root)
    os.close(descriptor)
    Path(probe_name).unlink()


@router.get("/ready")
def ready(request: Request) -> dict[str, object]:
    """Report readiness only after storage and the primary database respond."""

    settings: Settings = request.app.state.settings
    try:
        _prove_writable(settings.data_root)
    except OSError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Storage is not writable",
        ) from error

    try:
        database_ready = request.app.state.database.ping()
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is not ready",
        ) from error
    if not database_ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is not ready",
        )

    return {"status": "ready", "checks": {"storage": "ok", "database": "ok"}}
