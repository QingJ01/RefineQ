# RefineQ operations

Production state spans PostgreSQL and the object store selected in the administrator console. Stop
writes before backup or restore so both snapshots represent the same point in time.

## Health and model-call observability

The public reverse proxy sends `/health` directly to the API. Container health checks use the same
readiness semantics with short startup intervals; a successful response proves the process and its
required local dependencies are ready, not that every optional AI provider is reachable. Do not put
credentials, user data, or provider responses in this endpoint.

Question generation, workspace routing, and Agent replies release their database transactions before
waiting on model providers. A slow provider should therefore increase request latency without holding
an idle database transaction. Safe fallback logs contain only an event name, reason category, elapsed
time, and generation mode. Answers, material text, tokens, email addresses, owner identifiers, and
provider endpoints must not be added to those events.

## Administrator account

Local development:

```powershell
$env:REFINEQ_ADMIN_PASSWORD = "replace-with-a-strong-password"
refineq-admin --email qingj1314@163.com --display-name QingJ01
Remove-Item Env:REFINEQ_ADMIN_PASSWORD
```

Compose deployment:

```powershell
docker compose --env-file .env -f infra/compose.yml exec `
  -e REFINEQ_ADMIN_PASSWORD="replace-with-a-strong-password" `
  api refineq-admin --email qingj1314@163.com --display-name QingJ01
```

The command is idempotent. Re-running it promotes an existing account to `admin` and resets its
password; plaintext credentials are never saved by the command.

## Internal learning-loop metrics

An authenticated administrator can query the built-in journey aggregate without installing an
analytics SDK:

```text
GET /admin/metrics/learning?starts_at=2026-08-03T00:00:00Z&ends_at=2026-08-10T00:00:00Z
```

The interval is left-closed/right-open and cannot exceed 31 days. The response contains unique
active learners, unique learners shown at least one material-grounded grade, their completion rate,
and nearest-rank P50/P90 seconds for intent-to-grounded-grade and revisit-open-to-question. Empty
samples return `sample_size: 0` with null percentiles.

Journey events are stored in a separate owner/workspace event record, are idempotent, and are
bounded to the newest 500 events per workspace. They never advance the learning-domain version or
invalidate an in-flight question. Event-write failures are logged without changing the success
result of resolve, upload, question, grade, or snapshot operations. Treat these metrics as
product-flow and retention proxies only: they do not provide an external truth for mastery
calibration.
Event writes share the workspace lifecycle lock with deletion. A failed workspace deletion restores
the event snapshot alongside workspace, learning, and session state; a successful deletion cannot be
followed by a late request recreating an orphan event record.

## Demo data

```powershell
python scripts/seed_demo.py --data-root .\data-demo
```

The command prints the local demo credentials and learning-space identifier. Re-running it leaves existing
attempts, mastery, and plans unchanged.

## PostgreSQL production backup

Create a database dump while the database container is healthy:

```powershell
docker compose --env-file .env -f infra/compose.yml exec -T database `
  pg_dump -U refineq -d refineq -Fc > .\backups\refineq-postgres.dump
```

Also back up the `refineq-data` volume when local object storage is enabled. When S3-compatible
storage is enabled, use that provider's versioned backup or replication facility. Preserve the
Fernet key separately; without it, saved API and object-storage credentials cannot be decrypted.

## Managed backups in the administrator console

Open **System administration → Platform operations** to inspect user quotas, background indexing
jobs, recent audit activity, and backups managed under `REFINEQ_BACKUP_ROOT`. **Create backup** produces
a verified archive and records the action in the administrator audit log. The backup list exposes
only generated identifiers, timestamps, counts, and byte sizes; absolute server paths are never sent
to the browser.

The Compose deployment mounts `REFINEQ_BACKUP_ROOT=/backups` from the separate
`refineq-backups` volume. Keeping archives outside `/data` prevents recursive backups, and the
dedicated writable mount keeps managed backup creation working while the container root filesystem
is read-only. Copy both the PostgreSQL dump and this volume to storage with an independent failure
domain; a volume on the same host is durable across container replacement, not a disaster-recovery
copy by itself.

The restore action in the console is validation-only: it verifies the selected archive and records
the validation result, but does not replace a running system's state. For an actual restore, stop
writes and use the supported restore command below against an empty destination. This separation
prevents an accidental browser action from replacing live data.

Backup creation is compensated if its audit record cannot be written, so a failed request does not
leave an untracked archive. If an operation fails, retry from the localized error banner and inspect
server logs using the request time; the UI intentionally does not expose internal exception text.

## Legacy local backup

```powershell
python scripts/backup.py .\backups\refineq.zip --data-root .\data
```

The archive contains a manifest with a SHA-256 digest for every file. JSON is parsed before it is
accepted, and each SQLite database is copied through the SQLite backup API and integrity-checked.
Existing archive paths are never overwritten.

Store backups as secrets: they include accounts, encrypted model configuration, uploaded material,
and all learning history. A locally generated model-encryption key lives under the data root and is
therefore included too. Public deployments should supply `REFINEQ_MODEL_ENCRYPTION_KEY` from a
separate secret store and back up that secret independently.

Keep the encryption key stable during restore and upgrade. Replacing it does not corrupt learning
data, but saved model credentials can no longer be decrypted and must be entered again.

## Legacy local restore

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

## Upgrade legacy project data

```powershell
python scripts/migrate_workspaces.py .\data .\backups\before-workspaces.zip
```

This command detects older `projects` records and converts them in place to personal learning
spaces. It performs a complete conflict preflight and creates a verified full-data backup before
changing the first record. Learning state and Agent sessions are relinked to `workspace_id`; the
old record is removed only after the replacement is durable. Re-running the command is a no-op.

Choose a new archive path outside the data root. If a workspace with the same ID but incompatible
content already exists, migration stops without creating a backup or modifying data.

## Import the pre-PostgreSQL layout

Run a report first, then repeat without `--dry-run`:

```powershell
refineq-migrate-postgres --data-root .\data --dry-run
refineq-migrate-postgres --data-root .\data
```

The importer copies `auth.json`, owner-scoped JSON records, and each owner's legacy
`knowledge/search.sqlite3` into the configured SQL database. It is idempotent and never deletes or
rewrites source files. Existing SQL rows win, so a rerun cannot replace newer production state.

Personal model credentials are not silently promoted to a platform-wide secret. If one legacy
account's configuration should become the shared chat integration, select it explicitly in both
the report and import runs:

```powershell
refineq-migrate-postgres --data-root .\data --platform-owner-email owner@example.com --dry-run
refineq-migrate-postgres --data-root .\data --platform-owner-email owner@example.com
```

Imported chunks intentionally enter PostgreSQL without fabricated vectors. After configuring and
enabling the embedding integration, RefineQ schedules a bounded background backfill. Check the API
logs for `Embedding batch failed` warnings; these messages include only the exception type and never
provider credentials. Re-save the embedding configuration to retry missing vectors after correcting
the provider or network issue. Lexical retrieval remains available throughout the backfill.

## Integration recovery

Losing or replacing `REFINEQ_MODEL_ENCRYPTION_KEY` makes saved integration secrets unreadable. The
API fails closed in this state and does not silently redirect S3 uploads to the local volume. Restore
the original key from the secret store or intentionally re-enter all integration credentials.

If an endpoint is rejected as non-public, confirm the hostname is in the appropriate server
allowlist. Enable “Allow private network” only for an operator-controlled private service such as
MinIO; do not use it to bypass a misspelled or unexpected public provider address.
