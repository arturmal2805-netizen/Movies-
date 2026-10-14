"""Known audiences outrank noisy niche reviews without making a new veto."""
import unittest
from unittest.mock import Mock,patch
from urllib.parse import urlsplit,parse_qs
from audience_priority import selection_priority_score
from recommend import preferred_audience_languages,recommend_user,load_config,selection56_diagnostics
from recommendation_sources import tmdb_candidates
from test_recommendation_pipeline import FakeBackend,movie,NOW

class EstablishedAudienceTests(unittest.TestCase):
 def test_language_direction_uses_positive_support_not_negative_flood(self):
  rows=[{'impression':'like','metadata':{'year':2020,'genreIds':[27],'originalLanguage':'en'}}for _ in range(5)]
  rows +=[{'impression':'dislike','metadata':{'year':2020,'genreIds':[27],'originalLanguage':'fr'}}for _ in range(500)]
  self.assertEqual(preferred_audience_languages(rows),['en'])
  self.assertEqual(preferred_audience_languages(rows[:2]),[])
  self.assertEqual(preferred_audience_languages([dict(row,metadata=dict(row['metadata'],genreIds=[16]))for row in rows]),[])
 def test_known_language_lists_cover_every_period_and_preserve_broad_fallback(self):
  b=Mock();b.movie.return_value={'results':[],'total_pages':20}
  cfg=dict(load_config(),_now=NOW,_preferred_languages=['en'],_evidence_routes=True)
  tmdb_candidates(b,[],cfg)
  queries=[parse_qs(urlsplit(c.args[0]).query)for c in b.movie.call_args_list]
  established=[q for q in queries if q.get('with_original_language')==['en']]
  self.assertTrue(established)
  self.assertTrue(all(q['vote_count.gte']==['1000']and'35'in q['without_genres'][0].split(',')for q in established))
  self.assertTrue(any(q.get('with_original_language')is None and q['vote_count.gte']==['100']for q in queries))
  self.assertTrue({'2000-01-01','2005-01-01','2010-01-01','2015-01-01','2020-01-01','2025-01-01'}.issubset({q['primary_release_date.gte'][0]for q in established}))
  self.assertLessEqual(len(queries),64)
 def test_no_known_audience_available_still_saves_thirty_valid_films(self):
  b=FakeBackend();b.ratings=[{'tmdb_id':800+i,'impression':'like','metadata':{'year':2020,'genreIds':[27],'originalLanguage':'en'}}for i in range(3)]
  candidates=[dict(movie(5000000+i),genres=[{'id':27}],genre_ids=[27],vote_count=200)for i in range(30)]
  by_id={m['id']:m for m in candidates}
  def lookup(path):
   if path.startswith('discover/'):
    q=parse_qs(urlsplit(path).query)
    return {'total_pages':1,'results':[]if q['vote_count.gte']==['1000']else candidates}
   if path.startswith('movie/')and'/recommendations?'not in path and'/similar?'not in path:return by_id[int(path.split('/')[1].split('?')[0])]
   return {'results':[]}
  b.movie=lookup
  cfg=dict(load_config(),sources=[{'id':'tmdb','adapter':'tmdb_discover','enabled':True,'pages':3}],history_enrichment_per_run=0)
  self.assertEqual(recommend_user(b,{'user_id':'test'},NOW,cfg,manual=True),30)
  self.assertEqual(b.search_report['selectedAudience1000'],0)
  self.assertTrue(all(r['metadata']['recommendationSelectionVersion']=='audience-first56'for r in b.collection))
