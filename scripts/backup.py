"""Create a verified RefineQ runtime backup."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from refineq.config import Settings
from refineq.operations.backup import create_backup


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, nargs="?")
    parser.add_argument("--data-root", type=Path, help="Override REFINEQ_DATA_ROOT")
    arguments = parser.parse_args()
    root = arguments.data_root or Settings().data_root
    archive = arguments.archive or Path("backups") / (
        f"refineq-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.zip"
    )
    result = create_backup(root, archive)
    print(f"Backup verified: {result.archive} ({result.file_count} files)")


if __name__ == "__main__":
    main()

