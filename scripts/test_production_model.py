"""Production learning must be private, coverage-safe and never an admission gate."""
import copy,unittest,datetime,threading
from unittest.mock import Mock
from urllib.parse import urlsplit,parse_qs
from production_model import production_features,fit_production,production_score
from movie_features import profile,match_score,feature_metadata,eligible_for_discovery,rating_signal
from recommend import preferred_production_seeds,history_enrichment_ids,enrich_history,load_config
from recommendation_sources import discover
from test_recommendation_pipeline import FakeBackend,movie
from warm_personal_history import warm_profiles


def history():
 return [{'tmdb_id':2100000+i,'impression':'like' if i<10 else 'dislike','plot':9 if i<10 else 1,
          'cinematography':8 if i<10 else 1,'updated_at':'2026-10-01T12:00:00+00:00',
          'metadata':{'title':'Test','year':2020,'genreIds':[27],'companyIds':[101 if i<10 else 102],
                      'castIds':[201 if i<10 else 202],'productionBudget':30000000 if i<10 else 500000,
                      'rating':6.5}} for i in range(40)]


class ProductionTests(unittest.TestCase):
 def test_identical_themes_can_be_ranked_by_personal_production_evidence(self):
  rows=history();current=profile(rows);previous=profile(rows,include_production=False)
  self.assertEqual(current.model_version,'production-aware43');self.assertEqual(previous.model_version,'duration-aware42')
  self.assertAlmostEqual(match_score(rows[0]['metadata'],previous),match_score(rows[-1]['metadata'],previous))
  self.assertGreater(match_score(rows[0]['metadata'],current),match_score(rows[-1]['metadata'],current))
  self.assertEqual(preferred_production_seeds(current,'company'),[101]);self.assertEqual(preferred_production_seeds(current,'cast'),[201])
  self.assertTrue(eligible_for_discovery(rows[-1]['metadata']))
  for row in rows:self.assertLessEqual(abs(production_score(row['metadata'],current.production_model)),2)

 def test_budget_preference_can_run_in_either_direction(self):
  for liked,rejected in [(30000000,500000),(500000,30000000)]:
   rows=history()
   for r in rows:r['metadata']=dict(r['metadata'],companyIds=[1],castIds=[2],productionBudget=liked if r['impression']=='like' else rejected)
   model=fit_production(rows)
   self.assertGreater(production_score(rows[0]['metadata'],model),production_score(rows[-1]['metadata'],model))

 def test_budget_quality_interaction_distinguishes_equal_marginal_preferences(self):
  rows=[]
  for i in range(80):
   budget=1000000 if i%4<2 else 30000000;rating=4. if i%2==0 else 8.
   liked=(i%4 in (0,3));rows.append({'impression':'like' if liked else 'dislike','metadata':{'budget':budget,'rating':rating}})
  model=fit_production(rows)
  self.assertGreater(production_score(rows[0]['metadata'],model),production_score(rows[1]['metadata'],model))
  self.assertGreater(production_score(rows[3]['metadata'],model),production_score(rows[2]['metadata'],model))

 def test_unfilled_history_cannot_create_a_fake_production_preference(self):
  rows=history();baseline=fit_production(rows)
  expanded=fit_production(rows+[{'impression':'dislike','metadata':{}} for _ in range(1000)])
  self.assertEqual(baseline,expanded)
  for movie_data in ({},{'budget':0},{'companyIds':[99999],'castIds':[99999]}):self.assertEqual(production_score(movie_data,baseline),0)
  incomplete=[{'impression':'like' if i<10 else 'dislike','metadata':{'companyIds':[1],**({'budget':30000000} if i<10 else {})}} for i in range(40)]
  model=fit_production(incomplete)
  self.assertAlmostEqual(production_score({'companyIds':[1],'budget':30000000},model),production_score({'companyIds':[1]},model))

 def test_partial_class_coverage_and_missing_metadata_keep_previous_model(self):
  for rows in (history()[:10],history()[10:], [dict(r,metadata={'year':2020,'genreIds':[27]}) for r in history()]):
   self.assertFalse(fit_production(rows)['ready'])
  rows=history()
  for r in rows:r['metadata']['genreIds']=[16]
  self.assertFalse(profile(rows).production_model['ready'])

 def test_canonical_identifiers_only_and_unknown_budget_is_not_zero(self):
  for invalid in (None,False,True,0,-1,'30000000',float('nan'),float('inf')):
   self.assertFalse(any(k[0]=='budget' for k in production_features({'budget':invalid})))
  for invalid in (None,3,False,'studio',{},[{'name':'Unverified'}]):
   self.assertEqual(production_features({'production_companies':invalid,'credits':{'cast':invalid}}),{})
  detail=dict(movie(2100000),budget=0,production_companies=[{'id':101},{'id':101},{'id':True}],credits={'cast':[{'id':201},{'id':201},{'name':'Unverified'}]})
  meta=feature_metadata(detail)
  self.assertEqual(meta['companyIds'],[101]);self.assertEqual(meta['castIds'],[201]);self.assertIsNone(meta['productionBudget']);self.assertTrue(meta['productionChecked'])
  self.assertEqual(production_features(detail),production_features(meta))

 def test_refresh_preserves_opinions_and_dates_and_is_resumable(self):
  backend=FakeBackend();rows=history();original=copy.deepcopy(rows)
  for r in rows:
   for key in ('companyIds','castIds','productionBudget'):r['metadata'].pop(key)
  def lookup(path):
   mid=int(path.split('/')[1].split('?')[0]);like=mid<2100010
   return dict(movie(mid),genres=[{'id':27}],budget=30000000 if like else 500000,production_companies=[{'id':101 if like else 102}],credits={'cast':[{'id':201 if like else 202}]})
  backend.movie=lookup
  self.assertEqual(enrich_history(backend,'test',rows,[],load_config()),40)
  for r,before in zip(rows,original):
   for key in ('plot','cinematography','impression','updated_at'):self.assertEqual(r[key],before[key])
  self.assertEqual(profile(rows).model_version,'production-aware43')
  backend.patched.clear();self.assertEqual(enrich_history(backend,'test',rows,[],load_config()),0);self.assertEqual(backend.patched,[])

 def test_metadata_sampling_covers_likes_and_late_rejections_without_a_prefix_bias(self):
  rows=history()+[dict(history()[-1],tmdb_id=2200000+i) for i in range(100)]
  pending={r['tmdb_id']:[('ratings',r)] for r in rows}
  selected=history_enrichment_ids(pending,20)
  self.assertEqual(len(selected),20);self.assertEqual(len(set(selected)),20)
  self.assertTrue(any(mid<2100010 for mid in selected));self.assertTrue(any(mid>=2200050 for mid in selected))
  self.assertEqual(history_enrichment_ids(pending,0),[])

 def test_new_studio_and_cast_paths_survive_dispatch_and_preserve_budget_and_broad_routes(self):
  backend=Mock();backend.movie.return_value={'results':[movie(2500000)],'total_pages':20}
  cfg=dict(load_config(),discovery_request_limit=24,sources=[{'id':'tmdb','adapter':'tmdb_discover','enabled':True,'pages':3}],
           _now=datetime.datetime(2026,10,13,tzinfo=datetime.timezone.utc),_evidence_routes=True,
           _preferred_companies=[101,102,103,104,105,106],_preferred_cast=[201,202,203,204],
           _preferred_keywords=[1,2,3,4],_preferred_keyword_groups=[[5,6],[7,8],[9,10],[11,12]],_preferred_periods=[2010,2020])
  pool,_=discover(backend,[53,878],cfg)
  queries=[parse_qs(urlsplit(c.args[0]).query) for c in backend.movie.call_args_list]
  self.assertLessEqual(len(queries),24)
  self.assertEqual({q['with_companies'][0] for q in queries if 'with_companies' in q},{'101','102'})
  self.assertTrue(any(q.get('with_cast')==['201'] for q in queries))
  self.assertTrue(all(q.get('with_genres')==['27'] for q in queries if 'with_companies' in q or 'with_cast' in q))
  self.assertTrue(any(q['sort_by']==['popularity.desc'] for q in queries))
  self.assertIn('liked-studio',pool[0]['_personal_routes']);self.assertIn('liked-cast',pool[0]['_personal_routes'])

 def test_warmup_crosses_multiple_batches_without_creating_films_or_changing_schedule(self):
  backend=FakeBackend();backend.ratings=history();backend.movie=lambda path:dict(movie(int(path.split('/')[1].split('?')[0])),production_companies=[{'id':101}],budget=5000000)
  self.assertEqual(warm_profiles(backend,[{'user_id':'test'}],dict(load_config(),history_enrichment_per_run=7)),0)
  self.assertTrue(all(r['metadata'].get('productionChecked') for r in backend.ratings))
  self.assertEqual(backend.collection,[])
  self.assertTrue(all(set(body)=={'metadata'} for body in backend.patched))

 def test_unavailable_history_metadata_is_not_reported_as_a_complete_success(self):
  backend=FakeBackend();backend.ratings=[{'tmdb_id':2100000,'impression':'like','metadata':{'title':'Test'}}]
  backend.movie=lambda path:(_ for _ in ()).throw(RuntimeError('Provider unavailable'))
  before=copy.deepcopy(backend.ratings)
  self.assertEqual(warm_profiles(backend,[{'user_id':'test'}],load_config()),1)
  self.assertEqual(backend.ratings,before);self.assertEqual(backend.patched,[])

 def test_card_feedback_is_interest_not_a_fabricated_technical_review(self):
  r={'impression':'dislike','plot':10,'cinematography':10,'metadata':{'ratingFeedbackStage':'interest'}}
  self.assertEqual(rating_signal(r),-1)
  r['metadata']['ratingFeedbackStage']='watched'
  self.assertGreater(rating_signal(r),-1)

 def test_metadata_refresh_cannot_overwrite_a_newer_card_or_viewed_reaction(self):
  backend=FakeBackend();rows=history()[:1];before=copy.deepcopy(rows)
  backend.movie=lambda path:dict(movie(2100000),budget=5000000,production_companies=[{'id':101}])
  calls=[]
  def db(path,method='GET',body=None,prefer=None):
   calls.append((path,body,prefer));return []
  backend.db=db
  self.assertEqual(enrich_history(backend,'test',rows,[],load_config()),0)
  self.assertIn('updated_at=eq.2026-10-01T12%3A00%3A00%2B00%3A00',calls[0][0])
  self.assertEqual(calls[0][2],'return=representation');self.assertEqual(rows,before)

 def test_bulk_metadata_writes_run_in_a_bounded_parallel_group(self):
  backend=FakeBackend();rows=history()[:8]
  backend.movie=lambda path:dict(movie(int(path.split('/')[1].split('?')[0])),budget=5000000)
  barrier=threading.Barrier(4);lock=threading.Lock();active=peak=0
  def db(path,method='GET',body=None,prefer=None):
   nonlocal active,peak
   with lock:active+=1;peak=max(peak,active)
   try:barrier.wait(timeout=3);return [{'metadata':body['metadata']}]
   finally:
    with lock:active-=1
  backend.db=db
  self.assertEqual(enrich_history(backend,'test',rows,[],dict(load_config(),detail_workers=4)),8)
  self.assertEqual(peak,4)


if __name__=='__main__':unittest.main()
