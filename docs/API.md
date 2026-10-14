# API Contract (v0.2)

Base path: `/api/v1`. Swagger UI is available at `/docs`.

## Existing prototype API (retained for compatibility)

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/health` | API health |
| `GET` | `/meters` | Demo meter listing |
| `GET` | `/meters/{meter_id}` | Balance, simulated relay state, tariff and room |
| `PATCH` | `/meters/{meter_id}/power` | Simulated relay ON/OFF |
| `POST` | `/meters/{meter_id}/recharges` | Simulated recharge with optional idempotency key |
| `GET` | `/meters/{meter_id}/recharges` | Recharge history, optional status filter |
| `POST` | `/meters/{meter_id}/readings` | Legacy manual simulated reading |
| `GET` | `/meters/{meter_id}/readings` | Recent readings |
| `GET` | `/meters/{meter_id}/report?period=7d` | `1d`, `7d`, or `30d` aggregate |
| `POST` | `/tickets` | Legacy ticket creation by user ID |
| `GET` | `/users/{user_id}/tickets` | Legacy ticket list |

## Authentication

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/auth/login` | Exchange username/password for a bearer token |
| `GET` | `/auth/me` | Read the authenticated account |

Example login body: `{"username":"admin","password":"Admin123!"}`. Use the returned `access_token` as `Authorization: Bearer <token>`. Tokens expire in eight hours. Change local demo credentials and `AUTH_SECRET` before sharing.

## Admin APIs (ADMIN role required)

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/admin/rooms` | List rooms, meters and resident accounts |
| `POST` | `/admin/rooms` | Create a room/meter, initial ledger entry, and optionally the first tenant |
| `POST` | `/admin/rooms/{room_id}/tenants` | Add a resident to an existing room |

## Appliance and scenario simulation

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/simulation/appliances` | Read catalogue of simulated appliances and wattages |
| `GET` | `/simulation/scenarios?audience=RESIDENT` | List built-in and account-owned templates for that audience |
| `POST` | `/simulation/scenarios` | Save a custom template; ADMIN audience requires an admin account |
| `GET` | `/meters/{meter_id}/simulation/appliances` | List active appliances (signed in; residents only for their own room) |
| `PUT` | `/meters/{meter_id}/simulation/appliances/{appliance_id}` | Enable or disable an appliance (signed in; room access enforced) |
| `POST` | `/meters/{meter_id}/simulation/tick` | Accumulate elapsed simulated seconds and debit for rounded consumption (signed in; room access enforced) |
| `POST` | `/simulation/scenarios/{scenario_id}/apply` | Replay a daily template on a meter, or across every meter as admin |

Scenario applications dated today create readings and debit the wallet. A past date creates historical-only readings and does not debit the current balance again. Future dates are rejected. All simulation endpoints are software-only; no physical relay is involved.

## Error behavior

- `401`: a signed-in account is required or the token is invalid/expired.
- `403`: wrong role or resident attempting to access another room's meter.
- `404`: referenced meter, room, appliance or scenario not found.
- `409`: empty/off meter, duplicate room number or a conflicting recharge idempotency key.
- `422`: invalid request values, malformed daily schedule or unknown appliance ID.

## Security limitation

The legacy prototype API rows above remain available for compatibility and are not all tenant-scoped/authenticated yet. Do not deploy this API publicly until those legacy contracts are secured; see `SECURITY.md`.
