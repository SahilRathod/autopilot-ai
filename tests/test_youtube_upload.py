"""Private upload contract: no real Google credentials or network calls."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
import httpx
from app import editor, platform_core as core, video_assembly as assembly
from app import youtube_connection as yt, youtube_upload as upload


class YouTubeUploadTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        out = root / "output"
        out.mkdir()
        for p in (patch.object(core, "DB", root / "db.sqlite"),
                  patch.object(editor, "OUT", out),
                  patch.object(yt, "protect", side_effect=lambda s: b"encrypted:" + s.encode()),
                  patch.object(yt, "unprotect", side_effect=lambda b: b.decode().removeprefix("encrypted:"))):
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(yt.clear_pending)
        core.initialize()
        upload.initialize()
        self.w = core.new_workspace("Local")
        self.c = core.new_channel(self.w, "Gaming", "gaming")
        self.other = core.new_workspace("Other")
        self.other_c = core.new_channel(self.other, "Other", "gaming")
        self.job = core.add_job(self.w, self.c, "Test upload", "short")
        core.transition(self.w, self.job, "ready_for_review")
        core.transition(self.w, self.job, "approved")
        self.file = out / "export.mp4"
        self.file.write_bytes(b"local synthetic output")
        with core.connect() as db:
            db.execute("""INSERT INTO assembly_exports(job_id,workspace_id,channel_id,state,
                      candidate_ids_json,caption_lines_json,caption_mode,audio_mode,quality,
                      total_seconds,output_path) VALUES(?,?,?,'ready','[]','[]','none','preserve','fast',3,?)""",
                       (self.job,self.w,self.c,str(self.file)))
        (root / "youtube-client.json").write_text(json.dumps({"installed": {
            "client_id":"test.apps.googleusercontent.com","client_secret":"secret"}}))
        self.profile = {"id":"UC-test","title":"Gaming channel","subscriber_count":"100"}
        self.session = "https://www.googleapis.com/upload/youtube/v3/videos?upload_id=secret-session"
        self.result = {"id":"abc123","snippet":{"channelId":"UC-test"},"status":{"privacyStatus":"private"}}

    def authorize(self, upload_scope=False, profile=None):
        q = parse_qs(urlsplit(yt.begin(self.w,self.c,upload_scope)["authorization_url"]).query)
        scope = yt.READ_SCOPE + (" " + yt.UPLOAD_SCOPE if upload_scope else "")
        with patch.object(yt,"exchange_code",return_value={"access_token":"access","refresh_token":"refresh","scope":scope}), \
             patch.object(yt,"read_channel",return_value=profile or self.profile):
            return yt.finish(q["state"][0],"code")

    def enqueue(self, consent=True):
        with patch.object(assembly,"validate_output"):
            return upload.enqueue(self.w,self.c,self.job,"Private draft","Description","20",False,consent)

    def test_upgrade_checks_identity_and_preserves_read_grant_on_failure(self):
        self.authorize()
        self.assertFalse(yt.status(self.w,self.c)["upload_authorized"])
        with self.assertRaises(ValueError):
            self.authorize(True, self.profile | {"id":"wrong"})
        self.assertFalse(yt.status(self.w,self.c)["upload_authorized"])
        self.assertTrue(self.authorize(True)["upload_authorized"])

    def test_requires_scope_explicit_consent_and_scoped_approved_export(self):
        self.authorize()
        with self.assertRaises(ValueError):
            self.enqueue()
        self.authorize(True)
        with self.assertRaises(ValueError):
            self.enqueue(False)
        with self.assertRaises(ValueError):
            upload.enqueue(self.other,self.other_c,self.job,"Test","", "20",False,True)
        self.assertEqual(self.enqueue()["state"],"pending")
        with self.assertRaises(ValueError):
            self.enqueue()

    def test_worker_records_real_provider_id_and_never_leaks_session(self):
        self.authorize(True)
        self.enqueue()
        response=httpx.Response(200,json=self.result)
        with patch.object(yt,"refresh_access",return_value="access"), \
             patch.object(yt,"read_channel",return_value=self.profile), \
             patch.object(upload,"initiate",return_value=self.session), \
             patch.object(upload,"send_chunk",return_value=response):
            task=upload.run_once()
        self.assertEqual(task["state"],"uploaded",task)
        self.assertEqual(task["video_id"],"abc123")
        self.assertNotIn("secret-session",json.dumps(upload.tasks(self.w,self.c)))
        self.assertEqual(upload.tasks(self.other,self.other_c),[])

    def test_source_change_prevents_network_transfer(self):
        self.authorize(True)
        self.enqueue()
        self.file.write_bytes(b"changed after approval")
        with patch.object(upload,"initiate") as initiate:
            self.assertEqual(upload.run_once()["state"],"failed")
            initiate.assert_not_called()

    def test_ambiguous_final_response_never_starts_second_session(self):
        self.authorize(True)
        self.enqueue()
        with patch.object(yt,"refresh_access",return_value="access"), \
             patch.object(yt,"read_channel",return_value=self.profile), \
             patch.object(upload,"initiate",return_value=self.session), \
             patch.object(upload,"send_chunk",side_effect=RuntimeError("connection lost")):
            self.assertEqual(upload.run_once()["state"],"interrupted")
        with patch.object(yt,"refresh_access",return_value="access"), \
             patch.object(yt,"read_channel",return_value=self.profile), \
             patch.object(upload,"initiate") as initiate, \
             patch.object(upload,"query_session",return_value=httpx.Response(404)):
            upload.retry(self.w,self.c,self.job)
            self.assertEqual(upload.run_once()["state"],"review_required")
            initiate.assert_not_called()

    def test_reject_untrusted_session_and_non_private_response(self):
        for url in ("http://www.googleapis.com/upload/youtube/v3/videos",
                    "https://www.googleapis.com.evil.test/upload/youtube/v3/videos",
                    "https://www.googleapis.com@evil.test/upload/youtube/v3/videos"):
            with self.assertRaises(ValueError):
                upload.validate_session(url)
        with self.assertRaises(ValueError):
            upload.verify_result(self.result | {"status":{"privacyStatus":"public"}},"UC-test")

    def test_range_parsing(self):
        self.assertEqual(upload.next_offset(httpx.Response(308),100),0)
        self.assertEqual(upload.next_offset(httpx.Response(308,headers={"Range":"bytes=0-49"}),100),50)
        with self.assertRaises(ValueError):
            upload.next_offset(httpx.Response(308,headers={"Range":"bytes=0-999"}),100)


    def test_http_private_upload_requires_consent_and_reports_scope(self):
        from fastapi.testclient import TestClient
        from apps.api.main import app
        self.authorize(True)
        with TestClient(app,base_url="http://127.0.0.1:8000") as client, \
             patch.object(assembly,"validate_output"):
            path=f"/api/v1/workspaces/{self.w}/channels/{self.c}/youtube/uploads"
            data={"job_id":self.job,"title":"Private test","category_id":"20",
                  "made_for_kids":False,"private_upload_approved":False,"expected_output":str(self.file)}
            self.assertEqual(client.post(path,json=data).status_code,409)
            data["private_upload_approved"]=True
            self.assertEqual(client.post(path,json=data,headers={"Origin":"https://example.com"}).status_code,403)
            response=client.post(path,json=data)
            self.assertEqual(response.status_code,202,response.text)
            self.assertEqual(client.get(path).json()[0]["state"],"pending")
            other=f"/api/v1/workspaces/{self.other}/channels/{self.other_c}/youtube/uploads"
            self.assertEqual(client.get(other).json(),[])


    def test_pending_upload_can_be_cancelled_before_network(self):
        self.authorize(True)
        self.enqueue()
        self.assertEqual(upload.cancel(self.w,self.c,self.job)["state"],"cancelled")
        with patch.object(upload,"initiate") as initiate:
            self.assertIsNone(upload.run_once())
            initiate.assert_not_called()

    def test_google_protocol_uses_private_metadata_and_exact_content_range(self):
        self.authorize(True)
        self.enqueue()
        with core.connect() as db:
            row=db.execute("SELECT * FROM youtube_uploads WHERE job_id=?",(self.job,)).fetchone()
        with patch.object(upload,"_http",return_value=httpx.Response(200,headers={"Location":self.session})) as send:
            self.assertEqual(upload.initiate(row,"token"),self.session)
        request=send.call_args.kwargs
        self.assertEqual(request["json"]["status"]["privacyStatus"],"private")
        self.assertFalse(request["json"]["status"]["selfDeclaredMadeForKids"])
        self.assertEqual(request["params"]["notifySubscribers"],"false")
        with patch.object(upload,"_http",return_value=httpx.Response(308)) as send:
            upload.send_chunk(self.session,"token",b"abcd",4,10)
            self.assertEqual(send.call_args.kwargs["headers"]["Content-Range"],"bytes 4-7/10")
            upload.query_session(self.session,"token",10)
            self.assertEqual(send.call_args.kwargs["headers"]["Content-Range"],"bytes */10")


    def test_reviewed_export_version_must_match_current_output(self):
        self.authorize(True)
        with patch.object(assembly,"validate_output") as validate:
            with self.assertRaises(ValueError):
                upload.enqueue(self.w,self.c,self.job,"Test","","20",False,True,"stale.mp4")
            validate.assert_not_called()
