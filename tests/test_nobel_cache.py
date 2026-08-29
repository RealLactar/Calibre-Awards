"""Offline coverage for Nobel persistent laureate-archive cache."""

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
from awards.sources import hugo, nebula, newbery, nobel, world_fantasy

_UTC = timezone.utc
_TESTS_DIR = Path(__file__).resolve().parent

HEMINGWAY_FACTS_URL = (
    'https://www.nobelprize.org/prizes/literature/1954/hemingway/facts/'
)
SARTRE_FACTS_URL = (
    'https://www.nobelprize.org/prizes/literature/1964/sartre/facts/'
)
PASTERNAK_FACTS_URL = (
    'https://www.nobelprize.org/prizes/literature/1958/pasternak/facts/'
)
NERUDA_FACTS_URL = (
    'https://www.nobelprize.org/prizes/literature/1971/neruda/facts/'
)


def _load_test_module(name: str):
    path = _TESTS_DIR / f'{name}.py'
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_FIXTURE_BODY: str | None = None


def _fixture_body() -> str:
    global _FIXTURE_BODY
    if _FIXTURE_BODY is None:
        path = _TESTS_DIR / 'test_nobel_parser.py'
        spec = importlib.util.spec_from_file_location(
            '_nobel_parser_fixture_source', path
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _FIXTURE_BODY = module.FIXTURE_BODY
    return _FIXTURE_BODY


def _complete_archive():
    return nobel._parse_laureates_payload(200, _fixture_body())


def _with_extra_laureate(archive):
    extra = nobel._Laureate(
        laureate_id='569',
        known_name='Sully Prudhomme',
        match_names=(
            'Sully Prudhomme',
            'René François Armand Prudhomme',
        ),
        prize=nobel._LiteraturePrize(
            award_year=1901,
            prize_status='received',
            source_url=(
                'https://www.nobelprize.org/prizes/literature/1901/'
                'prudhomme/facts/'
            ),
            notes=None,
        ),
    )
    return archive + (extra,)


def _save_disk(records, *, generated_at=None, ttl_seconds=None, version=None):
    cache.save_source_cache(
        nobel.SOURCE_KEY,
        nobel.CACHE_VERSION if version is None else version,
        records=[nobel._record_to_cache_dict(record) for record in records],
        source_urls=nobel._archive_source_urls(),
        coverage=nobel._coverage_from_records(records),
        ttl_seconds=(
            nobel.CACHE_TTL_SECONDS if ttl_seconds is None else ttl_seconds
        ),
        generated_at=generated_at,
    )


class NobelPersistentCacheTests(unittest.TestCase):
    def setUp(self):
        nobel._reset_runtime_state()
        cache._reset_runtime_state()
        self._temp = TemporaryDirectory()
        self.cache_dir = Path(self._temp.name)
        cache.set_cache_directory(self.cache_dir)

    def tearDown(self):
        nobel._reset_runtime_state()
        cache._reset_runtime_state()
        self._temp.cleanup()

    def _disk_path(self):
        return self.cache_dir / 'nobel.json'

    def _assert_hemingway_author_result(self, results):
        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertEqual(result.work_title, 'Ernest Hemingway')
        self.assertEqual(result.work_author, 'Ernest Hemingway')
        self.assertEqual(result.award_name, 'Nobel Prize')
        self.assertEqual(result.award_year, 1954)
        self.assertEqual(result.category, 'Literature')
        self.assertEqual(result.status, 'Winner')
        self.assertIsNone(result.rank)
        self.assertEqual(result.source_name, 'NobelPrize.org')
        self.assertEqual(result.source_url, HEMINGWAY_FACTS_URL)
        self.assertIsNone(result.notes)
        self.assertEqual(result.identity_kind, 'author')
        self.assertFalse(result.is_specifically_cited_work)

    def test_cache_identity_constants(self):
        self.assertEqual(nobel.SOURCE_KEY, 'nobel')
        self.assertEqual(nobel.CACHE_VERSION, 1)
        self.assertEqual(nobel.CACHE_BASE_TTL_SECONDS, 7 * 24 * 60 * 60)
        self.assertEqual(nobel.CACHE_REFRESH_OFFSET_SECONDS, 4 * 60 * 60)
        self.assertEqual(
            nobel.CACHE_TTL_SECONDS,
            nobel.CACHE_BASE_TTL_SECONDS + nobel.CACHE_REFRESH_OFFSET_SECONDS,
        )
        self.assertEqual(nobel.CACHE_TTL_SECONDS, 619200)

    def test_complete_archive_helper_passes_source_validation(self):
        nobel._validate_cached_archive(_complete_archive())

    def test_laureate_round_trips_all_fields(self):
        original = nobel._Laureate(
            laureate_id='645',
            known_name='Pablo Neruda',
            match_names=(
                'Pablo Neruda',
                'Neftalí Ricardo Reyes Basoalto',
            ),
            prize=nobel._LiteraturePrize(
                award_year=1971,
                prize_status='received',
                source_url=NERUDA_FACTS_URL,
                notes=None,
            ),
        )
        restored = nobel._record_from_cache_dict(
            nobel._record_to_cache_dict(original)
        )
        self.assertEqual(restored, original)
        self.assertIsInstance(restored.match_names, tuple)
        self.assertEqual(restored.match_names, original.match_names)
        self.assertIsInstance(restored.prize, nobel._LiteraturePrize)
        self.assertEqual(restored.prize, original.prize)

    def test_nested_prize_notes_round_trip_for_non_received_status(self):
        declined = nobel._Laureate(
            laureate_id='637',
            known_name='Jean-Paul Sartre',
            match_names=('Jean-Paul Sartre',),
            prize=nobel._LiteraturePrize(
                award_year=1964,
                prize_status='declined',
                source_url=SARTRE_FACTS_URL,
                notes='Nobel Prize status: declined.',
            ),
        )
        restricted = nobel._Laureate(
            laureate_id='629',
            known_name='Boris Pasternak',
            match_names=('Boris Pasternak', 'Boris Leonidovich Pasternak'),
            prize=nobel._LiteraturePrize(
                award_year=1958,
                prize_status='restricted',
                source_url=PASTERNAK_FACTS_URL,
                notes='Nobel Prize status: restricted.',
            ),
        )
        for original in (declined, restricted):
            restored = nobel._record_from_cache_dict(
                nobel._record_to_cache_dict(original)
            )
            self.assertEqual(restored, original)
            self.assertEqual(restored.prize.notes, original.prize.notes)

    def test_record_order_is_preserved(self):
        archive = _complete_archive()
        restored = nobel._records_from_cache_payload(
            {
                'records': [
                    nobel._record_to_cache_dict(record) for record in archive
                ],
                'source_urls': list(nobel._archive_source_urls()),
            }
        )
        self.assertEqual(restored, archive)
        self.assertEqual(
            [record.laureate_id for record in restored[:3]],
            [record.laureate_id for record in archive[:3]],
        )
        self.assertEqual(
            [record.known_name for record in restored[:3]],
            [record.known_name for record in archive[:3]],
        )

    def test_fresh_cache_lookup_makes_zero_network_calls(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        nobel._reset_runtime_state()
        with patch.object(
            nobel, '_request_json', side_effect=AssertionError('network')
        ), patch.object(
            nobel, '_load_live_archive', side_effect=AssertionError('live')
        ):
            results = nobel.lookup(
                'For Whom the Bell Tolls', 'Ernest Hemingway'
            )
        self._assert_hemingway_author_result(results)
        cited = nobel.lookup('The Old Man and the Sea', 'Ernest Hemingway')
        self.assertEqual(len(cited), 1)
        self.assertEqual(cited[0].work_title, 'The Old Man and the Sea')
        self.assertEqual(cited[0].identity_kind, 'work')
        self.assertTrue(cited[0].is_specifically_cited_work)
        self.assertEqual(cited[0].source_url, HEMINGWAY_FACTS_URL)

    def test_fresh_cache_does_not_consume_refresh_budget(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        nobel._reset_runtime_state()
        with cache.lookup_refresh_budget():
            with patch.object(
                nobel, '_load_live_archive', side_effect=AssertionError('live')
            ):
                results = nobel.lookup(
                    'For Whom the Bell Tolls', 'Ernest Hemingway'
                )
            self._assert_hemingway_author_result(results)
            self.assertTrue(cache.try_claim_stale_refresh())

    def test_restart_simulation_reloads_disk_after_ram_clear(self):
        archive = _complete_archive()
        with patch.object(
            nobel, '_load_live_archive', return_value=archive
        ) as live:
            first = nobel.lookup(
                'For Whom the Bell Tolls', 'Ernest Hemingway'
            )
        self._assert_hemingway_author_result(first)
        self.assertEqual(live.call_count, 1)
        self.assertTrue(self._disk_path().is_file())
        nobel._reset_runtime_state()
        self.assertTrue(self._disk_path().is_file())
        with patch.object(
            nobel, '_request_json', side_effect=AssertionError('network')
        ), patch.object(
            nobel, '_load_live_archive', side_effect=AssertionError('live')
        ):
            second = nobel.lookup(
                'For Whom the Bell Tolls', 'Ernest Hemingway'
            )
        self._assert_hemingway_author_result(second)

    def test_stale_cache_successful_refresh_replaces_disk(self):
        stale = _complete_archive()
        _save_disk(
            stale,
            generated_at=datetime(2020, 1, 1, tzinfo=_UTC),
            ttl_seconds=60,
        )
        original = self._disk_path().read_text(encoding='utf-8')
        refreshed = _with_extra_laureate(stale)
        with patch.object(nobel, '_load_live_archive', return_value=refreshed):
            results = nobel.lookup(
                'For Whom the Bell Tolls', 'Ernest Hemingway'
            )
        self._assert_hemingway_author_result(results)
        updated = self._disk_path().read_text(encoding='utf-8')
        self.assertNotEqual(updated, original)
        payload = json.loads(updated)
        ids = [item['laureate_id'] for item in payload['records']]
        self.assertIn('569', ids)
        extra = nobel.lookup('Les Destinées', 'Sully Prudhomme')
        self.assertEqual(len(extra), 1)
        self.assertEqual(extra[0].work_author, 'Sully Prudhomme')
        self.assertEqual(extra[0].award_year, 1901)

    def test_stale_cache_claims_refresh_slot_inside_lookup_budget(self):
        stale = _complete_archive()
        _save_disk(
            stale,
            generated_at=datetime(2020, 1, 1, tzinfo=_UTC),
            ttl_seconds=60,
        )
        nobel._reset_runtime_state()
        refreshed = _with_extra_laureate(stale)
        with cache.lookup_refresh_budget():
            with patch.object(
                nobel, '_load_live_archive', return_value=refreshed
            ):
                results = nobel.lookup(
                    'For Whom the Bell Tolls', 'Ernest Hemingway'
                )
            self._assert_hemingway_author_result(results)
            self.assertFalse(cache.try_claim_stale_refresh())

    def test_stale_cache_failed_refresh_uses_stale_and_keeps_file(self):
        stale = _complete_archive()
        _save_disk(
            stale,
            generated_at=datetime(2020, 1, 1, tzinfo=_UTC),
            ttl_seconds=60,
        )
        original = self._disk_path().read_text(encoding='utf-8')
        with patch.object(
            nobel,
            '_load_live_archive',
            side_effect=nobel.NobelSourceError('api down'),
        ):
            results = nobel.lookup(
                'For Whom the Bell Tolls', 'Ernest Hemingway'
            )
        self._assert_hemingway_author_result(results)
        self.assertEqual(self._disk_path().read_text(encoding='utf-8'), original)

    def test_stale_cache_without_refresh_slot_uses_stale_and_skips_network(self):
        stale = _complete_archive()
        _save_disk(
            stale,
            generated_at=datetime(2020, 1, 1, tzinfo=_UTC),
            ttl_seconds=60,
        )
        nobel._reset_runtime_state()
        with cache.lookup_refresh_budget():
            self.assertTrue(cache.try_claim_stale_refresh())
            with patch.object(
                nobel, '_load_live_archive', side_effect=AssertionError('live')
            ) as mocked:
                results = nobel.lookup(
                    'For Whom the Bell Tolls', 'Ernest Hemingway'
                )
            mocked.assert_not_called()
        self._assert_hemingway_author_result(results)

    def test_missing_cache_live_fetches_after_stale_refresh_budget_consumed(self):
        self.assertFalse(self._disk_path().is_file())
        live = _complete_archive()
        with cache.lookup_refresh_budget():
            self.assertTrue(cache.try_claim_stale_refresh())
            with patch.object(
                nobel, '_load_live_archive', return_value=live
            ) as mocked:
                results = nobel.lookup(
                    'For Whom the Bell Tolls', 'Ernest Hemingway'
                )
            self.assertEqual(mocked.call_count, 1)
        self._assert_hemingway_author_result(results)

    def test_bad_award_year_is_rejected(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        payload = json.loads(self._disk_path().read_text(encoding='utf-8'))
        payload['records'][0]['prize']['award_year'] = 0
        self._disk_path().write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
            + '\n',
            encoding='utf-8',
        )
        live = _complete_archive()
        with patch.object(
            nobel, '_load_live_archive', return_value=live
        ) as mocked:
            results = nobel.lookup(
                'For Whom the Bell Tolls', 'Ernest Hemingway'
            )
        self.assertEqual(mocked.call_count, 1)
        self._assert_hemingway_author_result(results)

    def test_missing_known_name_is_rejected(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        payload = json.loads(self._disk_path().read_text(encoding='utf-8'))
        del payload['records'][0]['known_name']
        self._disk_path().write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
            + '\n',
            encoding='utf-8',
        )
        live = _complete_archive()
        with patch.object(
            nobel, '_load_live_archive', return_value=live
        ) as mocked:
            nobel.lookup('For Whom the Bell Tolls', 'Ernest Hemingway')
        self.assertEqual(mocked.call_count, 1)

    def test_malformed_nested_prize_is_rejected(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        payload = json.loads(self._disk_path().read_text(encoding='utf-8'))
        payload['records'][0]['prize'] = 'not a prize object'
        self._disk_path().write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
            + '\n',
            encoding='utf-8',
        )
        live = _complete_archive()
        with patch.object(
            nobel, '_load_live_archive', return_value=live
        ) as mocked:
            nobel.lookup('For Whom the Bell Tolls', 'Ernest Hemingway')
        self.assertEqual(mocked.call_count, 1)

    def test_malformed_match_names_is_rejected(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        payload = json.loads(self._disk_path().read_text(encoding='utf-8'))
        payload['records'][0]['match_names'] = 'Ernest Hemingway'
        self._disk_path().write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
            + '\n',
            encoding='utf-8',
        )
        live = _complete_archive()
        with patch.object(
            nobel, '_load_live_archive', return_value=live
        ) as mocked:
            nobel.lookup('For Whom the Bell Tolls', 'Ernest Hemingway')
        self.assertEqual(mocked.call_count, 1)

    def test_unexpected_category_field_is_rejected(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        payload = json.loads(self._disk_path().read_text(encoding='utf-8'))
        payload['records'][0]['category'] = 'Physics'
        self._disk_path().write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
            + '\n',
            encoding='utf-8',
        )
        live = _complete_archive()
        with patch.object(
            nobel, '_load_live_archive', return_value=live
        ) as mocked:
            nobel.lookup('For Whom the Bell Tolls', 'Ernest Hemingway')
        self.assertEqual(mocked.call_count, 1)

    def test_off_host_source_url_is_rejected(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        payload = json.loads(self._disk_path().read_text(encoding='utf-8'))
        payload['records'][0]['prize']['source_url'] = (
            'https://example.com/laureate/625'
        )
        self._disk_path().write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
            + '\n',
            encoding='utf-8',
        )
        live = _complete_archive()
        with patch.object(
            nobel, '_load_live_archive', return_value=live
        ) as mocked:
            nobel.lookup('For Whom the Bell Tolls', 'Ernest Hemingway')
        self.assertEqual(mocked.call_count, 1)

    def test_notes_status_mismatch_is_rejected(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        payload = json.loads(self._disk_path().read_text(encoding='utf-8'))
        payload['records'][0]['prize']['notes'] = 'Nobel Prize status: declined.'
        self._disk_path().write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
            + '\n',
            encoding='utf-8',
        )
        live = _complete_archive()
        with patch.object(
            nobel, '_load_live_archive', return_value=live
        ) as mocked:
            nobel.lookup('For Whom the Bell Tolls', 'Ernest Hemingway')
        self.assertEqual(mocked.call_count, 1)

    def test_incomplete_cited_work_coverage_is_rejected(self):
        hemingway = [
            record
            for record in _complete_archive()
            if record.laureate_id == '625'
        ]
        cache.save_source_cache(
            nobel.SOURCE_KEY,
            nobel.CACHE_VERSION,
            records=[nobel._record_to_cache_dict(hemingway[0])],
            source_urls=nobel._archive_source_urls(),
            coverage={'laureate_count': 1},
            ttl_seconds=nobel.CACHE_TTL_SECONDS,
            generated_at=datetime.now(_UTC),
        )
        live = _complete_archive()
        with patch.object(
            nobel, '_load_live_archive', return_value=live
        ) as mocked:
            results = nobel.lookup(
                'For Whom the Bell Tolls', 'Ernest Hemingway'
            )
        self.assertEqual(mocked.call_count, 1)
        self._assert_hemingway_author_result(results)

    def test_version_mismatch_uses_live_path(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC), version=2)
        live = _complete_archive()
        with patch.object(
            nobel, '_load_live_archive', return_value=live
        ) as mocked:
            results = nobel.lookup(
                'For Whom the Bell Tolls', 'Ernest Hemingway'
            )
        self.assertEqual(mocked.call_count, 1)
        self._assert_hemingway_author_result(results)

    def test_save_failure_does_not_fail_lookup(self):
        archive = _complete_archive()
        with patch.object(nobel, '_load_live_archive', return_value=archive):
            with patch.object(
                nobel.cache,
                'save_source_cache',
                side_effect=OSError('disk full'),
            ):
                results = nobel.lookup(
                    'For Whom the Bell Tolls', 'Ernest Hemingway'
                )
        self._assert_hemingway_author_result(results)

    def test_ram_reset_does_not_delete_disk_cache(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        nobel._laureates_cache = archive
        self.assertTrue(self._disk_path().is_file())
        nobel._reset_runtime_state()
        self.assertTrue(self._disk_path().is_file())
        self.assertIsNone(nobel._laureates_cache)
        with patch.object(
            nobel, '_load_live_archive', side_effect=AssertionError('live')
        ), patch.object(
            nobel, '_request_json', side_effect=AssertionError('network')
        ):
            results = nobel.lookup(
                'For Whom the Bell Tolls', 'Ernest Hemingway'
            )
        self._assert_hemingway_author_result(results)


class NobelFiveSourceRefreshBudgetTests(unittest.TestCase):
    def setUp(self):
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

    def tearDown(self):
        nobel._reset_runtime_state()
        newbery._reset_runtime_state()
        hugo._reset_runtime_state()
        world_fantasy._reset_runtime_state()
        nebula._clear_caches_for_tests()
        cache._reset_runtime_state()
        self._temp.cleanup()

    def test_one_optional_refresh_among_five_stale_sources(self):
        nobel_stale = _complete_archive()
        nebula_stale = self._nebula_tests._complete_archive()
        wfa_stale = self._wfa_tests._complete_archive()
        hugo_stale = self._hugo_tests._complete_archive()
        newbery_stale = self._newbery_tests._complete_archive()
        stale_at = datetime(2020, 1, 1, tzinfo=_UTC)
        _save_disk(nobel_stale, generated_at=stale_at, ttl_seconds=60)
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
        ) as nobel_live:
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
            )
            self.assertEqual(sum(first_counts), 1)

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
            )
            self.assertEqual(sum(second_counts), 1)
            for first_n, second_n in zip(first_counts, second_counts):
                if first_n:
                    self.assertEqual(second_n, 0)


if __name__ == '__main__':
    unittest.main()
