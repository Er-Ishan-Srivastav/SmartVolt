# Load Lab quantity controls rollout

This release adds per-appliance quantities. Migration `0007_appliance_quantities` adds a `quantity` column defaulting to `1`; it is additive and does not delete existing active-appliance rows or any meter/consumption/recharge data.

## 1. Apply to local repositories

Back up/commit any local changes first. The supplied `SmartVolt-load-quantity.patch` is generated against the SmartVolt clean-restart source baseline.

For each repository (`D:\SmartVolt` and `D:\SmartVolt-clean`), in Git Bash:

```bash
cd /d/SmartVolt-clean  # change to /d/SmartVolt for the other repo

git status --short
git apply --check /c/Users/ishan/Downloads/SmartVolt-load-quantity.patch
```

Only if `git apply --check` succeeds:

```bash
git apply /c/Users/ishan/Downloads/SmartVolt-load-quantity.patch
```

If `git apply --check` fails, do not force it or use `--reject`; the two source trees differ. Keep the source tree intact and compare it with the supplied updated ZIP before deciding how to merge.

Validate each updated repository from its root:

```bash
python -m pytest -q
cd frontend
npm ci
npm run build
cd ..
```

For the local production-like stack in `D:\SmartVolt-clean`, rebuild and restart only the app services (leave the database volume intact):

```bash
docker compose -p smartvolt-cleanstart --env-file .env.production -f docker-compose.prod.yml -f docker-compose.localtest.yml build api frontend
docker compose -p smartvolt-cleanstart --env-file .env.production -f docker-compose.prod.yml -f docker-compose.localtest.yml up -d db api frontend
docker compose -p smartvolt-cleanstart --env-file .env.production -f docker-compose.prod.yml -f docker-compose.localtest.yml ps
```

The API startup runs Alembic migrations. Confirm `0007_appliance_quantities` with:

```bash
docker compose -p smartvolt-cleanstart --env-file .env.production -f docker-compose.prod.yml -f docker-compose.localtest.yml exec api alembic current
```

Open `http://localhost:8080`. Test setting an appliance count, applying a changed count, saving a template with several units, and reviewing the estimated kWh/cost. Don't run the simulation clock against any real test balance unless intended.

## 2. Deploy to the existing EC2 instance

Do not terminate/recreate EC2, remove Docker volumes, or use `docker compose down -v`.

From Windows Git Bash, upload the provided deployment source archive (use your current EC2 public IPv4 and key path):

```bash
scp -i "/c/Users/ishan/Downloads/smartvolt-prod-key.pem" /c/Users/ishan/Downloads/SmartVolt-load-quantity-deploy.tar.gz ubuntu@YOUR_CURRENT_EC2_PUBLIC_IP:/home/ubuntu/
```

Connect using SSH, then run on Ubuntu:

```bash
cd /opt/smartvolt
STAMP=$(date +%F-%H%M%S)
mkdir -p "$HOME/smartvolt-backups"
sudo docker compose -p smartvolt-prod --env-file .env.production -f docker-compose.prod.yml exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' > "$HOME/smartvolt-backups/pre-load-quantity-$STAMP.sql"
test -s "$HOME/smartvolt-backups/pre-load-quantity-$STAMP.sql" || { echo "Database backup failed; STOP"; exit 1; }
sudo tar -czf "$HOME/smartvolt-source-pre-load-quantity-$STAMP.tar.gz" --exclude='smartvolt/.env.production' -C /opt smartvolt
```

After the backup file is confirmed non-empty, extract the new code over the existing source directory. The deployment archive excludes `.env.production`, so your production secrets stay in place:

```bash
sudo tar -xzf "$HOME/smartvolt-load-quantity-deploy.tar.gz" -C /opt/smartvolt
sudo chown -R ubuntu:ubuntu /opt/smartvolt
chmod 600 /opt/smartvolt/.env.production
cd /opt/smartvolt
```

Tag the current app images as a rollback aid before rebuilding (if the tags exist):

```bash
sudo docker image tag smartvolt-prod-api:latest smartvolt-prod-api:pre-load-quantity
sudo docker image tag smartvolt-prod-frontend:latest smartvolt-prod-frontend:pre-load-quantity
```

Build and update only the API/frontend services. Do not stop PostgreSQL, remove volumes, or restart Caddy unnecessarily:

```bash
sudo docker compose -p smartvolt-prod --env-file .env.production -f docker-compose.prod.yml build api frontend
sudo docker compose -p smartvolt-prod --env-file .env.production -f docker-compose.prod.yml up -d api frontend
sudo docker compose -p smartvolt-prod --env-file .env.production -f docker-compose.prod.yml ps
sudo docker compose -p smartvolt-prod --env-file .env.production -f docker-compose.prod.yml exec api alembic current
curl -fsS https://smartvolt-demo.duckdns.org/api/v1/health
```

Expected Alembic head: `0007_appliance_quantities`. Expected public health response contains `"status":"ok"`. Inspect API logs if the migration or health check fails:

```bash
sudo docker compose -p smartvolt-prod --env-file .env.production -f docker-compose.prod.yml logs --tail=120 api frontend
```

The migration adds a non-null column with default `1`, so existing appliance records are treated as single units. The database volume is preserved. Existing custom scenarios without quantity metadata remain valid and are interpreted as one unit per appliance.

## 3. Production smoke test precautions

After local verification, open `https://smartvolt-demo.duckdns.org/overview` and confirm the quantity control appears. You can turn a device on, check its effective wattage, and turn it off again, but do not press **Run clock** on a room with a real wallet unless you intend to consume its balance. Avoid applying a current-day scenario to a production room during verification: current-day scenario runs debit the wallet. Historical-date scenario runs do not debit the wallet but do create historical telemetry, so prefer local testing for end-to-end billing checks.
