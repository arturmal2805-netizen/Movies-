import unittest
from unittest.mock import Mock,patch
from movie_features import profile,match_score,features
from recommend import preferred_director_seeds,rank_candidates,recommend_user,load_config
from recommendation_sources import director_candidates
import test_personalized_discovery as discovery_fixture
from test_recommendation_pipeline import FakeBackend,movie,NOW


def horror(mid,word='unknown'):
 return dict(movie(mid),genres=[{'id':27}],genre_ids=[27],keywords=[word])


class SearchEvidenceTests(unittest.TestCase):
 def test_translated_director_alias_is_a_real_feature_not_a_display_name_guess(self):
  rows=discovery_fixture.PersonalizedDiscoveryTests().history()
  for r in rows[:4]:r['metadata']['director']='Зак Креггер'
  model=profile(rows);plain=horror(700000)
  plain['director']='Zach Cregger'
  verified=dict(plain,directorAliases=['Зак Креггер'])
  self.assertGreater(match_score(verified,model),match_score(plain,model))
  self.assertIn(('director','зак креггер'),features(verified))
  self.assertNotIn(('director','зак креггер'),features(verified,include_director_aliases=False))

 def test_alias_is_persisted_only_when_canonical_credits_confirm_the_same_person(self):
  for canonical_id,expected in ((12,['Зак Креггер']),(13,None)):
   backend=FakeBackend();backend.ratings=discovery_fixture.PersonalizedDiscoveryTests().history()
   canonical=dict(horror(700000),credits={'crew':[{'id':canonical_id,'name':'Zach Cregger','job':'Director'}]})
   backend.movie=lambda path:canonical
   coarse=dict(horror(700000),_liked_directors=['Зак Креггер'],_director_alias_ids={'Зак Креггер':12})
   with patch('recommend.discover',return_value=([coarse],[])):
    self.assertEqual(recommend_user(backend,{'user_id':'test'},NOW,dict(load_config(),history_enrichment_per_run=0),manual=True),1)
   self.assertEqual(backend.collection[0]['metadata'].get('directorAliases'),expected)

 def test_single_strong_like_can_expand_director_search_but_prior_rejection_blocks_it(self):
  rows=discovery_fixture.PersonalizedDiscoveryTests().history()
  single={'tmdb_id':900000,'impression':'like','plot':10,'cinematography':10,'metadata':{'year':2020,'genreIds':[27],'director':'One hit'}}
  self.assertIn('One hit',preferred_director_seeds(rows+[single],profile(rows+[single])))
  negative=dict(single,tmdb_id=900001,impression='dislike')
  self.assertNotIn('One hit',preferred_director_seeds(rows+[single,negative],profile(rows+[single,negative])))

 def test_director_discovery_rotates_new_names_after_four_stable_preferences(self):
  rows=discovery_fixture.PersonalizedDiscoveryTests().history()
  for i in range(16):rows.append({'tmdb_id':900000+i,'impression':'like','plot':10,'cinematography':10,'metadata':{'year':2020,'genreIds':[27],'director':'Creator '+str(i)}})
  model=profile(rows);a=preferred_director_seeds(rows,model,rotation=0);b=preferred_director_seeds(rows,model,rotation=8)
  self.assertEqual(a[:4],b[:4]);self.assertNotEqual(a[4:],b[4:]);self.assertEqual(len(a),8)

 def test_negative_rating_of_verified_translated_director_blocks_single_hit_expansion(self):
  rows=discovery_fixture.PersonalizedDiscoveryTests().history()
  positive={'tmdb_id':900000,'impression':'like','plot':10,'cinematography':10,'metadata':{'year':2020,'genreIds':[27],'director':'One hit'}}
  negative={'tmdb_id':900001,'impression':'dislike','metadata':{'year':2020,'genreIds':[27],'director':'English name','directorAliases':['One hit']}}
  self.assertNotIn('One hit',preferred_director_seeds(rows+[positive,negative],profile(rows+[positive,negative])))

 def test_one_anchor_resolves_a_director_without_guessing_a_translated_name(self):
  backend=Mock()
  backend.movie.side_effect=[{'credits':{'crew':[{'id':12,'job':'Director'}]}},{'crew':[dict(horror(700000),job='Director')]}]
  result=director_candidates(backend,['Переведённое имя'],{'_director_anchor_ids':{'Переведённое имя':[600001]}})
  self.assertEqual(result[0]['_director_alias_ids'],{'Переведённое имя':12})
  self.assertTrue(backend.movie.call_args.args[0].startswith('person/12/'))

 def test_sparse_personal_routes_get_verification_priority_not_a_final_score_bonus(self):
  plain=horror(700000);personal=dict(horror(700001),_liked_directors=['Trusted'])
  self.assertEqual(rank_candidates([plain,personal],[],[],now=NOW,preliminary=True)[0][1]['id'],700001)
  self.assertEqual(rank_candidates([plain,personal],[],[],now=NOW)[0][1]['id'],700000)

 def test_weak_full_batch_triggers_more_search_and_is_replaced_by_better_matches(self):
  backend=FakeBackend();backend.ratings=discovery_fixture.PersonalizedDiscoveryTests().history()
  weak=[horror(600000+i) for i in range(60)];strong=[horror(700000+i,'body horror') for i in range(30)]
  by_id={m['id']:m for m in weak+strong};backend.movie=lambda path:by_id[int(path.split('/')[1].split('?')[0])]
  with patch('recommend.discover',side_effect=[(weak,[]),(strong,[])]) as search,patch('recommend.match_score',side_effect=lambda m,t:1 if 'body horror' in m.get('keywords',[]) else -1):
   count=recommend_user(backend,{'user_id':'test'},NOW,dict(load_config(),manual_quality_pool=30,history_enrichment_per_run=0),manual=True)
  self.assertEqual(count,30);self.assertEqual(search.call_count,2)
  self.assertTrue(all(row['tmdb_id']>=700000 for row in backend.collection))
