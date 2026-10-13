# Team Workflow

The supplied specification defines seven module owners. Keep module ownership clear, but use pull requests to agree on shared schema and API contracts.

## Branching and pull requests

- `main` is the stable integration branch; never push unfinished features directly to it.
- Create one branch per issue: `feat/recharge-history`, `feat/usage-report`, `fix/balance-race`, `test/ticket-api`.
- Make focused commits using imperative messages, e.g. `Add consumption ledger entry`.
- Open a PR with purpose, screenshots/API examples where useful, tests run and migration notes.
- Require at least one team review. Resolve review comments before merging.
- Never commit `.env`, credentials, database files or real tenant data.

## First-week integration order

1. **Krunal — core backend:** confirm routes/service contracts and tariff assumptions with Ishan.
2. **Ishan — database:** review table constraints, indexes, aggregate semantics and transaction consistency; own all schema migrations.
3. **Khushi — QA/auth:** define auth roles and add integration/data-integrity tests before endpoints are exposed.
4. **Harsh — dashboard:** use `GET /meters/{id}` and `PATCH /meters/{id}/power` contracts.
5. **Hansal — wallet:** use the recharge endpoint and recharge-history filter; treat recharge as simulated until a payment adapter is planned.
6. **Harshvardhan — charts:** use the report endpoint; agree on CO₂ factor and source before presenting environmental estimates.
7. **Komal — history/rooms:** build room/usage summaries and CSV exports after field names and date semantics are stable.

## API/schema contract rules

- Schema or response-shape changes need a PR and, where relevant, a migration.
- Keep money as `NUMERIC`/`Decimal`, never binary floating-point values in the database.
- Recharge, balance debit, ledger, and reading must be committed atomically.
- `wallet_ledger.amount` is positive for credits and negative for consumption debits.
- PostgreSQL is the shared team database. SQLite is for local quick-start and tests, not for validating concurrency behavior.
- The simulator should call billing services; do not duplicate tariff arithmetic in route handlers or the frontend.

## Definition of done

- [ ] Acceptance criteria are met.
- [ ] Automated test covers the happy path and relevant failure paths.
- [ ] `pytest`, `ruff check .` and `ruff format --check .` pass.
- [ ] Migration is reversible and tested when schema changes.
- [ ] API docs/readme are updated if behavior changes.
- [ ] Auth/data exposure and failure handling were considered.
