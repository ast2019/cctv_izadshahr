#!/usr/bin/env python3
"""Generate portal/js/camera-ip-map.js from config/*/config.yml.

Single source of truth = the Frigate configs. Run after any camera move:
    python3 scripts/gen-camera-ip-map.py

The map ({site: {camera: ip}}) powers IP display + search in the admin panel.
Exit code is non-zero if the on-disk file is out of date when called with
--check (used in validation/CI).
"""
from __future__ import annotations

import glob
import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "portal" / "js" / "camera-ip-map.js"


def build_map() -> dict:
    m: dict[str, dict[str, str]] = {}
    for f in sorted(glob.glob(str(ROOT / "config" / "*" / "config.yml"))):
        site = Path(f).parent.name
        data = yaml.safe_load(open(f, encoding="utf-8"))
        streams = (data.get("go2rtc") or {}).get("streams") or {}
        for cam, urls in streams.items():
            ip = None
            for u in urls if isinstance(urls, list) else [urls]:
                mm = re.search(r"(\d+\.\d+\.\d+\.\d+)", str(u))
                if mm:
                    ip = mm.group(1)
                    break
            if ip:
                m.setdefault(site, {})[cam] = ip
    return m


def render(m: dict) -> str:
    header = (
        "/**\n"
        " * Camera -> IP map, GENERATED from the Frigate configs.\n"
        " * Do not edit by hand. Regenerate after any camera move:\n"
        " *   python3 scripts/gen-camera-ip-map.py\n"
        " * Used by the admin panel to show and search cameras by IP.\n"
        " */\n"
    )
    body = "const CAMERA_IP = " + json.dumps(
        m, ensure_ascii=False, indent=2, sort_keys=True
    ) + ";\n"
    return header + body


def main() -> int:
    content = render(build_map())
    if "--check" in sys.argv:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != content:
            print("camera-ip-map.js is OUT OF DATE — run: python3 scripts/gen-camera-ip-map.py")
            return 1
        print("camera-ip-map.js is up to date")
        return 0
    OUT.write_text(content, encoding="utf-8")
    total = sum(len(v) for v in build_map().values())
    print(f"wrote {OUT.relative_to(ROOT)} ({total} cameras)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
