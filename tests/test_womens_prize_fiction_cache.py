"""Offline coverage for Women's Prize for Fiction persistent archive cache."""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from awards import cache
from awards.cache_control import refresh_award_source_cache
from awards.sources import hugo, pulitzer, womens_prize_fiction as wpf
from tests.test_womens_prize_fiction_parser import (
    _OFFICIAL,
    archive_html,
    home_html,
)

_UTC = timezone.utc


def _record(year, title=None, author=None, slug=None):
    if title is None or author is None or slug is None:
        title, author, slug = _OFFICIAL[year]
    return wpf._ParsedRecord(
        award_year=year,
        category=wpf.CATEGORY,
        status='Winner',
        work_title=title,
        work_author=author,
        source_url=f'https://womensprize.com/library/{slug}/',
    )


def _complete_archive(*, current_year=2026, include_current=True, max_year=None):
    if max_year is None:
        max_year = current_year if include_current else current_year - 1
    records = [_record(year) for year in range(wpf.ARCHIVE_MIN_YEAR, max_year + 1)]
    return tuple(records)


def _snapshot(records, *, archive_max_year=None, current_year=2026):
    if archive_max_year is None:
        archive_max_year = max(
            year for year in (record.award_year for record in records)
            if year < current_year or year == max(r.award_year for r in records)
        )
        archived = [record.award_year for record in records if record.award_year != current_year]
        archive_max_year = max(archived) if archived else max(
            record.award_year for record in records
        )
    state = 'winner' if any(
        record.award_year == current_year for record in records
    ) else 'absent'
    return wpf._ParseSnapshot(
        records=records,
        archive_max_year=archive_max_year,
        current_year_state=state,
    )


def _save_disk(records, *, generated_at=None, ttl_seconds=None, version=None, current_year=2026):
    with patch.object(wpf, '_current_calendar_year', return_value=current_year):
        cache.save_source_cache(
            wpf.SOURCE_KEY,
            wpf.CACHE_VERSION if version is None else version,
            records=[wpf._record_to_cache_dict(record) for record in records],
            source_urls=wpf._archive_source_urls(),
            coverage=wpf._coverage_from_snapshot(
                _snapshot(records, current_year=current_year)
            ),
            ttl_seconds=(
                wpf.CACHE_TTL_SECONDS if ttl_seconds is None else ttl_seconds
            ),
            generated_at=generated_at,
        )


def _fetch_ok(url):
    if url == wpf.PREVIOUS_PRIZES_URL:
        return archive_html(max_year=2025)
    if url == wpf.SOURCE_HOME_URL:
        return home_html()
    raise AssertionError(url)


class WomensPrizeFictionPersistentCacheTests(unittest.TestCase):
    def setUp(self):
        wpf._reset_runtime_state()
        cache._reset_runtime_state()
        self._temp = TemporaryDirectory()
        self.cache_dir = Path(self._temp.name)
        cache.set_cache_directory(self.cache_dir)
        self._shortlist_stub = patch.object(
            wpf, '_get_shortlisted_records', return_value=()
        )
        self._shortlist_stub.start()

    def tearDown(self):
        self._shortlist_stub.stop()
        wpf._reset_runtime_state()
        cache._reset_runtime_state()
        self._temp.cleanup()

    def _disk_path(self):
        return self.cache_dir / 'womens_prize_fiction.json'

    def _rewrite(self, mutate):
        payload = json.loads(self._disk_path().read_text(encoding='utf-8'))
        mutate(payload)
        self._disk_path().write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
            + '\n',
            encoding='utf-8',
        )

    def _assert_dunmore(self, results):
        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertEqual(result.work_title, 'A Spell of Winter')
        self.assertEqual(result.work_author, 'Helen Dunmore')
        self.assertEqual(result.award_name, "Women's Prize for Fiction")
        self.assertEqual(result.award_year, 1996)
        self.assertEqual(result.category, 'Fiction')
        self.assertEqual(result.status, 'Winner')
        self.assertIsNone(result.rank)
        self.assertEqual(result.source_name, "Women's Prize for Fiction")
        self.assertEqual(
            result.source_url,
            'https://womensprize.com/library/a-spell-of-winter/',
        )
        self.assertIsNone(result.notes)
        self.assertEqual(result.identity_kind, 'work')

    def test_cache_identity_constants(self):
        self.assertEqual(wpf.SOURCE_KEY, 'womens_prize_fiction')
        self.assertEqual(wpf.CACHE_VERSION, 1)
        self.assertEqual(wpf.CACHE_BASE_TTL_SECONDS, 7 * 24 * 60 * 60)
        self.assertEqual(wpf.CACHE_REFRESH_OFFSET_SECONDS, 10 * 60 * 60)
        self.assertEqual(
            wpf.CACHE_TTL_SECONDS,
            wpf.CACHE_BASE_TTL_SECONDS + wpf.CACHE_REFRESH_OFFSET_SECONDS,
        )
        self.assertEqual(wpf.CACHE_TTL_SECONDS, 640800)

    def test_live_success_writes_womens_prize_fiction_json(self):
        archive = _complete_archive(current_year=2026)
        with patch.object(wpf, '_current_calendar_year', return_value=2026):
            with patch.object(wpf, '_load_live_archive', return_value=archive):
                results = wpf.lookup('A Spell of Winter', 'Helen Dunmore')
        self._assert_dunmore(results)
        self.assertTrue(self._disk_path().is_file())
        payload = json.loads(self._disk_path().read_text(encoding='utf-8'))
        self.assertEqual(payload['source_key'], 'womens_prize_fiction')
        self.assertEqual(
            payload['source_urls'],
            [wpf.PREVIOUS_PRIZES_URL, wpf.SOURCE_HOME_URL],
        )
        encoded = json.dumps(payload)
        self.assertNotIn('<html', encoded)
        self.assertNotIn('shortlist', encoded.casefold())
        self.assertNotIn('longlist', encoded.casefold())
        self.assertNotIn('query_title', encoded)
        self.assertNotIn('qualification', encoded)
        self.assertEqual(payload['coverage']['min_year'], 1996)
        self.assertEqual(payload['coverage']['max_winner_year'], 2026)
        self.assertEqual(payload['coverage']['current_year'], 2026)
        self.assertEqual(payload['coverage']['current_year_state'], 'winner')
        self.assertEqual(payload['record_count'], 31)

    def test_cold_success_performs_exactly_two_gets(self):
        fetched = []

        def _fetch(url):
            fetched.append(url)
            return _fetch_ok(url)

        with patch.object(wpf, '_current_calendar_year', return_value=2026):
            with patch.object(wpf, '_fetch_html', side_effect=_fetch):
                results = wpf.lookup('The Correspondent', 'Virginia Evans')
        self.assertEqual(fetched, [wpf.PREVIOUS_PRIZES_URL, wpf.SOURCE_HOME_URL])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].award_year, 2026)
        self.assertTrue(self._disk_path().is_file())

    def test_fresh_disk_replay_makes_zero_http(self):
        archive = _complete_archive(current_year=2026)
        with patch.object(wpf, '_current_calendar_year', return_value=2026):
            _save_disk(archive, generated_at=datetime.now(_UTC))
            wpf._reset_runtime_state()
            with patch.object(
                wpf, '_fetch_html', side_effect=AssertionError('network')
            ), patch.object(
                wpf, '_load_live_archive', side_effect=AssertionError('live')
            ):
                results = wpf.lookup('A Spell of Winter', 'Helen Dunmore')
        self._assert_dunmore(results)

    def test_ram_reset_plus_fresh_disk_makes_zero_http(self):
        archive = _complete_archive(current_year=2026)
        with patch.object(wpf, '_current_calendar_year', return_value=2026):
            with patch.object(wpf, '_load_live_archive', return_value=archive) as live:
                first = wpf.lookup('A Spell of Winter', 'Helen Dunmore')
            self._assert_dunmore(first)
            self.assertEqual(live.call_count, 1)
            wpf._reset_runtime_state()
            self.assertTrue(self._disk_path().is_file())
            with patch.object(
                wpf, '_fetch_html', side_effect=AssertionError('network')
            ), patch.object(
                wpf, '_load_live_archive', side_effect=AssertionError('live')
            ):
                second = wpf.lookup('A Spell of Winter', 'Helen Dunmore')
        self._assert_dunmore(second)

    def test_stale_slot_live_success_replaces_disk(self):
        stale = _complete_archive(current_year=2026, include_current=False)
        with patch.object(wpf, '_current_calendar_year', return_value=2026):
            _save_disk(
                stale,
                generated_at=datetime(2020, 1, 1, tzinfo=_UTC),
                ttl_seconds=60,
            )
            original_generated = json.loads(
                self._disk_path().read_text(encoding='utf-8')
            )['generated_at']
            refreshed = _complete_archive(current_year=2026)
            with cache.lookup_refresh_budget():
                with patch.object(wpf, '_load_live_archive', return_value=refreshed):
                    results = wpf.lookup('A Spell of Winter', 'Helen Dunmore')
            self._assert_dunmore(results)
            updated = json.loads(self._disk_path().read_text(encoding='utf-8'))
            self.assertNotEqual(updated['generated_at'], original_generated)
            extra = wpf.lookup('The Correspondent', 'Virginia Evans')
            self.assertEqual(len(extra), 1)
            self.assertEqual(extra[0].award_year, 2026)

    def test_stale_slot_live_failure_keeps_file_unchanged(self):
        stale = _complete_archive(current_year=2026)
        with patch.object(wpf, '_current_calendar_year', return_value=2026):
            _save_disk(
                stale,
                generated_at=datetime(2020, 1, 1, tzinfo=_UTC),
                ttl_seconds=60,
            )
            original = self._disk_path().read_text(encoding='utf-8')
            with cache.lookup_refresh_budget():
                with patch.object(
                    wpf,
                    '_load_live_archive',
                    side_effect=wpf.WomensPrizeFictionSourceError('down'),
                ):
                    results = wpf.lookup('A Spell of Winter', 'Helen Dunmore')
            self._assert_dunmore(results)
            self.assertEqual(self._disk_path().read_text(encoding='utf-8'), original)

    def test_stale_without_slot_uses_stale_and_skips_network(self):
        stale = _complete_archive(current_year=2026)
        with patch.object(wpf, '_current_calendar_year', return_value=2026):
            _save_disk(
                stale,
                generated_at=datetime(2020, 1, 1, tzinfo=_UTC),
                ttl_seconds=60,
            )
            wpf._reset_runtime_state()
            with cache.lookup_refresh_budget():
                self.assertTrue(cache.try_claim_stale_refresh())
                with patch.object(
                    wpf, '_load_live_archive', side_effect=AssertionError('live')
                ) as mocked, patch.object(
                    wpf, '_fetch_html', side_effect=AssertionError('network')
                ):
                    results = wpf.lookup('A Spell of Winter', 'Helen Dunmore')
                mocked.assert_not_called()
        self._assert_dunmore(results)

    def test_missing_cache_requires_live(self):
        self.assertFalse(self._disk_path().is_file())
        live = _complete_archive(current_year=2026)
        with patch.object(wpf, '_current_calendar_year', return_value=2026):
            with patch.object(wpf, '_load_live_archive', return_value=live) as mocked:
                results = wpf.lookup('A Spell of Winter', 'Helen Dunmore')
            self.assertEqual(mocked.call_count, 1)
        self._assert_dunmore(results)

    def test_malformed_disk_requires_live(self):
        archive = _complete_archive(current_year=2026)
        with patch.object(wpf, '_current_calendar_year', return_value=2026):
            _save_disk(archive, generated_at=datetime.now(_UTC))
            self._rewrite(
                lambda payload: payload['records'][0].__setitem__('award_year', 0)
            )
            live = _complete_archive(current_year=2026)
            with patch.object(wpf, '_load_live_archive', return_value=live) as mocked:
                wpf.lookup('A Spell of Winter', 'Helen Dunmore')
            self.assertEqual(mocked.call_count, 1)

    def test_version_mismatch_uses_live_path(self):
        archive = _complete_archive(current_year=2026)
        with patch.object(wpf, '_current_calendar_year', return_value=2026):
            _save_disk(archive, generated_at=datetime.now(_UTC), version=2)
            live = _complete_archive(current_year=2026)
            with patch.object(wpf, '_load_live_archive', return_value=live) as mocked:
                results = wpf.lookup('A Spell of Winter', 'Helen Dunmore')
            self.assertEqual(mocked.call_count, 1)
        self._assert_dunmore(results)

    def test_malformed_archive_page_does_not_write_cache(self):
        self.assertFalse(self._disk_path().is_file())
        with patch.object(
            wpf, '_fetch_html', return_value='<html><h1>Unrelated</h1></html>'
        ):
            with self.assertRaises(wpf.WomensPrizeFictionSourceError):
                wpf.lookup('A Spell of Winter', 'Helen Dunmore')
        self.assertFalse(self._disk_path().is_file())

    def test_wrong_page_identity_does_not_write_cache(self):
        html = (
            '<html><h1>Women\'s Prize for Non-Fiction</h1>'
            '<section class="book-grid"></section></html>'
        )
        with patch.object(wpf, '_fetch_html', return_value=html):
            with self.assertRaises(wpf.WomensPrizeFictionSourceError):
                wpf.lookup('A Spell of Winter', 'Helen Dunmore')
        self.assertFalse(self._disk_path().is_file())

    def test_missing_1996_anchor_rejects_live_and_does_not_write(self):
        html = archive_html().replace(
            'A Spell of Winter',
            'Wrong Oldest',
        ).replace('Helen Dunmore', 'Someone Else')

        def _fetch(url):
            if url == wpf.PREVIOUS_PRIZES_URL:
                return html
            return home_html()

        with patch.object(wpf, '_current_calendar_year', return_value=2026):
            with patch.object(wpf, '_fetch_html', side_effect=_fetch):
                with self.assertRaises(wpf.WomensPrizeFictionSourceError):
                    wpf.lookup('A Spell of Winter', 'Helen Dunmore')
        self.assertFalse(self._disk_path().is_file())

    def test_historical_gap_is_rejected(self):
        archive = [
            record
            for record in _complete_archive(current_year=2026)
            if record.award_year != 2010
        ]
        with patch.object(wpf, '_current_calendar_year', return_value=2026):
            with self.assertRaises(wpf.WomensPrizeFictionSourceError) as raised:
                wpf._validate_cached_archive(tuple(archive))
            self.assertIn('2010', str(raised.exception))

    def test_archive_card_count_growth_is_accepted(self):
        with patch.object(wpf, '_current_calendar_year', return_value=2026):
            grown = _complete_archive(current_year=2026, max_year=2026)
            wpf._validate_cached_archive(grown)
            coverage = wpf._coverage_from_snapshot(
                _snapshot(grown, archive_max_year=2026, current_year=2026)
            )
            self.assertEqual(coverage['archive_max_year'], 2026)
            self.assertEqual(coverage['max_winner_year'], 2026)

    def test_current_year_winner_is_optional_when_not_yet_awarded(self):
        absent = _complete_archive(current_year=2026, include_current=False)
        with patch.object(wpf, '_current_calendar_year', return_value=2026):
            wpf._validate_cached_archive(absent)
            coverage = wpf._coverage_from_snapshot(
                _snapshot(absent, archive_max_year=2025, current_year=2026)
            )
            self.assertEqual(coverage['current_year_state'], 'absent')
            self.assertEqual(coverage['max_winner_year'], 2025)

    def test_completed_prior_year_winner_is_required(self):
        incomplete = _complete_archive(current_year=2026, include_current=False)
        with patch.object(wpf, '_current_calendar_year', return_value=2027):
            with self.assertRaises(wpf.WomensPrizeFictionSourceError) as raised:
                wpf._validate_cached_archive(incomplete)
            self.assertIn('2026', str(raised.exception))

    def test_january_rollover_accepts_official_prior_year_from_main_page(self):
        def _fetch(url):
            if url == wpf.PREVIOUS_PRIZES_URL:
                return archive_html(max_year=2025)
            if url == wpf.SOURCE_HOME_URL:
                return home_html(year=2026)
            raise AssertionError(url)

        with patch.object(wpf, '_current_calendar_year', return_value=2027):
            with patch.object(wpf, '_fetch_html', side_effect=_fetch):
                results = wpf.lookup('The Correspondent', 'Virginia Evans')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].award_year, 2026)
        payload = json.loads(self._disk_path().read_text(encoding='utf-8'))
        self.assertEqual(payload['coverage']['max_winner_year'], 2026)
        self.assertEqual(payload['coverage']['current_year_state'], 'absent')

    def test_duplicate_archive_and_main_winner_merges_once(self):
        def _fetch(url):
            if url == wpf.PREVIOUS_PRIZES_URL:
                return archive_html(max_year=2026)
            if url == wpf.SOURCE_HOME_URL:
                return home_html()
            raise AssertionError(url)

        with patch.object(wpf, '_current_calendar_year', return_value=2026):
            with patch.object(wpf, '_fetch_html', side_effect=_fetch):
                results = wpf.lookup('The Correspondent', 'Virginia Evans')
        self.assertEqual(len(results), 1)
        payload = json.loads(self._disk_path().read_text(encoding='utf-8'))
        years = [item['award_year'] for item in payload['records']]
        self.assertEqual(years.count(2026), 1)
        self.assertEqual(payload['record_count'], 31)

    def test_home_failure_today_may_keep_completed_archive_without_2026(self):
        def _fetch(url):
            if url == wpf.PREVIOUS_PRIZES_URL:
                return archive_html(max_year=2025)
            raise wpf.WomensPrizeFictionSourceError('home down')

        with patch.object(wpf, '_current_calendar_year', return_value=2026):
            with patch.object(wpf, '_fetch_html', side_effect=_fetch):
                results = wpf.lookup('A Spell of Winter', 'Helen Dunmore')
        self._assert_dunmore(results)
        payload = json.loads(self._disk_path().read_text(encoding='utf-8'))
        years = [item['award_year'] for item in payload['records']]
        self.assertEqual(max(years), 2025)
        self.assertNotIn(2026, years)

    def test_archive_failure_without_cache_fails_closed(self):
        def _fetch(url):
            raise wpf.WomensPrizeFictionSourceError('archive down')

        with patch.object(wpf, '_fetch_html', side_effect=_fetch):
            with self.assertRaises(wpf.WomensPrizeFictionSourceError):
                wpf.lookup('A Spell of Winter', 'Helen Dunmore')
        self.assertFalse(self._disk_path().is_file())

    def test_manual_refresh_removes_only_womens_prize_cache_and_ram(self):
        archive = _complete_archive(current_year=2026)
        with patch.object(wpf, '_current_calendar_year', return_value=2026):
            _save_disk(archive, generated_at=datetime.now(_UTC))
        wpf._archive_records_cache = archive
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
            wpf, '_fetch_html', side_effect=AssertionError('network')
        ), patch.object(
            wpf, '_load_live_archive', side_effect=AssertionError('live')
        ):
            self.assertTrue(refresh_award_source_cache('womens_prize_fiction'))
        self.assertFalse(self._disk_path().exists())
        self.assertIsNone(wpf._archive_records_cache)
        self.assertTrue((self.cache_dir / 'hugo.json').is_file())
        self.assertTrue(pulitzer_path.is_file())
        self.assertEqual(hugo._archive_records_cache, ())

    def test_manual_refresh_makes_zero_http(self):
        archive = _complete_archive(current_year=2026)
        with patch.object(wpf, '_current_calendar_year', return_value=2026):
            _save_disk(archive, generated_at=datetime.now(_UTC))
        wpf._archive_records_cache = archive
        with patch.object(
            wpf, '_fetch_html', side_effect=AssertionError('network')
        ) as fetch, patch.object(
            wpf, 'lookup', side_effect=AssertionError('lookup')
        ):
            self.assertTrue(refresh_award_source_cache('womens_prize_fiction'))
        fetch.assert_not_called()

    def test_ram_reset_does_not_delete_disk_cache(self):
        archive = _complete_archive(current_year=2026)
        with patch.object(wpf, '_current_calendar_year', return_value=2026):
            _save_disk(archive, generated_at=datetime.now(_UTC))
            wpf._archive_records_cache = archive
            self.assertTrue(self._disk_path().is_file())
            wpf._reset_runtime_state()
            self.assertTrue(self._disk_path().is_file())
            self.assertIsNone(wpf._archive_records_cache)
            with patch.object(
                wpf, '_load_live_archive', side_effect=AssertionError('live')
            ), patch.object(
                wpf, '_fetch_html', side_effect=AssertionError('network')
            ):
                results = wpf.lookup('A Spell of Winter', 'Helen Dunmore')
        self._assert_dunmore(results)

    def test_record_payload_omits_html_query_and_qualification(self):
        payload = wpf._record_to_cache_dict(_record(1996))
        self.assertEqual(set(payload), set(wpf._RECORD_CACHE_FIELDS))
        self.assertNotIn('rank', payload)
        self.assertNotIn('html', payload)
        self.assertNotIn('qualification', payload)
        self.assertNotIn('query_title', payload)
        self.assertNotIn('shortlist', payload)
        self.assertNotIn('longlist', payload)


def _shortlist_html(year):
    from tests.test_womens_prize_fiction_parser import (
        _html_2017,
        _html_2018,
        _html_2019,
        _html_2020,
        _html_2021,
        _html_2022,
        _html_2023,
        _html_2024,
        _html_2025,
        _html_2026,
    )
    builders = {
        2017: _html_2017,
        2018: _html_2018,
        2019: _html_2019,
        2020: _html_2020,
        2021: _html_2021,
        2022: _html_2022,
        2023: _html_2023,
        2024: _html_2024,
        2025: _html_2025,
        2026: _html_2026,
    }
    return builders[year]()


def _winner_years():
    return frozenset(range(wpf.ARCHIVE_MIN_YEAR, 2027))


def _shortlist_path(cache_dir, year):
    return cache._entry_cache_path(
        cache_dir,
        wpf.SOURCE_KEY,
        wpf.SHORTLIST_ENTRY_KIND,
        str(year),
    )


class WomensPrizeFictionShortlistCacheTests(unittest.TestCase):
    def setUp(self):
        wpf._reset_runtime_state()
        cache._reset_runtime_state()
        self._temp = TemporaryDirectory()
        self.cache_dir = Path(self._temp.name)
        cache.set_cache_directory(self.cache_dir)

    def tearDown(self):
        wpf._reset_runtime_state()
        cache._reset_runtime_state()
        self._temp.cleanup()

    def _save_shortlist(self, year, records, *, generated_at=None, ttl=None, state='shortlist', url=None):
        if url is None:
            url = wpf.VERIFIED_SHORTLIST_URLS[year]
        cache.save_cache_entry(
            wpf.SOURCE_KEY,
            wpf.SHORTLIST_ENTRY_KIND,
            str(year),
            wpf.SHORTLIST_CACHE_VERSION,
            records=[wpf._record_to_cache_dict(record) for record in records],
            source_urls=[url] if url else [],
            coverage={'award_year': year, 'state': state},
            ttl_seconds=(
                wpf.HISTORICAL_SHORTLIST_CACHE_TTL_SECONDS if ttl is None else ttl
            ),
            generated_at=generated_at,
        )

    def _records(self, year):
        return wpf._parse_shortlist_article(
            _shortlist_html(year),
            year,
            wpf.VERIFIED_SHORTLIST_URLS[year],
        )

    def test_cache_identity_constants(self):
        self.assertEqual(wpf.SHORTLIST_CACHE_VERSION, 1)
        self.assertEqual(wpf.SHORTLIST_ENTRY_KIND, 'shortlists')
        self.assertEqual(wpf.SHORTLIST_MIN_YEAR, 2017)
        self.assertEqual(wpf.MAX_VERIFIED_SHORTLIST_YEAR, 2026)
        self.assertEqual(
            wpf.HISTORICAL_SHORTLIST_CACHE_TTL_SECONDS,
            180 * 24 * 60 * 60,
        )
        self.assertEqual(
            wpf.CURRENT_SHORTLIST_CACHE_REFRESH_OFFSET_SECONDS,
            11 * 60 * 60,
        )
        self.assertEqual(
            wpf.CURRENT_SHORTLIST_CACHE_TTL_SECONDS,
            7 * 24 * 60 * 60 + 11 * 60 * 60,
        )
        self.assertEqual(wpf.CACHE_REFRESH_OFFSET_SECONDS, 10 * 60 * 60)

    def test_mapped_historical_year_cold_is_one_article_get(self):
        fetched = []

        def _fetch(url):
            fetched.append(url)
            return _shortlist_html(2017)

        with patch.object(wpf, '_current_calendar_year', return_value=2026):
            with patch.object(wpf, '_fetch_html', side_effect=_fetch):
                records = wpf._get_one_shortlist_year(2017, _winner_years())
        self.assertEqual(fetched, [wpf.VERIFIED_SHORTLIST_URLS[2017]])
        self.assertEqual(len(records), 6)
        path = _shortlist_path(self.cache_dir, 2017)
        payload = json.loads(path.read_text(encoding='utf-8'))
        self.assertNotIn('<html', json.dumps(payload))
        self.assertEqual(payload['coverage']['state'], 'shortlist')
        self.assertEqual(payload['record_count'], 6)

    def test_historical_fresh_is_zero_http(self):
        records = self._records(2018)
        self._save_shortlist(2018, records, generated_at=datetime.now(_UTC))
        wpf._reset_runtime_state()
        with patch.object(
            wpf, '_fetch_html', side_effect=AssertionError('network')
        ):
            loaded = wpf._get_one_shortlist_year(2018, _winner_years())
        self.assertEqual(len(loaded), 6)

    def test_historical_stale_slot_won_refreshes_one_year(self):
        stale = self._records(2019)
        self._save_shortlist(
            2019,
            stale,
            generated_at=datetime(2020, 1, 1, tzinfo=_UTC),
            ttl=60,
        )
        fetched = []

        def _fetch(url):
            fetched.append(url)
            return _shortlist_html(2019)

        with cache.lookup_refresh_budget():
            with patch.object(wpf, '_fetch_html', side_effect=_fetch):
                loaded = wpf._get_one_shortlist_year(2019, _winner_years())
            self.assertFalse(cache.try_claim_stale_refresh())
        self.assertEqual(fetched, [wpf.VERIFIED_SHORTLIST_URLS[2019]])
        self.assertEqual(len(loaded), 6)

    def test_historical_stale_slot_denied_is_zero_http(self):
        records = self._records(2020)
        self._save_shortlist(
            2020,
            records,
            generated_at=datetime(2020, 1, 1, tzinfo=_UTC),
            ttl=60,
        )
        wpf._reset_runtime_state()
        with cache.lookup_refresh_budget():
            self.assertTrue(cache.try_claim_stale_refresh())
            with patch.object(
                wpf, '_fetch_html', side_effect=AssertionError('network')
            ):
                loaded = wpf._get_one_shortlist_year(2020, _winner_years())
        self.assertEqual(len(loaded), 6)

    def test_historical_stale_refresh_failure_keeps_stale(self):
        records = self._records(2022)
        self._save_shortlist(
            2022,
            records,
            generated_at=datetime(2020, 1, 1, tzinfo=_UTC),
            ttl=60,
        )
        original = _shortlist_path(self.cache_dir, 2022).read_text(encoding='utf-8')
        with cache.lookup_refresh_budget():
            with patch.object(
                wpf,
                '_fetch_html',
                side_effect=wpf.WomensPrizeFictionSourceError('down'),
            ):
                loaded = wpf._get_one_shortlist_year(2022, _winner_years())
        self.assertEqual(len(loaded), 6)
        self.assertEqual(
            _shortlist_path(self.cache_dir, 2022).read_text(encoding='utf-8'),
            original,
        )

    def test_malformed_historical_requires_live(self):
        records = self._records(2023)
        self._save_shortlist(2023, records, generated_at=datetime.now(_UTC))
        path = _shortlist_path(self.cache_dir, 2023)
        payload = json.loads(path.read_text(encoding='utf-8'))
        payload['records'] = payload['records'][:3]
        path.write_text(json.dumps(payload), encoding='utf-8')
        fetched = []

        def _fetch(url):
            fetched.append(url)
            return _shortlist_html(2023)

        with patch.object(wpf, '_fetch_html', side_effect=_fetch):
            loaded = wpf._get_one_shortlist_year(2023, _winner_years())
        self.assertEqual(fetched, [wpf.VERIFIED_SHORTLIST_URLS[2023]])
        self.assertEqual(len(loaded), 6)

    def test_exact_six_required_before_save(self):
        with self.assertRaises(wpf.WomensPrizeFictionSourceError):
            wpf._records_from_shortlist_pairs(
                2024,
                [('A', 'One', 'https://womensprize.com/library/a/')],
                wpf.VERIFIED_SHORTLIST_URLS[2024],
            )
        path = _shortlist_path(self.cache_dir, 2024)
        self.assertFalse(path.is_file())

    def test_year_keys_are_independent(self):
        self._save_shortlist(2017, self._records(2017), generated_at=datetime.now(_UTC))
        self._save_shortlist(2018, self._records(2018), generated_at=datetime.now(_UTC))
        self.assertTrue(_shortlist_path(self.cache_dir, 2017).is_file())
        self.assertTrue(_shortlist_path(self.cache_dir, 2018).is_file())
        _shortlist_path(self.cache_dir, 2017).unlink()
        self.assertTrue(_shortlist_path(self.cache_dir, 2018).is_file())

    def test_failed_year_does_not_erase_winners_or_sibling_year(self):
        winners = _complete_archive(current_year=2026)
        self._save_shortlist(2017, self._records(2017), generated_at=datetime.now(_UTC))
        fetched = []

        def _fetch(url):
            fetched.append(url)
            if url == wpf.VERIFIED_SHORTLIST_URLS[2018]:
                raise wpf.WomensPrizeFictionSourceError('2018 down')
            if url in wpf.VERIFIED_SHORTLIST_URLS.values():
                year = [
                    key for key, value in wpf.VERIFIED_SHORTLIST_URLS.items()
                    if value == url
                ][0]
                return _shortlist_html(year)
            raise AssertionError(url)

        with patch.object(wpf, '_current_calendar_year', return_value=2026):
            with patch.object(wpf, '_get_archive_records', return_value=winners):
                with patch.object(wpf, '_fetch_html', side_effect=_fetch):
                    dunmore = wpf.lookup('A Spell of Winter', 'Helen Dunmore')
                    stay = wpf.lookup('Stay With Me', 'Ayọ̀bámi Adébáyọ̀̀')
        self.assertEqual(len(dunmore), 1)
        self.assertEqual(dunmore[0].status, 'Winner')
        self.assertEqual(len(stay), 1)
        self.assertEqual(stay[0].status, 'Shortlisted')
        self.assertTrue(_shortlist_path(self.cache_dir, 2017).is_file())

    def test_future_discovery_uses_sitemap_then_article(self):
        url_2027 = 'https://womensprize.com/announcing-the-2027-womens-prize-for-fiction-shortlist/'
        sitemap = (
            '<urlset><url><loc>'
            f'{url_2027}'
            '</loc></url>'
            '<url><loc>https://womensprize.com/announcing-the-2027-womens-prize-for-non-fiction-shortlist/</loc></url>'
            '<url><loc>https://womensprize.com/announcing-the-2027-discoveries-shortlist/</loc></url>'
            '</urlset>'
        )
        article = (
            '<html><body>'
            '<h1 class="product_title entry-title">Announcing the 2027 '
            'Women&#8217;s Prize for Fiction shortlist!</h1>'
            '<div class="main-content"><section class="wysiwyg-layout">'
            '<p>The Women’s Prize for Fiction shortlist.</p>'
            '<ul>'
            '<li><em><a href="https://womensprize.com/library/one/">One</a></em> by A</li>'
            '<li><em><a href="https://womensprize.com/library/two/">Two</a></em> by B</li>'
            '<li><em><a href="https://womensprize.com/library/three/">Three</a></em> by C</li>'
            '<li><em><a href="https://womensprize.com/library/four/">Four</a></em> by D</li>'
            '<li><em><a href="https://womensprize.com/library/five/">Five</a></em> by E</li>'
            '<li><em><a href="https://womensprize.com/library/six/">Six</a></em> by F</li>'
            '</ul></section></div></body></html>'
        )
        fetched = []

        def _fetch(url):
            fetched.append(url)
            if url == wpf.POST_SITEMAP_URL:
                return sitemap
            if url == url_2027:
                return article
            raise AssertionError(url)

        with patch.object(wpf, '_current_calendar_year', return_value=2027):
            with patch.object(wpf, '_fetch_html', side_effect=_fetch):
                records = wpf._get_one_shortlist_year(2027, _winner_years())
        self.assertEqual(fetched, [wpf.POST_SITEMAP_URL, url_2027])
        self.assertEqual(len(records), 6)

    def test_future_discovery_falls_back_to_rest(self):
        url_2028 = 'https://womensprize.com/revealing-the-2028-womens-prize-for-fiction-shortlist/'
        article = (
            '<html><body>'
            '<h1 class="product_title entry-title">Revealing the 2028 '
            'Women’s Prize for Fiction Shortlist</h1>'
            '<div class="main-content"><section class="wysiwyg-layout">'
            '<p>The Women’s Prize for Fiction shortlist.</p>'
            '<ul>'
            '<li><em><a href="https://womensprize.com/library/one/">One</a></em> by A</li>'
            '<li><em><a href="https://womensprize.com/library/two/">Two</a></em> by B</li>'
            '<li><em><a href="https://womensprize.com/library/three/">Three</a></em> by C</li>'
            '<li><em><a href="https://womensprize.com/library/four/">Four</a></em> by D</li>'
            '<li><em><a href="https://womensprize.com/library/five/">Five</a></em> by E</li>'
            '<li><em><a href="https://womensprize.com/library/six/">Six</a></em> by F</li>'
            '</ul></section></div></body></html>'
        )
        fetched = []

        def _fetch(url):
            fetched.append(url)
            if url == wpf.POST_SITEMAP_URL:
                return '<urlset></urlset>'
            if url.startswith(wpf.REST_POSTS_SEARCH_URL):
                return json.dumps([{'link': url_2028}])
            if url == url_2028:
                return article
            raise AssertionError(url)

        with patch.object(wpf, '_current_calendar_year', return_value=2028):
            with patch.object(wpf, '_fetch_html', side_effect=_fetch):
                records = wpf._get_one_shortlist_year(
                    2028, frozenset(range(1996, 2028))
                )
        self.assertEqual(fetched[0], wpf.POST_SITEMAP_URL)
        self.assertTrue(fetched[1].startswith(wpf.REST_POSTS_SEARCH_URL))
        self.assertEqual(fetched[2], url_2028)
        self.assertEqual(len(records), 6)

    def test_ambiguous_discovery_fails_closed(self):
        sitemap = (
            '<urlset>'
            '<url><loc>https://womensprize.com/announcing-the-2027-womens-prize-for-fiction-shortlist/</loc></url>'
            '<url><loc>https://womensprize.com/revealing-the-2027-womens-prize-for-fiction-shortlist/</loc></url>'
            '</urlset>'
        )
        with patch.object(wpf, '_current_calendar_year', return_value=2027):
            with patch.object(wpf, '_fetch_html', return_value=sitemap):
                with self.assertRaises(wpf.WomensPrizeFictionSourceError):
                    wpf._discover_future_shortlist_url(2027)

    def test_current_year_absent_is_cached(self):
        fetched = []

        def _fetch(url):
            fetched.append(url)
            if url == wpf.POST_SITEMAP_URL:
                return '<urlset></urlset>'
            if url.startswith(wpf.REST_POSTS_SEARCH_URL):
                return '[]'
            raise AssertionError(url)

        winners = frozenset(range(1996, 2027))
        with patch.object(wpf, '_current_calendar_year', return_value=2027):
            with patch.object(wpf, '_fetch_html', side_effect=_fetch):
                records = wpf._get_one_shortlist_year(2027, winners)
            self.assertEqual(records, ())
            path = _shortlist_path(self.cache_dir, 2027)
            payload = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(payload['coverage']['state'], 'absent')
            self.assertEqual(payload['records'], [])
            first = list(fetched)
            wpf._reset_runtime_state()
            with patch.object(
                wpf, '_fetch_html', side_effect=AssertionError('network')
            ):
                again = wpf._get_one_shortlist_year(2027, winners)
            self.assertEqual(again, ())
            self.assertEqual(first[0], wpf.POST_SITEMAP_URL)

    def test_completed_year_cached_absent_is_invalid(self):
        cache.save_cache_entry(
            wpf.SOURCE_KEY,
            wpf.SHORTLIST_ENTRY_KIND,
            '2026',
            wpf.SHORTLIST_CACHE_VERSION,
            records=[],
            source_urls=[],
            coverage={'award_year': 2026, 'state': 'absent'},
            ttl_seconds=wpf.CURRENT_SHORTLIST_CACHE_TTL_SECONDS,
            generated_at=datetime.now(_UTC),
        )
        fetched = []

        def _fetch(url):
            fetched.append(url)
            return _shortlist_html(2026)

        with patch.object(wpf, '_fetch_html', side_effect=_fetch):
            records = wpf._get_one_shortlist_year(2026, _winner_years())
        self.assertEqual(fetched, [wpf.VERIFIED_SHORTLIST_URLS[2026]])
        self.assertEqual(len(records), 6)

    def test_current_shortlist_becomes_historical_ttl_after_winner(self):
        records = self._records(2026)
        snapshot = wpf._ShortlistYearSnapshot(
            award_year=2026,
            state='shortlist',
            source_url=wpf.VERIFIED_SHORTLIST_URLS[2026],
            records=records,
        )
        wpf._save_persistent_shortlist_year(snapshot, frozenset())
        without_winner = json.loads(
            _shortlist_path(self.cache_dir, 2026).read_text(encoding='utf-8')
        )
        self.assertEqual(
            without_winner['ttl_seconds'],
            wpf.CURRENT_SHORTLIST_CACHE_TTL_SECONDS,
        )
        wpf._save_persistent_shortlist_year(snapshot, _winner_years())
        with_winner = json.loads(
            _shortlist_path(self.cache_dir, 2026).read_text(encoding='utf-8')
        )
        self.assertEqual(
            with_winner['ttl_seconds'],
            wpf.HISTORICAL_SHORTLIST_CACHE_TTL_SECONDS,
        )

    def test_manual_refresh_clears_winner_and_shortlist_and_is_zero_http(self):
        winners = _complete_archive(current_year=2026)
        with patch.object(wpf, '_current_calendar_year', return_value=2026):
            cache.save_source_cache(
                wpf.SOURCE_KEY,
                wpf.CACHE_VERSION,
                records=[wpf._record_to_cache_dict(record) for record in winners],
                source_urls=wpf._archive_source_urls(),
                coverage=wpf._coverage_from_snapshot(
                    _snapshot(winners, current_year=2026)
                ),
                ttl_seconds=wpf.CACHE_TTL_SECONDS,
            )
        self._save_shortlist(2017, self._records(2017), generated_at=datetime.now(_UTC))
        wpf._archive_records_cache = winners
        wpf._shortlist_year_cache[2017] = self._records(2017)
        hugo._archive_records_cache = ()
        cache.save_source_cache(
            'hugo',
            1,
            records=[{'title': 'hugo', 'year': 2020}],
            source_urls=['https://example.test/hugo'],
            coverage={'source': 'hugo'},
            ttl_seconds=3600,
        )
        with patch.object(
            wpf, '_fetch_html', side_effect=AssertionError('network')
        ):
            self.assertTrue(refresh_award_source_cache('womens_prize_fiction'))
        self.assertFalse((self.cache_dir / 'womens_prize_fiction.json').exists())
        self.assertFalse(_shortlist_path(self.cache_dir, 2017).exists())
        self.assertIsNone(wpf._archive_records_cache)
        self.assertEqual(wpf._shortlist_year_cache, {})
        self.assertTrue((self.cache_dir / 'hugo.json').is_file())
        self.assertEqual(hugo._archive_records_cache, ())

    def test_cold_2026_lookup_is_twelve_gets(self):
        fetched = []

        def _fetch(url):
            fetched.append(url)
            if url == wpf.PREVIOUS_PRIZES_URL:
                return archive_html(max_year=2025)
            if url == wpf.SOURCE_HOME_URL:
                return home_html()
            for year, mapped in wpf.VERIFIED_SHORTLIST_URLS.items():
                if url == mapped:
                    return _shortlist_html(year)
            raise AssertionError(url)

        with patch.object(wpf, '_current_calendar_year', return_value=2026):
            with patch.object(wpf, '_fetch_html', side_effect=_fetch):
                results = wpf.lookup('Kingfisher', 'Rozie Kelly')
        self.assertEqual(fetched[:2], [wpf.PREVIOUS_PRIZES_URL, wpf.SOURCE_HOME_URL])
        self.assertEqual(
            fetched[2:],
            [wpf.VERIFIED_SHORTLIST_URLS[year] for year in range(2017, 2027)],
        )
        self.assertEqual(len(fetched), 12)
        self.assertNotIn(wpf.POST_SITEMAP_URL, fetched)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, 'Shortlisted')
        self.assertIsNone(results[0].rank)


if __name__ == '__main__':
    unittest.main()
