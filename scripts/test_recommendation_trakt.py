import os
import unittest
from unittest.mock import Mock, patch
from recommendation_sources import trakt_candidates, discover, hourly_limit

class TraktTests(unittest.TestCase):
 def backend(self):
  backend=Mock()
  backend.movie.side_effect=lambda path:{'id':int(path.split('/')[1].split('?')[0]),'genres':[{'id':878}], 'poster_path':'/poster.jpg'}
  return backend
 def test_lists_use_client_id_and_resolve_canonical_ids_once(self):
  backend=self.backend()
  backend.request.side_effect=[
   [{'movie':{'ids':{'tmdb':501,'trakt':900}}},{'movie':{'ids':{'tmdb':True}}},{'movie':{'ids':{'imdb':'tt999'}}},None],
   [{'ids':{'tmdb':501}},{'ids':{'tmdb':502}},{'ids':{'tmdb':-4}}]]
  with patch.dict(os.environ,{'TRAKT_CLIENT_ID':' fake-\nclient '}):
   movies=trakt_candidates(backend,[],{'candidate_limit':40})
  self.assertEqual([m['id'] for m in movies],[501,502])
  self.assertEqual(movies[0]['genre_ids'],[878])
  self.assertEqual(backend.movie.call_count,2)
  for call in backend.request.call_args_list:
   self.assertEqual(call.args[1]['trakt-api-key'],'fake-client')
   self.assertEqual(call.args[1]['trakt-api-version'],'2')
   self.assertNotIn('Authorization',call.args[1])
 def test_failed_list_and_one_bad_detail_keep_other_candidates(self):
  backend=self.backend();backend.request.side_effect=[RuntimeError(),[{'ids':{'tmdb':501}},{'ids':{'tmdb':502}}]]
  backend.movie.side_effect=lambda path:(_ for _ in ()).throw(RuntimeError()) if path.startswith('movie/501?') else {'id':502,'genres':[]}
  with patch.dict(os.environ,{'TRAKT_CLIENT_ID':'fake'}):movies=trakt_candidates(backend,[],{'candidate_limit':4})
  self.assertEqual([m['id'] for m in movies],[502])
 def test_missing_key_does_not_query_trakt(self):
  backend=self.backend()
  with patch.dict(os.environ,{},clear=True):
   with self.assertRaises(ValueError):trakt_candidates(backend,[],{})
  backend.request.assert_not_called()
 def test_failed_trakt_does_not_increase_budget_or_stop_tmdb(self):
  backend=self.backend();backend.movie.side_effect=None;backend.movie.return_value={'results':[{'id':501}]}
  config={'base_per_hour':5,'extra_per_source':2,'maximum_per_hour':20,'minimum_votes':100,
   'sources':[{'id':'tmdb','adapter':'tmdb_discover','enabled':True,'pages':1},{'id':'trakt','adapter':'trakt','enabled':True}]}
  with patch.dict(os.environ,{},clear=True):pool,status=discover(backend,[],config)
  self.assertEqual(status[-1]['status'],'failed')
  self.assertEqual(hourly_limit(config,[(0,pool[0],'')]),5)
 def test_candidate_lookup_is_bounded(self):
  backend=self.backend();backend.request.return_value=[{'ids':{'tmdb':i}} for i in range(1,100)]
  with patch.dict(os.environ,{'TRAKT_CLIENT_ID':'fake'}):movies=trakt_candidates(backend,[],{'candidate_limit':4})
  self.assertLessEqual(len(movies),4)

 def test_successful_trakt_contribution_grows_budget_and_merges_duplicates(self):
  backend=self.backend()
  backend.movie.side_effect=lambda path:{'results':[{'id':501}]} if path.startswith('discover/') else {'id':int(path.split('/')[1].split('?')[0]),'genres':[]}
  backend.request.side_effect=[[{'movie':{'ids':{'tmdb':501}}}],[{'ids':{'tmdb':502}}]]
  config={'base_per_hour':5,'extra_per_source':2,'maximum_per_hour':20,'minimum_votes':100,
   'sources':[{'id':'tmdb','adapter':'tmdb_discover','enabled':True,'pages':1},{'id':'trakt','adapter':'trakt','enabled':True,'candidate_limit':4}]}
  with patch.dict(os.environ,{'TRAKT_CLIENT_ID':'fake'}):pool,status=discover(backend,[],config)
  self.assertEqual([m['id'] for m in pool],[501,502])
  self.assertEqual(pool[0]['discovery_sources'],['tmdb','trakt'])
  self.assertEqual(status[-1]['status'],'ok')
  self.assertEqual(hourly_limit(config,[(0,m,'') for m in pool]),7)
