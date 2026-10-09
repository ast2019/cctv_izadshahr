#!/usr/bin/env python3
"""Unit tests for camera → IT ticket decisions (no network)."""
from __future__ import annotations

import unittest
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))

import camera_ticket_notifier as mod
from camera_ticket_notifier import (
    build_task_payload,
    can_ticket,
    decide_action,
    default_cam_state,
    emit_ticket,
    external_id,
    load_state,
    parse_camera_fps,
    process_camera_sample,
    save_state,
)


class ParseAndIdsTests(unittest.TestCase):
    def test_parse_fps(self):
        fps = parse_camera_fps(
            {
                "cameras": {
                    "cam_a": {"camera_fps": 5.0},
                    "cam_b": {"camera_fps": 0},
                    "bad": "x",
                }
            }
        )
        self.assertEqual(fps["cam_a"], 5.0)
        self.assertEqual(fps["cam_b"], 0.0)
        self.assertNotIn("bad", fps)

    def test_external_id_stable(self):
        self.assertEqual(
            external_id("center11", "cam_5"),
            "camera-center11-cam_5-offline",
        )


class EligibilityTests(unittest.TestCase):
    def test_temp_never(self):
        self.assertFalse(can_ticket("temp", "cam_1"))

    def test_allowlist(self):
        old_a, old_d = mod.ALLOWLIST, mod.DENYLIST
        try:
            mod.ALLOWLIST = frozenset({"center11:cam_5"})
            mod.DENYLIST = frozenset()
            self.assertTrue(can_ticket("center11", "cam_5"))
            self.assertFalse(can_ticket("center11", "cam_6"))
        finally:
            mod.ALLOWLIST, mod.DENYLIST = old_a, old_d

    def test_denylist(self):
        old_a, old_d = mod.ALLOWLIST, mod.DENYLIST
        try:
            mod.ALLOWLIST = frozenset()
            mod.DENYLIST = frozenset({"cafe:dvr_cafe_ch1"})
            self.assertFalse(can_ticket("cafe", "dvr_cafe_ch1"))
            self.assertTrue(can_ticket("cafe", "vorodi_cafe"))
        finally:
            mod.ALLOWLIST, mod.DENYLIST = old_a, old_d


class DecideActionTests(unittest.TestCase):
    def test_online_resets(self):
        st = default_cam_state()
        st.update({"status": "broken", "fail_streak": 3, "ticketed": True})
        action, new = decide_action(
            cam_state=st,
            is_online=True,
            fail_threshold=3,
            bootstrapped=True,
            bootstrap_ticket=False,
            eligible=True,
        )
        self.assertEqual(action, "mark_ok")
        self.assertEqual(new["status"], "ok")
        self.assertFalse(new["ticketed"])
        self.assertEqual(new["fail_streak"], 0)

    def test_debounce_before_ticket(self):
        st = default_cam_state()
        for i in range(1, 3):
            action, st = decide_action(
                cam_state=st,
                is_online=False,
                fail_threshold=3,
                bootstrapped=True,
                bootstrap_ticket=False,
                eligible=True,
            )
            self.assertEqual(action, "streak")
            self.assertEqual(st["fail_streak"], i)
        action, st = decide_action(
            cam_state=st,
            is_online=False,
            fail_threshold=3,
            bootstrapped=True,
            bootstrap_ticket=False,
            eligible=True,
        )
        self.assertEqual(action, "ticket")

    def test_already_ticketed_no_spam(self):
        st = default_cam_state()
        st.update({"fail_streak": 5, "ticketed": True, "status": "broken"})
        action, _ = decide_action(
            cam_state=st,
            is_online=False,
            fail_threshold=3,
            bootstrapped=True,
            bootstrap_ticket=False,
            eligible=True,
        )
        self.assertEqual(action, "none")

    def test_bootstrap_silent_immediate(self):
        action, st = decide_action(
            cam_state=default_cam_state(),
            is_online=False,
            fail_threshold=3,
            bootstrapped=False,
            bootstrap_ticket=False,
            eligible=True,
        )
        self.assertEqual(action, "bootstrap_silent")
        self.assertTrue(st["ticketed"])

    def test_bootstrap_ticket_mode_waits_threshold(self):
        st = default_cam_state()
        action, st = decide_action(
            cam_state=st,
            is_online=False,
            fail_threshold=3,
            bootstrapped=False,
            bootstrap_ticket=True,
            eligible=True,
        )
        self.assertEqual(action, "streak")
        st["fail_streak"] = 2
        action, st = decide_action(
            cam_state=st,
            is_online=False,
            fail_threshold=3,
            bootstrapped=False,
            bootstrap_ticket=True,
            eligible=True,
        )
        self.assertEqual(action, "bootstrap_ticket")


class PayloadTests(unittest.TestCase):
    def test_description_has_site_and_time_and_collaborators(self):
        body = build_task_payload(
            site="center11",
            camera="cam_5",
            fps=0.0,
            offline_since_local="2026-10-09 15:40:00",
            assignee="faraji",
            collaborator_labels="بهرامی، صحراگرد",
            collaborators=["bahrami", "sahragard"],
        )
        self.assertIn("center11", body["title"])
        self.assertIn("نمونه Frigate: center11", body["description"])
        self.assertIn("تقریباً از: 2026-10-09 15:40:00", body["description"])
        self.assertIn("همکاران: بهرامی، صحراگرد", body["description"])
        self.assertEqual(body["assignee_username"], "faraji")
        self.assertEqual(body["collaborator_usernames"], ["bahrami", "sahragard"])
        self.assertEqual(body["external_id"], "camera-center11-cam_5-offline")
        self.assertEqual(body["source"], "cameras")

    def test_assignee_stripped_from_collaborators(self):
        body = build_task_payload(
            site="cafe",
            camera="cam_1",
            fps=0.0,
            offline_since_local="2026-10-09 15:40:00",
            assignee="faraji",
            collaborators=["faraji", "bahrami", "sahragard", "bahrami"],
        )
        self.assertEqual(body["collaborator_usernames"], ["bahrami", "sahragard"])


class ProcessSampleTests(unittest.TestCase):
    def test_one_ticket_per_outage(self):
        state = {"bootstrapped_sites": ["center11"], "cameras": {}}
        posts: list[dict] = []

        def fake_emit(body, **_kw):
            posts.append(body)
            return "posted", {"ok": True, "task_id": 128}

        for _ in range(3):
            process_camera_sample(
                state,
                site="center11",
                camera="cam_5",
                fps=0.0,
                fail_threshold=3,
                emit_fn=fake_emit,
            )
        self.assertEqual(len(posts), 1)

        # Still offline — no second post
        process_camera_sample(
            state,
            site="center11",
            camera="cam_5",
            fps=0.0,
            fail_threshold=3,
            emit_fn=fake_emit,
        )
        self.assertEqual(len(posts), 1)

        # Recover then drop again → new ticket allowed
        process_camera_sample(
            state,
            site="center11",
            camera="cam_5",
            fps=5.0,
            fail_threshold=3,
            emit_fn=fake_emit,
        )
        for _ in range(3):
            process_camera_sample(
                state,
                site="center11",
                camera="cam_5",
                fps=0.0,
                fail_threshold=3,
                emit_fn=fake_emit,
            )
        self.assertEqual(len(posts), 2)

    def test_bootstrap_no_post(self):
        state = {"bootstrapped_sites": [], "cameras": {}}
        posts: list[dict] = []

        def fake_emit(body, **_kw):
            posts.append(body)
            return "posted", {"ok": True, "task_id": 1}

        action = process_camera_sample(
            state,
            site="cafe",
            camera="cam_x",
            fps=0.0,
            fail_threshold=3,
            bootstrap_ticket=False,
            emit_fn=fake_emit,
        )
        self.assertTrue(action.startswith("bootstrap_silent"))
        self.assertEqual(posts, [])
        self.assertTrue(state["cameras"]["cafe:cam_x"]["ticketed"])


class EmitFlagsTests(unittest.TestCase):
    def test_dry_run_skips_http(self):
        called = []

        def fake_post(body, **_kw):
            called.append(body)
            return 201, {"ok": True}

        result, meta = emit_ticket(
            {"external_id": "x", "title": "t"},
            dry_run=True,
            enabled=True,
            api_key="sk_test",
            post_fn=fake_post,
        )
        self.assertEqual(result, "dry_run")
        self.assertEqual(called, [])
        self.assertEqual(meta["skipped"], "dry_run")

    def test_disabled_and_no_key(self):
        r1, _ = emit_ticket({"external_id": "x"}, dry_run=False, enabled=False, api_key="k")
        r2, _ = emit_ticket({"external_id": "x"}, dry_run=False, enabled=True, api_key="")
        self.assertEqual(r1, "disabled")
        self.assertEqual(r2, "no_api_key")


class StatePersistTests(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "state.json"
            state = {
                "bootstrapped_sites": ["cafe"],
                "cameras": {"cafe:cam_1": {"status": "broken", "ticketed": True}},
            }
            save_state(state, path)
            loaded = load_state(path)
            self.assertEqual(loaded["bootstrapped_sites"], ["cafe"])
            self.assertTrue(loaded["cameras"]["cafe:cam_1"]["ticketed"])


if __name__ == "__main__":
    unittest.main()
