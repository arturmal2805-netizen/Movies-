import datetime,gzip,io,json,os,sqlite3,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from imdb_datasets import PublicImdbIndex,build_index,prepare,BoundedLines
from imdb_audience import validated_imdb_metrics,enrich_audience
from recommendation_sources import imdb_dataset_candidates,discover
from recommend import load_config,recommend_user
from test_recommendation_pipeline import FakeBackend,movie,NOW

RHEADER='tconst\taverageRating\tnumVotes\n'
BHEADER='tconst\ttitleType\tprimaryTitle\toriginalTitle\tisAdult\tstartYear\tendYear\truntimeMinutes\tgenres\n'

def fixture(path,count=40,changes=None):
 ratings=[RHEADER];basics=[BHEADER]
 for i in range(count):
  identity='tt'+str(1000000+i);r={'rating':7.1,'votes':30000+i,'kind':'movie','adult':0,'year':2020,'genres':'Horror,Thriller'}
  if changes and i in changes:r.update(changes[i])
  ratings.append(f"{identity}\t{r['rating']}\t{r['votes']}\n")
  basics.append(f"{identity}\t{r['kind']}\tPublic title\tPublic title\t{r['adult']}\t{r['year']}\t\\N\t100\t{r['genres']}\n")
 build_index(path,ratings,basics,minimum_ratings=0)
 return PublicImdbIndex(path)

class ImdbDatasetTests(unittest.TestCase):
 def setUp(self):self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'public.db'
 def tearDown(self):self.temp.cleanup()
 def test_exact_dataset_id_movie_type_and_independent_audience_counts(self):
  index=fixture(self.path,4,{1:{'kind':'tvSeries'},2:{'genres':'Horror,Comedy'},3:{'adult':1}})
  films=[{'id':901+i,'imdb_id':'tt'+str(1000000+i),'vote_count':120}for i in range(4)]
  self.assertEqual(index.enrich(films),3);self.assertNotIn('remoteMetrics',films[1])
  self.assertEqual(validated_imdb_metrics(films[0]),{'rating':7.1,'votes':30000});self.assertEqual(films[0]['vote_count'],120)
  self.assertEqual([r[0]for r in index.candidates(2000,NOW.year)],['tt1000000'])
  index.record_mapping('tt1000000',901)
  with sqlite3.connect(self.path)as c:self.assertEqual({r[0]for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")},{'audience','films','metadata'})
 def test_truncated_bad_or_corrupt_refresh_preserves_old_index(self):
  index=fixture(self.path,1);before=self.path.read_bytes()
  for ratings,basics in [(['invalid\n'],[BHEADER]),([RHEADER,'tt1000000\t7.1\t30000\n'],['invalid\n'])]:
   with self.assertRaises(ValueError):build_index(self.path,ratings,basics,minimum_ratings=0)
   self.assertEqual(self.path.read_bytes(),before)
  corrupt=gzip.compress((RHEADER+'tt1000000\t7.1\t30000\n').encode())[:-5]
  with self.assertRaises((EOFError,OSError)):build_index(self.path,BoundedLines(io.BytesIO(corrupt)),[BHEADER],minimum_ratings=0)
  self.assertEqual(self.path.read_bytes(),before);self.assertEqual(index.lookup(['tt1000000'])['tt1000000']['imdbVoteCount'],30000)
 def test_stale_future_and_wrong_schema_indices_are_not_trusted(self):
  index=fixture(self.path,1)
  for stamp in [(NOW-datetime.timedelta(days=8)).isoformat(),(NOW+datetime.timedelta(days=2)).isoformat(),'invalid']:
   with sqlite3.connect(self.path)as c:c.execute("UPDATE metadata SET value=? WHERE key='updated'",(stamp,))
   self.assertIsNone(index.metadata());self.assertEqual(index.lookup(['tt1000000']),{})
 def test_daily_cache_reuses_public_data_without_http_or_private_context(self):
  fixture(self.path,1)
  with patch('imdb_datasets.urllib.request.urlopen',side_effect=AssertionError('No download needed')):self.assertTrue(prepare(self.path)['cached'])
  index=PublicImdbIndex(self.path);self.assertEqual(index.mapping(['tt1000000']),{})
 def test_genre_filters_are_applied_before_the_candidate_limit(self):
  index=fixture(self.path,40,{i:{'genres':'Drama','votes':1000000}for i in range(39)})
  self.assertEqual([r[0]for r in index.candidates(2000,NOW.year,limit=1)],['tt1000039'])
 def test_complete_source_restores_horror_only_after_canonical_id_and_all_guards(self):
  index=fixture(self.path,8)
  b=FakeBackend();b.imdb_index=index
  def api(path):
   if path.startswith('find/'):
    identity=path.split('/')[1].split('?')[0];return {'movie_results':[{'id':901+int(identity[2:])-1000000}]}
   mid=int(path.split('/')[1].split('?')[0]);i=mid-901
   film=dict(movie(mid),imdb_id='tt'+str(1000000+i),genre_ids=[53],genres=[{'id':53}],keywords=[])
   if i==1:film['imdb_id']='tt9999999'
   if i==2:film['original_language']='ja'
   if i==3:film['production_countries']=[{'iso_3166_1':'IN'}]
   if i==4:film['release_date']='1999-01-01'
   if i==5:film['genres']=[{'id':99}];film['genre_ids']=[99]
   if i==6:film['genres']=[{'id':27},{'id':35}];film['genre_ids']=[27,35]
   return film
  b.movie=api
  config={'_excluded_ids':{908},'_now':NOW,'candidate_limit':40,'resolution_limit':40,'discovery_workers':4}
  found=imdb_dataset_candidates(b,[],config);self.assertEqual([m['id']for m in found],[901])
  with patch('recommend.discover',return_value=(found,[])),patch.dict(os.environ,{},clear=True):
   self.assertEqual(recommend_user(b,{'user_id':'test'},NOW,dict(load_config(),history_enrichment_per_run=0),manual=True),1)
  m=b.collection[0]['metadata'];self.assertEqual(m['genreIds'],[53]);self.assertEqual(m['genre'],'Ужасы');self.assertEqual(m['remoteMetrics']['imdbVoteCount'],30000)
 def test_verified_audiences_survive_an_omdb_outage_and_fill_thirty(self):
  b=FakeBackend();b.imdb_index=fixture(self.path,40)
  films=[dict(movie(5000000+i),imdb_id='tt'+str(1000000+i))for i in range(40)]
  b.movie=lambda path:films[int(path.split('/')[1].split('?')[0])-5000000]
  b.request=lambda *args:(_ for _ in ()).throw(RuntimeError('Optional OMDb failed'))
  with patch('recommend.discover',return_value=(films,[])),patch.dict(os.environ,{'OMDB_API_KEY':'fake-for-test'}):
   self.assertEqual(recommend_user(b,{'user_id':'test'},NOW,dict(load_config(),history_enrichment_per_run=0),manual=True),30)
  self.assertEqual(b.search_report['imdbDatasetResolved'],40);self.assertEqual(b.search_report['selectedImdb10000'],30)
  self.assertTrue(all(r['metadata']['remoteMetrics']['imdbVoteCount']>=30000 for r in b.collection))
 def test_actual_dispatch_transmits_preferred_language_routes(self):
  cfg=dict(load_config(),sources=[{'id':'tmdb','adapter':'tmdb_discover','enabled':True}],_preferred_languages=['en'])
  seen=[]
  def adapter(b,p,c):seen.extend(c.get('_preferred_languages',[]));return [movie(901)]
  with patch.dict('recommendation_sources.ADAPTERS',{'tmdb_discover':adapter}):discover(FakeBackend(),[],cfg)
  self.assertEqual(seen,['en'])

class ImdbDatasetSupplementTests(unittest.TestCase):
 def test_optional_critic_lookup_does_not_replace_fresh_dataset_audience(self):
  from urllib.parse import urlsplit,parse_qs
  from unittest.mock import Mock
  with tempfile.TemporaryDirectory()as temp:
   index=fixture(Path(temp)/'public.db',2);films=[{'imdb_id':'tt1000000'},{'imdb_id':'tt1000001'}];index.enrich(films)
   b=Mock()
   b.request.side_effect=lambda url,headers:{'Response':'True','Type':'movie','imdbID':parse_qs(urlsplit(url).query)['i'][0],'imdbRating':'6.0','imdbVotes':'1000','Metascore':'75','Genre':'Horror, Thriller'}
   with patch.dict(os.environ,{'OMDB_API_KEY':'fake-for-test'}):s=enrich_audience(b,films,40)
   self.assertEqual(s['imdbResolved'],2)
   for movie in films:
    self.assertEqual(movie['remoteMetrics']['imdb'],7.1);self.assertGreaterEqual(movie['remoteMetrics']['imdbVoteCount'],30000);self.assertEqual(movie['remoteMetrics']['metascore'],75)
    self.assertEqual(movie['remoteMetrics']['imdbSource'],'IMDb datasets');self.assertIn('omdbUpdatedAt',movie['remoteMetrics'])

class ImdbDatasetRouteBudgetTests(unittest.TestCase):
 def test_invalid_public_metadata_does_not_consume_the_new_candidate_target(self):
  with tempfile.TemporaryDirectory()as temp:
   index=fixture(Path(temp)/'public.db',80,{i:{'votes':300000}for i in range(40)})
   b=FakeBackend();b.imdb_index=index
   def api(path):
    if path.startswith('find/'):
     identity=path.split('/')[1].split('?')[0];return {'movie_results':[{'id':5000000+int(identity[2:])-1000000}]}
    mid=int(path.split('/')[1].split('?')[0]);i=mid-5000000
    return dict(movie(mid),imdb_id='tt'+str(1000000+i),vote_count=-1 if i<40 else 200)
   b.movie=api
   found=imdb_dataset_candidates(b,[],{'_now':NOW,'candidate_limit':15,'resolution_limit':80,'minimum_votes':100})
   self.assertEqual(len(found),15);self.assertTrue(all(m['id']>=5000040 for m in found))
