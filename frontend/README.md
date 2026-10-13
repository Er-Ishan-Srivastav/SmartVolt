# SmartVolt Dashboard

React + TypeScript + Vite frontend for the SmartVolt simulation API.

## Local development

```bash
npm install
npm run dev
```

Vite serves the dashboard on `http://127.0.0.1:5173` and proxies `/api/*` to `http://127.0.0.1:8000`. Set `VITE_API_PROXY_TARGET` to override the proxy target (Docker Compose uses `http://api:8000`).

## Build

```bash
npm run build
npm run preview
```

This is a demo UI. It has no real sign-in and no payment gateway. Tenant identity fields are temporary scaffolding until the authentication module is implemented.
