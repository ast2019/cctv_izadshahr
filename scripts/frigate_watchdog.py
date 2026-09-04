#!/usr/bin/env python3
"""Recover hung Frigate instances and the portal when video stops loading.

Docker `restart: unless-stopped` only helps when the process *exits*. A hung
Frigate still looks "Up" while /api/stats times out and latest.jpg never
arrives. This loop probes the unauthenticated internal API (port 5000) and
go2rtc-backed snapshots, then restarts only the stuck container.

Safety:
  * startup grace (~90s) — do not judge a just-started instance
  * consecutive failures before restart
  * per-instance cooldown and hourly restart cap
  * never mass-restart every Frigate in one cycle (likely a host/network outage)
  * the `temp` review instance is never treated as a hang (broken cams expected)
"""
from __future__ import annotations

from datetime import datetime, timezone
from http.client import HTTPConnection
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen
import json
import os
import socket
import sys
import time
import traceback

INSTANCES = [
    {"id": "cafe", "container": "frigate-cafe", "base": "http://frigate-cafe:5000"},
    {"id": "center11", "container": "frigate-center11", "base": "http://frigate-center11:5000"},
    {"id": "center22", "container": "frigate-center22", "base": "http://frigate-center22:5000"},
    {"id": "restaurant", "container": "frigate-restaurant", "base": "http://frigate-restaurant:5000"},
    {"id": "sahel", "container": "frigate-sahel", "base": "http://frigate-sahel:5000"},
    {"id": "villa", "container": "frigate-villa", "base": "http://frigate-villa:5000"},
    {"id": "mahoote", "container": "frigate-mahoote", "base": "http://frigate-mahoote:5000"},
    {"id": "tasisat", "container": "frigate-tasisat", "base": "http://frigate-tasisat:5000"},
    {"id": "entezamat", "container": "frigate-entezamat", "base": "http://frigate-entezamat:5000"},
    {"id": "anbar", "container": "frigate-anbar", "base": "http://frigate-anbar:5000"},
    {"id": "khanedari", "container": "frigate-khanedari", "base": "http://frigate-khanedari:5000"},
    {
        "id": "temp",
        "container": "frigate-temp",
        "base": "http://frigate-temp:5000",
        # Scratch instance for unidentified/broken cams — never treat as a hang.
        "ignore_dead_video": True,
        "exclude_from_mass_outage": True,
    },
]

# Cameras here are expected to be broken/offline. Zero video is not a system hang.
REVIEW_INSTANCE_IDS = frozenset(
    inst["id"] for inst in INSTANCES if inst.get("ignore_dead_video")
)

PORTAL_CONTAINER = "cctv-portal"
PORTAL_HEALTH_URL = os.environ.get("PORTAL_HEALTH_URL", "http://portal/health/cafe/")

CYCLE_SEC = int(os.environ.get("WATCHDOG_CYCLE_SEC", "45"))
STARTUP_GRACE_SEC = int(os.environ.get("WATCHDOG_STARTUP_GRACE_SEC", "90"))
FAIL_THRESHOLD = int(os.environ.get("WATCHDOG_FAIL_THRESHOLD", "3"))
COOLDOWN_SEC = int(os.environ.get("WATCHDOG_COOLDOWN_SEC", "300"))
MAX_RESTARTS_PER_HOUR = int(os.environ.get("WATCHDOG_MAX_RESTARTS_HOUR", "3"))
MAX_FRIGATE_RESTARTS_PER_CYCLE = int(os.environ.get("WATCHDOG_MAX_PER_CYCLE", "2"))
MASS_FAIL_RATIO = float(os.environ.get("WATCHDOG_MASS_FAIL_RATIO", "0.5"))
API_TIMEOUT = int(os.environ.get("WATCHDOG_API_TIMEOUT", "8"))
SNAP_TIMEOUT = int(os.environ.get("WATCHDOG_SNAP_TIMEOUT", "10"))
SNAP_PROBES = int(os.environ.get("WATCHDOG_SNAP_PROBES", "3"))
RESTART_TIMEOUT_SEC = int(os.environ.get("WATCHDOG_RESTART_T", "30"))

DATA_DIR = Path(os.environ.get("WATCHDOG_DATA", "/data"))
STATE_PATH = DATA_DIR / "state.json"
STATUS_PATH = DATA_DIR / "status.json"
DOCKER_SOCK = os.environ.get("DOCKER_SOCK", "/var/run/docker.sock")
DOCKER_API = os.environ.get("DOCKER_API", "v1.41")

HANG_VERDICTS = frozenset({"unresponsive", "dead_video"})


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_iso(ts: str | None) -> float | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def http_get(url: str, timeout: int) -> tuple[int, bytes, str]:
    req = Request(url, headers={"User-Agent": "frigate-watchdog"})
    with urlopen(req, timeout=timeout) as resp:
        data = resp.read()
        ctype = (resp.headers.get("Content-Type") or "").lower()
        return resp.status, data, ctype


def http_get_json(url: str, timeout: int) -> dict:
    _status, data, _ctype = http_get(url, timeout)
    return json.loads(data.decode("utf-8") or "{}")


def is_jpeg(data: bytes, ctype: str) -> bool:
    return "jpeg" in ctype or "jpg" in ctype or data.startswith(b"\xff\xd8")


def live_camera_names(stats: dict) -> list[str]:
    cams = stats.get("cameras") or {}
    live = []
    for name, cam in cams.items():
        if not isinstance(cam, dict):
            continue
        try:
            fps = float(cam.get("camera_fps") or 0)
        except (TypeError, ValueError):
            fps = 0.0
        if fps > 0:
            live.append(name)
    return live


def service_uptime_sec(stats: dict) -> float:
    svc = stats.get("service") or {}
    try:
        return float(svc.get("uptime") or 0)
    except (TypeError, ValueError):
        return 0.0


def classify_probe(
    probe: dict,
    grace_sec: int = STARTUP_GRACE_SEC,
    ignore_dead_video: bool = False,
) -> dict:
    """Turn a probe result into a verdict. Pure — used by tests."""
    if not probe.get("api_ok"):
        return {
            "verdict": "unresponsive",
            "detail": probe.get("api_error") or "api timeout/error",
        }

    names = list(probe.get("camera_names") or [])
    live = list(probe.get("live_names") or [])
    snaps = list(probe.get("snapshots") or [])
    snap_ok = sum(1 for s in snaps if s.get("ok"))
    uptime = float(probe.get("uptime_sec") or 0)

    if not names:
        return {"verdict": "empty", "detail": "no cameras in stats"}

    if live or snap_ok > 0:
        return {
            "verdict": "ok",
            "detail": f"{len(live)}/{len(names)} live · {snap_ok}/{len(snaps)} jpeg",
        }

    if uptime and uptime < grace_sec:
        return {
            "verdict": "starting",
            "detail": f"uptime {int(uptime)}s < grace {grace_sec}s",
        }

    if ignore_dead_video:
        return {
            "verdict": "review",
            "detail": f"0/{len(names)} live · review instance (broken cams ignored)",
        }

    return {
        "verdict": "dead_video",
        "detail": f"0/{len(names)} live · {snap_ok}/{len(snaps)} jpeg",
    }


def hourly_restart_count(restarts: list, now_ts: float) -> int:
    cutoff = now_ts - 3600
    n = 0
    for item in restarts or []:
        ts = parse_iso(item.get("ts") if isinstance(item, dict) else None)
        if ts is not None and ts >= cutoff:
            n += 1
    return n


def restart_decision(
    *,
    verdict: str,
    consecutive_bad: int,
    last_restart: str | None,
    restarts: list,
    now_ts: float,
    fail_threshold: int = FAIL_THRESHOLD,
    cooldown_sec: int = COOLDOWN_SEC,
    max_per_hour: int = MAX_RESTARTS_PER_HOUR,
) -> tuple[bool, str]:
    if verdict not in HANG_VERDICTS:
        return False, "healthy_or_wait"
    if consecutive_bad < fail_threshold:
        return False, f"need {fail_threshold} consecutive fails (have {consecutive_bad})"
    last_ts = parse_iso(last_restart)
    if last_ts is not None and (now_ts - last_ts) < cooldown_sec:
        return False, f"cooldown {int(cooldown_sec - (now_ts - last_ts))}s left"
    if hourly_restart_count(restarts, now_ts) >= max_per_hour:
        return False, f"hourly cap {max_per_hour} reached"
    return True, f"{verdict} x{consecutive_bad}"


def mass_outage(verdicts: list[str], ratio: float = MASS_FAIL_RATIO) -> bool:
    hang = [v for v in verdicts if v in HANG_VERDICTS]
    if len(verdicts) < 2:
        return False
    return len(hang) / len(verdicts) >= ratio


def mass_outage_verdicts(probes: list[dict]) -> list[str]:
    """Exclude review/temp instances so broken scratch cams cannot look like a host outage."""
    out = []
    for p in probes:
        if p.get("id") in REVIEW_INSTANCE_IDS or p.get("exclude_from_mass_outage"):
            continue
        out.append(p.get("verdict") or "unresponsive")
    return out


def pick_snap_targets(camera_names: list[str], live_names: list[str], limit: int) -> list[str]:
    ordered = list(live_names) + [n for n in camera_names if n not in live_names]
    # unique preserve order
    seen = set()
    out = []
    for n in ordered:
        if n in seen:
            continue
        seen.add(n)
        out.append(n)
        if len(out) >= limit:
            break
    return out


class DockerUnix:
    def __init__(self, sock_path: str = DOCKER_SOCK, api: str = DOCKER_API):
        self.sock_path = sock_path
        self.api = api

    def _request(self, method: str, path: str, timeout: int = 60) -> tuple[int, bytes]:
        conn = _UnixHTTPConnection(self.sock_path, timeout=timeout)
        try:
            conn.request(method, path, headers={"Host": "localhost", "Content-Length": "0"})
            resp = conn.getresponse()
            body = resp.read()
            return resp.status, body
        finally:
            conn.close()

    def inspect(self, name: str) -> dict | None:
        status, body = self._request("GET", f"/{self.api}/containers/{name}/json", timeout=15)
        if status == 404:
            return None
        if status >= 400:
            raise RuntimeError(f"docker inspect {name}: HTTP {status} {body[:200]!r}")
        return json.loads(body.decode("utf-8"))

    def restart(self, name: str, t: int = RESTART_TIMEOUT_SEC) -> None:
        status, body = self._request(
            "POST", f"/{self.api}/containers/{name}/restart?t={t}", timeout=t + 20
        )
        if status not in (204, 200):
            raise RuntimeError(f"docker restart {name}: HTTP {status} {body[:200]!r}")


class _UnixHTTPConnection(HTTPConnection):
    def __init__(self, unix_path: str, timeout: int = 60):
        super().__init__("localhost", timeout=timeout)
        self.unix_path = unix_path

    def connect(self):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect(self.unix_path)
        self.sock = sock


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def save_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def probe_instance(inst: dict) -> dict:
    base = inst["base"]
    probe = {
        "id": inst["id"],
        "container": inst["container"],
        "api_ok": False,
        "api_error": None,
        "uptime_sec": 0,
        "camera_names": [],
        "live_names": [],
        "snapshots": [],
    }
    try:
        stats = http_get_json(f"{base}/api/stats", API_TIMEOUT)
    except Exception as exc:
        probe["api_error"] = f"{type(exc).__name__}: {exc}"
        classified = classify_probe(
            probe, ignore_dead_video=bool(inst.get("ignore_dead_video"))
        )
        probe.update(classified)
        return probe

    probe["api_ok"] = True
    probe["uptime_sec"] = service_uptime_sec(stats)
    cams = stats.get("cameras") or {}
    probe["camera_names"] = [n for n in cams.keys() if isinstance(cams.get(n), dict)]
    probe["live_names"] = live_camera_names(stats)

    for name in pick_snap_targets(probe["camera_names"], probe["live_names"], SNAP_PROBES):
        url = f"{base}/api/{quote(name, safe='')}/latest.jpg"
        try:
            _status, data, ctype = http_get(url, SNAP_TIMEOUT)
            ok = bool(data) and is_jpeg(data, ctype)
            probe["snapshots"].append({"camera": name, "ok": ok})
        except Exception as exc:
            probe["snapshots"].append(
                {"camera": name, "ok": False, "error": f"{type(exc).__name__}"}
            )

    classified = classify_probe(
        probe, ignore_dead_video=bool(inst.get("ignore_dead_video"))
    )
    probe.update(classified)
    return probe


def probe_portal() -> dict:
    try:
        status, _data, _ctype = http_get(PORTAL_HEALTH_URL, API_TIMEOUT)
        if status in (200, 204, 401, 403):
            return {"verdict": "ok", "detail": f"HTTP {status}"}
        return {"verdict": "unresponsive", "detail": f"HTTP {status}"}
    except Exception as exc:
        return {"verdict": "unresponsive", "detail": f"{type(exc).__name__}: {exc}"}


def container_age_sec(info: dict | None) -> float | None:
    if not info:
        return None
    started = ((info.get("State") or {}).get("StartedAt") or "").strip()
    if not started or started.startswith("0001"):
        return None
    ts = parse_iso(started)
    if ts is None:
        return None
    return max(0.0, time.time() - ts)


def default_inst_state() -> dict:
    return {
        "consecutive_bad": 0,
        "last_ok": None,
        "last_restart": None,
        "restarts": [],
    }


def apply_probe_to_state(st: dict, verdict: str, now: str) -> dict:
    out = dict(st)
    if verdict in HANG_VERDICTS:
        out["consecutive_bad"] = int(out.get("consecutive_bad") or 0) + 1
    else:
        out["consecutive_bad"] = 0
        if verdict == "ok":
            out["last_ok"] = now
    return out


def record_restart(st: dict, now: str, reason: str) -> dict:
    out = dict(st)
    out["last_restart"] = now
    out["consecutive_bad"] = 0
    hist = list(out.get("restarts") or [])
    hist.append({"ts": now, "reason": reason})
    out["restarts"] = hist[-20:]
    return out


def log(msg: str) -> None:
    print(f"{now_iso()} {msg}", flush=True)


def run_cycle(docker: DockerUnix, state: dict) -> dict:
    now = now_iso()
    now_ts = time.time()
    inst_state = state.setdefault("instances", {})
    portal_state = state.setdefault("portal", default_inst_state())
    actions = list(state.get("recent_actions") or [])

    probes = []
    for inst in INSTANCES:
        try:
            probes.append(probe_instance(inst))
        except Exception as exc:
            probes.append(
                {
                    "id": inst["id"],
                    "container": inst["container"],
                    "verdict": "unresponsive",
                    "detail": f"probe crash: {exc}",
                    "api_ok": False,
                    "camera_names": [],
                    "live_names": [],
                    "snapshots": [],
                    "uptime_sec": 0,
                }
            )

    recording_verdicts = mass_outage_verdicts(probes)
    skip_mass = mass_outage(recording_verdicts)
    if skip_mass:
        log(
            f"mass outage ({sum(1 for v in recording_verdicts if v in HANG_VERDICTS)}/"
            f"{len(recording_verdicts)} recording instances hung) "
            "— skip Frigate restarts this cycle"
        )

    restarted = 0
    status_instances = []

    for probe in probes:
        sid = probe["id"]
        st = inst_state.get(sid) or default_inst_state()
        st = apply_probe_to_state(st, probe["verdict"], now)

        want, why = restart_decision(
            verdict=probe["verdict"],
            consecutive_bad=int(st.get("consecutive_bad") or 0),
            last_restart=st.get("last_restart"),
            restarts=st.get("restarts") or [],
            now_ts=now_ts,
        )
        if sid in REVIEW_INSTANCE_IDS:
            want = False
            why = "review_instance_ignored"

        action = None
        if want and skip_mass:
            action = "skipped_mass_outage"
        elif want and restarted >= MAX_FRIGATE_RESTARTS_PER_CYCLE:
            action = "deferred_cycle_cap"
        elif want:
            info = None
            try:
                info = docker.inspect(probe["container"])
            except Exception as exc:
                log(f"inspect {probe['container']} failed: {exc}")
            age = container_age_sec(info)
            restarting = bool((info or {}).get("State", {}).get("Restarting"))
            if info is None:
                action = "missing_container"
            elif restarting:
                action = "already_restarting"
            elif age is not None and age < STARTUP_GRACE_SEC:
                action = f"startup_grace {int(age)}s"
            else:
                try:
                    docker.restart(probe["container"])
                    st = record_restart(st, now, probe["detail"])
                    restarted += 1
                    action = "restarted"
                    actions.append(
                        {
                            "ts": now,
                            "target": probe["container"],
                            "action": "restart",
                            "reason": probe["detail"],
                        }
                    )
                    log(f"RESTART {probe['container']} ({probe['verdict']}: {probe['detail']})")
                except Exception as exc:
                    action = f"restart_failed: {exc}"
                    log(action)

        inst_state[sid] = st
        status_instances.append(
            {
                "id": sid,
                "container": probe["container"],
                "verdict": probe["verdict"],
                "detail": probe["detail"],
                "live": len(probe.get("live_names") or []),
                "cameras": len(probe.get("camera_names") or []),
                "consecutive_bad": st.get("consecutive_bad") or 0,
                "last_restart": st.get("last_restart"),
                "action": action or why,
            }
        )
        if probe["verdict"] in HANG_VERDICTS:
            log(f"{sid}: {probe['verdict']} — {probe['detail']} ({action or why})")

    portal = probe_portal()
    portal_state = apply_probe_to_state(portal_state, portal["verdict"], now)
    portal_action = None
    want_portal, portal_why = restart_decision(
        verdict=portal["verdict"],
        consecutive_bad=int(portal_state.get("consecutive_bad") or 0),
        last_restart=portal_state.get("last_restart"),
        restarts=portal_state.get("restarts") or [],
        now_ts=now_ts,
    )
    frigates_ok = sum(
        1 for p in probes if p.get("id") not in REVIEW_INSTANCE_IDS and p.get("verdict") == "ok"
    )
    if want_portal and frigates_ok >= 2:
        try:
            docker.restart(PORTAL_CONTAINER)
            portal_state = record_restart(portal_state, now, portal["detail"])
            portal_action = "restarted"
            actions.append(
                {
                    "ts": now,
                    "target": PORTAL_CONTAINER,
                    "action": "restart",
                    "reason": portal["detail"],
                }
            )
            log(f"RESTART {PORTAL_CONTAINER} ({portal['detail']})")
        except Exception as exc:
            portal_action = f"restart_failed: {exc}"
            log(portal_action)
    elif want_portal:
        portal_action = "skipped_frigates_also_down"
    else:
        portal_action = portal_why

    state["instances"] = inst_state
    state["portal"] = portal_state
    state["recent_actions"] = actions[-40:]
    state["updated_at"] = now

    status = {
        "updated_at": now,
        "available": True,
        "mass_outage": skip_mass,
        "portal": {
            "verdict": portal["verdict"],
            "detail": portal["detail"],
            "consecutive_bad": portal_state.get("consecutive_bad") or 0,
            "last_restart": portal_state.get("last_restart"),
            "action": portal_action,
        },
        "instances": status_instances,
        "recent_actions": state["recent_actions"][-10:],
        "policy": {
            "cycle_sec": CYCLE_SEC,
            "fail_threshold": FAIL_THRESHOLD,
            "cooldown_sec": COOLDOWN_SEC,
            "startup_grace_sec": STARTUP_GRACE_SEC,
            "max_restarts_per_hour": MAX_RESTARTS_PER_HOUR,
        },
    }
    save_json(STATUS_PATH, status)
    save_json(STATE_PATH, state)
    return status


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    docker = DockerUnix()
    state = load_json(STATE_PATH, {})
    log(
        f"watchdog start cycle={CYCLE_SEC}s threshold={FAIL_THRESHOLD} "
        f"grace={STARTUP_GRACE_SEC}s cooldown={COOLDOWN_SEC}s"
    )
    time.sleep(int(os.environ.get("WATCHDOG_INITIAL_SLEEP", "20")))
    while True:
        try:
            run_cycle(docker, state)
        except Exception:
            log("cycle error:\n" + traceback.format_exc())
        time.sleep(max(15, CYCLE_SEC))


if __name__ == "__main__":
    sys.exit(main() or 0)
