#!/bin/bash
# Reset Frigate UI passwords (run on server from repo root with sudo docker access)
set -euo pipefail
cd /home/rootuser/cctv_izadshahr

OLD_ADMIN='tiw73TC67fxP5GqnEi6Mnltcg'
NEW_ADMIN='Admin@1405!'
CEO_PASS='Ceo@1405!'

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
  if [[ -z "$TOKEN" ]]; then
    echo "  ERROR: cannot login as admin"
    continue
  fi
  curl -sk -X PUT "https://127.0.0.1:${port}/api/users/admin/password" \
    -H "Authorization: Bearer ${TOKEN}" \
    -H 'Content-Type: application/json' \
    -d "{\"password\":\"${NEW_ADMIN}\"}" >/dev/null
  TOKEN=$(curl -sk -X POST "https://127.0.0.1:${port}/api/login" \
    -H 'Content-Type: application/json' \
    -d "{\"user\":\"admin\",\"password\":\"${NEW_ADMIN}\"}" -c - | awk '/frigate_token/ {print $7}')
  curl -sk -X PUT "https://127.0.0.1:${port}/api/users/ceo/password" \
    -H "Authorization: Bearer ${TOKEN}" \
    -H 'Content-Type: application/json' \
    -d "{\"password\":\"${CEO_PASS}\"}" >/dev/null
  echo "  admin + ceo passwords updated"
  curl -sk -X POST "http://127.0.0.1:8888/cafe/api/login" -H 'Content-Type: application/json' \
    -d "{\"user\":\"admin\",\"password\":\"${NEW_ADMIN}\"}" -o /dev/null -w "  portal test admin: %{http_code}\n" 2>/dev/null || true
done

echo "=== verify new passwords via portal ==="
for user pass in "admin ${NEW_ADMIN}" "ceo ${CEO_PASS}"; do
  set -- $user $pass
  for path in cafe center11; do
    code=$(curl -sk -o /dev/null -w '%{http_code}' -X POST "http://127.0.0.1:8888/${path}/api/login" \
      -H 'Content-Type: application/json' -d "{\"user\":\"$1\",\"password\":\"$2\"}")
    echo "$1 @ $path => $code"
  done
done
