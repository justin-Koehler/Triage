# Intake

Der Chat ist die Erfassung, kein Formular. Ein kurzer Satz reicht. Die KI schreibt die Beschreibung und schlägt Nutzen, Problem, Lösung und Risiken vor.

## Ablauf

1. Satz eingeben (kein Autor, kein Vorgangstyp, kein leeres Beschreibungsfeld abfragen).
2. KI-Beschreibung + Übersicht. Nutzer kann korrigieren.
3. Höchstens wenige Dialog-Fragen für Lücken, die sich nicht aus dem Text ergeben.
4. Review, dann lokal anlegen, danach optional Jira-Sync.

## Arten

| Art | Wann |
|---|---|
| **IT Request** | IT muss fachlich mitmachen (Systeme, Software, Zugänge, Betrieb, Hardware). |
| **Change Request** | Organisation, Prozess, Kommunikation, Kultur — ohne technische IT-Umsetzung. |

Die Art kommt zuerst vom Modell, Keywords nur als Fallback.

## Wer füllt welches Feld

Gesteuert über `fill` in `config/triage_rules.yaml`:

| `fill` | Wer | Chat |
|---|---|---|
| `dialog` | Zeitraum, Auftraggeber, Gesellschaft | ja, budgetiert |
| `draft` | KI-Vorschlag (Beschreibung, Nutzen, …) | nie fragen |
| `workspace` | Hub nach der Anlage | nie |
| `controlling` | Controlling im Hub | nie |
| `computed` | `app/domain/calc.py` | nie |

Autor und Bearbeiter kommen aus dem Login, nicht aus dem Dialog. Jira-Assignee = angemeldete Person.

## Status nach der Anlage

Status-Updates sind PLAN/IST-Berichte im Workspace, kein zweiter Chat. QG-Stufen (Steckbrief → QG1 → QG2 → Freigabe → Umsetzung) sind Prozess, keine Workflow-Engine.
