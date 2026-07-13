#!/usr/bin/env python3
"""Probe a sample of cameras for brand / ONVIF / basic AI hints via HTTP."""
import json, socket, urllib.request, urllib.error, ssl, re, base64
from concurrent.futures import ThreadPoolExecutor, as_completed

AUTH = ("admin", "admin123")
TIMEOUT = 3

# Active + a few planned samples
IPS = [
    # cafe DVR
    "192.168.51.204",
    # center11 active
    "192.168.51.4", "192.168.51.5", "192.168.51.6",
    "192.168.51.9", "192.168.51.13", "192.168.51.41",
    # planned samples
    "192.168.51.10", "192.168.51.30", "192.168.51.47",
    "192.168.51.71", "192.168.51.84", "192.168.51.90",
    "192.168.51.99", "192.168.51.100",
]

PATHS = [
    "/",
    "/ISAPI/System/deviceInfo",
    "/ISAPI/System/capabilities",
    "/ISAPI/Smart/capabilities",
    "/ISAPI/Event/triggers",
    "/onvif/device_service",
    "/cgi-bin/magicBox.cgi?action=getDeviceType",  # Dahua
    "/cgi-bin/configManager.cgi?action=getConfig&name=VideoAnalyseRule",  # Dahua AI rules
]

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def try_http(ip, path, https=False):
    scheme = "https" if https else "http"
    url = f"{scheme}://{ip}{path}"
    user, pwd = AUTH
    token = base64.b64encode(f"{user}:{pwd}".encode()).decode()
    req = urllib.request.Request(url, headers={
        "Authorization": f"Basic {token}",
        "User-Agent": "cctv-probe/1.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx if https else None) as r:
            body = r.read(4000)
            return r.status, body
    except urllib.error.HTTPError as e:
        body = e.read(1500) if e.fp else b""
        return e.code, body
    except Exception as e:
        return None, str(e).encode()

def probe(ip):
    out = {"ip": ip, "alive": False, "brand": None, "hints": [], "samples": []}
    # port 80 open?
    try:
        s = socket.create_connection((ip, 80), timeout=2)
        s.close()
        out["alive"] = True
    except Exception:
        # try 443
        try:
            s = socket.create_connection((ip, 443), timeout=2)
            s.close()
            out["alive"] = True
            out["hints"].append("https-only")
        except Exception:
            out["hints"].append("no-web-ui")
            return out

    for path in PATHS:
        for https in (False, True):
            code, body = try_http(ip, path, https=https)
            if code is None:
                continue
            text = body.decode("utf-8", errors="ignore")[:800]
            if code in (200, 401, 403) and path == "/":
                if "Hikvision" in text or "hikvision" in text.lower():
                    out["brand"] = "Hikvision"
                elif "Dahua" in text or "dahua" in text.lower() or "WEB SERVICE" in text:
                    out["brand"] = out["brand"] or "Dahua?"
                elif "NVR" in text or "DVR" in text:
                    out["hints"].append("dvr/nvr-ui")
            if code == 200 and "ISAPI" in path:
                out["brand"] = out["brand"] or "Hikvision"
                out["samples"].append((path, text[:300].replace("\n", " ")))
                if "Smart" in path or "VideoAnalyse" in path or "Event" in path:
                    # look for keywords
                    low = text.lower()
                    for kw in ("face", "intrusion", "linecrossing", "people", "vehicle", "motion", "smart", "anpr", "lpr"):
                        if kw in low:
                            out["hints"].append(f"kw:{kw}")
            if code == 200 and "magicBox" in path:
                out["brand"] = "Dahua"
                out["samples"].append((path, text[:200]))
            if code == 200 and "VideoAnalyseRule" in path:
                out["brand"] = "Dahua"
                out["hints"].append("dahua-video-analyse")
                out["samples"].append((path, text[:300]))
            if code in (200, 401) and "onvif" in path.lower():
                out["hints"].append("onvif-endpoint")
            if code == 200:
                break  # got something for this path
    return out

results = []
with ThreadPoolExecutor(max_workers=8) as ex:
    futs = {ex.submit(probe, ip): ip for ip in IPS}
    for f in as_completed(futs):
        results.append(f.result())

results.sort(key=lambda x: x["ip"])
print(json.dumps(results, indent=2, ensure_ascii=False))
