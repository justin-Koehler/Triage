# Deploy-Reihenfolge (Kurz):
#
# 1. Image bauen und in die Registry pushen (Tag = Git-SHA, kein latest)
# 2. Secret anlegen (siehe secret.example.yaml)
# 3. Image-Tag in app.yaml / kustomization setzen
# 4. kubectl apply -k k8s/
#
# Managed Postgres der Plattform: StatefulSet weglassen, nur DATABASE_URL im Secret.
#
# Auth/SSO und Host-Härtung folgen später — Manifeste sind vorbereitet.
