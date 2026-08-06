"""Migrate legacy learning projects to implicit workspaces."""

from __future__ import annotations

import argparse
from pathlib import Path

from refineq.operations.workspace_migration import migrate_projects_to_workspaces


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Back up RefineQ data and migrate legacy projects to learning workspaces."
    )
    parser.add_argument("data_root", type=Path, help="RefineQ runtime data directory")
    parser.add_argument("backup_archive", type=Path, help="New backup zip path")
    args = parser.parse_args()

    result = migrate_projects_to_workspaces(args.data_root, args.backup_archive)
    if result.backup is None:
        print("No legacy projects found; no files changed.")
        return 0
    print(f"Migrated {result.migrated_count} learning space(s). Backup: {result.backup.archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
