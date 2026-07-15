#!/usr/bin/env python3
"""Compare stream/device settings for cam_4 vs cam_41."""
import base64, re, urllib.request, ssl, json

AUTH = base64.b64encode(b"admin:admin123").decode()
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

CAMS = {
    "cam_4": "192.168.51.4",
    "cam_41": "192.168.51.41",
}

PATHS = [
    "/ISAPI/System/deviceInfo",
    "/ISAPI/Streaming/channels/101",  # main
    "/ISAPI/Streaming/channels/102",  # sub (often used by Frigate)
    "/ISAPI/Streaming/channels",
]

def get(ip, path):
    req = urllib.request.Request(
        f"http://{ip}{path}",
        headers={"Authorization": f"Basic {AUTH}", "User-Agent": "cctv-compare"},
    )
    with urllib.request.urlopen(req, timeout=6) as r:
        return r.read().decode("utf-8", errors="ignore")

def pick(xml, *tags):
    out = {}
    for t in tags:
        m = re.search(rf"<{t}>(.*?)</{t}>", xml, re.I | re.S)
        if m:
            out[t] = re.sub(r"\s+", " ", m.group(1)).strip()
    return out

KEYS_DEVICE = ["deviceName", "model", "serialNumber", "firmwareVersion", "macAddress", "deviceType"]
KEYS_STREAM = [
    "id", "channelName", "enabled",
    "videoResolutionWidth", "videoResolutionHeight",
    "videoCodecType", "videoQualityControlType",
    "constantBitRate", "vbrUpperCap", "maxFrameRate",
    "GovLength", "fixedQuality", "smoothing",
]

for name, ip in CAMS.items():
    print("=" * 60)
    print(f"{name} @ {ip}")
    try:
        info = get(ip, "/ISAPI/System/deviceInfo")
        d = pick(info, *KEYS_DEVICE)
        print("DEVICE:", json.dumps(d, ensure_ascii=False))
    except Exception as e:
        print("DEVICE FAIL:", e)
        continue

    for ch in ("101", "102"):
        try:
            xml = get(ip, f"/ISAPI/Streaming/channels/{ch}")
            s = pick(xml, *KEYS_STREAM)
            # also Video namespace variants
            for t in KEYS_STREAM:
                if t not in s:
                    m = re.search(rf"<{t}[^>]*>(.*?)</{t}>", xml, re.I | re.S)
                    if m:
                        s[t] = re.sub(r"\s+", " ", m.group(1)).strip()
            print(f"CH{ch}:", json.dumps(s, ensure_ascii=False))
            # raw snippet for codec/bitrate area
            for kw in ("videoResolutionWidth", "constantBitRate", "videoCodecType", "maxFrameRate", "vbrUpperCap"):
                if kw not in s:
                    pass
        except Exception as e:
            print(f"CH{ch} FAIL:", e)

# Frigate live fps from stats
print("=" * 60)
print("FRIGATE center11 stats fps:")
import http.cookiejar
cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
req = urllib.request.Request(
    "http://127.0.0.1:8888/center11/api/login",
    data=json.dumps({"user": "ceo", "password": "Cctv1405"}).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
op.open(req)
with op.open("http://127.0.0.1:8888/center11/api/stats") as r:
    stats = json.load(r)
for cam in ("cam_4", "cam_41"):
    c = (stats.get("cameras") or {}).get(cam) or {}
    print(f"  {cam}: fps={c.get('camera_fps')} process_fps={c.get('process_fps')} skipped={c.get('skipped_fps')} ffmpeg_pid={c.get('ffmpeg_pid')}")
