import unittest
from unittest.mock import Mock
from urllib.parse import urlsplit,parse_qs
from recommend import rank_candidates,valid_candidate
from movie_features import rating_signal,profile,match_score
from recommendation_sources import tmdb_candidates
from test_recommendation_pipeline import NOW,movie

class HorrorPreferenceTests(unittest.TestCase):
 def test_documentary_is_rejected_in_discovery_and_canonical_detail_formats(self):
  for extra in ({'genre_ids':[99]},{'genre_ids':[27,99]},{'genres':[{'id':99}]},{'genreIds':[99]}):
   candidate=movie(901);candidate.pop('genres');candidate.update(extra)
   self.assertFalse(valid_candidate(candidate,100,NOW.date()))
   self.assertEqual(rank_candidates([candidate],[],[],now=NOW),[])

 def test_explicit_horror_preference_beats_general_popularity(self):
  horror=dict(movie(901),genres=[{'id':27}],genre_ids=[27])
  drama=dict(movie(902),genres=[{'id':18}],genre_ids=[18],vote_count=100000,vote_average=9,popularity=10000)
  ranked=rank_candidates([drama,horror],[],[],now=NOW)
  self.assertEqual(ranked[0][1]['id'],901);self.assertIn('Приоритет хоррорам',ranked[0][2])

 def test_worst_rating_lowers_similar_themes_without_blacklisting_all_horror(self):
  body=dict(movie(901),genre_ids=[27],genres=[{'id':27}],keywords=['body horror'])
  ghost=dict(movie(902),genre_ids=[27],genres=[{'id':27}],keywords=['ghost'])
  rating={'tmdb_id':900,'impression':'dislike','plot':1,'cinematography':1,'metadata':{'genreIds':[27],'keywords':['body horror']}}
  self.assertEqual(rating_signal(rating),-1)
  taste=profile([rating]);self.assertLess(match_score(body,taste),match_score(ghost,taste))
  self.assertEqual(rank_candidates([body,ghost],[rating],[],now=NOW)[0][1]['id'],902)

 def test_discovery_searches_horror_first_and_excludes_documentaries_in_every_query(self):
  backend=Mock();backend.movie.return_value={'results':[]}
  tmdb_candidates(backend,[99,35,27],{'minimum_votes':100,'pages':3,'_now':NOW})
  queries=[parse_qs(urlsplit(c.args[0]).query) for c in backend.movie.call_args_list]
  self.assertTrue(all(q['without_genres']==['99'] for q in queries));self.assertEqual(queries[0]['with_genres'],['27'])
  self.assertTrue(any(q.get('with_genres')==['27'] and q['sort_by']==['vote_average.desc'] for q in queries));self.assertFalse(any(q.get('with_genres')==['99'] for q in queries))
