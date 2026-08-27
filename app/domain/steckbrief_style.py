"""Länge und Stil für Steckbrief-Prosa."""

from __future__ import annotations

# Harte Caps beim Speichern/Clippen (etwas über dem typischen Maximum).
CLIP = {
    "description": 700,
    "benefit": 280,
    "reason": 450,
    "solution": 700,
    "risks": 500,
}

# Default für clip_tight, wenn kein Feld angegeben.
DEFAULT_CLIP = 450

STECKBRIEF_STYLE = """Vorbild: interne Change-Steckbriefe, sachlich, ohne Marketing.

Länge und Inhalt:
- Beschreibung: 200–450 Zeichen, was der Change ist und worum es geht.
  Kontext, betroffene Bereiche, Phasen/Abgrenzung erlaubt.
- Nutzen: kurz die Wirkung (Qualität, Risiko, Aufwand, Strategie), 80–220 Zeichen.
- Problem/Begründung: ein dichter Absatz, typisch 100–350 Zeichen.
  Ist-Schmerz konkret, ohne Nutzen oder Maßnahme zu wiederholen.
- Lösung/Ziele: oft länger, 200–550 Zeichen. Was eingeführt wird, Ziele,
  ggf. Abgrenzung (NICHT-Ziel). Aufzählungen in Prosa ok.
- Risiken: konkret benannt, typisch 80–350 Zeichen. Keine Floskeln.

Ton: intern, sachlich, wie in der Akte.
Geschlechtssprache: immer geschlechtsneutral (Mitarbeitende, Personen, Leitung).
Rechtschreibung: deutsche Orthografie mit Umlauten und ß
(Maßnahme, Einführung, weiß, ausschließlich — nicht Massnahme/Einfuehrung/weiss).
Keine Broschüre, keine erfundenen Zahlen/Systeme.
"""

# Kurze Beispiele für Prompt-Orientierung.
EXAMPLES = """Beispiele im Stil der Steckbriefe:

Beschreibung (~200 Z.):
„Urlaubsanträge sollen digital erfasst werden statt auf Papier. Führungskraft
und Personal geben frei; der Resturlaub kommt aus dem Personalsystem.“

Problem (~180 Z.):
„Auf Papier fehlt der Stand. Anträge gehen verloren, Nachfragen sind Normalfall.
Die Personalabteilung pflegt Resturlaub parallel in einer eigenen Datei.“

Lösung (~220 Z.):
„Digitales Formular mit zweistufiger Freigabe. Resturlaub kommt aus dem
Personalsystem. NICHT-Ziel: vollautomatische Genehmigung ohne Prüfung.“

Risiken (~120 Z.):
„Führung bleibt auf Papier, wenn der alte Weg offen bleibt. Löschkonzept
und Betriebsrat vor Go-Live klären.“
"""
