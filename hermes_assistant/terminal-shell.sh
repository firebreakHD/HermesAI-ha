#!/usr/bin/env bash

cd /data/hermes || exit 1
printf '%s\n' \
  'Hermes setup terminal' \
  '─────────────────────' \
  'hermes setup                           Configure a provider' \
  'hermes auth add openai-codex --browser Add a Codex account with browser login' \
  'hermes model                           Select provider/model' \
  'hermes update                          Update Hermes Agent' \
  'hermes --help                          Show all commands'
exec bash
