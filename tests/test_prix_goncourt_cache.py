"""Offline coverage for Prix Goncourt persistent parsed-archive cache."""

from __future__ import annotations

import hashlib
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
        self._skip_selection = patch.object(
            pg,
            '_load_live_selections',
            side_effect=pg.PrixGoncourtSourceError('selection skipped'),
        )
        self._skip_selection.start()

    def tearDown(self):
        self._skip_selection.stop()
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
        cache.save_cache_entry(
            pg.SOURCE_KEY,
            pg.SELECTION_ENTRY_KIND,
            pg.SELECTIONS_URL,
            pg.SELECTION_CACHE_VERSION,
            records=[{'title': 'finalist', 'year': 2025}],
            source_urls=[pg.SELECTIONS_URL],
            coverage={'kind': 'finalist_archive'},
            ttl_seconds=3600,
            generated_at=datetime(2026, 1, 1, tzinfo=_UTC),
        )
        pg._selection_records_cache = ()
        pg._selection_coverage_cache = {'kind': 'finalist_archive'}
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
        self.assertIsNone(pg._selection_records_cache)
        self.assertIsNone(pg._selection_coverage_cache)
        self.assertIsNone(
            cache.load_cache_entry(
                pg.SOURCE_KEY,
                pg.SELECTION_ENTRY_KIND,
                pg.SELECTIONS_URL,
                pg.SELECTION_CACHE_VERSION,
            )
        )
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


def _load_selection_parser_tests():
    path = _TESTS_DIR / 'test_prix_goncourt_selection_parser.py'
    spec = importlib.util.spec_from_file_location(
        'test_prix_goncourt_selection_parser',
        path,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_SELECTION_TESTS = _load_selection_parser_tests()
official_selections_html = _SELECTION_TESTS.official_selections_html


def _finalist_record(year, title, author):
    return pg._ParsedRecord(
        award_year=year,
        category=pg.CATEGORY,
        status='Finalist',
        work_title=title,
        work_author=author,
        source_url=pg.SELECTIONS_URL,
    )


def _complete_finalists(*, current_year=2026, extra=()):
    records = []
    for year in range(pg.FINALIST_MIN_YEAR, current_year):
        for index in range(1, 5):
            records.append(
                _finalist_record(
                    year,
                    f'Selection Title {year}-{index}',
                    f'Selection Author {year}-{index}',
                )
            )
    records.extend(extra)
    return tuple(records)


def _selection_coverage(*, current_year=2026, state='absent', extra_markers=None):
    markers = {}
    for year in range(pg.FINALIST_MIN_YEAR, current_year):
        known = _KNOWN_WINNERS.get(year)
        markers[str(year)] = known[0] if known else f'Stub Title {year}'
    if extra_markers:
        markers.update(extra_markers)
    return {
        'kind': 'finalist_archive',
        'min_year': pg.FINALIST_MIN_YEAR,
        'max_completed_year': current_year - 1,
        'current_year': current_year,
        'current_year_state': state,
        'winner_marker_titles': markers,
    }


def _save_selection_disk(records, coverage, *, generated_at=None, ttl_seconds=None, version=None):
    cache.save_cache_entry(
        pg.SOURCE_KEY,
        pg.SELECTION_ENTRY_KIND,
        pg.SELECTIONS_URL,
        pg.SELECTION_CACHE_VERSION if version is None else version,
        records=[pg._record_to_cache_dict(record) for record in records],
        source_urls=[pg.SELECTIONS_URL],
        coverage=coverage,
        ttl_seconds=(
            pg.SELECTION_CACHE_TTL_SECONDS if ttl_seconds is None else ttl_seconds
        ),
        generated_at=generated_at,
    )


def _selection_path(cache_dir: Path) -> Path:
    digest = hashlib.sha256(pg.SELECTIONS_URL.encode('utf-8')).hexdigest()
    return cache_dir / pg.SOURCE_KEY / pg.SELECTION_ENTRY_KIND / f'{digest}.json'


class PrixGoncourtSelectionCacheTests(unittest.TestCase):
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

    def _winners(self):
        return _complete_archive()

    def _lookup_bel_obscur(self):
        extra = (
            _finalist_record(2025, 'Le bel obscur', 'Caroline LAMARCHE'),
        )
        return extra

    def test_valid_live_selection_writes_keyed_entry(self):
        winners = self._winners()
        finalists = _complete_finalists() + self._lookup_bel_obscur()
        coverage = _selection_coverage()
        with patch.object(pg, '_current_calendar_year', return_value=2026):
            with patch.object(pg, '_get_archive_records', return_value=winners):
                with patch.object(
                    pg,
                    '_load_live_selections',
                    return_value=(finalists, coverage),
                ):
                    results = pg.lookup('Le bel obscur', 'Caroline LAMARCHE')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, 'Finalist')
        self.assertTrue(_selection_path(self.cache_dir).is_file())
        payload = json.loads(_selection_path(self.cache_dir).read_text(encoding='utf-8'))
        self.assertEqual(payload['entry_kind'], 'selections')
        self.assertEqual(payload['entry_key'], pg.SELECTIONS_URL)
        self.assertEqual(payload['source_cache_version'], 1)
        self.assertNotIn('html', json.dumps(payload))
        self.assertNotIn('rank', json.dumps(payload['records']))
        self.assertNotIn('qualification', json.dumps(payload))

    def test_fresh_selection_disk_replay_is_zero_http(self):
        winners = self._winners()
        finalists = _complete_finalists() + self._lookup_bel_obscur()
        with patch.object(pg, '_current_calendar_year', return_value=2026):
            _save_disk(winners, generated_at=datetime.now(_UTC))
            _save_selection_disk(
                finalists,
                _selection_coverage(),
                generated_at=datetime.now(_UTC),
            )
            pg._reset_runtime_state()
            with patch.object(
                pg, '_load_live_archive', side_effect=AssertionError('winner live')
            ), patch.object(
                pg, '_load_live_selections', side_effect=AssertionError('sel live')
            ), patch.object(
                pg, '_fetch_html', side_effect=AssertionError('network')
            ):
                results = pg.lookup('Le bel obscur', 'Caroline LAMARCHE')
        self.assertEqual(results[0].status, 'Finalist')
        self.assertEqual(results[0].source_url, pg.SELECTIONS_URL)

    def test_ram_reset_then_fresh_selection_disk_is_zero_http(self):
        winners = self._winners()
        finalists = _complete_finalists() + self._lookup_bel_obscur()
        with patch.object(pg, '_current_calendar_year', return_value=2026):
            _save_disk(winners, generated_at=datetime.now(_UTC))
            _save_selection_disk(
                finalists,
                _selection_coverage(),
                generated_at=datetime.now(_UTC),
            )
            pg._selection_records_cache = finalists
            pg._selection_coverage_cache = _selection_coverage()
            pg._reset_runtime_state()
            self.assertIsNone(pg._selection_records_cache)
            self.assertIsNone(pg._selection_coverage_cache)
            self.assertTrue(_selection_path(self.cache_dir).is_file())
            with patch.object(
                pg, '_fetch_html', side_effect=AssertionError('network')
            ):
                results = pg.lookup('Le bel obscur', 'Caroline LAMARCHE')
        self.assertEqual(results[0].work_title, 'Le bel obscur')

    def test_stale_selection_slot_success_replaces(self):
        winners = self._winners()
        stale = _complete_finalists()
        fresh = _complete_finalists() + self._lookup_bel_obscur()
        coverage = _selection_coverage()
        with patch.object(pg, '_current_calendar_year', return_value=2026):
            _save_disk(winners, generated_at=datetime.now(_UTC))
            _save_selection_disk(
                stale,
                coverage,
                generated_at=datetime(2020, 1, 1, tzinfo=_UTC),
                ttl_seconds=1,
            )
            with patch.object(
                pg, '_load_live_selections', return_value=(fresh, coverage)
            ) as live:
                results = pg.lookup('Le bel obscur', 'Caroline LAMARCHE')
            self.assertEqual(live.call_count, 1)
        self.assertEqual(results[0].work_title, 'Le bel obscur')
        payload = json.loads(_selection_path(self.cache_dir).read_text(encoding='utf-8'))
        titles = {item['work_title'] for item in payload['records']}
        self.assertIn('Le bel obscur', titles)

    def test_stale_selection_slot_failure_keeps_file(self):
        winners = self._winners()
        stale = _complete_finalists() + self._lookup_bel_obscur()
        coverage = _selection_coverage()
        with patch.object(pg, '_current_calendar_year', return_value=2026):
            _save_disk(winners, generated_at=datetime.now(_UTC))
            _save_selection_disk(
                stale,
                coverage,
                generated_at=datetime(2020, 1, 1, tzinfo=_UTC),
                ttl_seconds=1,
            )
            before = _selection_path(self.cache_dir).read_text(encoding='utf-8')
            with patch.object(
                pg,
                '_load_live_selections',
                side_effect=pg.PrixGoncourtSourceError('blocked'),
            ):
                results = pg.lookup('Le bel obscur', 'Caroline LAMARCHE')
        self.assertEqual(results[0].status, 'Finalist')
        self.assertEqual(
            _selection_path(self.cache_dir).read_text(encoding='utf-8'),
            before,
        )

    def test_stale_selection_without_slot_is_zero_http(self):
        winners = self._winners()
        stale = _complete_finalists() + self._lookup_bel_obscur()
        coverage = _selection_coverage()
        with patch.object(pg, '_current_calendar_year', return_value=2026):
            _save_disk(winners, generated_at=datetime.now(_UTC))
            _save_selection_disk(
                stale,
                coverage,
                generated_at=datetime(2020, 1, 1, tzinfo=_UTC),
                ttl_seconds=1,
            )
            with patch.object(cache, 'try_claim_stale_refresh', return_value=False):
                with patch.object(
                    pg, '_load_live_selections', side_effect=AssertionError('sel')
                ), patch.object(
                    pg, '_fetch_html', side_effect=AssertionError('network')
                ):
                    results = pg.lookup('Le bel obscur', 'Caroline LAMARCHE')
        self.assertEqual(results[0].status, 'Finalist')

    def test_missing_selection_cache_live_success_persists(self):
        winners = self._winners()
        finalists = _complete_finalists() + self._lookup_bel_obscur()
        with patch.object(pg, '_current_calendar_year', return_value=2026):
            _save_disk(winners, generated_at=datetime.now(_UTC))
            with patch.object(
                pg,
                '_load_live_selections',
                return_value=(finalists, _selection_coverage()),
            ):
                pg.lookup('Le bel obscur', 'Caroline LAMARCHE')
        self.assertTrue(_selection_path(self.cache_dir).is_file())

    def test_missing_selection_cache_live_failure_still_returns_winners(self):
        winners = self._winners()
        with patch.object(pg, '_current_calendar_year', return_value=2026):
            _save_disk(winners, generated_at=datetime.now(_UTC))
            with patch.object(
                pg,
                '_load_live_selections',
                side_effect=pg.PrixGoncourtSourceError('blocked'),
            ), patch.object(
                pg, '_fetch_html', side_effect=AssertionError('network')
            ):
                results = pg.lookup('La Maison vide', 'Laurent Mauvignier')
        self.assertEqual(results[0].status, 'Winner')
        self.assertFalse(_selection_path(self.cache_dir).exists())

    def test_malformed_selection_live_does_not_write_cache(self):
        winners = self._winners()
        with patch.object(pg, '_current_calendar_year', return_value=2026):
            _save_disk(winners, generated_at=datetime.now(_UTC))
            with patch.object(
                pg,
                '_load_live_selections',
                side_effect=pg.PrixGoncourtSourceError('ambiguous'),
            ):
                results = pg.lookup('La Maison vide', 'Laurent Mauvignier')
        self.assertEqual(results[0].status, 'Winner')
        self.assertFalse(_selection_path(self.cache_dir).exists())

    def test_malformed_selection_disk_attempts_live_enrichment(self):
        winners = self._winners()
        finalists = _complete_finalists() + self._lookup_bel_obscur()
        with patch.object(pg, '_current_calendar_year', return_value=2026):
            _save_disk(winners, generated_at=datetime.now(_UTC))
            _save_selection_disk(finalists, _selection_coverage())
            payload = json.loads(_selection_path(self.cache_dir).read_text(encoding='utf-8'))
            payload['records'] = [{'bad': True}]
            _selection_path(self.cache_dir).write_text(
                json.dumps(payload),
                encoding='utf-8',
            )
            with patch.object(
                pg,
                '_load_live_selections',
                return_value=(finalists, _selection_coverage()),
            ) as live:
                results = pg.lookup('Le bel obscur', 'Caroline LAMARCHE')
            self.assertEqual(live.call_count, 1)
        self.assertEqual(results[0].status, 'Finalist')

    def test_version_mismatch_attempts_live_enrichment(self):
        winners = self._winners()
        finalists = _complete_finalists() + self._lookup_bel_obscur()
        with patch.object(pg, '_current_calendar_year', return_value=2026):
            _save_disk(winners, generated_at=datetime.now(_UTC))
            _save_selection_disk(finalists, _selection_coverage(), version=99)
            with patch.object(
                pg,
                '_load_live_selections',
                return_value=(finalists, _selection_coverage()),
            ) as live:
                pg.lookup('Le bel obscur', 'Caroline LAMARCHE')
            self.assertEqual(live.call_count, 1)

    def test_current_year_absent_state_round_trips(self):
        winners = self._winners()
        finalists = _complete_finalists()
        coverage = _selection_coverage(state='absent')
        with patch.object(pg, '_current_calendar_year', return_value=2026):
            _save_disk(winners, generated_at=datetime.now(_UTC))
            _save_selection_disk(finalists, coverage, generated_at=datetime.now(_UTC))
            pg._reset_runtime_state()
            loaded = pg._load_persistent_selections(winners)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded[1]['coverage']['current_year_state'], 'absent')

    def test_2027_rollover_rejects_2026_incomplete_coverage(self):
        winners = _complete_archive(current_year=2027)
        finalists = _complete_finalists(current_year=2026)
        coverage = _selection_coverage(current_year=2026, state='absent')
        with patch.object(pg, '_current_calendar_year', return_value=2026):
            _save_selection_disk(finalists, coverage, generated_at=datetime.now(_UTC))
        pg._reset_runtime_state()
        with patch.object(pg, '_current_calendar_year', return_value=2027):
            _save_disk(winners, generated_at=datetime.now(_UTC))
            with patch.object(
                pg,
                '_load_live_selections',
                side_effect=pg.PrixGoncourtSourceError('needed'),
            ) as live:
                results = pg.lookup('La Maison vide', 'Laurent Mauvignier')
            self.assertEqual(live.call_count, 1)
        self.assertEqual(results[0].status, 'Winner')

    def test_manual_refresh_clears_winner_and_selection_zero_http(self):
        winners = self._winners()
        finalists = _complete_finalists()
        _save_disk(winners, generated_at=datetime.now(_UTC))
        _save_selection_disk(finalists, _selection_coverage())
        cache.save_source_cache(
            'hugo',
            1,
            records=[{'title': 'hugo'}],
            source_urls=['https://example.test/hugo'],
            coverage={'source': 'hugo'},
            ttl_seconds=3600,
            generated_at=datetime(2026, 1, 1, tzinfo=_UTC),
        )
        pg._archive_records_cache = winners
        pg._selection_records_cache = finalists
        with patch.object(
            pg, '_fetch_html', side_effect=AssertionError('network')
        ), patch.object(
            pg, 'lookup', side_effect=AssertionError('lookup')
        ):
            self.assertTrue(refresh_award_source_cache('prix_goncourt'))
        self.assertFalse((self.cache_dir / 'prix_goncourt.json').exists())
        self.assertFalse(_selection_path(self.cache_dir).exists())
        self.assertTrue((self.cache_dir / 'hugo.json').is_file())
        self.assertIsNone(pg._archive_records_cache)
        self.assertIsNone(pg._selection_records_cache)

    def test_reset_runtime_state_clears_both_ram_only(self):
        winners = self._winners()
        finalists = _complete_finalists()
        _save_disk(winners, generated_at=datetime.now(_UTC))
        _save_selection_disk(finalists, _selection_coverage())
        pg._archive_records_cache = winners
        pg._selection_records_cache = finalists
        pg._selection_coverage_cache = _selection_coverage()
        pg._reset_runtime_state()
        self.assertIsNone(pg._archive_records_cache)
        self.assertIsNone(pg._selection_records_cache)
        self.assertIsNone(pg._selection_coverage_cache)
        self.assertTrue((self.cache_dir / 'prix_goncourt.json').is_file())
        self.assertTrue(_selection_path(self.cache_dir).is_file())

    def test_shared_budget_does_not_refresh_both_stale_datasets(self):
        winners = self._winners()
        finalists = _complete_finalists() + self._lookup_bel_obscur()
        stale_at = datetime(2020, 1, 1, tzinfo=_UTC)
        with patch.object(pg, '_current_calendar_year', return_value=2026):
            _save_disk(winners, generated_at=stale_at, ttl_seconds=1)
            _save_selection_disk(
                finalists,
                _selection_coverage(),
                generated_at=stale_at,
                ttl_seconds=1,
            )
            with cache.lookup_refresh_budget():
                with patch.object(
                    pg, '_load_live_archive', return_value=winners
                ) as winner_live, patch.object(
                    pg, '_load_live_selections', side_effect=AssertionError('sel')
                ) as sel_live:
                    results = pg.lookup('Le bel obscur', 'Caroline LAMARCHE')
        self.assertEqual(winner_live.call_count, 1)
        sel_live.assert_not_called()
        self.assertEqual(results[0].status, 'Finalist')


if __name__ == '__main__':
    unittest.main()

