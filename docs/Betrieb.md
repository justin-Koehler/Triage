# Betrieb

## Lokal

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8787
```

App: http://127.0.0.1:8787 · Settings: `/settings`

SQLite unter `data/` (gitignored). Schema in Dev: `create_all`; Compose/K8s: Alembic beim Start.

## Tests

```bash
pytest tests/unit
pytest tests/contract
ruff check .
```

`pytest -m eval` braucht ein LLM. CI läuft ohne Live-Modell (`pip audit`, Image-Build, Trivy).

## Docker Compose

```bash
cp deploy/compose.env.example deploy/compose.env
# SESSION_SECRET, SETTINGS_ENCRYPTION_KEY, POSTGRES_PASSWORD setzen
docker compose --env-file deploy/compose.env up --build -d
```

Caddy ist der einzige Host-Port (80/443). App und Postgres intern. Image-Tag in Prod = Git-SHA, nicht `latest`.

## Kubernetes

Vorlagen unter `k8s/`:

1. Image bauen und pushen (Tag = Git-SHA)
2. Secret aus `k8s/secret.example.yaml` (Werte nicht committen)
3. Image-Tag in `k8s/app.yaml` setzen
4. `kubectl apply -k k8s/`

Host und TLS am Ingress an die eigene Plattform anpassen. Managed Postgres: StatefulSet weglassen, nur `DATABASE_URL` im Secret.
