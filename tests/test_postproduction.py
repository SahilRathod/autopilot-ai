"""Timed caption, narration, thumbnail and export revision regressions."""
import hashlib
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import editor, platform_core as core, video_assembly as assembly
from app import youtube_upload as upload, postproduction as post


class PostProductionTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root=Path(temp.name)
        raw,out=root/"raw",root/"output"
        raw.mkdir();out.mkdir()
        for p in (patch.object(core,"DB",root/"db.sqlite"),patch.object(editor,"RAW",raw),patch.object(editor,"OUT",out)):
            p.start();self.addCleanup(p.stop)
        core.initialize();post.initialize()
        self.w=core.new_workspace("Local")
        self.c=core.new_channel(self.w,"Gaming","gaming")
        self.other=core.new_workspace("Other")
        self.other_c=core.new_channel(self.other,"Other","gaming")
        self.job=core.add_job(self.w,self.c,"Finished video","long")
        core.transition(self.w,self.job,"ready_for_review")
        core.transition(self.w,self.job,"approved")
        self.original=out/"original.mp4"
        self.original.write_bytes(b"original")
        with core.connect() as db:
            db.execute("""INSERT INTO assembly_exports(job_id,workspace_id,channel_id,state,
                candidate_ids_json,caption_lines_json,caption_mode,audio_mode,quality,total_seconds,output_path)
                VALUES(?,?,?,'ready','[]','[]','none','preserve','fast',3,?)""",
                (self.job,self.w,self.c,str(self.original)))
        self.srt="1\n00:00:00,100 --> 00:00:01,200\nHello gamers\n\n2\n00:00:01,300 --> 00:00:02,700\nWelcome back\n"

    def test_timestamp_validation(self):
        self.assertEqual(len(post.parse_srt(self.srt,3)),2)
        for bad in (self.srt.replace("00:00:02,700","00:00:09,700"),
                    self.srt.replace("00:00:01,300","00:00:00,300"),
                    self.srt.replace("Hello gamers","<b>unsafe</b>"),"1\nnot a timestamp\nText"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                post.parse_srt(bad,3)

    def test_failed_revision_never_changes_original(self):
        with patch.object(post,"mux_captions",side_effect=RuntimeError("failed")):
            with self.assertRaises(RuntimeError):
                post.attach_captions(self.w,self.c,self.job,self.srt)
        self.assertEqual(assembly.export_file(self.w,self.c,self.job),self.original)
        self.assertEqual(self.original.read_bytes(),b"original")

    def test_revision_preserves_previous_video_and_is_scoped(self):
        def fake(source,target,srt):
            target.write_bytes(b"new video")
        with patch.object(post,"mux_captions",side_effect=fake),patch.object(assembly,"validate_output"):
            result=post.attach_captions(self.w,self.c,self.job,self.srt)
        self.assertEqual(result["caption_mode"],"soft")
        self.assertEqual(self.original.read_bytes(),b"original")
        self.assertNotEqual(assembly.export_file(self.w,self.c,self.job),self.original)
        self.assertEqual(len(post.history(self.w,self.c,self.job)),2)
        with self.assertRaises(ValueError):
            post.history(self.other,self.other_c,self.job)

    def test_postproduction_rejects_job_with_upload_record(self):
        upload.initialize()
        with core.connect() as db:
            db.execute("""INSERT INTO youtube_uploads(job_id,workspace_id,channel_id,remote_channel_id,
                state,title,description,category_id,made_for_kids,file_sha256,file_bytes)
                VALUES(?,?,?,'remote','pending','test','','20',0,?,?)""",
                (self.job,self.w,self.c,hashlib.sha256(b"original").hexdigest(),8))
        with patch.object(post,"mux_captions") as mux:
            with self.assertRaises(ValueError):
                post.attach_captions(self.w,self.c,self.job,self.srt)
            mux.assert_not_called()

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),"FFmpeg unavailable")
    def test_real_caption_mux_narration_mix_and_thumbnail(self):
        subprocess.run(["ffmpeg","-nostdin","-y","-loglevel","error","-f","lavfi",
            "-i","color=c=blue:s=1280x720:r=30:d=3","-f","lavfi","-i","sine=frequency=440:duration=3",
            "-c:v","libx264","-preset","ultrafast","-pix_fmt","yuv420p","-c:a","aac","-shortest",str(self.original)],
            check=True,timeout=60)
        post.attach_captions(self.w,self.c,self.job,self.srt)
        captioned=assembly.export_file(self.w,self.c,self.job)
        assembly.validate_output(captioned,"long","fast","soft",3)
        voice=editor.RAW/"voice.wav"
        subprocess.run(["ffmpeg","-nostdin","-y","-loglevel","error","-f","lavfi",
            "-i","sine=frequency=880:duration=1.5",str(voice)],check=True,timeout=30)
        post.mix_voiceover(self.w,self.c,self.job,"voice.wav",0.2,1.0)
        result=assembly.export_file(self.w,self.c,self.job)
        assembly.validate_output(result,"long","fast","soft",3)
        post.create_thumbnail(self.w,self.c,self.job,1.0)
        image=post.thumbnail_file(self.w,self.c,self.job)
        self.assertTrue(image.read_bytes().startswith(b"\xff\xd8"))
        self.assertEqual(len(post.history(self.w,self.c,self.job)),3)
        self.assertTrue(self.original.exists() and captioned.exists())

    def test_optional_transcription_srt_uses_actual_segment_times(self):
        from types import SimpleNamespace
        with patch.object(post,"recognize",return_value=[SimpleNamespace(start=0.2,end=1.4,text="Hello")]):
            target=post.transcribe(self.w,self.c,self.job,"en")
        self.assertIn("00:00:00,200 --> 00:00:01,400",target.read_text(encoding="utf-8"))


    def test_http_caption_revision_and_thumbnail_scope(self):
        from fastapi.testclient import TestClient
        from apps.api.main import app
        def fake(source,target,srt):
            target.write_bytes(b"captioned")
        base=f"/api/v1/workspaces/{self.w}/channels/{self.c}/media/exports/{self.job}"
        other=f"/api/v1/workspaces/{self.other}/channels/{self.other_c}/media/exports/{self.job}"
        with TestClient(app) as client,patch.object(post,"mux_captions",side_effect=fake), \
             patch.object(assembly,"validate_output"):
            response=client.post(base+"/captions",json={"srt":self.srt})
            self.assertEqual(response.status_code,201,response.text)
            revisions=client.get(base+"/revisions").json()
            self.assertEqual(len(revisions),2)
            self.assertEqual(client.post(base+f"/revisions/{revisions[-1]['id']}/activate").status_code,200)
            self.assertEqual(assembly.export_file(self.w,self.c,self.job),self.original)
            self.assertEqual(client.get(other+"/revisions").status_code,404)
