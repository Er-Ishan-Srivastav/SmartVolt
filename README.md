# SmartVolt — Smart Prepaid Energy Meter Simulator

SmartVolt is a full-stack project foundation for simulating prepaid electricity meters in hostels and shared accommodation. It models rooms, tenants, meters, wallet recharges, consumption readings, a ledger, and support tickets without requiring physical IoT hardware.

> **Current milestone:** authenticated full-stack prepaid-meter simulation. The React workspace includes Overview, Usage history, Transactions, Room details, Admin Console, Load Lab, Settings, and Help & support; backend-enforced roles and revocable eight-hour sessions; permanent room/tenant/meter/recharge/ticket identifiers; safe room archival; meter-targeted simulated recharges; threaded room-wide/private support tickets; hourly/daily energy analytics; CSV usage exports; printable monthly statements; configurable grid-emissions estimates; and an opt-in autonomous simulation worker. Payment-provider integration, individual roommate consumption allocation, dynamic time-of-use tariffs, and production identity hardening remain follow-on work. Recharge is simulated and does not move real money.

## Stack

- **API:** Python 3.11+, FastAPI, Pydantic
- **Data:** SQLAlchemy 2.x, Alembic migrations, PostgreSQL (recommended); SQLite for quick local development and tests
- **Quality:** pytest, HTTPX, Ruff, GitHub Actions
- **Frontend:** React 18, TypeScript, Vite, Recharts, Lucide
- **Run options:** local Python/Node or Docker Compose

## Quick start — Windows PowerShell

```powershell
# 1. Extract the repository archive and enter the project folder.
cd SmartVolt

# 2. Create and activate a virtual environment.
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. Install the app and developer tools.
python -m pip install --upgrade pip
pip install -e ".[dev]"

# 4. Create local configuration and initialize the database.
Copy-Item .env.example .env
alembic upgrade head
python -m app.db.seed

# 5. Start the API.
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs` for the interactive Swagger API. The health endpoint is `http://127.0.0.1:8000/api/v1/health`.

### Quick start — macOS/Linux

```bash
cd SmartVolt
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
cp .env.example .env
alembic upgrade head
python -m app.db.seed
uvicorn app.main:app --reload
```

## Start the frontend locally

In a **second terminal** (PowerShell or macOS/Linux shell), start the React dashboard:

```bash
cd SmartVolt/frontend
npm ci
npm run dev
```

Open `http://127.0.0.1:5173`. The workspace pages are available at `/overview`, `/usage`, `/transactions`, `/rooms`, `/simulation`, `/admin`, `/settings`, and `/support`. The top-bar theme control switches between Night mode and Day mode; the choice is saved in browser local storage. Vite proxies `/api` requests to the FastAPI server at `http://127.0.0.1:8000`. After signing in as a resident, the dashboard associates wallet and support operations with that account and selects its assigned meter.

The default `.env.example` uses a local SQLite database to reduce setup friction. For team development, prefer the PostgreSQL setup below so everyone uses the same database engine as CI and deployment.

## Admin, residents and load simulation

The seed creates demo residents `ishan` / `resident123` and `krunal` / `resident123`, plus an admin configured by `ADMIN_USERNAME` / `ADMIN_PASSWORD` (defaults `admin` / `Admin123!`). Keep these demo credentials local-only and configure a strong `AUTH_SECRET`.

The `/admin` page creates rooms, meters, opening wallet balances, and resident accounts. `/simulation` is the Load Lab: toggle an appliance catalogue, run a live simulation clock at different speeds, apply built-in weekday/exam/weekend/heatwave/vacation templates, backfill previous dates, or save a user-specific custom template. Current-day simulation consumes prepaid credit; historical backfills do not debit the current wallet. Residents are limited to their assigned meter and admins can manage all rooms. Appliance and relay behavior is software simulation only. See `docs/API.md`, `docs/DATA_MODEL.md`, and `SECURITY.md`.

## Run the full stack with Docker Compose

Install Docker Desktop, then from the repository root run:

```bash
docker compose up --build -d
docker compose exec api python -m app.db.seed
```

Open the dashboard at `http://127.0.0.1:5173`, the API docs at `http://127.0.0.1:8000/docs`, and PostgreSQL at `localhost:5432`. Compose starts PostgreSQL, runs migrations before starting the API, and serves the Vite dashboard with `/api` proxied to the API service. To view logs, use `docker compose logs -f api frontend`. Stop the stack with `docker compose down`; add `-v` only when you intentionally want to delete the persisted database volume.

The Compose database credentials are **development-only**. Do not reuse them for a deployed environment.

## Hourly analysis, environmental estimate and billing exports

The Usage page supports a 24-bucket hourly report for a selected Asia/Kolkata calendar day, plus daily summaries and 7-/30-day rolling views. Hourly reporting does not misattribute older block-based scenario records to the hour at which the block happened to be saved; such records are included in day totals and labeled as unallocated/coarse history. New scenario applications preserve hour-by-hour energy across hour boundaries.

The environmental panel estimates grid-related CO₂ as `recorded kWh × configured grid factor`. The current default is `0.675 kg CO₂/kWh`, associated with CEA CDM CO₂ Baseline Database Version 22.0; review the current official source before using this in a formal report: https://cea.nic.in/cdm-co2-baseline-database/?lang=en. The displayed “tree-year equivalent” uses an educational assumption of `22 kg CO₂ per tree-year`, not an ecological claim that actual trees were saved. Both factors are configurable in `.env` through `GRID_CO2_FACTOR_KG_PER_KWH` and `TREE_CO2_ABSORPTION_KG_PER_YEAR`.

The Usage page also provides a meter-scoped CSV usage export with date boundaries in Indian Standard Time and a printable monthly billing summary/receipt. Exports include meter/room metadata, recorded units and cost, and the environmental-estimate source. Historical statements report the meter's current tariff as informational only; do not interpret it as a stored historic tariff schedule.

## Autonomous telemetry worker

The API does not launch the synthetic consumption worker automatically. For local testing, enable `SIMULATOR_ENABLED=true` in `.env`, then run `python -m app.simulator` in a third terminal. It creates synthetic consumption at the configured interval and may debit active meter balances, so leave it disabled unless synthetic wallet deductions are intended. For Docker production, the worker is an opt-in Compose profile:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml --profile simulator up -d simulator
```

Do not enable it for real resident balances unless the simulation nature and deduction rules are understood. The worker emits structured operational messages and supports graceful shutdown.

## Useful commands

```bash
# Run tests
pytest

# Lint
ruff check .

# Apply database migrations after pulling changes
alembic upgrade head

# Create a new migration after changing SQLAlchemy models
alembic revision --autogenerate -m "describe schema change"

# Run the separate worker only after setting SIMULATOR_ENABLED=true in .env
python -m app.simulator
```

## API starter surface

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/v1/health` | Health check |
| GET | `/api/v1/meters` | List demo meters |
| GET | `/api/v1/meters/{meter_id}` | Meter state and current balance |
| PATCH | `/api/v1/meters/{meter_id}/power` | Simulated relay on/off |
| POST | `/api/v1/meters/{meter_id}/recharges` | Simulated wallet recharge |
| GET | `/api/v1/meters/{meter_id}/recharges` | Recharge history; optional `status` filter |
| POST | `/api/v1/meters/{meter_id}/readings` | Record simulated consumption (development/admin surface) |
| GET | `/api/v1/meters/{meter_id}/readings` | Reading history |
| GET | `/api/v1/meters/{meter_id}/report?period=7d` | Usage, cost, daily aggregation and environmental estimate (`1d`, `7d`, `30d`); `granularity=hourly&date=YYYY-MM-DD` returns 24 IST buckets |
| GET | `/api/v1/meters/{meter_id}/usage-export?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD` | Meter-authorized CSV usage export for up to 366 inclusive IST calendar days |
| GET | `/api/v1/meters/{meter_id}/billing-statement?month=YYYY-MM` | Meter-authorized monthly summary for printing/saving as PDF |
| POST | `/api/v1/tickets` | Raise a room-wide (default) or private support ticket |
| GET | `/api/v1/users/{user_id}/tickets` | List own tickets and authorized room-wide tickets |
| GET | `/api/v1/tickets/{ticket_id}` | Get an authorized ticket conversation |
| POST | `/api/v1/tickets/{ticket_id}/messages` | Reply to an open ticket |
| GET | `/api/v1/admin/tickets` | Administrator ticket queue and filters |
| PATCH | `/api/v1/admin/tickets/{ticket_id}` | Change status or priority |

Example request bodies:

```json
// POST /api/v1/meters/1/recharges
{
  "user_id": 1,
  "amount": "200.00",
  "idempotency_key": "optional-client-generated-unique-key"
}
```

```json
// PATCH /api/v1/meters/1/power
{ "power_status": false }
```

```json
// POST /api/v1/meters/1/readings
{ "units_used": "0.250" }
```

Amounts are represented as decimal strings in JSON where practical to avoid floating-point money rounding.

## Seeded demo data

`python -m app.db.seed` creates a demo room, users (Krunal and Ishan), a meter and an initial balance only when the demo room does not already exist. The seed operation is idempotent. IDs are database-generated; inspect the response or database rather than assuming IDs in a shared environment.

## Data model

- `rooms`: room number and creation timestamp
- `users`: tenant name/phone and primary room
- `meters`: room-linked meter, balance, relay state, tariff
- `consumption_logs`: measured/simulated kWh, cost, balance after debit, timestamp and source/note
- `recharges`: user-attributed simulated recharge and status
- `wallet_ledger`: append-only credit/debit entries and balance snapshots
- `tickets`: tenant support issues

`wallet_ledger` records balance changes separately from current meter state so changes can be reconciled. Recharge/consumption services use a row lock on PostgreSQL and commit the meter update, transaction record and ledger entry in one database transaction. SQLite is suitable for local learning and unit tests but does not provide the same row-lock semantics as PostgreSQL.

## Team workstreams (from the supplied project specification)

| Member | Workstream |
|---|---|
| Krunal | Project lead/core backend, tariff logic and telemetry generator |
| Ishan | SQL schema, aggregates, auth/role schema, load persistence and safe balance transactions |
| Harsh | Dashboard shell, balance card and relay toggle |
| Harshvardhan | Charts, time filters and CO₂/tree estimates |
| Hansal | Recharge flow, recharge history and tenant attribution |
| Komal | Usage history, room detail and billing exports |
| Khushi | Authentication, profile/settings, tickets and QA |

See [`docs/TEAM_WORKFLOW.md`](docs/TEAM_WORKFLOW.md) before parallel work begins.

## Development and security notes

- Protected meter, wallet, reading, report, simulator, account, and support routes validate the current session and enforce room/account scope, while admin operations require the ADMIN role. This is still a student simulation and not a production security certification: apply rate limiting, review all authorization paths, configure high-entropy deployment secrets, secure backups, and conduct PostgreSQL concurrency and browser end-to-end tests before public access. See `SECURITY.md`.
- Recharge is a payment **simulation**; no payment provider or actual money movement is configured.
- Do not commit `.env`, credentials, database dumps, personal data or production tokens.
- Add authorization checks before allowing a tenant to view or mutate another tenant's records.
- Keep schema changes in Alembic migrations; do not rely on `create_all()` in deployed environments.

## GitHub repository setup

For an existing clone, keep its `.git` directory and apply changes in place. If you're starting from a source-only archive, use a fresh clone of the repository first so the existing commit history and remote are preserved. To publish an entirely new project, create a **blank** GitHub repository (do not pre-add a README or license), then run from this directory:

```bash
git remote add origin https://github.com/Er-Ishan-Srivastav/SmartVolt.git
git push -u origin main
```

If you chose another GitHub repository name or owner, replace the URL accordingly. Invite the remaining six teammates as collaborators, create issues from `docs/ROADMAP.md`, and use pull requests for all team changes. See [`CONTRIBUTING.md`](CONTRIBUTING.md) and [`docs/TEAM_WORKFLOW.md`](docs/TEAM_WORKFLOW.md).

## Project specification

The scope and seven-person workstream mapping are based on the provided *Smart Energy Meter Web Application Specification*. The starter deliberately makes a few implementation choices explicit: FastAPI + PostgreSQL as the shared team baseline, SQLite as a zero-setup local option, and an append-only ledger to audit wallet movements.
