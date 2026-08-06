# Deploy RefineQ

The supported production topology is Caddy in front of one Next.js container and one FastAPI
container. Only Caddy publishes host ports. API and web traffic stays on the Compose network, and
all mutable learner state is stored in the `refineq-data` volume.

## Requirements

- Docker Engine with Compose v2
- A host with ports 80 and 443 available
- A DNS record pointing your domain to that host when HTTPS is required

## Start locally

```powershell
Copy-Item .env.example .env
docker compose --env-file .env -f infra/compose.yml up -d --build
docker compose --env-file .env -f infra/compose.yml ps
```

Open `http://localhost`. The default `.env.example` uses an HTTP-only Caddy address (`:80`).

For any public or shared deployment, generate `REFINEQ_MODEL_ENCRYPTION_KEY` before starting the
stack. It must be a Fernet key and must remain the same across restarts and upgrades:

```powershell
python -c "import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
```

Put the result in the private `.env` file, never in source control. If the value is left empty,
RefineQ creates a local key under the data volume; that fallback is intended only for local
development. Changing or losing the key makes saved model credentials unreadable, in which case
each learner must save their model settings again.

`REFINEQ_MODEL_ENDPOINT_ALLOWED_HOSTS` is a comma-separated server-side allowlist. The default is
`api.openai.com`. Add a host only when the deployment operator explicitly trusts that HTTPS model
endpoint; learner-provided URLs cannot extend the allowlist.

The remaining values in `.env.example` set per-user material, workspace, project, Agent-session,
and request-rate boundaries. The extraction budget separately caps PDF pages, DOCX archive entry
count, expanded DOCX bytes and compression ratio, extracted characters, and wall-clock extraction
time. `REFINEQ_MATERIAL_MAX_REQUEST_BYTES` is enforced by both Caddy and the ASGI receive boundary
before multipart parsing. `REFINEQ_MATERIAL_UPLOAD_MAX_CONCURRENT_GLOBAL` and
`REFINEQ_MATERIAL_UPLOAD_MAX_CONCURRENT_PER_USER` reject excess uploads before their multipart
bodies are parsed, preventing queued requests from multiplying the memory budget. The matching
idle and total body timeout settings release those admission slots when a client sends a chunked
body too slowly; extraction time is budgeted separately. Tune these values for host capacity, but
keep finite limits in public deployments.

## Enable public HTTPS

Set these values in `.env`:

```dotenv
REFINEQ_DOMAIN=learn.example.com
REFINEQ_HTTP_PORT=80
REFINEQ_HTTPS_PORT=443
```

Caddy will request and renew certificates after DNS and firewall access are correct. Do not expose
ports 8000 or 3000; they are internal service ports.

The Compose profile sets `REFINEQ_FORWARDED_ALLOW_IPS=*` because the API is reachable only through
the private Compose network. This lets Uvicorn use Caddy's forwarded client address so rate limits
remain per client. If port 8000 is ever exposed, replace `*` with the exact trusted proxy IPs or
CIDR ranges before starting the API.

## Verify health

```powershell
docker compose --env-file .env -f infra/compose.yml ps
Invoke-RestMethod http://localhost/api/health/ready
```

The readiness endpoint performs a real write probe in the mounted data volume without revealing an
internal path.

## Back up the volume

Pause application writes, copy the volume to a temporary host directory, then use the verified
backup command described in [operations.md](operations.md). Backups contain account data, uploaded
materials, learning history, and encrypted model credentials. When the local-development key
fallback is used, the backup also contains that key. Backups must always be encrypted at rest.

Before any restore or volume migration, stop the stack and confirm the destination is empty. The
restore command refuses to merge or overwrite an existing runtime.

## Update

```powershell
docker compose --env-file .env -f infra/compose.yml build --pull
docker compose --env-file .env -f infra/compose.yml up -d
docker compose --env-file .env -f infra/compose.yml ps
```

Keep the previous images and a verified backup until registration, automatic learning-space
routing, upload, question grading, refresh recovery, and Agent navigation have all been
smoke-tested.
