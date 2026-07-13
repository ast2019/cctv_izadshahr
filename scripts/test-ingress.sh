#!/bin/bash
TOKEN=$(curl -sk -X POST 'https://127.0.0.1:8972/api/login' -H 'Content-Type: application/json' \
  -d '{"user":"ceo","password":"Cctv1405"}' -c - | awk '/frigate_token/ {print $7}')
echo "token len: ${#TOKEN}"

echo '--- with X-Ingress-Path ---'
curl -sk -H "Authorization: Bearer ${TOKEN}" -H 'X-Ingress-Path: /cafe' https://127.0.0.1:8972/ | grep -oE '(<base[^>]*>|baseUrl[^,;]{0,60})' | head -5
echo '--- without ---'
curl -sk -H "Authorization: Bearer ${TOKEN}" https://127.0.0.1:8972/ | grep -oE '(<base[^>]*>|baseUrl[^,;]{0,60})' | head -5
