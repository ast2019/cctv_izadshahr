#!/usr/bin/env bash
# Sync Frigate UI users across instances (run on server from repo root).
# Usage:
#   ADMIN_PASSWORD='CctvAdmin1405' VIEWER_PASSWORD='Cctv1405' ./scripts/sync-frigate-users.sh
#
# Requires: curl, docker compose, sudo

set -euo pipefail
cd "$(dirname "$0")/.."

ADMIN_PASSWORD="${ADMIN_PASSWORD:-}"
VIEWER_USER="${VIEWER_USER:-ceo}"
VIEWER_PASSWORD="${VIEWER_PASSWORD:-Cctv1405}"
VIEWER_ROLE="${VIEWER_ROLE:-viewer}"

declare -A INSTANCES=(
  [frigate-cafe]=8972
  [frigate-center11]=8973
  [frigate-center22]=8974
  [frigate-restaurant]=8975
  [frigate-sahel]=8976
  [frigate-villa]=8977
  [frigate-mahoote]=8978
  [frigate-tasisat]=8980
  [frigate-entezamat]=8981
  # Temporary camera-identification instance; keep its portal users in sync too.
  [frigate-temp]=8979
)

get_temp_admin_password() {
  local service="$1"
  sudo docker compose logs "$service" 2>&1 \
    | grep 'Password:' \
    | grep '\*\*\*' \
    | tail -1 \
    | sed 's/.*Password: //;s/   \*\*\*//'
}

login_token() {
  local port="$1" user="$2" pass="$3"
  curl -sk -X POST "https://127.0.0.1:${port}/api/login" \
    -H "Content-Type: application/json" \
    -d "{\"user\":\"${user}\",\"password\":\"${pass}\"}" \
    -c - | awk '/frigate_token/ {print $7}'
}

api() {
  local method="$1" port="$2" token="$3" path="$4" data="${5:-}"
  if [[ -n "$data" ]]; then
    curl -sk -X "$method" "https://127.0.0.1:${port}${path}" \
      -H "Authorization: Bearer ${token}" \
      -H "Content-Type: application/json" \
      -d "$data"
  else
    curl -sk -X "$method" "https://127.0.0.1:${port}${path}" \
      -H "Authorization: Bearer ${token}"
  fi
}

for service in "${!INSTANCES[@]}"; do
  port="${INSTANCES[$service]}"
  echo "=== ${service} (port ${port}) ==="

  if ! sudo docker compose ps --status running "$service" 2>/dev/null | grep -q "$service"; then
    echo "  skip: not running"
    continue
  fi

  temp_pass="$(get_temp_admin_password "$service")"
  if [[ -z "$temp_pass" ]]; then
    echo "  skip: no temp admin password in logs (maybe already changed)"
    temp_pass="${ADMIN_PASSWORD:-}"
  fi
  if [[ -z "$temp_pass" ]]; then
    echo "  skip: set ADMIN_PASSWORD or reset admin via config"
    continue
  fi

  token="$(login_token "$port" admin "$temp_pass" || true)"
  if [[ -z "$token" && -n "$ADMIN_PASSWORD" && "$temp_pass" != "$ADMIN_PASSWORD" ]]; then
    token="$(login_token "$port" admin "$ADMIN_PASSWORD" || true)"
    temp_pass="$ADMIN_PASSWORD"
  fi
  if [[ -z "$token" ]]; then
    echo "  error: admin login failed"
    continue
  fi

  if [[ -n "$ADMIN_PASSWORD" && "$temp_pass" != "$ADMIN_PASSWORD" ]]; then
    api PUT "$port" "$token" "/api/users/admin/password" "{\"password\":\"${ADMIN_PASSWORD}\"}" >/dev/null
    echo "  admin password updated"
    token="$(login_token "$port" admin "$ADMIN_PASSWORD")"
  fi

  users_json="$(api GET "$port" "$token" "/api/users")"
  if echo "$users_json" | grep -q "\"${VIEWER_USER}\""; then
    api PUT "$port" "$token" "/api/users/${VIEWER_USER}/password" "{\"password\":\"${VIEWER_PASSWORD}\"}" >/dev/null
    api PUT "$port" "$token" "/api/users/${VIEWER_USER}/role" "{\"role\":\"${VIEWER_ROLE}\"}" >/dev/null 2>/dev/null || true
    echo "  viewer '${VIEWER_USER}' password/role synced"
  else
    api POST "$port" "$token" "/api/users" \
      "{\"username\":\"${VIEWER_USER}\",\"password\":\"${VIEWER_PASSWORD}\",\"role\":\"${VIEWER_ROLE}\"}" >/dev/null
    echo "  viewer '${VIEWER_USER}' created"
  fi
done

echo "done"
