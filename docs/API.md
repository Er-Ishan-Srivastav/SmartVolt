# API Contract (v0.2)

Base path: `/api/v1`. Swagger UI is available at `/docs`.

## Application API

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/health` | API health |
| `GET` | `/meters` | Demo meter listing |
| `GET` | `/meters/{meter_id}` | Balance, simulated relay state, tariff and room |
| `PATCH` | `/meters/{meter_id}/power` | Simulated relay ON/OFF |
| `POST` | `/meters/{meter_id}/recharges` | Resident self-recharge for the signed-in user's own room, with optional idempotency key |
| `GET` | `/meters/{meter_id}/recharges` | Recharge history for an authorized meter, optional status filter |
| `POST` | `/meters/{meter_id}/readings` | Legacy manual simulated reading |
| `GET` | `/meters/{meter_id}/readings` | Recent readings |
| `GET` | `/meters/{meter_id}/report?period=7d` | Daily aggregate (`1d`, `7d`, `30d`) or `granularity=hourly&date=YYYY-MM-DD` for 24 Asia/Kolkata hour buckets; includes configurable CO₂ estimate and source metadata |
| `GET` | `/meters/{meter_id}/usage-export?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD` | CSV usage export for an authorized meter, date range inclusive in IST, maximum 366 calendar days |
| `GET` | `/meters/{meter_id}/billing-statement?month=YYYY-MM` | Monthly consumption/recharge/balance summary for print/save as PDF; the tariff field is current/informational, not a historic tariff schedule |
| `POST` | `/tickets` | Create a room-wide (default) or private support ticket; requester identity is derived from the session |
| `GET` | `/users/{user_id}/tickets` | Own tickets plus room-wide tickets visible to the signed-in resident |
| `GET` | `/tickets/{ticket_id}` | Read ticket details and conversation if authorized |
| `POST` | `/tickets/{ticket_id}/messages` | Add a reply to an accessible, non-closed ticket |
| `GET` | `/admin/tickets` | Admin-only ticket queue; supports `bucket=PENDING` or `bucket=CLOSED`, plus optional `status` and `visibility` filters |
| `GET` | `/admin/tickets/summary` | Counts all pending and resolved/closed tickets, including older records outside the current list page |
| `PATCH` | `/admin/tickets/{ticket_id}` | Admin-only status/priority update; sending an admin response is required before resolving/closing |

## Authentication

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/auth/login` | Exchange username/password for a bearer token |
| `GET` | `/auth/me` | Validate the current session and read the signed-in account |
| `POST` | `/auth/logout` | Revoke the current session server-side |
| `PATCH` | `/auth/profile` | Update the signed-in account name and contact number; username, role, tenant code, and room assignment are not self-editable |
| `POST` | `/auth/change-password` | Verify current password, change password, and revoke every active session for the account |

Example login body: `{"username":"admin","password":"Admin123!"}`. Use the returned `access_token` as `Authorization: Bearer <token>`. Sessions are stored server-side, expire in eight hours, and are revoked on logout; self-service password changes revoke all active sessions for that account. The frontend keeps bearer tokens in per-tab `sessionStorage` and validates the session against `/auth/me` when loaded. Change local demo credentials and `AUTH_SECRET` before sharing.

## Admin APIs (ADMIN role required)

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/admin/rooms` | List rooms, meters and resident accounts |
| `GET` | `/admin/recharge-targets?query=...` | Search active meters by meter/room ID or code, room number, tenant code, tenant name, or username |
| `POST` | `/admin/recharges` | Recharge a resolved meter; records administrator actor separately from optional tenant context |
| `GET` | `/admin/recharges` | Cross-room recharge history with meter, tenant context, actor, amount, status, and date filters |
| `POST` | `/admin/rooms` | Create a room/meter, initial ledger entry, and optionally the first tenant |
| `PATCH` | `/admin/rooms/{room_id}` | Update room number and meter tariff |
| `DELETE` | `/admin/rooms/{room_id}` | Archive a room and disable its meter without deleting history; returns `409` while active tenants remain assigned |
| `POST` | `/admin/rooms/{room_id}/tenants` | Add a resident to an existing room |
| `PATCH` | `/admin/tenants/{tenant_id}` | Update tenant name, username, phone, or password |
| `DELETE` | `/admin/tenants/{tenant_id}` | Deactivate tenant, unassign room, revoke sessions, and retain historical account references |

Room archiving preserves the meter, balance, readings, recharge records, and wallet ledger entries; only current simulated appliance state is cleared. Tenant deactivation is intentionally non-destructive to account history: it clears the room assignment and login credentials instead of deleting the underlying user row.

## Appliance and scenario simulation

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/simulation/appliances` | Read catalogue of simulated appliances and wattages |
| `GET` | `/simulation/scenarios?audience=RESIDENT` | List built-in and account-owned templates for that audience |
| `POST` | `/simulation/scenarios` | Save a custom template; ADMIN audience requires an admin account |
| `GET` | `/meters/{meter_id}/simulation/appliances` | List active appliances (signed in; residents only for their own room) |
| `PUT` | `/meters/{meter_id}/simulation/appliances/{appliance_id}` | Enable/disable an appliance and set its quantity (signed in; room access enforced) |
| `POST` | `/meters/{meter_id}/simulation/tick` | Accumulate elapsed simulated seconds and debit for rounded consumption (signed in; room access enforced) |
| `POST` | `/simulation/scenarios/{scenario_id}/apply` | Replay a daily template on a meter, or across every meter as admin |

Scenario applications dated today create readings and debit the wallet. A past date creates historical-only readings and does not debit the current balance again. Future dates are rejected. All simulation endpoints are software-only; no physical relay is involved.

Live appliance switches accept `{"enabled": true, "quantity": 3}` to represent three units of the same appliance. Quantity is constrained to 1–100; the API returns each appliance's per-unit `watts` and stored `quantity`, while the tick response's `live_watts` is the combined wattage. Disabling an appliance uses `{"enabled": false}`.

Each scenario block may include `appliance_quantities`, for example `{"label":"Evening fans","start_min":1080,"end_min":1200,"appliance_ids":["fan"],"appliance_quantities":{"fan":3}}`. Quantities must be 1–100 and may only name appliance IDs in the same block. Existing scenarios without this map remain compatible and are treated as one unit per listed appliance.

## Error behavior

- `401`: a signed-in account is required or the token is invalid/expired.
- `403`: wrong role or resident attempting to access another room's meter.
- `404`: referenced meter, room, appliance or scenario not found.
- `409`: empty/off meter, duplicate room number/username/phone or a conflicting recharge idempotency key.
- `422`: invalid request values, malformed daily schedule or unknown appliance ID.

## Security limitation

Meter, wallet, reading, report, support, and simulation operations require a valid session. Residents can access their own tickets, room-wide tickets belonging to their current room, and ticket replies permitted by visibility; private tickets remain requester/admin-only. Admin APIs require the ADMIN role. This is still a student simulation and should not be exposed publicly without a full production security review; see `SECURITY.md`.


## Room and tenant lifecycle (migration 0004)

Admin room responses include `room_code` and `is_active`; their meter payload includes `meter_code` and `is_active`; resident entries include `tenant_code` and `is_active`. New codes are allocated automatically.

- `GET /api/v1/admin/rooms?include_archived=true` includes archived rooms (default is active rooms only).
- `DELETE /api/v1/admin/rooms/{room_id}` archives rather than physically deleting. It returns `409` while active tenants remain assigned. History is retained.
- `POST /api/v1/admin/rooms/{room_id}/restore` reactivates an archived room/meter.
- Deactivated tenants cannot authenticate; deactivating a tenant revokes their live sessions.

## Recharge attribution and idempotency (migration 0005)

`recharges.recharge_code` issues permanent human-readable references such as `RCH-000001`. The legacy `recharges.user_id` field now represents optional tenant context, not the transaction actor. `recharges.actor_user_id` stores the authenticated user who performed the operation. `wallet_ledger.actor_user_id` records the actor independently of its optional legacy/tenant-context `user_id`. Transactions created before migration 0005 keep actor attribution unknown rather than guessing it.

Admin recharge target selectors are `meter_id`, `meter_code`, `room_id`, `room_code`, `room_no`, `tenant_id`, `tenant_code`, and `username`. The server resolves a room or tenant selector to the room's active meter before crediting the wallet. `tenant_context_id` is optional and, when provided, must be an active resident assigned to the selected meter's room. Amount, balance, recharge record, and ledger credit commit atomically. An idempotency key cannot be reused for a different actor, meter, tenant context, or amount.


## Support conversations (migration 0006)

Tickets have permanent `TKT-000001`-style codes, a room association and immutable room-code/room-number snapshots, visibility (`ROOM` or `PRIVATE`), priority (`LOW`, `NORMAL`, `HIGH`, `URGENT`), status (`OPEN`, `IN_PROGRESS`, `AWAITING_RESIDENT`, `RESOLVED`, `CLOSED`), and created/updated timestamps. Existing tickets are backfilled. Existing tickets whose requester had no room assignment are made private by default. The original ticket description is preserved and copied into the new `ticket_messages` timeline as the initial message.

Room-wide tickets are visible to the requester and active residents currently assigned to the ticket's original room. Private tickets are visible to the requester and administrators. Administrators can reply to any ticket and change status/priority. A resident reply to a resolved ticket reopens it; a reply to an awaiting-resident ticket returns it to in-progress. Closed tickets must be reopened by an administrator before another reply can be posted. Resolving/closing requires at least one administrator response. Messages preserve author-name and role snapshots for readable history after account deactivation.


## Hourly consumption analysis

`GET /api/v1/meters/{meter_id}/report?granularity=hourly&date=YYYY-MM-DD` returns 24 Asia/Kolkata hour buckets. Legacy block-based scenario data and seeded daily-total history are reported as unallocated rather than falsely assigned to one hour. Daily reports also group timestamps by Asia/Kolkata calendar date.


## Usage exports, billing statements and environmental estimates

Usage export rows include reading ID, timestamp in `Asia/Kolkata`, source/note, units, recorded cost and balance after the reading. CSV is UTF-8 with BOM for spreadsheet compatibility; user-controlled text cells are protected against spreadsheet formula execution. The endpoint refuses reversed ranges and ranges over 366 inclusive calendar days.

Monthly statements include meter/room identifiers, date period, recorded kWh/cost, recharge totals/count, available ledger-based opening/closing balances, and the estimated environmental metric. The statements are summaries for a simulation, not tax invoices and not proof of an actual utility payment. A missing ledger snapshot is represented as `null`, not guessed.

Environmental estimate: `estimated_co2_kg = total_units_kwh * GRID_CO2_FACTOR_KG_PER_KWH`. The factor defaults to `0.675 kg/kWh` and is configurable. It is identified with CEA CO₂ Baseline Database Version 22.0; administrators should verify the current official database before formal reporting: https://cea.nic.in/cdm-co2-baseline-database/?lang=en. `tree_years_equivalent` uses the explicitly illustrative `TREE_CO2_ABSORPTION_KG_PER_YEAR` assumption (default 22 kg/year); this is not a claim about actual trees saved.

## Telemetry worker

The autonomous worker is opt-in and runs separately from the API. Set `SIMULATOR_ENABLED=true` before `python -m app.simulator`. For production Compose, enable only deliberately with `--profile simulator`. Each tick may debit an active meter, so the worker must remain disabled unless synthetic consumption and wallet deduction are intended.
