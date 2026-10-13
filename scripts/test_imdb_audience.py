import os,unittest,math,copy
from unittest.mock import Mock,patch
from imdb_audience import parse_metrics,validated_imdb_metrics,enrich_audience
from audience_priority import selection_priority_score,confidence_quality
from recommend import recommend_user,load_config
from test_recommendation_pipeline import FakeBackend,movie,NOW

def response(identity='tt1234567',**kwargs):return {'Response':'True','Type':'movie','imdbID':identity,'imdbRating':'6.8','imdbVotes':'25,000',**kwargs}

class ImdbAudienceTests(unittest.TestCase):
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
