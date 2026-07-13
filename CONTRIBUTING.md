# Contributing

Thanks for your interest in improving AI Portfolio Compass.

This project handles sensitive financial context, so contributions should keep
privacy, local-first behavior, and read-only brokerage access as core design
constraints.

## Development Setup

Create a local environment file:

```bash
cp .env.example .env
```

Install backend dependencies:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Install frontend dependencies:

```bash
cd frontend
npm install
```

Run the app from the repository root:

```bash
./scripts/start.sh
```

## Before Opening a Pull Request

- Do not commit `.env`, database files, logs, account exports, screenshots with
  private holdings, QR codes, or real API keys.
- Run backend tests with `pytest`.
- Run the frontend build with `npm run build` from `frontend/`.
- Keep new provider integrations optional and disabled unless configured by the user.
- Preserve the no-trading-action boundary unless the project maintainers have
  explicitly accepted a design change.

## Pull Request Guidelines

- Explain the user-facing behavior change.
- Include tests for backend logic when practical.
- Update README or docs when setup, configuration, API behavior, or safety
  boundaries change.
- Keep pull requests focused; unrelated refactors should be separate.

## Security and Privacy

If you discover a vulnerability or a privacy risk, do not open a public issue
with sensitive details. Follow the reporting guidance in [SECURITY.md](SECURITY.md).
