import unittest
from unittest.mock import Mock,patch
from recommend import liked_movie_seeds,preferred_director_seeds,recommend_user,load_config
from recommendation_sources import director_candidates,discover
from movie_features import profile
from test_recommendation_pipeline import FakeBackend,movie,NOW

class PersonalizedDiscoveryTests(unittest.TestCase):
 def history(self):
  return [{'tmdb_id':600000+i,'impression':'like' if i<8 else 'dislike','metadata':{'year':2020,'genreIds':[27],'director':'Trusted' if i<4 else 'Rejected','keywords':['monster' if i<8 else 'ghost']}} for i in range(40)]

 def test_recent_likes_cannot_be_crowded_out_by_old_keyword_rich_movies(self):
  rows=self.history()
  for row in rows[:8]:row['metadata']['keywords']=['monster']+[f'tag {i}' for i in range(24)]
  for i in range(4):rows.append({'tmdb_id':700000+i,'impression':'like','updated_at':f'2026-10-10T12:0{i}:00+00:00','metadata':{'year':2020,'genreIds':[27],'keywords':['monster']}})
  seeds=liked_movie_seeds(rows,12,rotation=1)
  self.assertEqual(seeds[:4],[700003,700002,700001,700000])
  self.assertEqual(len(seeds),12)

 def test_rotation_is_repeatable_and_changes_only_positive_eligible_anchors(self):
  rows=[dict(self.history()[0],tmdb_id=600000+i) for i in range(40)]
  first=liked_movie_seeds(rows,12,rotation=1)
  self.assertEqual(first,liked_movie_seeds(rows,12,rotation=1))
  self.assertNotEqual(first,liked_movie_seeds(rows,12,rotation=2))
  rows.append(dict(rows[0],tmdb_id=800000,impression='dislike'))
  rows.append(dict(rows[0],tmdb_id=800001,metadata={'year':1999,'genreIds':[27]}))
  self.assertNotIn(800000,liked_movie_seeds(rows,12,rotation=1))
  self.assertNotIn(800001,liked_movie_seeds(rows,12,rotation=1))

 def test_directors_need_repeated_likes_and_positive_lift(self):
  rows=self.history();model=profile(rows)
  self.assertEqual(preferred_director_seeds(rows,model),['Trusted'])
  singleton=dict(rows[0],tmdb_id=900000,metadata=dict(rows[0]['metadata'],director='One hit'))
  self.assertNotIn('One hit',preferred_director_seeds(rows+[singleton],profile(rows+[singleton])))
  self.assertEqual(preferred_director_seeds(rows[:4],profile(rows[:4])),[])

 def test_director_lookup_excludes_cast_and_ambiguous_people_and_seen_movies(self):
  backend=Mock()
  def lookup(path):
   if path.startswith('search/person?'):return {'results':[{'id':12,'name':'Trusted'}]}
   return {'cast':[{'id':1}], 'crew':[dict(movie(600001),job='Director'),dict(movie(600002),job='Writer'),dict(movie(600003),job='Director')]}
  backend.movie.side_effect=lookup
  found=director_candidates(backend,['Trusted'],{'_excluded_ids':{600001}})
  self.assertEqual([m['id'] for m in found],[600003])
  backend.movie.return_value={'results':[{'id':12,'name':'Trusted'},{'id':13,'name':'Trusted'}]};backend.movie.side_effect=None;backend.movie.reset_mock()
  self.assertEqual(director_candidates(backend,['Trusted'],{}),[])
  self.assertEqual(backend.movie.call_count,1)

 def test_original_person_name_can_match_localized_search_results(self):
  backend=Mock();backend.movie.side_effect=[{'results':[{'id':12,'name':'Локализованное имя','original_name':'Original Name'}]},{'crew':[dict(movie(600001),job='Director')]}]
  self.assertEqual(len(director_candidates(backend,['Original Name'],{})),1)

 def test_director_failure_is_optional_and_dispatch_preserves_candidates(self):
  backend=Mock();backend.movie.side_effect=lambda path: (_ for _ in ()).throw(RuntimeError('offline')) if path.startswith('search/person') else {'results':[movie(600001)]}
  config=dict(load_config(),sources=[{'id':'tmdb','adapter':'tmdb_discover','enabled':True,'pages':1}],_preferred_directors=['Trusted'])
  pool,statuses=discover(backend,[],config)
  self.assertEqual([m['id'] for m in pool],[600001]);self.assertEqual(statuses[0]['status'],'ok')
  self.assertTrue(any(c.args[0].startswith('search/person?') for c in backend.movie.call_args_list))

 def test_optional_director_candidates_still_need_canonical_policy_validation(self):
  backend=FakeBackend();backend.ratings=self.history()
  bad=dict(movie(700000),genres=[{'id':16}],genre_ids=[16],keywords=['monster'])
  backend.movie=lambda path:bad
  with patch('recommend.discover',return_value=([bad],[])):
   self.assertEqual(recommend_user(backend,{'user_id':'test'},NOW,dict(load_config(),history_enrichment_per_run=0),manual=True),0)
  self.assertEqual(backend.collection,[])

 def test_manual_search_passes_learned_directors_into_adapter(self):
  backend=FakeBackend();backend.ratings=self.history()
  with patch('recommend.discover',return_value=([],[])) as search:
   recommend_user(backend,{'user_id':'test'},NOW,dict(load_config(),history_enrichment_per_run=0),manual=True)
  self.assertEqual(search.call_args.args[2]['_preferred_directors'],['Trusted'])

 def test_route_attribution_survives_duplicate_sources_and_canonical_enrichment(self):
  backend=Mock()
  def lookup(path):
   if path.startswith('movie/600001/recommendations'):return {'results':[movie(700000)]}
   if path.startswith('search/person?'):return {'results':[{'id':12,'name':'Trusted'}]}
   if path.startswith('person/12/movie_credits'):return {'crew':[dict(movie(700000),job='Director')]}
   return {'results':[movie(700000)]}
  backend.movie.side_effect=lookup
  config=dict(load_config(),sources=[{'id':'tmdb','adapter':'tmdb_discover','enabled':True,'pages':1}],_preferred_movie_ids=[600001],_preferred_directors=['Trusted'])
  pool,_=discover(backend,[],config)
  self.assertEqual(len(pool),1);self.assertEqual(pool[0]['_liked_anchor_ids'],[600001]);self.assertEqual(pool[0]['_liked_directors'],['Trusted'])
  backend=FakeBackend();canonical=dict(movie(700000),genres=[{'id':27}],genre_ids=[27],keywords=['monster'])
  backend.movie=lambda path:canonical
  with patch('recommend.discover',return_value=(pool,[])):
   self.assertEqual(recommend_user(backend,{'user_id':'test'},NOW,dict(load_config(),history_enrichment_per_run=0),manual=True),1)
  metadata=backend.collection[0]['metadata']
  self.assertEqual(metadata['recommendationAnchorIds'],[600001]);self.assertEqual(metadata['recommendationDirectorSeeds'],['Trusted']);self.assertEqual(metadata['recommendationSearchVersion'],'feedback-search33')

 def test_personal_keyword_queries_precede_broad_lists_and_require_horror(self):
  from urllib.parse import urlsplit,parse_qs
  backend=Mock();backend.movie.return_value={'results':[]}
  config=dict(load_config(),sources=[{'id':'tmdb','adapter':'tmdb_discover','enabled':True,'pages':3}],_preferred_keywords=[101,102,103,104])
  discover(backend,[],config)
  paths=[c.args[0] for c in backend.movie.call_args_list if c.args[0].startswith('discover/movie?')]
  self.assertEqual(len(paths),21)
  for path in paths[:12]:
   query=parse_qs(urlsplit(path).query);self.assertIn(int(query['with_keywords'][0]),[101,102,103,104]);self.assertEqual(query['with_genres'],['27'])

 def test_translated_director_is_resolved_from_two_verified_liked_film_credits(self):
  backend=Mock()
  def lookup(path):
   if path.startswith('movie/'):return {'credits':{'crew':[{'id':42,'name':'English Name','job':'Director'},{'id':99,'name':'Actor','job':'Actor'}]}}
   if path.startswith('person/42/'):return {'crew':[dict(movie(700000),job='Director')]}
   raise AssertionError('Must not guess translated name or use search')
  backend.movie.side_effect=lookup
  result=director_candidates(backend,['Переведённое имя'],{'_director_anchor_ids':{'Переведённое имя':[600000,600001]}})
  self.assertEqual([m['id'] for m in result],[700000]);self.assertEqual(backend.movie.call_count,3)

 def test_conflicting_director_credits_are_never_resolved_by_guessing(self):
  backend=Mock();backend.movie.side_effect=[{'credits':{'crew':[{'id':42,'job':'Director'}]}},{'credits':{'crew':[{'id':43,'job':'Director'}]}}]
  self.assertEqual(director_candidates(backend,['Name'],{'_director_anchor_ids':{'Name':[600000,600001]}}),[])
  self.assertEqual(backend.movie.call_count,2)
