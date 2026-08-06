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

## Enable public HTTPS

Set these values in `.env`:

```dotenv
REFINEQ_DOMAIN=learn.example.com
REFINEQ_HTTP_PORT=80
REFINEQ_HTTPS_PORT=443
```

Caddy will request and renew certificates after DNS and firewall access are correct. Do not expose
ports 8000 or 3000; they are internal service ports.

## Verify health

```powershell
docker compose --env-file .env -f infra/compose.yml ps
Invoke-RestMethod http://localhost/api/health/ready
```

The readiness endpoint performs a real write probe in the mounted data volume without revealing an
internal path.

## Back up the volume

Pause application writes, copy the volume to a temporary host directory, then use the verified
backup command described in [operations.md](operations.md). Backups contain credentials and model
keys and must be encrypted at rest.

Before any restore or volume migration, stop the stack and confirm the destination is empty. The
restore command refuses to merge or overwrite an existing runtime.

## Update

```powershell
docker compose --env-file .env -f infra/compose.yml build --pull
docker compose --env-file .env -f infra/compose.yml up -d
docker compose --env-file .env -f infra/compose.yml ps
```

Keep the previous images and a verified backup until registration, upload, planning, practice, and
Agent navigation have all been smoke-tested.
