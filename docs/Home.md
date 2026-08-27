# CRITR Wiki

CRITR (Change-Request Intake & Triage) nimmt Change- und IT-Requests im Gespräch auf, schreibt den Steckbrief und legt ihn **zuerst lokal** an. Jira ist nur Sync-Ziel.

```
Idee → kurzer Satz → KI-Steckbrief → Review → lokal anlegen → Jira-Sync
```

Die KI formuliert Beschreibung, Nutzen, Problem, Lösung und Risiken aus dem Freitext. Sie erfindet keine Zahlen, Systeme oder Namen. Nachgefragt werden höchstens wenige Pflichtfakten (Zeitraum, Auftraggeber, Gesellschaft).

## Seiten

- [Architektur](Architektur.md) — Schichten, Wahrheit, Outbox
- [Intake](Intake.md) — Dialog, Arten, Feld-Besitzer
- [Konfiguration](Konfiguration.md) — YAML, Wissensbasis, Settings
- [Betrieb](Betrieb.md) — Lokal, Docker, Kubernetes, Tests
- [Sicherheit](Sicherheit.md) — Secrets, Auth-Stand, Checkliste
- [Roadmap](Roadmap.md) — Nächste Schritte (GitHub Project)

Quellcode und Setup: [README im Repository](https://github.com/justin-Koehler/Triage).
