"""Command-line administrator bootstrap for local and container deployments."""

from __future__ import annotations

import argparse
import getpass
import os
from pathlib import Path

from refineq.config import Settings
from refineq.database.engine import Database
from refineq.identity.service import IdentityService
from refineq.operations.admin import ensure_admin


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", default="qingj1314@163.com")
    parser.add_argument("--display-name", default="QingJ01")
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--database-url")
    arguments = parser.parse_args()

    settings = Settings(
        data_root=arguments.data_root or Settings().data_root,
        _env_file=None if arguments.data_root else ".env",
    )
    database_url = arguments.database_url or settings.resolved_database_url
    password = os.environ.get("REFINEQ_ADMIN_PASSWORD") or getpass.getpass(
        "Administrator password: "
    )
    database = Database(database_url)
    database.initialize()
    try:
        result = ensure_admin(
            IdentityService(database),
            email=arguments.email,
            password=password,
            display_name=arguments.display_name,
        )
    finally:
        database.close()
    action = "created" if result.created else "updated"
    print(f"Administrator {action}: {result.user.email}")
