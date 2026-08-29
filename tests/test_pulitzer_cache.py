"""Offline coverage for Pulitzer persistent parsed-archive cache."""

from __future__ import annotations

import importlib.util
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from awards import cache
from awards.engine import lookup_awards
from awards.sources import hugo, nebula, newbery, nobel, pulitzer, world_fantasy

_UTC = timezone.utc
_TESTS_DIR = Path(__file__).resolve().parent
_FIXTURES = _TESTS_DIR / 'fixtures' / 'pulitzer'

BELOVED_URL = 'https://www.pulitzer.org/winners/toni-morrison'
GRAPES_URL = 'https://www.pulitzer.org/winners/john-steinbeck'


def _load_test_module(name: str):
    path = _TESTS_DIR / f'{name}.py'
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _complete_archive(*, beloved=True):
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
    if not beloved:
        fiction = [
            pulitzer._ParsedRecord(
                award_year=record.award_year,
                category=record.category,
                status=record.status,
                work_title=(
                    'Jazz' if record.work_title == 'Beloved' else record.work_title
                ),
                work_author=record.work_author,
                source_url=record.source_url,
            )
            for record in fiction
        ]
    return tuple(fiction + novel)


def _with_extra_fiction_winner(archive):
    extra = pulitzer._ParsedRecord(
        award_year=1989,
        category='Fiction',
        status='Winner',
        work_title='Breathing Lessons',
        work_author='Anne Tyler',
        source_url='https://www.pulitzer.org/winners/anne-tyler',
    )
    return archive + (extra,)


def _save_disk(records, *, generated_at=None, ttl_seconds=None, version=None):
    cache.save_source_cache(
        pulitzer.SOURCE_KEY,
        pulitzer.CACHE_VERSION if version is None else version,
        records=[pulitzer._record_to_cache_dict(record) for record in records],
        source_urls=pulitzer._archive_source_urls(),
        coverage=pulitzer._coverage_from_records(records),
        ttl_seconds=(
            pulitzer.CACHE_TTL_SECONDS if ttl_seconds is None else ttl_seconds
        ),
        generated_at=generated_at,
    )


def _blocked():
    return pulitzer._blocked_error(pulitzer.FICTION_URL, 403)


class PulitzerPersistentCacheTests(unittest.TestCase):
    def setUp(self):
        pulitzer._reset_runtime_state()
        cache._reset_runtime_state()
        self._temp = TemporaryDirectory()
        self.cache_dir = Path(self._temp.name)
        cache.set_cache_directory(self.cache_dir)

    def tearDown(self):
        pulitzer._reset_runtime_state()
        cache._reset_runtime_state()
        self._temp.cleanup()

    def _disk_path(self):
        return self.cache_dir / 'pulitzer.json'

    def _rewrite_records(self, mutate):
        payload = json.loads(self._disk_path().read_text(encoding='utf-8'))
        mutate(payload)
        self._disk_path().write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
            + '\n',
            encoding='utf-8',
        )

    def _assert_beloved(self, results):
        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertEqual(result.work_title, 'Beloved')
        self.assertEqual(result.work_author, 'Toni Morrison')
        self.assertEqual(result.award_name, 'Pulitzer Prize')
        self.assertEqual(result.award_year, 1988)
        self.assertEqual(result.category, 'Fiction')
        self.assertEqual(result.status, 'Winner')
        self.assertIsNone(result.rank)
        self.assertEqual(result.source_name, 'Pulitzer Prizes')
        self.assertEqual(result.source_url, BELOVED_URL)
        self.assertIsNone(result.notes)

    def test_cache_identity_constants(self):
        self.assertEqual(pulitzer.SOURCE_KEY, 'pulitzer')
        self.assertEqual(pulitzer.CACHE_VERSION, 1)
        self.assertEqual(pulitzer.CACHE_BASE_TTL_SECONDS, 7 * 24 * 60 * 60)
        self.assertEqual(pulitzer.CACHE_REFRESH_OFFSET_SECONDS, 5 * 60 * 60)
        self.assertEqual(
            pulitzer.CACHE_TTL_SECONDS,
            pulitzer.CACHE_BASE_TTL_SECONDS + pulitzer.CACHE_REFRESH_OFFSET_SECONDS,
        )
        self.assertEqual(pulitzer.CACHE_TTL_SECONDS, 622800)

    def test_complete_archive_helper_passes_source_validation(self):
        pulitzer._validate_cached_archive(_complete_archive())

    def test_parsed_record_round_trips_all_fields(self):
        original = pulitzer._ParsedRecord(
            award_year=1988,
            category='Fiction',
            status='Winner',
            work_title='Beloved',
            work_author='Toni Morrison',
            source_url=BELOVED_URL,
        )
        restored = pulitzer._record_from_cache_dict(
            pulitzer._record_to_cache_dict(original)
        )
        self.assertEqual(restored, original)
        finalist = pulitzer._ParsedRecord(
            award_year=1991,
            category='Fiction',
            status='Finalist',
            work_title='The Things They Carried',
            work_author="Tim O'Brien",
            source_url='https://www.pulitzer.org/finalists/tim-obrien',
        )
        self.assertEqual(
            pulitzer._record_from_cache_dict(
                pulitzer._record_to_cache_dict(finalist)
            ),
            finalist,
        )
        novel = pulitzer._ParsedRecord(
            award_year=1940,
            category='Novel',
            status='Winner',
            work_title='The Grapes of Wrath',
            work_author='John Steinbeck',
            source_url=GRAPES_URL,
        )
        self.assertEqual(
            pulitzer._record_from_cache_dict(pulitzer._record_to_cache_dict(novel)),
            novel,
        )

    def test_record_order_is_preserved(self):
        archive = _complete_archive()
        restored = pulitzer._records_from_cache_payload(
            {
                'records': [
                    pulitzer._record_to_cache_dict(record) for record in archive
                ],
                'source_urls': list(pulitzer._archive_source_urls()),
            }
        )
        self.assertEqual(restored, archive)
        self.assertEqual(
            [record.work_title for record in restored[:3]],
            [record.work_title for record in archive[:3]],
        )

    def test_fresh_cache_lookup_makes_zero_network_calls(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        pulitzer._reset_runtime_state()
        with patch.object(
            pulitzer, '_fetch_html', side_effect=AssertionError('network')
        ), patch.object(
            pulitzer, '_load_live_archive', side_effect=AssertionError('live')
        ):
            results = pulitzer.lookup('Beloved', 'Toni Morrison')
        self._assert_beloved(results)
        grapes = pulitzer.lookup('The Grapes of Wrath', 'John Steinbeck')
        self.assertEqual(len(grapes), 1)
        self.assertEqual(grapes[0].category, 'Novel')
        self.assertEqual(grapes[0].source_url, GRAPES_URL)

    def test_fresh_cache_does_not_consume_refresh_budget(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        pulitzer._reset_runtime_state()
        with cache.lookup_refresh_budget():
            with patch.object(
                pulitzer, '_load_live_archive', side_effect=AssertionError('live')
            ):
                results = pulitzer.lookup('Beloved', 'Toni Morrison')
            self._assert_beloved(results)
            self.assertTrue(cache.try_claim_stale_refresh())

    def test_fresh_cache_survives_hypothetical_live_403(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        pulitzer._reset_runtime_state()
        with patch.object(
            pulitzer, '_fetch_html', side_effect=_blocked()
        ), patch.object(
            pulitzer, '_load_live_archive', side_effect=_blocked()
        ):
            results = pulitzer.lookup('Beloved', 'Toni Morrison')
        self._assert_beloved(results)

    def test_restart_simulation_reloads_disk_after_ram_clear(self):
        archive = _complete_archive()
        with patch.object(
            pulitzer, '_load_live_archive', return_value=archive
        ) as live:
            first = pulitzer.lookup('Beloved', 'Toni Morrison')
        self._assert_beloved(first)
        self.assertEqual(live.call_count, 1)
        self.assertTrue(self._disk_path().is_file())
        pulitzer._reset_runtime_state()
        self.assertTrue(self._disk_path().is_file())
        with patch.object(
            pulitzer, '_fetch_html', side_effect=AssertionError('network')
        ), patch.object(
            pulitzer, '_load_live_archive', side_effect=AssertionError('live')
        ):
            second = pulitzer.lookup('Beloved', 'Toni Morrison')
        self._assert_beloved(second)

    def test_stale_cache_successful_refresh_replaces_disk(self):
        stale = _complete_archive()
        _save_disk(
            stale,
            generated_at=datetime(2020, 1, 1, tzinfo=_UTC),
            ttl_seconds=60,
        )
        original = self._disk_path().read_text(encoding='utf-8')
        refreshed = _with_extra_fiction_winner(stale)
        with patch.object(pulitzer, '_load_live_archive', return_value=refreshed):
            results = pulitzer.lookup('Beloved', 'Toni Morrison')
        self._assert_beloved(results)
        updated = self._disk_path().read_text(encoding='utf-8')
        self.assertNotEqual(updated, original)
        extra = pulitzer.lookup('Breathing Lessons', 'Anne Tyler')
        self.assertEqual(len(extra), 1)
        self.assertEqual(extra[0].award_year, 1989)

    def test_stale_cache_claims_refresh_slot_inside_lookup_budget(self):
        stale = _complete_archive()
        _save_disk(
            stale,
            generated_at=datetime(2020, 1, 1, tzinfo=_UTC),
            ttl_seconds=60,
        )
        pulitzer._reset_runtime_state()
        refreshed = _complete_archive(beloved=False)
        with cache.lookup_refresh_budget():
            with patch.object(
                pulitzer, '_load_live_archive', return_value=refreshed
            ):
                results = pulitzer.lookup('Jazz', 'Toni Morrison')
            self.assertEqual(results[0].work_title, 'Jazz')
            self.assertFalse(cache.try_claim_stale_refresh())

    def test_stale_cache_live_403_uses_stale_and_keeps_file(self):
        stale = _complete_archive()
        _save_disk(
            stale,
            generated_at=datetime(2020, 1, 1, tzinfo=_UTC),
            ttl_seconds=60,
        )
        original = self._disk_path().read_text(encoding='utf-8')
        with patch.object(pulitzer, '_load_live_archive', side_effect=_blocked()):
            results = pulitzer.lookup('Beloved', 'Toni Morrison')
        self._assert_beloved(results)
        self.assertEqual(self._disk_path().read_text(encoding='utf-8'), original)

    def test_stale_cache_without_refresh_slot_uses_stale_and_skips_network(self):
        stale = _complete_archive()
        _save_disk(
            stale,
            generated_at=datetime(2020, 1, 1, tzinfo=_UTC),
            ttl_seconds=60,
        )
        pulitzer._reset_runtime_state()
        with cache.lookup_refresh_budget():
            self.assertTrue(cache.try_claim_stale_refresh())
            with patch.object(
                pulitzer, '_load_live_archive', side_effect=AssertionError('live')
            ) as mocked, patch.object(
                pulitzer, '_fetch_html', side_effect=AssertionError('network')
            ):
                results = pulitzer.lookup('Beloved', 'Toni Morrison')
            mocked.assert_not_called()
        self._assert_beloved(results)

    def test_missing_cache_live_fetches_after_stale_refresh_budget_consumed(self):
        self.assertFalse(self._disk_path().is_file())
        live = _complete_archive()
        with cache.lookup_refresh_budget():
            self.assertTrue(cache.try_claim_stale_refresh())
            with patch.object(
                pulitzer, '_load_live_archive', return_value=live
            ) as mocked:
                results = pulitzer.lookup('Beloved', 'Toni Morrison')
            self.assertEqual(mocked.call_count, 1)
        self._assert_beloved(results)

    def test_no_cache_live_403_still_raises(self):
        self.assertFalse(self._disk_path().is_file())
        with patch.object(pulitzer, '_load_live_archive', side_effect=_blocked()):
            with self.assertRaises(pulitzer.PulitzerSourceError) as raised:
                pulitzer.lookup('Beloved', 'Toni Morrison')
        self.assertIn('HTTP 403', str(raised.exception))
        self.assertIsNone(pulitzer._archive_records_cache)
        self.assertFalse(self._disk_path().is_file())

    def test_malformed_disk_live_403_still_raises(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        self._rewrite_records(
            lambda payload: payload['records'][0].__setitem__('award_year', 0)
        )
        with patch.object(
            pulitzer, '_load_live_archive', side_effect=_blocked()
        ) as mocked:
            with self.assertRaises(pulitzer.PulitzerSourceError) as raised:
                pulitzer.lookup('Beloved', 'Toni Morrison')
        self.assertEqual(mocked.call_count, 1)
        self.assertIn('HTTP 403', str(raised.exception))

    def test_unsupported_category_is_rejected(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        self._rewrite_records(
            lambda payload: payload['records'][0].__setitem__(
                'category', 'Poetry'
            )
        )
        live = _complete_archive()
        with patch.object(
            pulitzer, '_load_live_archive', return_value=live
        ) as mocked:
            pulitzer.lookup('Beloved', 'Toni Morrison')
        self.assertEqual(mocked.call_count, 1)

    def test_bad_award_year_is_rejected(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        self._rewrite_records(
            lambda payload: payload['records'][0].__setitem__('award_year', 0)
        )
        live = _complete_archive()
        with patch.object(
            pulitzer, '_load_live_archive', return_value=live
        ) as mocked:
            pulitzer.lookup('Beloved', 'Toni Morrison')
        self.assertEqual(mocked.call_count, 1)

    def test_invalid_status_is_rejected(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        self._rewrite_records(
            lambda payload: payload['records'][0].__setitem__('status', 'Nominee')
        )
        live = _complete_archive()
        with patch.object(
            pulitzer, '_load_live_archive', return_value=live
        ) as mocked:
            pulitzer.lookup('Beloved', 'Toni Morrison')
        self.assertEqual(mocked.call_count, 1)

    def test_missing_winner_coverage_is_rejected(self):
        archive = _complete_archive()
        fiction_only_finalists = []
        for record in archive:
            if record.category == 'Fiction' and record.status == 'Winner':
                fiction_only_finalists.append(
                    pulitzer._ParsedRecord(
                        award_year=record.award_year,
                        category=record.category,
                        status='Finalist',
                        work_title=record.work_title,
                        work_author=record.work_author,
                        source_url=pulitzer.FICTION_URL,
                    )
                )
            else:
                fiction_only_finalists.append(record)
        cache.save_source_cache(
            pulitzer.SOURCE_KEY,
            pulitzer.CACHE_VERSION,
            records=[
                pulitzer._record_to_cache_dict(record)
                for record in fiction_only_finalists
            ],
            source_urls=pulitzer._archive_source_urls(),
            coverage={'winner_count': 0},
            ttl_seconds=pulitzer.CACHE_TTL_SECONDS,
            generated_at=datetime.now(_UTC),
        )
        live = _complete_archive()
        with patch.object(
            pulitzer, '_load_live_archive', return_value=live
        ) as mocked:
            results = pulitzer.lookup('Beloved', 'Toni Morrison')
        self.assertEqual(mocked.call_count, 1)
        self._assert_beloved(results)

    def test_off_host_source_url_is_rejected(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        self._rewrite_records(
            lambda payload: payload['records'][0].__setitem__(
                'source_url', 'https://example.com/winners/toni-morrison'
            )
        )
        live = _complete_archive()
        with patch.object(
            pulitzer, '_load_live_archive', return_value=live
        ) as mocked:
            pulitzer.lookup('Beloved', 'Toni Morrison')
        self.assertEqual(mocked.call_count, 1)

    def test_malformed_field_is_rejected(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        self._rewrite_records(
            lambda payload: payload['records'][0].pop('work_title')
        )
        live = _complete_archive()
        with patch.object(
            pulitzer, '_load_live_archive', return_value=live
        ) as mocked:
            pulitzer.lookup('Beloved', 'Toni Morrison')
        self.assertEqual(mocked.call_count, 1)

    def test_novel_fiction_boundary_violation_is_rejected(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))

        def _mutate(payload):
            for item in payload['records']:
                if item['category'] == 'Fiction':
                    item['award_year'] = 1940
                    break

        self._rewrite_records(_mutate)
        live = _complete_archive()
        with patch.object(
            pulitzer, '_load_live_archive', return_value=live
        ) as mocked:
            pulitzer.lookup('Beloved', 'Toni Morrison')
        self.assertEqual(mocked.call_count, 1)

    def test_incomplete_archive_is_rejected(self):
        fiction = [
            record
            for record in _complete_archive()
            if record.category == 'Fiction'
        ]
        cache.save_source_cache(
            pulitzer.SOURCE_KEY,
            pulitzer.CACHE_VERSION,
            records=[pulitzer._record_to_cache_dict(record) for record in fiction],
            source_urls=pulitzer._archive_source_urls(),
            coverage={'categories': ['Fiction']},
            ttl_seconds=pulitzer.CACHE_TTL_SECONDS,
            generated_at=datetime.now(_UTC),
        )
        live = _complete_archive()
        with patch.object(
            pulitzer, '_load_live_archive', return_value=live
        ) as mocked:
            results = pulitzer.lookup('Beloved', 'Toni Morrison')
        self.assertEqual(mocked.call_count, 1)
        self._assert_beloved(results)

    def test_version_mismatch_uses_live_path(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC), version=2)
        live = _complete_archive()
        with patch.object(
            pulitzer, '_load_live_archive', return_value=live
        ) as mocked:
            results = pulitzer.lookup('Beloved', 'Toni Morrison')
        self.assertEqual(mocked.call_count, 1)
        self._assert_beloved(results)

    def test_save_failure_does_not_fail_lookup(self):
        archive = _complete_archive()
        with patch.object(pulitzer, '_load_live_archive', return_value=archive):
            with patch.object(
                pulitzer.cache,
                'save_source_cache',
                side_effect=OSError('disk full'),
            ):
                results = pulitzer.lookup('Beloved', 'Toni Morrison')
        self._assert_beloved(results)

    def test_ram_reset_does_not_delete_disk_cache(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        pulitzer._archive_records_cache = archive
        self.assertTrue(self._disk_path().is_file())
        pulitzer._reset_runtime_state()
        self.assertTrue(self._disk_path().is_file())
        self.assertIsNone(pulitzer._archive_records_cache)
        with patch.object(
            pulitzer, '_load_live_archive', side_effect=AssertionError('live')
        ), patch.object(
            pulitzer, '_fetch_html', side_effect=AssertionError('network')
        ):
            results = pulitzer.lookup('Beloved', 'Toni Morrison')
        self._assert_beloved(results)


class PulitzerSixSourceRefreshBudgetTests(unittest.TestCase):
    def setUp(self):
        pulitzer._reset_runtime_state()
        nobel._reset_runtime_state()
        newbery._reset_runtime_state()
        hugo._reset_runtime_state()
        world_fantasy._reset_runtime_state()
        nebula._clear_caches_for_tests()
        cache._reset_runtime_state()
        self._temp = TemporaryDirectory()
        cache.set_cache_directory(Path(self._temp.name))
        self._nebula_tests = _load_test_module('test_nebula_cache')
        self._wfa_tests = _load_test_module('test_world_fantasy_cache')
        self._hugo_tests = _load_test_module('test_hugo_cache')
        self._newbery_tests = _load_test_module('test_newbery_cache')
        self._nobel_tests = _load_test_module('test_nobel_cache')

    def tearDown(self):
        pulitzer._reset_runtime_state()
        nobel._reset_runtime_state()
        newbery._reset_runtime_state()
        hugo._reset_runtime_state()
        world_fantasy._reset_runtime_state()
        nebula._clear_caches_for_tests()
        cache._reset_runtime_state()
        self._temp.cleanup()

    def test_one_optional_refresh_among_six_stale_sources(self):
        pulitzer_stale = _complete_archive()
        nobel_stale = self._nobel_tests._complete_archive()
        nebula_stale = self._nebula_tests._complete_archive()
        wfa_stale = self._wfa_tests._complete_archive()
        hugo_stale = self._hugo_tests._complete_archive()
        newbery_stale = self._newbery_tests._complete_archive()
        stale_at = datetime(2020, 1, 1, tzinfo=_UTC)
        _save_disk(pulitzer_stale, generated_at=stale_at, ttl_seconds=60)
        self._nobel_tests._save_disk(
            nobel_stale, generated_at=stale_at, ttl_seconds=60
        )
        self._nebula_tests._save_disk(
            nebula_stale, generated_at=stale_at, ttl_seconds=60
        )
        self._wfa_tests._save_disk(
            wfa_stale, generated_at=stale_at, ttl_seconds=60
        )
        self._hugo_tests._save_disk(
            hugo_stale, generated_at=stale_at, ttl_seconds=60
        )
        self._newbery_tests._save_disk(
            newbery_stale, generated_at=stale_at, ttl_seconds=60
        )
        pulitzer._reset_runtime_state()
        nobel._reset_runtime_state()
        newbery._reset_runtime_state()
        hugo._reset_runtime_state()
        world_fantasy._reset_runtime_state()
        nebula._clear_caches_for_tests()

        enabled = (
            'nebula',
            'world_fantasy',
            'hugo',
            'newbery',
            'nobel',
            'pulitzer',
        )
        with patch.object(
            nebula, '_load_live_archive', return_value=nebula_stale
        ) as nebula_live, patch.object(
            world_fantasy, '_load_live_archive', return_value=wfa_stale
        ) as wfa_live, patch.object(
            hugo, '_load_live_archive', return_value=hugo_stale
        ) as hugo_live, patch.object(
            newbery, '_load_live_archive', return_value=newbery_stale
        ) as newbery_live, patch.object(
            nobel, '_load_live_archive', return_value=nobel_stale
        ) as nobel_live, patch.object(
            pulitzer, '_load_live_archive', return_value=pulitzer_stale
        ) as pulitzer_live:
            first = lookup_awards(
                'Dune',
                'Frank Herbert',
                enabled_source_keys=enabled,
            )
            self.assertEqual(len(first.failures), 0)
            first_counts = (
                nebula_live.call_count,
                wfa_live.call_count,
                hugo_live.call_count,
                newbery_live.call_count,
                nobel_live.call_count,
                pulitzer_live.call_count,
            )
            self.assertEqual(sum(first_counts), 1)

            pulitzer._reset_runtime_state()
            nobel._reset_runtime_state()
            newbery._reset_runtime_state()
            hugo._reset_runtime_state()
            world_fantasy._reset_runtime_state()
            nebula._clear_caches_for_tests()
            second = lookup_awards(
                'Dune',
                'Frank Herbert',
                enabled_source_keys=enabled,
            )
            self.assertEqual(len(second.failures), 0)
            second_counts = (
                nebula_live.call_count - first_counts[0],
                wfa_live.call_count - first_counts[1],
                hugo_live.call_count - first_counts[2],
                newbery_live.call_count - first_counts[3],
                nobel_live.call_count - first_counts[4],
                pulitzer_live.call_count - first_counts[5],
            )
            self.assertEqual(sum(second_counts), 1)
            for first_n, second_n in zip(first_counts, second_counts):
                if first_n:
                    self.assertEqual(second_n, 0)


if __name__ == '__main__':
    unittest.main()
