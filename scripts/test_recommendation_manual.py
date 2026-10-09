import unittest
from unittest.mock import patch
from test_recommendation_pipeline import FakeBackend, NOW, movie
from recommend import load_config, recommend_user, run

OWNER='00000000-0000-4000-8000-000000000001'
REQUEST='00000000-0000-4000-8000-000000000002'

class ManualTests(unittest.TestCase):
 def test_manual_bypasses_completed_slot_and_rolling_cap_without_duplicates(self):
  backend=FakeBackend();config=load_config()
  backend.collection=[{'tmdb_id':2000+i,'reason':'earlier','created_at':NOW.isoformat()} for i in range(config['maximum_per_hour'])]
  user={'user_id':OWNER,'last_recommendation_at':NOW.isoformat()}
  with patch.dict('os.environ',{},clear=True):
   self.assertEqual(recommend_user(backend,user,NOW,config,manual=True),30)
   self.assertEqual(recommend_user(backend,user,NOW,config,manual=True),0)
  self.assertEqual(len({r['tmdb_id'] for r in backend.collection}),130)
  self.assertEqual(backend.patched,[])
  self.assertTrue(all(r['metadata']['recommendationMode']=='manual' for r in backend.collection[100:]))

 def test_manual_saves_fewer_than_base_and_does_not_consume_scheduled_budget(self):
  backend=FakeBackend();config=load_config();user={'user_id':OWNER}
  candidates=[dict(movie(901),discovery_sources=['tmdb'])]
  with patch('recommend.discover',return_value=(candidates,[])):
   self.assertEqual(recommend_user(backend,user,NOW,config,manual=True,request_id=REQUEST),1)
  self.assertEqual(backend.collection[0]['metadata']['recommendationRequestId'],REQUEST)
  with patch.dict('os.environ',{},clear=True):
   self.assertEqual(recommend_user(backend,user,NOW,config),15)

 def test_website_request_resolves_owner_and_claims_once(self):
  class Jobs:
   def __init__(self):self.calls=[];self.status='queued'
   def db(self,path,method='GET',body=None,prefer=None):
    self.calls.append((path,method,body))
    if path.startswith('recommendation_jobs'):
     if method=='GET':return [{'id':REQUEST,'user_id':OWNER,'status':self.status}]
     self.status=body['status'];return [{'id':REQUEST}]
    return [{'user_id':OWNER}]
  backend=Jobs()
  with patch.dict('os.environ',{'SUPABASE_URL':'test','SUPABASE_SERVICE_ROLE_KEY':'test','TMDB_ACCESS_TOKEN':'test','MANUAL_RECOMMENDATIONS':'true','RECOMMENDATION_REQUEST_ID':REQUEST},clear=True),patch('recommend.Backend',return_value=backend),patch('recommend.recommend_user',return_value=7) as recommend:
   run();run()
  self.assertEqual(recommend.call_count,1)
  self.assertEqual(recommend.call_args.args[1]['user_id'],OWNER)
  self.assertTrue(recommend.call_args.kwargs['manual'])
  self.assertEqual(backend.status,'completed')
  self.assertTrue(any('user_id=eq.'+OWNER in path for path,_,_ in backend.calls if path.startswith('profiles')))
  self.assertEqual(next(body['added_count'] for _,_,body in backend.calls if body and body.get('status')=='completed'),7)
