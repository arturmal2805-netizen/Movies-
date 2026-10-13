import unittest
from unittest.mock import Mock
from urllib.parse import parse_qs,urlsplit
from recommend import preferred_keyword_groups,load_config
from recommendation_sources import discover


def row(mid,label,names,ids):
 return {'tmdb_id':mid,'impression':label,'metadata':{'year':2020,'genreIds':[27],'keywords':names,'keywordIds':ids}}


class KeywordGroupTests(unittest.TestCase):
 def test_only_repeated_positive_non_generic_combinations_become_search_queries(self):
  rows=[row(i,'like',['alien monster','survival horror','sequel'],[10,20,30]) for i in range(3)]
  rows+=[row(100+i,'dislike',['ghost','haunted house'],[40,50]) for i in range(20)]
  rows.append(row(200,'like',['rare liked','singleton'],[60,70]))
  self.assertEqual(preferred_keyword_groups(rows),[[10,20]])

 def test_combination_with_negative_personal_lift_is_not_a_preference(self):
  rows=[row(i,'like',['ghost','house'],[10,20]) for i in range(3)]
  rows+=[row(10+i,'like',['alien'],[30]) for i in range(10)]
  rows+=[row(100+i,'dislike',['ghost','house'],[10,20]) for i in range(10)]
  self.assertEqual(preferred_keyword_groups(rows),[])

 def test_and_groups_reach_adapter_without_removing_broad_search_or_exceeding_budget(self):
  backend=Mock();backend.movie.return_value={'results':[],'total_pages':100}
  cfg=dict(load_config(),discovery_request_limit=24,sources=[{'id':'tmdb','adapter':'tmdb_discover','enabled':True,'pages':3}],
           _preferred_keywords=[10,20,30,40],_preferred_keyword_groups=[[11,12],[21,22],[31,32],[41,42]])
  discover(backend,[53,878],cfg)
  queries=[parse_qs(urlsplit(call.args[0]).query) for call in backend.movie.call_args_list]
  self.assertLessEqual(len(queries),24)
  self.assertTrue(any(q.get('with_keywords')==['11,12'] for q in queries))
  self.assertTrue(any(q.get('with_keywords')==['4565'] for q in queries))
  self.assertTrue(any(q.get('with_genres')==['27'] and 'with_keywords' not in q for q in queries))
