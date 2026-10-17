# Security Policy

SmartVolt is a local student simulation. Appliance loads and relay states are simulated; no physical electrical hardware or payment gateway is connected.

## Development authentication

- Admin login uses the `ADMIN_USERNAME` and `ADMIN_PASSWORD` settings. Fresh local demo defaults are `admin` / `Admin123!`.
- The seed creates resident accounts `ishan` and `krunal`, both with demo password `resident123`. These are development-only credentials.
- Passwords are stored as PBKDF2-SHA256 hashes; raw passwords are never stored. API access tokens are HMAC-signed, backed by a database session record, and expire after eight hours. Sign-out and tenant password resets revoke sessions server-side.
- The frontend requires a successful server-side `/auth/me` check before rendering account data. Bearer tokens are stored in per-tab `sessionStorage`; logout and password resets revoke sessions server-side. The backend scopes meter, wallet, usage, simulation and support endpoints to a valid session; residents can access meters in their assigned room, their own tickets, and room-wide tickets belonging to their current room; private tickets are requester/admin-only. Admin-only routes enforce administrator roles on the backend.
- Run `alembic upgrade head` after pulling updates to create the `auth_sessions` table.

## Known limitations

- This remains a student simulation, not production-grade identity infrastructure. Before public deployment, add login throttling, use a high-entropy secret with rotation, review token storage/XSS risk, audit logs, backups, and PostgreSQL concurrency/security testing.
- Authentication is bearer-token based with per-tab `sessionStorage` for this local demo. A production deployment should prefer a reviewed session design with secure, HttpOnly cookies and CSRF protection where appropriate.
- Recharge requests create simulated successful transactions; they do not move money.
- Docker Compose's default database password is for local development only.

Do not post secrets, credentials, personal data, or exploitable production details in public issues.
