"""FastAPI integration tests. Run after pip installing apps/api/requirements.txt."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from fastapi.testclient import TestClient
    from apps.api.main import app
    from app import platform_core as core
except ImportError:
    TestClient = None


@unittest.skipUnless(TestClient is not None, "Install apps/api/requirements.txt for API tests")
class APITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patch_db = patch.object(core, "DB", Path(self.tmp.name) / "test.sqlite3")
        self.patch_db.start()
        core.initialize()
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.patch_db.stop()
        self.tmp.cleanup()

    def test_crud_overview_and_approval_flow(self):
        api = self.client
        w = api.post('/api/v1/workspaces', json={'name': 'Studio'})
        self.assertEqual(w.status_code, 201)
        wid = w.json()['id']
        c = api.post(f'/api/v1/workspaces/{wid}/channels', json={'name': 'Gaming', 'niche': 'gaming'})
        self.assertEqual(c.status_code, 201)
        cid = c.json()['id']
        job = api.post(f'/api/v1/workspaces/{wid}/jobs', json={'channel_id':cid,'title':'Valorant tips','format':'short'})
        self.assertEqual(job.status_code, 201)
        jid = job.json()['id']
        self.assertEqual(api.post(f'/api/v1/workspaces/{wid}/jobs/{jid}/transition', json={'to':'queued'}).status_code, 409)
        for state in ('ready_for_review','approved','queued'):
            result=api.post(f'/api/v1/workspaces/{wid}/jobs/{jid}/transition', json={'to':state})
            self.assertEqual(result.status_code,200)
        self.assertEqual(api.get(f'/api/v1/workspaces/{wid}/overview').json()['queue'],1)
        self.assertEqual(api.get('/api/v1/health').json()['publishing'],False)
        self.assertGreaterEqual(len(api.get(f'/api/v1/workspaces/{wid}/audit').json()),4)

    def test_workspace_isolation_and_validation(self):
        api=self.client
        wa=api.post('/api/v1/workspaces',json={'name':'A'}).json()['id']
        wb=api.post('/api/v1/workspaces',json={'name':'B'}).json()['id']
        ch=api.post(f'/api/v1/workspaces/{wa}/channels',json={'name':'Gaming','niche':'gaming'}).json()
        cid=ch['id']
        self.assertEqual(api.get(f'/api/v1/workspaces/{wb}/channels').json(),[])
        self.assertEqual(api.post(f'/api/v1/workspaces/{wb}/jobs',json={'channel_id':cid,'title':'oops','format':'short'}).status_code,404)
        self.assertEqual(api.patch(f'/api/v1/workspaces/{wb}/channels/{cid}',json={'name':'Stolen'}).status_code,404)
        self.assertEqual(api.post(f'/api/v1/workspaces/{wa}/jobs',json={'channel_id':cid,'title':'x','format':'invalid'}).status_code,422)
        changed=api.patch(f'/api/v1/workspaces/{wa}/channels/{cid}',json={'language':'English'})
        self.assertEqual(changed.json()['language'],'English')
        self.assertEqual(api.post(f'/api/v1/workspaces/{wa}/channels',json={'name':'Gaming','niche':'other'}).status_code,409)

if __name__ == '__main__': unittest.main()
