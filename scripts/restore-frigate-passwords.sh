#!/usr/bin/env bash
# Restore the known Frigate UI passwords on EVERY instance, in one pass.
#
#   scripts/restore-frigate-passwords.sh <admin-password> <ceo-password>
#
# Why not scripts/sync-frigate-users.sh? That one goes through Frigate's REST
# API, which enforces password rules (min 12 chars, and newer builds also demand
# a special character). A short historic password like an 8-character one can
# never be re-applied that way — the API answers 400 and the user keeps the old
# or missing password. Logging in has no such rule: Frigate only verifies the
# stored hash.
#
# So this script hashes the password with Frigate's OWN hash_password() inside
# each container and writes the row straight into /config/frigate.db. Same hash
# format, same verification path, no API validation in the way.
#
# Passwords travel over stdin only — never in argv of a container command.
# Nothing else is touched: cameras, recordings and configs stay as they are.
# No restart needed: Frigate reads the user table on every login.

set -uo pipefail
cd "$(dirname "$0")/.."

ADMIN_PASSWORD="${1:-${ADMIN_PASSWORD:-}}"
CEO_PASSWORD="${2:-${CEO_PASSWORD:-}}"
CEO_USER="${CEO_USER:-ceo}"

if [[ -z "$ADMIN_PASSWORD" || -z "$CEO_PASSWORD" ]]; then
  cat >&2 <<'USAGE'
usage: scripts/restore-frigate-passwords.sh <admin-password> <ceo-password>

Sets user 'admin' (role admin) and user 'ceo' (role viewer) on every running
Frigate instance, then verifies both logins against the authenticated port.
USAGE
  exit 2
fi

# service:host-port  (host port maps to the container's authenticated 8971)
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
  "frigate-khanedari:8983"
)

compose() {
  if [[ "${EUID}" -eq 0 ]]; then
    docker compose "$@"
  else
    sudo docker compose "$@"
  fi
}

PY_SRC="$(mktemp)"
trap 'rm -f "$PY_SRC"' EXIT

# Runs inside the Frigate container. ADMIN_PW / CEO_PW / CEO_USER come from the
# bootstrap below, which reads them off stdin.
cat >"$PY_SRC" <<'PYSRC'
import binascii
import hashlib
import os
import secrets
import sqlite3
import sys

DB = os.environ.get("FRIGATE_DB", "/config/frigate.db")
sys.path.insert(0, "/opt/frigate")

# Prefer Frigate's own hasher so the stored format always matches this build.
hash_password = None
verify_password = None
source = "builtin"
for mod in ("frigate.api.auth", "frigate.util.auth", "frigate.api.defs.auth"):
    try:
        m = __import__(mod, fromlist=["hash_password", "verify_password"])
    except Exception:
        continue
    if getattr(m, "hash_password", None):
        hash_password = m.hash_password
        verify_password = getattr(m, "verify_password", None)
        source = mod
        break

if hash_password is None:
    # Same scheme Frigate uses: "<iterations>$<salt>$<hex>" PBKDF2-SHA256.
    def hash_password(password, iterations=600000):
        salt = secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations
        )
        return "%d$%s$%s" % (iterations, salt, binascii.hexlify(digest).decode("ascii"))


def check(password, stored):
    """True if `password` validates against `stored`, whatever the arg order."""
    if verify_password:
        for args in ((password, stored), (stored, password)):
            try:
                if verify_password(*args):
                    return True
            except Exception:
                continue
    try:
        iterations, salt, expected = stored.split("$", 2)
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt.encode("utf-8"), int(iterations)
        )
        return binascii.hexlify(digest).decode("ascii") == expected
    except Exception:
        return False


wanted = [("admin", ADMIN_PW, "admin"), (CEO_USER, CEO_PW, "viewer")]

try:
    con = sqlite3.connect(DB, timeout=25)
except Exception as exc:
    print(f"  FAIL cannot open {DB}: {exc}")
    raise SystemExit(1)
con.execute("PRAGMA busy_timeout=25000")

columns = {row[1]: row for row in con.execute("PRAGMA table_info('user')")}
if not columns:
    print("  SKIP no 'user' table yet — auth has never initialised on this instance")
    print("       start it once on port 8971 so Frigate creates the table, then rerun")
    raise SystemExit(3)

print(f"  hasher: {source}")
for username, password, role in wanted:
    password_hash = hash_password(password)
    exists = con.execute(
        "SELECT 1 FROM user WHERE username=?", (username,)
    ).fetchone()
    if exists:
        assignments = ["password_hash=?"]
        values = [password_hash]
        if "role" in columns:
            assignments.append("role=?")
            values.append(role)
        values.append(username)
        con.execute(
            f"UPDATE user SET {', '.join(assignments)} WHERE username=?", values
        )
        action = "updated"
    else:
        row = {"username": username, "password_hash": password_hash}
        if "role" in columns:
            row["role"] = role
        if "notification_tokens" in columns:
            row["notification_tokens"] = "[]"
        # Fill any other NOT NULL column that has no default.
        for name, info in columns.items():
            if name in row:
                continue
            not_null, default = info[3], info[4]
            if not_null and default is None:
                row[name] = ""
        placeholders = ", ".join("?" * len(row))
        con.execute(
            f"INSERT INTO user ({', '.join(row)}) VALUES ({placeholders})",
            list(row.values()),
        )
        action = "created"
    con.commit()

    stored = con.execute(
        "SELECT password_hash FROM user WHERE username=?", (username,)
    ).fetchone()
    ok = bool(stored) and check(password, stored[0])
    print(f"  {action:<7} {username:<6} hash-check: {'ok' if ok else 'FAILED'}")
    if not ok:
        raise SystemExit(1)
PYSRC

# Reads the two passwords off stdin, then executes the script that follows.
BOOTSTRAP='import sys
ADMIN_PW = sys.stdin.readline().rstrip("\n")
CEO_PW = sys.stdin.readline().rstrip("\n")
CEO_USER = sys.stdin.readline().rstrip("\n")
src = sys.stdin.read()
exec(compile(src, "restore-passwords", "exec"), globals())'

login_status() {
  local port="$1" user="$2" password="$3"
  U="$user" P="$password" python3 -c \
    'import json,os;print(json.dumps({"user":os.environ["U"],"password":os.environ["P"]}))' \
  | curl -sk -o /dev/null -w '%{http_code}' --connect-timeout 3 --max-time 12 \
      -X POST "https://127.0.0.1:${port}/api/login" \
      -H 'Content-Type: application/json' --data-binary @- 2>/dev/null
}

written=()
failed=()
skipped=()

for instance in "${INSTANCES[@]}"; do
  service="${instance%%:*}"
  name="${service#frigate-}"
  echo "=== ${name} ==="

  if ! compose ps --status running "$service" 2>/dev/null | grep -q "$service"; then
    echo "  SKIP container is not running"
    skipped+=("$name")
    continue
  fi

  {
    printf '%s\n%s\n%s\n' "$ADMIN_PASSWORD" "$CEO_PASSWORD" "$CEO_USER"
    cat "$PY_SRC"
  } | compose exec -T "$service" python3 -c "$BOOTSTRAP"
  # PIPESTATUS[1] = the container's exit code (pipefail could mask it with SIGPIPE)
  status="${PIPESTATUS[1]}"
  case "$status" in
    0) written+=("$name") ;;
    3) skipped+=("$name") ;;
    *) echo "  FAIL could not write users"; failed+=("$name") ;;
  esac
done

echo
echo "=== verifying real logins on the authenticated port (8971) ==="
printf '%-12s %-8s %-8s\n' instance admin "$CEO_USER"
verify_failed=()
for instance in "${INSTANCES[@]}"; do
  service="${instance%%:*}"
  port="${instance##*:}"
  name="${service#frigate-}"
  if [[ " ${skipped[*]-} " == *" ${name} "* ]]; then
    printf '%-12s %-8s %-8s (skipped)\n' "$name" "-" "-"
    continue
  fi
  a="$(login_status "$port" admin "$ADMIN_PASSWORD")"
  c="$(login_status "$port" "$CEO_USER" "$CEO_PASSWORD")"
  printf '%-12s %-8s %-8s\n' "$name" "${a:-none}" "${c:-none}"
  [[ "$a" == "200" && "$c" == "200" ]] || verify_failed+=("$name")
done

echo
echo "200 = login accepted. Anything else on a non-skipped instance is a problem."
echo "written: ${written[*]:-none}"
[[ ${#skipped[@]} -gt 0 ]] && echo "skipped: ${skipped[*]}"
[[ ${#failed[@]} -gt 0 ]] && echo "write failures: ${failed[*]}"
if [[ ${#verify_failed[@]} -gt 0 ]]; then
  echo "login verification failed: ${verify_failed[*]}" >&2
  exit 1
fi

echo
echo "All good. The portal accepts these credentials as soon as one instance does:"
echo "  scripts/diag-portal-login.sh ${CEO_USER} '<password>'"
