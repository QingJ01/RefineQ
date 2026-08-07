"""Command-line legacy data importer for local and container deployments."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from refineq.config import Settings
from refineq.database.engine import Database
from refineq.operations.postgres_migration import LegacyDataMigrator


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, help="Legacy data directory")
    parser.add_argument("--database-url", help="postgresql+psycopg:// URL")
    parser.add_argument(
        "--platform-owner-email",
        help="Explicit legacy account whose personal model config becomes platform-wide",
    )
    parser.add_argument("--dry-run", action="store_true")
    arguments = parser.parse_args()

    settings = Settings(_env_file=".env")
    data_root = (arguments.data_root or settings.data_root).expanduser().resolve()
    database_url = arguments.database_url or settings.resolved_database_url
    database = Database(database_url)
    database.initialize()
    try:
        report = LegacyDataMigrator(
            data_root,
            database,
            platform_owner_email=arguments.platform_owner_email,
            integration_encryption_key=settings.model_encryption_key,
            allowed_model_hosts=settings.allowed_model_hosts,
        ).migrate(dry_run=arguments.dry_run)
    finally:
        database.close()
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
