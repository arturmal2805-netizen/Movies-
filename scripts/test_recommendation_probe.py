import unittest
from unittest.mock import patch
from test_recommendation_pipeline import FakeBackend,movie,NOW
from recommend import recommend_user,load_config

class ProbeCommandTests(unittest.TestCase):
 def test_published_probe_command_selects_manual_read_only_mode(self):
  import runpy
  from pathlib import Path
  b=FakeBackend();b.search_report={'accepted':30}
  with patch('builtins.print'),patch.dict('os.environ',{},clear=True),patch('recommend.Backend',return_value=b),patch('recommend.read_rows',return_value=[{'user_id':'test'}]),patch('recommend.recommend_user',return_value=30)as run:
   runpy.run_path(str(Path(__file__).with_name('probe_recommendations.py')),run_name='__main__')
  self.assertTrue(run.call_args.kwargs['manual']);self.assertTrue(run.call_args.kwargs['dry_run'])
  self.assertEqual(b.collection,[]);self.assertEqual(b.patched,[])

class ReadOnlySearchTests(unittest.TestCase):
 def test_no_profiles_cannot_be_reported_as_successful_real_validation(self):
  import runpy
  from pathlib import Path
  with patch('builtins.print'),patch.dict('os.environ',{},clear=True),patch('recommend.Backend',return_value=FakeBackend()),patch('recommend.read_rows',return_value=[]):
   with self.assertRaisesRegex(RuntimeError,'No private profile'):runpy.run_path(str(Path(__file__).with_name('probe_recommendations.py')),run_name='__main__')
 def test_real_pipeline_dry_run_selects_thirty_without_writing_or_budget_fetches(self):
  b=FakeBackend();candidates=[dict(movie(5000000+i),budget=None)for i in range(30)]
  b.movie=lambda path:candidates[int(path.split('/')[1].split('?')[0])-5000000]
  with patch('recommend.discover',return_value=(candidates,[])):
   self.assertEqual(recommend_user(b,{'user_id':'test'},NOW,load_config(),manual=True,dry_run=True),30)
  self.assertEqual(b.collection,[]);self.assertEqual(b.patched,[])
  self.assertEqual(b.search_report['wouldAdd'],30);self.assertNotIn('added',b.search_report)
 def test_probe_does_not_claim_validated_quantity_below_minimum(self):
  import runpy
  from pathlib import Path
  with patch('builtins.print'),patch.dict('os.environ',{},clear=True),patch('recommend.Backend',return_value=FakeBackend()),patch('recommend.read_rows',return_value=[{'user_id':'test'}]),patch('recommend.recommend_user',return_value=3):
   with self.assertRaisesRegex(RuntimeError,'fewer than 15'):runpy.run_path(str(Path(__file__).with_name('probe_recommendations.py')),run_name='__main__')
