import unittest
from budget_evidence import BudgetVerifier,parse_evidence,USD,query_for
from recommend import recommend_user,load_config
from unittest.mock import patch
from test_recommendation_pipeline import FakeBackend,movie,NOW

def claim(mid,amount='4000000',**changes):
 values={'tmdb':str(mid),'movie':'http://www.wikidata.org/entity/Q123','currency':USD,'amount':amount,'imdb':'tt1234567','reference':'https://en.wikipedia.org/wiki/Test_film',**changes}
 return {k:{'value':v}for k,v in values.items()}
def data(rows):return {'results':{'bindings':rows}}

class BudgetEvidenceTests(unittest.TestCase):
 def test_identity_currency_reference_and_numeric_proof_are_required(self):
  m={'id':5000001,'external_ids':{'imdb_id':'tt1234567'}}
  for change in [{'tmdb':'5000002'},{'imdb':'tt9999999'},{'currency':'EUR'},{'reference':''},{'amount':'nan'},{'lower':'5000000'},{'movie':'https://example.com/Q123'}]:
   self.assertEqual(parse_evidence(data([claim(m['id'],**change)]),[m]),{})
  proof=parse_evidence(data([claim(m['id'])]),[m])[m['id']]
  self.assertEqual(proof['amountUSD'],4000000);self.assertEqual(proof['tmdbId'],m['id'])
 def test_conflicting_claims_and_ranges_use_the_lower_verified_amount(self):
  m={'id':5000001}
  proof=parse_evidence(data([claim(m['id'],amount='5000000',lower='2000000'),claim(m['id'],amount='7000000')]),[m])[m['id']]
  self.assertEqual(proof['amountUSD'],2000000)
 def test_known_tmdb_budgets_are_never_overridden_and_optional_failures_are_bounded(self):
  calls=[]
  verifier=BudgetVerifier(fetch=lambda ids:calls.append(ids)or data([claim(i)for i in ids]))
  movies=[{'id':1,'budget':1000000},{'id':2,'budget':0}];verifier.verify(movies)
  self.assertEqual(calls,[[2]]);self.assertEqual(movies[0]['budget'],1000000);self.assertEqual(movies[1]['budget'],4000000)
  def fail(ids):raise RuntimeError('network down')
  v=BudgetVerifier(fetch=fail);v.verify([{'id':i}for i in range(1000,1100)])
  self.assertEqual(v.failures,2);self.assertEqual(len(v.attempted),40)
 def test_verified_unknown_budgets_can_refill_a_real_thirty_film_batch_without_guessing(self):
  b=FakeBackend();candidates=[dict(movie(5000000+i),budget=0)for i in range(50)]
  b.movie=lambda path:candidates[int(path.split('/')[1].split('?')[0])-5000000]
  b.budget_claims=lambda ids:data([claim(mid)for mid in ids])
  with patch('recommend.discover',return_value=(candidates,[])):
   self.assertEqual(recommend_user(b,{'user_id':'test'},NOW,dict(load_config(),history_enrichment_per_run=0),manual=True),30)
  self.assertTrue(all(r['metadata']['productionBudget']==4000000 and r['metadata']['budgetEvidence']['tmdbId']==r['tmdb_id']for r in b.collection))
  self.assertTrue(all(r['metadata']['recommendationBudgetSource']=='wikidata'for r in b.collection))
 def test_dry_run_executes_search_and_proof_without_any_database_mutations(self):
  b=FakeBackend();candidates=[movie(5000000+i)for i in range(30)]
  b.movie=lambda path:candidates[int(path.split('/')[1].split('?')[0])-5000000]
  with patch('recommend.discover',return_value=(candidates,[])):
   self.assertEqual(recommend_user(b,{'user_id':'test'},NOW,load_config(),manual=True,dry_run=True),30)
  self.assertEqual(b.collection,[]);self.assertEqual(b.patched,[])
 def test_queries_use_only_valid_provider_ids_and_reference_claims(self):
  q=query_for([5,'unsafe',False]);self.assertIn('"5"',q);self.assertNotIn('unsafe',q);self.assertIn('prov:wasDerivedFrom',q)

class BudgetOutageTests(unittest.TestCase):
 def test_unverified_empty_batch_during_budget_outage_is_not_reported_as_success(self):
  b=FakeBackend();candidates=[dict(movie(5000000+i),budget=0)for i in range(30)]
  b.movie=lambda path:candidates[int(path.split('/')[1].split('?')[0])-5000000]
  def fail(ids):raise RuntimeError('temporary budget provider outage')
  b.budget_claims=fail
  with patch('recommend.discover',return_value=(candidates,[])):
   with self.assertRaisesRegex(Exception,'Budget verification unavailable'):
    recommend_user(b,{'user_id':'test'},NOW,dict(load_config(),history_enrichment_per_run=0),manual=True)
  self.assertEqual(b.collection,[]);self.assertEqual(b.patched,[])


class DeferredBudgetTests(unittest.TestCase):
 def test_deep_verified_candidates_are_retained_when_early_budget_proofs_are_low(self):
  b=FakeBackend();candidates=[dict(movie(5000000+i),budget=0)for i in range(100)]
  b.movie=lambda path:candidates[int(path.split('/')[1].split('?')[0])-5000000]
  b.budget_claims=lambda ids:data([claim(mid,amount='2000000'if mid<5000060 else'5000000')for mid in ids])
  with patch('recommend.discover',return_value=(candidates,[])):
   self.assertEqual(recommend_user(b,{'user_id':'test'},NOW,dict(load_config(),history_enrichment_per_run=0),manual=True),30)
  self.assertTrue(all(r['tmdb_id']>=5000060 for r in b.collection))

class ProbeCommandTests(unittest.TestCase):
 def test_published_probe_command_selects_manual_read_only_mode(self):
  import runpy
  from pathlib import Path
  b=FakeBackend();b.search_report={'accepted':30}
  with patch.dict('os.environ',{},clear=True),patch('recommend.Backend',return_value=b),patch('recommend.read_rows',return_value=[{'user_id':'test'}]),patch('recommend.recommend_user',return_value=30)as run:
   runpy.run_path(str(Path(__file__).with_name('probe_recommendations.py')),run_name='__main__')
  self.assertTrue(run.call_args.kwargs['manual']);self.assertTrue(run.call_args.kwargs['dry_run'])
  self.assertEqual(b.collection,[]);self.assertEqual(b.patched,[])
