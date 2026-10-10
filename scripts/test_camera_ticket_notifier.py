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
    normalize_api_key,
    parse_base_urls,
    parse_camera_fps,
    post_task,
    process_camera_sample,
    run_cycle,
    save_state,
    should_failover_status,
)
from urllib.error import URLError
import camera_ticket_notifier as mod


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


class ApiKeyTests(unittest.TestCase):
    def test_strips_client_prefix(self):
        self.assertEqual(
            normalize_api_key("CCTVizad:ttMJ8QbMgNSOw3mQpo_IguHQP9ahPZVLLc7oY5xSXqI"),
            "ttMJ8QbMgNSOw3mQpo_IguHQP9ahPZVLLc7oY5xSXqI",
        )

    def test_keeps_bare_secret(self):
        self.assertEqual(normalize_api_key("abc123"), "abc123")

    def test_keeps_sk_tokens(self):
        self.assertEqual(normalize_api_key("sk_cameras_xxx"), "sk_cameras_xxx")


class ProcessFlowTests(unittest.TestCase):
    def test_bootstrap_then_new_outage_tickets_once(self):
        """Full site process: first scan silent, later outage tickets once."""
        state = {"bootstrapped_sites": [], "cameras": {}}
        posts: list[dict] = []

        def emit(body, **_kw):
            posts.append(body)
            return "posted", {"ok": True, "task_id": 99, "_http_status": 201}

        # Cycle 1 — bootstrap already-offline cam_a (no ticket)
        a1 = process_camera_sample(
            state,
            site="center11",
            camera="cam_a",
            fps=0.0,
            fail_threshold=3,
            emit_fn=emit,
        )
        self.assertTrue(a1.startswith("bootstrap_silent"))
        state["bootstrapped_sites"] = ["center11"]
        self.assertEqual(posts, [])

        # Online cam_b stays quiet
        process_camera_sample(
            state, site="center11", camera="cam_b", fps=5.0, fail_threshold=3, emit_fn=emit
        )

        # cam_b drops for 3 cycles → one ticket
        for _ in range(3):
            process_camera_sample(
                state,
                site="center11",
                camera="cam_b",
                fps=0.0,
                fail_threshold=3,
                emit_fn=emit,
            )
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["external_id"], "camera-center11-cam_b-offline")
        self.assertEqual(posts[0]["assignee_username"], "faraji")
        self.assertEqual(posts[0]["collaborator_usernames"], ["bahrami", "sahragard"])

        # Still offline — no spam
        process_camera_sample(
            state, site="center11", camera="cam_b", fps=0.0, fail_threshold=3, emit_fn=emit
        )
        self.assertEqual(len(posts), 1)

    def test_fatal_401_stops_retry_spam(self):
        state = {"bootstrapped_sites": ["cafe"], "cameras": {}}

        def emit(body, **_kw):
            return "error", {"ok": False, "error": "unauthorized", "_http_status": 401}

        for _ in range(3):
            action = process_camera_sample(
                state,
                site="cafe",
                camera="cam_z",
                fps=0.0,
                fail_threshold=3,
                emit_fn=emit,
            )
        self.assertTrue(action.endswith(":fatal"))
        self.assertTrue(state["cameras"]["cafe:cam_z"]["ticketed"])

        # Next cycle must not call emit again (ticketed)
        calls = []

        def emit2(body, **_kw):
            calls.append(1)
            return "posted", {"ok": True, "task_id": 1}

        process_camera_sample(
            state, site="cafe", camera="cam_z", fps=0.0, fail_threshold=3, emit_fn=emit2
        )
        self.assertEqual(calls, [])

    def test_run_cycle_marks_site_bootstrapped(self):
        state = {"bootstrapped_sites": [], "cameras": {}}

        def fake_probe(inst):
            return {
                "site": inst["id"],
                "ok": True,
                "uptime_sec": 500,
                "cameras": {"cam_1": 0.0, "cam_2": 4.0},
                "error": None,
                "in_grace": False,
            }

        old = mod.probe_instance
        try:
            mod.probe_instance = fake_probe  # type: ignore
            run_cycle(state, instances=[{"id": "villa", "base": "http://x"}])
        finally:
            mod.probe_instance = old

        self.assertIn("villa", state["bootstrapped_sites"])
        self.assertTrue(state["cameras"]["villa:cam_1"]["ticketed"])
        self.assertEqual(state["cameras"]["villa:cam_2"]["status"], "ok")


class FailoverTests(unittest.TestCase):
    def test_parse_base_urls_list(self):
        urls = parse_base_urls(
            "http://192.168.0.90:5000/api/v1, http://188.121.144.90:5000/api/v1",
            "",
        )
        self.assertEqual(
            urls,
            [
                "http://192.168.0.90:5000/api/v1",
                "http://188.121.144.90:5000/api/v1",
            ],
        )

    def test_defaults_lan_then_public(self):
        urls = parse_base_urls("", "")
        self.assertEqual(urls[0], "http://192.168.0.90:5000/api/v1")
        self.assertEqual(urls[1], "http://188.121.144.90:5000/api/v1")

    def test_failover_on_network_error(self):
        calls: list[str] = []

        def once(body, *, base_url, **_kw):
            calls.append(base_url)
            if "192.168.0.90" in base_url:
                raise URLError("timed out")
            return 201, {"ok": True, "task_id": 9, "_base_url": base_url}

        status, payload = post_task(
            {"external_id": "camera-x-offline", "title": "t"},
            base_urls=[
                "http://192.168.0.90:5000/api/v1",
                "http://188.121.144.90:5000/api/v1",
            ],
            post_once_fn=once,
        )
        self.assertEqual(status, 201)
        self.assertEqual(payload["task_id"], 9)
        self.assertEqual(len(calls), 2)

    def test_failover_on_503(self):
        calls: list[str] = []

        def once(body, *, base_url, **_kw):
            calls.append(base_url)
            if "192.168.0.90" in base_url:
                return 503, {"ok": False, "error": "api_disabled", "_base_url": base_url}
            return 200, {"ok": True, "task_id": 3, "idempotent_replay": True}

        status, payload = post_task(
            {"external_id": "camera-x-offline"},
            base_urls=[
                "http://192.168.0.90:5000/api/v1",
                "http://188.121.144.90:5000/api/v1",
            ],
            post_once_fn=once,
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("idempotent_replay"))
        self.assertEqual(len(calls), 2)

    def test_no_failover_on_401(self):
        calls: list[str] = []

        def once(body, *, base_url, **_kw):
            calls.append(base_url)
            return 401, {"ok": False, "error": "unauthorized"}

        status, payload = post_task(
            {"external_id": "camera-x-offline"},
            base_urls=[
                "http://192.168.0.90:5000/api/v1",
                "http://188.121.144.90:5000/api/v1",
            ],
            post_once_fn=once,
        )
        self.assertEqual(status, 401)
        self.assertEqual(len(calls), 1)
        self.assertTrue(should_failover_status(503))
        self.assertFalse(should_failover_status(401))


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
