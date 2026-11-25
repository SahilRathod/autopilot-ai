import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import platform_core as core, youtube_connection as yt, youtube_insights as insights


class InsightsTests(unittest.TestCase):
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
        self.other = core.new_channel(self.w, "Other", "gaming")
        with core.connect() as db:
            db.execute("""INSERT INTO youtube_links(local_channel_id, workspace_id,
                remote_channel_id,profile_json,encrypted_refresh,client_id)
                VALUES(?,?,?,?,?,?)""", (self.c,self.w,"UC-owner",'{"id":"UC-owner"}',b"secret","client"))
        for p in (patch.object(yt,"config",return_value={"client_id":"client"}),
                  patch.object(yt,"unprotect",return_value="refresh-secret"),
                  patch.object(yt,"refresh_access",return_value="access-secret")):
            p.start()
            self.addCleanup(p.stop)

    def test_recent_uploads_use_owner_playlist_and_actual_counts(self):
        replies = [
            {"items":[{"id":"UC-owner","snippet":{"title":"Gaming"},"statistics":{"viewCount":"123","hiddenSubscriberCount":True},"contentDetails":{"relatedPlaylists":{"uploads":"UU-owner"}}}]},
            {"items":[{"contentDetails":{"videoId":"abc"}},{"contentDetails":{"videoId":"def"}}]},
            {"items":[{"id":"abc","snippet":{"channelId":"UC-owner","title":"A","publishedAt":"2026-01-01T00:00:00Z"},"statistics":{"viewCount":"12","likeCount":"2"},"status":{"privacyStatus":"private"}},
                      {"id":"def","snippet":{"channelId":"other","title":"Wrong"}}]}
        ]
        with patch.object(insights,"_get",side_effect=replies) as fetch:
            result=insights.snapshot(self.w,self.c)
        self.assertEqual(fetch.call_count,3)
        self.assertEqual(result["channel"]["views"],"123")
        self.assertIsNone(result["channel"]["subscribers"])
        self.assertEqual(len(result["videos"]),1)
        self.assertEqual(result["videos"][0]["views"],"12")
        self.assertIsNone(result["videos"][0]["comments"])
        self.assertNotIn("secret",json.dumps(result))
        self.assertEqual(fetch.call_args_list[1].args[2]["playlistId"],"UU-owner")

    def test_identity_mismatch_and_unlinked_channel_fail_closed(self):
        with patch.object(insights,"_get",return_value={"items":[{"id":"wrong"}]}) as fetch:
            with self.assertRaises(ValueError):
                insights.snapshot(self.w,self.c)
            self.assertEqual(fetch.call_count,1)
        with patch.object(insights,"_get") as fetch:
            with self.assertRaises(ValueError):
                insights.snapshot(self.w,self.other)
            fetch.assert_not_called()

    def test_comments_require_owned_video(self):
        with patch.object(insights,"_get",return_value={"items":[{"id":"abc","snippet":{"channelId":"wrong"}}]}) as fetch:
            with self.assertRaises(ValueError):
                insights.comments(self.w,self.c,"abc")
            self.assertEqual(fetch.call_count,1)

    def test_comments_plain_text_only(self):
        with patch.object(insights,"_get",side_effect=[
            {"items":[{"id":"abc","snippet":{"channelId":"UC-owner"}}]},
            {"items":[{"snippet":{"topLevelComment":{"id":"xyz","snippet":{"textOriginal":"Great video","authorDisplayName":"Viewer","likeCount":2,"publishedAt":"2026-01-01"}},"totalReplyCount":3}}]}
        ]) as fetch:
            result=insights.comments(self.w,self.c,"abc")
        self.assertEqual(result[0]["text"],"Great video")
        self.assertEqual(result[0]["replies"],3)
        self.assertEqual(fetch.call_args.args[2]["textFormat"],"plainText")

    def test_report_requires_analytics_scope(self):
        with patch.object(yt,"refresh_access") as refresh:
            with self.assertRaises(ValueError):
                insights.report(self.w,self.c)
            refresh.assert_not_called()

    def test_report_maps_actual_columns_and_missing_values(self):
        with core.connect() as db:
            db.execute("UPDATE youtube_links SET analytics_authorized=1")
        from unittest.mock import Mock
        response=Mock()
        response.json.return_value={"columnHeaders":[{"name":"averageViewDuration"},{"name":"views"}],"rows":[[34.5,42]]}
        with patch.object(yt,"read_channel",return_value={"id":"UC-owner"}), patch.object(yt,"_request",return_value=response) as call:
            report=insights.report(self.w,self.c)
        self.assertEqual(report["metrics"]["averageViewDuration"],34.5)
        self.assertEqual(report["metrics"]["views"],42)
        self.assertIsNone(report["metrics"]["subscribersLost"])
        self.assertEqual(call.call_args.kwargs["params"]["ids"],"channel==MINE")

    def test_http_insights_loopback_and_scope(self):
        from fastapi.testclient import TestClient
        from apps.api.main import app
        with TestClient(app,base_url="http://127.0.0.1:8000") as client, patch.object(insights,"snapshot",return_value={"videos":[]}):
            path=f"/api/v1/workspaces/{self.w}/channels/{self.c}/youtube/insights"
            self.assertEqual(client.get(path).json(),{"videos":[]})
        with TestClient(app,base_url="http://external.test") as client:
            self.assertEqual(client.get(path).status_code,403)

    def test_analytics_consent_requests_previous_upload_scope(self):
        from urllib.parse import parse_qs, urlsplit
        self.addCleanup(yt.clear_pending)
        with core.connect() as db:
            db.execute("UPDATE youtube_links SET upload_authorized=1 WHERE local_channel_id=?", (self.c,))
        with patch.object(yt,"protect",return_value=b"placeholder"):
            url=yt.begin(self.w,self.c,False,True)["authorization_url"]
        query=parse_qs(urlsplit(url).query)
        self.assertEqual(set(query["scope"][0].split()),{yt.READ_SCOPE,yt.UPLOAD_SCOPE,yt.ANALYTICS_SCOPE})
        self.assertTrue(yt.status(self.w,self.c)["upload_authorized"])
        self.assertFalse(yt.status(self.w,self.c)["analytics_authorized"])
