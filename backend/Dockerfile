# JARVIS backend container image (for Hybrid/Remote deployment, ADR-0004).
# The desktop client itself does NOT require Docker.
#
# Build context: the `backend/` directory (see infra/docker-compose.yml).
FROM python:3.12-slim

WORKDIR /srv/jarvis

COPY pyproject.toml ./
COPY app ./app

RUN pip install --no-cache-dir .

EXPOSE 8000

# Default-deny: shell runs nothing unless JARVIS_ALLOWLIST_COMMANDS is set.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]