# CTO Agents Backend

This project provides a FastAPI-based backend service that manages application configuration and agent metadata. It targets Python 3.12 and includes:

- Centralised application settings powered by `pydantic-settings`.
- Standardised API response envelopes and error models.
- An agents manifest service that maintains a Markdown catalogue with caching support.
- A FastAPI application bootstrap with health endpoint, CORS configuration, and lifecycle events.

## Getting started

Install dependencies and run the application using `uvicorn`:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
uvicorn app.main:app --reload
```

Environment variables prefixed with `APP_` can be used to configure provider credentials, base URLs, and filesystem paths. By default, the service will ensure the required data, configuration, and agents manifest resources exist at start-up.
