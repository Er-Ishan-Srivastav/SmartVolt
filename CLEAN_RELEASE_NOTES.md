# SmartVolt clean source bundle

This archive was prepared from the uploaded SmartVolt source snapshot. It contains source code, tests, Alembic migrations, package manifests/lockfiles, documentation, and development/production deployment configuration.

## Intentionally excluded

- `.git/`: Git history is local and should not be copied into a release archive.
- `.venv/`, `frontend/node_modules/`, Python/Node caches, `smartvolt.egg-info/`, and compiled frontend output: regenerate locally.
- `smartvolt.db` and any other SQLite/database files: preserve and back up separately; never ship a development database to production.
- Real `.env` files and other environment-specific secrets: templates `.env.example` and `.env.production.example` are included.
- The empty root `package-lock.json`: this project manages npm dependencies in `frontend/`, where `package.json` and `package-lock.json` are kept together.

## Use this archive

1. Extract to a new directory, e.g. `D:\SmartVolt-clean`. Do not overwrite your current working repository until you have reviewed and tested the clean copy.
2. Local backend: create a new virtual environment, install `pip install -e ".[dev]"`, copy `.env.example` to `.env`, then run `python -m alembic upgrade head`. Seed only for a disposable/demo database with `python -m app.db.seed`.
3. Frontend: run `npm ci` from `frontend/`, then `npm run build`.
4. For production, follow `docs/DOCKER_DEPLOYMENT.md`. Create `.env.production` from the example and replace every placeholder. Do not run the development seed against production; use `python -m app.db.bootstrap_admin` after migrations.
5. The autonomous simulator is opt-in because it debits simulated wallet balances. Do not enable it unless intended.

## Important

This is a clean source bundle, not a backup of the local SQLite database or Git history. Keep the original repository and database backup until the clean copy has passed validation.

## Load Lab quantity controls (2026-10-17)

- The appliance board now controls 1–100 running units per appliance; live wattage and simulated billing scale by quantity.
- Daily templates now have explicit unit count, minute-level start time, runtime, and estimated daily kWh/cost.
- Template blocks store `appliance_quantities`; legacy templates without the field keep their one-unit behavior.
- Alembic migration `0007_appliance_quantities` adds the live quantity column without deleting current appliance rows.
- API tests cover live wattage/billing by quantity and scenario validation.
