# Deploy RefineQ

The production topology is Caddy in front of Next.js and FastAPI, backed by PostgreSQL 17 with the
pgvector extension. Only Caddy publishes host ports. Original uploads use the `refineq-data` volume
until an administrator switches object storage to an S3-compatible service.

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

Every integration has a server-side connection test. Endpoints must use HTTPS and the hostname must
appear in `REFINEQ_MODEL_ENDPOINT_ALLOWED_HOSTS`; browser clients never receive saved secrets.

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
```

Expected checks are `storage: ok` and `database: ok`. Then smoke-test registration, admin login,
integration tests, automatic learning-space routing, upload, question grading, and refresh recovery.

## Update

Take a PostgreSQL dump and an object-storage snapshot first, then:

```powershell
docker compose --env-file .env -f infra/compose.yml build --pull
docker compose --env-file .env -f infra/compose.yml up -d
docker compose --env-file .env -f infra/compose.yml ps
```

Keep the previous images and verified backups until the smoke test completes. Backup and migration
commands are documented in [operations.md](operations.md).
