"""Restore a verified RefineQ backup into an empty data root."""

from __future__ import annotations

import argparse
from pathlib import Path

from refineq.operations.backup import restore_backup


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("destination", type=Path)
    arguments = parser.parse_args()
    result = restore_backup(arguments.archive, arguments.destination)
    print(f"Restore verified: {result.destination} ({result.file_count} files)")


if __name__ == "__main__":
    main()
