"""Length is learned from opinions, not used as an eligibility threshold."""
import unittest
from movie_features import profile,match_score,predictive_features,eligible_for_discovery


class DurationTasteTests(unittest.TestCase):
 def test_length_preference_can_favour_either_shorter_or_longer_films(self):
  for liked,rejected in ((90,130),(130,90)):
   rows=[{'tmdb_id':i+1,'impression':'like' if i<10 else 'dislike',
          'metadata':{'year':2020,'genreIds':[27],'minutes':liked if i<10 else rejected}} for i in range(100)]
   model=profile(rows);previous=profile(rows,include_runtime=False)
   self.assertGreater(match_score(rows[0]['metadata'],model),match_score(rows[-1]['metadata'],model))
   self.assertAlmostEqual(match_score(rows[0]['metadata'],previous),match_score(rows[-1]['metadata'],previous))
   self.assertEqual(model.model_version,'duration-aware42')
   self.assertEqual(previous.model_version,'synopsis-aware40')
   self.assertTrue(eligible_for_discovery(rows[-1]['metadata']))

 def test_canonical_and_saved_length_agree_invalid_values_are_unknown(self):
  self.assertEqual(predictive_features({'runtime':105}),predictive_features({'minutes':105}))
  for invalid in (None,False,True,0,-1,'100',float('nan'),float('inf')):
   self.assertFalse(any(k[0]=='runtime' for k in predictive_features({'minutes':invalid})))

 def test_unseen_length_never_dilutes_existing_negative_evidence(self):
  rows=[{'tmdb_id':i+1,'impression':'like' if i<10 else 'dislike',
         'metadata':{'genreIds':[27],'keywords':['ritual' if i<10 else 'ghost']}} for i in range(100)]
  model=profile(rows);film=rows[-1]['metadata']
  self.assertAlmostEqual(match_score(film,model),match_score(dict(film,minutes=100),model))
  self.assertAlmostEqual(match_score(film,model),match_score(film,profile(rows,include_runtime=False)))


if __name__=='__main__':unittest.main()
