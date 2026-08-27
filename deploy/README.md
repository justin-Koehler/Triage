# Compose / Container Deploy

## Lokal starten

```bash
cp deploy/compose.env.example deploy/compose.env
# SESSION_SECRET, SETTINGS_ENCRYPTION_KEY, POSTGRES_PASSWORD setzen

docker compose --env-file deploy/compose.env up --build -d
```

Caddy: http://127.0.0.1/  
App intern: `app:8000` · Postgres intern: `postgres:5432`

## Härtung (Checkliste)

- Caddy ist der einzige Host-Port (80/443)
- App: non-root, `read_only`, `cap_drop: ALL`, `no-new-privileges`
- Getrennte Netze: `proxy_network` / `backend_network`
- Kein Docker-Socket-Mount
- Image-Tag in Prod = Git-SHA (`IMAGE_TAG=…`), kein `latest`

## Schema

Beim Start: `alembic upgrade head` (siehe `entrypoint.sh`).

## Später

- TLS in `Caddyfile` oder über K8s Ingress
- SSO/Login
- Host-Härtung der VM
