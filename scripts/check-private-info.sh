#!/usr/bin/env bash
# Fails if a tracked file contains something that identifies a private setup:
# private/Tailscale IP addresses, *.ts.net hostnames, or real Alexa skill/device IDs.
# Documentation uses placeholders (music.example.com, amzn1.ask.skill.xxxx...) instead.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

patterns=(
  '\b192\.168\.[0-9]{1,3}\.[0-9]{1,3}\b'                     # home LAN
  '\b10\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\b'               # private range
  '\b172\.(1[6-9]|2[0-9]|3[01])\.[0-9]{1,3}\.[0-9]{1,3}\b'   # private range
  '\b100\.(6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7])\.[0-9]{1,3}\.[0-9]{1,3}\b'  # Tailscale CGNAT
  '[a-z0-9-]+\.[a-z0-9-]+\.ts\.net'                          # a real tailnet name
  'amzn1\.ask\.skill\.[0-9a-f]{8}-[0-9a-f]{4}-'              # a real skill ID (UUID form)
  'amzn1\.ask\.device\.[A-Z0-9]{20,}'                        # a real device ID
)

found=0
for p in "${patterns[@]}"; do
  # placeholders used in the docs are allowed
  if git grep -nIE "$p" -- . ':!scripts/check-private-info.sh' ':!uv.lock' \
    | grep -vE 'your-tailnet\.ts\.net'; then
    found=1
  fi
done
if [ "$found" -ne 0 ]; then
  echo "::error::Private details found above. Replace them with placeholders." >&2
  exit 1
fi
echo "No private details found."
