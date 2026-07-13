#!/usr/bin/env bash
# Obtain Let's Encrypt certificate and enable HTTPS nginx config.
# Usage: CCTV_DOMAIN=cctv.example.com CCTV_EMAIL=you@example.com ./scripts/init-ssl.sh
set -euo pipefail
cd "$(dirname "$0")/.."

DOMAIN="${CCTV_DOMAIN:?Set CCTV_DOMAIN}"
EMAIL="${CCTV_EMAIL:?Set CCTV_EMAIL}"
CAFE_HOST="cafe.${DOMAIN}"
CENTER_HOST="center11.${DOMAIN}"

echo "Requesting certificate for: ${DOMAIN}, ${CAFE_HOST}, ${CENTER_HOST}"

mkdir -p certbot/conf certbot/www

# Start nginx HTTP-only for ACME challenge
sudo docker compose up -d portal

sudo docker run --rm \
  -v "$(pwd)/certbot/conf:/etc/letsencrypt" \
  -v "$(pwd)/certbot/www:/var/www/certbot" \
  certbot/certbot certonly --webroot -w /var/www/certbot \
  --email "${EMAIL}" --agree-tos --no-eff-email \
  -d "${DOMAIN}" -d "${CAFE_HOST}" -d "${CENTER_HOST}"

# Enable SSL nginx config
export CCTV_DOMAIN="${DOMAIN}"
envsubst '${CCTV_DOMAIN}' < portal/nginx.ssl.conf.template > portal/nginx.ssl.conf

sudo docker compose --profile ssl up -d portal
echo "Done. Portal: https://${DOMAIN}"
