#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
test -f .env || { echo "copy .env.example to .env and fill every required value" >&2; exit 1; }
case "${1:-}" in down|rm) echo "destructive compose operations are intentionally blocked" >&2; exit 1;; esac
exec docker compose --env-file .env -f compose.yaml "$@"
