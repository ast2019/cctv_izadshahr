#!/bin/bash
test() {
  label=$1; user=$2; pass=$3
  code=$(curl -sk -o /tmp/o.txt -w '%{http_code}' -X POST 'http://127.0.0.1:8888/cafe/api/login' \
    -H 'Content-Type: application/json' -d "{\"user\":\"$user\",\"password\":\"$pass\"}")
  echo "$label => $code $(cat /tmp/o.txt)"
}
test admin123 admin admin123
test admin-pass admin '12345@'
test admin-tiw admin 'tiw73TC67fxP5GqnEi6Mnltcg'
test ceo ceo 'Ceo@1405!'
test ceo-no-bang ceo 'Ceo@1405'
