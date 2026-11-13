"""AI Director tests — all offline or mocked; never call Google."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from app import platform_core as core, ai_director as ai

class Reply:
    status_code=200
    def json(self):
        return {"candidates":[{"content":{"parts":[{"text":json.dumps({
            "title":"Draft", "hook":"Real hook", "script":"Needs footage",
            "description":"Demo", "outline":["Hook","Example"],
            "keywords":["gaming"],"shorts":["Tip"],"research_needed":["Verify clips"]
        })}]}}]}

class FakeClient:
    def __init__(self): self.calls=0
    async def post(self,url,headers,json):
        self.calls+=1
        assert "gemini-2.5-flash-lite:generateContent" in url
        assert headers.get("x-goog-api-key") == "fake"
        return Reply()

class DirectorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.patch=patch.object(core,"DB",Path(self.tmp.name)/"test.sqlite")
        self.patch.start()
        core.initialize()
        ai.initialize()
        self.a=core.new_workspace("A");self.b=core.new_workspace("B")
        self.ca=core.new_channel(self.a,"Gaming","gaming")
        self.cb=core.new_channel(self.b,"Education","education")

    async def asyncTearDown(self):
        self.patch.stop();self.tmp.cleanup()

    async def test_offline_cache_workspace_and_approval(self):
        ai.remember(self.a,self.ca,"tone","Friendly Hinglish")
        first=await ai.generate(self.a,self.ca,"Valorant beginner mistakes")
        repeat=await ai.generate(self.a,self.ca,"Valorant beginner mistakes")
        self.assertEqual(first["id"],repeat["id"])
        self.assertTrue(repeat["cached"])
        self.assertIn("DRAFT TEMPLATE",first["result"]["script"])
        self.assertEqual(ai.drafts(self.b,self.cb),[])
        with self.assertRaises(ValueError): ai.remember(self.b,self.ca,"tone","Wrong tenant")
        job=ai.submit(self.a,self.ca,first["id"])
        self.assertEqual(job,ai.submit(self.a,self.ca,first["id"]))
        self.assertEqual(core.jobs(self.a,self.ca)[0]["state"],"draft")
        with self.assertRaises(ValueError): ai.submit(self.b,self.cb,first["id"])
        ai.remember(self.a,self.ca,"tone","New tone")
        changed=await ai.generate(self.a,self.ca,"Valorant beginner mistakes")
        self.assertNotEqual(changed["id"],first["id"])

    async def test_cloud_requires_opt_in(self):
        with patch.dict(os.environ,{"GEMINI_API_KEY":"fake","AUTOPILOT_CLOUD_MODE":"disabled"},clear=False):
            with self.assertRaises(ai.AIError):
                await ai.generate(self.a,self.ca,"Minecraft survival",provider="gemini",client=FakeClient())

    async def test_one_mocked_gemini_request_cache_and_cap(self):
        client=FakeClient()
        with patch.dict(os.environ,{"GEMINI_API_KEY":"fake","AUTOPILOT_CLOUD_MODE":"free_only",
                                    "GEMINI_FREE_TIER_CONFIRMED":"1","AUTOPILOT_DAILY_REQUEST_CAP":"1"},clear=False):
            a=await ai.generate(self.a,self.ca,"Minecraft survival",provider="gemini",client=client)
            b=await ai.generate(self.a,self.ca,"Minecraft survival",provider="gemini",client=client)
            self.assertEqual(client.calls,1)
            self.assertTrue(b["cached"])
            self.assertEqual(a["result"]["title"],"Draft")
            with self.assertRaises(ai.AIError):
                await ai.generate(self.a,self.ca,"Another topic",provider="gemini",client=client)

if __name__=="__main__": unittest.main()
