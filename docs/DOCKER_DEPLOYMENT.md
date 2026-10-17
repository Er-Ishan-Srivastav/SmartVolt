# Docker deployment with HTTPS

SmartVolt now has two Docker paths:

- `docker-compose.yml` is for local development and keeps the Vite dev server and direct localhost ports.
- `docker-compose.prod.yml` builds a static React frontend, runs the API as a non-root user, keeps PostgreSQL/API ports unpublished, and puts Caddy in front to obtain and renew TLS certificates automatically.

## Requirements

- A server with Docker Engine and the Docker Compose plugin.
- A domain you control, with its DNS `A` record pointing to the server. If the domain has an `AAAA` record, that IPv6 address must also point to this server.
- Inbound TCP ports 80 and 443 open in the host firewall and cloud firewall. UDP 443 is optional but enables HTTP/3.
- SmartVolt remains a student simulation, not a certified utility/payment platform. Before allowing untrusted public users, review `SECURITY.md`, enable abuse protection/rate limiting, test authorization and PostgreSQL concurrency, and configure backups/monitoring. HTTPS encrypts traffic but is not a substitute for application-level security.

## Configure secrets

From the repository root, copy the example file:

```bash
cp .env.production.example .env.production
```

Set `SMARTVOLT_DOMAIN` to the real domain. Generate different random values for `POSTGRES_PASSWORD` and `AUTH_SECRET`:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Run the command twice and paste each generated value into the matching variable. Set a unique `ADMIN_PASSWORD`; do not keep demo credentials. Do not commit `.env.production`.

## Start and inspect

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml config
docker compose --env-file .env.production -f docker-compose.prod.yml up --build -d
docker compose --env-file .env.production -f docker-compose.prod.yml ps
docker compose --env-file .env.production -f docker-compose.prod.yml logs -f caddy api
```

When DNS points to the server and ports 80/443 are reachable, Caddy obtains and renews the certificate automatically. Open `https://YOUR_DOMAIN`; API docs are at `https://YOUR_DOMAIN/docs`.

The production Compose file runs Alembic migrations when the API container starts. The database and Caddy certificate state are stored in named Docker volumes.

### Bootstrap the initial administrator safely

On a new production database, create the first admin without running the development demo seed (which creates residents with a shared demo password):

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml exec api python -m app.db.bootstrap_admin
```

The command creates the configured administrator only if the username is unused; it does not reset an existing account password and does not create demo residents. In `ENVIRONMENT=production`, it refuses to run with the demo password or a short/default application secret. Keep `.env.production` private. Create resident accounts later through the Admin Console.

### Optional synthetic telemetry

The synthetic-consumption worker is deliberately excluded from the default production startup. It can deduct balances, so enable it only when that behavior is intended:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml --profile simulator up -d simulator
```

Leave the simulator disabled for a static demonstration, or use a clearly labeled test environment with test balances. The CO₂ factor and illustrative tree-year conversion are configurable via `GRID_CO2_FACTOR_KG_PER_KWH` and `TREE_CO2_ABSORPTION_KG_PER_YEAR`. Stop the deployment with:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml down
```

Do not add `-v` unless you intentionally want to delete the persistent database and certificate volumes. Before upgrading a database schema, back up the PostgreSQL volume/data first.

## Return to local development

The existing local developer flow remains unchanged:

```bash
docker compose up --build -d
docker compose exec api python -m app.db.seed
```

It serves HTTP on localhost and uses development-only settings. Do not expose those development ports directly to the internet.
