import unittest
import urllib.error
import urllib.parse
from unittest.mock import Mock
from simkl_source import client_id, FEED_URL, auth_diagnostic, api_requirements
from recommendation_sources import simkl_candidates
from import_catalog import refresh


class SimklTests(unittest.TestCase):
    def test_auth_diagnostics_do_not_copy_sensitive_body(self):
        import io
        error = urllib.error.HTTPError('https://api.simkl.com/private', 401, 'private', {}, io.BytesIO(b'Missing OAuth bearer token private-secret'))
        result = auth_diagnostic(error)
        self.assertEqual(result['category'], 'authentication_rejected')
        self.assertIn('token', result['reasonHints'])
        self.assertNotIn('private-secret', str(result))

    def test_current_docs_expose_required_auth_and_app_fields(self):
        result = api_requirements({'paths': {'/movies/{id}': {'get': {'security': [{'bearerAuth': []}], 'parameters': [{'name': 'app-name', 'in': 'query', 'required': True}]}}}})
        self.assertEqual(result['parameters'][0]['name'], 'app-name')
        self.assertEqual(result['security'], [{'bearerAuth': []}])

    def test_normalize_wrapped_key_and_reject_client_secret(self):
        self.assertEqual(client_id(' abcd\nefgh \r\n'), 'abcdefgh')
        for value in ('simkl_cs_fake', '', 'abc:bad', 'ключ'):
            with self.assertRaises(ValueError): client_id(value)

    def test_resolve_imdb_and_deduplicate_canonical_ids(self):
        backend = Mock()
        backend.request.return_value = [
            {'ids': {'tmdb': '501', 'simkl': 999}},
            {'ids': {'imdb': 'tt12345'}},
            {'ids': {'tmdb': True, 'simkl': 501}},
            {'ids': {'simkl': 501}},
        ]
        backend.movie.side_effect = lambda path: {'movie_results': [{'id': 501}]} if path.startswith('find/') else {'id': 501, 'genres': [{'id': 878}]}
        result = simkl_candidates(backend, [], {'candidate_limit': 40})
        self.assertEqual([r['id'] for r in result], [501])
        self.assertEqual(result[0]['genre_ids'], [878])
        self.assertEqual(backend.movie.call_count, 2)
        self.assertNotIn('Authorization', backend.request.call_args.args[1])

    def test_failed_lookup_retains_other_candidates_and_limits_requests(self):
        backend = Mock()
        backend.request.return_value = [{'ids': {'tmdb': mid}} for mid in range(1, 100)]
        backend.movie.side_effect = lambda path: (_ for _ in ()).throw(TimeoutError()) if path.startswith('movie/1?') else {'id': 2, 'genres': []}
        self.assertEqual([r['id'] for r in simkl_candidates(backend, [], {'candidate_limit': 2})], [2])
        self.assertEqual(backend.movie.call_count, 2)

    def test_invalid_payload_does_not_confirm_feed(self):
        result = refresh({}, request=lambda *_: {'error': 'private message'}, environ={})
        self.assertEqual(result['sources']['simkl']['status'], 'error')

    def test_feed_and_wrapped_client_id_verified_separately_without_leaks(self):
        calls = []
        def request(url, headers):
            calls.append(url)
            if url != FEED_URL: self.assertEqual(headers['simkl-api-key'], 'abcdef')
            if url.endswith('openapi.json'): return {}
            return [] if url == FEED_URL else {'ids': {'imdb': 'tt0816692', 'simkl': 123}}
        result = refresh({}, request=request, environ={'SIMKL_CLIENT_ID': ' abc\ndef '})
        state = result['sources']['simkl']
        self.assertEqual((state['status'], state['credentialStatus']), ('ok', 'ok'))
        query = urllib.parse.parse_qs(urllib.parse.urlparse(next(url for url in calls if '/movies/' in url and '?' in url)).query)
        self.assertEqual(query['client_id'], ['abcdef'])
        self.assertEqual(query['app-name'], ['Nightshift'])
        self.assertNotIn('abcdef', str(result))

    def test_bad_client_id_does_not_disable_public_feed(self):
        def request(url, headers):
            if url == FEED_URL: return []
            raise urllib.error.HTTPError(url, 412, 'private key', {}, None)
        state = refresh({}, request=request, environ={'SIMKL_CLIENT_ID': 'fake'})['sources']['simkl']
        self.assertEqual((state['status'], state['credentialStatus'], state['credentialHttpStatus']), ('ok', 'error', 412))
        self.assertNotIn('private key', str(state))
