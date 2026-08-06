# RefineQ operations

All commands operate on the directory selected by `REFINEQ_DATA_ROOT`. Stop writes before a
production backup or restore so the application and operator have a clear maintenance boundary.

## Demo data

```powershell
python scripts/seed_demo.py --data-root .\data-demo
```

The command prints the local demo credentials and project identifier. Re-running it leaves existing
attempts, mastery, and plans unchanged.

## Backup

```powershell
python scripts/backup.py .\backups\refineq.zip --data-root .\data
```

The archive contains a manifest with a SHA-256 digest for every file. JSON is parsed before it is
accepted, and each SQLite database is copied through the SQLite backup API and integrity-checked.
Existing archive paths are never overwritten.

Store backups as secrets: they include accounts, model configuration, uploaded material, and all
learning history.

## Restore

```powershell
python scripts/restore.py .\backups\refineq.zip .\restored-data
```

Restore rejects unsafe archive paths, duplicate entries, altered checksums, malformed JSON, damaged
SQLite files, and non-empty destinations. It validates the complete staged tree before atomically
installing the destination.

## Move a data root

```powershell
python scripts/migrate_data.py .\data .\data-new .\backups\before-migration.zip
```

Migration is a backup followed by a verified restore. No destination file is written until the
source backup has completed, and a non-empty destination is rejected.

