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
