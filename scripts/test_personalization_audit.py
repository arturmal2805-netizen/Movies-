import unittest,datetime
from unittest.mock import Mock
from movie_features import profile,match_score,rating_signal,eligible_for_discovery
from diagnose_taste import analyze
from recommendation_sources import tmdb_candidates
from recommend import rank_candidates
from test_recommendation_pipeline import movie,NOW

class PersonalizationAuditTests(unittest.TestCase):
 def history(self):
  return [{'tmdb_id':1000,'updated_at':'2020-01-01','impression':'like','plot':10,'cinematography':10,'metadata':{'year':2020,'genreIds':[27],'keywords':['body horror','mutation'],'director':'Old favorite'}}]+[{'tmdb_id':1001+i,'updated_at':'2026-01-01','impression':'dislike','plot':1,'cinematography':1,'metadata':{'year':2020,'genreIds':[27],'keywords':['ghost','haunted house'],'director':'Rejected director'}} for i in range(524)]
 def test_525_ratings_retain_old_positive_neighbors_despite_mass_recent_rejections(self):
  rows=self.history();model=profile(rows)
  self.assertEqual(len(model.anchors),525)
  self.assertGreater(match_score(rows[0]['metadata'],model),0)
  self.assertGreater(match_score(rows[0]['metadata'],model),match_score(rows[1]['metadata'],model))
 def test_report_uses_all_rows_and_reports_sparse_metadata_honestly(self):
  report=analyze(self.history());self.assertEqual(report['ratings_count'],525);self.assertEqual(report['model_anchor_count'],525)
  self.assertEqual(report['metadata_coverage']['with_country_field'],0)
  self.assertEqual(report['validation']['training_count']+report['validation']['held_out_count'],525)
  self.assertIsNone(report['validation']['current']['pairwise_auc']) # Held-out set contains only dislikes.
 def test_neutral_five_five_is_not_a_rejection(self):self.assertEqual(rating_signal({'impression':'neutral','plot':5,'cinematography':5}),0)
 def test_equal_scores_do_not_use_known_answers_to_break_ties(self):
  rows=[{'tmdb_id':i,'impression':'like' if i>=58 else 'dislike','metadata':{}} for i in range(60)]
  validation=analyze(rows)['validation']
  self.assertEqual(validation['current']['pairwise_auc'],.5)
  self.assertEqual(validation['current']['precision_at_10'],0)
 def test_country_language_and_animation_are_rechecked_on_canonical_details(self):
  for extra in [{'production_countries':[{'iso_3166_1':'CN'}]},{'original_language':'zh'},{'original_language':'cn'},{'genres':[{'id':27},{'id':16}]}]:
   candidate=dict(movie(999),**extra);self.assertFalse(eligible_for_discovery(candidate))
 def test_like_seed_discovery_uses_tmdb_recommendations_and_is_bounded(self):
  backend=Mock();backend.movie.return_value={'results':[]}
  tmdb_candidates(backend,[],{'minimum_votes':100,'_now':NOW,'_preferred_movie_ids':list(range(1,20))})
  seeds=[c.args[0] for c in backend.movie.call_args_list if '/recommendations?' in c.args[0]]
  self.assertEqual(len(seeds),6);self.assertTrue(seeds[0].startswith('movie/1/'))
 def test_bad_theme_is_not_sent_just_to_fill_a_large_batch(self):
  rows=self.history();bad=dict(movie(900),genre_ids=[27],genres=[{'id':27}],keywords=['ghost','haunted house'],director='Rejected director')
  self.assertEqual(rank_candidates([bad],rows,[],now=NOW),[])
 def test_private_audit_never_combines_users_or_duplicates(self):
  for rows in [[{'user_id':'a','tmdb_id':1},{'user_id':'b','tmdb_id':2}],[{'tmdb_id':1},{'tmdb_id':1}]]:
   with self.assertRaises(ValueError):analyze(rows)
