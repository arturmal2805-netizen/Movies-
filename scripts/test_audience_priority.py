"""Regression checks for audience priority and the three-film search bottleneck."""
import datetime,math,unittest
from unittest.mock import Mock,patch
from urllib.parse import parse_qs,urlsplit
from audience_priority import audience_score,audience_priority_score,audience_first_score,public_quality_score
from recommendation_sources import tmdb_candidates
from recommend import recommend_user,load_config,rank_candidates,audience_diagnostics,diverse_candidates
from movie_features import profile
from test_recommendation_pipeline import FakeBackend,movie
NOW=datetime.datetime(2026,10,13,18,30,tzinfo=datetime.timezone.utc)
def horror(mid,**kwargs):return dict(movie(mid),genre_ids=[27],genres=[{'id':27}],**kwargs)

class AudiencePriorityTests(unittest.TestCase):
 def test_strict_public_order_cannot_be_overridden_by_personal_or_route_bonuses(self):
  low=dict(horror(2501001),popularity=2,vote_count=100,_liked_directors=['A director'],_matched_theme_groups=['1,2'])
  high=dict(horror(2501002),popularity=30,vote_count=5000)
  with patch('recommend.match_score',side_effect=lambda m,t:100 if m['id']==low['id'] else -100):
   for preliminary in (False,True):
    ranked=rank_candidates([low,high],[],[],now=NOW,preliminary=preliminary)
    self.assertEqual([r[1]['id'] for r in ranked],[high['id'],low['id']])
    self.assertEqual(diverse_candidates(ranked,strict_audience=True),ranked)
 def test_personal_preferences_break_equal_public_audience_ties(self):
  low=horror(2501001);high=horror(2501002)
  with patch('recommend.match_score',side_effect=lambda m,t:-3 if m['id']==low['id'] else 3):
   self.assertEqual(rank_candidates([low,high],[],[],now=NOW)[0][1]['id'],high['id'])
 def test_public_first_score_has_no_saturation_and_invalid_numbers_are_neutral(self):
  a={'popularity':40,'vote_count':20000};b={'popularity':400,'vote_count':200000}
  self.assertGreater(audience_first_score(b),audience_first_score(a))
  self.assertTrue(math.isfinite(audience_first_score({'popularity':1e308,'vote_count':1e308})))
  for value in (None,0,-1,True,'100',float('nan'),float('inf')):
   self.assertEqual(audience_first_score({'popularity':value,'vote_count':value}),0)
 def test_pool_diagnostics_distinguish_proposed_and_available_audiences(self):
  a=dict(horror(2501001),popularity=2,vote_count=100)
  b=dict(horror(2501002),popularity=20,vote_count=5000)
  result=audience_diagnostics([(10,a,''),(9,b,'')],1,True)
  self.assertEqual(result['recommendationProposedVoteMedian'],100)
  self.assertEqual(result['recommendationAudiencePoolVoteMedian'],5000)
  self.assertTrue(all(value is None for value in audience_diagnostics([],30).values()))
 def test_previous_audience_version_is_frozen_and_new_votes_have_seven_times_the_weight(self):
  m={'popularity':20,'vote_count':5000,'vote_average':7}
  expected=.4*math.log2(21/9)+.1*math.log2(5500/1500)+.006*.5*5000/5500
  self.assertAlmostEqual(audience_priority_score(m,True,legacy=True),expected)
  a={'popularity':8,'vote_count':400};b=dict(a,vote_count=4000)
  old=audience_score(b,legacy=True)-audience_score(a,legacy=True)
  self.assertAlmostEqual(audience_score(b)-audience_score(a),old*7)
 def test_popular_audience_can_override_a_weak_niche_keyword_advantage(self):
  niche=dict(horror(2501001),popularity=2,vote_count=100,vote_average=5.5)
  public=dict(horror(2501002),popularity=20,vote_count=5000,vote_average=7)
  # Previously the niche film's weak thematic advantage overcame its tiny audience.
  self.assertGreater(1.6+audience_priority_score(niche,True,legacy=True),.1+audience_priority_score(public,True,legacy=True))
  with patch('recommend.match_score',side_effect=lambda m,t:1.6 if m['id']==niche['id'] else .1):
   self.assertEqual(rank_candidates([niche,public],[],[],now=NOW)[0][1]['id'],public['id'])
 def test_headline_popularity_and_vote_lists_own_most_of_the_deeper_broad_requests(self):
  backend=Mock();backend.movie.return_value={'results':[],'total_pages':500}
  cfg=dict(load_config(),_now=NOW,_evidence_routes=True,_preferred_keywords=list(range(100,112)),
           _preferred_keyword_groups=[[201,202],[203,204],[205,206],[207,208]],_preferred_periods=[2010,2020],
           _discovery_pages={},_discovery_totals={})
  for i in range(3):tmdb_candidates(backend,[53,878],dict(cfg,_search_round=i))
  queries=[parse_qs(urlsplit(c.args[0]).query) for c in backend.movie.call_args_list]
  deep=[q for q in queries if q['page']!=['1'] and 'with_companies' not in q and 'with_cast' not in q]
  headline=[q for q in deep if q['sort_by'][0] in ('popularity.desc','vote_count.desc') and
            q['primary_release_date.gte']==['2000-01-01'] and q['primary_release_date.lte']==[NOW.date().isoformat()] and
            ((q.get('with_genres')==['27'] and 'with_keywords' not in q) or
             (q.get('with_keywords') in (['4565'],['4458']) and 'with_genres' not in q))]
  self.assertGreater(len(headline),len(deep)*.4)
  self.assertTrue(any(q.get('with_keywords')==['201,202'] for q in queries))
  self.assertEqual(len(queries),192)
 def test_public_popularity_breaks_close_personal_ties(self):
  rows=[{'tmdb_id':900000+i,'impression':'like' if i<8 else 'dislike','metadata':{'genreIds':[27],'year':2020,'keywords':['body horror' if i<8 else 'ghost']}} for i in range(40)]
  obscure=horror(2500001);popular=dict(obscure,id=2500002,popularity=30)
  obscure['popularity']=2
  with patch('recommend.match_score',return_value=.5):
   ordered=rank_candidates([obscure,popular],rows,[],now=NOW,tastes=profile(rows))
  self.assertEqual(ordered[0][1]['id'],2500002)
  self.assertGreater(ordered[0][0]-ordered[1][0],3)
 def test_strict_audience_order_precedes_personal_advantage_for_admissible_films(self):
  a=horror(2500001);b=dict(a,id=2500002,popularity=1000000)
  with patch('recommend.match_score',side_effect=lambda m,t:2 if m['id']==a['id'] else -2):
   self.assertEqual(rank_candidates([b,a],[],[],now=NOW)[0][1]['id'],b['id'])
 def test_votes_are_soft_and_missing_numbers_are_neutral(self):
  self.assertGreater(audience_score({'vote_count':20000}),audience_score({'vote_count':200}))
  for value in (None,0,-1,float('nan'),float('inf'),True,'100'):
   self.assertEqual(audience_score({'popularity':value,'vote_count':value}),0)
  self.assertEqual(audience_score({'remoteMetrics':{'popularity':30,'voteCount':2000}}),audience_score({'popularity':30,'vote_count':2000}))
  self.assertLessEqual(audience_priority_score({'popularity':1e300,'vote_count':1e300}),3)
 def test_null_top_level_uses_remote_data_and_quality_is_overflow_safe(self):
  self.assertEqual(audience_score({'popularity':None,'vote_count':None,'remoteMetrics':{'popularity':30,'voteCount':2000}}),audience_score({'popularity':30,'vote_count':2000}))
  self.assertEqual(audience_score({'remoteMetrics':[]}),0)
  self.assertTrue(math.isfinite(public_quality_score({'vote_average':10,'vote_count':1e308})))
  self.assertGreater(public_quality_score({'vote_average':8,'vote_count':20000}),public_quality_score({'vote_average':9,'vote_count':100}))
 def test_popularity_cannot_bypass_policy_or_drop_small_valid_batches(self):
  good=horror(2500001);bad=dict(good,id=2500002,release_date='1999-01-01',popularity=1000000)
  self.assertEqual([r[1]['id'] for r in rank_candidates([good,bad],[],[],now=NOW)],[good['id']])
 def test_refills_use_every_request_on_new_pages_even_with_many_narrow_routes(self):
  backend=Mock();backend.movie.return_value={'results':[],'total_pages':120}
  cfg=dict(load_config(),_now=NOW,_evidence_routes=True,_preferred_keywords=list(range(100,112)),
           _preferred_keyword_groups=[[201,202],[203,204],[205,206],[207,208]],_preferred_periods=[2010,2020],
           _preferred_companies=[101,102,103,104,105,106],_preferred_cast=[701,702,703,704],
           _discovery_pages={},_discovery_totals={},_discovery_stats={})
  for i in range(3):
   before=len(backend.movie.call_args_list)
   tmdb_candidates(backend,[53,878],dict(cfg,_search_round=i))
   self.assertEqual(len(backend.movie.call_args_list)-before,64)
  paths=[c.args[0] for c in backend.movie.call_args_list]
  self.assertEqual(len(paths),len(set(paths)))
  broad=[parse_qs(urlsplit(p).query) for p in paths if 'with_keywords' not in parse_qs(urlsplit(p).query) and 'with_companies' not in p and 'with_cast' not in p]
  self.assertTrue(any(q['sort_by']==['popularity.desc'] and int(q['page'][0])>=8 for q in broad))
  self.assertEqual(cfg['_discovery_stats']['requests'],192)
 def test_failed_pages_retry_next_pass_and_short_lists_return_unused_budget(self):
  backend=Mock();failed=False
  def lookup(path):
   nonlocal failed
   q=parse_qs(urlsplit(path).query)
   if q['sort_by']==['popularity.desc'] and q.get('with_genres')==['27']:
    if q['page']==['2'] and not failed:failed=True;raise RuntimeError('temporary')
    return {'results':[],'total_pages':100}
   return {'results':[],'total_pages':1}
  backend.movie.side_effect=lookup
  cfg={'minimum_votes':100,'pages':3,'discovery_request_limit':24,'_now':NOW,'_discovery_pages':{},'_discovery_totals':{}}
  tmdb_candidates(backend,[],cfg);tmdb_candidates(backend,[],dict(cfg,_search_round=1))
  page2=[c for c in backend.movie.call_args_list if parse_qs(urlsplit(c.args[0]).query).get('with_genres')==['27'] and parse_qs(urlsplit(c.args[0]).query)['sort_by']==['popularity.desc'] and parse_qs(urlsplit(c.args[0]).query)['page']==['2']]
  self.assertEqual(len(page2),2)
 def test_manual_pipeline_rescues_three_to_thirty_from_popular_head_pages(self):
  backend=FakeBackend();backend.ratings=[{'tmdb_id':900000+i,'impression':'like' if i<8 else 'dislike','metadata':{'genreIds':[27],'year':2020,'keywords':['body horror' if i<8 else 'ghost']}} for i in range(40)]
  known=[horror(2500000+i) for i in range(400)]
  backend.collection=[{'tmdb_id':m['id']} for m in known]
  fresh=[horror(2600000+i) for i in range(3)]
  better=[dict(horror(2700000+i),popularity=30,keywords=['body horror']) for i in range(60)]
  all_movies={m['id']:m for m in known+fresh+better}
  def lookup(path):
   if path.startswith('discover/'):
    q=parse_qs(urlsplit(path).query);page=int(q['page'][0])
    if q.get('with_genres')==['27'] and q['sort_by']==['popularity.desc'] and 'with_keywords' not in q:
     rows=known[(page-1)*20:page*20] if page<21 else better[(page-21)*20:(page-20)*20]
     return {'results':rows+fresh if page==1 else rows,'total_pages':23}
    return {'results':known[:20]+fresh,'total_pages':1}
   if '/recommendations?' in path or '/similar?' in path:return {'results':[]}
   return all_movies[int(path.split('/')[1].split('?')[0])]
  backend.movie=lookup
  cfg=dict(load_config(),history_enrichment_per_run=0,manual_quality_pool=60,
           sources=[{'id':'tmdb','adapter':'tmdb_discover','enabled':True,'pages':3}])
  with patch('recommend.preferred_keyword_seeds',return_value=list(range(100,112))),patch('recommend.preferred_keyword_groups',return_value=[[201,202],[203,204],[205,206],[207,208]]),patch('recommend.preferred_periods',return_value=[2010,2020]),patch('recommend.preferred_production_seeds',side_effect=lambda t,kind,**k:[101,102,103,104,105,106] if kind=='company' else [701,702,703,704]):
   self.assertEqual(recommend_user(backend,{'user_id':'test'},NOW,cfg,manual=True),30)
  saved=backend.collection[400:]
  self.assertTrue(all(r['tmdb_id']>=2700000 for r in saved))
  self.assertTrue(all(r['metadata']['recommendationAudienceScore']>0 for r in saved))
  self.assertTrue(all(r['metadata']['recommendationDiscoveryRequests']<=cfg['discovery_request_limit']*cfg['search_rounds'] for r in saved))
  self.assertEqual(len(set(r['tmdb_id'] for r in saved)),30)
 def test_refill_failure_does_not_finish_an_empty_scheduled_hour(self):
  backend=FakeBackend()
  with patch('recommend.discover',side_effect=[([],[{'source':'tmdb','status':'ok'}]),([],[{'source':'tmdb','status':'failed'}])]):
   with self.assertRaisesRegex(RuntimeError,'Search incomplete'):
    recommend_user(backend,{'user_id':'test'},NOW,load_config())
  self.assertEqual(backend.patched,[])
 def test_invalid_request_limit_is_rejected(self):
  with patch('recommend.json.loads',return_value=dict(load_config(),discovery_request_limit=500)):
   with self.assertRaisesRegex(ValueError,'Discovery request limit'):load_config()

if __name__=='__main__':unittest.main()
