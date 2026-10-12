import unittest
from movie_features import profile, match_score
from recommend import rank_candidates
from selection_quality import selection_floor, selection_evaluation
from test_recommendation_pipeline import movie, NOW


def history():
    import datetime
    return [{'tmdb_id':i+1,'updated_at':(datetime.datetime(2025,1,1)+datetime.timedelta(days=i)).isoformat(),
             'impression':'like' if i%5==0 else 'dislike',
             'metadata':{'year':2021,'genreIds':[27],'keywords':['body horror' if i%5==0 else 'haunted house'],'originalLanguage':'en'}} for i in range(400)]


class SelectionTests(unittest.TestCase):
    def test_insufficient_data_does_not_invent_a_threshold(self):
        self.assertIsNone(selection_floor([]))
        self.assertIsNone(selection_floor([{'impression':'dislike'}]*120))

    def test_later_validation_labels_do_not_leak_into_calibration(self):
        rows=history();before=selection_evaluation(rows)
        changed=[dict(r,impression='dislike' if r['impression']=='like' else 'like') if i>=320 else r for i,r in enumerate(rows)]
        after=selection_evaluation(changed)
        self.assertEqual(before['floor'],after['floor']);self.assertEqual(before['training'],320)
        self.assertLessEqual(before['after']['accepted'],before['before']['accepted'])

    def test_calibrated_floor_filters_final_details_but_not_search_candidates(self):
        rows=history();model=profile(rows)
        good=dict(movie(600000),genre_ids=[27],genres=[{'id':27}],keywords=['body horror'])
        weak=dict(movie(600001),genre_ids=[27],genres=[{'id':27}],keywords=['unobserved'])
        model.selection_floor=(match_score(good,model)+match_score(weak,model))/2
        self.assertEqual(len(rank_candidates([good,weak],rows,[],now=NOW,preliminary=True,tastes=model)),2)
        result=rank_candidates([good,weak],rows,[],now=NOW,tastes=model)
        self.assertEqual([r[1]['id'] for r in result],[600000])
