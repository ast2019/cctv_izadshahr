#!/usr/bin/env python3
"""Portal API: host metrics + SQLite (auth audit + camera health log)."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import json
import os
import sqlite3
import threading

PROC = "/host/proc"
DB_PATH = Path(os.environ.get("PORTAL_DB", "/data/portal.db"))
LOAD_RATIO_LIMIT = 0.5
MEM_PERCENT_LIMIT = 30.0

_db_lock = threading.Lock()


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
                """
            )
            conn.commit()
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
    def _json(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

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

        self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

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

        self.send_error(404)

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    init_db()
    HTTPServer(("0.0.0.0", 9090), Handler).serve_forever()
