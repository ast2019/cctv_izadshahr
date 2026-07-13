#!/usr/bin/env bash
# Quick verify login (run on server as root from repo dir)
PASS="${1:?password required}"
PORT="${2:?port required}"
TOKEN=$(curl -sk -X POST "https://127.0.0.1:${PORT}/api/login" \
  -H 'Content-Type: application/json' \
  -d "{\"user\":\"admin\",\"password\":\"${PASS}\"}" -c - | awk '/frigate_token/ {print $7}')
echo "port ${PORT}: token ${#TOKEN} chars"
curl -sk "https://127.0.0.1:${PORT}/api/users" -H "Authorization: Bearer ${TOKEN}"
echo
