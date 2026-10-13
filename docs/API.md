# API Contract (v0.1)

Base path: `/api/v1`. Swagger UI is available at `/docs` when the API server is running.

| Endpoint | Success | Notes |
|---|---:|---|
| `GET /health` | 200 | API process health, not a full DB readiness check |
| `GET /meters` | 200 | Lists demo meters; requires tenant-scoping before production |
| `GET /meters/{meter_id}` | 200 | Returns balance, relay state, tariff and room ID |
| `PATCH /meters/{meter_id}/power` | 200 | Body: `{"power_status": true}`; refuses ON at zero balance (409) |
| `POST /meters/{meter_id}/recharges` | 201 | Body: `user_id`, positive `amount`, optional `idempotency_key`; verifies same room |
| `GET /meters/{meter_id}/recharges` | 200 | Optional `status=SUCCESSFUL` or `status=FAILED`; `limit` 1–200 |
| `POST /meters/{meter_id}/readings` | 201 | Body: `units_used`; simulation/admin write surface, returns 409 when meter is off/empty |
| `GET /meters/{meter_id}/readings` | 200 | Newest readings first; `limit` 1–500 |
| `GET /meters/{meter_id}/report?period=7d` | 200 | `period` is `1d`, `7d`, or `30d`; aggregates units/cost and daily buckets (`1d` is the current UTC calendar day; `7d` and `30d` are rolling windows) |
| `POST /tickets` | 201 | Body: `user_id`, `issue_type`, `description` |
| `GET /users/{user_id}/tickets` | 200 | Ticket history for a tenant |

## Error behavior

- `404`: meter/user not found.
- `403`: user is not assigned to the meter's room for recharge.
- `409`: attempting to power on an empty meter, duplicate idempotency key with a different request, or recording consumption when meter is off/empty.
- `422`: request body or query validation failed.

## Important current limitations

No authentication middleware is installed. The `/meters` listing and user-facing APIs are prototype contracts; add identity-aware authorization before deployment. Recharge requests write a **simulated successful** transaction and are not evidence of real payment. Only an external simulator/admin should be able to post readings in a deployed design.
