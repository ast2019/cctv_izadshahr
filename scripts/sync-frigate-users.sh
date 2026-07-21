#!/usr/bin/env bash
# Sync and verify Frigate UI users across every instance.
# Run from any directory after (re)creating the Frigate containers.
# Optional overrides:
#   ADMIN_PASSWORD=... VIEWER_USER=... VIEWER_PASSWORD=... VIEWER_ROLE=...

set -uo pipefail
cd "$(dirname "$0")/.."

ADMIN_PASSWORD="${ADMIN_PASSWORD:-CctvAdmin1405}"
VIEWER_USER="${VIEWER_USER:-ceo}"
VIEWER_PASSWORD="${VIEWER_PASSWORD:-Cctv1405}"
VIEWER_ROLE="${VIEWER_ROLE:-viewer}"
READY_RETRIES="${READY_RETRIES:-30}"
READY_DELAY="${READY_DELAY:-2}"

INSTANCES=(
  "frigate-cafe:8972"
  "frigate-center11:8973"
  "frigate-center22:8974"
  "frigate-restaurant:8975"
  "frigate-sahel:8976"
  "frigate-villa:8977"
  "frigate-mahoote:8978"
  "frigate-temp:8979"
  "frigate-tasisat:8980"
  "frigate-entezamat:8981"
  "frigate-anbar:8982"
)

compose() {
  if [[ "${EUID}" -eq 0 ]]; then
    docker compose "$@"
  else
    sudo docker compose "$@"
  fi
}

get_temp_admin_password() {
  local service="$1"
  compose logs "$service" 2>&1 \
    | grep 'Password:' \
    | grep '\*\*\*' \
    | tail -1 \
    | sed 's/.*Password: //;s/   \*\*\*//'
}

wait_for_gateway() {
  local port="$1" attempt
  for ((attempt = 1; attempt <= READY_RETRIES; attempt++)); do
    if curl -sk --connect-timeout 2 --max-time 5 -o /dev/null \
      "https://127.0.0.1:${port}/api/version"; then
      return 0
    fi
    sleep "$READY_DELAY"
  done
  return 1
}

login_token() {
  local port="$1" user="$2" pass="$3"
  curl -fsSk --connect-timeout 3 --max-time 10 \
    -X POST "https://127.0.0.1:${port}/api/login" \
    -H "Content-Type: application/json" \
    -d "{\"user\":\"${user}\",\"password\":\"${pass}\"}" \
    -c - 2>/dev/null | awk '/frigate_token/ {print $7}'
}

api() {
  local method="$1" port="$2" token="$3" path="$4" data="${5:-}"
  local args=(-fsSk --connect-timeout 3 --max-time 15 -X "$method"
    "https://127.0.0.1:${port}${path}"
    -H "Authorization: Bearer ${token}")
  if [[ -n "$data" ]]; then
    args+=(-H "Content-Type: application/json" -d "$data")
  fi
  curl "${args[@]}"
}

sync_instance() {
  local service="$1" port="$2" token temp_pass users_json
  echo "=== ${service} (port ${port}) ==="

  if ! compose ps --status running "$service" 2>/dev/null | grep -q "$service"; then
    echo "  ERROR: service is not running"
    return 1
  fi

  if ! wait_for_gateway "$port"; then
    echo "  ERROR: authenticated gateway did not become ready"
    return 1
  fi

  token="$(login_token "$port" admin "$ADMIN_PASSWORD" || true)"
  if [[ -z "$token" ]]; then
    temp_pass="$(get_temp_admin_password "$service" || true)"
    if [[ -z "$temp_pass" ]]; then
      echo "  ERROR: admin login failed and no temporary password was found"
      return 1
    fi
    token="$(login_token "$port" admin "$temp_pass" || true)"
    if [[ -z "$token" ]]; then
      echo "  ERROR: temporary admin login failed"
      return 1
    fi
    if ! api PUT "$port" "$token" "/api/users/admin/password" \
      "{\"password\":\"${ADMIN_PASSWORD}\"}" >/dev/null; then
      echo "  ERROR: could not set the admin password"
      return 1
    fi
    echo "  admin password updated"
    token="$(login_token "$port" admin "$ADMIN_PASSWORD" || true)"
  fi

  if [[ -z "$token" ]]; then
    echo "  ERROR: admin verification failed"
    return 1
  fi

  if ! users_json="$(api GET "$port" "$token" "/api/users")"; then
    echo "  ERROR: could not list users"
    return 1
  fi

  if grep -q "\"${VIEWER_USER}\"" <<<"$users_json"; then
    if ! api PUT "$port" "$token" "/api/users/${VIEWER_USER}/password" \
      "{\"password\":\"${VIEWER_PASSWORD}\"}" >/dev/null; then
      echo "  ERROR: could not update viewer password"
      return 1
    fi
    if ! api PUT "$port" "$token" "/api/users/${VIEWER_USER}/role" \
      "{\"role\":\"${VIEWER_ROLE}\"}" >/dev/null; then
      echo "  ERROR: could not update viewer role"
      return 1
    fi
    echo "  viewer '${VIEWER_USER}' password/role updated"
  else
    if ! api POST "$port" "$token" "/api/users" \
      "{\"username\":\"${VIEWER_USER}\",\"password\":\"${VIEWER_PASSWORD}\",\"role\":\"${VIEWER_ROLE}\"}" >/dev/null; then
      echo "  ERROR: could not create viewer '${VIEWER_USER}'"
      return 1
    fi
    echo "  viewer '${VIEWER_USER}' created"
  fi

  if [[ -z "$(login_token "$port" admin "$ADMIN_PASSWORD" || true)" ]]; then
    echo "  ERROR: final admin login verification failed"
    return 1
  fi
  if [[ -z "$(login_token "$port" "$VIEWER_USER" "$VIEWER_PASSWORD" || true)" ]]; then
    echo "  ERROR: final viewer login verification failed"
    return 1
  fi

  echo "  OK: admin and viewer logins verified"
}

failures=()
for instance in "${INSTANCES[@]}"; do
  service="${instance%%:*}"
  port="${instance##*:}"
  if ! sync_instance "$service" "$port"; then
    failures+=("$service")
  fi
done

if ((${#failures[@]} > 0)); then
  echo "FAILED: ${failures[*]}" >&2
  exit 1
fi

echo "All Frigate users synchronized and verified."
