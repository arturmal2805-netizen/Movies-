"""Explicit indie exclusions must refill, not silently relax or empty valid pools."""
import math,unittest
from unittest.mock import patch
from production_policy import production_budget,production_exclusion,budget_priority_score
from audience_priority import audience_production_score
from recommend import recommend_user,load_config,rank_candidates
from test_recommendation_pipeline import FakeBackend,movie,NOW

def horror(mid,**kwargs):return dict(movie(mid),genre_ids=[27],genres=[{'id':27}],**kwargs)

class ProductionPolicyTests(unittest.TestCase):
 def test_canonical_budget_boundary_and_unknown_or_malformed_values(self):
  for value in (None,0,-1,True,False,'500000',float('nan'),float('inf')):
   self.assertIsNone(production_budget({'budget':value}))
   self.assertEqual(production_exclusion({'budget':value}),'unverified_budget')
   self.assertIsNone(production_exclusion({'budget':value},require_budget=False))
  self.assertEqual(production_budget({'productionBudget':None,'budget':5000000}),5000000)
  self.assertEqual(production_exclusion({'budget':2999999}),'known_low_budget')
  self.assertIsNone(production_exclusion({'budget':3000000}))
 def test_exact_canonical_indie_keywords_not_synopsis_or_company_names(self):
  for words in (['independent film'],{'keywords':[{'name':'Low-Budget'}]},['microbudget']):
   self.assertEqual(production_exclusion({'keywords':words,'budget':50000000}),'independent_or_low_budget')
  for m in ({'keywords':['independent woman']},{'overview':'an independent film critic'},{'companyIds':[1]},{'keywords':None},{'keywords':42}):
   self.assertIsNone(production_exclusion(dict(m,budget=15000000)))
 def test_popularity_and_known_budget_have_material_independent_effects(self):
  mid=horror(7100000,popularity=5,budget=10000000)
  large=dict(mid,id=7100001,budget=50000000)
  self.assertGreater(audience_production_score(large)-audience_production_score(mid),3)
  trending=dict(mid,id=7100002,popularity=100)
  self.assertGreater(audience_production_score(trending),audience_production_score(large))
  with patch('recommend.match_score',side_effect=lambda m,t:100 if m['id']==mid['id'] else -100):
   self.assertEqual(rank_candidates([mid,large],[],[],now=NOW)[0][1]['id'],large['id'])
  self.assertTrue(math.isfinite(budget_priority_score({'budget':1e308})))
 def test_popular_indie_is_removed_and_cannot_bypass_policy(self):
  cheap=horror(7100000,budget=100000,popularity=1e6)
  indie=horror(7100001,budget=50000000,popularity=1e6,keywords=['independent film'])
  good=horror(7100002,budget=30000000)
  self.assertEqual([r[1]['id'] for r in rank_candidates([cheap,indie,good],[],[],now=NOW)],[good['id']])
 def test_canonical_cheap_first_page_refills_to_thirty_without_indie_filler(self):
  first=[horror(7100000+i,popularity=100) for i in range(80)]
  later=[horror(7200000+i,popularity=5) for i in range(40)]
  backend=FakeBackend()
  backend.movie=lambda p:dict(horror(int(p.split('/')[1].split('?')[0])),budget=100000 if int(p.split('/')[1].split('?')[0])<7200000 else 30000000)
  cfg=dict(load_config(),history_enrichment_per_run=0,manual_quality_pool=30)
  with patch('recommend.discover',side_effect=[(first,[]),(later,[])]):
   self.assertEqual(recommend_user(backend,{'user_id':'test'},NOW,cfg,manual=True),30)
  self.assertTrue(all(r['metadata']['productionBudget']==30000000 for r in backend.collection))
  self.assertTrue(all(r['metadata']['recommendationProductionExcludedCount']==80 for r in backend.collection))
 def test_unknown_coarse_budget_is_enriched_past_full_high_popularity_batch(self):
  first=[horror(7100000+i,popularity=100,budget=10000000) for i in range(60)]
  late=[horror(7200000+i,popularity=50,budget=None) for i in range(30)]
  backend=FakeBackend();backend.movie=lambda p:dict(next(m for m in first+late if m['id']==int(p.split('/')[1].split('?')[0])),popularity=100 if int(p.split('/')[1].split('?')[0])<7200000 else 50,budget=10000000 if int(p.split('/')[1].split('?')[0])<7200000 else 100000000)
  cfg=dict(load_config(),history_enrichment_per_run=0,manual_quality_pool=30)
  with patch('recommend.discover',return_value=(first+late,[])),patch('recommend.match_score',return_value=1):
   self.assertEqual(recommend_user(backend,{'user_id':'test'},NOW,cfg,manual=True),30)
  self.assertTrue(all(r['tmdb_id']>=7200000 for r in backend.collection))
 def test_unknown_canonical_budget_cannot_fill_a_small_or_full_batch(self):
  for n in (3,30):
   candidates=[horror(7100000+i,budget=0) for i in range(n)]
   backend=FakeBackend();backend.movie=lambda p:next(m for m in candidates if m['id']==int(p.split('/')[1].split('?')[0]))
   with patch('recommend.discover',return_value=(candidates,[])):
    self.assertEqual(recommend_user(backend,{'user_id':'test'},NOW,dict(load_config(),history_enrichment_per_run=0),manual=True),0)
   self.assertEqual(backend.collection,[])

class StrictProductionAndStyleTests(unittest.TestCase):
 def test_zombeavers_and_unknown_budget_cannot_pass_the_final_gate(self):
  from recommend import valid_candidate
  beavers=horror(254474,genreIds=[27,28,35],title='Zombeavers',budget=None)
  self.assertEqual(production_exclusion(beavers),'horror_comedy')
  self.assertFalse(valid_candidate(beavers,100,NOW.date()))
  missing=horror(7100000,budget=None)
  self.assertTrue(valid_candidate(missing,100,NOW.date(),require_target=False))
  self.assertFalse(valid_candidate(missing,100,NOW.date()))
 def test_director_exception_requires_canonical_director_not_a_route_claim(self):
  from production_policy import director_focus
  raw=horror(7100000,budget=2000000,_liked_directors=['Robert Eggers'],credits={'crew':[{'job':'Director','name':'Another director'}]})
  self.assertFalse(director_focus(raw));self.assertEqual(production_exclusion(raw),'known_low_budget')
  raw['credits']['crew']=[{'job':'Actor','name':'Robert Eggers'},{'job':'Director','name':'Another director'}]
  self.assertFalse(director_focus(raw))
  raw['credits']['crew']=[{'job':'Director','name':'Robert Eggers'}];raw['keywords']=['independent film']
  self.assertIsNone(production_exclusion(raw))
  raw['budget']=None;self.assertEqual(production_exclusion(raw),'unverified_budget')
 def test_single_vampire_or_monster_word_is_not_style_similarity(self):
  from production_policy import style_affinity
  self.assertEqual(style_affinity({'keywords':['vampire','monster','zombie','animal attack']}),0)
  self.assertGreater(style_affinity({'keywords':['gothic horror','period piece','isolation']}),0)
 def test_large_budget_bad_reviews_cannot_override_convincing_public_reviews(self):
  weak=horror(7100000,budget=100000000,popularity=100,vote_count=5000,vote_average=4)
  strong=horror(7100001,budget=5000000,popularity=10,vote_count=2000,vote_average=7)
  self.assertEqual(rank_candidates([weak,strong],[],[],now=NOW)[0][1]['id'],strong['id'])
 def test_refill_replaces_unknown_and_comedy_pool_with_thirty_verified_films(self):
  first=[horror(7100000+i,budget=None) for i in range(80)]
  later=[horror(7200000+i,budget=None) for i in range(40)]
  backend=FakeBackend();backend.movie=lambda p:dict(horror(int(p.split('/')[1].split('?')[0])),budget=None if int(p.split('/')[1].split('?')[0])<7200000 else 5000000)
  with patch('recommend.discover',side_effect=[(first,[]),(later,[])]):
   self.assertEqual(recommend_user(backend,{'user_id':'test'},NOW,dict(load_config(),history_enrichment_per_run=0,manual_quality_pool=30),manual=True),30)
  self.assertTrue(all(r['metadata']['productionBudget']==5000000 for r in backend.collection))
 def test_focus_titles_resolve_exactly_and_do_not_create_training_ratings(self):
  from recommend import focus_reference_ids
  from unittest.mock import Mock
  backend=Mock();backend.movie.return_value={'results':[{'id':503919,'original_title':'The Lighthouse','release_date':'2019-10-18'},{'id':999,'original_title':'The Lighthouse','release_date':'2000-01-01'}]}
  ratings=[];self.assertIn(503919,focus_reference_ids(backend,ratings));self.assertEqual(ratings,[])
  backend.movie.return_value={'results':[{'id':503919,'original_title':'The Lighthouse','release_date':'2019-10-18'},{'id':998,'original_title':'The Lighthouse','release_date':'2019-09-01'}]}
  self.assertNotIn(503919,focus_reference_ids(backend,ratings))

 def test_added_user_directors_are_material_preferences_not_actor_credits(self):
  from production_policy import director_focus,style_affinity
  for name in ('Zach Cregger','Зак Креггер','David Robert Mitchell','Дэвид Роберт Митчелл'):
   row={'budget':2300000,'director':name,'genreIds':[27]}
   self.assertTrue(director_focus(row));self.assertEqual(style_affinity(row),0);self.assertIsNone(production_exclusion(row))
   self.assertEqual(production_exclusion(dict(row,budget=None)),'unverified_budget')
