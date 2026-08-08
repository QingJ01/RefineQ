"""Create an idempotent local demo learner."""

from __future__ import annotations

import argparse
from pathlib import Path

from refineq.config import Settings
from refineq.database.engine import Database
from refineq.operations.demo import seed_demo


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, help="Override REFINEQ_DATA_ROOT")
    arguments = parser.parse_args()
    settings = (
        Settings(data_root=arguments.data_root)
        if arguments.data_root is not None
        else Settings()
    )
    if settings.demo_password is None:
        raise SystemExit("REFINEQ_DEMO_PASSWORD is required to seed the demo learner")

    database = Database(settings.resolved_database_url)
    database.initialize()
    try:
        result = seed_demo(
            database,
            settings.data_root,
            email=settings.demo_email,
            password=settings.demo_password.get_secret_value(),
        )
    finally:
        database.close()
    print(f"Demo ready: {result.email}")
    print(f"Learning space: {result.workspace_id}")


if __name__ == "__main__":
    main()
