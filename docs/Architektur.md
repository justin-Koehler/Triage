# Architektur

CRITR ist ein FastAPI-Dienst mit statischer UI. Eine SQLite- oder Postgres-Datenbank ist die Quelle der Wahrheit. Jira (oder ein Fake-Port in Tests) hängt nur über eine Outbox dran.

## Schichten

| Schicht | Rolle |
|---|---|
| `static/` | Workspace, Settings, Aufwandstabelle |
| `app/api/` | HTTP: Sessions, Requests, Auth, Settings, Jira-Lookup |
| `app/services/` | Intake, Steckbrief-Felder, Workspace, Aufwand |
| `app/triage/` | Dialog-Engine, LLM-Provider |
| `app/domain/` | Regeln, Text, Kalkulation, Routing |
| `app/ports/` | Ticket-Adapter (Jira REST v3, Fake) |
| `app/sync/` | Outbox: lokal zuerst, Key nachziehen |

## Datenfluss

1. Nutzer schreibt einen Satz im Chat.
2. Die Engine füllt den Draft (Beschreibung und Übersicht per KI, Fakten aus Text und max. wenigen Fragen).
3. Review im Workspace; „Anlegen“ speichert lokal.
4. Ein Outbox-Job läuft im Hintergrund und legt den Vorgang im Ticket-Port an.
5. Der externe Key (z. B. Jira) wird nachgezogen. Fehlt Jira, bleibt der lokale Vorgang gültig.

## Prinzipien

- **Lokal zuerst.** Ohne Fremdsystem gibt es trotzdem einen Steckbrief.
- **Nichts erfinden.** Leere Felder bleiben leer, bis Text oder Nutzer sie füllen.
- **Konfiguration statt Code.** Pflichtfelder, Zuständigkeit und Risiken liegen unter `config/`.
- **Ein Prozess, zwei Arten.** Change Request und IT Request teilen den Steckbrief; IT hat zusätzliche Rollenfelder.
