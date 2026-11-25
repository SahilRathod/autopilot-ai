"""API regression tests for local media candidates and tenant boundary."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient

from app import editor, media_intelligence as media, platform_core as core, highlight_ranker as ranker
from apps.api.main import app


class MediaAPITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        folder = Path(self.tmp.name).resolve()
        self.raw = folder / "raw"
        self.raw.mkdir()
        (self.raw / "raw.mp4").write_bytes(b"realistic test placeholder")
        self.p_db = patch.object(core, "DB", folder / "db.sqlite")
        self.p_raw = patch.object(editor, "RAW", self.raw)
        self.p_db.start()
        self.p_raw.start()
        self.client = TestClient(app)
        self.client.__enter__()
        self.w = core.new_workspace("A")
        self.c = core.new_channel(self.w, "Gaming", "gaming")
        self.other = core.new_workspace("Other")
        self.other_c = core.new_channel(self.other, "Tech", "technology")
        self.meta = {"duration_seconds": 44.0, "width": 1280, "height": 720,
                     "fps": 30.0, "video_codec": "h264", "audio_codec": None}

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.p_raw.stop()
        self.p_db.stop()
        self.tmp.cleanup()

    def test_api_import_scan_list_and_tenant_isolation(self):
        base = f"/api/v1/workspaces/{self.w}/channels/{self.c}/media"
        other = f"/api/v1/workspaces/{self.other}/channels/{self.other_c}/media"
        with patch.object(media, "probe_metadata", return_value=self.meta):
            response = self.client.post(base + "/import", json={"filename": "raw.mp4"})
        self.assertEqual(response.status_code, 201)
        asset = response.json()
        self.assertEqual(asset["filename"], "raw.mp4")
        self.assertEqual(len(self.client.get(base + "/assets").json()), 1)
        self.assertEqual(self.client.get(other + "/assets").json(), [])
        self.assertEqual(self.client.get(other + f"/assets/{asset['id']}").status_code, 404)
        with patch.object(media, "detect_changes", return_value=[7.0, 20.0]):
            scan = self.client.post(base + f"/assets/{asset['id']}/scan",
                                    json={"clip_seconds": 10, "threshold": 0.35,
                                          "max_scan_seconds": 44})
        self.assertEqual(scan.status_code, 200)
        candidates = self.client.get(base + f"/assets/{asset['id']}/candidates").json()
        self.assertEqual(len(candidates), scan.json()["candidate_count"])
        self.assertGreaterEqual(len(candidates), 2)
        self.assertEqual(self.client.get(other + f"/assets/{asset['id']}/candidates").status_code, 404)

    def test_video_preview_supports_byte_ranges_without_leaking_other_channels(self):
        base = f"/api/v1/workspaces/{self.w}/channels/{self.c}/media"
        other = f"/api/v1/workspaces/{self.other}/channels/{self.other_c}/media"
        with patch.object(media, "probe_metadata", return_value=self.meta):
            asset = self.client.post(base + "/import", json={"filename": "raw.mp4"}).json()
        url = base + f"/assets/{asset['id']}/preview"
        response = self.client.get(url, headers={"Range": "bytes=2-5"})
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response.content, b"alis")
        self.assertEqual(response.headers["content-range"],
                         f"bytes 2-5/{len((self.raw / 'raw.mp4').read_bytes())}")
        self.assertEqual(response.headers["content-type"], "video/mp4")
        self.assertEqual(response.headers["cache-control"], "private, no-store")
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertEqual(self.client.get(other + f"/assets/{asset['id']}/preview").status_code, 404)

    def test_range_requests_reuse_verified_source_until_file_changes(self):
        base = f"/api/v1/workspaces/{self.w}/channels/{self.c}/media"
        with patch.object(media, "probe_metadata", return_value=self.meta):
            item = self.client.post(base + "/import", json={"filename": "raw.mp4"}).json()
        # Clear the preview cache to keep this test independent of previous tests.
        media._cached_preview_hash.cache_clear()
        url = base + f"/assets/{item['id']}/preview"
        original_hash = media._fingerprint
        with patch.object(media, "_fingerprint", wraps=original_hash) as fingerprint:
            self.assertEqual(self.client.get(url, headers={"Range": "bytes=0-3"}).status_code, 206)
            self.assertEqual(self.client.get(url, headers={"Range": "bytes=4-7"}).status_code, 206)
            self.assertEqual(fingerprint.call_count, 1, "Repeated ranges must not rehash unchanged video")
            (self.raw / "raw.mp4").write_bytes(b"the content has been changed")
            self.assertEqual(self.client.get(url).status_code, 409)
            self.assertEqual(fingerprint.call_count, 2)

    def test_video_preview_refuses_source_changed_since_import(self):
        base = f"/api/v1/workspaces/{self.w}/channels/{self.c}/media"
        with patch.object(media, "probe_metadata", return_value=self.meta):
            asset = self.client.post(base + "/import", json={"filename": "raw.mp4"}).json()
        (self.raw / "raw.mp4").write_bytes(b"modified raw data")
        response = self.client.get(base + f"/assets/{asset['id']}/preview")
        self.assertEqual(response.status_code, 409)
        self.assertIn("changed", response.json()["detail"].lower())


    def test_ranked_candidate_endpoint_returns_explainable_local_scores(self):
        base = f"/api/v1/workspaces/{self.w}/channels/{self.c}/media"
        other = f"/api/v1/workspaces/{self.other}/channels/{self.other_c}/media"
        with patch.object(media, "probe_metadata", return_value=self.meta):
            asset = self.client.post(base + "/import", json={"filename": "raw.mp4"}).json()
        with patch.object(media, "detect_changes", return_value=[12, 29]):
            scan = self.client.post(base + f"/assets/{asset['id']}/scan",
                                    json={"clip_seconds": 10})
        self.assertEqual(scan.status_code, 200)
        ranking = self.client.post(base + f"/assets/{asset['id']}/rank",
                                   json={"profile": "sandbox", "max_seconds": 100})
        self.assertEqual(ranking.status_code, 200)
        rows = ranking.json()
        self.assertGreaterEqual(len(rows), 2)
        self.assertEqual(rows[0]["profile"], "sandbox")
        self.assertIn("reasons", rows[0]["evidence"])
        self.assertEqual(rows[0]["audio_analyzed"], False)
        response = self.client.get(base + f"/assets/{asset['id']}/rankings?profile=sandbox")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), rows)
        self.assertEqual(self.client.get(other + f"/assets/{asset['id']}/rankings?profile=sandbox").status_code, 404)
        self.assertEqual(self.client.post(base + f"/assets/{asset['id']}/rank",
                                         json={"profile": "imaginary"}).status_code, 422)

    def test_ranking_requires_scene_scan_and_is_reset_by_rescan(self):
        base = f"/api/v1/workspaces/{self.w}/channels/{self.c}/media"
        with patch.object(media, "probe_metadata", return_value=self.meta):
            asset = self.client.post(base + "/import", json={"filename": "raw.mp4"}).json()
        target = base + f"/assets/{asset['id']}"
        self.assertEqual(self.client.post(target + "/rank", json={}).status_code, 409)
        with patch.object(media, "detect_changes", return_value=[]):
            self.assertEqual(self.client.post(target + "/scan", json={}).status_code, 200)
        self.assertEqual(self.client.post(target + "/rank", json={}).status_code, 200)
        with patch.object(media, "detect_changes", return_value=[22]):
            self.assertEqual(self.client.post(target + "/scan", json={}).status_code, 200)
        self.assertEqual(self.client.get(target + "/rankings").json(), [])

    def test_api_rejects_bad_input(self):
        base = f"/api/v1/workspaces/{self.w}/channels/{self.c}/media"
        self.assertEqual(self.client.post(base + "/import",
                         json={"filename": "../passwords.mp4"}).status_code, 422)
        self.assertEqual(self.client.post(base + "/import",
                         json={"filename": "raw.mp4", "unsupported": True}).status_code, 422)


if __name__ == "__main__":
    unittest.main()
