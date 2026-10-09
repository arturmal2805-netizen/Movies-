import copy
import datetime
import unittest
from unittest.mock import patch
from recommend import load_config, recommend_user, read_rows
from recommendation_sources import discover, hourly_limit

NOW = datetime.datetime.now(datetime.timezone.utc)


def movie(mid):
    return {'id': mid, 'title': 'Test film', 'genre_ids': [878], 'genres': [{'id': 878}],
            'keywords': ['dystopia'], 'poster_path': '/poster.jpg', 'runtime': 100, 'release_date': '2020-01-01',
            'vote_count': 200, 'vote_average': 7, 'popularity': 10}


class FakeBackend:
    def __init__(self):
        self.collection = []
        self.now = NOW
        self.ratings = [{'tmdb_id': 900, 'impression': 'like', 'plot': 9,
                         'cinematography': 8, 'metadata': {'genreIds': [878]}}]
        self.patched = []
        self.fail_after = None

    def movie(self, path):
        if path.startswith('discover'):
            return {'results': [movie(i) for i in range(901, 931)] + [movie(900)]}
        return movie(int(path.split('/')[1].split('?')[0]))

    def db(self, path, method='GET', body=None, prefer=None):
        if method == 'POST':
            if self.fail_after is not None and len(self.collection) >= self.fail_after:
                raise RuntimeError('Simulated write failure')
            if any(r['tmdb_id'] == body['tmdb_id'] for r in self.collection):
                return []
            row = dict(body, created_at=self.now.isoformat())
            self.collection.append(row)
            return [row]
        if method == 'PATCH':
            self.patched.append(body)
            return None
        return self.ratings if path.startswith('ratings') else self.collection


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config()
        self.backend = FakeBackend()
        self.user = {'user_id': 'test-user'}

    def test_hourly_batch_uses_server_taste_and_never_duplicates(self):
        with patch.dict('os.environ', {}, clear=True):
            self.assertEqual(recommend_user(self.backend, self.user, NOW, self.config), self.config["base_per_hour"])
            self.assertEqual(recommend_user(self.backend, self.user, NOW, self.config), 0)
        self.assertEqual(len(self.backend.collection), self.config["base_per_hour"])
        row = self.backend.collection[0]
        self.assertEqual(row['metadata']['discoverySources'], ['tmdb'])
        self.assertIn('Фантастика', row['reason'])
        self.assertEqual(row['metadata']['tmdbId'], row['tmdb_id'])

    def test_fewer_than_base_candidates_are_saved_instead_of_discarded(self):
        for count in (1, 3, 9, 14):
            backend = FakeBackend()
            config = dict(self.config, base_per_hour=15)
            candidates = [dict(movie(901+i), discovery_sources=['tmdb']) for i in range(count)]
            with patch('recommend.discover', return_value=(candidates, [{'source':'tmdb','status':'ok','candidates':count}])):
                self.assertEqual(recommend_user(backend, self.user, NOW, config), count)
            self.assertEqual(len(backend.collection), count)
            self.assertEqual(len(backend.patched), 1)

    def test_partial_write_retry_respects_rolling_hour_cap(self):
        self.backend.fail_after = 1
        with self.assertRaises(RuntimeError):
            recommend_user(self.backend, self.user, NOW, self.config)
        self.assertEqual(self.backend.patched, [])
        self.backend.fail_after = None
        self.assertEqual(recommend_user(self.backend, self.user, NOW, self.config), self.config["base_per_hour"] - 1)
        self.assertEqual(len(self.backend.collection), self.config["base_per_hour"])

    def test_completed_recent_batch_does_not_query_providers(self):
        user = dict(self.user, last_recommendation_at=NOW.isoformat())
        with patch.object(self.backend, 'movie', side_effect=AssertionError('Must not query')):
            self.assertEqual(recommend_user(self.backend, user, NOW, self.config), 0)

    def test_next_scheduled_hour_runs_even_when_previous_batch_is_less_than_60_minutes_old(self):
        now = datetime.datetime(2026,10,9,15,17,tzinfo=datetime.timezone.utc)
        backend=FakeBackend();backend.now=now
        previous=now-datetime.timedelta(minutes=21)
        user=dict(self.user,last_recommendation_at=previous.isoformat())
        backend.collection=[{'tmdb_id':2000,'reason':'older batch','created_at':previous.isoformat()}]
        candidates=[dict(movie(901+i),discovery_sources=['tmdb']) for i in range(3)]
        with patch('recommend.discover',return_value=(candidates,[])):
            self.assertEqual(recommend_user(backend,user,now,self.config),3)
        self.assertEqual(len(backend.collection),4)

    def test_rolling_maximum_is_preserved_across_two_scheduled_hours(self):
        now=datetime.datetime(2026,10,9,15,17,tzinfo=datetime.timezone.utc)
        backend=FakeBackend();backend.now=now
        previous=now-datetime.timedelta(minutes=21)
        backend.collection=[{'tmdb_id':2000+i,'reason':'older batch','created_at':previous.isoformat()} for i in range(self.config['maximum_per_hour']-1)]
        candidates=[dict(movie(901+i),discovery_sources=['tmdb']) for i in range(3)]
        with patch('recommend.discover',return_value=(candidates,[])):
            self.assertEqual(recommend_user(backend,self.user,now,self.config),1)
        self.assertEqual(len(backend.collection),self.config['maximum_per_hour'])

    def test_sources_deduplicate_and_isolate_failed_provider(self):
        config = copy.deepcopy(self.config)
        config['sources'] += [{'id': 'other', 'enabled': True, 'adapter': 'other'},
                              {'id': 'broken', 'enabled': True, 'adapter': 'broken'}]
        adapters = {'other': lambda *_: [movie(901), movie(999)],
                    'broken': lambda *_: (_ for _ in ()).throw(RuntimeError())}
        with patch.dict('recommendation_sources.ADAPTERS', adapters):
            pool, statuses = discover(self.backend, [], config)
        self.assertEqual(sum(m['id'] == 901 for m in pool), 1)
        self.assertEqual(next(m for m in pool if m['id'] == 901)['discovery_sources'], ['tmdb', 'other'])
        self.assertEqual(statuses[-1]['status'], 'failed')
        ranked = [(0, m, '') for m in pool]
        self.assertEqual(hourly_limit(config, ranked), config["base_per_hour"] + config["extra_per_source"])
        self.assertEqual(hourly_limit(config, [(0, {'discovery_sources': list(range(100))}, '')]), config['maximum_per_hour'])

    def test_all_providers_failed_is_failure_without_success_timestamp(self):
        with patch.object(self.backend, 'movie', side_effect=RuntimeError('Unavailable')):
            with self.assertRaises(RuntimeError):
                recommend_user(self.backend, self.user, NOW, self.config)
        self.assertEqual(self.backend.collection, [])
        self.assertEqual(self.backend.patched, [])

    def test_paginated_history_is_not_truncated(self):
        class Pages:
            def db(self, path):
                return list(range(500)) if 'offset=0' in path else [500]
        self.assertEqual(len(read_rows(Pages(), 'ratings?select=*&order=tmdb_id')), 501)

    def test_feed_normalizes_deduplicates_and_bounds_canonical_ids(self):
        from recommendation_sources import tmdb_id_feed
        with patch.dict('os.environ', {'TEST_FEED_URL': 'https://feed.example/movies'}), \
             patch.object(self.backend, 'request', create=True, return_value={'tmdb_ids': [901, 901, 'tt901', -5, True, 902, 903]}):
            result = tmdb_id_feed(self.backend, [], {'url_env': 'TEST_FEED_URL', 'candidate_limit': 2})
        self.assertEqual([m['id'] for m in result], [901, 902])
        self.assertEqual(result[0]['genre_ids'], [878])

    def test_unavailable_feed_does_not_increase_volume(self):
        config = copy.deepcopy(self.config)
        config['sources'][1]['enabled'] = True
        with patch.dict('os.environ', {}, clear=True):
            pool, statuses = discover(self.backend, [], config)
        self.assertEqual(statuses[-1]['status'], 'failed')
        self.assertEqual(hourly_limit(config, [(0, m, '') for m in pool]), config['base_per_hour'])
