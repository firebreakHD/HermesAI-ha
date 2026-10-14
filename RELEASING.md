# Veröffentlichung und Updates

## Mit GitHub Desktop veröffentlichen

Die Dateien in diesem Ordner sind für
`https://github.com/firebreakHD/HermesAI` vorbereitet. Der lokale Git-Verlauf
wurde entfernt; du erstellst das Repository und den ersten Commit selbst.
In GitHub Desktop:

1. **File → Add local repository** wählen und genau den Ordner `HA_ADDON`
   auswählen. Wenn GitHub Desktop meldet, dass dort noch kein Repository
   vorhanden ist, **Create a repository here** wählen.
2. Alle vorbereiteten Dateien mit **Commit to main** als ersten Commit speichern.
3. **Publish repository** klicken. Als Namen `HermesAI` und als Konto
   `firebreakHD` wählen.
4. **Keep this code private** deaktivieren und veröffentlichen.
5. Unter **Actions** den erfolgreichen Build abwarten.

GitHub Actions baut `amd64` und `aarch64` und veröffentlicht die Images als
`ghcr.io/firebreakhd/amd64-hermes-assistant:2.0.0` und
`ghcr.io/firebreakhd/aarch64-hermes-assistant:2.0.0`. Stelle beide GHCR-Pakete
nach dem ersten erfolgreichen Build auf **Public**. Anschließend kann
`https://github.com/firebreakHD/HermesAI` im Home-Assistant-Add-on-Store als
Repository hinzugefügt werden.

## Neue Add-on-Version

1. Die Versionsnummer in `hermes_assistant/config.yaml` und den
   `BUILD_VERSION`-Standard im Dockerfile erhöhen.
2. Die Änderung in `CHANGELOG.md` und
   `hermes_assistant/CHANGELOG.md` beschreiben.
3. Die Änderungen in GitHub Desktop committen und `main` mit
   **Push origin** hochladen. Der Workflow baut und veröffentlicht die neue
   Versionsnummer automatisch.
4. Nach erfolgreichem GitHub-Action-Build den Home-Assistant-Add-on-Store neu
   laden. Die höhere Versionsnummer macht das Update sichtbar.

`hermes update` im Terminal aktualisiert nur die persistente Hermes-Laufzeit
und ändert die Add-on-Version nicht.
