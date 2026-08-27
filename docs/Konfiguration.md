# Konfiguration

Nichts davon ins Git, was Geheimnisse, echte Personen oder echte Vorhaben enthält. `.env` und `deploy/compose.env` sind gitignored.

## Dateien

| Datei / Ordner | Zweck |
|---|---|
| `config/triage_rules.yaml` | Pflichtfelder, Fragen, `fill`, Gesellschaften |
| `config/field_map.yaml` | Domain → Jira (nur der Adapter liest das) |
| `config/responsibles/` | Zuständigkeit per Keywords (eine Datei pro Rolle) |
| `config/priority_keywords.md` | Dringlichkeit per Treffer |
| `config/topics/` | Diagnose-Fragen pro Thema |
| `config/risks/` | Risiko-Muster aus Stichwörtern |
| `config/rates.yaml` | Tagessätze für die Kalkulation |
| `knowledge/tickets/` | Gelöste Fälle als Markdown (eigene Exporte, nicht committen) |
| `.env` / Settings-Tab | LLM, Jira, Session-Secret |

Jira-Projektkey und Custom-Field-IDs in der Vorlage sind Platzhalter. Lokal die eigenen Werte setzen.

## Runtime

LLM und Jira-Zugang lassen sich im Tab **Einstellungen** speichern (verschlüsselt in der DB). Env-Werte sind Fallback. `TICKET_PORT=fake` braucht kein Jira.

Wissensbasis: Frontmatter `id`, `title`, `kind`, `status: solved`. Ein einzelnes Randstichwort zieht keinen Fall.
