# Sicherheit

## Secrets

- `.env`, `deploy/compose.env` und echte K8s-Secrets nie committen.
- Produktiv `SESSION_SECRET` und `SETTINGS_ENCRYPTION_KEY` setzen (nicht die Dev-Defaults).
- LLM- und Jira-Tokens nur in Settings oder Secret-Store.

## Auth (aktueller Stand)

Dev-Login über Jira-Assignable-User (exakter Name). Das ist ein Gate für den Pilot, kein SSO. Settings schreiben nur angemeldete Nutzer. SSO/OIDC ist geplant, siehe [Roadmap](Roadmap.md).

Bis SSO:

- Nicht ins offene Internet stellen.
- Session-Cookie härten (Secure, SameSite), sobald TLS steht.

## Container

Non-root Image, `read_only`, `cap_drop: ALL`, `no-new-privileges`, getrennte Netze (Proxy / Backend). Caddy allein nach außen. Kein Docker-Socket-Mount.

Checkliste im Repo: `knowledge/SECURITY_CHECKLIST.md` (Host-Härtung, Firewall, Updates — wenn ein Server da ist).
