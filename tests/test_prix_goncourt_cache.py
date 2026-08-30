"""Offline coverage for Prix Goncourt persistent parsed-archive cache."""

from __future__ import annotations

import importlib.util
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from awards import cache
from awards.cache_control import refresh_award_source_cache
from awards.sources import hugo, prix_goncourt as pg, pulitzer

_UTC = timezone.utc
_TESTS_DIR = Path(__file__).resolve().parent


def _load_parser_tests():
    path = _TESTS_DIR / 'test_prix_goncourt_parser.py'
    spec = importlib.util.spec_from_file_location(
        'test_prix_goncourt_parser',
        path,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_PARSER_TESTS = _load_parser_tests()
_KNOWN_WINNERS = _PARSER_TESTS._KNOWN_WINNERS
official_winners_html = _PARSER_TESTS.official_winners_html


def _record(year, title=None, author=None):
    if title is None or author is None:
        known = _KNOWN_WINNERS.get(year)
        if known:
            title, author = known
        else:
            title = f'Stub Title {year}'
            author = f'Stub Author {year}'
    return pg._ParsedRecord(
        award_year=year,
        category=pg.CATEGORY,
        status='Winner',
        work_title=title,
        work_author=author,
        source_url=pg.WINNERS_URL,
    )


def _complete_archive(*, current_year=2026, extra=()):
    records = [_record(year) for year in range(pg.ARCHIVE_MIN_YEAR, current_year)]
    records.extend(extra)
    return tuple(records)


def _save_disk(records, *, generated_at=None, ttl_seconds=None, version=None):
    cache.save_source_cache(
        pg.SOURCE_KEY,
        pg.CACHE_VERSION if version is None else version,
        records=[pg._record_to_cache_dict(record) for record in records],
        source_urls=pg._archive_source_urls(),
        coverage=pg._coverage_from_records(records),
        ttl_seconds=pg.CACHE_TTL_SECONDS if ttl_seconds is None else ttl_seconds,
        generated_at=generated_at,
    )


class PrixGoncourtPersistentCacheTests(unittest.TestCase):
    def setUp(self):
        pg._reset_runtime_state()
        cache._reset_runtime_state()
        self._temp = TemporaryDirectory()
        self.cache_dir = Path(self._temp.name)
        cache.set_cache_directory(self.cache_dir)

    def tearDown(self):
        pg._reset_runtime_state()
        cache._reset_runtime_state()
        self._temp.cleanup()

    def _disk_path(self):
        return self.cache_dir / 'prix_goncourt.json'

    def _rewrite_records(self, mutate):
        payload = json.loads(self._disk_path().read_text(encoding='utf-8'))
        mutate(payload)
        self._disk_path().write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
            + '\n',
            encoding='utf-8',
        )

    def _assert_2025(self, results):
        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertEqual(result.work_title, 'La Maison vide')
        self.assertEqual(result.work_author, 'Laurent Mauvignier')
        self.assertEqual(result.award_name, 'Prix Goncourt')
        self.assertEqual(result.award_year, 2025)
        self.assertEqual(result.category, 'Fiction')
        self.assertEqual(result.status, 'Winner')
        self.assertIsNone(result.rank)
        self.assertEqual(result.source_name, 'Prix Goncourt')
        self.assertEqual(result.source_url, pg.WINNERS_URL)
        self.assertIsNone(result.notes)
        self.assertEqual(result.identity_kind, 'work')

    def test_cache_identity_constants(self):
        self.assertEqual(pg.SOURCE_KEY, 'prix_goncourt')
        self.assertEqual(pg.CACHE_VERSION, 1)
        self.assertEqual(pg.CACHE_BASE_TTL_SECONDS, 7 * 24 * 60 * 60)
        self.assertEqual(pg.CACHE_REFRESH_OFFSET_SECONDS, 8 * 60 * 60)
        self.assertEqual(
            pg.CACHE_TTL_SECONDS,
            pg.CACHE_BASE_TTL_SECONDS + pg.CACHE_REFRESH_OFFSET_SECONDS,
        )
        self.assertEqual(pg.CACHE_TTL_SECONDS, 633600)

    def test_complete_archive_helper_passes_source_validation(self):
        with patch.object(pg, '_current_calendar_year', return_value=2026):
            pg._validate_cached_archive(_complete_archive())

    def test_parsed_record_round_trips_all_fields(self):
        original = _record(2025)
        restored = pg._record_from_cache_dict(pg._record_to_cache_dict(original))
        self.assertEqual(restored, original)

    def test_rank_is_not_persisted(self):
        payload = pg._record_to_cache_dict(_record(2025))
        self.assertNotIn('rank', payload)
        self.assertNotIn('html', payload)
        self.assertNotIn('qualification', payload)
        self.assertEqual(set(payload), set(pg._RECORD_CACHE_FIELDS))

    def test_live_validated_archive_writes_prix_goncourt_json(self):
        archive = _complete_archive()
        with patch.object(pg, '_current_calendar_year', return_value=2026):
            with patch.object(pg, '_load_live_archive', return_value=archive):
                results = pg.lookup('La Maison vide', 'Laurent Mauvignier')
        self._assert_2025(results)
        self.assertTrue(self._disk_path().is_file())
        payload = json.loads(self._disk_path().read_text(encoding='utf-8'))
        self.assertEqual(payload['source_key'], 'prix_goncourt')
        self.assertEqual(payload['source_urls'], [pg.WINNERS_URL])
        self.assertGreater(payload['record_count'], 0)
        raw = self._disk_path().read_text(encoding='utf-8')
        self.assertNotIn('<html', raw)
        self.assertNotIn('qualification', raw)
        self.assertNotIn('"rank"', raw)

    def test_fresh_cache_lookup_makes_zero_network_calls(self):
        archive = _complete_archive()
        with patch.object(pg, '_current_calendar_year', return_value=2026):
            _save_disk(archive, generated_at=datetime.now(_UTC))
            pg._reset_runtime_state()
            with patch.object(
                pg, '_fetch_html', side_effect=AssertionError('network')
            ), patch.object(
                pg, '_load_live_archive', side_effect=AssertionError('live')
            ):
                results = pg.lookup('La Maison vide', 'Laurent Mauvignier')
        self._assert_2025(results)

    def test_ram_reset_plus_fresh_disk_makes_zero_http(self):
        archive = _complete_archive()
        with patch.object(pg, '_current_calendar_year', return_value=2026):
            with patch.object(pg, '_load_live_archive', return_value=archive) as live:
                first = pg.lookup('La Maison vide', 'Laurent Mauvignier')
            self._assert_2025(first)
            self.assertEqual(live.call_count, 1)
            pg._reset_runtime_state()
            self.assertTrue(self._disk_path().is_file())
            with patch.object(
                pg, '_fetch_html', side_effect=AssertionError('network')
            ), patch.object(
                pg, '_load_live_archive', side_effect=AssertionError('live')
            ):
                second = pg.lookup('La Maison vide', 'Laurent Mauvignier')
        self._assert_2025(second)

    def test_stale_cache_successful_refresh_replaces_disk(self):
        stale = _complete_archive()
        _save_disk(
            stale,
            generated_at=datetime(2020, 1, 1, tzinfo=_UTC),
            ttl_seconds=60,
        )
        original_generated = json.loads(
            self._disk_path().read_text(encoding='utf-8')
        )['generated_at']
        refreshed = stale[:-1] + (
            _record(2025, 'La Maison vide', 'Laurent Mauvignier'),
        )
        with patch.object(pg, '_current_calendar_year', return_value=2026):
            with patch.object(pg, '_load_live_archive', return_value=refreshed):
                results = pg.lookup('La Maison vide', 'Laurent Mauvignier')
        self._assert_2025(results)
        updated = json.loads(self._disk_path().read_text(encoding='utf-8'))
        self.assertNotEqual(updated['generated_at'], original_generated)

    def test_stale_cache_live_failure_keeps_file_unchanged(self):
        stale = _complete_archive()
        _save_disk(
            stale,
            generated_at=datetime(2020, 1, 1, tzinfo=_UTC),
            ttl_seconds=60,
        )
        original = self._disk_path().read_text(encoding='utf-8')
        with patch.object(pg, '_current_calendar_year', return_value=2026):
            with patch.object(
                pg,
                '_load_live_archive',
                side_effect=pg.PrixGoncourtSourceError('archive down'),
            ):
                results = pg.lookup('La Maison vide', 'Laurent Mauvignier')
        self._assert_2025(results)
        self.assertEqual(self._disk_path().read_text(encoding='utf-8'), original)

    def test_stale_cache_without_refresh_slot_uses_stale_and_skips_network(self):
        stale = _complete_archive()
        _save_disk(
            stale,
            generated_at=datetime(2020, 1, 1, tzinfo=_UTC),
            ttl_seconds=60,
        )
        pg._reset_runtime_state()
        with patch.object(pg, '_current_calendar_year', return_value=2026):
            with cache.lookup_refresh_budget():
                self.assertTrue(cache.try_claim_stale_refresh())
                with patch.object(
                    pg, '_load_live_archive', side_effect=AssertionError('live')
                ) as mocked, patch.object(
                    pg, '_fetch_html', side_effect=AssertionError('network')
                ):
                    results = pg.lookup('La Maison vide', 'Laurent Mauvignier')
                mocked.assert_not_called()
        self._assert_2025(results)

    def test_missing_cache_live_fetches_after_stale_refresh_budget_consumed(self):
        self.assertFalse(self._disk_path().is_file())
        live = _complete_archive()
        with patch.object(pg, '_current_calendar_year', return_value=2026):
            with cache.lookup_refresh_budget():
                self.assertTrue(cache.try_claim_stale_refresh())
                with patch.object(
                    pg, '_load_live_archive', return_value=live
                ) as mocked:
                    results = pg.lookup('La Maison vide', 'Laurent Mauvignier')
                self.assertEqual(mocked.call_count, 1)
        self._assert_2025(results)

    def test_malformed_disk_requires_live(self):
        archive = _complete_archive()
        with patch.object(pg, '_current_calendar_year', return_value=2026):
            _save_disk(archive, generated_at=datetime.now(_UTC))
            self._rewrite_records(
                lambda payload: payload['records'][0].__setitem__('award_year', 0)
            )
            live = _complete_archive()
            with patch.object(
                pg, '_load_live_archive', return_value=live
            ) as mocked:
                pg.lookup('La Maison vide', 'Laurent Mauvignier')
            self.assertEqual(mocked.call_count, 1)

    def test_version_mismatch_uses_live_path(self):
        archive = _complete_archive()
        with patch.object(pg, '_current_calendar_year', return_value=2026):
            _save_disk(archive, generated_at=datetime.now(_UTC), version=2)
            live = _complete_archive()
            with patch.object(
                pg, '_load_live_archive', return_value=live
            ) as mocked:
                results = pg.lookup('La Maison vide', 'Laurent Mauvignier')
            self.assertEqual(mocked.call_count, 1)
        self._assert_2025(results)

    def test_save_failure_does_not_fail_lookup(self):
        archive = _complete_archive()
        with patch.object(pg, '_current_calendar_year', return_value=2026):
            with patch.object(pg, '_load_live_archive', return_value=archive):
                with patch.object(
                    pg.cache,
                    'save_source_cache',
                    side_effect=OSError('disk full'),
                ):
                    results = pg.lookup('La Maison vide', 'Laurent Mauvignier')
        self._assert_2025(results)

    def test_ram_reset_does_not_delete_disk_cache(self):
        archive = _complete_archive()
        with patch.object(pg, '_current_calendar_year', return_value=2026):
            _save_disk(archive, generated_at=datetime.now(_UTC))
            pg._archive_records_cache = archive
            self.assertTrue(self._disk_path().is_file())
            pg._reset_runtime_state()
            self.assertTrue(self._disk_path().is_file())
            self.assertIsNone(pg._archive_records_cache)
            with patch.object(
                pg, '_load_live_archive', side_effect=AssertionError('live')
            ), patch.object(
                pg, '_fetch_html', side_effect=AssertionError('network')
            ):
                results = pg.lookup('La Maison vide', 'Laurent Mauvignier')
        self._assert_2025(results)

    def test_manual_refresh_removes_prix_goncourt_json_and_ram_only(self):
        archive = _complete_archive()
        with patch.object(pg, '_current_calendar_year', return_value=2026):
            _save_disk(archive, generated_at=datetime.now(_UTC))
        pg._archive_records_cache = archive
        hugo._archive_records_cache = ()
        cache.save_source_cache(
            'hugo',
            1,
            records=[{'title': 'hugo', 'year': 2020}],
            source_urls=['https://example.test/hugo'],
            coverage={'source': 'hugo'},
            ttl_seconds=3600,
            generated_at=datetime(2026, 1, 1, tzinfo=_UTC),
        )
        pulitzer_path = self.cache_dir / 'pulitzer.json'
        cache.save_source_cache(
            'pulitzer',
            1,
            records=[{'title': 'pulitzer', 'year': 2020}],
            source_urls=['https://example.test/pulitzer'],
            coverage={'source': 'pulitzer'},
            ttl_seconds=3600,
            generated_at=datetime(2026, 1, 1, tzinfo=_UTC),
        )
        with patch.object(
            pg, '_fetch_html', side_effect=AssertionError('network')
        ), patch.object(
            pg, '_load_live_archive', side_effect=AssertionError('live')
        ):
            self.assertTrue(refresh_award_source_cache('prix_goncourt'))
        self.assertFalse(self._disk_path().exists())
        self.assertIsNone(pg._archive_records_cache)
        self.assertTrue((self.cache_dir / 'hugo.json').is_file())
        self.assertTrue(pulitzer_path.is_file())
        self.assertEqual(hugo._archive_records_cache, ())

    def test_manual_refresh_makes_zero_http(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        pg._archive_records_cache = archive
        with patch.object(
            pg, '_fetch_html', side_effect=AssertionError('network')
        ) as fetch, patch.object(
            pg, 'lookup', side_effect=AssertionError('lookup')
        ):
            self.assertTrue(refresh_award_source_cache('prix_goncourt'))
        fetch.assert_not_called()

    def test_cache_ending_before_previous_year_requires_live_after_rollover(self):
        archive = _complete_archive(current_year=2026)
        with patch.object(pg, '_current_calendar_year', return_value=2026):
            _save_disk(archive, generated_at=datetime.now(_UTC))
        pg._reset_runtime_state()
        live = _complete_archive(current_year=2027)
        with patch.object(pg, '_current_calendar_year', return_value=2027):
            with patch.object(
                pg, '_load_live_archive', return_value=live
            ) as mocked:
                results = pg.lookup('La Maison vide', 'Laurent Mauvignier')
            self.assertEqual(mocked.call_count, 1)
        self._assert_2025(results)

    def test_current_year_present_cache_round_trip(self):
        archive = _complete_archive(current_year=2026) + (
            _record(2026, 'Stub Title 2026', 'Stub Author 2026'),
        )
        with patch.object(pg, '_current_calendar_year', return_value=2026):
            pg._validate_cached_archive(archive)
            _save_disk(archive, generated_at=datetime.now(_UTC))
            pg._reset_runtime_state()
            with patch.object(
                pg, '_load_live_archive', side_effect=AssertionError('live')
            ):
                results = pg.lookup('Stub Title 2026', 'Stub Author 2026')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].award_year, 2026)
        self.assertEqual(results[0].status, 'Winner')


class PrixGoncourtGeneratedHtmlCachePathTests(unittest.TestCase):
    def setUp(self):
        pg._reset_runtime_state()
        cache._reset_runtime_state()
        self._temp = TemporaryDirectory()
        cache.set_cache_directory(Path(self._temp.name))

    def tearDown(self):
        pg._reset_runtime_state()
        cache._reset_runtime_state()
        self._temp.cleanup()

    def test_parse_of_generated_archive_html_is_cacheable(self):
        html = official_winners_html(max_year=2025)
        with patch.object(pg, '_current_calendar_year', return_value=2026):
            records, years = pg._parse_winners_html(html)
            pg._validate_archive(records, years)
            _save_disk(records, generated_at=datetime.now(_UTC))
            pg._reset_runtime_state()
            with patch.object(
                pg, '_fetch_html', side_effect=AssertionError('network')
            ):
                results = pg.lookup('La Maison vide', 'Laurent Mauvignier')
        self.assertEqual(results[0].award_year, 2025)
        self.assertEqual(results[0].status, 'Winner')


if __name__ == '__main__':
    unittest.main()
