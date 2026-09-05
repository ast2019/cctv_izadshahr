#!/usr/bin/env bash
# Why does portal login say "wrong username/password"?
#
# Run ON THE SERVER, from anywhere:
#   scripts/diag-portal-login.sh <user> <password>
#   scripts/diag-portal-login.sh ceo 'Cctv1405'
#
# It walks the login path layer by layer and prints a verdict:
#   1. which UI users actually exist in each config/<instance>/frigate.db
#   2. what each Frigate answers to /api/login from the HOST (port 897x)
#   3. what each Frigate answers from INSIDE portal-metrics (the real path,
#      container → frigate-<name>:8971) — this is what login depends on
#   4. what the portal endpoint /api/portal-login/ returns
#   5. the last login lines from the portal-metrics log
#
# Nothing is changed; passwords are never printed.

set -uo pipefail
cd "$(dirname "$0")/.."

USER_NAME="${1:-}"
USER_PASS="${2:-}"
if [[ -z "$USER_NAME" || -z "$USER_PASS" ]]; then
  echo "usage: $0 <user> <password>" >&2
  exit 2
fi

PORTAL_URL="${PORTAL_URL:-http://127.0.0.1:8888}"

# service:host-port — host port maps to the container's authenticated 8971
INSTANCES=(
  "frigate-cafe:8972"
  "frigate-center11:8973"
  "frigate-center22:8974"
  "frigate-restaurant:8975"
  "frigate-sahel:8976"
  "frigate-villa:8977"
  "frigate-mahoote:8978"
  "frigate-tasisat:8980"
  "frigate-entezamat:8981"
  "frigate-anbar:8982"
  "frigate-khanedari:8983"
)

compose() {
  if [[ "${EUID}" -eq 0 ]]; then
    docker compose "$@"
  else
    sudo docker compose "$@"
  fi
}

hr() { printf '%s\n' "------------------------------------------------------------"; }

echo "== 1. UI users present in each frigate.db =="
echo "   (a user missing here can never log in through that instance)"
for instance in "${INSTANCES[@]}"; do
  service="${instance%%:*}"
  name="${service#frigate-}"
  db="config/${name}/frigate.db"
  if [[ ! -f "$db" ]]; then
    printf '  %-12s no frigate.db (auth never initialised)\n' "$name"
    continue
  fi
  users="$(python3 - "$db" <<'PY' 2>/dev/null
import sqlite3, sys
try:
    con = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
    rows = con.execute("SELECT username, role FROM user ORDER BY username").fetchall()
    print(", ".join(f"{u}({r})" for u, r in rows) if rows else "(table empty)")
except Exception as exc:
    print(f"unreadable: {exc}")
PY
)"
  printf '  %-12s %s\n' "$name" "$users"
done

hr
echo "== 2. POST /api/login from the HOST (https://127.0.0.1:<port>) =="
echo "   200 = accepted · 401 = user unknown or wrong password · other = broken"
body="$(python3 - "$USER_NAME" "$USER_PASS" <<'PY'
import json, sys
print(json.dumps({"user": sys.argv[1], "password": sys.argv[2]}))
PY
)"
for instance in "${INSTANCES[@]}"; do
  service="${instance%%:*}"
  port="${instance##*:}"
  name="${service#frigate-}"
  code="$(curl -sk -o /dev/null -w '%{http_code}' --connect-timeout 3 --max-time 10 \
    -X POST "https://127.0.0.1:${port}/api/login" \
    -H 'Content-Type: application/json' -H 'X-CSRF-TOKEN: 1' \
    -d "$body" 2>/dev/null)"
  printf '  %-12s port %-5s => %s\n' "$name" "$port" "${code:-no-answer}"
done

hr
echo "== 3. Same check from INSIDE portal-metrics (the path login really uses) =="
if ! compose ps --status running portal-metrics 2>/dev/null | grep -q portal-metrics; then
  echo "  portal-metrics is NOT running — every login returns 503/failure."
else
  FRIGATE_USER="$USER_NAME" FRIGATE_PASS="$USER_PASS" \
  compose exec -T -e FRIGATE_USER -e FRIGATE_PASS portal-metrics python3 - <<'PY'
import json, os, ssl, time
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

names = ["cafe", "center11", "center22", "restaurant", "sahel", "villa",
         "mahoote", "tasisat", "entezamat", "anbar", "khanedari"]
payload = json.dumps({
    "user": os.environ["FRIGATE_USER"],
    "password": os.environ["FRIGATE_PASS"],
}).encode()
ctx = ssl._create_unverified_context()
accepted, rejected, broken = [], [], []
for name in names:
    url = f"https://frigate-{name}:8971/api/login"
    req = Request(url, data=payload, method="POST", headers={
        "Content-Type": "application/json",
        "X-CSRF-TOKEN": "1",
        "User-Agent": "diag-portal-login",
    })
    started = time.monotonic()
    try:
        with urlopen(req, timeout=5, context=ctx) as resp:
            status, note = resp.status, "accepted"
            accepted.append(name)
    except HTTPError as exc:
        status, note = exc.code, "rejected" if exc.code in (401, 403) else "error"
        (rejected if exc.code in (401, 403) else broken).append(name)
    except (URLError, TimeoutError, OSError) as exc:
        status, note = "-", f"{type(exc).__name__}: {getattr(exc, 'reason', exc)}"
        broken.append(name)
    print(f"  {name:<12} {str(status):<5} {note}  ({time.monotonic() - started:.1f}s)")

print()
if accepted:
    print(f"  VERDICT: credentials are valid ({', '.join(accepted)} accepted) —")
    print("           the portal must be able to log this user in.")
elif rejected and broken:
    print(f"  VERDICT: only a partial answer. {len(rejected)} instance(s) rejected the")
    print(f"           password but {len(broken)} could not answer ({', '.join(broken)}).")
    print("           Fix those instances before trusting the 'wrong password' message.")
elif rejected:
    print("  VERDICT: every instance rejected this user/password —")
    print("           the account does not exist, or the password differs.")
    print("           Re-sync users: scripts/sync-frigate-users.sh")
else:
    print("  VERDICT: no instance answered at all (network/DNS/TLS or all down).")
    print("           The portal reports 503 'auth backend unavailable', not a bad password.")
PY
fi

hr
echo "== 4. The portal endpoint the browser calls =="
resp="$(curl -s -o /tmp/portal-login-out -w '%{http_code}' --max-time 40 \
  -X POST "${PORTAL_URL}/api/portal-login/" \
  -H 'Content-Type: application/json' \
  -d "$(python3 - "$USER_NAME" "$USER_PASS" <<'PY'
import json, sys
print(json.dumps({"username": sys.argv[1], "password": sys.argv[2]}))
PY
)" 2>/dev/null)"
echo "  POST ${PORTAL_URL}/api/portal-login/ => ${resp:-no-answer}"
echo "  body: $(head -c 300 /tmp/portal-login-out 2>/dev/null)"
rm -f /tmp/portal-login-out
echo "  200 = login works · 401 = rejected · 503 = backend unreachable"
echo "  404 = portal-metrics runs an OLD portal-api.py (redeploy it)"

hr
echo "== 5. Recent login attempts recorded by portal-metrics =="
compose logs --tail 400 portal-metrics 2>/dev/null | grep '\[login\]' | tail -15 \
  || echo "  (no [login] lines — this portal-api.py predates login tracing)"

hr
echo "Done. Sections 3 and 5 are the ones that decide the case."
