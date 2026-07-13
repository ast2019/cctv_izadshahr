#!/bin/bash
set -euo pipefail
cd /home/rootuser/cctv_izadshahr

ADMIN_PASS='tiw73TC67fxP5GqnEi6Mnltcg'
CEO_PASS='Ceo@1405!'

for port in 8972 8973; do
  echo "=== port $port ==="
  TOKEN=$(curl -sk -X POST "https://127.0.0.1:${port}/api/login" \
    -H 'Content-Type: application/json' \
    -d "{\"user\":\"admin\",\"password\":\"${ADMIN_PASS}\"}" -c - | awk '/frigate_token/ {print $7}')
  echo "admin token len: ${#TOKEN}"
  curl -sk "https://127.0.0.1:${port}/api/users" -H "Authorization: Bearer ${TOKEN}"
  echo
done

echo '=== nginx login log tail ==='
echo '12345@' | sudo -S docker logs cctv-portal 2>&1 | grep -i login | tail -10
