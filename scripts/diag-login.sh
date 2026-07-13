#!/bin/bash
NEW_ADMIN='Admin@1405!'
CEO_PASS='Ceo@1405!'

echo "=== direct frigate ==="
for port in 8972 8973; do
  for user in admin ceo; do
    if [ "$user" = admin ]; then pass="$NEW_ADMIN"; else pass="$CEO_PASS"; fi
    code=$(curl -sk -o /tmp/o.txt -w '%{http_code}' -X POST "https://127.0.0.1:${port}/api/login" \
      -H 'Content-Type: application/json' -d "{\"user\":\"${user}\",\"password\":\"${pass}\"}")
    echo "port $port $user => $code $(head -c 80 /tmp/o.txt)"
  done
done

echo "=== portal ==="
for path in cafe center11; do
  for user in admin ceo; do
    if [ "$user" = admin ]; then pass="$NEW_ADMIN"; else pass="$CEO_PASS"; fi
    code=$(curl -sk -o /tmp/o.txt -w '%{http_code}' -X POST "http://127.0.0.1:8888/${path}/api/login" \
      -H 'Content-Type: application/json' -d "{\"user\":\"${user}\",\"password\":\"${pass}\"}")
    echo "$path $user => $code $(head -c 80 /tmp/o.txt)"
  done
done

echo "=== portal index creds line ==="
grep -o 'login-creds.*</p>' /home/rootuser/cctv_izadshahr/portal/index.html || grep login-creds /home/rootuser/cctv_izadshahr/portal/index.html

echo "=== recent login attempts ==="
echo '12345@' | sudo -S docker logs cctv-portal 2>&1 | grep 'api/login' | tail -15

echo "=== list users cafe ==="
TOKEN=$(curl -sk -X POST 'https://127.0.0.1:8972/api/login' -H 'Content-Type: application/json' \
  -d "{\"user\":\"admin\",\"password\":\"${NEW_ADMIN}\"}" -c - | awk '/frigate_token/ {print $7}')
curl -sk "https://127.0.0.1:8972/api/users" -H "Authorization: Bearer ${TOKEN}"
echo
