#!/bin/bash
NEW_ADMIN='Admin@1405!'
CEO_PASS='Ceo@1405!'
for user in admin ceo; do
  if [ "$user" = admin ]; then pass="$NEW_ADMIN"; else pass="$CEO_PASS"; fi
  for path in cafe center11; do
    code=$(curl -sk -o /dev/null -w '%{http_code}' -X POST "http://127.0.0.1:8888/${path}/api/login" \
      -H 'Content-Type: application/json' -d "{\"user\":\"${user}\",\"password\":\"${pass}\"}")
    echo "$user @ $path => $code"
  done
done
