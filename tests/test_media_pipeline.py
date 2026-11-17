"""Tests for manual FFmpeg production linkage; subprocess is mocked."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from app import platform_core as core, media_pipeline as media
from app import editor

class MediaWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_override = patch.object(core, "DB", Path(self.temp.name) / "db.sqlite")
        self.db_override.start()
        self.raw_override = patch.object(editor, "RAW", Path(self.temp.name) / "raw")
        self.raw_override.start()
        self.out_override = patch.object(editor, "OUT", Path(self.temp.name) / "out")
        self.out_override.start()
        editor.RAW.mkdir()
        (editor.RAW / "footage.mp4").write_bytes(b"fake source")
        core.initialize()
        self.w = core.new_workspace("Studio")
        self.ch = core.new_channel(self.w, "Gaming", "gaming")
        self.j = core.add_job(self.w, self.ch, "Original highlight", "short")

    def tearDown(self):
        self.out_override.stop(); self.raw_override.stop()
        self.db_override.stop(); self.temp.cleanup()

    def test_approval_required_for_manual_render(self):
        with self.assertRaises(ValueError):
            media.render_job(self.w, self.j, "footage.mp4", 0, 3)

    def test_finished_render_is_persisted_once(self):
        core.transition(self.w, self.j, "ready_for_review")
        core.transition(self.w, self.j, "approved")
        def fake_highlight(source, start, seconds, vertical, filename):
            self.assertEqual(source, "footage.mp4")
            self.assertTrue(vertical)
            editor.OUT.mkdir(exist_ok=True)
            output = editor.OUT / filename
            output.write_bytes(b"rendered")
            return str(output)
        with patch.object(editor, "highlight", side_effect=fake_highlight) as mocked:
            first = media.render_job(self.w, self.j, "footage.mp4", 0, 3)
            self.assertEqual(first["state"], "ready")
            self.assertTrue(Path(first["output_path"]).exists())
            with self.assertRaises(ValueError):
                media.render_job(self.w, self.j, "footage.mp4", 0, 3)
            self.assertEqual(mocked.call_count, 1)
        other = core.new_workspace("Other")
        with self.assertRaises(ValueError):
            media.render_job(other, self.j, "footage.mp4", 0, 3)

    def test_failed_render_can_retry(self):
        core.transition(self.w, self.j, "ready_for_review")
        core.transition(self.w, self.j, "approved")
        with patch.object(editor, "highlight", side_effect=RuntimeError("ffmpeg failure")):
            with self.assertRaises(RuntimeError):
                media.render_job(self.w, self.j, "footage.mp4", 0, 3)
        with core.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM job_renders").fetchone()[0], 0)
        self.assertEqual(core.jobs(self.w)[0]["state"], "approved")

if __name__=="__main__":
    unittest.main()
