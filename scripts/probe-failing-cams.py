#!/usr/bin/env python3
"""Probe RTSP credentials for cameras that currently return 401/timeout."""
import itertools
import subprocess
from urllib.parse import quote

FP = "/usr/lib/ffmpeg/5.0/bin/ffprobe"
IPS = ["192.168.51.52", "192.168.51.53", "192.168.51.54"]
CREDS = [
    ("admin", "1259110@av"),
    ("admin", "admin123"),
    ("admin", "12345@"),
    ("admin", "123456"),
    ("admin", "Admin123"),
    ("Admin", "admin123"),
    ("admin", "1259110av"),
]
PATHS = [
    "/Streaming/Channels/102",
    "/Streaming/Channels/101",
    "/ISAPI/Streaming/channels/102",
]


def probe(url: str) -> str:
    r = subprocess.run(
        [
            FP,
            "-rtsp_transport",
            "tcp",
            "-timeout",
            "3000000",
            "-v",
            "error",
            "-show_entries",
            "stream=codec_name,width,height",
            "-of",
            "csv",
            url,
        ],
        capture_output=True,
        text=True,
    )
    out = (r.stdout + r.stderr).strip().splitlines()
    return out[0] if out else f"exit={r.returncode}"


ok = []
for ip, (user, pw), path in itertools.product(IPS, CREDS, PATHS):
    enc = quote(pw, safe="")
    url = f"rtsp://{user}:{enc}@{ip}:554{path}"
    first = probe(url)
    if first.startswith("stream,"):
        print("OK", ip, user, pw, path, first)
        ok.append((ip, user, pw, path, first))
    else:
        err = "401" if "401" in first else ("timeout" if "timeout" in first.lower() else first[:90])
        print("FAIL", ip, user, pw, path.rsplit("/", 1)[-1], err)

print("===SUMMARY OK===", ok)

# control: known-good camera
ctrl = probe("rtsp://admin:1259110%40av@192.168.51.47:554/Streaming/Channels/102")
print("CONTROL .47", ctrl)
