# SmartVolt final-iteration candidate

This iteration closes selected specification gaps while deliberately keeping broader financial/accounting features for a later release.

## Included in this candidate

- Authenticated room/meter-scoped hourly and daily/7-/30-day consumption analytics using `Asia/Kolkata` reporting boundaries.
- Legacy scenario-block readings are identified as coarse/unallocated in hourly analytics instead of being falsely assigned to one hour.
- Configurable grid CO₂ estimate in reports, usage CSV, and monthly billing statement. The default is `0.675 kg CO₂/kWh`, associated with CEA CO₂ Baseline Database Version 22.0 for FY 2025–26; verify the latest official factor before formal reporting: https://cea.nic.in/cdm-co2-baseline-database/?lang=en. Numeric support for the FY 2025–26 weighted average is also summarized here: https://www.textileschool.com/42388/supplier-carbon-questionnaire-scope-1-2/.
- An illustrative tree-year equivalent based on `TREE_CO2_ABSORPTION_KG_PER_YEAR=22.0`. This is explicitly an educational equivalence, not a claim of actual trees saved.
- Meter-scoped usage CSV export for inclusive IST date ranges up to 366 calendar days, with spreadsheet formula-injection protection.
- Printable monthly billing summary/receipt containing readings, consumption cost, recharges, ledger-derived balance snapshots where available, and environmental estimate. It is not a tax invoice or a record of real utility-payment processing; the tariff shown is the current tariff, not a historic tariff schedule.
- Separate synthetic telemetry worker with configurable interval/load, structured logging, graceful shutdown, and disabled-by-default local operation.
- Production Compose exposes the synthetic worker only through the explicit `simulator` profile.
- A production initial-admin bootstrap that does not create demo residents with shared development passwords.
- Updated setup, API, data-model, roadmap, and production deployment documentation.

## Deliberately deferred

- Per-roommate allocation of shared-meter consumption. This requires an explicit and defensible allocation policy; the shared meter does not measure each person's individual energy use.
- Dynamic/time-of-use tariffs and historical tariff versioning.
- Real payment gateway integration, failed payment attempts, refunds and settlement reconciliation.
- Production identity hardening such as rate limiting, security-reviewed cookie/session design, admin audit log, and full PostgreSQL concurrent debit/recharge stress tests.
- Complete calendar-month analytics and historical snapshots of environmental factors.

## Local verification

From the repository root on Windows/Git Bash:

```bash
source .venv/Scripts/activate
python -m alembic upgrade head
python -m pytest
python -m ruff check .
cd frontend
npm ci
npm run build
```

The source-bundle validation completed with 51 backend tests passing, Python compilation passing, and the TypeScript `tsc -b` project check passing. The current Linux packaging environment does not have Ruff installed and its npm registry request did not complete; the full Vite production bundle must therefore be confirmed on the Windows development machine with the commands above.

## Production deployment gate

Before public AWS access, review `SECURITY.md`, use the `docker-compose.prod.yml` path, generate a unique `AUTH_SECRET`, PostgreSQL password and administrator password, provision the initial admin with `python -m app.db.bootstrap_admin`, and do not run the development demo seed against production. Keep PostgreSQL/API ports private, expose HTTPS through Caddy, configure host/cloud firewall rules, enable cost controls, and establish/verify database backups. The simulator profile must remain disabled unless synthetic consumption and balance deduction are intentionally wanted.
