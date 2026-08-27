# Wissensbasis: gelöste Changes

Markdown-Fälle in `tickets/` nutzt CRITR für ähnliche Lösungen und Aufwand.

Eigene Exporte hier ablegen. Personen-, Kosten- und Projektdaten nicht ins Git
committen (siehe `.gitignore`).

## Frontmatter

| Feld | Pflicht | Bedeutung |
|---|---|---|
| `id` | ja | Stabile Kennung |
| `title` | ja | Einzeiler |
| `kind` | nein | `change_request` / `it_request` |
| `service` | nein | Thema-Slug (`prozess`, `software`, `sap`, …) |
| `status` | nein | Nur `solved` zählt |
| `effort_fb` / `effort_it` | nein | Personentage |
| `duration` | nein | z. B. `ca. 6 Wochen` |

Ein einzelnes Randstichwort zieht keinen Fall. Beispiel: `tickets/EXAMPLE-urlaubsantraege.md`.
