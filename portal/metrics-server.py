#!/usr/bin/env python3
"""Host CPU/RAM metrics for portal (reads /host/proc from host mount)."""
from http.server import BaseHTTPRequestHandler, HTTPServer
import json

PROC = "/host/proc"
LOAD_RATIO_LIMIT = 0.5  # load_1m >= cores * 0.5 → pressure
MEM_PERCENT_LIMIT = 30.0


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


def snapshot():
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


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.rstrip("/") not in ("", "/api/host-metrics"):
            self.send_error(404)
            return
        body = json.dumps(snapshot()).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", 9090), Handler).serve_forever()
