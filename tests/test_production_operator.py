"""Operator scheduling, atomic reviewed drafts and explicit render approval."""
from datetime import datetime, timedelta, timezone
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import editor, platform_core as core, ai_director as ai, media_intelligence as media
from app import render_queue, production_operator as op


class OperatorTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root=Path(tmp.name)
        raw=root/"raw";raw.mkdir()
        (raw/"game.mp4").write_bytes(b"source")
        for p in (patch.object(core,"DB",root/"db.sqlite"),patch.object(editor,"RAW",raw)):
            p.start();self.addCleanup(p.stop)
        core.initialize();op.initialize()
        self.w=core.new_workspace("Local")
        self.c=core.new_channel(self.w,"Gaming","gaming")
        self.other=core.new_workspace("Other")
        self.other_c=core.new_channel(self.other,"Other","gaming")
        with patch.object(media,"probe_metadata",return_value={
            "duration_seconds":40.,"width":640,"height":360,"fps":30.,
            "video_codec":"h264","audio_codec":None}):
            asset=media.import_media(self.w,self.c,"game.mp4")
        self.asset=asset["id"]

    def schedule(self,asset=None,due=None):
        return op.schedule(self.w,self.c,"Three practical gaming tips","short",due,asset,8,120,"balanced")

    def test_future_task_persists_until_due_and_cancel_is_scoped(self):
        task=self.schedule(due=(datetime.now(timezone.utc)+timedelta(hours=2)).isoformat())
        self.assertIsNone(op.run_once())
        self.assertEqual(op.tasks(self.w,self.c)[0]["state"],"pending")
        self.assertEqual(op.tasks(self.other,self.other_c),[])
        with self.assertRaises(ValueError):
            op.cancel(self.other,self.other_c,task["id"])
        self.assertEqual(op.cancel(self.w,self.c,task["id"])["state"],"cancelled")

    def test_operator_creates_one_review_job_without_cloud_or_render(self):
        task=self.schedule()
        with patch.object(ai,"cloud") as cloud,patch.object(render_queue,"enqueue") as enqueue:
            result=op.run_once()
        cloud.assert_not_called();enqueue.assert_not_called()
        self.assertEqual(result["state"],"review")
        self.assertEqual(core.jobs(self.w)[0]["state"],"ready_for_review")
        self.assertEqual(len(core.jobs(self.w)),1)
        self.assertIsNone(op.run_once())
        with self.assertRaises(ValueError):
            op.queue_recommended(self.w,self.c,task["id"])
        with core.connect() as db:
            self.assertEqual(db.execute("SELECT job_id FROM ai_drafts").fetchone()[0],result["job_id"])

    def test_existing_candidates_not_invalidated_and_render_requires_approval(self):
        with patch.object(media,"detect_changes",return_value=[12,25]):
            media.scan_media(self.w,self.c,self.asset,8,.35,120)
        original=media.candidates(self.w,self.c,self.asset)
        task=self.schedule(self.asset)
        with patch.object(media,"scan_media") as scan:
            result=op.run_once()
        scan.assert_not_called()
        self.assertEqual(result["state"],"review")
        self.assertTrue(result["candidate_ids"])
        self.assertEqual(media.candidates(self.w,self.c,self.asset),original)
        with self.assertRaises(ValueError):
            op.queue_recommended(self.w,self.c,task["id"])
        core.transition(self.w,result["job_id"],"approved")
        self.assertEqual(op.queue_recommended(self.w,self.c,task["id"])["state"],"pending")

    def test_failure_has_no_duplicate_job_and_retry_works(self):
        task=self.schedule()
        with patch.object(ai,"offline",side_effect=RuntimeError("generation failure")):
            self.assertEqual(op.run_once()["state"],"failed")
        self.assertEqual(core.jobs(self.w),[])
        op.retry(self.w,self.c,task["id"])
        self.assertEqual(op.run_once()["state"],"review")
        self.assertEqual(len(core.jobs(self.w)),1)

    def test_interrupted_task_recovers_explicitly(self):
        task=self.schedule()
        with core.connect() as db:
            db.execute("UPDATE operator_tasks SET state='running' WHERE id=?",(task["id"],))
        self.assertIsNone(op.run_once())
        self.assertEqual(op.tasks(self.w,self.c)[0]["state"],"interrupted")
        self.assertEqual(op.retry(self.w,self.c,task["id"])["state"],"pending")

    def test_cross_channel_asset_and_naive_due_time_rejected(self):
        with self.assertRaises(ValueError):
            op.schedule(self.other,self.other_c,"Other topic","short",None,self.asset,8,120,"balanced")
        with self.assertRaises(ValueError):
            self.schedule(due="2026-12-01T12:00:00")
