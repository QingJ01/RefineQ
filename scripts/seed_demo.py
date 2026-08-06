"""Create an idempotent local demo learner."""

from __future__ import annotations

import argparse
from pathlib import Path

from refineq.config import Settings
from refineq.operations.demo import seed_demo


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, help="Override REFINEQ_DATA_ROOT")
    arguments = parser.parse_args()
    root = arguments.data_root or Settings().data_root
    result = seed_demo(root)
    print(f"Demo ready: {result.email} / {result.password}")
    print(f"Project: {result.project_id}")


if __name__ == "__main__":
    main()

