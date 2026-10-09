import datetime,json,threading,time,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit,parse_qs
from recommend import Backend,rank_candidates,diverse_candidates,recommend_user,load_config
from movie_features import classify,profile,rating_signal,eligible_for_discovery,match_score
from recommendation_sources import tmdb_candidates,simkl_candidates,trakt_candidates,detail_path
from test_recommendation_pipeline import FakeBackend,movie

ROOT=Path(__file__).resolve().parents[1]
NOW=datetime.datetime(2026,10,9,18,17,tzinfo=datetime.timezone.utc)
class QualityTests(unittest.TestCase):
 def test_common_annotated_category_examples(self):
  for case in json.loads((ROOT/'config/category-checks.json').read_text()):
   with self.subTest(case['name']):self.assertEqual(classify(case['movie']),case['expected'])
 def test_discovery_policy_shared_with_browser(self):
  for case in json.loads((ROOT/'config/discovery-checks.json').read_text()):
   with self.subTest(case['name']):self.assertEqual(eligible_for_discovery(case['movie']),case['expected'])
 def test_rejecting_ghosts_preserves_body_horror_preference(self):
  body={'genreIds':[27],'keywords':['body horror','mutation'],'director':'Body Director'}
  ghost={'genreIds':[27],'keywords':['ghost','haunted house'],'director':'Ghost Director'}
  ratings=[{'impression':'like','plot':10,'cinematography':10,'metadata':body}]+[{'impression':'dislike','plot':1,'cinematography':1,'metadata':ghost} for _ in range(8)]
  taste=profile(ratings)
  self.assertGreater(match_score(body,taste),0);self.assertGreater(match_score(body,taste),match_score(ghost,taste))
 def test_neutral_does_not_dilute_and_all_history_is_used(self):
  movie={'genreIds':[27],'keywords':['body horror']};liked={'metadata':movie,'impression':'like'}
  self.assertEqual(match_score(movie,profile([liked])),match_score(movie,profile([liked]+[dict(liked,impression='neutral')]*100)))
  self.assertEqual(len(profile([liked]*100).anchors),100)
 def test_search_requests_only_modern_films_and_excludes_documentaries(self):
  backend=Mock();backend.movie.return_value={'results':[]}
  tmdb_candidates(backend,[35,28,18,878],{'minimum_votes':100,'pages':2,'_now':NOW})
  for call in backend.movie.call_args_list:
   p=parse_qs(urlsplit(call.args[0]).query)
   self.assertEqual(p['primary_release_date.gte'],['2000-01-01']);self.assertEqual(p['without_genres'],['99,16,10751'])
   if 'with_genres' in p:self.assertIn(p['with_genres'][0],['27','878'])
 def test_pipeline_rechecks_canonical_genres_and_saves_small_valid_batch(self):
  backend=FakeBackend()
  candidates=[dict(movie(901),genre_ids=[27]),dict(movie(902),genre_ids=[27]),dict(movie(903),genre_ids=[27]),dict(movie(904),genre_ids=[18],_discovery_category='dystopian')]
  canonical={901:dict(movie(901),genres=[{'id':27},{'id':18}],genre_ids=[27,18]),902:dict(movie(902),release_date='1999-01-01',genres=[{'id':27}],genre_ids=[27]),903:dict(movie(903),genres=[{'id':27},{'id':99}],genre_ids=[27,99]),904:dict(movie(904),keywords=[],genres=[{'id':18}],genre_ids=[18])}
  backend.movie=lambda path:canonical[int(path.split('/')[1].split('?')[0])]
  with patch('recommend.discover',return_value=(candidates,[])):
   self.assertEqual(recommend_user(backend,{'user_id':'test'},NOW,load_config(),manual=True),1)
  self.assertEqual([r['tmdb_id'] for r in backend.collection],[901])
 def test_manual_search_changes_deeper_pages_with_request_seed(self):
  backend=Mock();backend.movie.return_value={'results':[]}
  config={'minimum_votes':100,'pages':3,'_now':NOW}
  tmdb_candidates(backend,[],dict(config,_page_seed=1));first={parse_qs(urlsplit(c.args[0]).query)['page'][0] for c in backend.movie.call_args_list}
  backend.reset_mock();tmdb_candidates(backend,[],dict(config,_page_seed=2));second={parse_qs(urlsplit(c.args[0]).query)['page'][0] for c in backend.movie.call_args_list}
  self.assertNotEqual(first,second)
 def test_all_canonically_excluded_is_empty_success_not_network_error(self):
  backend=FakeBackend();backend.movie=lambda path:dict(movie(901),genres=[{'id':27},{'id':99}],genre_ids=[27,99])
  with patch('recommend.discover',return_value=([dict(movie(901),genre_ids=[27])],[])):
   self.assertEqual(recommend_user(backend,{'user_id':'test'},NOW,load_config(),manual=True),0)
  self.assertEqual(backend.collection,[])
 def test_theme_preference_breaks_same_genre_tie(self):
  ratings=[{'tmdb_id':800,'impression':'like','metadata':{'genreIds':[27],'keywords':['body horror']}}]
  body=dict(movie(901),genres=[{'id':27}],genre_ids=[27],keywords={'keywords':[{'id':1,'name':'body horror'}]})
  ghost=dict(movie(902),genres=[{'id':27}],genre_ids=[27],keywords={'keywords':[{'id':2,'name':'ghost'}]})
  self.assertEqual(rank_candidates([ghost,body],ratings,[],now=NOW)[0][1]['id'],901)
 def test_negative_impression_is_not_reversed_by_high_technical_scores(self):
  self.assertLess(rating_signal({'impression':'dislike','plot':10,'cinematography':10}),0)
 def test_quality_is_confidence_adjusted_and_bad_numbers_are_rejected(self):
  flimsy=dict(movie(901),vote_count=100,vote_average=9)
  reliable=dict(movie(902),vote_count=20000,vote_average=8)
  invalid=dict(movie(903),vote_average=float('nan'))
  self.assertEqual([r[1]['id'] for r in rank_candidates([flimsy,reliable,invalid],[],[],now=NOW)],[902,901])
 def test_diversity_breaks_quality_ties_without_overriding_strong_taste(self):
  entries=[(8,movie(901),''),(3,movie(902),''),(3,dict(movie(903),genre_ids=[35],genres=[{'id':35}]),'')]
  result=diverse_candidates(entries)
  self.assertEqual([e[1]['id'] for e in result],[901,903,902])
 def test_rotating_search_separates_genres_and_is_bounded(self):
  backend=Mock();backend.movie.return_value={'results':[movie(901)]}
  config={'minimum_votes':100,'pages':3,'_now':NOW,'_preferred_keywords':[123]}
  tmdb_candidates(backend,[27,878],config)
  params=[parse_qs(urlsplit(call.args[0]).query) for call in backend.movie.call_args_list]
  self.assertLessEqual(len(params),24)
  self.assertIn({'27','878'},[set(p['with_genres'][0] for p in params if 'with_genres' in p)])
  self.assertTrue(any(p['sort_by']==['vote_average.desc'] for p in params))
  self.assertTrue(any(p.get('with_keywords')==['123'] for p in params))
  first_pages={p['page'][0] for p in params}
  backend.reset_mock();tmdb_candidates(backend,[],dict(config,_now=NOW+datetime.timedelta(hours=1)))
  next_pages={parse_qs(urlsplit(call.args[0]).query)['page'][0] for call in backend.movie.call_args_list}
  self.assertNotEqual(first_pages,next_pages);self.assertIn('1',next_pages)
 def test_partial_tmdb_page_failure_preserves_other_pages(self):
  backend=Mock();backend.movie.side_effect=lambda p:(_ for _ in ()).throw(RuntimeError()) if 'vote_average.desc' in p else {'results':[movie(901)]}
  self.assertTrue(tmdb_candidates(backend,[],{'minimum_votes':100,'pages':2,'_now':NOW}))
 def test_collected_external_films_are_skipped_before_detail_requests(self):
  backend=Mock();backend.request.return_value=[{'ids':{'tmdb':901}}]
  self.assertEqual(simkl_candidates(backend,[],{'_excluded_ids':{901}}),[])
  with patch.dict('os.environ',{'TRAKT_CLIENT_ID':'fake'}):self.assertEqual(trakt_candidates(backend,[],{'_excluded_ids':{901}}),[])
  backend.movie.assert_not_called()
 def backend(self):
  with patch.dict('os.environ',{'SUPABASE_URL':'https://project.example','SUPABASE_SERVICE_ROLE_KEY':'sb_secret_fake','TMDB_ACCESS_TOKEN':'fake'}):return Backend()
 def test_shared_details_are_requested_once_even_concurrently_and_not_mutated(self):
  backend=self.backend()
  def request(*_):time.sleep(.01);return {'id':901,'genres':[{'id':27}]}
  with patch.object(backend,'request',side_effect=request) as network:
   with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(backend.movie,[detail_path(901)]*8))
   self.assertEqual(network.call_count,1)
   results[0]['genres'][0]['id']=35
   self.assertEqual(backend.movie(detail_path(901))['genres'][0]['id'],27)
 def test_failed_cache_entry_can_retry(self):
  backend=self.backend()
  with patch.object(backend,'request',side_effect=[RuntimeError(),{'id':901}]):
   with self.assertRaises(RuntimeError):backend.movie(detail_path(901))
   self.assertEqual(backend.movie(detail_path(901))['id'],901)
 def test_parallel_enrichment_is_bounded_and_saves_category_keyword_and_director(self):
  backend=FakeBackend();active=0;peak=0;lock=threading.Lock()
  def lookup(path):
   nonlocal active,peak
   with lock:active+=1;peak=max(peak,active)
   try:
    time.sleep(.005)
    mid=int(path.split('/')[1].split('?')[0])
    return dict(movie(mid),genres=[{'id':27}],keywords={'keywords':[{'id':12,'name':'body horror'}]},credits={'crew':[{'job':'Director','name':'Test Director'}]})
   finally:
    with lock:active-=1
  backend.movie=lookup
  config=load_config();candidates=[dict(movie(901+i),discovery_sources=['tmdb']) for i in range(20)]
  with patch('recommend.discover',return_value=(candidates,[])):
   self.assertEqual(recommend_user(backend,{'user_id':'test'},NOW,config),15)
  self.assertGreater(peak,1);self.assertLessEqual(peak,4)
  meta=backend.collection[0]['metadata'];self.assertEqual(meta['moods'],['horror','body-horror'])
  self.assertEqual(meta['keywordIds'],[12]);self.assertEqual(meta['director'],'Test Director')
 def test_metadata_outage_does_not_mark_hour_completed(self):
  backend=FakeBackend();backend.movie=Mock(side_effect=RuntimeError())
  with patch('recommend.discover',return_value=([movie(901)],[])),self.assertRaises(RuntimeError):recommend_user(backend,{'user_id':'test'},NOW,load_config())
  self.assertEqual(backend.patched,[])
 def test_history_enrichment_preserves_user_fields_and_is_resumable(self):
  from recommend import enrich_history
  backend=Mock();backend.movie.side_effect=lambda path:dict(movie(int(path.split('/')[1].split('?')[0])),keywords={'keywords':[{'id':12,'name':'body horror'}]})
  rows=[{'tmdb_id':1000+i,'saved':True,'created_at':'2020-01-01','metadata':{'id':10001000+i,'tmdbId':1000+i,'title':'Old film','director':'Manual Director'}} for i in range(15)]
  enrich_history(backend,'test',[],rows,dict(load_config(),history_enrichment_per_run=12))
  self.assertEqual(backend.movie.call_count,12);self.assertEqual(backend.db.call_count,12)
  for call in backend.db.call_args_list:self.assertEqual(set(call.args[2]),{'metadata'})
  self.assertEqual(rows[0]['saved'],True);self.assertEqual(rows[0]['created_at'],'2020-01-01')
  self.assertEqual(rows[0]['metadata']['director'],'Manual Director');self.assertEqual(rows[0]['metadata']['featureVersion'],2)
  backend.reset_mock();enrich_history(backend,'test',[],rows,dict(load_config(),history_enrichment_per_run=12))
  self.assertEqual(backend.movie.call_count,3)
 def test_history_enrichment_failure_keeps_original_metadata(self):
  from recommend import enrich_history
  backend=Mock();backend.movie.side_effect=RuntimeError()
  rows=[{'tmdb_id':1000,'metadata':{'title':'Old film'}}]
  enrich_history(backend,'test',[],rows,dict(load_config(),history_enrichment_per_run=12))
  self.assertEqual(rows[0]['metadata'],{'title':'Old film'});backend.db.assert_not_called()
