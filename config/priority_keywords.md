---
# Ohne Treffer gilt die default_priority der Anliegen-Art aus triage_rules.yaml.
default: null
---

# Prioritäten-Keywords

Ein Treffer setzt die Priorität. Die höchste getroffene Stufe gewinnt, `critical`
schlägt also `high`. Mehrwortige Einträge werden als Teilstring gesucht,
einzelne Wörter nur als ganzes Wort.

## critical

- gesetzliche frist
- go-live steht
- produktion steht
- nichts geht mehr
- keiner kann arbeiten
- datenschutzvorfall
- sicherheitsvorfall
- notfall

## high

- dringend
- eilig
- sofort
- eskalation
- eskaliert
- frist
- deadline
- heute noch
- bis morgen
- go-live
- einführungstermin
- rollout-termin
- schulungstermin
- ganze abteilung

## medium

- verbesserung
- wunsch
- nächste woche
- mittelfristig
- prozess
- digitalisieren
- umstellung

## low

- kleinigkeit
- kosmetik
- irgendwann
- nice to have
- wenn zeit ist
- kein termindruck
- niedrige priorität
