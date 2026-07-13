#!/bin/bash
# Test login with stale cookie
curl -sk -o /dev/null -w 'no cookie: %{http_code}\n' -X POST 'http://127.0.0.1:8888/cafe/api/login' \
  -H 'Content-Type: application/json' \
  -d '{"user":"ceo","password":"Cctv1405"}'

curl -sk -o /dev/null -w 'bad cookie: %{http_code}\n' -X POST 'http://127.0.0.1:8888/cafe/api/login' \
  -H 'Content-Type: application/json' \
  -b 'frigate_token=invalid.jwt.token' \
  -d '{"user":"ceo","password":"Cctv1405"}'

# Get real cookie from failed browser scenario - login direct then try portal
TOKEN=$(curl -sk -X POST 'https://127.0.0.1:8972/api/login' -H 'Content-Type: application/json' \
  -d '{"user":"ceo","password":"wrong"}' -c - 2>/dev/null | awk '/frigate_token/ {print $7}')
curl -sk -o /dev/null -w 'wrong pass cookie len0: %{http_code}\n' -X POST 'http://127.0.0.1:8888/cafe/api/login' \
  -H 'Content-Type: application/json' \
  -d '{"user":"ceo","password":"Cctv1405"}'

# username field instead of user
curl -sk -o /dev/null -w 'username field: %{http_code}\n' -X POST 'http://127.0.0.1:8888/cafe/api/login' \
  -H 'Content-Type: application/json' \
  -d '{"username":"ceo","password":"Cctv1405"}'

# user field
curl -sk -o /dev/null -w 'user field: %{http_code}\n' -X POST 'http://127.0.0.1:8888/cafe/api/login' \
  -H 'Content-Type: application/json' \
  -d '{"user":"ceo","password":"Cctv1405"}'
