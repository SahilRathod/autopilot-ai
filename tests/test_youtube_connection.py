"""Local YouTube connection tests; never contact a real Google account."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from app import platform_core as core, youtube_connection as yt


class YouTubeConnectionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        p = patch.object(core, "DB", Path(temp.name) / "db.sqlite")
        p.start()
        self.addCleanup(p.stop)
        core.initialize()
        yt.initialize()
        self.w = core.new_workspace("Local")
        self.c = core.new_channel(self.w, "Gaming", "gaming")
        self.other = core.new_workspace("Other")
        self.other_c = core.new_channel(self.other, "Other", "gaming")
        (core.DB.parent / "youtube-client.json").write_text(json.dumps({"installed": {
            "client_id": "test.apps.googleusercontent.com",
            "client_secret": "test-secret", "redirect_uris": ["http://localhost"]}}))
        for p in (patch.object(yt, "protect", side_effect=lambda s: b"encrypted:" + s.encode()),
                  patch.object(yt, "unprotect", side_effect=lambda b: b.decode().removeprefix("encrypted:"))):
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(yt.clear_pending)

    def begin(self):
        return parse_qs(urlsplit(yt.begin(self.w, self.c)["authorization_url"]).query)

    def token(self):
        return {"access_token": "access-secret", "refresh_token": "refresh-secret",
                "scope": yt.READ_SCOPE, "expires_in": 3600}

    def channel(self):
        return {"id": "UC-test", "title": "Gaming channel", "subscriber_count": "100",
                "video_count": "7", "view_count": "1234", "thumbnail_url": ""}

    def link(self):
        q = self.begin()
        with patch.object(yt, "exchange_code", return_value=self.token()) as exchange, \
             patch.object(yt, "read_channel", return_value=self.channel()):
            yt.finish(q["state"][0], "code")
        self.assertEqual(exchange.call_count, 1)
        return q

    def test_pkce_and_scope_and_single_use_state(self):
        q = self.link()
        self.assertEqual(q["code_challenge_method"], ["S256"])
        self.assertEqual(q["scope"], [yt.READ_SCOPE])
        self.assertEqual(q["access_type"], ["offline"])
        self.assertEqual(q["redirect_uri"], ["http://127.0.0.1:8000/api/v1/youtube/callback"])
        with self.assertRaises(ValueError):
            yt.finish(q["state"][0], "code")
        self.assertEqual(yt.status(self.w, self.c)["channel"]["id"], "UC-test")
        self.assertFalse(yt.status(self.other, self.other_c)["connected"])
        with self.assertRaises(ValueError):
            yt.status(self.other, self.c)

    def test_never_returns_token_and_rejects_reconnect(self):
        self.link()
        status = json.dumps(yt.status(self.w, self.c))
        self.assertNotIn("refresh-secret", status)
        self.assertNotIn("access-secret", status)
        with self.assertRaises(ValueError):
            self.begin()

    def test_refresh_checks_same_channel_and_disconnect_revokes(self):
        self.link()
        with patch.object(yt, "refresh_access", return_value="new-access"), \
             patch.object(yt, "read_channel", return_value=self.channel()):
            self.assertTrue(yt.refresh(self.w, self.c)["connected"])
        with patch.object(yt, "refresh_access", return_value="new-access"), \
             patch.object(yt, "read_channel", return_value=self.channel() | {"id": "other"}):
            with self.assertRaises(ValueError):
                yt.refresh(self.w, self.c)
        with patch.object(yt, "revoke_token") as revoke:
            yt.disconnect(self.w, self.c)
        revoke.assert_called_once_with("refresh-secret")
        self.assertFalse(yt.status(self.w, self.c)["connected"])

    def test_denied_scope_or_missing_refresh_token_does_not_link(self):
        for tok in (self.token() | {"scope": "wrong"}, self.token() | {"refresh_token": ""}):
            q = self.begin()
            with patch.object(yt, "exchange_code", return_value=tok), \
                 patch.object(yt, "read_channel", return_value=self.channel()):
                with self.assertRaises(ValueError):
                    yt.finish(q["state"][0], "code")
        self.assertFalse(yt.status(self.w, self.c)["connected"])

    def test_invalid_state_and_wrong_scope_do_not_contact_google(self):
        with patch.object(yt, "exchange_code") as exchange:
            with self.assertRaises(ValueError):
                yt.finish("random", "code")
            exchange.assert_not_called()

    def test_revocation_failure_keeps_link_for_retry(self):
        self.link()
        with patch.object(yt, "revoke_token", side_effect=RuntimeError("offline")):
            with self.assertRaises(RuntimeError):
                yt.disconnect(self.w, self.c)
        self.assertTrue(yt.status(self.w, self.c)["connected"])


    def test_http_connection_callback_is_scoped_and_never_returns_credentials(self):
        from fastapi.testclient import TestClient
        from apps.api.main import app
        with TestClient(app, base_url="http://127.0.0.1:8000") as client:
            path = f"/api/v1/workspaces/{self.w}/channels/{self.c}/youtube"
            response = client.post(path + "/connect", json={})
            self.assertEqual(response.status_code, 200, response.text)
            q = parse_qs(urlsplit(response.json()["authorization_url"]).query)
            with patch.object(yt, "exchange_code", return_value=self.token()), \
                 patch.object(yt, "read_channel", return_value=self.channel()):
                callback = client.get("/api/v1/youtube/callback",
                                      params={"state": q["state"][0], "code": "code"})
            self.assertEqual(callback.status_code, 200)
            self.assertIn("Connection successful", callback.text)
            self.assertNotIn("access-secret", callback.text)
            status = client.get(path).json()
            self.assertTrue(status["connected"])
            self.assertNotIn("refresh-secret", json.dumps(status))
            self.assertTrue(client.get(f"/api/v1/workspaces/{self.w}/overview").json()["youtube_connected"])
            self.assertFalse(client.get(f"/api/v1/workspaces/{self.other}/overview").json()["youtube_connected"])
            self.assertEqual(client.get(f"/api/v1/workspaces/{self.other}/channels/{self.c}/youtube").status_code, 404)

    def test_expired_state_is_rejected_before_token_exchange(self):
        q = self.begin()
        with patch.object(yt.time, "monotonic", return_value=yt.time.monotonic() + 601), \
             patch.object(yt, "exchange_code") as exchange:
            with self.assertRaises(ValueError):
                yt.finish(q["state"][0], "code")
            exchange.assert_not_called()


    def test_forget_local_does_not_call_google_and_removes_credential(self):
        self.link()
        with patch.object(yt, "revoke_token") as revoke:
            result = yt.forget_local(self.w, self.c)
        revoke.assert_not_called()
        self.assertFalse(result["connected"])
        with core.connect() as db:
            self.assertIsNone(db.execute("SELECT 1 FROM youtube_links").fetchone())
