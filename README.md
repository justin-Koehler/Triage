# CRITR — Change-Request Intake & Triage

CRITR nimmt einen Change oder IT-Request im Gespräch auf, schreibt den Steckbrief und legt ihn zuerst **lokal** an. Jira ist nur Sync-Ziel (Outbox, asynchron). Die eigene Datenbank bleibt die Quelle der Wahrheit.

Die KI formuliert Beschreibung, Nutzen, Problem, Lösung und Risiken aus dem Freitext — ohne Zahlen, Systeme oder Namen zu erfinden. Nachgefragt werden höchstens wenige Pflichtfakten (z. B. Zeitraum, Auftraggeber, Gesellschaft).

```
Idee → kurzer Satz → KI-Steckbrief → Review → lokal anlegen → Jira-Sync
```

Zwei Arten: **Change Request** (Organisation, Prozess, Kommunikation) und **IT Request** (Systeme, Software, Zugänge, Betrieb).

## Voraussetzungen

- Python 3.11+
- optional: Docker, ein LLM (Ollama lokal oder API-Key), Jira nur wenn synchronisiert werden soll

## Lokal starten

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8787
```

- App: http://127.0.0.1:8787
- Einstellungen (LLM, Jira): http://127.0.0.1:8787/settings

Ohne Jira bleibt `TICKET_PORT=fake`. Credentials gehören nur in `.env` oder den Einstellungen-Tab, nie ins Git.

## Was die App macht

1. **Intake** — Dialog füllt den Steckbrief. Die KI schreibt Prosa; der Mensch bestätigt.
2. **Workspace** — Liste, Detail, Status-Updates, Aufwandsschätzung.
3. **Sync** — „In Jira anlegen“ speichert lokal und schickt den Vorgang über die Outbox nach. Der Jira-Key kommt nach.
4. **Wissensbasis** — gelöste Fälle als Markdown unter `knowledge/tickets/` (eigene Exporte, nicht committen).

Feldquellen (`config/triage_rules.yaml`): Dialog (max. wenige Fragen), KI-Entwurf, Workspace, Controlling oder berechnet (`app/domain/calc.py`).

## Konfiguration

| Datei | Zweck |
|---|---|
| `config/triage_rules.yaml` | Pflichtfelder, Fragen, `fill`-Besitzer |
| `config/field_map.yaml` | Mapping auf Jira-Felder (Adapter only) |
| `config/responsibles/` | Zuständigkeit per Keywords |
| `config/topics/`, `config/risks/` | Themenfragen und Risiko-Muster |
| `.env` | Secrets, DB, LLM — gitignored |

Jira-Projekt, Feld-IDs und Login bitte lokal setzen. Die Beispiele im Repo sind Platzhalter.

## Tests

```bash
pytest tests/unit
pytest tests/contract
ruff check .
```

Eval gegen ein Golden Set: `pytest -m eval` (braucht LLM). CI läuft ohne Live-LLM.

## Docker

```bash
cp deploy/compose.env.example deploy/compose.env
# SESSION_SECRET, SETTINGS_ENCRYPTION_KEY, POSTGRES_PASSWORD setzen
docker compose --env-file deploy/compose.env up --build -d
```

Caddy ist der einzige Host-Port (80/443). App und Postgres bleiben intern. Schema: Alembic beim Start.

## Kubernetes

Vorlagen unter [`k8s/`](k8s/). Secret aus `k8s/secret.example.yaml` anlegen, Image-Tag setzen, `kubectl apply -k k8s/`. Host/TLS an die eigene Plattform anpassen.

Auth ist Dev-Login über Jira-Assignable-User; SSO ist nicht Teil dieses Stands.
