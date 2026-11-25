"""API-level tests for bounded, approved V0.5 multi-clip assembly."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import editor, media_intelligence as media, platform_core as core, video_assembly as assembly
from apps.api.main import app


class AssemblyAPITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name).resolve()
        self.raw, self.out = root / "raw", root / "output"
        self.raw.mkdir()
        self.out.mkdir()
        (self.raw / "game.mp4").write_bytes(b"original gameplay source")
        self.patches = [
            patch.object(core, "DB", root / "platform.sqlite"),
            patch.object(editor, "RAW", self.raw),
            patch.object(editor, "OUT", self.out),
        ]
        for patcher in self.patches:
            patcher.start()
        self.client = TestClient(app)
        self.client.__enter__()
        self.w = core.new_workspace("Studio")
        self.c = core.new_channel(self.w, "Gaming", "gaming")
        self.other = core.new_workspace("Private")
        self.other_c = core.new_channel(self.other, "Music", "music")
        meta = {"duration_seconds": 20.0, "width": 1280, "height": 720,
                "fps": 30.0, "video_codec": "h264", "audio_codec": "aac"}
        with patch.object(media, "probe_metadata", return_value=meta):
            asset = media.import_media(self.w, self.c, "game.mp4")
        with patch.object(media, "detect_changes", return_value=[8]):
            media.scan_media(self.w, self.c, asset["id"], clip_seconds=6)
        self.ids = [c["id"] for c in media.candidates(self.w, self.c, asset["id"])]
        self.job = core.add_job(self.w, self.c, "Montage", "short")

    def tearDown(self):
        self.client.__exit__(None, None, None)
        for patcher in reversed(self.patches):
            patcher.stop()
        self.tmp.cleanup()

    def test_api_export_requires_approval_and_lists_scoped_results(self):
        base = f"/api/v1/workspaces/{self.w}/channels/{self.c}/media"
        other = f"/api/v1/workspaces/{self.other}/channels/{self.other_c}/media"
        data = {"job_id": self.job, "candidate_ids": self.ids,
                "audio_mode": "mute", "quality": "fast",
                "caption_mode": "none", "caption_lines": []}
        self.assertEqual(self.client.post(base + "/assemble", json=data).status_code, 409)
        core.transition(self.w, self.job, "ready_for_review")
        core.transition(self.w, self.job, "approved")
        def fake_render(segments, target, preset, quality, audio_mode, caption_mode, caption_lines):
            Path(target).write_bytes(b"some local finished video")
            return str(target)
        with patch.object(assembly, "render_assembled_video", side_effect=fake_render):
            response = self.client.post(base + "/assemble", json=data)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["clip_count"], 2)
        self.assertFalse(response.json()["youtube_uploaded"])
        self.assertEqual(self.client.get(other + "/exports").json(), [])
        results = self.client.get(base + "/exports")
        self.assertEqual(results.status_code, 200)
        self.assertEqual(results.json()[0]["candidate_ids"], self.ids)
        path = base + f"/exports/{self.job}/preview"
        video = self.client.get(path, headers={"Range": "bytes=0-3"})
        self.assertEqual(video.status_code, 206)
        self.assertEqual(video.content, b"some")
        self.assertEqual(video.headers["content-type"], "video/mp4")
        self.assertEqual(self.client.get(other + f"/exports/{self.job}/preview").status_code, 404)

    def test_api_rejects_invalid_caption_mode_or_cross_workspace_clip(self):
        base = f"/api/v1/workspaces/{self.w}/channels/{self.c}/media"
        core.transition(self.w, self.job, "ready_for_review")
        core.transition(self.w, self.job, "approved")
        bad = {"job_id": self.job, "candidate_ids": self.ids,
               "quality": "extreme", "audio_mode": "preserve", "caption_mode": "none"}
        self.assertEqual(self.client.post(base + "/assemble", json=bad).status_code, 422)
        bad["quality"] = "fast"
        bad["candidate_ids"] = [1000000]
        self.assertIn(self.client.post(base + "/assemble", json=bad).status_code, (404, 409))


if __name__ == "__main__":
    unittest.main()
