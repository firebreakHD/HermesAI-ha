# Verwendete Projekte

Das Add-on lädt beim Image-Build die folgenden Projekte. Ihre Quelltexte
werden nicht in diesem Git-Repository abgelegt.

| Projekt | Version im initialen Image | Lizenz |
| --- | --- | --- |
| [Hermes Agent](https://github.com/NousResearch/hermes-agent) | Commit `0e427d788d253630d38a3a51cd76849e73cd6925` | [MIT](https://github.com/NousResearch/hermes-agent/blob/main/LICENSE) |
| [Hermes WebUI](https://github.com/nesquena/hermes-webui) | Tag `v0.52.76` | [MIT](https://github.com/nesquena/hermes-webui/blob/master/LICENSE) |
| [ttyd](https://github.com/tsl0922/ttyd) | `1.7.7` | [MIT](https://github.com/tsl0922/ttyd/blob/1.7.7/LICENSE) |

Die Lizenzen von Hermes Agent und WebUI bleiben in ihren Checkouts im Image.
Die ttyd-Lizenz wird nach `/usr/share/doc/ttyd/LICENSE` kopiert.
