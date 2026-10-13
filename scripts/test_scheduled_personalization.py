"""Scheduled batches must use the same personal search as manual requests."""
import datetime
import unittest
from unittest.mock import patch
from recommend import recommend_user,load_config
from test_recommendation_pipeline import FakeBackend,movie

NOW=datetime.datetime(2026,10,13,18,30,tzinfo=datetime.timezone.utc)


def history():
 return [{'tmdb_id':900000+i,'impression':'like' if i<40 else 'dislike',
          'metadata':{'year':2020,'genreIds':[27],'keywords':['body horror' if i<40 else 'ghost']}} for i in range(100)]


def horror(mid,theme='body horror'):
 return dict(movie(mid),genres=[{'id':27}],genre_ids=[27],keywords=[theme])


class ScheduledPersonalizationTests(unittest.TestCase):
 def backend(self,candidates):
  backend=FakeBackend();backend.now=NOW;backend.ratings=history()
  by_id={m['id']:m for m in candidates}
  backend.movie=lambda path:by_id[int(path.split('/')[1].split('?')[0])]
  return backend

 def test_hourly_full_weak_batch_searches_again_and_replaces_it_with_better_matches(self):
  weak=[horror(2000000+i,'ghost') for i in range(60)]
  strong=[horror(2100000+i) for i in range(30)]
  backend=self.backend(weak+strong);cfg=dict(load_config(),history_enrichment_per_run=0,manual_quality_pool=30)
  with patch('recommend.discover',side_effect=[(weak,[]),(strong,[])]) as search,patch('recommend.match_score',side_effect=lambda m,t:1 if 'body horror' in m.get('keywords',[]) else -1):
   added=recommend_user(backend,{'user_id':'test'},NOW,cfg)
  self.assertEqual(added,cfg['base_per_hour']);self.assertEqual(search.call_count,2)
  self.assertTrue(all(row['tmdb_id']>=2100000 for row in backend.collection))
  first_config=search.call_args_list[0].args[2]
  self.assertEqual(len(first_config['_preferred_movie_ids']),36)
  self.assertTrue(first_config['_include_similar']);self.assertEqual(first_config['_anchor_batch_size'],12)
  self.assertTrue(all(row['metadata']['recommendationMode']=='scheduled' for row in backend.collection))
  self.assertTrue(all(row['metadata']['recommendationSearchVersion']=='audience-search42' for row in backend.collection))

 def test_hourly_checks_quality_pool_even_when_the_first_fifteen_are_positive(self):
  candidates=[horror(2000000+i) for i in range(150)];backend=self.backend(candidates)
  cfg=dict(load_config(),history_enrichment_per_run=0,manual_quality_pool=100)
  with patch('recommend.discover',return_value=(candidates,[])),patch('recommend.match_score',return_value=1):
   self.assertEqual(recommend_user(backend,{'user_id':'test'},NOW,cfg),15)
  self.assertTrue(all(row['metadata']['recommendationDetailsAttempted']>=100 for row in backend.collection))
  self.assertTrue(all(row['metadata']['recommendationQualityPoolTarget']==100 for row in backend.collection))

 def test_expanded_hourly_search_preserves_a_small_valid_weak_batch(self):
  for count in (1,3):
   candidates=[horror(2000000+i,'ghost') for i in range(count)];backend=self.backend(candidates)
   with patch('recommend.discover',return_value=(candidates,[])),patch('recommend.match_score',return_value=-1):
    self.assertEqual(recommend_user(backend,{'user_id':'test'},NOW,dict(load_config(),history_enrichment_per_run=0)),count)
   self.assertEqual(len(backend.collection),count)

 def test_completed_scheduled_slot_still_skips_every_provider_call(self):
  backend=self.backend([])
  with patch('recommend.discover') as discover:
   self.assertEqual(recommend_user(backend,{'user_id':'test','last_recommendation_at':NOW.isoformat()},NOW,load_config()),0)
  discover.assert_not_called();self.assertEqual(backend.collection,[])

 def test_rolling_maximum_is_preserved_while_searching_a_larger_candidate_pool(self):
  candidates=[horror(2000000+i) for i in range(150)];backend=self.backend(candidates)
  previous=(NOW-datetime.timedelta(minutes=20)).isoformat()
  backend.collection=[{'tmdb_id':2500000+i,'created_at':previous,'reason':'Earlier batch','metadata':{'recommendationMode':'scheduled'}} for i in range(90)]
  cfg=dict(load_config(),history_enrichment_per_run=0,manual_quality_pool=50)
  with patch('recommend.discover',return_value=(candidates,[])),patch('recommend.match_score',return_value=1):
   self.assertEqual(recommend_user(backend,{'user_id':'test','last_recommendation_at':previous},NOW,cfg),10)
  self.assertEqual(len(backend.collection),100)
  self.assertTrue(all(row['metadata']['recommendationBatchTarget']==10 for row in backend.collection[90:]))


if __name__=='__main__':unittest.main()
