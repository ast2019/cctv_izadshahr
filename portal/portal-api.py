#!/usr/bin/env python3
"""Portal API: host metrics + SQLite (auth audit + camera health) + hourly ambiance snapshots."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse, parse_qs, quote
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from http.cookies import SimpleCookie
import json
import os
import random
import secrets
import sqlite3
import ssl
import threading
import time

PROC = "/host/proc"
DB_PATH = Path(os.environ.get("PORTAL_DB", "/data/portal.db"))
SNAP_DIR = Path(os.environ.get("PORTAL_SNAP_DIR", "/data/snapshots"))
WATCHDOG_STATUS = Path(os.environ.get("WATCHDOG_STATUS", "/data/watchdog/status.json"))
LOAD_RATIO_LIMIT = 0.5
MEM_PERCENT_LIMIT = 30.0
# Delete auth + camera event history older than this many days.
RETENTION_DAYS = int(os.environ.get("PORTAL_RETENTION_DAYS", "30"))
SESSION_COOKIE = "portal_session"
SESSION_MAX_AGE = 2592000  # 30 days
_SSL_CTX = ssl._create_unverified_context()
# Per-instance timeout and total budget for one login. nginx gives up at 60s,
# so the whole password check must finish well before that.
LOGIN_TIMEOUT = float(os.environ.get("PORTAL_LOGIN_TIMEOUT", "5"))
LOGIN_DEADLINE = float(os.environ.get("PORTAL_LOGIN_DEADLINE", "25"))
# Password check only — does not create Frigate cookies. Try every recording
# instance so a user that exists on any synced DB can log into the portal.
AUTH_INSTANCE_IDS = (
    "cafe",
    "center11",
    "center22",
    "restaurant",
    "sahel",
    "villa",
    "mahoote",
    "tasisat",
    "entezamat",
    "anbar",
    "khanedari",
)


def auth_login_urls() -> list[str]:
    primary = os.environ.get("FRIGATE_AUTH_URL", "").strip()
    urls = [primary] if primary else []
    for name in AUTH_INSTANCE_IDS:
        url = f"https://frigate-{name}:8971/api/login"
        if url not in urls:
            urls.append(url)
    return urls


AUTH_LOGIN_URLS = auth_login_urls()

# Internal Frigate API (port 5000, no auth) — docker network hostnames
FRIGATE_SOURCES = [
    {"site": "cafe", "base": os.environ.get("FRIGATE_CAFE_URL", "http://frigate-cafe:5000")},
    {"site": "center11", "base": os.environ.get("FRIGATE_CENTER11_URL", "http://frigate-center11:5000")},
    {"site": "center22", "base": os.environ.get("FRIGATE_CENTER22_URL", "http://frigate-center22:5000")},
    {"site": "restaurant", "base": os.environ.get("FRIGATE_RESTAURANT_URL", "http://frigate-restaurant:5000")},
    {"site": "sahel", "base": os.environ.get("FRIGATE_SAHEL_URL", "http://frigate-sahel:5000")},
    {"site": "villa", "base": os.environ.get("FRIGATE_VILLA_URL", "http://frigate-villa:5000")},
    {"site": "mahoote", "base": os.environ.get("FRIGATE_MAHOOTE_URL", "http://frigate-mahoote:5000")},
]

SNAP_COUNT = int(os.environ.get("PORTAL_SNAP_COUNT", "8"))  # total tiles (split L/R)
SNAP_INTERVAL_SEC = int(os.environ.get("PORTAL_SNAP_INTERVAL", str(3600)))
SNAP_FETCH_TIMEOUT = 12

_db_lock = threading.Lock()
_snap_lock = threading.Lock()
_snap_manifest: dict = {"updated_at": None, "tiles": []}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def cpu_cores():
    try:
        n = 0
        with open(f"{PROC}/cpuinfo", encoding="utf-8") as f:
            for line in f:
                if line.startswith("processor"):
                    n += 1
        return n or 1
    except OSError:
        return 1


def load_avg():
    with open(f"{PROC}/loadavg", encoding="utf-8") as f:
        a, b, c, *_ = f.read().split()
        return float(a), float(b), float(c)


def memory():
    info = {}
    with open(f"{PROC}/meminfo", encoding="utf-8") as f:
        for line in f:
            if ":" not in line:
                continue
            key, val = line.split(":", 1)
            info[key.strip()] = int(val.strip().split()[0])
    total = info.get("MemTotal", 1)
    avail = info.get("MemAvailable", info.get("MemFree", 0))
    used = max(0, total - avail)
    pct = round((used / total) * 100, 1) if total else 0.0
    return {
        "total_kb": total,
        "used_kb": used,
        "available_kb": avail,
        "used_percent": pct,
    }


def host_snapshot():
    cores = cpu_cores()
    l1, l5, l15 = load_avg()
    mem = memory()
    load_limit = round(cores * LOAD_RATIO_LIMIT, 2)
    cpu_pressure = l1 >= load_limit
    mem_pressure = mem["used_percent"] > MEM_PERCENT_LIMIT
    return {
        "cpu_cores": cores,
        "load_average": {"1m": l1, "5m": l5, "15m": l15},
        "load_limit": load_limit,
        "cpu_pressure": cpu_pressure,
        "memory": mem,
        "memory_limit_percent": MEM_PERCENT_LIMIT,
        "memory_pressure": mem_pressure,
        "stable": not cpu_pressure and not mem_pressure,
    }


def db_connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _db_lock:
        conn = db_connect()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS auth_events (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  ts TEXT NOT NULL,
                  event TEXT NOT NULL,
                  username TEXT,
                  ip TEXT,
                  user_agent TEXT,
                  success INTEGER NOT NULL DEFAULT 1,
                  detail TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_auth_events_ts ON auth_events(ts DESC);
                CREATE INDEX IF NOT EXISTS idx_auth_events_user ON auth_events(username);

                CREATE TABLE IF NOT EXISTS camera_status (
                  camera TEXT NOT NULL,
                  site TEXT NOT NULL,
                  status TEXT NOT NULL,
                  first_seen TEXT NOT NULL,
                  last_change TEXT NOT NULL,
                  last_detail TEXT,
                  PRIMARY KEY (camera, site)
                );

                CREATE TABLE IF NOT EXISTS camera_events (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  ts TEXT NOT NULL,
                  event TEXT NOT NULL,
                  camera TEXT NOT NULL,
                  site TEXT,
                  detail TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_camera_events_ts ON camera_events(ts DESC);
                CREATE INDEX IF NOT EXISTS idx_camera_events_cam ON camera_events(camera);

                CREATE TABLE IF NOT EXISTS portal_sessions (
                  token TEXT PRIMARY KEY,
                  username TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  expires_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_portal_sessions_exp ON portal_sessions(expires_at);
                """
            )
            conn.commit()
        finally:
            conn.close()


def purge_old_data(days=RETENTION_DAYS):
    """Delete auth + camera events with a timestamp older than `days`.
    Timestamps are UTC ISO-8601 (same format), so lexical `<` compare is correct.
    camera_status is current-state (not history) and is left untouched."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with _db_lock:
        conn = db_connect()
        try:
            a = conn.execute("DELETE FROM auth_events WHERE ts < ?", (cutoff,)).rowcount
            e = conn.execute("DELETE FROM camera_events WHERE ts < ?", (cutoff,)).rowcount
            s = conn.execute("DELETE FROM portal_sessions WHERE expires_at < ?", (cutoff,)).rowcount
            conn.commit()
            return {"auth_events": a, "camera_events": e, "sessions": s, "cutoff": cutoff}
        finally:
            conn.close()


def insert_auth_event(event, username, ip, user_agent, success=True, detail=None):
    ts = now_iso()
    with _db_lock:
        conn = db_connect()
        try:
            conn.execute(
                """
                INSERT INTO auth_events (ts, event, username, ip, user_agent, success, detail)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ts,
                    event,
                    username or "",
                    ip or "",
                    (user_agent or "")[:400],
                    1 if success else 0,
                    detail,
                ),
            )
            conn.commit()
            return {"ok": True, "ts": ts}
        finally:
            conn.close()


def cookie_session_token(handler: BaseHTTPRequestHandler) -> str | None:
    raw = handler.headers.get("Cookie") or ""
    jar = SimpleCookie()
    try:
        jar.load(raw)
    except Exception:
        return None
    morsel = jar.get(SESSION_COOKIE)
    if not morsel or not morsel.value:
        return None
    return morsel.value.strip()


def create_portal_session(username: str) -> str:
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    exp = now + timedelta(seconds=SESSION_MAX_AGE)
    with _db_lock:
        conn = db_connect()
        try:
            conn.execute(
                """
                INSERT INTO portal_sessions (token, username, created_at, expires_at)
                VALUES (?, ?, ?, ?)
                """,
                (token, username, now.isoformat(), exp.isoformat()),
            )
            conn.commit()
        finally:
            conn.close()
    return token


def lookup_portal_session(token: str | None) -> str | None:
    if not token:
        return None
    now = datetime.now(timezone.utc).isoformat()
    with _db_lock:
        conn = db_connect()
        try:
            row = conn.execute(
                """
                SELECT username FROM portal_sessions
                WHERE token=? AND expires_at > ?
                """,
                (token, now),
            ).fetchone()
            return row["username"] if row else None
        finally:
            conn.close()


def delete_portal_session(token: str | None) -> None:
    if not token:
        return
    with _db_lock:
        conn = db_connect()
        try:
            conn.execute("DELETE FROM portal_sessions WHERE token=?", (token,))
            conn.commit()
        finally:
            conn.close()


def session_cookie_header(token: str, clear: bool = False) -> str:
    domain = os.environ.get("PORTAL_COOKIE_DOMAIN", "").strip()
    domain_part = f"; Domain={domain}" if domain else ""
    if clear:
        return (
            f"{SESSION_COOKIE}=; Path=/{domain_part}; HttpOnly; SameSite=Lax; Max-Age=0"
        )
    return (
        f"{SESSION_COOKIE}={token}; Path=/{domain_part}; HttpOnly; SameSite=Lax; "
        f"Max-Age={SESSION_MAX_AGE}"
    )


def instance_of_url(url: str) -> str:
    host = urlparse(url).hostname or url
    return host[8:] if host.startswith("frigate-") else host


def verify_frigate_password(username: str, password: str) -> dict:
    """Ask every Frigate instance whether this user/password pair is valid.

    Returns a report so a failure is never silent:
      result   'ok' | 'unauthorized' | 'unavailable'
      checked  ['cafe=200', 'center11=401', 'sahel=timeout', ...]
      rejected number of instances that explicitly said 401/403
      broken   number of instances that could not answer (down, timeout, 5xx)

    'unauthorized' means at least one instance actively rejected the password
    and none accepted it. When `broken` is also > 0 the answer is only partial:
    the instance holding this account may simply have been unreachable, so the
    caller must surface that instead of flatly blaming the password.
    """
    payload = json.dumps({"user": username, "password": password}).encode("utf-8")
    checked: list[str] = []
    rejected = 0
    broken = 0
    deadline = time.monotonic() + LOGIN_DEADLINE

    for url in AUTH_LOGIN_URLS:
        name = instance_of_url(url)
        if time.monotonic() >= deadline:
            checked.append(f"{name}=skipped")
            broken += 1
            continue
        req = Request(
            url,
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/json",
                # Frigate's own UI sends this on every write; harmless elsewhere.
                "X-CSRF-TOKEN": "1",
                "User-Agent": "portal-api/login",
            },
        )
        try:
            with urlopen(req, timeout=LOGIN_TIMEOUT, context=_SSL_CTX) as resp:
                checked.append(f"{name}={resp.status}")
                if 200 <= resp.status < 300:
                    return {
                        "result": "ok",
                        "checked": checked,
                        "rejected": rejected,
                        "broken": broken,
                    }
                broken += 1
        except HTTPError as exc:
            checked.append(f"{name}={exc.code}")
            if exc.code in (401, 403):
                rejected += 1
            else:
                broken += 1
        except (URLError, TimeoutError, OSError) as exc:
            reason = getattr(exc, "reason", exc) or exc
            checked.append(f"{name}={type(exc).__name__}:{reason}"[:80])
            broken += 1

    return {
        "result": "unauthorized" if rejected else "unavailable",
        "checked": checked,
        "rejected": rejected,
        "broken": broken,
    }


def list_auth_events(limit=50):
    limit = max(1, min(int(limit), 500))
    with _db_lock:
        conn = db_connect()
        try:
            rows = conn.execute(
                """
                SELECT id, ts, event, username, ip, user_agent, success, detail
                FROM auth_events
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def report_cameras(items):
    """Upsert camera status; write camera_events only on status change."""
    ts = now_iso()
    changed = []
    with _db_lock:
        conn = db_connect()
        try:
            for item in items:
                camera = str(item.get("camera") or "").strip()[:80]
                site = str(item.get("site") or "").strip()[:40]
                status = str(item.get("status") or "").strip().lower()
                detail = item.get("detail")
                if detail is not None:
                    detail = str(detail)[:300]
                if not camera or not site or status not in ("ok", "broken", "offline"):
                    continue
                row = conn.execute(
                    "SELECT status FROM camera_status WHERE camera=? AND site=?",
                    (camera, site),
                ).fetchone()
                if row is None:
                    conn.execute(
                        """
                        INSERT INTO camera_status
                          (camera, site, status, first_seen, last_change, last_detail)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (camera, site, status, ts, ts, detail),
                    )
                    event = "broken" if status in ("broken", "offline") else "seen"
                    conn.execute(
                        """
                        INSERT INTO camera_events (ts, event, camera, site, detail)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (ts, event, camera, site, detail),
                    )
                    changed.append({"camera": camera, "site": site, "event": event})
                elif row["status"] != status:
                    conn.execute(
                        """
                        UPDATE camera_status
                        SET status=?, last_change=?, last_detail=?
                        WHERE camera=? AND site=?
                        """,
                        (status, ts, detail, camera, site),
                    )
                    event = (
                        "recovered"
                        if status == "ok"
                        else ("offline" if status == "offline" else "broken")
                    )
                    conn.execute(
                        """
                        INSERT INTO camera_events (ts, event, camera, site, detail)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (ts, event, camera, site, detail),
                    )
                    changed.append({"camera": camera, "site": site, "event": event})
            conn.commit()
            return {"ok": True, "ts": ts, "changed": changed}
        finally:
            conn.close()


def list_broken_cameras():
    with _db_lock:
        conn = db_connect()
        try:
            rows = conn.execute(
                """
                SELECT camera, site, status, first_seen, last_change, last_detail
                FROM camera_status
                WHERE status IN ('broken', 'offline')
                ORDER BY last_change DESC
                """
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def list_camera_events(limit=50):
    limit = max(1, min(int(limit), 500))
    with _db_lock:
        conn = db_connect()
        try:
            rows = conn.execute(
                """
                SELECT id, ts, event, camera, site, detail
                FROM camera_events
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def http_get_json(url: str, timeout: int = 8):
    req = Request(url, headers={"User-Agent": "portal-api/snapshots"})
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_get_bytes(url: str, timeout: int = SNAP_FETCH_TIMEOUT) -> bytes:
    req = Request(url, headers={"User-Agent": "portal-api/snapshots"})
    with urlopen(req, timeout=timeout) as resp:
        data = resp.read()
        ctype = (resp.headers.get("Content-Type") or "").lower()
        if "jpeg" not in ctype and "jpg" not in ctype and not data.startswith(b"\xff\xd8"):
            raise ValueError(f"not jpeg from {url}")
        return data


def list_live_cameras():
    """Return [{site, camera, base}] for cameras with fps > 0."""
    out = []
    for src in FRIGATE_SOURCES:
        try:
            stats = http_get_json(f"{src['base']}/api/stats", timeout=6)
        except Exception:
            continue
        cams = stats.get("cameras") or {}
        for name, cam in cams.items():
            if cam and float(cam.get("camera_fps") or 0) > 0:
                out.append({"site": src["site"], "camera": name, "base": src["base"]})
    return out


def load_manifest_from_disk():
    global _snap_manifest
    path = SNAP_DIR / "manifest.json"
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("tiles"), list):
            with _snap_lock:
                _snap_manifest = data
    except Exception:
        pass


def collect_snapshots():
    """Pick random live cameras, save JPEGs, update manifest. Low load (~8 JPEGs/hour)."""
    global _snap_manifest
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    candidates = list_live_cameras()
    if not candidates:
        return False

    n = min(SNAP_COUNT, len(candidates))
    picked = random.sample(candidates, n)
    tiles = []
    batch = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    half = (n + 1) // 2

    for i, item in enumerate(picked):
        side = "left" if i < half else "right"
        cam = item["camera"]
        site = item["site"]
        fname = f"{batch}_{side}_{i}_{site}_{cam}.jpg".replace("/", "_")
        url = f"{item['base']}/api/{quote(cam, safe='')}/latest.jpg"
        try:
            data = http_get_bytes(url)
            (SNAP_DIR / fname).write_bytes(data)
            tiles.append(
                {
                    "side": side,
                    "site": site,
                    "camera": cam,
                    "file": fname,
                    "url": f"/api/snapshots/file/{fname}",
                }
            )
        except (URLError, HTTPError, TimeoutError, ValueError, OSError):
            continue

    if len(tiles) < 2:
        return False

    # Drop older files not in new set
    keep = {t["file"] for t in tiles}
    for p in SNAP_DIR.glob("*.jpg"):
        if p.name not in keep:
            try:
                p.unlink()
            except OSError:
                pass

    manifest = {"updated_at": now_iso(), "tiles": tiles, "interval_sec": SNAP_INTERVAL_SEC}
    (SNAP_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with _snap_lock:
        _snap_manifest = manifest
    return True


def snapshot_worker():
    # First run after short delay so Frigates are up
    time.sleep(15)
    while True:
        try:
            collect_snapshots()
        except Exception:
            pass
        try:
            purge_old_data()
        except Exception:
            pass
        time.sleep(max(60, SNAP_INTERVAL_SEC))


def get_manifest():
    with _snap_lock:
        return dict(_snap_manifest)


def client_ip(handler: BaseHTTPRequestHandler) -> str:
    xff = handler.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()
    return handler.headers.get("X-Real-IP") or handler.client_address[0]


def read_json(handler: BaseHTTPRequestHandler):
    length = int(handler.headers.get("Content-Length") or 0)
    raw = handler.rfile.read(length) if length else b"{}"
    try:
        return json.loads(raw.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return None


class Handler(BaseHTTPRequestHandler):
    def _json(self, code, payload, extra_headers=None):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        if extra_headers:
            for key, val in extra_headers:
                self.send_header(key, val)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, code, data: bytes, content_type: str, cache: str = "public, max-age=300"):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", cache)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        qs = parse_qs(parsed.query)

        if path in ("/", "/api/host-metrics"):
            try:
                self._json(200, host_snapshot())
            except Exception as exc:
                self._json(500, {"error": str(exc)})
            return

        if path == "/api/session":
            user = lookup_portal_session(cookie_session_token(self))
            if not user:
                self._json(401, {"ok": False})
                return
            self._json(200, {"ok": True, "username": user})
            return

        if path == "/api/audit":
            limit = (qs.get("limit") or ["50"])[0]
            try:
                self._json(200, {"events": list_auth_events(limit)})
            except Exception as exc:
                self._json(500, {"error": str(exc)})
            return

        if path == "/api/cameras/broken":
            try:
                self._json(200, {"cameras": list_broken_cameras()})
            except Exception as exc:
                self._json(500, {"error": str(exc)})
            return

        if path == "/api/cameras/events":
            limit = (qs.get("limit") or ["50"])[0]
            try:
                self._json(200, {"events": list_camera_events(limit)})
            except Exception as exc:
                self._json(500, {"error": str(exc)})
            return

        if path == "/api/snapshots":
            self._json(200, get_manifest())
            return

        if path == "/api/watchdog":
            try:
                if not WATCHDOG_STATUS.is_file():
                    self._json(200, {"available": False})
                    return
                data = json.loads(WATCHDOG_STATUS.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    self._json(200, {"available": False})
                    return
                data.setdefault("available", True)
                self._json(200, data)
            except Exception as exc:
                self._json(500, {"error": str(exc)})
            return

        if path.startswith("/api/snapshots/file/"):
            fname = path.split("/api/snapshots/file/", 1)[-1]
            # safety: only basename jpg
            fname = Path(fname).name
            if not fname.endswith(".jpg") or ".." in fname:
                self.send_error(400)
                return
            fpath = SNAP_DIR / fname
            if not fpath.is_file():
                self.send_error(404)
                return
            try:
                self._file(200, fpath.read_bytes(), "image/jpeg")
            except OSError as exc:
                self._json(500, {"error": str(exc)})
            return

        self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        if path == "/api/portal-login":
            data = read_json(self)
            if data is None:
                self._json(400, {"error": "invalid json"})
                return
            username = str(data.get("username") or data.get("user") or "").strip()[:80]
            password = str(data.get("password") or "")
            if not username or not password:
                self._json(400, {"error": "username and password required"})
                return
            report = verify_frigate_password(username, password)
            result = report["result"]
            trace = " ".join(report["checked"])
            # Always leave a trace: `docker compose logs portal-metrics`
            print(f"[login] user={username} result={result} {trace}", flush=True)
            if result == "ok":
                token = create_portal_session(username)
                insert_auth_event(
                    "login",
                    username,
                    client_ip(self),
                    self.headers.get("User-Agent", ""),
                    True,
                    trace,
                )
                self._json(
                    200,
                    {"ok": True, "username": username},
                    extra_headers=[("Set-Cookie", session_cookie_header(token))],
                )
                return
            insert_auth_event(
                "login_failed",
                username,
                client_ip(self),
                self.headers.get("User-Agent", ""),
                False,
                f"{result}: {trace}",
            )
            if result == "unauthorized":
                self._json(
                    401,
                    {
                        "ok": False,
                        "error": "bad credentials",
                        # >0 means the answer is partial: some instance that may
                        # hold this account never replied.
                        "unreachable": report["broken"],
                        "rejected": report["rejected"],
                    },
                )
            else:
                self._json(
                    503,
                    {
                        "ok": False,
                        "error": "auth backend unavailable",
                        "unreachable": report["broken"],
                    },
                )
            return

        if path == "/api/portal-logout":
            token = cookie_session_token(self)
            user = lookup_portal_session(token) or ""
            delete_portal_session(token)
            if user:
                insert_auth_event(
                    "logout",
                    user,
                    client_ip(self),
                    self.headers.get("User-Agent", ""),
                    True,
                    "portal session",
                )
            self._json(
                200,
                {"ok": True},
                extra_headers=[("Set-Cookie", session_cookie_header("", clear=True))],
            )
            return

        if path == "/api/audit":
            data = read_json(self)
            if data is None:
                self._json(400, {"error": "invalid json"})
                return
            event = (data.get("event") or "").strip().lower()
            if event not in ("login", "logout", "login_failed"):
                self._json(400, {"error": "event must be login|logout|login_failed"})
                return
            username = (data.get("username") or "").strip()[:80]
            success = bool(data.get("success", event != "login_failed"))
            detail = data.get("detail")
            if detail is not None:
                detail = str(detail)[:300]
            try:
                result = insert_auth_event(
                    event=event,
                    username=username,
                    ip=client_ip(self),
                    user_agent=self.headers.get("User-Agent", ""),
                    success=success,
                    detail=detail,
                )
                self._json(200, result)
            except Exception as exc:
                self._json(500, {"error": str(exc)})
            return

        if path == "/api/cameras/report":
            data = read_json(self)
            if data is None or not isinstance(data.get("cameras"), list):
                self._json(400, {"error": "cameras array required"})
                return
            try:
                self._json(200, report_cameras(data["cameras"]))
            except Exception as exc:
                self._json(500, {"error": str(exc)})
            return

        # Manual refresh for admins/ops (optional)
        if path == "/api/snapshots/refresh":
            try:
                ok = collect_snapshots()
                self._json(200 if ok else 503, get_manifest() if ok else {"error": "no snapshots"})
            except Exception as exc:
                self._json(500, {"error": str(exc)})
            return

        self.send_error(404)

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    init_db()
    try:
        purge_old_data()
    except Exception:
        pass
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    load_manifest_from_disk()
    threading.Thread(target=snapshot_worker, name="snap-worker", daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", 9090), Handler).serve_forever()
