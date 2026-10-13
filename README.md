# SmartVolt — Smart Prepaid Energy Meter Simulator

SmartVolt is a full-stack project foundation for simulating prepaid electricity meters in hostels and shared accommodation. It models rooms, tenants, meters, wallet recharges, consumption readings, a ledger, and support tickets without requiring physical IoT hardware.

> **Current milestone:** first working full-stack foundation. The React dashboard connects to the FastAPI meter, wallet, and usage APIs. Authentication/authorization, payment-provider integration, and production deployment hardening remain follow-on work. The recharge API simulates a payment and must not be treated as a real payment system.

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
npm install
npm run dev
```

Open `http://127.0.0.1:5173`. Vite proxies `/api` requests to the FastAPI server at `http://127.0.0.1:8000`. On a fresh seed, the frontend defaults to user ID `2` (Ishan); check the seed output if using an existing database. The backend currently has no authentication.

The default `.env.example` uses a local SQLite database to reduce setup friction. For team development, prefer the PostgreSQL setup below so everyone uses the same database engine as CI and deployment.

## Run the full stack with Docker Compose

Install Docker Desktop, then from the repository root run:

```bash
docker compose up --build -d
docker compose exec api python -m app.db.seed
```

Open the dashboard at `http://127.0.0.1:5173`, the API docs at `http://127.0.0.1:8000/docs`, and PostgreSQL at `localhost:5432`. Compose starts PostgreSQL, runs migrations before starting the API, and serves the Vite dashboard with `/api` proxied to the API service. To view logs, use `docker compose logs -f api frontend`. Stop the stack with `docker compose down`; add `-v` only when you intentionally want to delete the persisted database volume.

The Compose database credentials are **development-only**. Do not reuse them for a deployed environment.

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

# Run the separate simulated-consumption worker (defaults to one tick per hour)
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
| GET | `/api/v1/meters/{meter_id}/report?period=7d` | Usage, cost, and daily aggregates (`1d` = current UTC day; `7d`/`30d` = rolling windows) |
| POST | `/api/v1/tickets` | Raise a support ticket |
| GET | `/api/v1/users/{user_id}/tickets` | List a tenant's tickets |

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
- `consumption_logs`: measured/simulated kWh, cost, balance after debit, timestamp
- `recharges`: user-attributed simulated recharge and status
- `wallet_ledger`: append-only credit/debit entries and balance snapshots
- `tickets`: tenant support issues

`wallet_ledger` records balance changes separately from current meter state so changes can be reconciled. Recharge/consumption services use a row lock on PostgreSQL and commit the meter update, transaction record and ledger entry in one database transaction. SQLite is suitable for local learning and unit tests but does not provide the same row-lock semantics as PostgreSQL.

## Team workstreams (from the supplied project specification)

| Member | Workstream |
|---|---|
| Krunal | Project lead/core backend, tariff logic and telemetry generator |
| Ishan | SQL schema, aggregates and safe balance transactions |
| Harsh | Dashboard shell, balance card and relay toggle |
| Harshvardhan | Charts, time filters and CO₂/tree estimates |
| Hansal | Recharge flow, recharge history and tenant attribution |
| Komal | Usage history, room detail and billing exports |
| Khushi | Authentication, profile/settings, tickets and QA |

See [`docs/TEAM_WORKFLOW.md`](docs/TEAM_WORKFLOW.md) before parallel work begins.

## Development and security notes

- Authentication is not wired into the initial scaffold. Do not expose this API publicly as-is.
- The reading-write endpoint is intended for simulation/demo use. Restrict it to an authenticated simulator/admin before deployment.
- Recharge is a payment **simulation**; no payment provider or actual money movement is configured.
- Do not commit `.env`, credentials, database dumps, personal data or production tokens.
- Add authorization checks before allowing a tenant to view or mutate another tenant's records.
- Keep schema changes in Alembic migrations; do not rely on `create_all()` in deployed environments.

## GitHub repository setup

The archive contains an initialized local Git repository on `main` with the starter commit. To publish it, create a **blank** GitHub repository (do not pre-add a README or license), then run from this directory:

```bash
git remote add origin https://github.com/Er-Ishan-Srivastav/SmartVolt.git
git push -u origin main
```

If you chose another GitHub repository name or owner, replace the URL accordingly. Invite the remaining six teammates as collaborators, create issues from `docs/ROADMAP.md`, and use pull requests for all team changes. See [`CONTRIBUTING.md`](CONTRIBUTING.md) and [`docs/TEAM_WORKFLOW.md`](docs/TEAM_WORKFLOW.md).

## Project specification

The scope and seven-person workstream mapping are based on the provided *Smart Energy Meter Web Application Specification*. The starter deliberately makes a few implementation choices explicit: FastAPI + PostgreSQL as the shared team baseline, SQLite as a zero-setup local option, and an append-only ledger to audit wallet movements.
