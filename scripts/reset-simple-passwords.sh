#!/bin/bash
set -euo pipefail
cd /home/rootuser/cctv_izadshahr

OLD_ADMIN='Admin@1405!'
NEW_ADMIN='CctvAdmin1405'
CEO_PASS='Cctv1405'

for port in 8972 8973; do
  echo "=== port $port ==="
  TOKEN=$(curl -sk -X POST "https://127.0.0.1:${port}/api/login" \
    -H 'Content-Type: application/json' \
    -d "{\"user\":\"admin\",\"password\":\"${OLD_ADMIN}\"}" -c - | awk '/frigate_token/ {print $7}')
  if [[ -z "$TOKEN" ]]; then
    TOKEN=$(curl -sk -X POST "https://127.0.0.1:${port}/api/login" \
      -H 'Content-Type: application/json' \
      -d "{\"user\":\"admin\",\"password\":\"${NEW_ADMIN}\"}" -c - | awk '/frigate_token/ {print $7}')
  fi
  [[ -n "$TOKEN" ]] || { echo "  FAIL admin login"; continue; }
  curl -sk -X PUT "https://127.0.0.1:${port}/api/users/admin/password" \
    -H "Authorization: Bearer ${TOKEN}" -H 'Content-Type: application/json' \
    -d "{\"password\":\"${NEW_ADMIN}\"}" >/dev/null
  TOKEN=$(curl -sk -X POST "https://127.0.0.1:${port}/api/login" \
    -H 'Content-Type: application/json' \
    -d "{\"user\":\"admin\",\"password\":\"${NEW_ADMIN}\"}" -c - | awk '/frigate_token/ {print $7}')
  curl -sk -X PUT "https://127.0.0.1:${port}/api/users/ceo/password" \
    -H "Authorization: Bearer ${TOKEN}" -H 'Content-Type: application/json' \
    -d "{\"password\":\"${CEO_PASS}\"}" >/dev/null
  echo "  passwords updated"
done

for user in admin ceo; do
  if [ "$user" = admin ]; then pass="$NEW_ADMIN"; else pass="$CEO_PASS"; fi
  for path in cafe center11; do
    code=$(curl -sk -o /dev/null -w '%{http_code}' -X POST "http://127.0.0.1:8888/${path}/api/login" \
      -H 'Content-Type: application/json' -d "{\"user\":\"${user}\",\"password\":\"${pass}\"}")
    echo "$user @ $path => $code"
  done
done
