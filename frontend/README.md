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
