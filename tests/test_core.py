import unittest
from app import strategy
from app.editor import source

class CoreTests(unittest.TestCase):
    def test_four_proposals(self):
        self.assertEqual(len(strategy.proposals()),4)
    def test_brief_hinglish(self):
        self.assertIn('Hinglish',strategy.script_brief({'game':'BGMI','format':'short','title':'Tip'}))
    def test_path_guard(self):
        with self.assertRaises(ValueError): source('../secrets.mp4')

if __name__=='__main__': unittest.main()
