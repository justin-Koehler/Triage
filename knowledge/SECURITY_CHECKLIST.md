# 🔒 Security Checklist — Cloud Deployment (Ubuntu VM + Docker)

> **Für Coding Agents:** Diese Checkliste ist verbindlich bei jedem neuen Deployment, jeder Dockerfile-Änderung und jedem Dependency-Update. Alle Punkte müssen geprüft und bestätigt werden.

---

## 1. 🖥️ Host-Härtung (Ubuntu VM)

### SSH
- [ ] SSH Key Authentication aktiviert (`PasswordAuthentication no` in `/etc/ssh/sshd_config`)
- [ ] Root-Login deaktiviert (`PermitRootLogin no`)
- [ ] SSH Rate Limiting aktiv (`ufw limit 22`)

### Firewall (UFW)
- [ ] Default: alle eingehenden Verbindungen geblockt (`ufw default deny incoming`)
- [ ] Default: alle ausgehenden Verbindungen erlaubt (`ufw default allow outgoing`)
- [ ] Nur folgende Ports offen: **22, 80, 443**
- [ ] UFW aktiviert (`ufw enable`)

### System
- [ ] System aktualisiert (`apt update && apt upgrade`)
- [ ] Automatische Security-Updates aktiviert (`unattended-upgrades`)
- [ ] Monitoring installiert: **Auditd** oder **Falco** für Container-Aktivitäten

---

## 2. 🐳 Docker Netzwerk

### Netzwerk-Topologie
- [ ] Kein Default-Bridge-Netzwerk verwendet
- [ ] Separate Netzwerke nach Vertrauenszonen:

```
Internet
    │ (nur 80/443)
    ▼
  [Caddy]  ── proxy_network
               │
           [Frontend] ── frontend_network
                             │
                          [API] ── backend_network
                                       │
                                 [Postgres]
                                 [Redis]
```

- [ ] Caddy ist der **einzige** nach außen exponierte Container
- [ ] Postgres und Redis sind **nicht** im selben Netzwerk wie Frontend
- [ ] Kein Container hat direkten Zugriff auf `/var/run/docker.sock`

### Docker Compose Beispiel
```yaml
networks:
  proxy_network:
    driver: bridge
  frontend_network:
    driver: bridge
  backend_network:
    driver: bridge

services:
  caddy:
    networks:
      - proxy_network
    ports:
      - "80:80"
      - "443:443"

  frontend:
    networks:
      - proxy_network
      - frontend_network

  api:
    networks:
      - frontend_network
      - backend_network

  postgres:
    networks:
      - backend_network

  redis:
    networks:
      - backend_network
```

---

## 3. 📦 Dockerfile

### Base Image
- [ ] Kein `latest` Tag — immer gepinnte Version (`node:22.13.1-alpine`)
- [ ] Alpine-basiertes Image bevorzugen (minimale Angriffsfläche)
- [ ] Base Image mit `trivy` auf CVEs gescannt

### Multi-Stage Build
- [ ] Multi-Stage Build verwendet (Builder vs. Runner)
- [ ] Finales Image enthält **keine** Dev-Dependencies, Build-Tools oder Secrets

### User
- [ ] Runner-Stage startet mit `USER node` (nie als root)
- [ ] `WORKDIR` gesetzt

### Dependencies
- [ ] `npm ci` statt `npm install` (reproduzierbare Builds)
- [ ] `package-lock.json` ist im Repository committed

### Secrets
- [ ] Keine Secrets via `ENV` oder `ARG` im Dockerfile
- [ ] Secrets werden via Docker Secrets oder Environment-Injection zur Laufzeit übergeben
- [ ] `docker history image:tag` zeigt keine Secrets

### Filesystem & Capabilities
- [ ] `read_only: true` in docker-compose gesetzt
- [ ] `tmpfs` für Verzeichnisse die schreiben müssen:
```yaml
tmpfs:
  - /tmp
  - /app/.next/cache
```
- [ ] `--cap-drop=ALL` gesetzt, nur benötigte Capabilities explizit hinzufügen
- [ ] `--security-opt=no-new-privileges` gesetzt

### Dockerfile Vorlage (NextJS)
```dockerfile
# Stage 1: Builder
FROM node:22.13.1-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# Stage 2: Runner
FROM node:22.13.1-alpine AS runner
WORKDIR /app
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/package*.json ./
RUN npm ci --only=production
USER node
CMD ["node", "server.js"]
```

---

## 4. 📚 App & Dependencies

### Lokale Prüfung (vor jedem Commit)
- [ ] `npm audit` ausgeführt — keine HIGH oder CRITICAL Vulnerabilities
- [ ] `trivy image myimage:latest` ausgeführt — keine CRITICAL Vulnerabilities

### CI/CD Pipeline
- [ ] Trivy Scan in Pipeline integriert mit `--exit-code 1` bei CRITICAL:
```yaml
- name: Scan Docker Image
  run: trivy image --exit-code 1 --severity CRITICAL myimage:latest
```
- [ ] Pipeline schlägt fehl bei kritischen CVEs — kein Deployment möglich
- [ ] Dependabot aktiviert für automatische Dependency-Updates:
```yaml
# .github/dependabot.yml
version: 2
updates:
  - package-ecosystem: "npm"
    directory: "/"
    schedule:
      interval: "weekly"
```

### Supply Chain
- [ ] Keine unbekannten Base Images von unverifizierten Quellen
- [ ] Typosquatting-Check bei neuen Paketen (z.B. `reqeusts` statt `requests`)
- [ ] `postinstall` Scripts in `package.json` auf Schadcode geprüft

---

## 5. 🚨 Angriffsvektoren — Awareness

| Angriffsvektor | Gegenmaßnahme |
|---|---|
| Container läuft als root | `USER node` in Dockerfile |
| Container Escape | `--cap-drop=ALL`, `no-new-privileges` |
| Docker Socket exposed | Niemals `-v /var/run/docker.sock` mounten |
| Lateral Movement im Netzwerk | Separate Docker-Netzwerke |
| Secrets im Image Layer | Multi-Stage Build, keine ENV-Secrets |
| Kompromittierte Dependency | `npm audit`, Trivy, Dependabot |
| Brute-Force SSH | SSH Keys, `ufw limit 22` |
| Ungepatchtes System | `unattended-upgrades` |
| Schadcode via RCE nachgeladen | `read_only: true`, `tmpfs` |

---

## ✅ Pre-Deployment Sign-off

Vor jedem Deployment müssen folgende Befehle erfolgreich ausgeführt worden sein:

```bash
# 1. Dependency Scan
npm audit

# 2. Image bauen
docker build -t myapp:latest .

# 3. Image scannen
trivy image --exit-code 1 --severity CRITICAL myapp:latest

# 4. Firewall prüfen
ufw status verbose

# 5. Container nicht als root
docker inspect myapp:latest | grep User
```

> ⚠️ **Kein Deployment ohne grüne Checks.**
