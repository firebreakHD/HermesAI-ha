# Hermes Assistant

Hermes Agent für Home Assistant mit der bekannten Hermes WebUI und einem
integrierten Setup-Terminal. Die aktuelle offizielle Hermes-Version wird beim
ersten Start installiert und kann anschließend im Terminal mit
`hermes update` aktualisiert werden.

Der authentifizierte Hermes API Server verbindet JARVIS mit demselben Agenten.
Home-Assistant-Zugriff, MCP, beobachtete Entities und der Codex-Login per
`hermes auth add openai-codex --browser` sind vorbereitet.

Die bestehende Beeper-Linux-Installation unter `/data/hermes/beeper-cli/`
startet auf einem eigenen persistenten Bildschirm und ist ausschließlich über
**Werkzeuge → Beeper Linux** im authentifizierten Home-Assistant-Ingress erreichbar.
Anmeldung, Geräteprüfung und Chat-Konten bleiben manuell.

Vor dem Start einen starken `api_server_key` in den Optionen eintragen. Die
vollständige Einrichtung steht in [DOCS.md](DOCS.md).
