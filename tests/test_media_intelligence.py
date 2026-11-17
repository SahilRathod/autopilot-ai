"""V0.5 media intelligence: test-first channel scoping, probe, scene cuts and safe render."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import platform_core as core, editor, media_pipeline, media_intelligence as media


class MediaIntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.raw = self.root / "raw"
        self.raw.mkdir()
        (self.raw / "game.mp4").write_bytes(b"unchanged demo source")
        self.p_db = patch.object(core, "DB", self.root / "test.sqlite")
        self.p_raw = patch.object(editor, "RAW", self.raw)
        self.p_db.start()
        self.p_raw.start()
        core.initialize()
        media.initialize()
        self.w = core.new_workspace("One")
        self.c = core.new_channel(self.w, "Gaming", "gaming")
        self.c2 = core.new_channel(self.w, "Tech", "technology")
        self.other = core.new_workspace("Other")
        self.other_c = core.new_channel(self.other, "Another", "gaming")
        self.metadata = {
            "duration_seconds": 32.0, "width": 1920, "height": 1080,
            "fps": 60.0, "video_codec": "h264", "audio_codec": "aac",
        }

    def tearDown(self):
        self.p_raw.stop()
        self.p_db.stop()
        self.temp.cleanup()

    def _import(self, channel_id=None):
        with patch.object(media, "probe_metadata", return_value=self.metadata):
            return media.import_media(self.w, channel_id or self.c, "game.mp4")

    def test_import_is_idempotent_and_scoped(self):
        first = self._import()
        same = self._import()
        different_channel = self._import(self.c2)
        self.assertEqual(first["id"], same["id"])
        self.assertNotEqual(first["id"], different_channel["id"])
        self.assertEqual(len(media.assets(self.w, self.c)), 1)
        self.assertEqual(media.assets(self.other, self.other_c), [])
        with self.assertRaises(ValueError):
            media.asset(self.other, self.other_c, first["id"])
        with self.assertRaises(ValueError):
            media.import_media(self.w, self.c, "../game.mp4")

    def test_scan_builds_bounded_segments_and_rejects_changed_sources(self):
        imported = self._import()
        with patch.object(media, "detect_changes", return_value=[2.0, 9.0, 9.6, 29.0, 50.0]) as detect:
            result = media.scan_media(self.w, self.c, imported["id"],
                                      clip_seconds=12, max_scan_seconds=32)
        self.assertEqual(result["asset_id"], imported["id"])
        self.assertGreaterEqual(result["candidate_count"], 2)
        self.assertLessEqual(result["candidate_count"], 5)
        found = media.candidates(self.w, self.c, imported["id"])
        self.assertTrue(all(0 <= r["start_seconds"] <= 20 for r in found))
        self.assertTrue(all(r["duration_seconds"] <= 12 for r in found))
        self.assertIn("opening_segment", {r["reason"] for r in found})
        detect.assert_called_once()
        with self.assertRaises(ValueError):
            media.candidates(self.other, self.other_c, imported["id"])

        (self.raw / "game.mp4").write_bytes(b"changed video after import")
        with self.assertRaises(ValueError):
            media.scan_media(self.w, self.c, imported["id"])

    def test_empty_scan_still_offers_manual_opening_segment(self):
        imported = self._import()
        with patch.object(media, "detect_changes", return_value=[]):
            result = media.scan_media(self.w, self.c, imported["id"], clip_seconds=15)
        self.assertEqual(result["candidate_count"], 1)
        item = media.candidates(self.w, self.c, imported["id"])[0]
        self.assertEqual(item["start_seconds"], 0)
        self.assertEqual(item["reason"], "opening_segment")

    def test_render_candidate_reuses_approved_job_and_guards_scope(self):
        imported = self._import()
        with patch.object(media, "detect_changes", return_value=[8]):
            media.scan_media(self.w, self.c, imported["id"], clip_seconds=10)
        suggestion = next(x for x in media.candidates(self.w, self.c, imported["id"])
                          if x["reason"] == "scene_change")
        job = core.add_job(self.w, self.c, "Approved content", "short")
        with patch.object(media_pipeline, "render_job") as run:
            with self.assertRaises(ValueError):
                media.render_candidate(self.w, self.c, suggestion["id"], job)
            run.assert_not_called()
            core.transition(self.w, job, "ready_for_review")
            core.transition(self.w, job, "approved")
            run.return_value = {"state": "ready", "youtube_uploaded": False}
            result = media.render_candidate(self.w, self.c, suggestion["id"], job)
            self.assertFalse(result["youtube_uploaded"])
            run.assert_called_once_with(self.w, job, "game.mp4",
                                        suggestion["start_seconds"],
                                        suggestion["duration_seconds"])

        other_job = core.add_job(self.w, self.c2, "Wrong channel", "short")
        with self.assertRaises(ValueError):
            media.render_candidate(self.w, self.c, suggestion["id"], other_job)
        with self.assertRaises(ValueError):
            media.render_candidate(self.other, self.other_c, suggestion["id"], job)

    def test_invalid_scan_inputs_are_rejected(self):
        imported = self._import()
        for kwargs in ({"threshold": 0}, {"threshold": 2}, {"clip_seconds": -5},
                       {"max_scan_seconds": 10000}, {"clip_seconds": float("nan")}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                media.scan_media(self.w, self.c, imported["id"], **kwargs)

    def test_ffprobe_json_fields(self):
        reply = {
            "format": {"duration": "10.25"},
            "streams": [
                {"codec_type": "video", "codec_name": "h264",
                 "width": 1280, "height": 720, "avg_frame_rate": "30000/1001"},
                {"codec_type": "audio", "codec_name": "aac"},
            ],
        }
        with patch.object(media.shutil, "which", return_value="ffprobe"), \
             patch.object(media.subprocess, "run",
                          return_value=subprocess.CompletedProcess([], 0, json.dumps(reply), "")):
            found = media.probe_metadata(self.raw / "game.mp4")
        self.assertEqual(found["duration_seconds"], 10.25)
        self.assertEqual(found["width"], 1280)
        self.assertAlmostEqual(found["fps"], 29.97, places=2)
        self.assertEqual(found["audio_codec"], "aac")

    def test_cut_detection_parses_ffmpeg_showinfo(self):
        output = ("[Parsed_showinfo_3 @ 0xabc] n: 0 pts: 3 pts_time:2.5 "
                  "fmt:yuv420p\n[Parsed_showinfo_3 @ 0xabc] n: 1 pts: 7 pts_time:5.5 fmt:yuv420p\n")
        with patch.object(media.shutil, "which", return_value="ffmpeg"), \
             patch.object(media.subprocess, "run",
                          return_value=subprocess.CompletedProcess([], 0, "", output)) as run:
            found = media.detect_changes(self.raw / "game.mp4", 8, 0.35)
        self.assertEqual(found, [2.5, 5.5])
        self.assertIn("showinfo", run.call_args.args[0][run.call_args.args[0].index("-vf") + 1])

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                         "Real FFmpeg/FFprobe unavailable")
    def test_real_ffmpeg_detects_synthetic_color_cut(self):
        path = self.raw / "synthetic.mp4"
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=c=red:s=160x90:r=15:d=2",
            "-f", "lavfi", "-i", "color=c=blue:s=160x90:r=15:d=2",
            "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]",
            "-map", "[v]", "-y", str(path),
        ], check=True, timeout=30)
        metadata = media.probe_metadata(path)
        self.assertAlmostEqual(metadata["duration_seconds"], 4, delta=0.15)
        scene_times = media.detect_changes(path, 4, 0.25)
        self.assertTrue(any(abs(t-2) < 0.6 for t in scene_times), scene_times)


if __name__ == "__main__":
    unittest.main()
