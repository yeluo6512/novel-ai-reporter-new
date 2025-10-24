# Dockerized FastAPI Application

This repository ships a minimal FastAPI application that is ready to run in a
containerized environment. The application serves an API from `/` and `/health`,
and optionally exposes built frontend assets from `frontend/dist`.

## Quick start

1. Copy the provided environment template:

   ```bash
   cp .env.example .env
   ```

2. Prepare the bind-mounted volumes (creates `./data` and `./config` with
   sensible permissions):

   ```bash
   ./scripts/prepare-volumes.sh
   ```

3. Build and start the stack:

   ```bash
   docker compose up --build
   ```

   Or run the helper that preps volumes and launches Compose in one step:

   ```bash
   ./scripts/dev-up.sh
   ```

   The API will be available at <http://localhost:8080> with a health check at
   <http://localhost:8080/health>.

## Docker image design

- **Base image**: `python:3.12-slim` using a multi-stage build.
- **Dependency installation**: requirements are installed into a virtual
  environment during the builder stage to keep the runtime image lean.
- **Non-root runtime**: the container runs as `appuser` (UID/GID 1000 by
  default). You can override the username, UID, or GID at build time via
  `APP_USER`, `APP_UID`, and `APP_GID` build arguments. The docker-compose file
  reads these from environment variables if supplied.
- **Static assets**: the frontend production build under `frontend/dist` is
  copied into `/app/static` and served from `/static`.
- **Configuration**: any files in `./config` on the host are mounted to
  `/app/config` (read-only) inside the container.
- **Health check**: Docker performs an HTTP health check on
  `http://127.0.0.1:8080/health`.
- **Startup command**: the app starts with `uvicorn app.main:app --host 0.0.0.0 --port 8080`.

## Volume management & permissions

Two bind-mounted directories are expected:

- `./data` → `/app/data`
- `./config` → `/app/config`

The `scripts/prepare-volumes.sh` helper ensures both directories exist and are
writable. If you require the container to run under a different UID/GID, set the
following variables before building:

```bash
echo "APP_UID=$(id -u)" >> .env
echo "APP_GID=$(id -g)" >> .env
```

Then rebuild the image (`docker compose build`). If the host directories were
already created, you may also need to adjust ownership manually:

```bash
sudo chown -R <uid>:<gid> data config
```

## Development notes

- To run the application without Docker, create a virtual environment, install
  `requirements.txt`, and start Uvicorn manually:

  ```bash
  python -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.txt
  uvicorn app.main:app --reload
  ```

- Update `frontend/dist` with your actual compiled frontend build so it is
  bundled automatically into the container image.

- Place environment-specific configuration files under `config/` or supply them
  via the mounted volume at runtime.

- Additional docker-compose profiles or services (e.g., databases) can be added
  by extending `docker-compose.yml` or creating a `docker-compose.override.yml`.
