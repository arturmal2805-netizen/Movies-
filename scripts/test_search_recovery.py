"""A large rated catalogue must not reduce personal search to exhausted anchors."""
import unittest
from unittest.mock import Mock,patch
from urllib.parse import urlsplit,parse_qs
from recommend import anchor_feedback,liked_movie_seeds,preferred_keyword_seeds,preferred_periods,recommend_user,load_config
from recommendation_sources import discover,tmdb_candidates
from movie_features import profile
from test_recommendation_pipeline import FakeBackend,movie,NOW


def history():
 return [{'tmdb_id':900000+i,'impression':'like' if i<40 else 'dislike',
          'updated_at':f'2026-10-10T12:{i%60:02d}:00+00:00',
          'metadata':{'year':2020,'genreIds':[27],'director':'Favorite' if i<40 else 'Rejected',
                      'keywords':['body horror' if i<40 else 'ghost']}} for i in range(100)]


def horror(mid,theme='body horror'):
 return dict(movie(mid),genres=[{'id':27}],genre_ids=[27],keywords=[theme])


class SearchRecoveryTests(unittest.TestCase):
 def test_manual_anchors_reach_thirty_six_distinct_positive_films_not_twelve(self):
  seeds=liked_movie_seeds(history(),36,rotation=1)
  self.assertEqual(len(seeds),36);self.assertEqual(len(set(seeds)),36)
  self.assertTrue(all(900000<=mid<900040 for mid in seeds))

 def test_all_thirty_six_anchors_get_both_routes_before_any_deeper_page(self):
  backend=Mock();backend.movie.return_value={'results':[]}
  cfg={'minimum_votes':100,'pages':1,'_now':NOW,'_preferred_movie_ids':list(range(1,37)),
       '_anchor_batch_size':12,'_include_similar':True,'_discovery_pages':{}}
  for search_round in range(3):tmdb_candidates(backend,[],dict(cfg,_search_round=search_round))
  paths=[c.args[0] for c in backend.movie.call_args_list if c.args[0].startswith('movie/')]
  self.assertEqual(len(paths),72);self.assertEqual(len(paths),len(set(paths)))
  self.assertEqual({int(p.split('/')[1]) for p in paths},set(range(1,37)))
  self.assertTrue(all(parse_qs(urlsplit(p).query)['page']==['1'] for p in paths))

 def test_similar_failure_does_not_remove_recommendations_and_route_identity_survives_merge(self):
  backend=Mock()
  def fetch(path):
   if '/similar?' in path:raise RuntimeError('offline')
   return {'results':[horror(700000)]}
  backend.movie.side_effect=fetch
  cfg=dict(load_config(),sources=[{'id':'tmdb','adapter':'tmdb_discover','enabled':True,'pages':1}],
           _preferred_movie_ids=[900000],_include_similar=True)
  pool,_=discover(backend,[],cfg)
  self.assertEqual(len(pool),1);self.assertEqual(pool[0]['_personal_routes'],['recommendations'])
  backend.movie.side_effect=lambda path:{'results':[horror(700000)]}
  pool,_=discover(backend,[],cfg)
  self.assertEqual(set(pool[0]['_personal_routes']),{'recommendations','similar'})
  self.assertEqual(pool[0]['_liked_anchor_ids'],[900000])

 def test_full_pipeline_recovers_thirty_from_later_anchors_when_initial_routes_are_exhausted(self):
  backend=FakeBackend();backend.ratings=history()
  def fetch(path):
   if path.startswith('discover/'):return {'results':[],'total_pages':1}
   if '/recommendations?' in path:return {'results':[horror(900000)]} # Already rated.
   if '/similar?' in path:
    anchor=int(path.split('/')[1]);return {'results':[horror(700000+i) for i in range(30)] if anchor>=900012 else []}
   return horror(int(path.split('/')[1].split('?')[0]))
  backend.movie=fetch
  cfg=dict(load_config(),history_enrichment_per_run=0,manual_quality_pool=30,
           sources=[{'id':'tmdb','adapter':'tmdb_discover','enabled':True,'pages':1}])
  with patch('recommend.liked_movie_seeds',return_value=list(range(900000,900036))):
   self.assertEqual(recommend_user(backend,{'user_id':'test'},NOW,cfg,manual=True),30)
  self.assertTrue(all(r['metadata']['recommendationPersonalRoutes']==['similar'] for r in backend.collection))
  self.assertTrue(all(r['metadata']['recommendationSearchPasses']==2 for r in backend.collection))
  self.assertTrue(all(r['metadata']['recommendationAnchorCount']==36 for r in backend.collection))
  self.assertTrue(all(r['metadata']['recommendationAnchorCoverage']==24 for r in backend.collection))

 def test_repeated_route_misses_reduce_priority_without_deleting_a_liked_anchor(self):
  rows=history()[:6]
  for i,row in enumerate(rows):row['updated_at']=f'2026-10-10T12:0{i}:00+00:00'
  failed=rows[-1]['tmdb_id']
  feedback=[{'tmdb_id':700000+i,'impression':'dislike','metadata':{'recommendationAnchorIds':[failed]},'updated_at':'2026-10-11'} for i in range(12)]
  before=liked_movie_seeds(rows,3);after=liked_movie_seeds(rows+feedback,3)
  self.assertEqual(before[0],failed);self.assertNotIn(failed,after)
  self.assertIn(failed,liked_movie_seeds(rows+feedback,6))

 def test_feedback_deduplicates_ratings_shares_credit_and_ignores_watched(self):
  row={'tmdb_id':10,'impression':'dislike','updated_at':'2026-10-10','metadata':{'recommendationAnchorIds':[1,1,2,10,False,'3']}}
  expected=1/2.5
  self.assertEqual(anchor_feedback([row,row]),{1:expected,2:expected})
  newer=dict(row,impression='like',updated_at='2026-10-11')
  self.assertEqual(anchor_feedback([row,newer]),{1:1.5/2.5,2:1.5/2.5})
  self.assertEqual(anchor_feedback([dict(row,impression='watched')]),{})
  for anchors in (13,'1,2',{'id':1}):
   self.assertEqual(anchor_feedback([dict(row,metadata={'recommendationAnchorIds':anchors})]),{})

 def test_search_does_not_mistake_spin_off_for_a_personal_theme(self):
  rows=history()
  for r in rows[:40]:r['metadata'].update(keywords=['body horror','spin off','prequel'],keywordIds=[101,102,103])
  seeds=preferred_keyword_seeds(rows,profile(rows))
  self.assertIn(101,seeds);self.assertNotIn(102,seeds);self.assertNotIn(103,seeds)

 def test_keyword_search_rotates_twelve_themes_and_preserves_broad_horror_and_dystopia(self):
  backend=Mock();backend.movie.return_value={'results':[],'total_pages':1}
  cfg={'minimum_votes':100,'pages':1,'_now':NOW,'_preferred_keywords':list(range(100,112)),'_discovery_pages':{}}
  observed=set()
  for i in range(3):
   backend.movie.reset_mock();tmdb_candidates(backend,[],dict(cfg,_search_round=i))
   queries=[parse_qs(urlsplit(c.args[0]).query) for c in backend.movie.call_args_list]
   ids={int(q['with_keywords'][0]) for q in queries if q.get('with_genres')==['27'] and 'with_keywords' in q}
   self.assertEqual(len(ids),4);observed|=ids
   self.assertTrue(any(q.get('with_keywords')==['4565'] for q in queries))
   self.assertTrue(any(q.get('with_genres')==['27'] and 'with_keywords' not in q for q in queries))
  self.assertEqual(observed,set(range(100,112)))

 def test_preferred_period_routes_are_soft_and_cannot_change_explicit_minimum_year(self):
  rows=history();model=profile(rows)
  self.assertEqual(preferred_periods(model),[]) # Everyone shares the same year; not a discriminative preference.
  backend=Mock();backend.movie.return_value={'results':[]}
  tmdb_candidates(backend,[],{'minimum_votes':100,'pages':1,'_now':NOW,'_preferred_periods':[2020,2025,1990]})
  queries=[parse_qs(urlsplit(c.args[0]).query) for c in backend.movie.call_args_list]
  self.assertTrue(any(q['primary_release_date.gte']==['2020-01-01'] for q in queries))
  self.assertTrue(any(q['primary_release_date.gte']==['2000-01-01'] for q in queries))
  self.assertFalse(any(q['primary_release_date.gte']==['1990-01-01'] for q in queries))
  self.assertTrue(all(q['primary_release_date.lte'][0]<=NOW.date().isoformat() for q in queries))


if __name__=='__main__':unittest.main()
