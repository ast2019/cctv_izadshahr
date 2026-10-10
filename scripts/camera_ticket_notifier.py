#!/usr/bin/env python3
"""Notify the IT task board when a Frigate camera stays offline.

One-way: POST /api/v1/tasks only. Does not close tasks or poll IT status.

Safety:
  * disabled unless IT_TASKS_ENABLED=1 and API key is set
  * dry-run logs the payload without calling IT
  * consecutive fps=0 samples before ticketing (debounce)
  * startup grace per Frigate instance
  * offline must persist ~30 minutes (FAIL_THRESHOLD cycles) before ticketing
  * optional IT_TASKS_BOOTSTRAP_SILENT=1 skips tickets on first site scan
  * migrates old bootstrap-silent state so long-offline cams can be ticketed
  * stable external_id so IT can dedupe; local ticketed flag avoids spam
  * temp / review instances are never ticketed
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import json
import os
import sys
import time
import traceback

INSTANCES = [
    {"id": "cafe", "base": "http://frigate-cafe:5000"},
    {"id": "center11", "base": "http://frigate-center11:5000"},
    {"id": "center22", "base": "http://frigate-center22:5000"},
    {"id": "restaurant", "base": "http://frigate-restaurant:5000"},
    {"id": "sahel", "base": "http://frigate-sahel:5000"},
    {"id": "villa", "base": "http://frigate-villa:5000"},
    {"id": "mahoote", "base": "http://frigate-mahoote:5000"},
    {"id": "tasisat", "base": "http://frigate-tasisat:5000"},
    {"id": "entezamat", "base": "http://frigate-entezamat:5000"},
    {"id": "anbar", "base": "http://frigate-anbar:5000"},
    {"id": "khanedari", "base": "http://frigate-khanedari:5000"},
]

# Scratch / review — broken cams expected; never create IT tickets.
SKIP_INSTANCE_IDS = frozenset({"temp"})

# Persian section names (keep in sync with portal/js/sites.js titles).
SITE_TITLES = {
    "cafe": "کافه",
    "center11": "پذیرش و ورودی مجتمع",
    "restaurant": "رستوران",
    "sahel": "ساحل",
    "villa": "ویلاها",
    "mahoote": "محوطه",
    "center22": "پارکینگ",
    "tasisat": "تاسیسات",
    "entezamat": "انتظامات",
    "anbar": "انبار",
    "khanedari": "خانه‌داری",
    "temp": "موقت — بررسی دوربین‌ها",
}

CYCLE_SEC = int(os.environ.get("IT_TASKS_CYCLE_SEC", "60"))
# Default 30 × 60s ≈ 30 minutes of sustained outage before creating an IT task.
FAIL_THRESHOLD = int(os.environ.get("IT_TASKS_FAIL_THRESHOLD", "30"))
STARTUP_GRACE_SEC = int(os.environ.get("IT_TASKS_STARTUP_GRACE_SEC", "90"))
API_TIMEOUT = int(os.environ.get("IT_TASKS_API_TIMEOUT", "8"))
# Keep short so LAN timeout fails over to public quickly.
POST_TIMEOUT = int(os.environ.get("IT_TASKS_POST_TIMEOUT", "8"))

ENABLED = os.environ.get("IT_TASKS_ENABLED", "0").strip() in ("1", "true", "yes", "on")
DRY_RUN = os.environ.get("IT_TASKS_DRY_RUN", "0").strip() in ("1", "true", "yes", "on")
# Legacy: if 1, first scan of a site marks offline cams ticketed without POSTing.
BOOTSTRAP_SILENT = os.environ.get("IT_TASKS_BOOTSTRAP_SILENT", "0").strip() in (
    "1",
    "true",
    "yes",
    "on",
)

# Prefer LAN IT host; fall back to public IP if unreachable / 5xx.
DEFAULT_BASE_URLS = (
    "http://192.168.0.90:5000/api/v1",
    "http://188.121.144.90:5000/api/v1",
)
PRIORITY = os.environ.get("IT_TASKS_PRIORITY", "high").strip() or "high"


def normalize_api_key(raw: str) -> str:
    """IT Bearer expects the raw secret, not `ClientName:secret`.

    Runtime evidence: `CCTVizad:<secret>` → 401; bare `<secret>` → 201.
    """
    key = (raw or "").strip()
    if not key:
        return ""
    if ":" in key:
        client, _, secret = key.partition(":")
        secret = secret.strip()
        # Only strip when it looks like ClientName:secret (not a sk_… token).
        if client.strip() and secret and not client.strip().lower().startswith("sk_"):
            return secret
    return key


API_KEY = normalize_api_key(os.environ.get("IT_TASKS_API_KEY", ""))
# Business default: مسئول فرجی، همکاران بهرامی و صحراگرد (IT usernames).
ASSIGNEE = os.environ.get("IT_TASKS_ASSIGNEE", "faraji").strip()
# Display names for task description (Persian).
COLLABORATOR_LABELS = os.environ.get(
    "IT_TASKS_COLLABORATOR_LABELS", "بهرامی، صحراگرد"
).strip()
COLLABORATORS = [
    p.strip()
    for p in os.environ.get("IT_TASKS_COLLABORATORS", "bahrami,sahragard").split(",")
    if p.strip()
]

DATA_DIR = Path(os.environ.get("IT_TASKS_DATA", "/data"))
STATE_PATH = DATA_DIR / "state.json"


def parse_base_urls(
    raw_list: str | None = None,
    raw_single: str | None = None,
) -> list[str]:
    """Ordered IT API bases: try first, fail over to the next on outage."""
    if raw_list is None:
        raw_list = os.environ.get("IT_TASKS_BASE_URLS", "")
    if raw_single is None:
        raw_single = os.environ.get("IT_TASKS_BASE_URL", "")
    urls: list[str] = []
    seen: set[str] = set()
    for part in (raw_list or "").split(","):
        u = part.strip().rstrip("/")
        if u and u not in seen:
            seen.add(u)
            urls.append(u)
    if not urls:
        single = (raw_single or "").strip().rstrip("/")
        if single:
            urls.append(single)
    if not urls:
        urls = [u.rstrip("/") for u in DEFAULT_BASE_URLS]
    return urls


BASE_URLS = parse_base_urls()
# Kept for log compatibility / single-URL callers.
BASE_URL = BASE_URLS[0]


def should_failover_status(status: int) -> bool:
    """Retry next base on gateway / service-unavailable style responses."""
    return status in (502, 503, 504) or status >= 520


def is_permanent_client_error(status: int) -> bool:
    """Auth/validation errors will not succeed on retry with the same payload."""
    return status in (400, 401, 403)


def env_csv_pairs(name: str) -> frozenset[str]:
    """Parse site:camera,... into frozenset of 'site:camera' keys."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return frozenset()
    out = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        out.add(part.lower())
    return frozenset(out)


ALLOWLIST = env_csv_pairs("IT_TASKS_ALLOWLIST")
DENYLIST = env_csv_pairs("IT_TASKS_DENYLIST")


def log(msg: str) -> None:
    print(f"[camera-tickets] {msg}", flush=True)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return now_utc().isoformat()


def local_ts(dt: datetime | None = None) -> str:
    """Server-local wall clock for task descriptions."""
    dt = dt or datetime.now().astimezone()
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def camera_key(site: str, camera: str) -> str:
    return f"{site}:{camera}"


def external_id(site: str, camera: str) -> str:
    return f"camera-{site}-{camera}-offline"


def can_ticket(site: str, camera: str) -> bool:
    key = camera_key(site, camera).lower()
    if site in SKIP_INSTANCE_IDS:
        return False
    if DENYLIST and key in DENYLIST:
        return False
    if ALLOWLIST and key not in ALLOWLIST:
        return False
    return True


def posting_allowed() -> bool:
    return ENABLED and bool(API_KEY) and not DRY_RUN


def service_uptime_sec(stats: dict) -> float:
    svc = stats.get("service") or {}
    try:
        return float(svc.get("uptime") or 0)
    except (TypeError, ValueError):
        return 0.0


def parse_camera_fps(stats: dict) -> dict[str, float]:
    """Return {camera_name: fps} for cameras present in stats."""
    cams = stats.get("cameras") or {}
    out: dict[str, float] = {}
    for name, cam in cams.items():
        if not isinstance(cam, dict):
            continue
        try:
            fps = float(cam.get("camera_fps") or 0)
        except (TypeError, ValueError):
            fps = 0.0
        out[str(name)] = fps
    return out


def unlock_bootstrap_silent_cameras(cams: dict) -> int:
    """Re-open cams that were marked ticketed without ever posting to IT.

    Old default bootstrap_silent set ticketed=True with no last_task_id /
    last_error, so long-offline cameras never reached the board. Reset them
    and restart the outage timer so they can ticket after FAIL_THRESHOLD.
    """
    unlocked = 0
    for _key, st in cams.items():
        if not isinstance(st, dict):
            continue
        if (
            st.get("ticketed")
            and not st.get("last_task_id")
            and not st.get("last_error")
            and st.get("status") in ("broken", "offline", "unknown")
        ):
            st["ticketed"] = False
            st["fail_streak"] = 0
            st["post_fail_streak"] = 0
            unlocked += 1
    return unlocked


def load_state(path: Path = STATE_PATH) -> dict:
    empty = {"bootstrapped_sites": [], "cameras": {}}
    if not path.exists():
        return empty
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
    except (OSError, json.JSONDecodeError):
        return empty
    if not isinstance(data, dict):
        return empty
    cams = data.get("cameras")
    if not isinstance(cams, dict):
        cams = {}
    sites = data.get("bootstrapped_sites")
    if not isinstance(sites, list):
        # Migrate legacy boolean flag.
        sites = list({k.split(":")[0] for k in cams}) if data.get("bootstrapped") else []
    unlocked = unlock_bootstrap_silent_cameras(cams)
    if unlocked:
        log(f"migrated {unlocked} bootstrap-silent camera(s) back to watch queue")
    return {
        "bootstrapped_sites": [str(s) for s in sites],
        "cameras": cams,
    }


def save_state(state: dict, path: Path = STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def default_cam_state() -> dict:
    return {
        "status": "unknown",
        "fail_streak": 0,
        "ticketed": False,
        "offline_since": None,
        "last_task_id": None,
        "last_error": None,
        "last_seen_ok": None,
        "post_fail_streak": 0,
    }


def normalize_collaborators(
    collaborators: list[str], assignee: str
) -> list[str]:
    """Drop blanks and the assignee (IT rejects duplicate assignee as collaborator)."""
    seen: set[str] = set()
    out: list[str] = []
    assignee_l = assignee.strip().lower()
    for name in collaborators:
        n = name.strip()
        if not n:
            continue
        key = n.lower()
        if key == assignee_l or key in seen:
            continue
        seen.add(key)
        out.append(n)
    return out


def site_title_fa(site: str) -> str:
    return SITE_TITLES.get(site, site)


def build_task_payload(
    *,
    site: str,
    camera: str,
    fps: float,
    offline_since_local: str,
    assignee: str = ASSIGNEE,
    collaborator_labels: str = COLLABORATOR_LABELS,
    collaborators: list[str] | None = None,
    priority: str = PRIORITY,
) -> dict[str, Any]:
    collaborators = normalize_collaborators(
        collaborators if collaborators is not None else list(COLLABORATORS),
        assignee,
    )
    ext = external_id(site, camera)
    section = site_title_fa(site)
    description = (
        f"بخش: {section}\n"
        f"نام دوربین: {camera}\n"
        f"تقریباً از: {offline_since_local}\n"
        f"مسئول: {assignee or '(پیش‌فرض IT)'}\n"
        f"همکاران: {collaborator_labels}\n"
        f"site={site}\n"
        f"camera={camera}\n"
        f"fps={fps}"
    )
    body: dict[str, Any] = {
        "title": f"قطع دوربین {camera} — {site}",
        "description": description,
        "priority": priority,
        "source": "cameras",
        "external_id": ext,
    }
    if assignee:
        body["assignee_username"] = assignee
    if collaborators:
        body["collaborator_usernames"] = collaborators
    return body


def decide_action(
    *,
    cam_state: dict,
    is_online: bool,
    fail_threshold: int,
    bootstrapped: bool,
    bootstrap_silent: bool,
    eligible: bool,
) -> tuple[str, dict]:
    """Pure decision for one camera sample.

    Returns (action, updated_cam_state) where action is one of:
      none | mark_ok | streak | ticket | bootstrap_silent
    """
    st = dict(cam_state) if cam_state else default_cam_state()

    if is_online:
        st["status"] = "ok"
        st["fail_streak"] = 0
        st["ticketed"] = False
        st["offline_since"] = None
        st["last_error"] = None
        st["last_seen_ok"] = now_iso()
        return "mark_ok", st

    # Offline sample
    st["fail_streak"] = int(st.get("fail_streak") or 0) + 1
    if not st.get("offline_since"):
        st["offline_since"] = now_iso()
    st["status"] = "broken"

    if not eligible:
        return "none", st

    # Opt-in legacy: on the very first site scan, record outages without POSTing.
    if not bootstrapped and bootstrap_silent:
        st["ticketed"] = True
        return "bootstrap_silent", st

    if st.get("ticketed"):
        return "none", st

    if st["fail_streak"] >= fail_threshold:
        return "ticket", st

    return "streak", st


def http_get_json(url: str, timeout: int) -> dict:
    req = Request(url, headers={"User-Agent": "camera-ticket-notifier"})
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8") or "{}")


def post_task_once(
    body: dict,
    *,
    base_url: str,
    api_key: str = API_KEY,
    timeout: int = POST_TIMEOUT,
) -> tuple[int, dict]:
    """POST to a single IT base URL. Raises on network/timeout errors."""
    url = f"{base_url.rstrip('/')}/tasks"
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Idempotency-Key": str(body.get("external_id") or ""),
        "User-Agent": "camera-ticket-notifier",
    }
    req = Request(url, data=data, headers=headers, method="POST")
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8") or "{}"
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = {"raw": raw}
            out = payload if isinstance(payload, dict) else {"raw": payload}
            out.setdefault("_base_url", base_url)
            return resp.status, out
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        try:
            payload = json.loads(raw) if raw else {"error": str(exc)}
        except json.JSONDecodeError:
            payload = {"error": str(exc), "raw": raw}
        out = payload if isinstance(payload, dict) else {"error": str(exc)}
        out.setdefault("_base_url", base_url)
        return exc.code, out


def post_task(
    body: dict,
    *,
    base_urls: list[str] | None = None,
    api_key: str = API_KEY,
    timeout: int = POST_TIMEOUT,
    post_once_fn: Callable[..., tuple[int, dict]] | None = None,
) -> tuple[int, dict]:
    """POST with failover across ordered base URLs.

    Tries each URL until success (200/201) or a non-retryable HTTP error
    (e.g. 400/401). Network errors and 502/503/504 move to the next URL.
    """
    urls = list(base_urls) if base_urls is not None else list(BASE_URLS)
    if not urls:
        urls = list(DEFAULT_BASE_URLS)
    once = post_once_fn or post_task_once
    last_status = 0
    last_payload: dict = {"error": "no_base_urls"}

    for i, base in enumerate(urls):
        try:
            status, payload = once(
                body, base_url=base, api_key=api_key, timeout=timeout
            )
        except (URLError, TimeoutError, OSError) as exc:
            last_status = 0
            last_payload = {
                "error": f"{type(exc).__name__}: {exc}",
                "_base_url": base,
            }
            if i + 1 < len(urls):
                log(f"IT unreachable {base} ({last_payload['error']}) — failover")
                continue
            return last_status, last_payload

        last_status, last_payload = status, payload
        if status in (200, 201):
            if i > 0:
                log(f"IT failover ok via {base}")
            return status, payload
        if should_failover_status(status) and i + 1 < len(urls):
            log(f"IT {base} http={status} — failover to next")
            continue
        return status, payload

    return last_status, last_payload


def emit_ticket(
    body: dict,
    *,
    dry_run: bool = DRY_RUN,
    enabled: bool = ENABLED,
    api_key: str = API_KEY,
    post_fn: Callable[..., tuple[int, dict]] | None = None,
) -> tuple[str, dict]:
    """Create (or dry-run) an IT task. Returns (result, response_or_meta)."""
    if dry_run or not enabled or not api_key:
        mode = "dry_run" if dry_run else ("disabled" if not enabled else "no_api_key")
        log(
            f"{mode}: would POST {body.get('external_id')} "
            f"title={body.get('title')!r} bases={BASE_URLS}"
        )
        return mode, {"ok": True, "skipped": mode, "body": body, "bases": list(BASE_URLS)}

    fn = post_fn or post_task
    status, payload = fn(body)
    if not isinstance(payload, dict):
        payload = {"raw": payload}
    payload["_http_status"] = status
    if status in (200, 201) and payload.get("ok", True):
        log(
            f"task ok http={status} id={payload.get('task_id')} "
            f"ext={body.get('external_id')} via={payload.get('_base_url')} "
            f"replay={payload.get('idempotent_replay')}"
        )
        return "posted", payload
    log(f"task fail http={status} ext={body.get('external_id')} body={payload}")
    return "error", payload


def site_bootstrapped(state: dict, site: str) -> bool:
    sites = state.get("bootstrapped_sites") or []
    return site in sites


def mark_site_bootstrapped(state: dict, site: str) -> None:
    sites = state.setdefault("bootstrapped_sites", [])
    if site not in sites:
        sites.append(site)


def process_camera_sample(
    state: dict,
    *,
    site: str,
    camera: str,
    fps: float,
    fail_threshold: int = FAIL_THRESHOLD,
    bootstrap_silent: bool = BOOTSTRAP_SILENT,
    emit_fn: Callable[..., tuple[str, dict]] | None = None,
) -> str:
    """Update state for one camera reading; maybe create a ticket. Returns action."""
    cams: dict = state.setdefault("cameras", {})
    key = camera_key(site, camera)
    cam_state = cams.get(key) or default_cam_state()
    is_online = fps > 0
    eligible = can_ticket(site, camera)
    bootstrapped = site_bootstrapped(state, site)

    action, new_st = decide_action(
        cam_state=cam_state,
        is_online=is_online,
        fail_threshold=fail_threshold,
        bootstrapped=bootstrapped,
        bootstrap_silent=bootstrap_silent,
        eligible=eligible,
    )

    if action == "ticket":
        offline_iso = new_st.get("offline_since") or now_iso()
        try:
            offline_dt = datetime.fromisoformat(offline_iso.replace("Z", "+00:00"))
            offline_local = local_ts(offline_dt.astimezone())
        except ValueError:
            offline_local = local_ts()
        body = build_task_payload(
            site=site,
            camera=camera,
            fps=fps,
            offline_since_local=offline_local,
        )
        result, payload = (emit_fn or emit_ticket)(body)
        if result in ("posted", "dry_run", "disabled", "no_api_key"):
            new_st["ticketed"] = True
            new_st["last_task_id"] = payload.get("task_id")
            new_st["last_error"] = None
            new_st["post_fail_streak"] = 0
            action = f"{action}:{result}"
        else:
            new_st["last_error"] = str(payload.get("error") or payload)[:300]
            new_st["post_fail_streak"] = int(new_st.get("post_fail_streak") or 0) + 1
            # Permanent client errors (bad key / unknown user) — stop hammering.
            http_status = payload.get("_http_status")
            if is_permanent_client_error(int(http_status or 0)):
                new_st["ticketed"] = True
                action = f"{action}:fatal"
            else:
                # Transient — keep ticketed=false so a later cycle can retry.
                action = f"{action}:error"

    cams[key] = new_st
    return action


def probe_instance(inst: dict) -> dict:
    site = inst["id"]
    base = inst["base"]
    out: dict[str, Any] = {
        "site": site,
        "ok": False,
        "uptime_sec": 0.0,
        "cameras": {},
        "error": None,
        "in_grace": False,
    }
    try:
        stats = http_get_json(f"{base}/api/stats", API_TIMEOUT)
    except (URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError) as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
        return out

    uptime = service_uptime_sec(stats)
    out["ok"] = True
    out["uptime_sec"] = uptime
    out["cameras"] = parse_camera_fps(stats)
    out["in_grace"] = bool(uptime and uptime < STARTUP_GRACE_SEC)
    return out


def run_cycle(state: dict, instances: list[dict] | None = None) -> dict:
    """One full scan. Mutates and returns state."""
    instances = instances if instances is not None else INSTANCES
    summary = {"ok_instances": 0, "offline_samples": 0, "tickets": 0, "actions": []}

    for inst in instances:
        site = inst["id"]
        if site in SKIP_INSTANCE_IDS:
            continue
        probe = probe_instance(inst)
        if not probe["ok"]:
            log(f"{site}: stats fail {probe.get('error')}")
            continue
        summary["ok_instances"] += 1
        if probe["in_grace"]:
            log(f"{site}: grace uptime={int(probe['uptime_sec'])}s — skip")
            continue

        was_bootstrapped = site_bootstrapped(state, site)
        for camera, fps in sorted(probe["cameras"].items()):
            if fps <= 0:
                summary["offline_samples"] += 1
            action = process_camera_sample(
                state,
                site=site,
                camera=camera,
                fps=fps,
            )
            if action and action != "none":
                summary["actions"].append(f"{site}/{camera}:{action}")
            if "ticket" in action and "error" not in action:
                summary["tickets"] += 1

        # First non-grace successful scan of this site.
        if not was_bootstrapped:
            mark_site_bootstrapped(state, site)
            if BOOTSTRAP_SILENT:
                log(f"{site}: first scan done (bootstrap silent — no IT tickets)")
            else:
                log(
                    f"{site}: first scan done — offline cams will ticket after "
                    f"{FAIL_THRESHOLD * CYCLE_SEC // 60} min sustained outage"
                )

    state["last_cycle"] = now_iso()
    return state


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    log(
        f"start enabled={ENABLED} dry_run={DRY_RUN} bootstrap_silent={BOOTSTRAP_SILENT} "
        f"cycle={CYCLE_SEC}s threshold={FAIL_THRESHOLD} "
        f"(~{FAIL_THRESHOLD * CYCLE_SEC // 60}min) assignee={ASSIGNEE!r} "
        f"bases={BASE_URLS} key_set={bool(API_KEY)}"
    )
    if not ENABLED:
        log("IT_TASKS_ENABLED=0 — will detect/log but not POST to IT")
    elif DRY_RUN:
        log("IT_TASKS_DRY_RUN=1 — payloads logged only")
    elif not API_KEY:
        log("IT_TASKS_API_KEY empty — POST disabled")

    state = load_state()
    while True:
        try:
            state = run_cycle(state)
            save_state(state)
        except Exception:
            log("cycle error:\n" + traceback.format_exc())
        time.sleep(CYCLE_SEC)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
