"""Personal plot evidence must rank films without inventing labels or empty batches."""
import unittest
from unittest.mock import patch
from synopsis_model import fit_synopsis,synopsis_tokens,synopsis_score
from movie_features import profile,match_score,predictive_features
from recommend import diverse_candidates,recommend_user,load_config,enrich_history
from test_recommendation_pipeline import FakeBackend,movie,NOW


def history():
 return [{'tmdb_id':900000+i,'impression':'like' if i<10 else 'dislike',
          'metadata':{'genreIds':[27],'year':2020,'rating':6.5,'originalLanguage':'en',
                      'description':'Лес древний ритуал культ призрак' if i<10 else 'Телешоу шутка вечеринка смех комедия'}} for i in range(100)]


class SynopsisTests(unittest.TestCase):
 def test_plot_distinguishes_same_genre_without_keyword_or_director_evidence(self):
  rows=history();current=profile(rows);previous=profile(rows,include_synopsis=False,include_reach=False)
  liked,rejected=rows[0]['metadata'],rows[-1]['metadata']
  self.assertAlmostEqual(match_score(liked,previous),match_score(rejected,previous))
  self.assertGreater(match_score(liked,current),match_score(rejected,current))
  self.assertEqual(current.model_version,'duration-aware42');self.assertEqual(previous.model_version,'reliability-aware38')

 def test_neutral_and_watched_do_not_train_or_expand_the_private_vocabulary(self):
  rows=history();initial=fit_synopsis(rows)
  additions=[dict(rows[0],impression=label,metadata={'description':'invented neutral vocabulary'}) for label in ('neutral','watched') for _ in range(100)]
  self.assertEqual(initial,fit_synopsis(rows+additions))

 def test_unrecognised_missing_and_invalid_text_never_create_negative_evidence(self):
  model=fit_synopsis(history())
  for text in (None,'unobserved unknown words',42,False,{'label':'like'},''):
   self.assertEqual(synopsis_score({'description':text},model),0)
  self.assertEqual(synopsis_score({'title':'Лес ритуал культ','recommendationReason':'Лес ритуал культ','plot':10},model),0)

 def test_sparse_word_coverage_is_not_confused_with_many_occurrences_in_one_film(self):
  rows=history();rows[0]['metadata']['description']='singleton '*160
  model=fit_synopsis(rows)
  self.assertNotIn('singleton',model['vocabulary'])
  vocabulary=model['vocabulary'].copy();synopsis_score({'description':'new unseen candidate tokens'},model)
  self.assertEqual(model['vocabulary'],vocabulary)

 def test_text_is_bounded_normalised_and_canonical_overview_has_same_features(self):
  self.assertEqual(synopsis_tokens({'description':'Ритуал ритуалы РИТУАЛ'}),['ритуал']*3)
  self.assertEqual(synopsis_tokens({'description':'ЁЖИК'}),synopsis_tokens({'overview':'ежик'}))
  self.assertEqual(len(synopsis_tokens({'description':'forest '*1000})),160)
  self.assertFalse(synopsis_tokens({'description':' '*4000+'forest'}))
  for rows in ([],history()[:10],history()[10:]):self.assertFalse(fit_synopsis(rows)['vocabulary'])

 def test_audience_reach_is_learned_in_both_directions_without_a_minimum(self):
  for liked,rejected in ((2,40),(40,2)):
   rows=history()
   for row in rows:
    row['metadata'].pop('description');row['metadata']['remoteMetrics']={'popularity':liked if row['impression']=='like' else rejected}
   model=profile(rows);previous=profile(rows,include_synopsis=False,include_reach=False)
   self.assertGreater(match_score(rows[0]['metadata'],model),match_score(rows[-1]['metadata'],model))
   self.assertAlmostEqual(match_score(rows[0]['metadata'],previous),match_score(rows[-1]['metadata'],previous))
  for value in (None,False,-1,'5',float('nan'),float('inf')):
   self.assertFalse(any(key[0]=='reach' for key in predictive_features({'popularity':value})))
  self.assertEqual(predictive_features({'popularity':15}),predictive_features({'remoteMetrics':{'popularity':15}}))

 def test_all_weak_plot_matches_still_save_thirty_and_preserve_small_valid_batches(self):
  for count in (3,30):
   backend=FakeBackend();backend.ratings=history()
   candidates=[dict(movie(700000+i),genres=[{'id':27}],genre_ids=[27],overview=backend.ratings[-1]['metadata']['description']) for i in range(count)]
   backend.movie=lambda path:candidates[int(path.split('/')[1].split('?')[0])-700000]
   cfg=dict(load_config(),history_enrichment_per_run=0,manual_quality_pool=30)
   with patch('recommend.discover',return_value=(candidates,[])):
    self.assertEqual(recommend_user(backend,{'user_id':'test'},NOW,cfg,manual=True),count)
   self.assertTrue(all(r['metadata']['recommendationSynopsisScore']<0 for r in backend.collection))

 def test_batch_diversity_cannot_push_a_weaker_mixed_genre_above_a_stronger_match(self):
  first=[(10,horror(700000+i),'') for i in range(20)]
  strong=(5,horror(800000),'');weak=(4,dict(horror(800001),genre_ids=[27,35],genres=[{'id':27},{'id':35}]),'')
  ordered=diverse_candidates(first+[strong,weak]);ids=[entry[1]['id'] for entry in ordered]
  self.assertLess(ids.index(800000),ids.index(800001))

 def test_legacy_complete_metadata_backfills_context_without_altering_opinions_or_dates(self):
  backend=FakeBackend()
  row={'tmdb_id':700000,'impression':'like','plot':9,'cinematography':8,'updated_at':'2026-01-01',
       'metadata':{'title':'Old import','year':2020,'genreIds':[27],'keywords':[],'featureVersion':2,
                   'productionCountries':['US'],'originalLanguage':'en','remoteMetrics':{'imdb':7.1}}}
  backend.movie=lambda path:dict(horror(700000),overview='Лес древний ритуал',popularity=12)
  enrich_history(backend,'test',[row],[],load_config())
  self.assertEqual((row['impression'],row['plot'],row['cinematography'],row['updated_at']),('like',9,8,'2026-01-01'))
  self.assertEqual(row['metadata']['description'],'Лес древний ритуал')
  self.assertEqual(row['metadata']['remoteMetrics']['popularity'],12)
  self.assertEqual(row['metadata']['remoteMetrics']['imdb'],7.1)
  backend.patched.clear();enrich_history(backend,'test',[row],[],load_config())
  self.assertEqual(backend.patched,[])

 def test_empty_canonical_context_is_checked_once_and_does_not_invent_a_public_value(self):
  backend=FakeBackend()
  row={'tmdb_id':700000,'impression':'dislike','metadata':{'title':'Import','keywords':[],
       'featureVersion':2,'productionCountries':['US'],'originalLanguage':'en'}}
  canonical=horror(700000);canonical.pop('popularity');backend.movie=lambda path:canonical
  enrich_history(backend,'test',[row],[],load_config())
  self.assertNotIn('popularity',row['metadata']['remoteMetrics'])
  backend.patched.clear();enrich_history(backend,'test',[row],[],load_config())
  self.assertEqual(backend.patched,[])


def horror(mid):return dict(movie(mid),genre_ids=[27],genres=[{'id':27}])


if __name__=='__main__':unittest.main()
