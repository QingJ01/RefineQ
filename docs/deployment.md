# Deploy RefineQ

The production topology is Caddy in front of Next.js and FastAPI, backed by PostgreSQL 17 with the
pgvector extension. Only Caddy publishes host ports. Original uploads use the `refineq-data` volume
until an administrator switches object storage to an S3-compatible service.

Compose pins Caddy to `172.30.0.2`, and the API accepts forwarded client addresses only from that
source. If the private network changes, update the Caddy address and
`REFINEQ_FORWARDED_ALLOW_IPS` together. Never set the latter to `*`: otherwise a client that reaches
the API can forge its apparent source address and bypass source-keyed controls.

## Requirements

- Docker Engine with Compose v2
- Ports 80 and 443 available on the host
- A DNS record pointing to the host when public HTTPS is required

## Prepare configuration

```powershell
Copy-Item .env.example .env
```

Before a shared or public deployment, edit `.env` and change:

- `REFINEQ_POSTGRES_PASSWORD`
- the matching password inside `REFINEQ_DATABASE_URL` (URL-encode special characters)
- `REFINEQ_MODEL_ENCRYPTION_KEY`
- `REFINEQ_DOMAIN`
- `REFINEQ_PUBLIC_SITE_URL` so password-reset links point to the public HTTPS origin
- `REFINEQ_OBJECT_STORAGE_ENDPOINT_ALLOWED_HOSTS` before enabling an S3-compatible service

Generate the Fernet integration-encryption key with:

```powershell
python -c "import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
```

Keep this key outside source control and reuse it across upgrades. Losing it makes the API keys
stored in the administrator console unreadable.

## Start

```powershell
docker compose --env-file .env -f infra/compose.yml up -d --build
docker compose --env-file .env -f infra/compose.yml ps
```

PostgreSQL is not published to the host. The API waits for `pg_isready`, creates the `vector`
extension and application schema, then exposes readiness only after both database and local storage
checks pass.

Open `http://localhost` when `REFINEQ_DOMAIN=:80`.

## Optional SMTP password recovery

Password recovery stays hidden and reset tokens are not created unless SMTP has both a host and
sender configured. Set these values in `.env` when recovery is required:

```dotenv
REFINEQ_PUBLIC_SITE_URL=https://learn.example.com
REFINEQ_PASSWORD_RESET_TTL_MINUTES=20
REFINEQ_SMTP_HOST=smtp.example.com
REFINEQ_SMTP_PORT=587
REFINEQ_SMTP_FROM_EMAIL=RefineQ <no-reply@example.com>
REFINEQ_SMTP_USERNAME=
REFINEQ_SMTP_PASSWORD=
REFINEQ_SMTP_STARTTLS=true
REFINEQ_SMTP_USE_SSL=false
```

Set username and password together when the relay requires authentication. For implicit TLS,
disable STARTTLS and enable `REFINEQ_SMTP_USE_SSL`. Keep
`REFINEQ_PASSWORD_RESET_EXPOSE_TOKEN=false` in every shared or public environment.

## Seed presentation-only data

Set `REFINEQ_DEMO_PASSWORD` in the runtime environment, then run the idempotent seed inside the API
container. The command uses the configured database and never prints the password:

```powershell
docker compose --env-file .env -f infra/compose.yml exec api refineq-demo
```

The seeded account and learning records are presentation fixtures, not user-research evidence.

## Create the first administrator

```powershell
docker compose --env-file .env -f infra/compose.yml exec `
  -e REFINEQ_ADMIN_PASSWORD="replace-with-a-strong-password" `
  api refineq-admin --email qingj1314@163.com --display-name QingJ01
```

Sign in with that account and open “系统管理”. Configure only the services needed by the demo:

1. Model inference for Agent chat, question generation, and grading.
2. Embeddings for pgvector semantic retrieval (lexical retrieval works without it).
3. OCR only for scanned PDFs (text PDFs/DOCX/TXT/Markdown parse locally).
4. S3-compatible storage only when the local volume is insufficient.

Every integration has a server-side connection test. Model endpoints must use HTTPS and their
hostnames must appear in `REFINEQ_MODEL_ENDPOINT_ALLOWED_HOSTS`. S3 endpoints use the separate
`REFINEQ_OBJECT_STORAGE_ENDPOINT_ALLOWED_HOSTS` allowlist. The API resolves endpoints again before
outbound calls and rejects loopback, link-local, private, and reserved addresses by default.

Embedding providers may return either 1024-dimensional vectors (for example `BAAI/bge-m3`) or
1536-dimensional vectors. RefineQ validates the provider's native dimension and zero-pads 1024
dimensions to the PostgreSQL `vector(1536)` storage width. Zero padding preserves cosine similarity
while allowing both model families to share the same pgvector schema. The provider request omits the
optional `dimensions` parameter because not every OpenAI-compatible endpoint accepts it.

Private MinIO or model gateways require both controls:

1. Add the exact hostname to the corresponding server environment allowlist.
2. Select “允许私网地址 / Allow private network” for that integration in the administrator console.

Do not enable the private-network switch for public providers. Browser clients never receive saved
secrets. Redirect following is disabled for model-provider HTTP clients.

OCR rendering is bounded independently of the upload byte limit. The defaults allow up to 50 OCR
pages, four consecutive scanned pages per provider request, 12 million pixels per page, 80 million
pixels per document, and 40 MiB of rendered PNG data. Tune the `REFINEQ_MATERIAL_OCR_*` variables
only after measuring worker memory. Text pages in mixed PDFs stay local; only textless pages are sent
to the configured vision model.

When the embedding integration is enabled or updated, the API schedules a bounded background
backfill for legacy chunks that do not have vectors. Re-saving the embedding configuration safely
retries a previously interrupted backfill.

## Enable public HTTPS

```dotenv
REFINEQ_DOMAIN=learn.example.com
REFINEQ_HTTP_PORT=80
REFINEQ_HTTPS_PORT=443
```

Caddy requests and renews certificates after DNS and firewall access are correct. Do not expose
ports 8000, 3000, or 5432.

## Verify

```powershell
docker compose --env-file .env -f infra/compose.yml ps
Invoke-RestMethod http://localhost/api/health/ready
Invoke-RestMethod http://localhost/health/ready
```

Expected checks are `storage: ok` and `database: ok`. Then smoke-test registration, admin login,
integration tests, automatic learning-space routing, upload, question grading, and refresh recovery.
The repository CI additionally starts PostgreSQL with pgvector and pg_trgm to verify indexed Chinese
lexical search, vector search, JSONB persistence, and cross-connection quota locking.

## Update

Take a PostgreSQL dump and an object-storage snapshot first, then:

```powershell
docker compose --env-file .env -f infra/compose.yml build --pull
docker compose --env-file .env -f infra/compose.yml up -d
docker compose --env-file .env -f infra/compose.yml ps
```

Keep the previous images and verified backups until the smoke test completes. Backup and migration
commands are documented in [operations.md](operations.md).

## Build a clean source bundle

Create submission archives from a committed revision so local `.env` files, runtime data, caches,
and untracked files cannot leak into the bundle. From the repository root:

```powershell
$commit = git rev-parse HEAD
git archive --format=zip --prefix="RefineQ-$commit/" `
  --output="RefineQ-$commit-source.zip" $commit
Get-FileHash "RefineQ-$commit-source.zip" -Algorithm SHA256
```

The archive contains `.env.example`, `infra/`, `scripts/`, deployment and operations documents,
locked dependencies, tests, backend source, and the web application. It intentionally excludes
the Git history and every untracked or ignored runtime artifact. Never add a populated `.env`,
database dump, upload volume, model key, MCP bearer secret, or administrator password to a source
bundle.
