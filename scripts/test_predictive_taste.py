import math
import unittest
from movie_features import profile,match_score,predictive_features


def history():
 return [{'tmdb_id':i+1,'impression':'like' if i<10 else 'dislike','metadata':{'genreIds':[27],'keywords':['alien lifeform' if i<10 else 'haunted house'],'originalLanguage':'en' if i<10 else 'es','year':2020}} for i in range(100)]


class PredictiveTasteTests(unittest.TestCase):
 def test_imbalanced_rejections_do_not_erase_positive_themes(self):
  rows=history();model=profile(rows)
  self.assertTrue(model.predictive)
  self.assertGreater(match_score(rows[0]['metadata'],model),match_score(rows[-1]['metadata'],model))
  expected=math.log((10+1)/(10+2))-math.log((0+1)/(90+2))
  self.assertAlmostEqual(model[('keyword','alien lifeform')],expected)
  # Common horror is almost uninformative; it cannot dominate the specific theme.
  self.assertLess(abs(model[('genre',27)]),.1)

 def test_neutral_ratings_are_neither_positive_nor_negative_training_labels(self):
  rows=history();candidate=rows[0]['metadata']
  neutral=[dict(rows[0],impression='neutral',plot=10,cinematography=10)]*500
  self.assertAlmostEqual(match_score(candidate,profile(rows)),match_score(candidate,profile(rows+neutral)))

 def test_no_unlearned_feature_is_treated_as_dislike(self):
  self.assertEqual(match_score({'keywords':['unobserved theme']},profile(history())),0)

 def test_sparse_or_one_class_history_keeps_the_conservative_fallback(self):
  self.assertFalse(profile(history()[:10]).predictive)
  self.assertFalse(profile(history()[10:]).predictive)

 def test_canonical_and_browser_metadata_have_the_same_predictive_vector(self):
  self.assertEqual(predictive_features({'genreIds':[27],'year':2021,'originalLanguage':'en'}),predictive_features({'genre_ids':[27],'release_date':'2021-04-05','original_language':'en'}))

 def test_search_seeds_require_repeated_positive_evidence(self):
  from recommend import preferred_keyword_seeds
  rows=history()
  for row in rows:row['metadata']['keywordIds']=[101 if row['impression']=='like' else 202]
  # Rare rejected and singleton positive tags may have positive smoothed weights.
  # They must not become new search directions.
  rows[-1]['metadata']['keywords']=['rare rejected tag'];rows[-1]['metadata']['keywordIds']=[303]
  rows[0]['metadata']['keywords']=['singleton liked tag'];rows[0]['metadata']['keywordIds']=[404]
  model=profile(rows)
  self.assertGreater(model[('keyword','rare rejected tag')],0)
  self.assertEqual(preferred_keyword_seeds(rows,model),[101])
