# syntax=docker/dockerfile:1

FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./

RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt


FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="${VIRTUAL_ENV}/bin:${PATH}"
ENV STATIC_ROOT=/app/static

ARG APP_USER=appuser
ARG APP_UID=1000
ARG APP_GID=1000

RUN if ! getent group "${APP_GID}" >/dev/null; then \
      groupadd --gid "${APP_GID}" "${APP_USER}"; \
    fi \
    && if ! id -u "${APP_USER}" >/dev/null 2>&1; then \
      useradd --uid "${APP_UID}" --gid "${APP_GID}" --create-home "${APP_USER}"; \
    fi

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app

RUN mkdir -p /app/app /app/static /app/config /app/data \
    && chown -R ${APP_USER}:${APP_USER} /app

COPY --chown=${APP_USER}:${APP_USER} app /app/app
COPY --chown=${APP_USER}:${APP_USER} frontend/dist /app/static
COPY --chown=${APP_USER}:${APP_USER} config /app/config
COPY --chown=${APP_USER}:${APP_USER} requirements.txt /app/requirements.txt

USER ${APP_USER}

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=2)" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
