import unittest
from movie_features import profile, match_score
from recommend import rank_candidates,recommend_user,load_config
from selection_quality import selection_floor, selection_evaluation
from test_recommendation_pipeline import movie, NOW


def history():
    import datetime
    return [{'tmdb_id':i+1,'updated_at':(datetime.datetime(2025,1,1)+datetime.timedelta(days=i)).isoformat(),
             'impression':'like' if i%5==0 else 'dislike',
             'metadata':{'productionBudget':15000000,'year':2021,'genreIds':[27],'keywords':['body horror' if i%5==0 else 'haunted house'],'originalLanguage':'en'}} for i in range(400)]


class SelectionTests(unittest.TestCase):
    def test_insufficient_data_does_not_invent_a_threshold(self):
        self.assertIsNone(selection_floor([]))
        self.assertIsNone(selection_floor([{'impression':'dislike'}]*120))

    def test_later_validation_labels_do_not_leak_into_calibration(self):
        rows=history();before=selection_evaluation(rows)
        changed=[dict(r,impression='dislike' if r['impression']=='like' else 'like') if i>=320 else r for i,r in enumerate(rows)]
        after=selection_evaluation(changed)
        self.assertEqual(before['floor'],after['floor']);self.assertEqual(before['training'],320)
        self.assertEqual(before['after']['accepted'],30)
        self.assertEqual(before['metric'],'top_30')

    def test_low_personal_score_is_ranked_after_strong_match_not_removed(self):
        rows=history();model=profile(rows)
        good=dict(movie(600000),genre_ids=[27],genres=[{'id':27}],keywords=['body horror'])
        weak=dict(movie(600001),genre_ids=[27],genres=[{'id':27}],keywords=['unobserved'])
        model.selection_floor=(match_score(good,model)+match_score(weak,model))/2
        self.assertEqual(len(rank_candidates([good,weak],rows,[],now=NOW,preliminary=True,tastes=model)),2)
        result=rank_candidates([good,weak],rows,[],now=NOW,tastes=model)
        self.assertEqual([r[1]['id'] for r in result],[600000,600001])

    def test_manual_batch_still_saves_thirty_when_every_personal_margin_is_low(self):
        from unittest.mock import patch
        from test_recommendation_pipeline import FakeBackend
        backend=FakeBackend();backend.ratings=history()
        candidates=[dict(movie(600000+i),genre_ids=[27],genres=[{'id':27}],keywords=['haunted house']) for i in range(60)]
        backend.movie=lambda path: candidates[int(path.split('/')[1].split('?')[0])-600000]
        with patch('recommend.discover',return_value=(candidates,[])),patch('recommend.rejection_score',return_value=-100):
            count=recommend_user(backend,{'user_id':'test'},NOW,dict(load_config(),history_enrichment_per_run=0,manual_quality_pool=30),manual=True)
        self.assertEqual(count,30);self.assertEqual(len(backend.collection),30)
