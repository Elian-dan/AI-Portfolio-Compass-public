# Security Policy

AI Portfolio Compass is a local-first portfolio research tool. It may process
brokerage metadata, holdings, watchlists, imported files, and AI analysis
context, so privacy and safe defaults matter.

## Supported Versions

The project is currently in early `0.x` development. Security fixes are handled
on the `main` branch until a formal release policy is introduced.

## Reporting a Vulnerability

Please do not publish sensitive details in a public issue. Open a private
security advisory on GitHub if available, or contact the maintainers through the
repository owner profile.

Include:

- A concise description of the issue.
- Steps to reproduce.
- Whether secrets, account data, local databases, or external AI requests are involved.
- Suggested mitigation if you have one.

## Safety Boundaries

- The app does not implement order placement, cancellation, modification, or
  trading unlock flows.
- API keys should live only in `.env` or the user's runtime environment.
- Local databases, logs, exports, screenshots, QR codes, and imported account
  files must not be committed.
- External AI calls should receive only the minimum context needed for a single
  analysis request.

For more implementation detail, see [docs/SECURITY.md](docs/SECURITY.md).
