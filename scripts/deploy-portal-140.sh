#!/bin/bash
set -euo pipefail
cd /home/rootuser/cctv_izadshahr

echo '12345@' | sudo -S mkdir -p data/portal scripts
echo '12345@' | sudo -S cp -r /tmp/cctv_portal_v140/* portal/
echo '12345@' | sudo -S cp /tmp/docker-compose.yml docker-compose.yml
echo '12345@' | sudo -S cp /tmp/make-icons.py scripts/make-icons.py
echo '12345@' | sudo -S chown -R rootuser:rootuser data scripts/make-icons.py
echo '12345@' | sudo -S sed -i 's/\r$//' scripts/make-icons.py

# Generate icons from logo
echo '12345@' | sudo -S docker run --rm \
  -v "$(pwd)/portal/assets:/out" \
  -v "$(pwd)/scripts/make-icons.py:/tmp/make-icons.py:ro" \
  python:3.12-alpine \
  sh -c 'pip install -q pillow && python - <<"PY"
from pathlib import Path
from PIL import Image
ROOT = Path("/out")
img = Image.open(ROOT / "logo.png").convert("RGBA")

def fit(size):
    c = Image.new("RGBA", (size, size), (255, 255, 255, 255))
    x = img.copy()
    x.thumbnail((size - size // 10, size - size // 10), Image.Resampling.LANCZOS)
    c.paste(x, ((size - x.width) // 2, (size - x.height) // 2), x)
    return c

fit(32).save(ROOT / "favicon.png")
fit(180).save(ROOT / "apple-touch-icon.png")
fit(192).save(ROOT / "icon-192.png")
fit(512).save(ROOT / "icon-512.png")
print("icons ok")
PY'

echo '12345@' | sudo -S docker compose up -d --force-recreate portal-metrics portal
sleep 2
curl -s -o /dev/null -w "metrics:%{http_code}\n" http://127.0.0.1:8888/api/host-metrics/
curl -s -w "\naudit_post:%{http_code}\n" -X POST http://127.0.0.1:8888/api/audit/ \
  -H 'Content-Type: application/json' \
  -d '{"event":"login","username":"deploy-test","success":true}'
curl -s http://127.0.0.1:8888/api/audit/?limit=3
echo
ls -la portal/assets/favicon.png portal/assets/icon-192.png data/portal/ || true
echo '12345@' | sudo -S ls -la data/portal/
