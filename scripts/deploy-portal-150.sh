#!/bin/bash
set -euo pipefail
cd /home/rootuser/cctv_izadshahr

echo '12345@' | sudo -S cp -r /tmp/cctv_portal_v150/* portal/
echo '12345@' | sudo -S docker compose up -d --force-recreate portal-metrics
echo '12345@' | sudo -S docker compose restart portal
sleep 2

curl -s -o /dev/null -w "metrics:%{http_code}\n" http://127.0.0.1:8888/api/host-metrics/
curl -s -w "\nreport:%{http_code}\n" -X POST http://127.0.0.1:8888/api/cameras/report/ \
  -H 'Content-Type: application/json' \
  -d '{"cameras":[{"camera":"cam_test","site":"center11","status":"broken","detail":"deploy check"}]}'
curl -s http://127.0.0.1:8888/api/cameras/broken/
echo
curl -s 'http://127.0.0.1:8888/api/audit/?limit=2'
echo
