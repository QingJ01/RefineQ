"""Copy legacy RefineQ files into PostgreSQL without deleting the originals."""

from __future__ import annotations

from refineq.operations.migration_cli import main

if __name__ == "__main__":
    main()
