# Veröffentlichung und Updates

## Erstinstallation

Das öffentliche Repository ist
`https://github.com/firebreakHD/HermesAI-ha`. Unter **Actions** muss der
Build für die jeweilige Architektur erfolgreich abgeschlossen sein.

GitHub Actions baut `amd64` und `aarch64` und veröffentlicht die Images als
`ghcr.io/firebreakhd/amd64-hermes-assistant:2.0.0` und
`ghcr.io/firebreakhd/aarch64-hermes-assistant:2.0.0`. Stelle beide GHCR-Pakete
nach dem ersten erfolgreichen Build einzeln auf **Public**. Dazu auf GitHub
unter **Profil → Packages** das jeweilige Paket öffnen und unter
**Package settings → Danger Zone → Change visibility → Public** umstellen.
Ein öffentliches Repository allein macht GHCR-Container nicht öffentlich.
Anschließend kann `https://github.com/firebreakHD/HermesAI-ha` im
Home-Assistant-Add-on-Store als Repository hinzugefügt werden.

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
