"""Offline coverage for the bundled Pulitzer official seed archive."""

from __future__ import annotations

import json
import unittest
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from awards import cache
from awards.cache_control import refresh_award_source_cache
from awards.engine import lookup_awards
from awards.qualifier import QualificationDecision, qualify_award_result
from awards.registry import find_award_policy
from awards.sources import pulitzer

_UTC = timezone.utc
_TESTS_DIR = Path(__file__).resolve().parent
_SEED_FILE = _TESTS_DIR.parent / 'awards' / 'data' / 'pulitzer_seed.json'
_FIXTURES = _TESTS_DIR / 'fixtures' / 'pulitzer'
_CHALLENGE_HTML = (
    '<html><head><title>Just a moment...</title></head>'
    '<body>Just a moment... Enable JavaScript and cookies to continue'
    '<div id="cf-browser-verification"></div></body></html>'
)


def _blocked():
    return pulitzer._blocked_error(pulitzer.FICTION_URL, 403)


def _valid_seed_payload():
    return json.loads(pulitzer._read_bundled_seed_bytes())


def _write_seed(path: Path, payload) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        + '\n',
        encoding='utf-8',
    )


def _complete_excerpt_archive():
    fiction = pulitzer._parse_category_html(
        (_FIXTURES / 'fiction_excerpt.html').read_text(encoding='utf-8'),
        'Fiction',
        pulitzer.FICTION_URL,
    )
    novel = pulitzer._parse_category_html(
        (_FIXTURES / 'novel_excerpt.html').read_text(encoding='utf-8'),
        'Novel',
        pulitzer.NOVEL_URL,
    )
    return tuple(fiction + novel)


def _save_disk(records, *, generated_at=None, ttl_seconds=None):
    cache.save_source_cache(
        pulitzer.SOURCE_KEY,
        pulitzer.CACHE_VERSION,
        records=[pulitzer._record_to_cache_dict(record) for record in records],
        source_urls=pulitzer._archive_source_urls(),
        coverage=pulitzer._coverage_from_records(records),
        ttl_seconds=(
            pulitzer.CACHE_TTL_SECONDS if ttl_seconds is None else ttl_seconds
        ),
        generated_at=generated_at,
    )


def _assert_qualifies(test, result):
    qualification = qualify_award_result(
        result,
        find_award_policy(result),
    )
    test.assertEqual(qualification.decision, QualificationDecision.QUALIFIES)


class PulitzerSeedValidationTests(unittest.TestCase):
    def setUp(self):
        pulitzer._reset_runtime_state()
        pulitzer._seed_path_override = None
        self._temp = TemporaryDirectory()
        self.seed_path = Path(self._temp.name) / 'pulitzer_seed.json'

    def tearDown(self):
        pulitzer._seed_path_override = None
        pulitzer._reset_runtime_state()
        self._temp.cleanup()

    def _load_mutated(self, mutate):
        payload = _valid_seed_payload()
        mutate(payload)
        _write_seed(self.seed_path, payload)
        pulitzer._seed_path_override = self.seed_path
        return pulitzer._load_bundled_seed()

    def test_seed_file_exists_and_loads(self):
        self.assertTrue(_SEED_FILE.is_file())
        records = pulitzer._load_bundled_seed()
        self.assertGreater(len(records), 0)
        pulitzer._validate_cached_archive(records)

    def test_schema_version_and_metadata(self):
        payload = _valid_seed_payload()
        self.assertEqual(payload['seed_schema_version'], 1)
        self.assertEqual(pulitzer.SEED_SCHEMA_VERSION, 1)
        self.assertEqual(payload['source_key'], 'pulitzer')
        self.assertEqual(payload['reviewed_through_award_year'], 2026)
        self.assertEqual(pulitzer.SEED_REVIEWED_THROUGH_AWARD_YEAR, 2026)
        self.assertTrue(str(payload['reviewed_at']).strip())
        self.assertEqual(
            payload['official_source_urls'],
            list(pulitzer._archive_source_urls()),
        )

    def test_full_validation_accepts_shipped_seed(self):
        records = pulitzer._load_bundled_seed()
        payload = _valid_seed_payload()
        pulitzer._validate_seed_archive(records, payload)

    def test_missing_filesystem_override_fails_closed_as_unreadable(self):
        pulitzer._seed_path_override = Path(self._temp.name) / 'missing.json'
        with self.assertRaises(pulitzer.PulitzerSourceError) as raised:
            pulitzer._load_bundled_seed()
        self.assertIn('could not be read', str(raised.exception))
        self.assertNotIn('JSON', str(raised.exception))
        self.seed_path.write_text('{not json', encoding='utf-8')
        pulitzer._seed_path_override = self.seed_path
        with self.assertRaises(pulitzer.PulitzerSourceError) as raised:
            pulitzer._load_bundled_seed()
        self.assertIn('JSON', str(raised.exception))
        self.assertNotIn('resource could not be read', str(raised.exception))

    def test_wrong_schema_fails_closed(self):
        with self.assertRaises(pulitzer.PulitzerSourceError):
            self._load_mutated(
                lambda payload: payload.__setitem__('seed_schema_version', 99)
            )

    def test_missing_required_metadata_fails_closed(self):
        with self.assertRaises(pulitzer.PulitzerSourceError):
            self._load_mutated(lambda payload: payload.pop('reviewed_at'))

    def test_wrong_category_fails_closed(self):
        def mutate(payload):
            payload['records'][0]['category'] = 'Poetry'

        with self.assertRaises(pulitzer.PulitzerSourceError):
            self._load_mutated(mutate)

    def test_wrong_status_fails_closed(self):
        def mutate(payload):
            payload['records'][0]['status'] = 'Nominee'

        with self.assertRaises(pulitzer.PulitzerSourceError):
            self._load_mutated(mutate)

    def test_invalid_year_fails_closed(self):
        def mutate(payload):
            payload['records'][0]['award_year'] = 0

        with self.assertRaises(pulitzer.PulitzerSourceError):
            self._load_mutated(mutate)

    def test_blank_title_fails_closed(self):
        def mutate(payload):
            payload['records'][0]['work_title'] = '   '

        with self.assertRaises(pulitzer.PulitzerSourceError):
            self._load_mutated(mutate)

    def test_blank_author_fails_closed(self):
        def mutate(payload):
            payload['records'][0]['work_author'] = ''

        with self.assertRaises(pulitzer.PulitzerSourceError):
            self._load_mutated(mutate)

    def test_off_host_url_fails_closed(self):
        def mutate(payload):
            payload['records'][0]['source_url'] = (
                'https://en.wikipedia.org/wiki/Pulitzer_Prize'
            )

        with self.assertRaises(pulitzer.PulitzerSourceError):
            self._load_mutated(mutate)

    def test_duplicate_record_fails_closed(self):
        def mutate(payload):
            payload['records'].append(deepcopy(payload['records'][0]))

        with self.assertRaises(pulitzer.PulitzerSourceError):
            self._load_mutated(mutate)

    def test_missing_category_coverage_fails_closed(self):
        def mutate(payload):
            payload['records'] = [
                item
                for item in payload['records']
                if item['category'] != 'Novel'
            ]

        with self.assertRaises(pulitzer.PulitzerSourceError):
            self._load_mutated(mutate)

    def test_missing_latest_year_sentinel_fails_closed(self):
        def mutate(payload):
            payload['records'] = [
                item
                for item in payload['records']
                if not (
                    item['work_title'] == 'Angel Down'
                    and item['work_author'] == 'Daniel Kraus'
                )
            ]

        with self.assertRaises(pulitzer.PulitzerSourceError):
            self._load_mutated(mutate)

    def test_corrupted_seed_fails_closed(self):
        self.seed_path.write_text(
            json.dumps({'seed_schema_version': 1}) + '\n',
            encoding='utf-8',
        )
        pulitzer._seed_path_override = self.seed_path
        with self.assertRaises(pulitzer.PulitzerSourceError):
            pulitzer._load_bundled_seed()

    def test_sentinels_and_structural_absences(self):
        records = pulitzer._load_bundled_seed()
        for sentinel in pulitzer._SEED_SENTINELS:
            self.assertTrue(
                pulitzer._seed_has_sentinel(records, *sentinel),
                sentinel,
            )
        self.assertFalse(
            any(record.award_year == 1917 for record in records)
        )
        self.assertFalse(
            any(
                record.award_year == 2012
                and record.category == 'Fiction'
                and record.status == 'Winner'
                for record in records
            )
        )
        finalists_2012 = [
            record
            for record in records
            if record.award_year == 2012 and record.status == 'Finalist'
        ]
        titles = {record.work_title for record in finalists_2012}
        self.assertIn('Train Dreams', titles)
        self.assertIn('Swamplandia!', titles)
        self.assertIn('The Pale King', titles)


class PulitzerSeedFallbackTests(unittest.TestCase):
    def setUp(self):
        pulitzer._reset_runtime_state()
        pulitzer._seed_path_override = None
        cache._reset_runtime_state()
        self._temp = TemporaryDirectory()
        self.cache_dir = Path(self._temp.name)
        cache.set_cache_directory(self.cache_dir)

    def tearDown(self):
        pulitzer._seed_path_override = None
        pulitzer._reset_runtime_state()
        cache._reset_runtime_state()
        self._temp.cleanup()

    def _disk_path(self):
        return self.cache_dir / 'pulitzer.json'

    def test_no_disk_seed_valid_live_blocked_uses_seed(self):
        self.assertFalse(self._disk_path().is_file())
        with patch.object(pulitzer, '_load_live_archive', side_effect=_blocked()):
            results = pulitzer.lookup('Angel Down', 'Daniel Kraus')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].award_year, 2026)
        self.assertFalse(self._disk_path().is_file())

    def test_no_disk_seed_valid_lookup_requires_zero_network(self):
        self.assertFalse(self._disk_path().is_file())
        with patch.object(
            pulitzer, '_load_live_archive', side_effect=AssertionError('live')
        ), patch.object(
            pulitzer, '_fetch_html', side_effect=AssertionError('network')
        ):
            results = pulitzer.lookup('Angel Down', 'Daniel Kraus')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].work_title, 'Angel Down')
        self.assertEqual(results[0].work_author, 'Daniel Kraus')
        self.assertEqual(results[0].award_year, 2026)
        self.assertEqual(results[0].category, 'Fiction')
        self.assertEqual(results[0].status, 'Winner')

    def test_fresh_disk_cache_is_used(self):
        excerpt = _complete_excerpt_archive()
        jazz = pulitzer._ParsedRecord(
            award_year=1988,
            category='Fiction',
            status='Winner',
            work_title='Jazz',
            work_author='Toni Morrison',
            source_url='https://www.pulitzer.org/winners/toni-morrison',
        )
        rewritten = []
        for record in excerpt:
            if record.work_title == 'Beloved':
                rewritten.append(jazz)
            else:
                rewritten.append(record)
        _save_disk(tuple(rewritten), generated_at=datetime.now(_UTC))
        pulitzer._reset_runtime_state()
        with patch.object(
            pulitzer, '_load_live_archive', side_effect=AssertionError('live')
        ):
            results = pulitzer.lookup('Jazz', 'Toni Morrison')
        self.assertEqual(results[0].work_title, 'Jazz')
        self.assertEqual(pulitzer.lookup('Beloved', 'Toni Morrison'), [])

    def test_stale_disk_live_blocked_uses_stale(self):
        excerpt = _complete_excerpt_archive()
        _save_disk(
            excerpt,
            generated_at=datetime(2020, 1, 1, tzinfo=_UTC),
            ttl_seconds=60,
        )
        original = self._disk_path().read_text(encoding='utf-8')
        with patch.object(pulitzer, '_load_live_archive', side_effect=_blocked()):
            results = pulitzer.lookup('Beloved', 'Toni Morrison')
        self.assertEqual(results[0].work_title, 'Beloved')
        self.assertEqual(self._disk_path().read_text(encoding='utf-8'), original)

    def test_invalid_disk_seed_valid_live_blocked_uses_seed(self):
        excerpt = _complete_excerpt_archive()
        _save_disk(excerpt, generated_at=datetime.now(_UTC))
        payload = json.loads(self._disk_path().read_text(encoding='utf-8'))
        payload['records'][0]['award_year'] = 0
        self._disk_path().write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + '\n',
            encoding='utf-8',
        )
        with patch.object(pulitzer, '_load_live_archive', side_effect=_blocked()):
            results = pulitzer.lookup('Angel Down', 'Daniel Kraus')
        self.assertEqual(results[0].award_year, 2026)

    def test_complete_successful_live_refresh_is_persisted(self):
        excerpt = _complete_excerpt_archive()
        pulitzer.mark_official_refresh_requested()
        with patch.object(pulitzer, '_load_live_archive', return_value=excerpt):
            results = pulitzer.lookup('Beloved', 'Toni Morrison')
        self.assertEqual(results[0].work_title, 'Beloved')
        self.assertTrue(self._disk_path().is_file())
        pulitzer._reset_runtime_state()
        with patch.object(
            pulitzer, '_load_live_archive', side_effect=AssertionError('live')
        ):
            again = pulitzer.lookup('Beloved', 'Toni Morrison')
        self.assertEqual(again[0].work_title, 'Beloved')

    def test_partial_live_fiction_success_novel_403_keeps_seed(self):
        fiction_html = (_FIXTURES / 'fiction_excerpt.html').read_text(
            encoding='utf-8'
        )

        def fetch(opener, url):
            if url == pulitzer.FICTION_URL:
                return fiction_html
            raise _blocked()

        pulitzer.mark_official_refresh_requested()
        with patch.object(pulitzer, '_fetch_html', side_effect=fetch):
            results = pulitzer.lookup('Angel Down', 'Daniel Kraus')
        self.assertEqual(results[0].award_year, 2026)
        self.assertFalse(self._disk_path().is_file())

    def test_challenge_http_200_keeps_seed(self):
        def fetch(opener, url):
            if url == pulitzer.FICTION_URL:
                return _CHALLENGE_HTML
            raise AssertionError('novel should not be fetched')

        pulitzer.mark_official_refresh_requested()
        with patch.object(pulitzer, '_fetch_html', side_effect=fetch):
            results = pulitzer.lookup('Audition', 'Katie Kitamura')
        self.assertEqual(results[0].status, 'Finalist')
        self.assertFalse(self._disk_path().is_file())

    def test_seed_failure_live_failure_no_disk_raises(self):
        bad = Path(self._temp.name) / 'bad.json'
        bad.write_text('{', encoding='utf-8')
        pulitzer._seed_path_override = bad
        with patch.object(pulitzer, '_load_live_archive', side_effect=_blocked()):
            with self.assertRaises(pulitzer.PulitzerSourceError):
                pulitzer.lookup('Beloved', 'Toni Morrison')

    def test_manual_refresh_is_zero_http_then_failed_live_returns_seed(self):
        with patch.object(
            pulitzer, '_load_live_archive', side_effect=AssertionError('live')
        ), patch.object(
            pulitzer, '_fetch_html', side_effect=AssertionError('network')
        ):
            self.assertTrue(refresh_award_source_cache('pulitzer'))
        with patch.object(
            pulitzer, '_load_live_archive', side_effect=_blocked()
        ) as live:
            first = pulitzer.lookup('Angel Down', 'Daniel Kraus')
            self.assertEqual(live.call_count, 1)
            second = pulitzer.lookup('Audition', 'Katie Kitamura')
            self.assertEqual(live.call_count, 1)
        self.assertEqual(first[0].status, 'Winner')
        self.assertEqual(second[0].status, 'Finalist')

    def test_repeated_lookups_after_block_do_not_hammer_network(self):
        excerpt = _complete_excerpt_archive()
        _save_disk(
            excerpt,
            generated_at=datetime(2020, 1, 1, tzinfo=_UTC),
            ttl_seconds=60,
        )
        pulitzer._reset_runtime_state()
        with patch.object(
            pulitzer, '_load_live_archive', side_effect=_blocked()
        ) as live:
            pulitzer.lookup('Beloved', 'Toni Morrison')
            pulitzer._archive_records_cache = None
            pulitzer.lookup('Beloved', 'Toni Morrison')
        self.assertEqual(live.call_count, 1)

    def test_optional_refresh_failure_is_not_source_failure(self):
        report = lookup_awards(
            'Angel Down',
            'Daniel Kraus',
            enabled_source_keys=('pulitzer',),
        )
        self.assertEqual(len(report.failures), 0)
        self.assertEqual(len(report.assessments), 1)
        self.assertEqual(
            report.assessments[0].qualification.decision,
            QualificationDecision.QUALIFIES,
        )


class PulitzerSeedLookupTests(unittest.TestCase):
    def setUp(self):
        pulitzer._reset_runtime_state()
        cache._reset_runtime_state()
        self._temp = TemporaryDirectory()
        cache.set_cache_directory(self._temp.name)

    def tearDown(self):
        pulitzer._reset_runtime_state()
        cache._reset_runtime_state()
        self._temp.cleanup()

    def _lookup(self, title, author):
        with patch.object(
            pulitzer, '_load_live_archive', side_effect=AssertionError('live')
        ), patch.object(
            pulitzer, '_fetch_html', side_effect=AssertionError('network')
        ):
            return pulitzer.lookup(title, author)

    def test_angel_down_2026_fiction_winner(self):
        results = self._lookup('Angel Down', 'Daniel Kraus')
        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertEqual(result.award_year, 2026)
        self.assertEqual(result.category, 'Fiction')
        self.assertEqual(result.status, 'Winner')
        self.assertEqual(
            result.source_url,
            'https://www.pulitzer.org/winners/daniel-kraus',
        )
        _assert_qualifies(self, result)

    def test_audition_2026_fiction_finalist(self):
        results = self._lookup('Audition', 'Katie Kitamura')
        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertEqual(result.award_year, 2026)
        self.assertEqual(result.status, 'Finalist')
        self.assertEqual(
            result.source_url,
            'https://www.pulitzer.org/finalists/katie-kitamura',
        )
        _assert_qualifies(self, result)

    def test_2023_dual_winners(self):
        trust = self._lookup('Trust', 'Hernan Diaz')
        demon = self._lookup('Demon Copperhead', 'Barbara Kingsolver')
        self.assertEqual(trust[0].award_year, 2023)
        self.assertEqual(trust[0].status, 'Winner')
        self.assertEqual(demon[0].award_year, 2023)
        self.assertEqual(demon[0].status, 'Winner')
        self.assertNotEqual(trust[0].source_url, demon[0].source_url)
        _assert_qualifies(self, trust[0])
        _assert_qualifies(self, demon[0])

    def test_beloved_1988_fiction_winner(self):
        results = self._lookup('Beloved', 'Toni Morrison')
        self.assertEqual(results[0].award_year, 1988)
        self.assertEqual(
            results[0].source_url,
            'https://www.pulitzer.org/winners/toni-morrison',
        )
        _assert_qualifies(self, results[0])

    def test_grapes_of_wrath_1940_novel_winner(self):
        results = self._lookup('The Grapes of Wrath', 'John Steinbeck')
        self.assertEqual(results[0].category, 'Novel')
        self.assertEqual(results[0].award_year, 1940)
        self.assertEqual(
            results[0].source_url,
            'https://www.pulitzer.org/winners/john-steinbeck',
        )
        _assert_qualifies(self, results[0])

    def test_dune_is_not_a_pulitzer_result(self):
        self.assertEqual(self._lookup('Dune', 'Frank Herbert'), [])


class PulitzerSeedPackageTests(unittest.TestCase):
    def setUp(self):
        pulitzer._reset_runtime_state()
        pulitzer._seed_path_override = None
        cache._reset_runtime_state()
        self._temp = TemporaryDirectory()
        cache.set_cache_directory(Path(self._temp.name) / 'cache')

    def tearDown(self):
        pulitzer._seed_path_override = None
        pulitzer._reset_runtime_state()
        cache._reset_runtime_state()
        self._temp.cleanup()

    def test_source_tree_resource_loader_reads_seed(self):
        payload = json.loads(pulitzer._read_bundled_seed_bytes())
        self.assertEqual(payload['source_key'], 'pulitzer')
        records = pulitzer._load_bundled_seed()
        self.assertTrue(
            pulitzer._seed_has_sentinel(
                records,
                2026,
                'Fiction',
                'Winner',
                'Angel Down',
                'Daniel Kraus',
            )
        )

    def test_calibre_resource_loader_validates_and_looks_up_without_network(self):
        seed_bytes = _SEED_FILE.read_bytes()
        requested = []

        # Calibre 6 injects a one-user-argument function. This signature is an
        # intentional regression guard against passing newer optional flags.
        def fake_get_resources(name):
            requested.append(name)
            self.assertEqual(name, 'awards/data/pulitzer_seed.json')
            return seed_bytes

        with patch.dict(
            pulitzer.__dict__, {'get_resources': fake_get_resources}
        ), patch.object(
            pulitzer, '_load_live_archive', side_effect=AssertionError('live')
        ), patch.object(
            pulitzer, '_fetch_html', side_effect=AssertionError('network')
        ):
            records = pulitzer._load_bundled_seed()
            results = pulitzer.lookup('Angel Down', 'Daniel Kraus')
        self.assertEqual(len(records), 195)
        self.assertGreaterEqual(len(requested), 1)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].award_year, 2026)
        self.assertEqual(results[0].category, 'Fiction')
        self.assertEqual(results[0].status, 'Winner')

    def test_calibre_resource_loader_missing_resource_is_unreadable(self):
        def fake_get_resources(name):
            self.assertEqual(name, pulitzer._SEED_ZIP_PATH)
            return None

        with patch.dict(
            pulitzer.__dict__, {'get_resources': fake_get_resources}
        ):
            with self.assertRaises(pulitzer.PulitzerSourceError) as raised:
                pulitzer._load_bundled_seed()
        self.assertIn('could not be read', str(raised.exception))
        self.assertNotIn('JSON', str(raised.exception))
        self.assertIsNone(pulitzer._archive_records_cache)

    def test_calibre_resource_loader_invalid_json_is_reported(self):
        def fake_get_resources(name):
            self.assertEqual(name, pulitzer._SEED_ZIP_PATH)
            return b'{not json'

        with patch.dict(
            pulitzer.__dict__, {'get_resources': fake_get_resources}
        ):
            with self.assertRaises(pulitzer.PulitzerSourceError) as raised:
                pulitzer._load_bundled_seed()
        self.assertIn('not valid JSON', str(raised.exception))
        self.assertNotIn('could not be read', str(raised.exception))

    def test_calibre_resource_loader_does_not_touch_filesystem_fallback(self):
        seed_bytes = _SEED_FILE.read_bytes()

        def fake_get_resources(name):
            self.assertEqual(name, pulitzer._SEED_ZIP_PATH)
            return seed_bytes

        with patch.dict(
            pulitzer.__dict__, {'get_resources': fake_get_resources}
        ), patch.object(
            Path,
            'read_bytes',
            side_effect=AssertionError('filesystem fallback'),
        ):
            records = pulitzer._load_bundled_seed()
        self.assertEqual(len(records), 195)

    def test_calibre_six_one_argument_resource_loader_is_supported(self):
        calls = []

        def fake_get_resources(name):
            calls.append(name)
            return _SEED_FILE.read_bytes()

        with patch.dict(
            pulitzer.__dict__, {'get_resources': fake_get_resources}
        ):
            records = pulitzer._load_bundled_seed()
        self.assertEqual(calls, ['awards/data/pulitzer_seed.json'])
        self.assertEqual(len(records), 195)

    def test_empty_calibre_resource_fails_closed_as_unreadable(self):
        def fake_get_resources(name):
            self.assertEqual(name, pulitzer._SEED_ZIP_PATH)
            return b''

        with patch.dict(
            pulitzer.__dict__, {'get_resources': fake_get_resources}
        ):
            with self.assertRaises(pulitzer.PulitzerSourceError) as raised:
                pulitzer._load_bundled_seed()
        self.assertIn('could not be read', str(raised.exception))
        self.assertNotIn('JSON', str(raised.exception))

    def test_seed_lives_inside_runtime_awards_tree(self):
        self.assertEqual(
            pulitzer._SEED_ZIP_PATH,
            'awards/data/pulitzer_seed.json',
        )
        self.assertTrue(_SEED_FILE.is_file())


if __name__ == '__main__':
    unittest.main()
