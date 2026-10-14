# Veröffentlichung und Updates

## Erster GitHub-Push

Das Git-Repository in diesem Ordner ist für
`https://github.com/firebreakHD/HermesAI` vorgesehen. Erstelle auf GitHub
ein leeres öffentliches Repository mit diesem Namen und lade den lokalen
`main`-Branch hoch:

```sh
git push -u origin main
```

Warte auf den erfolgreichen GitHub-Actions-Build. Anschließend den Release-Tag
für die Versionsnummer setzen:

```sh
git tag v2.0.0
git push origin v2.0.0
```

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
3. Auf `main` committen und einen passenden Tag wie `v2.0.1` pushen.
4. Nach erfolgreichem GitHub-Action-Build den Home-Assistant-Add-on-Store neu
   laden. Die höhere Versionsnummer macht das Update sichtbar.

`hermes update` im Terminal aktualisiert nur die persistente Hermes-Laufzeit
und ändert die Add-on-Version nicht.
