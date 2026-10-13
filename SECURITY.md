# Security Policy

SmartVolt is currently a student simulation project, not a production payment or electrical-control system.

## Reporting

Do not post secrets, credentials, personal data or exploitable production details in a public issue. Contact the repository maintainers privately through GitHub if the repository is published and private contact is available.

## Known development limitations

- Authentication and tenant authorization are not implemented yet.
- The recharge endpoint is a payment simulation and does not call a payment provider.
- The consumption-write endpoint accepts simulated readings and must be access-controlled before deployment.
- The Docker Compose password is for local development only.

Do not expose the starter API publicly until authentication, authorization, rate limiting, secrets management, and production configuration have been reviewed.
