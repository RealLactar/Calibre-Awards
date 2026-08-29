"""Offline coverage for Booker persistent parsed-archive cache."""

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
from awards.sources import booker, hugo, pulitzer

_UTC = timezone.utc
_TESTS_DIR = Path(__file__).resolve().parent


def _load_parser_tests():
    path = _TESTS_DIR / 'test_booker_parser.py'
    spec = importlib.util.spec_from_file_location('test_booker_parser', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_PARSER_TESTS = _load_parser_tests()
MIDNIGHTS_CHILDREN = _PARSER_TESTS.MIDNIGHTS_CHILDREN
archive_html = _PARSER_TESTS.archive_html

MIDNIGHT_URL = (
    'https://thebookerprizes.com/the-booker-library/books/midnights-children'
)


def _record(year, title, author, slug, status='Winner'):
    return booker._ParsedRecord(
        award_year=year,
        category=booker.CATEGORY,
        status=status,
        work_title=title,
        work_author=author,
        source_url=f'https://thebookerprizes.com/the-booker-library/books/{slug}',
    )


def _complete_archive(*, current_year=None, extra=()):
    if current_year is None:
        current_year = booker._current_calendar_year()
    records = []
    for year in range(booker.ARCHIVE_MIN_YEAR, current_year):
        if year == 1974:
            records.append(
                _record(year, 'The Conservationist', 'Nadine Gordimer', 'the-conservationist')
            )
            records.append(_record(year, 'Holiday', 'Stanley Middleton', 'holiday'))
        elif year == 1981:
            records.append(
                _record(year, MIDNIGHTS_CHILDREN, 'Salman Rushdie', 'midnights-children')
            )
        elif year == 1992:
            records.append(
                _record(year, 'The English Patient', 'Michael Ondaatje', 'the-english-patient')
            )
            records.append(_record(year, 'Sacred Hunger', 'Barry Unsworth', 'sacred-hunger'))
        elif year == 2019:
            records.append(
                _record(year, 'Girl, Woman, Other', 'Bernardine Evaristo', 'girl-woman-other')
            )
            records.append(_record(year, 'The Testaments', 'Margaret Atwood', 'the-testaments'))
        else:
            records.append(
                _record(
                    year,
                    f'Stub Winner {year}',
                    f'Stub Winner Author {year}',
                    f'stub-winner-{year}',
                )
            )
        records.append(
            _record(
                year,
                f'Stub Short {year}',
                f'Stub Short Author {year}',
                f'stub-short-{year}',
                'Shortlisted',
            )
        )
    records.extend(extra)
    return tuple(records)


def _with_extra_shortlisted(archive):
    extra = _record(
        2024,
        'Orbital',
        'Samantha Harvey',
        'orbital',
        'Shortlisted',
    )
    return archive + (extra,)


def _save_disk(records, *, generated_at=None, ttl_seconds=None, version=None):
    cache.save_source_cache(
        booker.SOURCE_KEY,
        booker.CACHE_VERSION if version is None else version,
        records=[booker._record_to_cache_dict(record) for record in records],
        source_urls=booker._archive_source_urls(),
        coverage=booker._coverage_from_records(records),
        ttl_seconds=(
            booker.CACHE_TTL_SECONDS if ttl_seconds is None else ttl_seconds
        ),
        generated_at=generated_at,
    )


class BookerPersistentCacheTests(unittest.TestCase):
    def setUp(self):
        booker._reset_runtime_state()
        cache._reset_runtime_state()
        self._temp = TemporaryDirectory()
        self.cache_dir = Path(self._temp.name)
        cache.set_cache_directory(self.cache_dir)

    def tearDown(self):
        booker._reset_runtime_state()
        cache._reset_runtime_state()
        self._temp.cleanup()

    def _disk_path(self):
        return self.cache_dir / 'booker.json'

    def _rewrite_records(self, mutate):
        payload = json.loads(self._disk_path().read_text(encoding='utf-8'))
        mutate(payload)
        self._disk_path().write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
            + '\n',
            encoding='utf-8',
        )

    def _assert_midnight(self, results):
        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertEqual(result.work_title, MIDNIGHTS_CHILDREN)
        self.assertEqual(result.work_author, 'Salman Rushdie')
        self.assertEqual(result.award_name, 'Booker Prize')
        self.assertEqual(result.award_year, 1981)
        self.assertEqual(result.category, 'Fiction')
        self.assertEqual(result.status, 'Winner')
        self.assertIsNone(result.rank)
        self.assertEqual(result.source_name, 'The Booker Prize')
        self.assertEqual(result.source_url, MIDNIGHT_URL)
        self.assertIsNone(result.notes)

    def test_cache_identity_constants(self):
        self.assertEqual(booker.SOURCE_KEY, 'booker')
        self.assertEqual(booker.CACHE_VERSION, 1)
        self.assertEqual(booker.CACHE_BASE_TTL_SECONDS, 7 * 24 * 60 * 60)
        self.assertEqual(booker.CACHE_REFRESH_OFFSET_SECONDS, 6 * 60 * 60)
        self.assertEqual(
            booker.CACHE_TTL_SECONDS,
            booker.CACHE_BASE_TTL_SECONDS + booker.CACHE_REFRESH_OFFSET_SECONDS,
        )
        self.assertEqual(booker.CACHE_TTL_SECONDS, 626400)

    def test_complete_archive_helper_passes_source_validation(self):
        booker._validate_cached_archive(_complete_archive())

    def test_known_historical_joint_years_have_exactly_two_winners(self):
        self.assertEqual(booker._JOINT_WINNER_YEARS, frozenset({1974, 1992, 2019}))
        archive = _complete_archive()
        for year in (1974, 1992, 2019):
            winners = [
                record
                for record in archive
                if record.award_year == year and record.status == 'Winner'
            ]
            with self.subTest(year=year):
                self.assertEqual(len(winners), 2)

    def test_completed_year_with_one_winner_is_valid(self):
        archive = [
            record
            for record in _complete_archive()
            if not (record.award_year == 1974 and record.work_title == 'Holiday')
        ]
        booker._validate_cached_archive(tuple(archive))

    def test_completed_year_with_two_winners_is_valid(self):
        extra = _record(
            1981, 'Second 1981 Winner', 'Other Author', 'second-1981-winner'
        )
        booker._validate_cached_archive(_complete_archive() + (extra,))

    def test_completed_year_with_zero_winners_is_invalid(self):
        archive = [
            record
            for record in _complete_archive()
            if not (record.award_year == 1970 and record.status == 'Winner')
        ]
        with self.assertRaises(booker.BookerSourceError) as raised:
            booker._validate_cached_archive(tuple(archive))
        self.assertIn('1970', str(raised.exception))
        self.assertIn('1 or 2', str(raised.exception))

    def test_completed_year_with_more_than_two_winners_is_invalid(self):
        extras = (
            _record(1974, 'Third 1974 Winner', 'Third Author', 'third-1974-winner'),
        )
        with self.assertRaises(booker.BookerSourceError) as raised:
            booker._validate_cached_archive(_complete_archive() + extras)
        self.assertIn('1974', str(raised.exception))

    def test_parsed_record_round_trips_all_fields(self):
        original = _record(
            1981, MIDNIGHTS_CHILDREN, 'Salman Rushdie', 'midnights-children'
        )
        restored = booker._record_from_cache_dict(
            booker._record_to_cache_dict(original)
        )
        self.assertEqual(restored, original)
        shortlisted = _record(
            1984,
            'Empire of the Sun',
            'J. G. Ballard',
            'empire-of-the-sun',
            'Shortlisted',
        )
        self.assertEqual(
            booker._record_from_cache_dict(
                booker._record_to_cache_dict(shortlisted)
            ),
            shortlisted,
        )

    def test_rank_is_not_persisted(self):
        payload = booker._record_to_cache_dict(
            _record(1981, MIDNIGHTS_CHILDREN, 'Salman Rushdie', 'midnights-children')
        )
        self.assertNotIn('rank', payload)
        self.assertEqual(set(payload), set(booker._RECORD_CACHE_FIELDS))

    def test_live_validated_archive_writes_booker_json(self):
        archive = _complete_archive()
        with patch.object(booker, '_load_live_archive', return_value=archive):
            results = booker.lookup(MIDNIGHTS_CHILDREN, 'Salman Rushdie')
        self._assert_midnight(results)
        self.assertTrue(self._disk_path().is_file())
        payload = json.loads(self._disk_path().read_text(encoding='utf-8'))
        self.assertEqual(payload['source_key'], 'booker')
        self.assertEqual(payload['source_urls'], [booker.SOURCE_HOME_URL])
        self.assertGreater(payload['record_count'], 0)

    def test_fresh_cache_lookup_makes_zero_network_calls(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        booker._reset_runtime_state()
        with patch.object(
            booker, '_fetch_html', side_effect=AssertionError('network')
        ), patch.object(
            booker, '_load_live_archive', side_effect=AssertionError('live')
        ):
            results = booker.lookup(MIDNIGHTS_CHILDREN, 'Salman Rushdie')
        self._assert_midnight(results)

    def test_fresh_cache_does_not_consume_refresh_budget(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        booker._reset_runtime_state()
        with cache.lookup_refresh_budget():
            with patch.object(
                booker, '_load_live_archive', side_effect=AssertionError('live')
            ):
                results = booker.lookup(MIDNIGHTS_CHILDREN, 'Salman Rushdie')
            self._assert_midnight(results)
            self.assertTrue(cache.try_claim_stale_refresh())

    def test_ram_reset_plus_fresh_disk_makes_zero_http(self):
        archive = _complete_archive()
        with patch.object(booker, '_load_live_archive', return_value=archive) as live:
            first = booker.lookup(MIDNIGHTS_CHILDREN, 'Salman Rushdie')
        self._assert_midnight(first)
        self.assertEqual(live.call_count, 1)
        booker._reset_runtime_state()
        self.assertTrue(self._disk_path().is_file())
        with patch.object(
            booker, '_fetch_html', side_effect=AssertionError('network')
        ), patch.object(
            booker, '_load_live_archive', side_effect=AssertionError('live')
        ):
            second = booker.lookup(MIDNIGHTS_CHILDREN, 'Salman Rushdie')
        self._assert_midnight(second)

    def test_stale_cache_successful_refresh_replaces_disk(self):
        stale = _complete_archive()
        _save_disk(
            stale,
            generated_at=datetime(2020, 1, 1, tzinfo=_UTC),
            ttl_seconds=60,
        )
        original = self._disk_path().read_text(encoding='utf-8')
        original_generated = json.loads(original)['generated_at']
        refreshed = _with_extra_shortlisted(stale)
        with patch.object(booker, '_load_live_archive', return_value=refreshed):
            results = booker.lookup(MIDNIGHTS_CHILDREN, 'Salman Rushdie')
        self._assert_midnight(results)
        updated = json.loads(self._disk_path().read_text(encoding='utf-8'))
        self.assertNotEqual(updated['generated_at'], original_generated)
        extra = booker.lookup('Orbital', 'Samantha Harvey')
        self.assertEqual(len(extra), 1)
        self.assertEqual(extra[0].status, 'Shortlisted')

    def test_stale_cache_live_failure_keeps_file_unchanged(self):
        stale = _complete_archive()
        _save_disk(
            stale,
            generated_at=datetime(2020, 1, 1, tzinfo=_UTC),
            ttl_seconds=60,
        )
        original = self._disk_path().read_text(encoding='utf-8')
        with patch.object(
            booker,
            '_load_live_archive',
            side_effect=booker.BookerSourceError('archive down'),
        ):
            results = booker.lookup(MIDNIGHTS_CHILDREN, 'Salman Rushdie')
        self._assert_midnight(results)
        self.assertEqual(self._disk_path().read_text(encoding='utf-8'), original)

    def test_stale_cache_without_refresh_slot_uses_stale_and_skips_network(self):
        stale = _complete_archive()
        _save_disk(
            stale,
            generated_at=datetime(2020, 1, 1, tzinfo=_UTC),
            ttl_seconds=60,
        )
        booker._reset_runtime_state()
        with cache.lookup_refresh_budget():
            self.assertTrue(cache.try_claim_stale_refresh())
            with patch.object(
                booker, '_load_live_archive', side_effect=AssertionError('live')
            ) as mocked, patch.object(
                booker, '_fetch_html', side_effect=AssertionError('network')
            ):
                results = booker.lookup(MIDNIGHTS_CHILDREN, 'Salman Rushdie')
            mocked.assert_not_called()
        self._assert_midnight(results)

    def test_missing_cache_live_fetches_after_stale_refresh_budget_consumed(self):
        self.assertFalse(self._disk_path().is_file())
        live = _complete_archive()
        with cache.lookup_refresh_budget():
            self.assertTrue(cache.try_claim_stale_refresh())
            with patch.object(
                booker, '_load_live_archive', return_value=live
            ) as mocked:
                results = booker.lookup(MIDNIGHTS_CHILDREN, 'Salman Rushdie')
            self.assertEqual(mocked.call_count, 1)
        self._assert_midnight(results)

    def test_no_cache_live_failure_still_raises(self):
        self.assertFalse(self._disk_path().is_file())
        with patch.object(
            booker,
            '_load_live_archive',
            side_effect=booker.BookerSourceError('HTTP 500'),
        ):
            with self.assertRaises(booker.BookerSourceError):
                booker.lookup(MIDNIGHTS_CHILDREN, 'Salman Rushdie')
        self.assertIsNone(booker._archive_records_cache)
        self.assertFalse(self._disk_path().is_file())

    def test_malformed_live_does_not_write_cache(self):
        self.assertFalse(self._disk_path().is_file())
        with patch.object(
            booker, '_fetch_html', return_value='<html><h1>Unrelated</h1></html>'
        ):
            with self.assertRaises(booker.BookerSourceError):
                booker.lookup(MIDNIGHTS_CHILDREN, 'Salman Rushdie')
        self.assertFalse(self._disk_path().is_file())

    def test_malformed_disk_requires_live(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        self._rewrite_records(
            lambda payload: payload['records'][0].__setitem__('award_year', 0)
        )
        live = _complete_archive()
        with patch.object(
            booker, '_load_live_archive', return_value=live
        ) as mocked:
            booker.lookup(MIDNIGHTS_CHILDREN, 'Salman Rushdie')
        self.assertEqual(mocked.call_count, 1)

    def test_bool_award_year_is_rejected(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        self._rewrite_records(
            lambda payload: payload['records'][0].__setitem__('award_year', True)
        )
        live = _complete_archive()
        with patch.object(
            booker, '_load_live_archive', return_value=live
        ) as mocked:
            booker.lookup(MIDNIGHTS_CHILDREN, 'Salman Rushdie')
        self.assertEqual(mocked.call_count, 1)

    def test_wrong_category_is_rejected(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        self._rewrite_records(
            lambda payload: payload['records'][0].__setitem__('category', 'Poetry')
        )
        live = _complete_archive()
        with patch.object(
            booker, '_load_live_archive', return_value=live
        ) as mocked:
            booker.lookup(MIDNIGHTS_CHILDREN, 'Salman Rushdie')
        self.assertEqual(mocked.call_count, 1)

    def test_invalid_status_is_rejected(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        self._rewrite_records(
            lambda payload: payload['records'][0].__setitem__('status', 'Longlisted')
        )
        live = _complete_archive()
        with patch.object(
            booker, '_load_live_archive', return_value=live
        ) as mocked:
            booker.lookup(MIDNIGHTS_CHILDREN, 'Salman Rushdie')
        self.assertEqual(mocked.call_count, 1)

    def test_off_host_source_url_is_rejected(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        self._rewrite_records(
            lambda payload: payload['records'][0].__setitem__(
                'source_url', 'https://example.com/the-booker-library/books/x'
            )
        )
        live = _complete_archive()
        with patch.object(
            booker, '_load_live_archive', return_value=live
        ) as mocked:
            booker.lookup(MIDNIGHTS_CHILDREN, 'Salman Rushdie')
        self.assertEqual(mocked.call_count, 1)

    def test_rank_field_in_cache_record_is_rejected(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        self._rewrite_records(
            lambda payload: payload['records'][0].__setitem__('rank', None)
        )
        live = _complete_archive()
        with patch.object(
            booker, '_load_live_archive', return_value=live
        ) as mocked:
            booker.lookup(MIDNIGHTS_CHILDREN, 'Salman Rushdie')
        self.assertEqual(mocked.call_count, 1)

    def test_missing_winner_coverage_is_rejected(self):
        archive = [
            record
            for record in _complete_archive()
            if record.status != 'Winner' or record.award_year != 1970
        ]
        cache.save_source_cache(
            booker.SOURCE_KEY,
            booker.CACHE_VERSION,
            records=[booker._record_to_cache_dict(record) for record in archive],
            source_urls=booker._archive_source_urls(),
            coverage={'winner_count': 0},
            ttl_seconds=booker.CACHE_TTL_SECONDS,
            generated_at=datetime.now(_UTC),
        )
        live = _complete_archive()
        with patch.object(
            booker, '_load_live_archive', return_value=live
        ) as mocked:
            results = booker.lookup(MIDNIGHTS_CHILDREN, 'Salman Rushdie')
        self.assertEqual(mocked.call_count, 1)
        self._assert_midnight(results)

    def test_wrong_source_urls_are_rejected(self):
        archive = _complete_archive()
        cache.save_source_cache(
            booker.SOURCE_KEY,
            booker.CACHE_VERSION,
            records=[booker._record_to_cache_dict(record) for record in archive],
            source_urls=['https://thebookerprizes.com/'],
            coverage=booker._coverage_from_records(archive),
            ttl_seconds=booker.CACHE_TTL_SECONDS,
            generated_at=datetime.now(_UTC),
        )
        live = _complete_archive()
        with patch.object(
            booker, '_load_live_archive', return_value=live
        ) as mocked:
            booker.lookup(MIDNIGHTS_CHILDREN, 'Salman Rushdie')
        self.assertEqual(mocked.call_count, 1)

    def test_version_mismatch_uses_live_path(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC), version=2)
        live = _complete_archive()
        with patch.object(
            booker, '_load_live_archive', return_value=live
        ) as mocked:
            results = booker.lookup(MIDNIGHTS_CHILDREN, 'Salman Rushdie')
        self.assertEqual(mocked.call_count, 1)
        self._assert_midnight(results)

    def test_save_failure_does_not_fail_lookup(self):
        archive = _complete_archive()
        with patch.object(booker, '_load_live_archive', return_value=archive):
            with patch.object(
                booker.cache,
                'save_source_cache',
                side_effect=OSError('disk full'),
            ):
                results = booker.lookup(MIDNIGHTS_CHILDREN, 'Salman Rushdie')
        self._assert_midnight(results)

    def test_ram_reset_does_not_delete_disk_cache(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        booker._archive_records_cache = archive
        self.assertTrue(self._disk_path().is_file())
        booker._reset_runtime_state()
        self.assertTrue(self._disk_path().is_file())
        self.assertIsNone(booker._archive_records_cache)
        with patch.object(
            booker, '_load_live_archive', side_effect=AssertionError('live')
        ), patch.object(
            booker, '_fetch_html', side_effect=AssertionError('network')
        ):
            results = booker.lookup(MIDNIGHTS_CHILDREN, 'Salman Rushdie')
        self._assert_midnight(results)

    def test_manual_refresh_removes_booker_json_and_ram_only(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        booker._archive_records_cache = archive
        hugo._archive_records_cache = ()
        _save_disk_hugo = cache.save_source_cache
        _save_disk_hugo(
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
            booker, '_fetch_html', side_effect=AssertionError('network')
        ), patch.object(
            booker, '_load_live_archive', side_effect=AssertionError('live')
        ):
            self.assertTrue(refresh_award_source_cache('booker'))
        self.assertFalse(self._disk_path().exists())
        self.assertIsNone(booker._archive_records_cache)
        self.assertTrue((self.cache_dir / 'hugo.json').is_file())
        self.assertTrue(pulitzer_path.is_file())
        self.assertEqual(hugo._archive_records_cache, ())

    def test_manual_refresh_makes_zero_http(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        booker._archive_records_cache = archive
        with patch.object(
            booker, '_fetch_html', side_effect=AssertionError('network')
        ) as fetch, patch.object(
            booker, 'lookup', side_effect=AssertionError('lookup')
        ):
            self.assertTrue(refresh_award_source_cache('booker'))
        fetch.assert_not_called()


class BookerLiveHtmlCachePathTests(unittest.TestCase):
    def setUp(self):
        booker._reset_runtime_state()
        cache._reset_runtime_state()
        self._temp = TemporaryDirectory()
        cache.set_cache_directory(Path(self._temp.name))

    def tearDown(self):
        booker._reset_runtime_state()
        cache._reset_runtime_state()
        self._temp.cleanup()

    def test_parse_of_generated_archive_html_is_cacheable(self):
        html = archive_html(max_year=2026)
        with patch.object(booker, '_current_calendar_year', return_value=2026):
            records, years = booker._parse_archive_html(html)
            booker._validate_archive(records, years)
            _save_disk(records, generated_at=datetime.now(_UTC))
            booker._reset_runtime_state()
            with patch.object(
                booker, '_fetch_html', side_effect=AssertionError('network')
            ):
                results = booker.lookup(MIDNIGHTS_CHILDREN, 'Salman Rushdie')
        self.assertEqual(results[0].award_year, 1981)
        self.assertEqual(results[0].status, 'Winner')


if __name__ == '__main__':
    unittest.main()
