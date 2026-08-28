"""Offline coverage for Hugo persistent archive cache."""

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
from awards.sources import hugo, nebula, world_fantasy

_UTC = timezone.utc
_TESTS_DIR = Path(__file__).resolve().parent


def _load_test_module(name: str):
    path = _TESTS_DIR / f'{name}.py'
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _year_page_url(year: int) -> str:
    return f'https://www.thehugoawards.org/hugo-history/{year}-hugo-awards/'


def _hugo_record(
    year,
    category,
    status,
    title,
    author,
    *,
    source_url=None,
    match_titles=None,
):
    return hugo._ParsedRecord(
        award_year=year,
        category=category,
        status=status,
        work_title=title,
        work_author=author,
        source_url=_year_page_url(year) if source_url is None else source_url,
        match_titles=(title,) if match_titles is None else match_titles,
    )


def _complete_archive(*, dune=True):
    records: list[hugo._ParsedRecord] = []

    def _add(year, category, title, author='Pat Author', status='Winner'):
        records.append(_hugo_record(year, category, status, title, author))

    for year in sorted(hugo._required_cached_regular_years()):
        if hugo._year_requires_best_novel(year):
            if dune and year == 1966:
                _add(year, hugo.CATEGORY_BEST_NOVEL, 'Dune', 'Frank Herbert')
            else:
                _add(year, hugo.CATEGORY_BEST_NOVEL, f'Novel {year}')
        if year >= hugo._NOVELLA_REQUIRED_FROM_YEAR:
            _add(year, hugo.CATEGORY_BEST_NOVELLA, f'Novella {year}')
        if hugo._year_requires_novelette(year):
            _add(year, hugo.CATEGORY_BEST_NOVELETTE, f'Novelette {year}')
        if hugo._year_requires_short_story(year):
            _add(year, hugo.CATEGORY_BEST_SHORT_STORY, f'Short Story {year}')
        if hugo._year_requires_short_fiction(year):
            _add(year, hugo.CATEGORY_SHORT_FICTION, f'Short Fiction {year}')
        if hugo._year_requires_novel_or_novelette(year):
            _add(
                year,
                hugo.CATEGORY_BEST_NOVEL_OR_NOVELETTE,
                f'Novel or Novelette {year}',
            )
        if hugo._year_requires_best_series(year):
            _add(year, hugo.CATEGORY_BEST_SERIES, f'Series {year}')
        if hugo._year_requires_best_all_time_series(year):
            _add(
                year,
                hugo.CATEGORY_BEST_ALL_TIME_SERIES,
                f'All-Time Series {year}',
            )
        if hugo._year_requires_best_poem(year):
            _add(year, hugo.CATEGORY_BEST_POEM, f'Poem {year}')
        if hugo._year_requires_best_related_non_fiction_book(year):
            _add(
                year,
                hugo.CATEGORY_BEST_RELATED_NON_FICTION_BOOK,
                f'Related Non-Fiction {year}',
            )
        if hugo._year_requires_best_related_book(year):
            _add(year, hugo.CATEGORY_BEST_RELATED_BOOK, f'Related Book {year}')
    return tuple(records)


def _save_disk(records, *, generated_at=None, ttl_seconds=None, version=None):
    cache.save_source_cache(
        hugo.SOURCE_KEY,
        hugo.CACHE_VERSION if version is None else version,
        records=[hugo._record_to_cache_dict(record) for record in records],
        source_urls=hugo._archive_source_urls(),
        coverage=hugo._coverage_from_records(records),
        ttl_seconds=(
            hugo.CACHE_TTL_SECONDS if ttl_seconds is None else ttl_seconds
        ),
        generated_at=generated_at,
    )


class HugoPersistentCacheTests(unittest.TestCase):
    def setUp(self):
        hugo._reset_runtime_state()
        cache._reset_runtime_state()
        self._temp = TemporaryDirectory()
        self.cache_dir = Path(self._temp.name)
        cache.set_cache_directory(self.cache_dir)

    def tearDown(self):
        hugo._reset_runtime_state()
        cache._reset_runtime_state()
        self._temp.cleanup()

    def _disk_path(self):
        return self.cache_dir / 'hugo.json'

    def test_cache_identity_constants(self):
        self.assertEqual(hugo.SOURCE_KEY, 'hugo')
        self.assertEqual(hugo.CACHE_VERSION, 1)
        self.assertEqual(hugo.CACHE_BASE_TTL_SECONDS, 7 * 24 * 60 * 60)
        self.assertEqual(hugo.CACHE_REFRESH_OFFSET_SECONDS, 2 * 60 * 60)
        self.assertEqual(
            hugo.CACHE_TTL_SECONDS,
            hugo.CACHE_BASE_TTL_SECONDS + hugo.CACHE_REFRESH_OFFSET_SECONDS,
        )
        self.assertEqual(hugo.CACHE_TTL_SECONDS, 612000)

    def test_complete_archive_helper_passes_source_validation(self):
        hugo._validate_cached_archive(_complete_archive())

    def test_parsed_record_round_trips_all_fields(self):
        original = hugo._ParsedRecord(
            award_year=1966,
            category=hugo.CATEGORY_BEST_NOVEL,
            status='Winner',
            work_title='This Immortal',
            work_author='Roger Zelazny',
            source_url=_year_page_url(1966),
            match_titles=(
                'This Immortal',
                '...And Call Me Conrad (alt: This Immortal)',
                'This Immortal',
            ),
        )
        restored = hugo._record_from_cache_dict(
            hugo._record_to_cache_dict(original)
        )
        self.assertEqual(restored, original)
        self.assertIsInstance(restored.match_titles, tuple)
        self.assertEqual(restored.match_titles, original.match_titles)

    def test_record_order_is_preserved(self):
        archive = _complete_archive()
        restored = hugo._records_from_cache_payload(
            {
                'records': [
                    hugo._record_to_cache_dict(record) for record in archive
                ],
                'source_urls': list(hugo._archive_source_urls()),
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
        hugo._reset_runtime_state()
        with patch.object(
            hugo, '_fetch_archive_response', side_effect=AssertionError('network')
        ), patch.object(
            hugo, '_load_live_archive', side_effect=AssertionError('live')
        ):
            results = hugo.lookup('Dune', 'Frank Herbert')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].work_title, 'Dune')
        self.assertEqual(results[0].work_author, 'Frank Herbert')
        self.assertEqual(results[0].category, 'Best Novel')
        self.assertEqual(results[0].status, 'Winner')
        self.assertEqual(results[0].award_year, 1966)
        self.assertEqual(results[0].award_name, 'Hugo Award')
        self.assertEqual(results[0].source_name, 'Hugo Awards')
        self.assertEqual(results[0].source_url, _year_page_url(1966))
        self.assertEqual(hugo._archive_records_cache[0].award_year, 1953)

    def test_fresh_cache_does_not_consume_refresh_budget(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        hugo._reset_runtime_state()
        with cache.lookup_refresh_budget():
            with patch.object(
                hugo, '_load_live_archive', side_effect=AssertionError('live')
            ):
                results = hugo.lookup('Dune', 'Frank Herbert')
            self.assertEqual(results[0].work_title, 'Dune')
            self.assertTrue(cache.try_claim_stale_refresh())

    def test_restart_simulation_reloads_disk_after_ram_clear(self):
        archive = _complete_archive()
        with patch.object(
            hugo, '_load_live_archive', return_value=archive
        ) as live:
            first = hugo.lookup('Dune', 'Frank Herbert')
        self.assertEqual(len(first), 1)
        self.assertEqual(live.call_count, 1)
        self.assertTrue(self._disk_path().is_file())
        hugo._reset_runtime_state()
        self.assertTrue(self._disk_path().is_file())
        with patch.object(
            hugo, '_fetch_archive_response', side_effect=AssertionError('network')
        ), patch.object(
            hugo, '_load_live_archive', side_effect=AssertionError('live')
        ):
            second = hugo.lookup('Dune', 'Frank Herbert')
        self.assertEqual(len(second), 1)
        self.assertEqual(second[0].work_title, 'Dune')

    def test_stale_cache_successful_refresh_replaces_disk(self):
        stale = _complete_archive()
        _save_disk(
            stale,
            generated_at=datetime(2020, 1, 1, tzinfo=_UTC),
            ttl_seconds=60,
        )
        original = self._disk_path().read_text(encoding='utf-8')
        refreshed = _complete_archive(dune=False)
        with patch.object(hugo, '_load_live_archive', return_value=refreshed):
            results = hugo.lookup('Novel 1966', 'Pat Author')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].work_title, 'Novel 1966')
        updated = self._disk_path().read_text(encoding='utf-8')
        self.assertNotEqual(updated, original)
        payload = json.loads(updated)
        titles = [item['work_title'] for item in payload['records']]
        self.assertIn('Novel 1966', titles)
        self.assertNotIn('Dune', titles)

    def test_stale_cache_claims_refresh_slot_inside_lookup_budget(self):
        stale = _complete_archive()
        _save_disk(
            stale,
            generated_at=datetime(2020, 1, 1, tzinfo=_UTC),
            ttl_seconds=60,
        )
        hugo._reset_runtime_state()
        refreshed = _complete_archive(dune=False)
        with cache.lookup_refresh_budget():
            with patch.object(hugo, '_load_live_archive', return_value=refreshed):
                results = hugo.lookup('Novel 1966', 'Pat Author')
            self.assertEqual(results[0].work_title, 'Novel 1966')
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
            hugo,
            '_load_live_archive',
            side_effect=hugo.HugoSourceError('site down'),
        ):
            results = hugo.lookup('Dune', 'Frank Herbert')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].work_title, 'Dune')
        self.assertEqual(self._disk_path().read_text(encoding='utf-8'), original)

    def test_stale_cache_without_refresh_slot_uses_stale_and_skips_network(self):
        stale = _complete_archive()
        _save_disk(
            stale,
            generated_at=datetime(2020, 1, 1, tzinfo=_UTC),
            ttl_seconds=60,
        )
        hugo._reset_runtime_state()
        with cache.lookup_refresh_budget():
            self.assertTrue(cache.try_claim_stale_refresh())
            with patch.object(
                hugo, '_load_live_archive', side_effect=AssertionError('live')
            ) as mocked:
                results = hugo.lookup('Dune', 'Frank Herbert')
            mocked.assert_not_called()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].work_title, 'Dune')

    def test_missing_cache_live_fetches_after_stale_refresh_budget_consumed(self):
        self.assertFalse(self._disk_path().is_file())
        live = _complete_archive()
        with cache.lookup_refresh_budget():
            self.assertTrue(cache.try_claim_stale_refresh())
            with patch.object(
                hugo, '_load_live_archive', return_value=live
            ) as mocked:
                results = hugo.lookup('Dune', 'Frank Herbert')
            self.assertEqual(mocked.call_count, 1)
        self.assertEqual(results[0].work_title, 'Dune')

    def test_unsupported_category_is_rejected(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        payload = json.loads(self._disk_path().read_text(encoding='utf-8'))
        payload['records'][0]['category'] = 'Best Dramatic Presentation'
        self._disk_path().write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + '\n',
            encoding='utf-8',
        )
        live = _complete_archive()
        with patch.object(hugo, '_load_live_archive', return_value=live) as mocked:
            hugo.lookup('Dune', 'Frank Herbert')
        self.assertEqual(mocked.call_count, 1)

    def test_missing_historical_coverage_is_rejected(self):
        cache.save_source_cache(
            hugo.SOURCE_KEY,
            hugo.CACHE_VERSION,
            records=[
                hugo._record_to_cache_dict(
                    _hugo_record(
                        1966,
                        hugo.CATEGORY_BEST_NOVEL,
                        'Winner',
                        'Dune',
                        'Frank Herbert',
                    )
                )
            ],
            source_urls=hugo._archive_source_urls(),
            coverage={'categories': []},
            ttl_seconds=hugo.CACHE_TTL_SECONDS,
            generated_at=datetime.now(_UTC),
        )
        live = _complete_archive()
        with patch.object(hugo, '_load_live_archive', return_value=live) as mocked:
            results = hugo.lookup('Dune', 'Frank Herbert')
        self.assertEqual(mocked.call_count, 1)
        self.assertEqual(results[0].work_title, 'Dune')

    def test_invalid_status_is_rejected(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        payload = json.loads(self._disk_path().read_text(encoding='utf-8'))
        payload['records'][0]['status'] = 'Nominee'
        self._disk_path().write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + '\n',
            encoding='utf-8',
        )
        live = _complete_archive()
        with patch.object(hugo, '_load_live_archive', return_value=live) as mocked:
            hugo.lookup('Dune', 'Frank Herbert')
        self.assertEqual(mocked.call_count, 1)

    def test_malformed_match_titles_is_rejected(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        payload = json.loads(self._disk_path().read_text(encoding='utf-8'))
        payload['records'][0]['match_titles'] = 'Dune'
        self._disk_path().write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + '\n',
            encoding='utf-8',
        )
        live = _complete_archive()
        with patch.object(hugo, '_load_live_archive', return_value=live) as mocked:
            hugo.lookup('Dune', 'Frank Herbert')
        self.assertEqual(mocked.call_count, 1)

    def test_record_missing_required_field_is_rejected(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        payload = json.loads(self._disk_path().read_text(encoding='utf-8'))
        del payload['records'][0]['work_title']
        self._disk_path().write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + '\n',
            encoding='utf-8',
        )
        live = _complete_archive()
        with patch.object(hugo, '_load_live_archive', return_value=live) as mocked:
            hugo.lookup('Dune', 'Frank Herbert')
        self.assertEqual(mocked.call_count, 1)

    def test_version_mismatch_uses_live_path(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC), version=2)
        live = _complete_archive()
        with patch.object(hugo, '_load_live_archive', return_value=live) as mocked:
            results = hugo.lookup('Dune', 'Frank Herbert')
        self.assertEqual(mocked.call_count, 1)
        self.assertEqual(results[0].work_title, 'Dune')

    def test_save_failure_does_not_fail_lookup(self):
        archive = _complete_archive()
        with patch.object(hugo, '_load_live_archive', return_value=archive):
            with patch.object(
                hugo.cache,
                'save_source_cache',
                side_effect=OSError('disk full'),
            ):
                results = hugo.lookup('Dune', 'Frank Herbert')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].work_title, 'Dune')

    def test_ram_reset_does_not_delete_disk_cache(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        hugo._archive_records_cache = archive
        self.assertTrue(self._disk_path().is_file())
        hugo._reset_runtime_state()
        self.assertTrue(self._disk_path().is_file())
        self.assertIsNone(hugo._archive_records_cache)
        with patch.object(
            hugo, '_load_live_archive', side_effect=AssertionError('live')
        ):
            results = hugo.lookup('Dune', 'Frank Herbert')
        self.assertEqual(results[0].work_title, 'Dune')


class HugoNebulaWorldFantasyRefreshBudgetTests(unittest.TestCase):
    def setUp(self):
        hugo._reset_runtime_state()
        world_fantasy._reset_runtime_state()
        nebula._clear_caches_for_tests()
        cache._reset_runtime_state()
        self._temp = TemporaryDirectory()
        cache.set_cache_directory(Path(self._temp.name))
        self._nebula_tests = _load_test_module('test_nebula_cache')
        self._wfa_tests = _load_test_module('test_world_fantasy_cache')

    def tearDown(self):
        hugo._reset_runtime_state()
        world_fantasy._reset_runtime_state()
        nebula._clear_caches_for_tests()
        cache._reset_runtime_state()
        self._temp.cleanup()

    def test_one_optional_refresh_among_three_stale_sources(self):
        hugo_stale = _complete_archive()
        nebula_stale = self._nebula_tests._complete_archive()
        wfa_stale = self._wfa_tests._complete_archive()
        _save_disk(
            hugo_stale,
            generated_at=datetime(2020, 1, 1, tzinfo=_UTC),
            ttl_seconds=60,
        )
        self._nebula_tests._save_disk(
            nebula_stale,
            generated_at=datetime(2020, 1, 1, tzinfo=_UTC),
            ttl_seconds=60,
        )
        self._wfa_tests._save_disk(
            wfa_stale,
            generated_at=datetime(2020, 1, 1, tzinfo=_UTC),
            ttl_seconds=60,
        )
        hugo._reset_runtime_state()
        world_fantasy._reset_runtime_state()
        nebula._clear_caches_for_tests()

        with patch.object(
            nebula, '_load_live_archive', return_value=nebula_stale
        ) as nebula_live, patch.object(
            world_fantasy, '_load_live_archive', return_value=wfa_stale
        ) as wfa_live, patch.object(
            hugo, '_load_live_archive', return_value=hugo_stale
        ) as hugo_live:
            first = lookup_awards(
                'Dune',
                'Frank Herbert',
                enabled_source_keys=('nebula', 'world_fantasy', 'hugo'),
            )
            self.assertEqual(len(first.failures), 0)
            self.assertTrue(
                any(
                    item.result.work_title == 'Dune'
                    for item in first.assessments
                )
            )
            first_counts = (
                nebula_live.call_count,
                wfa_live.call_count,
                hugo_live.call_count,
            )
            self.assertEqual(sum(first_counts), 1)

            hugo._reset_runtime_state()
            world_fantasy._reset_runtime_state()
            nebula._clear_caches_for_tests()
            second = lookup_awards(
                'Dune',
                'Frank Herbert',
                enabled_source_keys=('nebula', 'world_fantasy', 'hugo'),
            )
            self.assertEqual(len(second.failures), 0)
            second_counts = (
                nebula_live.call_count - first_counts[0],
                wfa_live.call_count - first_counts[1],
                hugo_live.call_count - first_counts[2],
            )
            self.assertEqual(sum(second_counts), 1)
            for first_n, second_n in zip(first_counts, second_counts):
                if first_n:
                    self.assertEqual(second_n, 0)


if __name__ == '__main__':
    unittest.main()
