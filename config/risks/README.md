# Risikomuster

Pro Muster eine Markdown-Datei. Match über Stichwörter im Nutzertext.
Treffer → Warnung im Chat und Eintrag in `risks_obstacles`. Keine Extra-Frage.

Maßnahmen kommen aus dem Muster, ergänzt um die Lösung ähnlicher Fälle.

## Frontmatter

| Feld | Pflicht | Bedeutung |
|---|---|---|
| `name` | ja | Kurzname |
| `match` | ja | Stichwörter |
| `display` | nein | Anzeige in der Warnung |

Abschnitte: `## Risiko`, `## Maßnahmen`.
