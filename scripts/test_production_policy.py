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
   self.assertIsNone(production_exclusion({'budget':value}))
  self.assertEqual(production_budget({'productionBudget':None,'budget':5000000}),5000000)
  self.assertEqual(production_exclusion({'budget':9999999}),'known_low_budget')
  self.assertIsNone(production_exclusion({'budget':10000000}))
 def test_exact_canonical_indie_keywords_not_synopsis_or_company_names(self):
  for words in (['independent film'],{'keywords':[{'name':'Low-Budget'}]},['microbudget']):
   self.assertEqual(production_exclusion({'keywords':words,'budget':50000000}),'independent_or_low_budget')
  for m in ({'keywords':['independent woman']},{'overview':'an independent film critic'},{'companyIds':[1]},{'keywords':None},{'keywords':42}):
   self.assertIsNone(production_exclusion(m))
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
  late=[horror(7200000+i,popularity=50) for i in range(30)]
  backend=FakeBackend();backend.movie=lambda p:dict(next(m for m in first+late if m['id']==int(p.split('/')[1].split('?')[0])),budget=10000000 if int(p.split('/')[1].split('?')[0])<7200000 else 100000000)
  cfg=dict(load_config(),history_enrichment_per_run=0,manual_quality_pool=30)
  with patch('recommend.discover',return_value=(first+late,[])),patch('recommend.match_score',return_value=1):
   self.assertEqual(recommend_user(backend,{'user_id':'test'},NOW,cfg,manual=True),30)
  self.assertTrue(all(r['tmdb_id']>=7200000 for r in backend.collection))
 def test_unknown_budget_never_discards_valid_small_or_full_batches(self):
  for n in (3,30):
   candidates=[horror(7100000+i,budget=0) for i in range(n)]
   backend=FakeBackend();backend.movie=lambda p:next(m for m in candidates if m['id']==int(p.split('/')[1].split('?')[0]))
   with patch('recommend.discover',return_value=(candidates,[])):
    self.assertEqual(recommend_user(backend,{'user_id':'test'},NOW,dict(load_config(),history_enrichment_per_run=0),manual=True),n)
   self.assertTrue(all(r['metadata']['recommendationProposedBudgetMedian'] is None for r in backend.collection))
