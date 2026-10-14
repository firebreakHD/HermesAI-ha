# Veröffentlichung und Updates

## Erstinstallation

Das öffentliche Repository ist
`https://github.com/firebreakHD/HermesAI-ha`. Unter **Actions** muss der
Build für die jeweilige Architektur erfolgreich abgeschlossen sein.

GitHub Actions baut `amd64` und `aarch64` und veröffentlicht die Images als
`ghcr.io/firebreakhd/amd64-hermes-assistant:<VERSION>` und
`ghcr.io/firebreakhd/aarch64-hermes-assistant:<VERSION>`. Stelle beide GHCR-Pakete
nach dem ersten erfolgreichen Build einzeln auf **Public**. Dazu auf GitHub
unter **Profil → Packages** das jeweilige Paket öffnen und unter
**Package settings → Danger Zone → Change visibility → Public** umstellen.
Ein öffentliches Repository allein macht GHCR-Container nicht öffentlich.
Anschließend kann `https://github.com/firebreakHD/HermesAI-ha` im
Home-Assistant-Add-on-Store als Repository hinzugefügt werden.

## Neue Add-on-Version

1. Nur `RELEASE_VERSION` auf die nächste Version erhöhen. Die Versionsnummer
   in `hermes_assistant/config.yaml` und den `BUILD_VERSION`-Standard im
   Dockerfile **nicht** von Hand ändern. Diese beiden Werte zeigen immer auf
   eine bereits veröffentlichte Image-Version.
2. Die Änderung in `CHANGELOG.md` und
   `hermes_assistant/CHANGELOG.md` beschreiben.
3. Die Änderungen in GitHub Desktop committen und `main` mit
   **Push origin** hochladen. GitHub Actions baut beide Architekturen und
   prüft, ob beide GHCR-Images ohne Anmeldung abrufbar sind.
4. Erst danach schreibt der Workflow die neue Version in die Add-on-
   Konfiguration und das Dockerfile und pusht diesen Freigabe-Commit nach
   `main`. Dadurch sieht Home Assistant die neue Version erst, wenn ihre
   Images bereitstehen. Nach erfolgreichem Workflow den Add-on-Store neu
   laden und das Update installieren. In GitHub Desktop anschließend
   **Fetch origin** und **Pull origin** ausführen, damit der automatische
   Freigabe-Commit auch lokal vorhanden ist.

Wenn der Workflow beim Freigabe-Commit wegen fehlender Schreibrechte oder
Branch-Schutz stoppt, die GitHub-Actions-Berechtigung für `contents: write`
und die Branch-Regeln prüfen. Die Images können in diesem Fall bereits
vorhanden sein; Home Assistant bietet das Update erst nach dem Freigabe-Commit
an. Ein fehlgeschlagener Build lässt die bisherige Add-on-Version sichtbar.

`hermes update` im Terminal aktualisiert nur die persistente Hermes-Laufzeit
und ändert die Add-on-Version nicht.
