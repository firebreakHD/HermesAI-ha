#!/bin/sh
# Both the native agent-browser tool and the Bot Screen dock use this executable.
exec /usr/bin/chromium --restore-last-session "$@"
