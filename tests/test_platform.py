import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from app import platform_core as p

class MultiChannelTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.override=patch.object(p,'DB',Path(self.tmp.name)/'test.db')
        self.override.start()
        p.initialize()
    def tearDown(self):
        self.override.stop(); self.tmp.cleanup()
    def test_isolation_and_approval(self):
        a=p.new_workspace('Owner A'); b=p.new_workspace('Owner B')
        g=p.new_channel(a,'Game','gaming'); t=p.new_channel(a,'Tech','technology')
        other=p.new_channel(b,'Other','education')
        self.assertEqual(len(p.channels(a)),2)
        self.assertEqual(len(p.channels(b)),1)
        j=p.add_job(a,g,'Highlight','short')
        self.assertRaises(ValueError,p.add_job,a,other,'Wrong tenant','short')
        self.assertEqual(p.jobs(b),[])
        self.assertRaises(ValueError,p.transition,a,j,'queued')
        for state in ('ready_for_review','approved','queued'): p.transition(a,j,state)
        self.assertEqual(p.jobs(a,g)[0]['state'],'queued')
        self.assertEqual(p.jobs(a,t),[])
        self.assertRaises(ValueError,p.transition,b,j,'completed')
    def test_budget_and_publish_defaults(self):
        wid=p.new_workspace('Demo');cid=p.new_channel(wid,'Edu','education')
        channel=p.channels(wid)[0]
        self.assertEqual(channel['budget_inr'],0)
        self.assertEqual(channel['publishing_enabled'],0)

if __name__=='__main__':unittest.main()
