# SmartVolt clean restart — start here

This archive has the project files directly at its ZIP root, plus a separate local-test Nginx configuration and Compose override. It does not replace or edit the production Nginx/Caddy configuration.

## Important

- Keep your original `D:\SmartVolt` folder. It may contain your Git history and local work.
- Replace only your clean extraction folder (`D:\SmartVolt-clean`) if that is the folder you want to reset.
- Never run `docker compose down -v` during this workflow; `-v` deletes persistent volumes.
- Run every command below from Git Bash at `D:/SmartVolt-clean`, where `docker-compose.prod.yml` and `.env.production.example` are visible.
- The local-test Compose override exposes the frontend only on `127.0.0.1:8080` and proxies `/api/` to the API. It does not publish PostgreSQL or FastAPI to Windows.
- `SMARTVOLT_DOMAIN=localhost` is for this local test only. Set a real DNS name before running the AWS/HTTPS deployment.

## 1. Confirm the project root

```bash
cd /d/SmartVolt-clean
pwd
ls docker-compose.prod.yml docker-compose.localtest.yml frontend/nginx.localtest.conf .env.production.example
```

All four paths should be listed. If not, stop and correct the extraction directory before continuing.

## 2. Create a fresh local test environment

```bash
cp .env.production.example .env.production
python -c "import secrets; print(secrets.token_hex(32))"
python -c "import secrets; print(secrets.token_hex(32))"
python -c "import secrets; print(secrets.token_urlsafe(24))"
notepad .env.production
```

In `.env.production`, replace `POSTGRES_PASSWORD` with the first generated value; `AUTH_SECRET` with the second; and `ADMIN_PASSWORD` with the third. Set `SMARTVOLT_DOMAIN=localhost` and choose an `ADMIN_USERNAME`. Keep these generated values private. Do not put quotes around the values and do not paste secrets into chat or commit `.env.production`.

## 3. Validate and build (no services are started yet)

```bash
docker version
docker compose version
docker compose -p smartvolt-cleanstart --env-file .env.production -f docker-compose.prod.yml -f docker-compose.localtest.yml config --quiet
docker compose -p smartvolt-cleanstart --env-file .env.production -f docker-compose.prod.yml -f docker-compose.localtest.yml build
```

Proceed only if `config --quiet` exits successfully and both `smartvolt-prod-api` and `smartvolt-prod-frontend` finish building.

## 4. Start the isolated local production test

```bash
docker compose -p smartvolt-cleanstart --env-file .env.production -f docker-compose.prod.yml -f docker-compose.localtest.yml up -d db api frontend
docker compose -p smartvolt-cleanstart --env-file .env.production -f docker-compose.prod.yml -f docker-compose.localtest.yml ps
```

Wait until `db`, `api`, and `frontend` report healthy. Do not start `caddy` for the local test and do not enable the simulator.

## 5. Create the admin (new database only)

```bash
docker compose -p smartvolt-cleanstart --env-file .env.production -f docker-compose.prod.yml -f docker-compose.localtest.yml exec api python -m app.db.bootstrap_admin
```

Then check API health:

```bash
docker compose -p smartvolt-cleanstart --env-file .env.production -f docker-compose.prod.yml -f docker-compose.localtest.yml exec -T api python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=5).read().decode())"
```

Expected health output includes `"status":"ok"`.

## 6. Test login in the browser

Open `http://localhost:8080`. Log in using `ADMIN_USERNAME` and `ADMIN_PASSWORD` from `.env.production`. Check the admin dashboard and several data-backed pages. The local-test override is what routes login/API calls correctly; no manual Nginx file creation or bind-mount command is needed.

If a stage fails, stop there and share only the failing command and output. Do not keep running later stages after an earlier stage fails. Never share `.env.production`, passwords, tokens, or AUTH_SECRET.

## 7. Stop the local test without deleting data

```bash
docker compose -p smartvolt-cleanstart --env-file .env.production -f docker-compose.prod.yml -f docker-compose.localtest.yml down
```

This stops/removes the test containers and network but preserves its named database volume. Do not append `-v` unless you intentionally want to delete that volume.

## AWS deployment is a separate later step

For AWS, do not use `SMARTVOLT_DOMAIN=localhost`. First arrange DNS for a domain/subdomain pointing to the server, then set `SMARTVOLT_DOMAIN` to that real hostname, configure EC2 security-group rules for SSH from your current IP and HTTP/HTTPS, and start production with `docker-compose.prod.yml` only. Keep ports 5432 and 8000 private. The simulator stays off by default.
