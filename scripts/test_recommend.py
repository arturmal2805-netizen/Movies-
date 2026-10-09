import unittest
from recommend import rank_candidates,taste
class RecommendationTests(unittest.TestCase):
 def movie(self,id,genre=878):return {'id':id,'genre_ids':[genre],'keywords':['dystopia'] if genre==878 else [],'poster_path':'/p.jpg','adult':False,'release_date':'2020-01-01','vote_count':200,'vote_average':7,'popularity':10}
 def test_excludes_rated_collected_seeded_and_duplicates(self):
  ratings=[{'tmdb_id':100,'impression':'dislike'}]
  result=rank_candidates([self.movie(100),self.movie(101),self.movie(157336),self.movie(102)],ratings,[{'tmdb_id':101}])
  self.assertEqual([row[1]['id'] for row in result],[102])
 def test_taste_ranks_preferred_genre_and_explains_it(self):
  ratings=[{'tmdb_id':100,'impression':'like','plot':9,'cinematography':8,'metadata':{'genreIds':[878]}}]
  result=rank_candidates([self.movie(101,35),self.movie(102,878)],ratings,[])
  self.assertEqual(result[0][1]['id'],102)
  self.assertIn('Фантастика',result[0][2])
 def test_rejects_missing_photos_and_future_releases(self):
  no_photo=self.movie(100);no_photo['poster_path']=None
  future=self.movie(101);future['release_date']='2999-01-01'
  self.assertEqual(rank_candidates([no_photo,future],[],[]),[])
