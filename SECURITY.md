# Security Policy

SmartVolt is a local student simulation. Appliance loads and relay states are simulated; no physical electrical hardware or payment gateway is connected.

## Development authentication

- Admin login uses the `ADMIN_USERNAME` and `ADMIN_PASSWORD` settings. Fresh local demo defaults are `admin` / `Admin123!`.
- The seed creates resident accounts `ishan` and `krunal`, both with demo password `resident123`. These are development-only credentials.
- Passwords are stored as PBKDF2-SHA256 hashes; raw passwords are never stored. API access tokens are HMAC-signed and expire after eight hours. Configure `AUTH_SECRET` before sharing the app.
- New admin routes and load-simulation routes enforce roles on the backend. Residents can operate only the meter assigned to their room. Admins can manage rooms and apply scenarios to multiple rooms.

## Known limitations

- This is not production-grade identity infrastructure. Before deployment, use a reviewed auth/session implementation, strong secret generation and rotation, login throttling, secure cookies or carefully managed bearer tokens, audit review, backups, and PostgreSQL concurrency testing.
- Several legacy demo endpoints remain open for backward compatibility with the original prototype, including global meter listing/read routes, the simulated recharge route, legacy manual consumption writes, and support-ticket endpoints that accept a user ID. Do not expose the API publicly until these legacy contracts are tenant-scoped and authorized.
- Recharge requests create simulated successful transactions; they do not move money.
- Docker Compose's default database password is for local development only.

Do not post secrets, credentials, personal data, or exploitable production details in public issues.
