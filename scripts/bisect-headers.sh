#!/bin/bash
# Find which browser header causes 401 on login
BODY='{"user":"ceo","password":"Cctv1405"}'
URL='http://127.0.0.1:8888/cafe/api/login'

t() {
  label="$1"; shift
  code=$(curl -sk -o /tmp/o.txt -w '%{http_code}' -X POST "$URL" -H 'Content-Type: application/json' "$@" -d "$BODY")
  echo "$label => $code $(head -c 100 /tmp/o.txt)"
}

t 'plain'
t 'origin'   -H 'Origin: http://192.168.10.18:8888'
t 'referer'  -H 'Referer: http://192.168.10.18:8888/'
t 'ua'       -H 'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/150.0.0.0'
t 'host-ip'  -H 'Host: 192.168.10.18:8888'
t 'all'      -H 'Origin: http://192.168.10.18:8888' -H 'Referer: http://192.168.10.18:8888/' -H 'User-Agent: Mozilla/5.0 Chrome/150' -H 'Host: 192.168.10.18:8888'

# Also test direct against frigate with Host header
t2() {
  label="$1"; shift
  code=$(curl -sk -o /tmp/o.txt -w '%{http_code}' -X POST 'https://127.0.0.1:8972/api/login' -H 'Content-Type: application/json' "$@" -d "$BODY")
  echo "direct $label => $code $(head -c 100 /tmp/o.txt)"
}
t2 'plain'
t2 'host-ip' -H 'Host: 192.168.10.18:8888'
t2 'origin'  -H 'Origin: http://192.168.10.18:8888'
