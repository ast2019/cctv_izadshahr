#!/usr/bin/env python3
"""Static checks that portal login is a single token (no Docker)."""
from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PORTAL = ROOT / "portal"


def load_portal_api():
    os.environ.pop("FRIGATE_AUTH_URL", None)
    spec = importlib.util.spec_from_file_location("portal_api", PORTAL / "portal-api.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SITES = (
    "cafe",
    "center11",
    "center22",
    "restaurant",
    "sahel",
    "villa",
    "mahoote",
    "tasisat",
    "entezamat",
    "anbar",
    "khanedari",
    "temp",
)


class SessionStoreTests(unittest.TestCase):
    def test_one_token_maps_to_one_user(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        os.environ["PORTAL_DB"] = path
        try:
            api = load_portal_api()
            api.init_db()
            token = api.create_portal_session("ceo")
            self.assertEqual(api.lookup_portal_session(token), "ceo")
            self.assertIsNone(api.lookup_portal_session("not-a-token"))
            api.delete_portal_session(token)
            self.assertIsNone(api.lookup_portal_session(token))
        finally:
            os.environ.pop("PORTAL_DB", None)
            Path(path).unlink(missing_ok=True)


class CookieHeaderTests(unittest.TestCase):
    def test_host_only_httponly_path(self):
        api = load_portal_api()
        header = api.session_cookie_header("tok123")
        self.assertIn("portal_session=tok123", header)
        self.assertIn("Path=/", header)
        self.assertIn("HttpOnly", header)
        self.assertIn("SameSite=Lax", header)
        self.assertNotIn("Domain=", header)

    def test_optional_domain(self):
        api = load_portal_api()
        os.environ["PORTAL_COOKIE_DOMAIN"] = ".example.com"
        try:
            header = api.session_cookie_header("tok")
            self.assertIn("Domain=.example.com", header)
        finally:
            os.environ.pop("PORTAL_COOKIE_DOMAIN", None)


class AuthUrlTests(unittest.TestCase):
    def test_every_recording_instance_is_tried(self):
        api = load_portal_api()
        urls = api.auth_login_urls()
        for name in api.AUTH_INSTANCE_IDS:
            self.assertIn(f"https://frigate-{name}:8971/api/login", urls)
        self.assertNotIn("https://frigate-temp:8971/api/login", urls)


class PasswordCheckTests(unittest.TestCase):
    """The password check must never blame the user for a broken instance."""

    @staticmethod
    def stop(srv):
        srv.shutdown()
        srv.server_close()

    @staticmethod
    def stub(status: int):
        """Start a one-off HTTP server answering /api/login with `status`."""
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        import threading

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length") or 0))
                self.send_response(status)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *a):
                pass

        srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        return srv, f"http://127.0.0.1:{srv.server_address[1]}/api/login"

    def test_accepts_when_any_instance_accepts(self):
        api = load_portal_api()
        bad, bad_url = self.stub(401)
        good, good_url = self.stub(200)
        try:
            api.AUTH_LOGIN_URLS = [bad_url, good_url]
            report = api.verify_frigate_password("ceo", "pw")
        finally:
            self.stop(bad)
            self.stop(good)
        self.assertEqual(report["result"], "ok")
        self.assertEqual(report["broken"], 0)

    def test_all_rejecting_is_unauthorized(self):
        api = load_portal_api()
        a, a_url = self.stub(401)
        b, b_url = self.stub(401)
        try:
            api.AUTH_LOGIN_URLS = [a_url, b_url]
            report = api.verify_frigate_password("ceo", "pw")
        finally:
            self.stop(a)
            self.stop(b)
        self.assertEqual(report["result"], "unauthorized")
        self.assertEqual(report["rejected"], 2)
        self.assertEqual(report["broken"], 0)

    def test_nothing_reachable_is_unavailable_not_bad_password(self):
        api = load_portal_api()
        api.AUTH_LOGIN_URLS = ["http://127.0.0.1:1/api/login"]
        report = api.verify_frigate_password("ceo", "pw")
        self.assertEqual(report["result"], "unavailable")
        self.assertEqual(report["rejected"], 0)
        self.assertEqual(report["broken"], 1)

    def test_partial_answer_is_reported(self):
        """One instance says 401, another is down → 401 but flagged partial."""
        api = load_portal_api()
        a, a_url = self.stub(401)
        try:
            api.AUTH_LOGIN_URLS = [a_url, "http://127.0.0.1:1/api/login"]
            report = api.verify_frigate_password("ceo", "pw")
        finally:
            self.stop(a)
        self.assertEqual(report["result"], "unauthorized")
        self.assertEqual(report["rejected"], 1)
        self.assertEqual(report["broken"], 1)

    def test_every_instance_appears_in_the_trace(self):
        api = load_portal_api()
        a, a_url = self.stub(401)
        try:
            api.AUTH_LOGIN_URLS = [a_url, "http://127.0.0.1:1/api/login"]
            report = api.verify_frigate_password("ceo", "pw")
        finally:
            self.stop(a)
        self.assertEqual(len(report["checked"]), 2)
        self.assertTrue(any("401" in c for c in report["checked"]))


class NginxTokenUnityTests(unittest.TestCase):
    def test_http_and_ssl_share_locations_and_gate_on_cookie(self):
        http_conf = (PORTAL / "nginx.conf").read_text(encoding="utf-8")
        ssl_tpl = (PORTAL / "nginx.ssl.conf.template").read_text(encoding="utf-8")
        locations = (PORTAL / "nginx-portal-locations.inc").read_text(encoding="utf-8")
        auth_inc = (PORTAL / "nginx-frigate-auth.inc").read_text(encoding="utf-8")

        self.assertIn("include /usr/share/nginx/html/nginx-portal-locations.inc", http_conf)
        self.assertIn("include /usr/share/nginx/html/nginx-portal-locations.inc", ssl_tpl)
        self.assertIn("auth_request /internal/session", auth_inc)
        self.assertIn("error_page 401 403 = @portal_login", auth_inc)
        self.assertIn("location @portal_login", locations)
        self.assertIn("return 302 /?next=$uri", locations)
        self.assertNotIn("8971", locations)
        self.assertNotIn("8971", http_conf)
        self.assertNotIn("8971", ssl_tpl)
        self.assertNotIn("server_name cafe.", ssl_tpl)

        self.assertIn("frigate-temp:5000", locations)
        for site in SITES:
            self.assertIn(f"location /{site}/", locations)
            if site != "temp":
                self.assertRegex(locations, rf"proxy_pass http://frigate-{site}:5000")

    def test_frontend_does_not_call_frigate_login(self):
        app = (PORTAL / "js/app.js").read_text(encoding="utf-8")
        self.assertNotIn("loginAll", app)
        self.assertNotIn("/api/login", app)
        self.assertIn("/api/portal-login/", app)
        self.assertIn("verifyPortalSession", app)
        self.assertIn("__PORTAL_USER", app)


if __name__ == "__main__":
    unittest.main()
