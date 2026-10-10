"""Regression coverage for an exhausted catalog after hundreds of ratings."""
import datetime
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

from recommendation_sources import tmdb_candidates
from recommend import load_config, recommend_user, schedule_slot, RequestFailure
from test_recommendation_pipeline import FakeBackend, movie

NOW = datetime.datetime(2026, 10, 10, 18, 17, tzinfo=datetime.timezone.utc)


def horror(mid):
    return dict(movie(mid), genre_ids=[27], genres=[{'id': 27}])


class ExhaustionTests(unittest.TestCase):
    def backend(self, total):
        backend = Mock()
        def lookup(path):
            query = parse_qs(urlsplit(path).query)
            page = int(query['page'][0])
            self.assertLessEqual(page, min(500, max(1, total)))
            return {'total_pages': total,
                    'results': [horror(600000 + page * 20 + i) for i in range(20)]}
        backend.movie.side_effect = lookup
        return backend

    def config(self):
        return {'minimum_votes': 100, 'pages': 3, '_now': NOW,
                '_page_seed': 35 - schedule_slot(NOW), '_discovery_pages': {}}

    def test_exhausted_first_twenty_pages_do_not_hide_deeper_films(self):
        backend = self.backend(120)
        cfg = dict(self.config(), _excluded_ids=set(range(600000, 600420)))
        result = tmdb_candidates(backend, [], cfg)
        self.assertTrue(result)
        self.assertTrue(all(m['id'] >= 600420 for m in result))

    def test_refills_never_spend_deeper_requests_on_visited_pages(self):
        backend = self.backend(120)
        cfg = self.config()
        for search_round in range(4):
            tmdb_candidates(backend, [], dict(cfg, _search_round=search_round,
                                            _page_seed=cfg['_page_seed'] + search_round))
        paths = [c.args[0] for c in backend.movie.call_args_list
                 if parse_qs(urlsplit(c.args[0]).query)['page'] != ['1']]
        self.assertEqual(len(paths), len(set(paths)))

    def test_small_lists_never_request_nonexistent_pages(self):
        for total in (0, 1, 2, 3):
            backend = self.backend(total)
            cfg = self.config()
            tmdb_candidates(backend, [], cfg)
            tmdb_candidates(backend, [], dict(cfg, _search_round=1))

    def test_all_strategies_survive_personal_query_request_ceiling(self):
        backend = self.backend(120)
        tmdb_candidates(backend, [53, 878], dict(self.config(), _preferred_keywords=[11, 12, 13, 14]))
        paths = [c.args[0] for c in backend.movie.call_args_list]
        self.assertLessEqual(len(paths), 24)
        queries = [parse_qs(urlsplit(p).query) for p in paths]
        self.assertTrue(any(q.get('with_genres') == ['878'] for q in queries))
        self.assertTrue(any(q.get('with_genres') == ['27,53'] for q in queries))

    def test_full_manual_pipeline_saves_thirty_after_four_hundred_known_films(self):
        backend = FakeBackend()
        backend.collection = [{'tmdb_id': 600020 + i} for i in range(400)]
        discovery = self.backend(120)
        backend.movie = lambda p: discovery.movie(p) if p.startswith('discover/') else horror(int(p.split('/')[1].split('?')[0]))
        cfg = dict(load_config(), history_enrichment_per_run=0,
                   sources=[{'id': 'tmdb', 'adapter': 'tmdb_discover', 'enabled': True, 'pages': 3}])
        # Deterministic request seed selects a known deeper segment.
        seed = (35 - schedule_slot(NOW)) % 119
        request_id = '00000000-0000-4000-8000-' + format(seed, '012x')
        with patch('recommend.liked_movie_seeds', return_value=[]):
            self.assertEqual(recommend_user(backend, {'user_id': 'test'}, NOW, cfg,
                                            manual=True, request_id=request_id), 30)
        self.assertEqual(len(backend.collection), 430)
        self.assertTrue(all(row['tmdb_id'] >= 600420 for row in backend.collection[400:]))

    def test_provider_failure_is_not_reported_as_successful_zero_batch(self):
        backend = FakeBackend()
        with patch('recommend.discover', side_effect=[([], [{'source': 'tmdb', 'status': 'failed'}]), RuntimeError('offline')]):
            with self.assertRaisesRegex(RequestFailure, 'Search incomplete'):
                recommend_user(backend, {'user_id': 'test'}, NOW, load_config(), manual=True)
        self.assertEqual(backend.collection, [])

    def test_genuine_exhaustion_is_distinct_from_provider_failure(self):
        backend = FakeBackend()
        with patch('recommend.discover', return_value=([], [{'source': 'tmdb', 'status': 'ok'}])):
            self.assertEqual(recommend_user(backend, {'user_id': 'test'}, NOW, load_config(), manual=True), 0)
