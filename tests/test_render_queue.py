"""Daily-use render queue: persistence, approval, isolation and recovery."""
import tempfile
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from app import editor, media_intelligence as media, platform_core as core
from app import video_assembly as assembly, render_queue as queue, media_pipeline


class RenderQueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name).resolve()
        raw = root / "raw"
        raw.mkdir()
        (raw / "game.mp4").write_bytes(b"original footage")
        for p in [patch.object(core, "DB", root / "db.sqlite"),
                  patch.object(editor, "RAW", raw), patch.object(editor, "OUT", root / "out")]:
            p.start()
            self.addCleanup(p.stop)
        core.initialize()
        media.initialize()
        queue.initialize()
        self.w = core.new_workspace("Local")
        self.c = core.new_channel(self.w, "Gaming", "gaming")
        self.other = core.new_workspace("Other")
        self.other_c = core.new_channel(self.other, "Other channel", "gaming")
        meta = {"duration_seconds": 20., "width": 640, "height": 360,
                "fps": 30., "video_codec": "h264", "audio_codec": None}
        with patch.object(media, "probe_metadata", return_value=meta):
            a = media.import_media(self.w, self.c, "game.mp4")
        with patch.object(media, "detect_changes", return_value=[]):
            media.scan_media(self.w, self.c, a["id"], clip_seconds=6)
        self.ids = [r["id"] for r in media.candidates(self.w, self.c, a["id"])]
        self.job = core.add_job(self.w, self.c, "Reviewed clip", "short")

    def approve(self):
        core.transition(self.w, self.job, "ready_for_review")
        core.transition(self.w, self.job, "approved")

    def enqueue(self):
        return queue.enqueue(self.w, self.c, self.job, self.ids)

    def fake_render(self, segments, target, *args):
        Path(target).write_bytes(b"completed synthetic output")
        return str(target)

    def test_requires_approval_and_rejects_invalid_candidates(self):
        with self.assertRaises(ValueError):
            self.enqueue()
        self.approve()
        with self.assertRaises(ValueError):
            queue.enqueue(self.w, self.c, self.job, [999999])
        self.assertEqual(queue.list_tasks(self.w, self.c), [])

    def test_enqueue_is_durable_scoped_and_does_not_render(self):
        self.approve()
        with patch.object(assembly, "render_assembled_video") as render:
            task = self.enqueue()
            self.assertEqual(task["state"], "pending")
            render.assert_not_called()
        self.assertEqual(queue.list_tasks(self.w, self.c)[0]["job_id"], self.job)
        self.assertEqual(queue.list_tasks(self.other, self.other_c), [])
        with self.assertRaises(ValueError):
            self.enqueue()
        with self.assertRaises(ValueError):
            assembly.export_job(self.w, self.c, self.job, self.ids)
        with self.assertRaises(ValueError):
            media_pipeline.render_job(self.w, self.job, "game.mp4", 0, 3)

    def test_worker_runs_one_task_and_persists_result(self):
        self.approve()
        self.enqueue()
        with patch.object(assembly, "render_assembled_video", side_effect=self.fake_render), \
             patch.object(assembly, "validate_output"):
            result = queue.run_once()
        self.assertEqual(result["state"], "ready")
        self.assertEqual(queue.list_tasks(self.w, self.c)[0]["state"], "ready")
        self.assertEqual(len(assembly.exports(self.w, self.c)), 1)
        self.assertIsNone(queue.run_once())

    def test_worker_failure_is_visible_and_can_be_retried(self):
        self.approve()
        self.enqueue()
        with patch.object(assembly, "render_assembled_video", side_effect=RuntimeError("encoder failed")):
            self.assertEqual(queue.run_once()["state"], "failed")
        self.assertEqual(queue.retry(self.w, self.c, self.job)["state"], "pending")
        with patch.object(assembly, "render_assembled_video", side_effect=self.fake_render), \
             patch.object(assembly, "validate_output"):
            self.assertEqual(queue.run_once()["state"], "ready")

    def test_interrupted_worker_reconciles_only_finished_exports(self):
        self.approve()
        self.enqueue()
        with core.connect() as db:
            db.execute("UPDATE render_tasks SET state='running' WHERE job_id=?", (self.job,))
        queue.recover()
        self.assertEqual(queue.list_tasks(self.w, self.c)[0]["state"], "interrupted")
        self.assertIsNone(queue.run_once())
        self.assertEqual(queue.retry(self.w, self.c, self.job)["state"], "pending")

    def test_output_validation_checks_expected_streams(self):
        probe = {"format": {"duration": "6.0"}, "streams": [
            {"codec_type": "video", "codec_name": "h264", "width": 720, "height": 1280},
            {"codec_type": "audio", "codec_name": "aac"}]}
        with patch.object(assembly, "probe_output", return_value=probe):
            assembly.validate_output(Path("dummy.mp4"), "short", "fast", "none", 6)
            with self.assertRaises(ValueError):
                assembly.validate_output(Path("dummy.mp4"), "short", "fast", "soft", 6)
            with self.assertRaises(ValueError):
                assembly.validate_output(Path("dummy.mp4"), "long", "fast", "none", 6)

    def test_retry_refuses_unresolved_encoder_claim(self):
        self.approve()
        self.enqueue()
        with core.connect() as db:
            db.execute("UPDATE render_tasks SET state='running' WHERE job_id=?", (self.job,))
            db.execute("""INSERT INTO assembly_exports
                (job_id,workspace_id,channel_id,state,candidate_ids_json,caption_lines_json,
                 caption_mode,audio_mode,quality,total_seconds)
                 VALUES(?,?,?,'rendering','[]','[]','none','preserve','fast',6)""",
                (self.job,self.w,self.c))
        queue.recover()
        with self.assertRaises(ValueError):
            queue.retry(self.w, self.c, self.job)


    def test_http_enqueue_and_scope(self):
        from fastapi.testclient import TestClient
        from apps.api.main import app
        self.approve()
        with TestClient(app) as client:
            base = f"/api/v1/workspaces/{self.w}/channels/{self.c}/media/render-tasks"
            other = f"/api/v1/workspaces/{self.other}/channels/{self.other_c}/media/render-tasks"
            response = client.post(base, json={"job_id": self.job, "candidate_ids": self.ids})
            self.assertEqual(response.status_code, 202, response.text)
            self.assertEqual(response.json()["state"], "pending")
            self.assertEqual(client.get(base).json()[0]["job_id"], self.job)
            self.assertEqual(client.get(other).json(), [])


    def test_sqlite_backup_is_consistent_and_does_not_overwrite(self):
        import sqlite3
        from app.maintenance import backup_database
        self.approve()
        self.enqueue()
        destination = core.DB.parent / "backup.sqlite"
        backup_database(core.DB, destination)
        with sqlite3.connect(destination) as db:
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(db.execute("SELECT state FROM render_tasks").fetchone()[0], "pending")
        with self.assertRaises(FileExistsError):
            backup_database(core.DB, destination)


    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg unavailable")
    def test_real_worker_renders_and_validates_actual_video(self):
        source = editor.RAW / "synthetic.mp4"
        subprocess.run(["ffmpeg", "-nostdin", "-y", "-hide_banner", "-loglevel", "error",
                        "-f", "lavfi", "-i", "color=c=blue:s=160x90:r=15:d=3",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", str(source)],
                       check=True, timeout=30)
        asset = media.import_media(self.w, self.c, source.name)
        media.scan_media(self.w, self.c, asset["id"], clip_seconds=2, max_scan_seconds=3)
        ids = [row["id"] for row in media.candidates(self.w, self.c, asset["id"])]
        self.approve()
        queue.enqueue(self.w, self.c, self.job, ids, caption_mode="soft", caption_lines=["Test caption"])
        result = queue.run_once()
        self.assertEqual(result["state"], "ready", result)
        output = assembly.export_file(self.w, self.c, self.job)
        self.assertTrue(output.is_file())
        assembly.validate_output(output, "short", "fast", "soft", 2)

    def test_recovery_marks_already_committed_export_ready(self):
        self.approve()
        self.enqueue()
        with core.connect() as db:
            db.execute("UPDATE render_tasks SET state='running' WHERE job_id=?", (self.job,))
        with patch.object(assembly, "render_assembled_video", side_effect=self.fake_render), \
             patch.object(assembly, "validate_output"):
            assembly.export_job(self.w, self.c, self.job, self.ids, _queue_worker=True)
        queue.recover()
        self.assertEqual(queue.list_tasks(self.w, self.c)[0]["state"], "ready")
