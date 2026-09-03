#!/usr/bin/env python3
"""Unit tests for hang/recovery decisions (no Docker required)."""
from __future__ import annotations

from datetime import datetime, timezone
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from frigate_watchdog import (
    classify_probe,
    hourly_restart_count,
    mass_outage,
    pick_snap_targets,
    restart_decision,
)


class ClassifyProbeTests(unittest.TestCase):
    def test_unresponsive_on_api_fail(self):
        r = classify_probe({"api_ok": False, "api_error": "timeout"})
        self.assertEqual(r["verdict"], "unresponsive")

    def test_ok_when_any_camera_live(self):
        r = classify_probe(
            {
                "api_ok": True,
                "camera_names": ["cam_a", "cam_b"],
                "live_names": ["cam_a"],
                "snapshots": [{"ok": False}, {"ok": False}],
                "uptime_sec": 500,
            }
        )
        self.assertEqual(r["verdict"], "ok")

    def test_ok_when_jpeg_loads_even_if_fps_zero(self):
        r = classify_probe(
            {
                "api_ok": True,
                "camera_names": ["cam_a"],
                "live_names": [],
                "snapshots": [{"ok": True}],
                "uptime_sec": 500,
            }
        )
        self.assertEqual(r["verdict"], "ok")

    def test_starting_when_no_video_during_grace(self):
        r = classify_probe(
            {
                "api_ok": True,
                "camera_names": ["cam_a"],
                "live_names": [],
                "snapshots": [{"ok": False}],
                "uptime_sec": 20,
            },
            grace_sec=90,
        )
        self.assertEqual(r["verdict"], "starting")

    def test_dead_video_after_grace(self):
        r = classify_probe(
            {
                "api_ok": True,
                "camera_names": ["cam_a", "cam_b"],
                "live_names": [],
                "snapshots": [{"ok": False}, {"ok": False}],
                "uptime_sec": 400,
            },
            grace_sec=90,
        )
        self.assertEqual(r["verdict"], "dead_video")

    def test_empty_instance_not_a_hang(self):
        r = classify_probe(
            {
                "api_ok": True,
                "camera_names": [],
                "live_names": [],
                "snapshots": [],
                "uptime_sec": 400,
            }
        )
        self.assertEqual(r["verdict"], "empty")


class RestartDecisionTests(unittest.TestCase):
    def test_needs_consecutive_failures(self):
        ok, _ = restart_decision(
            verdict="unresponsive",
            consecutive_bad=2,
            last_restart=None,
            restarts=[],
            now_ts=1_000_000,
            fail_threshold=3,
        )
        self.assertFalse(ok)

    def test_restarts_after_threshold(self):
        ok, reason = restart_decision(
            verdict="dead_video",
            consecutive_bad=3,
            last_restart=None,
            restarts=[],
            now_ts=1_000_000,
            fail_threshold=3,
        )
        self.assertTrue(ok)
        self.assertIn("dead_video", reason)

    def test_cooldown_blocks(self):
        now = 1_700_000_000
        last = datetime.fromtimestamp(now - 30, tz=timezone.utc).isoformat()
        ok, _ = restart_decision(
            verdict="unresponsive",
            consecutive_bad=5,
            last_restart=last,
            restarts=[],
            now_ts=now,
            fail_threshold=3,
            cooldown_sec=300,
        )
        self.assertFalse(ok)

    def test_hourly_cap(self):
        now = 1_700_000_000.0
        restarts = [
            {"ts": datetime.fromtimestamp(now - offset, tz=timezone.utc).isoformat()}
            for offset in (0, 600, 1200)
        ]
        self.assertEqual(hourly_restart_count(restarts, now), 3)
        ok, _ = restart_decision(
            verdict="unresponsive",
            consecutive_bad=5,
            last_restart=None,
            restarts=restarts,
            now_ts=now,
            fail_threshold=3,
            max_per_hour=3,
        )
        self.assertFalse(ok)

    def test_healthy_never_restarts(self):
        ok, _ = restart_decision(
            verdict="ok",
            consecutive_bad=9,
            last_restart=None,
            restarts=[],
            now_ts=1,
        )
        self.assertFalse(ok)


class MassOutageTests(unittest.TestCase):
    def test_single_hang_is_not_mass(self):
        self.assertFalse(mass_outage(["ok", "ok", "unresponsive", "ok"], ratio=0.5))

    def test_half_or_more_is_mass(self):
        self.assertTrue(
            mass_outage(
                ["unresponsive", "dead_video", "ok", "unresponsive"],
                ratio=0.5,
            )
        )


class SnapTargetTests(unittest.TestCase):
    def test_prefers_live_then_others(self):
        self.assertEqual(
            pick_snap_targets(["a", "b", "c"], ["c"], 2),
            ["c", "a"],
        )


if __name__ == "__main__":
    unittest.main()
