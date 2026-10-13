import os,unittest,math,copy
from unittest.mock import Mock,patch
from imdb_audience import parse_metrics,validated_imdb_metrics,enrich_audience
from audience_priority import selection_priority_score,confidence_quality,imdb_audience_bonus
from recommend import recommend_user,load_config
from test_recommendation_pipeline import FakeBackend,movie,NOW

def response(identity='tt1234567',**kwargs):return {'Response':'True','Type':'movie','imdbID':identity,'imdbRating':'6.8','imdbVotes':'25,000',**kwargs}

class ImdbAudienceTests(unittest.TestCase):
 def test_large_audience_with_poor_reviews_gets_no_familiarity_bonus(self):
  proof=parse_metrics(response(imdbRating='5.7',imdbVotes='100,000'),'tt1234567')
  self.assertEqual(imdb_audience_bonus({'remoteMetrics':proof}),0)
  good=parse_metrics(response(imdbRating='6.8',imdbVotes='25,000'),'tt1234567')
  self.assertGreater(imdb_audience_bonus({'remoteMetrics':good}),0)

 def test_provider_identity_type_and_complete_numeric_evidence_are_required(self):
  for changes in ({'imdbID':'tt9999999'},{'Type':'series'},{'Response':'False'},{'imdbRating':'N/A'},{'imdbRating':'11.2'},{'imdbVotes':'1,23,456'},{'imdbVotes':'-1'},{'imdbVotes':True},{'imdbVotes':'N/A'}):self.assertIsNone(parse_metrics(response(**changes),'tt1234567'))
  proof=parse_metrics(response(),'tt1234567');self.assertEqual(proof['imdbVoteCount'],25000)
  self.assertEqual(validated_imdb_metrics({'imdb_id':'tt1234567','remoteMetrics':proof}),{'rating':6.8,'votes':25000})
  self.assertIsNone(validated_imdb_metrics({'imdb_id':'tt9999999','remoteMetrics':proof}))
 def test_unverified_rating_and_vote_claims_cannot_affect_selection(self):
  base={'popularity':3,'vote_count':300,'vote_average':6}
  proof=parse_metrics(response(),'tt1234567')
  self.assertGreater(selection_priority_score(dict(base,remoteMetrics=proof)),selection_priority_score(base))
  for changes in ({'imdbVerified':False},{'imdbVoteCount':None},{'imdbId':'bad'},{'imdb':float('nan')}):self.assertEqual(selection_priority_score(dict(base,remoteMetrics={**proof,**changes})),selection_priority_score(base))
 def test_requests_are_bounded_coalesced_and_wrong_entities_never_enriched(self):
  b=Mock();b.request.side_effect=lambda url,headers:response()
  films=[{'id':1,'imdb_id':'tt1234567'},{'id':2,'imdb_id':'tt1234567'},{'id':3,'imdb_id':'unsafe'},{'id':4,'imdb_id':'tt9999999'}]
  with patch.dict(os.environ,{'OMDB_API_KEY':'fake-for-test'}):s=enrich_audience(b,films,1)
  self.assertEqual(s['imdbRequests'],1);self.assertTrue(validated_imdb_metrics(films[0]));self.assertTrue(validated_imdb_metrics(films[1]));self.assertNotIn('remoteMetrics',films[2]);self.assertNotIn('remoteMetrics',films[3])
 def test_optional_provider_failure_retains_the_tmdb_batch_and_stops_early(self):
  b=Mock();b.request.side_effect=RuntimeError('provider unavailable')
  films=[{'id':i,'imdb_id':'tt'+str(1000000+i)}for i in range(80)]
  with patch.dict(os.environ,{'OMDB_API_KEY':'fake-for-test'}):s=enrich_audience(b,films,80)
  self.assertLessEqual(s['imdbRequests'],5);self.assertTrue(all('remoteMetrics'not in m for m in films))
 def test_full_pipeline_can_select_verified_imdb_audiences_while_preserving_true_tmdb_counts(self):
  b=FakeBackend();films=[dict(movie(5000000+i),imdb_id='tt'+str(1000000+i))for i in range(40)]
  b.movie=lambda path:films[int(path.split('/')[1].split('?')[0])-5000000]
  def request(url,headers):
   from urllib.parse import urlsplit,parse_qs
   identity=parse_qs(urlsplit(url).query)['i'][0]
   return response(identity,imdbVotes='25,000'if int(identity[2:])%2 else'1,000')
  b.request=request
  with patch.dict(os.environ,{'OMDB_API_KEY':'fake-for-test'}),patch('recommend.discover',return_value=(films,[])):
   self.assertEqual(recommend_user(b,{'user_id':'test'},NOW,dict(load_config(),history_enrichment_per_run=0),manual=True),30)
  self.assertEqual(b.search_report['selectedImdb10000'],20)
  self.assertTrue(all(row['metadata']['remoteMetrics']['voteCount']==200 for row in b.collection))
  self.assertTrue(all('productionBudget'not in row['metadata']for row in b.collection))

class ImdbEvidenceExpansionTests(unittest.TestCase):
 def test_verified_critics_and_genres_work_without_inventing_missing_audience(self):
  from imdb_audience import validated_critics_score,has_verified_genre
  from audience_priority import critics_bonus
  proof=parse_metrics(response(imdbRating='N/A',imdbVotes='N/A',Metascore='78',Genre='Horror, Mystery',Year='2020'),'tt1234567')
  film={'imdb_id':'tt1234567','remoteMetrics':proof}
  self.assertIsNone(validated_imdb_metrics(film));self.assertEqual(validated_critics_score(film),78)
  self.assertTrue(has_verified_genre(film,'Horror'));self.assertGreater(critics_bonus(film),0)
  for change in ({'imdbVerified':False},{'imdbId':'tt9999999'},{'metascore':'78'},{'metascore':True},{'metascore':101}):
   self.assertEqual(critics_bonus(dict(film,remoteMetrics={**proof,**change})),0)
  for change in ({'Type':'series'},{'imdbID':'tt9999999'}):
   self.assertIsNone(parse_metrics(response(imdbRating='N/A',imdbVotes='N/A',Metascore='99',**change),'tt1234567'))
 def test_explicit_horror_evidence_preserves_all_negative_genres_and_years(self):
  from movie_features import classify,eligible_for_discovery
  from production_policy import production_exclusion
  base=dict(movie(901),genre_ids=[53],genres=[{'id':53}],keywords=[])
  def checked(**kwargs):return dict(base,remoteMetrics=parse_metrics(response(Genre='Horror',Year='2020',**kwargs),'tt1234567'))
  self.assertNotIn('horror',classify(base));self.assertIn('horror',classify(checked()))
  for genre in ('Horror, Comedy','Horror, Documentary','Horror, Animation','Horror, Family','Horror, Adult'):
   film=dict(base,remoteMetrics=parse_metrics(response(Genre=genre,Year='2020'),'tt1234567'))
   self.assertIsNotNone(production_exclusion(film))
  self.assertEqual(production_exclusion(dict(base,remoteMetrics=parse_metrics(response(Genre='Horror',Year='1990'),'tt1234567'))),'imdb_release_year')
  for change in ({'release_date':'1999-01-01'},{'original_language':'ja'},{'production_countries':[{'iso_3166_1':'JP'}]}):
   self.assertFalse(eligible_for_discovery({**checked(),**change}))
 def test_pipeline_recovers_only_explicit_horror_and_never_repeats_history(self):
  from urllib.parse import urlsplit,parse_qs
  b=FakeBackend();base=lambda mid:dict(movie(mid),imdb_id='tt'+str(mid+1000000),genre_ids=[53],genres=[{'id':53}],keywords=[])
  films=[base(901+i)for i in range(40)]+[base(900)]
  b.movie=lambda path:base(int(path.split('/')[1].split('?')[0]))
  b.request=lambda url,headers:response(parse_qs(urlsplit(url).query)['i'][0],Genre='Horror',Year='2020',Metascore='75')
  with patch.dict(os.environ,{'OMDB_API_KEY':'fake-for-test'}),patch('recommend.discover',return_value=(films,[])):
   self.assertEqual(recommend_user(b,{'user_id':'test'},NOW,dict(load_config(),history_enrichment_per_run=0),manual=True),30)
  self.assertEqual(b.search_report['imdbGenreRescued'],40)
  self.assertTrue(all(r['tmdb_id']!=900 and r['metadata']['genreIds']==[53]and r['metadata']['genre']=='Ужасы'for r in b.collection))
  self.assertEqual(b.search_report['selectedCritics70'],30)
 def test_extended_check_reaches_good_later_candidates_and_stops_after_enough(self):
  from urllib.parse import urlsplit,parse_qs
  films=[{'id':i,'imdb_id':'tt'+str(1000000+i)}for i in range(200)]
  b=Mock()
  def request(url,headers):
   identity=parse_qs(urlsplit(url).query)['i'][0];i=int(identity[2:])-1000000
   return response(identity,imdbRating='6.8'if i>=80 else'5.0')
  b.request.side_effect=request
  with patch.dict(os.environ,{'OMDB_API_KEY':'fake-for-test'}):s=enrich_audience(b,films,160,eligible=lambda m:m['id']>=80,good_target=15)
  self.assertEqual(s['imdbRequests'],120);self.assertEqual(s['imdbResolved'],120)
  self.assertTrue(all('remoteMetrics'not in m for m in films[120:]))
 def test_provider_negative_genres_are_not_counted_as_a_successful_search(self):
  from urllib.parse import urlsplit,parse_qs
  from production_policy import production_exclusion
  films=[{'id':i,'genre_ids':[27],'imdb_id':'tt'+str(1000000+i)}for i in range(100)]
  b=Mock();b.request.side_effect=lambda url,headers:response(parse_qs(urlsplit(url).query)['i'][0],Genre='Horror, Comedy')
  with patch.dict(os.environ,{'OMDB_API_KEY':'fake-for-test'}):s=enrich_audience(b,films,100,eligible=lambda m:not production_exclusion(m))
  self.assertEqual(s['imdbRequests'],100)
