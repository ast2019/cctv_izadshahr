#!/usr/bin/env bash
# Zero the camera broken-status and event history so tracking starts fresh.
# Safe to run anytime — fresh data accumulates on the next portal poll.
# The login/auth audit log is intentionally NOT touched.
set -euo pipefail
cd "$(dirname "$0")/.."

compose() {
  if [[ "${EUID}" -eq 0 ]]; then
    docker compose "$@"
  else
    sudo docker compose "$@"
  fi
}

compose exec -T portal-metrics python3 - <<'PY'
import os, sqlite3
db = os.environ.get("PORTAL_DB", "/data/portal.db")
conn = sqlite3.connect(db)
try:
    ev = conn.execute("DELETE FROM camera_events").rowcount
    st = conn.execute("DELETE FROM camera_status").rowcount
    conn.commit()
    print(f"cleared: camera_events={ev} rows, camera_status={st} rows")
finally:
    conn.close()
PY

echo "Camera broken/event history reset. Login audit log kept intact."
