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

    def tearDown(self):
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


if __name__ == '__main__':
    unittest.main()
