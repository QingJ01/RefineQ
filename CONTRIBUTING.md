# Contributing to RefineQ

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Set-Location apps/web
npm ci
```

## Quality checks

Run the checks relevant to your change, then run the complete suite before opening a pull request:

```powershell
python -m pytest -q
python -m ruff check src tests scripts
Set-Location apps/web
npm test
npm run lint
npm run build
```

Use focused modules, explicit types, server-side authorization, atomic persistence, and tests for
every behavior change. Never commit user data, `.env` files, credentials, or generated build output.

Commit messages follow `<type>: <summary>`, for example `feat: add review queue filtering`.

