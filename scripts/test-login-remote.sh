#!/bin/bash
test_login() {
  label=$1; url=$2; user=$3; pass=$4
  code=$(curl -sk -o /tmp/login_out.txt -w '%{http_code}' -X POST "$url" \
    -H 'Content-Type: application/json' \
    -d "{\"user\":\"$user\",\"password\":\"$pass\"}")
  echo "$label HTTP=$code body=$(head -c 150 /tmp/login_out.txt)"
}

test_login 'direct-cafe-admin' 'https://127.0.0.1:8972/api/login' admin 'tiw73TC67fxP5GqnEi6Mnltcg'
test_login 'direct-cafe-ceo' 'https://127.0.0.1:8972/api/login' ceo 'Ceo@1405!'
test_login 'direct-c11-admin' 'https://127.0.0.1:8973/api/login' admin 'tiw73TC67fxP5GqnEi6Mnltcg'
test_login 'direct-c11-ceo' 'https://127.0.0.1:8973/api/login' ceo 'Ceo@1405!'
test_login 'portal-cafe-admin' 'http://127.0.0.1:8888/cafe/api/login' admin 'tiw73TC67fxP5GqnEi6Mnltcg'
test_login 'portal-wrong' 'http://127.0.0.1:8888/cafe/api/login' admin 'wrongpass'
test_login 'portal-ceo' 'http://127.0.0.1:8888/cafe/api/login' ceo 'Ceo@1405!'

echo '=== temp passwords in logs ==='
cd /home/rootuser/cctv_izadshahr
echo '12345@' | sudo -S docker compose logs frigate-cafe 2>&1 | grep -i 'Password:' | tail -2
echo '12345@' | sudo -S docker compose logs frigate-center11 2>&1 | grep -i 'Password:' | tail -2
