import unittest
from unittest.mock import patch
from interests import normalize_interests,build_style_model,pattern_affinity
from production_policy import production_exclusion
from recommend import Backend
import test_recommendation_diagnostics

class InterestsTests(unittest.TestCase):
 def test_aliases_cannot_duplicate_the_same_director_and_invalid_names_are_ignored(self):
  result=normalize_interests({'directors':['Robert Eggers','Роберт Эггерс',{'name':{}},'Coralie Fargeat']})
  self.assertEqual(len(result['directors']),2)
 def test_pipeline_passes_owned_genre_priority_and_no_filmographies_to_the_source(self):
  from recommend import recommend_user,load_config
  from test_recommendation_pipeline import FakeBackend,NOW
  from recommendation_sources import discover
  b=FakeBackend();b.load_interests=lambda uid:normalize_interests({'genrePriority':['dystopian','horror'],'directors':[]})
  with patch('recommend.discover',return_value=([],[]))as search:
   recommend_user(b,{'user_id':'test'},NOW,dict(load_config(),history_enrichment_per_run=0),manual=True)
  cfg=search.call_args.args[2]
  self.assertEqual(cfg['_genre_priority'],['dystopian','horror']);self.assertEqual(cfg['_preferred_directors'],[])
  with patch.dict('recommendation_sources.ADAPTERS',{'tmdb_discover':lambda backend,preferred,options:self.assertEqual(options['_genre_priority'],['dystopian','horror'])or []}):
   discover(b,[],dict(cfg,sources=[{'adapter':'tmdb_discover','id':'tmdb','enabled':True}]))
 def test_empty_directors_and_genre_priority_are_owned_settings_not_global_defaults(self):
  value=normalize_interests({'directors':[],'genrePriority':['dystopian','bad']})
  self.assertEqual(value['directors'],[]);self.assertEqual(value['genrePriority'],['dystopian','horror'])
  self.assertEqual(len(normalize_interests()['directors']),5)
  self.assertIn('Корали Фаржа',[d['name']for d in normalize_interests()['directors']])
 def test_director_preference_removal_removes_only_the_budget_exception(self):
  m={'budget':2000000,'director':'Robert Eggers','genreIds':[27]}
  self.assertIsNone(production_exclusion(m))
  self.assertEqual(production_exclusion(m,interests={'directors':[]}),'known_low_budget')
 def test_patterns_find_other_directors_and_ignore_a_bare_favorite_name(self):
  rows=[{'impression':'like','metadata':{'director':'Robert Eggers','keywords':['gothic horror','period piece','vampire']}}]+[{'impression':'dislike','metadata':{'director':'Other','keywords':['vampire','zombie']}}for _ in range(20)]
  model=build_style_model(rows)
  self.assertGreater(pattern_affinity({'director':'Unrelated director','keywords':['gothic horror','period piece']},model),0)
  self.assertEqual(pattern_affinity({'director':'Robert Eggers','keywords':[]},model),0)
  self.assertEqual(pattern_affinity({'keywords':['vampire','zombie']},model),0)
  self.assertEqual(build_style_model(rows,{'directors':[]})['reference_count'],0)
 def test_unrelated_keywords_from_different_reference_movies_are_not_a_pattern(self):
  rows=[{'impression':'like','metadata':{'director':'Robert Eggers','keywords':['gothic horror','period piece']}},{'impression':'like','metadata':{'director':'Zach Cregger','keywords':['body horror','identity']}}]
  model=build_style_model(rows)
  self.assertEqual(pattern_affinity({'keywords':['period piece','identity']},model),0)
  self.assertGreater(pattern_affinity({'keywords':['gothic horror','period piece']},model),0)
 def test_server_reads_private_auth_metadata_for_the_exact_profile(self):
  b=test_recommendation_diagnostics.DiagnosticTests().backend();uid='00000000-0000-4000-8000-000000000001'
  with patch.object(b,'request',return_value={'id':uid,'user_metadata':{'nightshift_interests':{'directors':[],'genrePriority':['dystopian','horror']}}})as request:
   result=b.load_interests(uid)
   self.assertTrue(request.call_args.args[0].endswith('/auth/v1/admin/users/'+uid))
   self.assertEqual(result['directors'],[]);self.assertEqual(result['genrePriority'][0],'dystopian')
  with patch.object(b,'request',return_value={'id':'another-user'}):
   with self.assertRaisesRegex(Exception,'not confirmed'):b.load_interests(uid)


class StyleConceptTests(unittest.TestCase):
 def test_synonyms_generalize_without_counting_two_names_of_one_theme_twice(self):
  rows=[{'impression':'like','metadata':{'director':'Robert Eggers','keywords':['gothic horror','period piece','isolation']}}]
  model=build_style_model(rows)
  self.assertGreater(pattern_affinity({'keywords':['gothic','19th century','alone']},model),0)
  self.assertEqual(pattern_affinity({'keywords':['gothic','gothic horror']},model),0)
  self.assertEqual(pattern_affinity({'keywords':['school','beach','friends']},model),0)
