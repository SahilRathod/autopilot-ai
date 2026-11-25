import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, Mock

from app import platform_core as core, youtube_connection as yt
from app import youtube_upload as upload, youtube_actions as actions


class YouTubeActionsTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        p=patch.object(core,"DB",Path(temp.name)/"db.sqlite")
        p.start()
        self.addCleanup(p.stop)
        core.initialize()
        upload.initialize()
        actions.initialize()
        self.w=core.new_workspace("Local")
        self.c=core.new_channel(self.w,"Gaming","gaming")
        self.job=core.add_job(self.w,self.c,"Reviewed","short")
        with core.connect() as db:
            db.execute("""INSERT INTO youtube_links(local_channel_id,workspace_id,remote_channel_id,profile_json,
                encrypted_refresh,client_id,upload_authorized,manage_authorized) VALUES(?,?,?,?,?,?,1,1)""",
                (self.c,self.w,"UC-owner",'{"id":"UC-owner"}',b"fixture","client"))
            db.execute("""INSERT INTO youtube_uploads(job_id,workspace_id,channel_id,remote_channel_id,state,title,
                description,category_id,made_for_kids,file_sha256,file_bytes,video_id)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",(self.job,self.w,self.c,"UC-owner","uploaded","Reviewed","","20",0,"fixture",1,"video123"))
        p=patch.object(actions,"_access",return_value=("UC-owner","fixture"))
        p.start()
        self.addCleanup(p.stop)
        self.when=(datetime.now(timezone.utc)+timedelta(hours=3)).replace(microsecond=0).isoformat()
        self.video={"id":"video123","etag":"etag","snippet":{"channelId":"UC-owner","title":"Reviewed"},"status":{
            "privacyStatus":"private","uploadStatus":"processed","license":"youtube","embeddable":True,
            "publicStatsViewable":True,"selfDeclaredMadeForKids":False}}

    def test_no_mutation_without_explicit_consent_or_future_time(self):
        with patch.object(actions,"_mutate") as mutate:
            for when,approved in ((self.when,False),("2020-01-01T00:00:00Z",True),("2027-01-01T12:00:00",True)):
                with self.assertRaises(ValueError):
                    actions.schedule(self.w,self.c,self.job,when,approved)
            mutate.assert_not_called()

    def test_only_reviewed_private_owned_processed_upload_can_be_scheduled(self):
        for change in ({"privacyStatus":"public"},{"uploadStatus":"uploaded"},{"publishAt":self.when}):
            v=self.video | {"status":self.video["status"] | change}
            with patch.object(actions,"_video",return_value=v), patch.object(actions,"_mutate") as mutate:
                with self.assertRaises(ValueError):
                    actions.schedule(self.w,self.c,self.job,self.when,True)
                mutate.assert_not_called()

    def test_provider_confirmed_schedule_and_no_automatic_repeat(self):
        v=self.video | {"status":self.video["status"] | {"publishAt":self.when}}
        with patch.object(actions,"_video",return_value=self.video), patch.object(actions,"_mutate",return_value=v) as mutate:
            result=actions.schedule(self.w,self.c,self.job,self.when,True)
            self.assertEqual(result["state"],"confirmed")
            self.assertEqual(mutate.call_args.args[3]["status"]["privacyStatus"],"private")
            self.assertFalse(mutate.call_args.args[3]["status"]["selfDeclaredMadeForKids"])
            with self.assertRaises(ValueError):
                actions.schedule(self.w,self.c,self.job,self.when,True)
            self.assertEqual(mutate.call_count,1)

    def test_uncertain_schedule_is_never_retried(self):
        with patch.object(actions,"_video",return_value=self.video), patch.object(actions,"_mutate",side_effect=RuntimeError("network")) as mutate:
            with self.assertRaises(RuntimeError):
                actions.schedule(self.w,self.c,self.job,self.when,True)
            self.assertEqual(actions.history(self.w,self.c)[0]["state"],"review_required")
            with self.assertRaises(ValueError):
                actions.schedule(self.w,self.c,self.job,self.when,True)
            self.assertEqual(mutate.call_count,1)

    def test_reply_checks_owned_video_and_parent_comment(self):
        with patch.object(actions,"_video",return_value=self.video), patch.object(actions,"_get",return_value={"items":[{"id":"parent","snippet":{"videoId":"wrong"}}]}), patch.object(actions,"_mutate") as mutate:
            with self.assertRaises(ValueError):
                actions.reply(self.w,self.c,"video123","parent","Thank you",True)
            mutate.assert_not_called()

    def test_reply_is_single_explicit_action(self):
        with patch.object(actions,"_video",return_value=self.video), patch.object(actions,"_get",return_value={"items":[{"id":"parent","snippet":{"videoId":"video123"}}]}), patch.object(actions,"_mutate",return_value={"id":"reply1","snippet":{"parentId":"parent"}}) as mutate:
            result=actions.reply(self.w,self.c,"video123","parent","Thank you",True)
            self.assertEqual(result["state"],"confirmed")
            with self.assertRaises(ValueError):
                actions.reply(self.w,self.c,"video123","parent","Thank you",True)
            self.assertEqual(mutate.call_count,1)
