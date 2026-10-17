# Initial Roadmap and Issue Backlog

Use these as initial GitHub Issues. Keep a single issue owner and use the team assignments in the project specification.

## P0 — foundation / integration

- [ ] **Confirm billing rules** (Krunal + Ishan): tariff units, rounding convention, cutoff behavior, refund/failed recharge semantics.
- [x] **Auth and authorization baseline** (Khushi): login/session, roles, current user-to-room scoping, password changes and session revocation are implemented; production rate limiting and deeper security review remain open.
- [ ] **PostgreSQL concurrency tests** (Ishan + Khushi): concurrent recharge/debit, no negative balance, ledger reconciliation.
- [x] **API contract examples** (Krunal + Harsh + Hansal): endpoint routes, authorization and key response behavior are documented; keep docs synchronized with future changes.
- [ ] **UI API states** (Harsh): improve loading/error/empty states and mobile navigation.

## P1 — product modules

- [x] **Room/member management** (Komal): room detail, multiple residents, contact/profile handling, archive lifecycle and room-scoped access.
- [x] **Recharge history UX** (Hansal): meter-scoped and admin-wide history with filters and separate actor/tenant-context attribution; individual consumption allocation per roommate remains deferred.
- [x] **Usage history/export** (Komal): CSV download with date range, meter/room metadata, recorded usage and cost, and environmental factor/source. Monthly printable billing summary is also available; historical tariffs are not versioned yet.
- [x] **Energy charts** (Harshvardhan): hourly and daily telemetry views plus 7-/30-day summaries, with units/cost reporting. Full calendar-month trend and units-vs-money presentation switch remain potential enhancements.
- [x] **Environmental estimate** (Harshvardhan): configurable CO₂ factor, official CEA source link, explicit tree-year assumption, and report/export inclusion.
- [x] **Support ticket UX** (Khushi): room-wide/private ticket creation, threaded replies, admin queue/history, status progression and visibility tests.
- [x] **Dedicated telemetry worker controls** (Krunal): separate opt-in worker, configurable interval/load, structured logging, and graceful shutdown. It is intentionally disabled by default.

## P2 — hardening / delivery

- [ ] API rate limiting and abuse protections.
- [ ] Structured logs, request IDs and useful service health checks.
- [ ] PostgreSQL backup/restore note and deployment configuration.
- [ ] Accessibility pass and responsive UI review.
- [ ] End-to-end smoke tests for browser flows.

## Acceptance baseline

Every completed issue should include a reproducible validation note; automated tests for logic changes; reversible migration where schema changes; and updated docs for endpoint, setup or security changes. No task is production-ready until tenant authorization has been tested.


## Deferred to future iterations

- **Individual roommate consumption allocation:** requires a transparent allocation policy (equal split, configurable shares, or per-appliance attribution) and should not be inferred from a single shared meter.
- **Dynamic/time-of-use tariffs:** the current schema and statements expose a fixed current tariff per meter; historical tariff schedules require versioned effective dates.
- **Actual payment gateway and failed-payment lifecycle:** recharges remain simulated successful credits and do not move real money.
- **Environmental model refinement:** the grid factor and tree-year conversion are configurable estimates; formal reporting should review current official factors and documented assumptions.
- **Production security hardening:** rate limiting, audit events, secure session/cookie review, PostgreSQL concurrency tests, end-to-end browser testing, and a rehearsed backup/restore procedure are required before a public deployment.
- **Calendar-month analytics and payment-ledger reconciliation UX:** can be added after the current hourly/daily/rolling reporting is accepted.


## Final-iteration release candidates

- [x] CSV usage exports scoped by authorized meter and inclusive IST date range (up to 366 calendar days).
- [x] Printable monthly billing statement with ledger-based balance snapshots when available and transparent missing-history handling.
- [x] Environmental grid-CO₂ estimate with configurable factor/source and an explicitly illustrative tree-year equivalent.
- [x] India-local hourly reporting; coarse legacy scenario blocks are reported as unallocated rather than misrepresented as precise hourly data.
- [x] Standalone opt-in telemetry worker with structured logs and graceful shutdown. Production Compose keeps it behind the `simulator` profile.
- [x] Safe initial production-admin bootstrap that does not create default-password demo residents.

## Deliberately deferred

- Per-roommate allocation of a shared meter's consumption.
- Dynamic/time-of-use tariffs and historical tariff versioning.
- Real payment-provider integration and a full failed-payment/refund lifecycle.
- Production security enhancement including rate limiting, stronger session architecture, auditable admin actions, PostgreSQL race/concurrency tests, and browser E2E tests.
- Full calendar-month chart and CO₂ factor versioned snapshots for historical recalculation.
