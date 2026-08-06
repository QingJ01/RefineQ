"""Move a RefineQ data root through a mandatory verified backup."""

from __future__ import annotations

import argparse
from pathlib import Path

from refineq.operations.migrate import migrate_data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("backup", type=Path)
    arguments = parser.parse_args()
    result = migrate_data(arguments.source, arguments.destination, arguments.backup)
    print(f"Migration backup: {result.backup.archive}")
    print(f"Migration destination: {result.restore.destination}")


if __name__ == "__main__":
    main()

