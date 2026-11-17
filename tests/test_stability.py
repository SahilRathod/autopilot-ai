"""V0.4.1 regression tests: costs, personalization, review and browser API."""
import asyncio
import json
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from app import ai_director as ai, platform_core as core
from apps.api.main import app
from fastapi.testclient import TestClient


class SlowGemini:
    def __init__(self):
        self.calls = 0

    async def post(self, url, headers, json):
        self.calls += 1
        await asyncio.sleep(.03)
        class Response:
            status_code = 200
            def json(self):
                return {"candidates": [{"content": {"parts": [{"text": __import__("json").dumps({
                    "title": "Reviewed tip", "hook": "Try this", "script": "Original draft",
                    "description": "A video", "outline": ["Hook", "Proof"],
                    "keywords": ["tips"], "shorts": ["One tip"],
                    "research_needed": ["Verify the footage"],
                })}]}}]}
        return Response()


class StabilityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_override = patch.object(core, "DB", Path(self.temp.name) / "test.sqlite")
        self.db_override.start()
        core.initialize()
        ai.initialize()
        self.w = core.new_workspace("Studio")
        self.c = core.new_channel(self.w, "Gaming", "gaming", "Hinglish")
        self.other = core.new_workspace("Another")
        self.other_c = core.new_channel(self.other, "School", "education", "English")

    async def asyncTearDown(self):
        self.db_override.stop()
        self.temp.cleanup()

    async def test_zero_cloud_cap_means_zero_calls(self):
        client = SlowGemini()
        with patch.dict(os.environ, {"GEMINI_API_KEY": "fake",
                                     "AUTOPILOT_CLOUD_MODE": "free_only",
                                     "GEMINI_FREE_TIER_CONFIRMED": "1",
                                     "AUTOPILOT_DAILY_REQUEST_CAP": "0"}):
            with self.assertRaises(ai.AIError):
                await ai.generate(self.w, self.c, "Valorant crosshair", provider="gemini", client=client)
        self.assertEqual(client.calls, 0)

    async def test_malformed_cap_fails_closed(self):
        with patch.dict(os.environ, {"AUTOPILOT_DAILY_REQUEST_CAP": "nope"}):
            with self.assertRaises(ai.AIError):
                ai.reserve(self.w, self.c)

    async def test_short_and_long_are_different(self):
        s = await ai.generate(self.w, self.c, "Minecraft survival", fmt="short")
        l = await ai.generate(self.w, self.c, "Minecraft survival", fmt="long")
        self.assertNotEqual(s["result"]["script"], l["result"]["script"])
        self.assertNotEqual(s["result"]["outline"], l["result"]["outline"])

    async def test_channel_memory_changes_content(self):
        a = await ai.generate(self.w, self.c, "Valorant aim tips")
        ai.remember(self.w, self.c, "tone", "Calm and professional")
        b = await ai.generate(self.w, self.c, "Valorant aim tips")
        self.assertNotEqual(a["result"]["script"], b["result"]["script"])
        self.assertIn("Calm and professional", b["result"]["script"])
        self.assertNotIn("Calm and professional", (await ai.generate(
            self.other, self.other_c, "Valorant aim tips"))["result"]["script"])
        self.assertIn("\n", b["result"]["script"])

    async def test_concurrent_duplicate_cloud_requests_share_one_result(self):
        client = SlowGemini()
        with patch.dict(os.environ, {"GEMINI_API_KEY": "fake",
                                     "AUTOPILOT_CLOUD_MODE": "free_only",
                                     "GEMINI_FREE_TIER_CONFIRMED": "1",
                                     "AUTOPILOT_DAILY_REQUEST_CAP": "1"}):
            results = await asyncio.gather(*(ai.generate(
                self.w, self.c, "Single flight topic", provider="gemini", client=client)
                for _ in range(12)))
        self.assertEqual(client.calls, 1)
        self.assertEqual(len({r["id"] for r in results}), 1)

    async def test_reservation_under_parallel_threads(self):
        with patch.dict(os.environ, {"AUTOPILOT_DAILY_REQUEST_CAP": "1"}):
            def claim():
                try:
                    ai.reserve(self.w, self.c)
                    return True
                except ai.AIError:
                    return False
            with ThreadPoolExecutor(max_workers=12) as executor:
                results = list(executor.map(lambda _: claim(), range(20)))
            self.assertEqual(sum(results), 1)


class BrowserIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.override = patch.object(core, "DB", Path(self.tmp.name) / "api.sqlite")
        self.override.start()
        core.initialize()
        ai.initialize()
        self.client = TestClient(app)
        self.client.__enter__()
        self.w = core.new_workspace("Website")
        self.c = core.new_channel(self.w, "Gaming", "gaming")

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.override.stop()
        self.tmp.cleanup()

    def test_memory_browser_preflight_put(self):
        p = f"/api/v1/workspaces/{self.w}/channels/{self.c}/ai/memory/tone"
        r = self.client.options(p, headers={
            "Origin": "http://127.0.0.1:3000",
            "Access-Control-Request-Method": "PUT",
            "Access-Control-Request-Headers": "content-type",
        })
        self.assertEqual(r.status_code, 200)
        self.assertIn("PUT", r.headers["access-control-allow-methods"])

    def test_job_content_is_readable_and_scoped(self):
        base = f"/api/v1/workspaces/{self.w}/channels/{self.c}/ai"
        generated = self.client.post(base + "/generate", json={"topic": "Valorant tips"})
        self.assertEqual(generated.status_code, 201)
        draft = generated.json()
        submitted = self.client.post(base + f"/drafts/{draft['id']}/submit")
        self.assertEqual(submitted.status_code, 200)
        job_id = submitted.json()["job_id"]
        detail = self.client.get(f"/api/v1/workspaces/{self.w}/jobs/{job_id}/content")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["draft_id"], draft["id"])
        self.assertIn("script", detail.json()["result"])
        other = core.new_workspace("Not owner")
        forbidden = self.client.get(f"/api/v1/workspaces/{other}/jobs/{job_id}/content")
        self.assertEqual(forbidden.status_code, 404)

if __name__ == "__main__":
    unittest.main()
