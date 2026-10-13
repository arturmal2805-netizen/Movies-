"""Budget cannot veto, rank or delay a batch; other explicit bans still apply."""
import copy,unittest
from unittest.mock import patch
from production_policy import production_exclusion,style_affinity,director_focus
from audience_priority import audience_production_score,selection_priority_score
from movie_features import profile,match_score
from recommend import recommend_user,load_config,rank_candidates,valid_candidate,focus_reference_ids
from test_recommendation_pipeline import FakeBackend,movie,NOW

def horror(mid,**kwargs):return dict(movie(mid),genre_ids=[27],genres=[{'id':27}],**kwargs)

class ProductionPolicyTests(unittest.TestCase):
 def test_every_budget_and_budget_proxy_is_neutral_for_admission_and_ranking(self):
  base=horror(7100000,popularity=10,vote_count=2000)
  for cost in (None,0,1,2999999,3000000,1000000000,-1,True,'500000',float('nan'),float('inf')):
   for tag in ('independent film','low budget','microbudget','micro budget'):
    row=dict(base,budget=cost,productionBudget=cost,keywords=[tag])
    self.assertIsNone(production_exclusion(row));self.assertTrue(valid_candidate(row,100,NOW.date()))
    self.assertEqual(audience_production_score(row),audience_production_score(base))
    self.assertEqual(selection_priority_score(row),selection_priority_score(base))
 def test_budget_is_not_a_learned_keyword_or_financial_feature(self):
  rows=[{'tmdb_id':i+1,'impression':'like' if i<10 else 'dislike','metadata':{'year':2020,'genreIds':[27],'companyIds':[1],'castIds':[2],'budget':100000000 if i<10 else 1}}for i in range(40)]
  before=profile(rows);changed=copy.deepcopy(rows)
  for row in changed:row['metadata'].update(budget=None,productionBudget=1,keywords=['microbudget','low budget','independent film'])
  after=profile(changed)
  for film in (rows[0]['metadata'],changed[0]['metadata']):self.assertAlmostEqual(match_score(film,before),match_score(film,after))
 def test_popularity_and_audience_breadth_have_material_priority(self):
  base=horror(7100000,popularity=2,vote_count=100)
  popular=dict(base,popularity=30,vote_count=5000)
  self.assertGreater(selection_priority_score(popular,-100),selection_priority_score(base,100))
  self.assertGreater(audience_production_score(dict(base,popularity=100))-audience_production_score(base),20)
 def test_canonical_unknown_budgets_fill_both_small_and_full_batches_without_lookups(self):
  for n in (3,30,60):
   candidates=[horror(7100000+i,budget=None if i%2 else 1,keywords=['independent film']) for i in range(n)]
   b=FakeBackend();b.movie=lambda path:next(m for m in candidates if m['id']==int(path.split('/')[1].split('?')[0]))
   b.budget_claims=lambda ids:self.fail('Retired budget provider must never be called')
   with patch('recommend.discover',return_value=(candidates,[])):
    self.assertEqual(recommend_user(b,{'user_id':'test'},NOW,dict(load_config(),history_enrichment_per_run=0),manual=True),min(30,n))
   self.assertEqual(len(b.collection),min(30,n))
   self.assertTrue(all(not any(k.startswith('recommendationBudget')for k in row['metadata'])for row in b.collection))
 def test_horror_comedy_and_camp_still_refill_to_thirty(self):
  first=[horror(7100000+i)for i in range(80)];later=[horror(7200000+i,budget=None)for i in range(40)]
  b=FakeBackend();b.movie=lambda path:dict(next(m for m in first+later if m['id']==int(path.split('/')[1].split('?')[0])),genreIds=[27,35]if int(path.split('/')[1].split('?')[0])<7200000 else[27])
  with patch('recommend.discover',side_effect=[(first,[]),(later,[])]):self.assertEqual(recommend_user(b,{'user_id':'test'},NOW,dict(load_config(),history_enrichment_per_run=0,manual_quality_pool=30),manual=True),30)
  self.assertTrue(all(row['tmdb_id']>=7200000 for row in b.collection))
  self.assertEqual(production_exclusion({'keywords':['parody']}),'camp_or_parody')
 def test_zombeavers_stays_banned_regardless_of_budget_or_director(self):
  beavers=horror(254474,genreIds=[27,28,35],title='Zombeavers',director='Robert Eggers')
  for cost in (None,1,1000000000):self.assertFalse(valid_candidate(dict(beavers,budget=cost),100,NOW.date()))
 def test_director_identity_is_canonical_and_style_requires_multiple_concepts(self):
  fake={'_liked_directors':['Robert Eggers'],'credits':{'crew':[{'job':'Actor','name':'Robert Eggers'},{'job':'Director','name':'Other'}]}}
  self.assertFalse(director_focus(fake));self.assertTrue(director_focus({'director':'Robert Eggers'}))
  self.assertEqual(style_affinity({'keywords':['vampire','monster','zombie','animal attack']}),0)
  self.assertGreater(style_affinity({'keywords':['gothic horror','period piece','isolation']}),0)
 def test_popularity_does_not_silence_convincing_public_review_difference(self):
  weak=horror(7100000,popularity=100,vote_count=5000,vote_average=4)
  strong=horror(7100001,popularity=10,vote_count=2000,vote_average=7)
  self.assertEqual(rank_candidates([weak,strong],[],[],now=NOW)[0][1]['id'],strong['id'])
 def test_focus_titles_resolve_exactly_and_do_not_create_training_ratings(self):
  from unittest.mock import Mock
  b=Mock();b.movie.return_value={'results':[{'id':503919,'original_title':'The Lighthouse','release_date':'2019-10-18'},{'id':999,'original_title':'The Lighthouse','release_date':'2000-01-01'}]}
  rows=[];self.assertIn(503919,focus_reference_ids(b,rows));self.assertEqual(rows,[])
  b.movie.return_value={'results':[{'id':503919,'original_title':'The Lighthouse','release_date':'2019-10-18'},{'id':998,'original_title':'The Lighthouse','release_date':'2019-09-01'}]}
  self.assertNotIn(503919,focus_reference_ids(b,rows))
