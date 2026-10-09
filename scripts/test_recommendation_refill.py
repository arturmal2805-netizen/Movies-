import unittest
from unittest.mock import Mock,patch
from urllib.parse import parse_qs,urlsplit
from recommend import recommend_user,load_config,liked_movie_seeds
from recommendation_sources import discover
from test_recommendation_pipeline import FakeBackend,movie,NOW

def horror(mid):
 return dict(movie(mid),genres=[{'id':27}],genre_ids=[27],keywords={'keywords':[{'id':12,'name':'body horror'}]})

class RefillTests(unittest.TestCase):
 def test_positive_seeds_cover_different_themes_and_ignore_family_favorites(self):
  rows=[{'tmdb_id':600000+i,'impression':'like','metadata':{'year':2020,'genreIds':[27],'keywords':['ghost'],'director':'Same director'}} for i in range(8)]
  rows.append({'tmdb_id':700000,'impression':'like','metadata':{'year':2020,'genreIds':[27],'keywords':['body horror'],'director':'Different director'}})
  rows.append({'tmdb_id':800000,'impression':'like','plot':10,'cinematography':10,'metadata':{'year':2020,'genreIds':[27,10751]}})
  seeds=liked_movie_seeds(rows)
  self.assertIn(700000,seeds[:2]);self.assertNotIn(800000,seeds);self.assertEqual(len(seeds),6)
 def test_liked_seeds_reach_the_real_adapter_dispatch(self):
  backend=Mock();backend.movie.return_value={'results':[]}
  config=dict(load_config(),sources=[{'id':'tmdb','adapter':'tmdb_discover','enabled':True,'pages':1}],_preferred_movie_ids=[600001,600002],_search_round=1)
  discover(backend,[],config)
  paths=[c.args[0] for c in backend.movie.call_args_list if '/recommendations?' in c.args[0]]
  self.assertEqual(len(paths),2)
  self.assertTrue(all(parse_qs(urlsplit(p).query)['page']==['2'] for p in paths))

 def test_refill_replaces_large_canonical_rejection_pool_and_reaches_thirty(self):
  backend=FakeBackend();calls=[]
  first=[horror(600000+i) for i in range(120)]
  second=[horror(700000+i) for i in range(30)]
  def lookup(path):
   mid=int(path.split('/')[1].split('?')[0]);calls.append(mid)
   return dict(horror(mid),genres=[{'id':27},{'id':10751}],genre_ids=[27,10751]) if 600000<=mid<600097 else horror(mid)
  backend.movie=lookup
  with patch('recommend.discover',side_effect=[(first,[]),(second,[])]) as search:
   self.assertEqual(recommend_user(backend,{'user_id':'test'},NOW,load_config(),manual=True),30)
  self.assertEqual(search.call_count,2)
  self.assertTrue(set(range(600000,600120)).issubset(search.call_args.args[2]['_excluded_ids']))
  self.assertEqual(len(calls),len(set(calls)))
  self.assertTrue(all(10751 not in row['metadata']['genreIds'] for row in backend.collection))
  self.assertLessEqual(len(calls),240)

 def test_detail_quota_stops_a_search_with_only_bad_candidates(self):
  backend=FakeBackend();calls=[]
  def lookup(path):
   mid=int(path.split('/')[1].split('?')[0]);calls.append(mid)
   return dict(horror(mid),genres=[{'id':27},{'id':16}],genre_ids=[27,16])
  backend.movie=lookup
  candidates=[horror(600000+i) for i in range(100)]
  with patch('recommend.discover',return_value=(candidates,[])) as search:
   self.assertEqual(recommend_user(backend,{'user_id':'test'},NOW,dict(load_config(),detail_candidate_limit=40),manual=True),0)
  self.assertEqual(len(calls),40);self.assertEqual(search.call_count,1)

 def test_refill_outage_retains_three_verified_films(self):
  backend=FakeBackend();backend.movie=lambda p:horror(int(p.split('/')[1].split('?')[0]))
  with patch('recommend.discover',side_effect=[([horror(600000+i) for i in range(3)],[]),RuntimeError('offline')]):
   self.assertEqual(recommend_user(backend,{'user_id':'test'},NOW,load_config(),manual=True),3)

 def test_sparse_negative_search_result_is_judged_after_canonical_keywords(self):
  backend=FakeBackend()
  backend.ratings=[{'tmdb_id':900+i,'impression':'dislike','plot':1,'cinematography':1,'metadata':{'genreIds':[27],'keywords':['ghost']}} for i in range(30)]
  backend.movie=lambda p:horror(int(p.split('/')[1].split('?')[0]))
  coarse=dict(horror(600000),keywords=['ghost'])
  with patch('recommend.discover',return_value=([coarse],[])):
   self.assertEqual(recommend_user(backend,{'user_id':'test'},NOW,load_config(),manual=True),1)
  self.assertEqual(backend.collection[0]['metadata']['keywords'],['body horror'])

 def test_full_manual_pipeline_sends_the_positive_rating_as_search_seed(self):
  backend=FakeBackend();backend.ratings=[{'tmdb_id':600001,'impression':'like','metadata':{'title':'Liked','year':2020,'genreIds':[27],'keywords':[],'productionCountries':['US'],'originalLanguage':'en','featureVersion':2}}]
  with patch('recommend.discover',return_value=([],[])) as search:
   recommend_user(backend,{'user_id':'test'},NOW,load_config(),manual=True)
  self.assertEqual(search.call_args_list[0].args[2]['_preferred_movie_ids'],[600001])
