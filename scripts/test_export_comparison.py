import unittest
from unittest.mock import patch
from diagnose_taste import compare_exports
from movie_features import profile

class ExportComparisonTests(unittest.TestCase):
 def rows(self):
  return [{'tmdb_id':i+1,'impression':'like' if i<5 else 'dislike','metadata':{'year':2020,'genreIds':[27],'keywords':['alien' if i<5 else 'ghost']}} for i in range(30)]

 def test_only_previous_export_trains_fresh_predictions(self):
  previous=self.rows();changed=dict(previous[0],impression='dislike')
  fresh={'tmdb_id':99,'impression':'like','metadata':{'year':2020,'genreIds':[27],'keywords':['alien'],'recommendationModel':'recorded-version'}}
  with patch('diagnose_taste.profile',wraps=profile) as fit:
   result=compare_exports(previous,[changed,*previous[1:],fresh])
   self.assertEqual(fit.call_args.args[0],previous)
  self.assertEqual(result['new_count'],1)
  self.assertEqual(result['changed_existing_count'],1)
  self.assertEqual(result['held_out_count'],1)
  self.assertEqual(result['training_count'],30)
  self.assertIsNone(result['pairwise_auc'])
  self.assertEqual(result['actual_model_versions'],{'recorded-version':1})

 def test_rejects_duplicate_ids_and_different_user_scope(self):
  rows=self.rows()
  with self.assertRaises(ValueError):compare_exports(rows,rows+[rows[0]])
  a=[dict(r,user_id='one') for r in rows];b=[dict(r,user_id='two') for r in rows]
  with self.assertRaises(ValueError):compare_exports(a,b)
