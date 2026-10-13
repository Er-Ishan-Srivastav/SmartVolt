# Contributing to SmartVolt

## Local checks

1. Create a virtual environment and install `pip install -e ".[dev]"`.
2. Copy `.env.example` to `.env`, then apply migrations with `alembic upgrade head`.
3. Run `pytest` and `ruff check .` before opening a pull request.
4. For UI work, run `cd frontend && npm install && npm run build`.

## Change guidelines

- Open an issue first for cross-module changes or a new feature.
- Branch from `main`, keep a branch scoped to one issue, and open a pull request.
- Add or update tests for changed behavior, including failure paths.
- Schema changes must include an Alembic migration.
- API changes must update the README/API docs and be communicated to frontend contributors.
- Never commit secrets, `.env`, local databases, production data or real payment details.
- Do not represent simulation data as actual electricity-meter telemetry or actual payments.

See [`docs/TEAM_WORKFLOW.md`](docs/TEAM_WORKFLOW.md) for module ownership and integration conventions.
