# Initial Roadmap and Issue Backlog

Use these as initial GitHub Issues. Keep a single issue owner and use the team assignments in the project specification.

## P0 — foundation / integration

- [ ] **Confirm billing rules** (Krunal + Ishan): tariff units, rounding convention, cutoff behavior, refund/failed recharge semantics.
- [ ] **Auth and authorization** (Khushi): login/session, roles, enforce user-to-room scoping on all tenant endpoints.
- [ ] **PostgreSQL concurrency tests** (Ishan + Khushi): concurrent recharge/debit, no negative balance, ledger reconciliation.
- [ ] **API contract examples** (Krunal + Harsh + Hansal): document stable response shapes and error codes.
- [ ] **UI API states** (Harsh): improve loading/error/empty states and mobile navigation.

## P1 — product modules

- [ ] **Room/member management** (Komal): room detail, residents, phone/contact handling with privacy controls.
- [ ] **Recharge history UX** (Hansal): status/date filters and per-roommate attribution view.
- [ ] **Usage history/export** (Komal): CSV download with billing period, tariff and meter metadata.
- [ ] **Energy charts** (Harshvardhan): hourly/daily/monthly filters, units-vs-money chart toggle.
- [ ] **Environmental estimate** (Harshvardhan): configurable CO₂ factor with documented source and explicit assumptions.
- [ ] **Support ticket UX** (Khushi): create/list tickets, ticket status progression and validation.
- [ ] **Dedicated telemetry worker controls** (Krunal): start/stop configuration, structured logging and graceful shutdown.

## P2 — hardening / delivery

- [ ] API rate limiting and abuse protections.
- [ ] Structured logs, request IDs and useful service health checks.
- [ ] PostgreSQL backup/restore note and deployment configuration.
- [ ] Accessibility pass and responsive UI review.
- [ ] End-to-end smoke tests for browser flows.

## Acceptance baseline

Every completed issue should include a reproducible validation note; automated tests for logic changes; reversible migration where schema changes; and updated docs for endpoint, setup or security changes. No task is production-ready until tenant authorization has been tested.
