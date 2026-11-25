"""Acceptance runner must leave the user's working database and media untouched."""
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import acceptance, editor, platform_core as core


class AcceptanceTests(unittest.TestCase):
    def test_missing_dependency_is_reported_without_creating_data(self):
        before = (core.DB, editor.RAW, editor.OUT)
        with patch.object(acceptance.shutil, "which", return_value=None):
            result = acceptance.run()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failed_stage"], "prerequisites")
        self.assertEqual((core.DB, editor.RAW, editor.OUT), before)
        self.assertFalse(result["live_youtube_verified"])

    def test_rejects_non_video_input_without_using_production_database(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "not-video.txt"
            file.write_text("not a video", encoding="utf-8")
            before = (core.DB, editor.RAW, editor.OUT)
            with patch.object(acceptance.shutil, "which", return_value="available"):
                report = acceptance.run(file)
            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["failed_stage"], "input")
            self.assertEqual((core.DB, editor.RAW, editor.OUT), before)
            self.assertNotIn(str(file), str(report))

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg unavailable")
    def test_real_local_workflow_reports_measured_export_and_restores_paths(self):
        before = (core.DB, editor.RAW, editor.OUT)
        with patch("app.ai_director.cloud", side_effect=AssertionError("No cloud requests")), \
             patch("app.youtube_connection._request", side_effect=AssertionError("No Google requests")):
            result = acceptance.run()
        self.assertEqual(result["status"], "passed", result)
        self.assertEqual(result["input_kind"], "synthetic")
        self.assertEqual(result["render"]["width"], 720)
        self.assertEqual(result["render"]["height"], 1280)
        self.assertGreater(result["render"]["seconds"], 0)
        self.assertGreater(result["render"]["wall_seconds"], 0)
        self.assertEqual(result["revisions"], 3)
        self.assertFalse(result["live_youtube_verified"])
        self.assertEqual((core.DB, editor.RAW, editor.OUT), before)
        self.assertTrue(all(step["status"] == "passed" for step in result["steps"]))
