"""Broader audience routes can rescue an exhausted personal candidate pool."""
import datetime
import unittest
from unittest.mock import Mock,patch
from urllib.parse import urlsplit,parse_qs
from recommendation_sources import tmdb_candidates
from recommend import recommend_user,load_config
from test_recommendation_pipeline import FakeBackend,movie


NOW=datetime.datetime(2026,10,13,18,30,tzinfo=datetime.timezone.utc)


class AudienceDiscoveryTests(unittest.TestCase):
 def test_new_routes_cover_horror_and_dystopia_without_raising_vote_minimum(self):
  backend=Mock();backend.movie.return_value={'results':[],'total_pages':30}
  config=dict(load_config(),discovery_request_limit=24,_now=NOW,_evidence_routes=True,_preferred_keywords=[1,2,3,4],
              _preferred_keyword_groups=[[5,6],[7,8],[9,10],[11,12]],_preferred_periods=[2010,2020])
  tmdb_candidates(backend,[53,878],config)
  queries=[parse_qs(urlsplit(c.args[0]).query) for c in backend.movie.call_args_list]
  self.assertLessEqual(len(queries),24)
  self.assertTrue(all(q['vote_count.gte']==['100'] for q in queries))
  audience=[q for q in queries if q['sort_by']==['vote_count.desc']]
  self.assertTrue(any(q.get('with_keywords')==['4565'] for q in audience))
  self.assertEqual({q['primary_release_date.gte'][0] for q in audience if q.get('with_genres')==['27']},
                   {'2000-01-01','2010-01-01','2020-01-01'})
  self.assertTrue(any(q['sort_by']==['popularity.desc'] for q in queries))
  self.assertTrue(any(q['sort_by']==['vote_average.desc'] for q in queries))
  self.assertTrue(all(q['primary_release_date.lte'][0]<=NOW.date().isoformat() for q in queries))

 def test_only_new_audience_route_returns_unseen_films_and_pipeline_saves_small_batch(self):
  backend=FakeBackend();backend.ratings=[{'tmdb_id':900000+i,'impression':'like' if i<10 else 'dislike',
       'metadata':{'year':2020,'genreIds':[27],'keywords':['ritual' if i<10 else 'ghost']}} for i in range(100)]
  candidates=[dict(movie(2100000+i),genres=[{'id':27}],genre_ids=[27],keywords=['ghost']) for i in range(3)]
  by_id={m['id']:m for m in candidates}
  def lookup(path):
   if path.startswith('discover/movie?'):
    query=parse_qs(urlsplit(path).query)
    return {'results':candidates if query['sort_by']==['vote_count.desc'] else [],'total_pages':1}
   if path.startswith('movie/') and '/recommendations?' not in path and '/similar?' not in path:
    return by_id[int(path.split('/')[1].split('?')[0])]
   return {'results':[]}
  backend.movie=lookup
  cfg=dict(load_config(),discovery_request_limit=24,sources=[{'id':'tmdb','adapter':'tmdb_discover','enabled':True,'pages':3}],history_enrichment_per_run=0)
  for manual in (False,True):
   backend.collection=[]
   with patch('recommend.match_score',return_value=-1):
    self.assertEqual(recommend_user(backend,{'user_id':'test'},NOW,cfg,manual=manual),3)
   self.assertTrue(all('audience-votes' in r['metadata']['recommendationPersonalRoutes'] for r in backend.collection))
   self.assertTrue(all(r['metadata']['recommendationSearchVersion']=='audience-search47' for r in backend.collection))


if __name__=='__main__':unittest.main()
