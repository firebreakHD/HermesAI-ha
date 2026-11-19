# B1 – lokale Build-Prüfung (19. November 2026)

## Umfang
Lokales Repository `/root/workspace/hermesai-ha-b1`, Ausgangs-Commit `f3a796ec1f24241b0fbe440df721d02885222975`. Keine Änderungen an laufenden Dateien, kein Add-on-Update oder Dienstneustart. Die B1-Sicherung `/data/hermes/backups/b1-before-20261119T120703/` bleibt erhalten.

Versionierte Dateien: `b1/b1.patch` (Änderungen an WebUI `api/auth.py`, `server.py`), `b1/files/api/ha_person.py`, `b1/files/tests/test_ha_person_assignment.py`, `b1/base-commit`, `b1/apply.py`, `b1/README.md`, `tests/test_b1_delivery.py` sowie Anpassungen an `run.sh`, `nginx.conf`, `Dockerfile`. Die beiden neuen WebUI-Dateien sind bytegleich mit den vorbereiteten Dateien im installierten Checkout; der Patch wurde isoliert gegen dessen Commit `6ea12c1548d54095b1fe6f63f799bca61708ef44` angewendet.

## Prüfungen und Grenzen
- Sieben isolierte Delivery-Tests bestanden: sauberer Checkout, idempotente Wiederholung, bereits vorbereiteter Dirty-Stand, kompatibles Upstream-Staging und Austausch, inkompatibles Upstream-Staging ohne Austausch, fremde Dirty-Änderung ohne Verlust sowie unterschiedliche Git-Hash-Abkürzungen. Testquelle ist eine Kopie des installierten WebUI-Checkouts, keine Live-Migration.
- Fünf Zuordnungstests bestanden (zwei IDs, unbekannte/ungültige Zuordnung, CSRF, untrusted Peer, Profilbindung). Ein realer HA-Ingress-Fluss wurde nicht getestet.
- `bash -n hermes_assistant/run.sh`, `nginx -t -c <lokaler Pfad>`, `python3 -m py_compile` und `git diff --check` bestanden. Nginx meldet zwei vorhandene Warnungen über doppelte MIME-Typen.
- Kein lokaler Docker-Build im HAOS-Add-on: dort fehlen `docker`, `podman`, `buildah`, `buildctl` und ein Docker-/Podman-Socket. Der spätere isolierte GitHub-Actions-Build ist unten dokumentiert.

## Start und Integrationen
Der B1-Patcher läuft vor dem WebUI-Start. Bei Inkompatibilität setzt `run.sh` `WEBUI_READY=false`, überspringt WebUI-Abhängigkeiten und WebUI-Startschleife; die Gateway-Schleife und separat gestarteten Nextcloud-Talk-, Browser-, Beeper- und Terminal-Prozesse bleiben im Skript erhalten. Die Profilkonfigurationen, Codex-Anmeldung, Google-/HA-Integrationen und Cronjobs werden nicht geändert. Das ist eine statische Startpfadprüfung, **kein** Laufzeitnachweis für diese Dienste nach einem neuen Image.

Der bisherige Docker-Healthcheck auf `/health` wäre nach Ingress-Sperre ein HTTP 403. Der lokale Dockerfile-Healthcheck erwartet daher 403 am lokalen Nginx-Zugang und prüft nur Nginx-Verfügbarkeit; er ersetzt **keine** WebUI-, Gateway- oder Integrations-Gesundheitsprüfung. Sein HTTP-Verhalten wurde im isolierten CI-Container gemessen (HTTP 403, Docker-Status healthy), aber nicht im produktiven HAOS-Add-on. Bei WebUI-Fail-Closed ist ein 502 auf der WebUI-Route zu erwarten, nicht für die getrennten Ingress-Routen.

## GitHub Actions – isolierter Build
Entwicklungsbranch `feature/b1-ha-ingress`, Workflow `.github/workflows/b1-isolated.yml`. Run `44522591144` für Commit `b09e2a1` ist **completed/success**: B1-Tests auf frischem Upstream-Checkout, Docker-Build ohne Veröffentlichung, Prüfung der eingebauten B1-Dateien und vorhandener Browser-/Talk-/Beeper-Binaries sowie Nginx-Syntax bestanden. Ein isoliert gestarteter Nginx-Container erreichte Docker-Healthstatus `healthy`; lokale `/health`- und `/browser/`-Aufrufe wurden erwartungsgemäß mit HTTP 403 abgewiesen. Frühere fehlgeschlagene Runs `44519967445`, `44520216868`, `44521503223`, `44522045279` betrafen CI-Pfad, Git-Diff-Hash-Abkürzung, partiellen Git-Klon und einen nicht im PATH liegenden Nginx-Befehl; die Fehler wurden auf dem Branch korrigiert. Die CI baut ein amd64-Testimage, pusht **kein** GHCR-Image und aktiviert **kein** HAOS-Add-on. Ein kompletter `/run.sh`-Start mit Supervisor/HAOS, FRIDAY, Talk, Beeper, Browser und zwei echten HA-Konten ist weiterhin offen.

## Späterer Installationsweg – nur nach neuer Freigabe
1. Auf einer Docker-fähigen Maschine aus dem lokalen Commit ein Add-on-Image mit dem vorhandenen `hermes_assistant/Dockerfile` und den B1-Dateien bauen; prüfen, dass `/opt/hermes-b1` enthalten ist, Healthcheck und Startpfad isoliert ausführen, beide HA-Identitäten erst im freigegebenen Ingress-Test prüfen. Keine Secrets in Build-Kontext oder Testlogs übernehmen.
2. Freigegebenen Build über die bestehende Add-on-Repository-/Image-Pipeline bereitstellen; nötige Versions-/Image-Referenzen erst dann aktualisieren. Kein paralleler Hermes-Gateway. Vorher die bestehende B1-Sicherung sowie den persistierten WebUI- und HA-Datenstand prüfen und einen konkreten Rückweg vereinbaren.
3. Add-on-Update/Neustart und Ingress-Test mit zwei HA-Konten erst nach gesonderter Freigabe. Prüfen: Zuordnung, JARVIS/FRIDAY, Talk, Beeper, Browser, vorhandene Integrationen und Healthcheck. Bei Fehler zurück zum vorherigen Add-on-Image; WebUI-Checkout anhand `b1/README.md` und der Sicherung wiederherstellen, Zuordnungsdatei nicht blind löschen.

Risiko: Bereits mit B1 geänderte Checkouts überspringen automatische WebUI-Updates absichtlich; ein neuer Upstream-Stand braucht eine saubere, freigegebene Migration. `webui-app.b1-previous` blockiert weitere Staging-Updates bis zur manuellen Prüfung. FRIDAY-Gesprächslisten sind weiterhin keine Vertraulichkeitsgrenze.
