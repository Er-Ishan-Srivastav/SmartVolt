# SmartVolt frontend

React + TypeScript + Vite user interface for the SmartVolt simulated prepaid energy meter.

## Run

```bash
npm install
npm run dev
```

The app uses the Vite proxy configured in `vite.config.ts` to forward `/api` to the FastAPI service.

## Workspace pages

- `/overview` — balance, energy summary, consumption chart, meter status and recent recharges.
- `/usage` — day/week/month aggregates, units-versus-cost chart toggle and recent individual readings.
- `/transactions` — recharge history, status filtering, search, and CSV export.
- `/rooms` — meter configuration, tariff, balance and simulated relay control.
- `/settings` — persistent day/night theme, low-balance reminder and demo resident ID.
- `/support` — create and review support tickets.

Navigation uses the History API, so page links work independently and browser back/forward is supported. Night mode is the default; the selected theme and a few demo preferences are stored locally in the browser. The application is a simulation only: it is not connected to a physical electrical relay or a real payment provider.

## Local demo accounts

Run `alembic upgrade head` and `python -m app.db.seed` from the repository root first. Default resident accounts are `ishan` / `resident123` and `krunal` / `resident123`. Administrator defaults are `admin` / `Admin123!`; the password can be configured with `ADMIN_PASSWORD` before seeding a fresh database. Change demo credentials and `AUTH_SECRET` before sharing.

Load Lab requires login to enable appliances, run a simulation tick, or apply a scenario. Residents can use only their assigned room meter. Admins can create rooms, add tenants, save administrator templates, and apply a scenario across rooms. Old dates generate historical readings without charging the current wallet.
