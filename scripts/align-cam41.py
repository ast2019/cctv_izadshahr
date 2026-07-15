#!/usr/bin/env python3
"""Align cam_41 encode settings to match cam_4 (same model DS-2CD2T42WD-I5)."""
import base64
import re
import urllib.request
import urllib.error

AUTH = base64.b64encode(b"admin:admin123").decode()
HDR = {
    "Authorization": f"Basic {AUTH}",
    "User-Agent": "cctv-align/1.0",
    "Content-Type": "application/xml; charset=UTF-8",
}

CAM4 = "192.168.51.4"
CAM41 = "192.168.51.41"


def http(method, ip, path, data=None):
    req = urllib.request.Request(
        f"http://{ip}{path}",
        data=data.encode("utf-8") if data is not None else None,
        headers=HDR,
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            return r.status, r.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        return e.code, body


def get_channel(ip, ch):
    code, body = http("GET", ip, f"/ISAPI/Streaming/channels/{ch}")
    if code != 200:
        raise RuntimeError(f"GET {ip} ch{ch} -> {code}: {body[:200]}")
    return body


def set_tag(xml, tag, value):
    """Replace first occurrence of <tag>...</tag> (non-greedy)."""
    pat = rf"(<{tag}>)(.*?)(</{tag}>)"
    if not re.search(pat, xml, flags=re.I | re.S):
        raise RuntimeError(f"tag <{tag}> not found")
    return re.sub(pat, rf"\g<1>{value}\g<3>", xml, count=1, flags=re.I | re.S)


def pick(xml, tag):
    m = re.search(rf"<{tag}>(.*?)</{tag}>", xml, re.I | re.S)
    return m.group(1).strip() if m else None


def summarize(ip, label):
    print(f"\n--- {label} ({ip}) ---")
    for ch in ("101", "102"):
        xml = get_channel(ip, ch)
        w = pick(xml, "videoResolutionWidth")
        h = pick(xml, "videoResolutionHeight")
        codec = pick(xml, "videoCodecType")
        vbr = pick(xml, "vbrUpperCap")
        fps = pick(xml, "maxFrameRate")
        name = pick(xml, "channelName")
        print(f"  CH{ch}: {w}x{h} {codec} vbr={vbr} fps={fps} name={name}")


# Reference from cam_4
ref101 = get_channel(CAM4, "101")
ref102 = get_channel(CAM4, "102")
print("Reference cam_4:")
print("  101:", pick(ref101, "videoResolutionWidth"), "x", pick(ref101, "videoResolutionHeight"))
print("  102:", pick(ref102, "videoResolutionWidth"), "x", pick(ref102, "videoResolutionHeight"))

summarize(CAM41, "BEFORE cam_41")

# Update cam_41 main stream (101) to match cam_4 main
xml101 = get_channel(CAM41, "101")
xml101 = set_tag(xml101, "videoResolutionWidth", pick(ref101, "videoResolutionWidth"))
xml101 = set_tag(xml101, "videoResolutionHeight", pick(ref101, "videoResolutionHeight"))
xml101 = set_tag(xml101, "videoCodecType", pick(ref101, "videoCodecType"))
xml101 = set_tag(xml101, "videoQualityControlType", pick(ref101, "videoQualityControlType"))
xml101 = set_tag(xml101, "constantBitRate", pick(ref101, "constantBitRate"))
xml101 = set_tag(xml101, "vbrUpperCap", pick(ref101, "vbrUpperCap"))
xml101 = set_tag(xml101, "maxFrameRate", pick(ref101, "maxFrameRate"))  # 2000 = 20fps
xml101 = set_tag(xml101, "GovLength", pick(ref101, "GovLength"))
xml101 = set_tag(xml101, "fixedQuality", pick(ref101, "fixedQuality"))

code, resp = http("PUT", CAM41, "/ISAPI/Streaming/channels/101", xml101)
print(f"\nPUT CH101 -> {code}")
if code not in (200, 201):
    print(resp[:500])

# Update cam_41 sub stream (102) to match cam_4 sub (what Frigate uses)
xml102 = get_channel(CAM41, "102")
xml102 = set_tag(xml102, "videoResolutionWidth", pick(ref102, "videoResolutionWidth"))
xml102 = set_tag(xml102, "videoResolutionHeight", pick(ref102, "videoResolutionHeight"))
xml102 = set_tag(xml102, "videoCodecType", pick(ref102, "videoCodecType"))
xml102 = set_tag(xml102, "videoQualityControlType", pick(ref102, "videoQualityControlType"))
xml102 = set_tag(xml102, "constantBitRate", pick(ref102, "constantBitRate"))
xml102 = set_tag(xml102, "vbrUpperCap", pick(ref102, "vbrUpperCap"))
xml102 = set_tag(xml102, "maxFrameRate", pick(ref102, "maxFrameRate"))
xml102 = set_tag(xml102, "GovLength", pick(ref102, "GovLength"))
xml102 = set_tag(xml102, "fixedQuality", pick(ref102, "fixedQuality"))

code, resp = http("PUT", CAM41, "/ISAPI/Streaming/channels/102", xml102)
print(f"PUT CH102 -> {code}")
if code not in (200, 201):
    print(resp[:500])

summarize(CAM41, "AFTER cam_41")
summarize(CAM4, "cam_4 (reference)")
