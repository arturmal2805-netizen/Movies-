"""Independent audience evidence must survive retrieval, ranking and saving."""
import copy,datetime,math,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from candidate_policy import valid_candidate
from imdb_audience import parse_metrics
from imdb_datasets import PublicImdbIndex
from recommendation_sources import imdb_dataset_candidates
from recommend import recommend_user,load_config
from test_imdb_audience import response
from test_imdb_datasets import fixture
from test_recommendation_pipeline import FakeBackend,movie,NOW

class IndependentAudienceAdmissionTests(unittest.TestCase):
 def film(self,mid=5000000,**changes):
  base=dict(movie(mid),genre_ids=[27],genres=[{'id':27}],vote_count=20,imdb_id='tt1234567',remoteMetrics=parse_metrics(response(imdbRating='7.1',imdbVotes='50,000'),'tt1234567'))
  return {**base,**changes}
 def test_verified_large_well_reviewed_audience_covers_sparse_tmdb_without_fabricating_counts(self):
  for count in (0,1,20,99,100):
   film=self.film(vote_count=count)
   self.assertTrue(valid_candidate(film,100,NOW.date()))
   self.assertEqual(film['vote_count'],count);self.assertEqual(film['remoteMetrics']['imdbVoteCount'],50000)
 def test_unknown_mismatched_low_quality_or_small_audience_does_not_override_the_floor(self):
  for changes in ({'imdbVerified':False},{'imdbId':'tt9999999'},{'imdb':6.4},{'imdbVoteCount':9999},{'imdb':None},{'imdbVoteCount':math.inf}):
   film=self.film();film['remoteMetrics'].update(changes)
   self.assertFalse(valid_candidate(film,100,NOW.date()))
   film['vote_count']=100;self.assertTrue(valid_candidate(film,100,NOW.date()))
  self.assertFalse(valid_candidate(self.film(remoteMetrics={}),100,NOW.date()))
 def test_all_content_identity_release_and_numeric_guards_survive_the_alternative_proof(self):
  for change in ({'id':0},{'adult':True},{'poster_path':None},{'release_date':'1999-12-31'},
                 {'release_date':(NOW.date()+datetime.timedelta(days=1)).isoformat()},
                 {'original_language':'ja'},{'production_countries':[{'iso_3166_1':'IN'}]},
                 {'genres':[{'id':27},{'id':35}],'genre_ids':[27,35]},
                 {'genres':[{'id':99}],'genre_ids':[99]},
                 {'vote_count':-1},{'vote_count':True},{'vote_count':math.nan},{'vote_count':None},{'popularity':math.inf}):
   with self.subTest(change=change):self.assertFalse(valid_candidate(self.film(**change),100,NOW.date()))
 def test_retrieval_pipeline_selects_thirty_new_known_films_instead_of_zero(self):
  with tempfile.TemporaryDirectory()as temp:
   index=fixture(Path(temp)/'public.db',40);b=FakeBackend();b.imdb_index=index
   def api(path):
    if path.startswith('find/'):
     identity=path.split('/')[1].split('?')[0];return {'movie_results':[{'id':5000000+int(identity[2:])-1000000}]}
    mid=int(path.split('/')[1].split('?')[0]);return dict(movie(mid),genre_ids=[27],genres=[{'id':27}],imdb_id='tt'+str(1000000+mid-5000000),vote_count=20)
   b.movie=api
   b.ratings.append({'tmdb_id':5000000,'impression':'dislike','metadata':{}})
   b.collection.append({'tmdb_id':5000001,'metadata':{}})
   config=dict(load_config(),sources=[{'id':'tmdb','adapter':'tmdb_discover','enabled':True,'pages':3},{'id':'imdb','adapter':'imdb_dataset','enabled':True,'candidate_limit':40,'resolution_limit':40}],history_enrichment_per_run=0)
   coarse=[dict(movie(5000000+i),vote_count=20,genre_ids=[53],genres=[],keywords=[])for i in range(40)]
   with patch.dict('os.environ',{},clear=True),patch.dict('recommendation_sources.ADAPTERS',{'tmdb_discover':lambda *_:coarse}):self.assertEqual(recommend_user(b,{'user_id':'test'},NOW,config,manual=True),30)
   saved=b.collection[1:]
   self.assertEqual(len(saved),30);self.assertEqual(len({row['tmdb_id']for row in saved}),30)
   self.assertTrue(all(row['tmdb_id']not in(5000000,5000001)for row in saved))
   self.assertTrue(all(row['metadata']['remoteMetrics']['voteCount']==20 and row['metadata']['remoteMetrics']['imdbVoteCount']>=30000 for row in saved))
   self.assertEqual(b.search_report['selectedEstablishedGood'],30)

 def test_popularity_changes_order_without_a_new_quality_veto(self):
  from audience_priority import public_recognition_bonus,selection_priority_score,selection_priority_score56
  small=dict(movie(1),vote_count=100,vote_average=6.8)
  known=dict(small,id=2,vote_count=5000)
  self.assertGreater(public_recognition_bonus(known),public_recognition_bonus(small))
  self.assertGreater(selection_priority_score(known)-selection_priority_score56(known),selection_priority_score(small)-selection_priority_score56(small))
  self.assertEqual(public_recognition_bonus(dict(small,vote_average=6)),0)
  self.assertEqual(public_recognition_bonus({}),0)
  for key,value in [('vote_count',True),('vote_count',math.inf),('vote_average',math.nan)]:self.assertEqual(public_recognition_bonus({**small,key:value}),0)

 def test_release_comparison_keeps_held_out_ratings_out_of_training(self):
  import release_validation
  from movie_features import profile as actual_profile,match_score as actual_match
  rows=[{'tmdb_id':5000000+i,'impression':'like'if i%5==0 else'neutral'if i%4==0 else'dislike','metadata':self.film(5000000+i,vote_count=200+i*20),'updated_at':'2026-10-14T12:00:00Z'}for i in range(100)]
  trained={}
  def train(data):
   model=actual_profile(data);trained[id(model)]={row['tmdb_id']for row in data};return model
  def score(movie,model):
   self.assertNotIn(movie['id'],trained[id(model)]);return actual_match(movie,model)
  with patch('release_validation.profile',side_effect=train),patch('release_validation.match_score',side_effect=score):report=release_validation.compare_release(rows)
  self.assertEqual(report['tested'],100);self.assertEqual(report['positives'],20);self.assertEqual(report['folds'],5)
  self.assertEqual(set(report['variants']),{'0','3','6'})
  text=str(report)
  for row in rows:self.assertNotIn(str(row['tmdb_id']),text)

 def test_coarse_first_source_cannot_erase_later_canonical_audience_or_leave_stale_genres(self):
  from recommendation_sources import discover
  film=self.film();del film['genre_ids']
  coarse=dict(movie(film['id']),genre_ids=[35],genres=[],vote_count=20,_liked_anchor_ids=[100])
  config=dict(load_config(),sources=[{'id':'coarse','adapter':'coarse','enabled':True},{'id':'canonical','adapter':'canonical','enabled':True},{'id':'last','adapter':'last','enabled':True}])
  adapters={'coarse':lambda *_:[coarse],'canonical':lambda *_:[film],'last':lambda *_:[coarse]}
  with patch.dict('recommendation_sources.ADAPTERS',adapters):found,statuses=discover(FakeBackend(),[],config)
  self.assertEqual(len(found),1);self.assertEqual(found[0]['remoteMetrics']['imdbVoteCount'],50000)
  self.assertNotIn('genre_ids',found[0]);self.assertEqual(found[0]['genres'],[{'id':27}])
  self.assertEqual(found[0]['_liked_anchor_ids'],[100]);self.assertEqual(found[0]['discovery_sources'],['coarse','canonical','last'])
  self.assertTrue(valid_candidate(found[0],100,NOW.date()))
