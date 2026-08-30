"""Offline coverage for Deutscher Buchpreis keyed persistent cache (G2)."""

from __future__ import annotations

import hashlib
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from awards import cache
from awards.cache_control import refresh_award_source_cache
from awards.sources import booker, german_book_prize as gbp
from tests.test_german_book_prize_parser import (
    archive_index_html,
    nominiert_longlist_only_html,
    nominiert_shortlist_html,
    official_year_html,
)

_UTC = timezone.utc
_STALE_AT = datetime(2020, 1, 1, tzinfo=_UTC)
_CURRENT = 2008
_COMPLETED = (2005, 2006, 2007)


def _entry_path(cache_dir: Path, entry_kind: str, entry_key: str) -> Path:
    digest = hashlib.sha256(entry_key.encode('utf-8')).hexdigest()
    return cache_dir / gbp.SOURCE_KEY / entry_kind / f'{digest}.json'


def _pages(
    current_year=_CURRENT,
    *,
    current_archive=None,
    nominiert=None,
    fail_years=(),
):
    index_years = list(range(gbp.ARCHIVE_MIN_YEAR, current_year))
    pages = {gbp.ARCHIVE_INDEX_URL: archive_index_html(index_years)}
    for year in index_years:
        pages[gbp._canonical_year_url(year)] = official_year_html(year)
    if current_archive is None:
        pages[gbp._canonical_year_url(current_year)] = '404'
    else:
        pages[gbp._canonical_year_url(current_year)] = current_archive
    pages[gbp.CURRENT_NOMINEES_URL] = nominiert or nominiert_longlist_only_html(
        current_year
    )
    for year in fail_years:
        pages[gbp._canonical_year_url(year)] = 'FAIL'
    return pages


class _HttpTracker:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def fetch_response(self, url: str):
        self.calls.append(url)
        body = self.pages.get(url)
        if body == 'FAIL':
            raise gbp.DeutscherBuchpreisSourceError(f'HTTP failed for {url}')
        if body == '404':
            return 404, ''
        if body is None:
            year = _year_from_url(url)
            if year is not None and url == gbp._canonical_year_url(year):
                return 404, ''
            raise gbp.DeutscherBuchpreisSourceError(f'missing {url}')
        return 200, body


def _year_from_url(url: str) -> int | None:
    return gbp._year_from_official_url(url)


def _save_index(years=_COMPLETED, *, generated_at=None, ttl_seconds=None, version=None):
    cache.save_cache_entry(
        gbp.SOURCE_KEY,
        gbp.INDEX_ENTRY_KIND,
        gbp.ARCHIVE_INDEX_URL,
        gbp.CACHE_VERSION if version is None else version,
        records=[{'award_year': year} for year in years],
        source_urls=[gbp.ARCHIVE_INDEX_URL],
        coverage=gbp._index_coverage(tuple(years)),
        ttl_seconds=(
            gbp.INDEX_CACHE_TTL_SECONDS if ttl_seconds is None else ttl_seconds
        ),
        generated_at=generated_at,
    )


def _save_completed(year, records, *, generated_at=None, ttl_seconds=None, version=None):
    cache.save_cache_entry(
        gbp.SOURCE_KEY,
        gbp.YEAR_ENTRY_KIND,
        gbp._year_entry_key(year),
        gbp.CACHE_VERSION if version is None else version,
        records=[gbp._record_to_cache_dict(record) for record in records],
        source_urls=[gbp._canonical_year_url(year)],
        coverage=gbp._completed_year_coverage(year),
        ttl_seconds=(
            gbp.HISTORICAL_YEAR_CACHE_TTL_SECONDS
            if ttl_seconds is None
            else ttl_seconds
        ),
        generated_at=generated_at,
    )


def _save_current(
    snapshot,
    *,
    generated_at=None,
    ttl_seconds=None,
    version=None,
):
    cache.save_cache_entry(
        gbp.SOURCE_KEY,
        gbp.YEAR_ENTRY_KIND,
        gbp._year_entry_key(snapshot.award_year),
        gbp.CACHE_VERSION if version is None else version,
        records=[gbp._record_to_cache_dict(record) for record in snapshot.records],
        source_urls=[snapshot.source_url],
        coverage=gbp._current_year_coverage(snapshot),
        ttl_seconds=(
            gbp.CURRENT_YEAR_CACHE_TTL_SECONDS if ttl_seconds is None else ttl_seconds
        ),
        generated_at=generated_at,
    )


def _completed_records(year):
    return gbp.parse_year_page(official_year_html(year), year, completed=True)


def _empty_current_snapshot(year=_CURRENT):
    return gbp._YearSnapshot(
        award_year=year,
        records=(),
        source_kind='nominiert',
        recognized_state='longlist_only',
        source_url=gbp.CURRENT_NOMINEES_URL,
    )


def _rewrite(path: Path, mutate):
    payload = json.loads(path.read_text(encoding='utf-8'))
    mutate(payload)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + '\n',
        encoding='utf-8',
    )


class GermanBookPrizeCacheTests(unittest.TestCase):
    def setUp(self):
        gbp._reset_runtime_state()
        cache._reset_runtime_state()
        booker._reset_runtime_state()
        self._temp = TemporaryDirectory()
        self.cache_dir = Path(self._temp.name)
        cache.set_cache_directory(self.cache_dir)

    def tearDown(self):
        gbp._reset_runtime_state()
        booker._reset_runtime_state()
        cache._reset_runtime_state()
        self._temp.cleanup()

    def _lookup(self, title, author, tracker, *, current_year=_CURRENT):
        with (
            patch.object(gbp, '_current_calendar_year', return_value=current_year),
            patch.object(gbp, '_fetch_response', side_effect=tracker.fetch_response),
        ):
            return gbp.lookup(title, author)

    def _prime_complete_disk(self, *, stale_historical=False, stale_current=False, stale_index=False):
        hist_at = _STALE_AT if stale_historical else None
        cur_at = _STALE_AT if stale_current else None
        idx_at = _STALE_AT if stale_index else None
        hist_ttl = 60 if stale_historical else None
        cur_ttl = 60 if stale_current else None
        idx_ttl = 60 if stale_index else None
        _save_index(_COMPLETED, generated_at=idx_at, ttl_seconds=idx_ttl)
        for year in _COMPLETED:
            _save_completed(
                year,
                _completed_records(year),
                generated_at=hist_at,
                ttl_seconds=hist_ttl,
            )
        _save_current(
            _empty_current_snapshot(),
            generated_at=cur_at,
            ttl_seconds=cur_ttl,
        )

    def test_cache_identity_constants(self):
        self.assertEqual(gbp.SOURCE_KEY, 'german_book_prize')
        self.assertEqual(gbp.CACHE_VERSION, 1)
        self.assertEqual(gbp.INDEX_ENTRY_KIND, 'index')
        self.assertEqual(gbp.YEAR_ENTRY_KIND, 'years')
        self.assertEqual(gbp.INDEX_CACHE_TTL_SECONDS, 630000)
        self.assertEqual(gbp.HISTORICAL_YEAR_CACHE_TTL_SECONDS, 15552000)
        self.assertEqual(gbp.CURRENT_YEAR_CACHE_TTL_SECONDS, 630000)
        self.assertEqual(gbp.CURRENT_YEAR_CACHE_REFRESH_OFFSET_SECONDS, 7 * 60 * 60)
        self.assertEqual(gbp._year_entry_key(2005), '2005')
        self.assertEqual(gbp._year_entry_key(2026), '2026')

    def test_cold_index_year_and_current_writes_keyed_entries(self):
        tracker = _HttpTracker(_pages())
        results = self._lookup('Es geht uns gut', 'Arno Geiger', tracker)
        self.assertEqual(len(results), 1)
        self.assertTrue(
            _entry_path(self.cache_dir, gbp.INDEX_ENTRY_KIND, gbp.ARCHIVE_INDEX_URL).is_file()
        )
        for year in _COMPLETED:
            self.assertTrue(
                _entry_path(self.cache_dir, gbp.YEAR_ENTRY_KIND, gbp._year_entry_key(year)).is_file()
            )
        self.assertTrue(
            _entry_path(
                self.cache_dir, gbp.YEAR_ENTRY_KIND, gbp._year_entry_key(_CURRENT)
            ).is_file()
        )
        current_payload = cache.load_cache_entry(
            gbp.SOURCE_KEY,
            gbp.YEAR_ENTRY_KIND,
            gbp._year_entry_key(_CURRENT),
            gbp.CACHE_VERSION,
        )
        self.assertEqual(current_payload['coverage']['recognized_state'], 'longlist_only')
        self.assertEqual(current_payload['coverage']['source_kind'], 'nominiert')
        self.assertEqual(current_payload['records'], [])

    def test_fresh_disk_full_replay_is_zero_http(self):
        self._prime_complete_disk()
        tracker = _HttpTracker(_pages())
        results = self._lookup('Es geht uns gut', 'Arno Geiger', tracker)
        self.assertEqual(len(results), 1)
        self.assertEqual(tracker.calls, [])

    def test_ram_reset_then_fresh_disk_is_zero_http(self):
        self._prime_complete_disk()
        tracker = _HttpTracker(_pages())
        self._lookup('Es geht uns gut', 'Arno Geiger', tracker)
        self.assertEqual(tracker.calls, [])
        gbp._reset_runtime_state()
        tracker2 = _HttpTracker(_pages())
        results = self._lookup('Es geht uns gut', 'Arno Geiger', tracker2)
        self.assertEqual(len(results), 1)
        self.assertEqual(tracker2.calls, [])

    def test_historical_stale_valid_used_without_http_or_refresh_slot(self):
        self._prime_complete_disk(stale_historical=True)
        claims = {'n': 0}
        real_claim = cache.try_claim_stale_refresh

        def wrapped_claim():
            claims['n'] += 1
            return real_claim()

        tracker = _HttpTracker(_pages())
        with cache.lookup_refresh_budget():
            with patch.object(cache, 'try_claim_stale_refresh', side_effect=wrapped_claim):
                results = self._lookup('Es geht uns gut', 'Arno Geiger', tracker)
            self.assertTrue(cache.try_claim_stale_refresh())
        self.assertEqual(len(results), 1)
        self.assertEqual(tracker.calls, [])
        self.assertEqual(claims['n'], 0)

    def test_current_fresh_is_zero_http_and_does_not_claim_slot(self):
        self._prime_complete_disk()
        claims = {'n': 0}
        real_claim = cache.try_claim_stale_refresh

        def wrapped_claim():
            claims['n'] += 1
            return real_claim()

        tracker = _HttpTracker(_pages())
        with cache.lookup_refresh_budget():
            with patch.object(cache, 'try_claim_stale_refresh', side_effect=wrapped_claim):
                self._lookup('Es geht uns gut', 'Arno Geiger', tracker)
            self.assertTrue(cache.try_claim_stale_refresh())
        self.assertEqual(tracker.calls, [])
        self.assertEqual(claims['n'], 0)

    def test_current_stale_slot_success_replaces_entry(self):
        self._prime_complete_disk(stale_current=True)
        shortlist = (
            ('Synthetic Short A', 'Synthetic Author A', 'book-1', 'Autorin'),
            ('Synthetic Short B', 'Synthetic Author B', 'book-2'),
            ('Synthetic Short C', 'Synthetic Author C', 'book-3'),
        )
        pages = _pages(nominiert=nominiert_shortlist_html(_CURRENT, shortlist))
        path = _entry_path(
            self.cache_dir, gbp.YEAR_ENTRY_KIND, gbp._year_entry_key(_CURRENT)
        )
        before = path.read_text(encoding='utf-8')
        tracker = _HttpTracker(pages)
        with cache.lookup_refresh_budget():
            results = self._lookup('Synthetic Short A', 'Synthetic Author A', tracker)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, 'Shortlisted')
        self.assertTrue(any(gbp.CURRENT_NOMINEES_URL in url for url in tracker.calls))
        after = cache.load_cache_entry(
            gbp.SOURCE_KEY,
            gbp.YEAR_ENTRY_KIND,
            gbp._year_entry_key(_CURRENT),
            gbp.CACHE_VERSION,
        )
        self.assertEqual(after['coverage']['recognized_state'], 'shortlist')
        self.assertNotEqual(before, path.read_text(encoding='utf-8'))

    def test_current_stale_slot_failure_uses_stale_and_leaves_file(self):
        self._prime_complete_disk(stale_current=True)
        path = _entry_path(
            self.cache_dir, gbp.YEAR_ENTRY_KIND, gbp._year_entry_key(_CURRENT)
        )
        before = path.read_text(encoding='utf-8')
        mtime = path.stat().st_mtime
        pages = _pages()
        pages[gbp.CURRENT_NOMINEES_URL] = 'FAIL'
        tracker = _HttpTracker(pages)
        with cache.lookup_refresh_budget():
            results = self._lookup('Es geht uns gut', 'Arno Geiger', tracker)
        self.assertEqual(len(results), 1)
        self.assertEqual(path.read_text(encoding='utf-8'), before)
        self.assertEqual(path.stat().st_mtime, mtime)

    def test_current_stale_without_slot_is_zero_http(self):
        self._prime_complete_disk(stale_current=True)
        tracker = _HttpTracker(_pages())
        with cache.lookup_refresh_budget():
            self.assertTrue(cache.try_claim_stale_refresh())
            results = self._lookup('Es geht uns gut', 'Arno Geiger', tracker)
        self.assertEqual(len(results), 1)
        self.assertEqual(tracker.calls, [])

    def test_missing_historical_year_is_required_live(self):
        _save_index()
        _save_completed(2005, _completed_records(2005))
        _save_completed(2006, _completed_records(2006))
        _save_current(_empty_current_snapshot())
        tracker = _HttpTracker(_pages())
        results = self._lookup('Stub Winner 2007', 'Stub Winner Author 2007', tracker)
        self.assertEqual(len(results), 1)
        self.assertIn(gbp._canonical_year_url(2007), tracker.calls)
        self.assertNotIn(gbp._canonical_year_url(2005), tracker.calls)

    def test_missing_current_is_required_live(self):
        _save_index()
        for year in _COMPLETED:
            _save_completed(year, _completed_records(year))
        tracker = _HttpTracker(_pages())
        self._lookup('Es geht uns gut', 'Arno Geiger', tracker)
        self.assertTrue(
            any(
                url in {gbp._canonical_year_url(_CURRENT), gbp.CURRENT_NOMINEES_URL}
                for url in tracker.calls
            )
        )

    def test_stale_index_with_complete_coverage_is_zero_http(self):
        self._prime_complete_disk(stale_index=True)
        tracker = _HttpTracker(_pages())
        results = self._lookup('Es geht uns gut', 'Arno Geiger', tracker)
        self.assertEqual(len(results), 1)
        self.assertEqual(tracker.calls, [])
        self.assertNotIn(gbp.ARCHIVE_INDEX_URL, tracker.calls)

    def test_index_missing_previous_completed_year_after_rollover_is_required_live(self):
        _save_index((2005, 2006))
        for year in (2005, 2006):
            _save_completed(year, _completed_records(year))
        _save_current(_empty_current_snapshot())
        tracker = _HttpTracker(_pages())
        results = self._lookup('Es geht uns gut', 'Arno Geiger', tracker)
        self.assertEqual(len(results), 1)
        self.assertIn(gbp.ARCHIVE_INDEX_URL, tracker.calls)

    def test_valid_empty_current_longlist_only_round_trips(self):
        self._prime_complete_disk()
        gbp._reset_runtime_state()
        payload = cache.load_cache_entry(
            gbp.SOURCE_KEY,
            gbp.YEAR_ENTRY_KIND,
            gbp._year_entry_key(_CURRENT),
            gbp.CACHE_VERSION,
        )
        restored = gbp._current_year_from_payload(payload, _CURRENT)
        self.assertEqual(restored, ())
        self.assertEqual(payload['coverage']['recognized_state'], 'longlist_only')
        tracker = _HttpTracker(_pages())
        self.assertEqual(
            self._lookup('Die Lücken', 'Shida Bazyar', tracker),
            [],
        )
        self.assertEqual(tracker.calls, [])

    def test_malformed_empty_current_coverage_is_rejected(self):
        _save_current(_empty_current_snapshot())
        path = _entry_path(
            self.cache_dir, gbp.YEAR_ENTRY_KIND, gbp._year_entry_key(_CURRENT)
        )

        def drop_state(payload):
            coverage = dict(payload['coverage'])
            del coverage['recognized_state']
            payload['coverage'] = coverage

        _rewrite(path, drop_state)
        self.assertIsNone(gbp._load_persistent_current_year(_CURRENT))

    def test_malformed_historical_coverage_is_rejected(self):
        _save_completed(2005, _completed_records(2005))
        path = _entry_path(
            self.cache_dir, gbp.YEAR_ENTRY_KIND, gbp._year_entry_key(2005)
        )

        def extra_field(payload):
            coverage = dict(payload['coverage'])
            coverage['extra'] = True
            payload['coverage'] = coverage

        _rewrite(path, extra_field)
        self.assertIsNone(gbp._load_persistent_completed_year(2005))

    def test_source_url_year_mismatch_is_rejected(self):
        records = _completed_records(2005)
        _save_completed(2005, records)
        path = _entry_path(
            self.cache_dir, gbp.YEAR_ENTRY_KIND, gbp._year_entry_key(2005)
        )

        def wrong_url(payload):
            payload['source_urls'] = [gbp._canonical_year_url(2006)]
            payload['records'][0]['source_url'] = gbp._canonical_year_url(2006)

        _rewrite(path, wrong_url)
        self.assertIsNone(gbp._load_persistent_completed_year(2005))

    def test_cache_version_mismatch_requires_live(self):
        _save_index(version=99)
        for year in _COMPLETED:
            _save_completed(year, _completed_records(year), version=99)
        _save_current(_empty_current_snapshot(), version=99)
        tracker = _HttpTracker(_pages())
        self._lookup('Es geht uns gut', 'Arno Geiger', tracker)
        self.assertIn(gbp.ARCHIVE_INDEX_URL, tracker.calls)

    def test_save_failure_does_not_fail_lookup(self):
        tracker = _HttpTracker(_pages())
        with patch.object(cache, 'save_cache_entry', side_effect=OSError('disk full')):
            results = self._lookup('Es geht uns gut', 'Arno Geiger', tracker)
        self.assertEqual(len(results), 1)

    def test_partial_cold_build_recovery_reuses_persisted_years(self):
        pages = _pages(fail_years=(2007,))
        tracker = _HttpTracker(pages)
        with self.assertRaises(gbp.DeutscherBuchpreisSourceError):
            self._lookup('Es geht uns gut', 'Arno Geiger', tracker)
        self.assertTrue(
            _entry_path(self.cache_dir, gbp.YEAR_ENTRY_KIND, gbp._year_entry_key(2005)).is_file()
        )
        self.assertTrue(
            _entry_path(self.cache_dir, gbp.YEAR_ENTRY_KIND, gbp._year_entry_key(2006)).is_file()
        )
        self.assertFalse(
            _entry_path(self.cache_dir, gbp.YEAR_ENTRY_KIND, gbp._year_entry_key(2007)).exists()
        )
        gbp._reset_runtime_state()
        pages_ok = _pages()
        tracker2 = _HttpTracker(pages_ok)
        results = self._lookup('Es geht uns gut', 'Arno Geiger', tracker2)
        self.assertEqual(len(results), 1)
        self.assertIn(gbp._canonical_year_url(2007), tracker2.calls)
        self.assertNotIn(gbp._canonical_year_url(2005), tracker2.calls)
        self.assertNotIn(gbp._canonical_year_url(2006), tracker2.calls)

    def test_reset_runtime_state_clears_ram_only(self):
        self._prime_complete_disk()
        tracker = _HttpTracker(_pages())
        self._lookup('Es geht uns gut', 'Arno Geiger', tracker)
        self.assertIsNotNone(gbp._archive_records_cache)
        self.assertIsNotNone(gbp._index_years_cache)
        self.assertTrue(gbp._year_records_cache)
        path = _entry_path(
            self.cache_dir, gbp.YEAR_ENTRY_KIND, gbp._year_entry_key(2005)
        )
        self.assertTrue(path.is_file())
        gbp._reset_runtime_state()
        self.assertIsNone(gbp._archive_records_cache)
        self.assertIsNone(gbp._index_years_cache)
        self.assertEqual(gbp._year_records_cache, {})
        self.assertTrue(path.is_file())

    def test_manual_refresh_clears_keyed_entries_and_ram_without_http(self):
        self._prime_complete_disk()
        self._lookup('Es geht uns gut', 'Arno Geiger', _HttpTracker(_pages()))
        cache.save_source_cache(
            booker.SOURCE_KEY,
            1,
            records=[{'title': 'keep'}],
            source_urls=['https://example.test/booker'],
            coverage={'source': 'booker'},
            ttl_seconds=3600,
        )
        with (
            patch('urllib.request.urlopen') as urlopen,
            patch.object(gbp, 'lookup') as gbp_lookup,
        ):
            self.assertTrue(refresh_award_source_cache('german_book_prize'))
        urlopen.assert_not_called()
        gbp_lookup.assert_not_called()
        self.assertFalse(
            _entry_path(self.cache_dir, gbp.INDEX_ENTRY_KIND, gbp.ARCHIVE_INDEX_URL).exists()
        )
        self.assertFalse(
            _entry_path(
                self.cache_dir, gbp.YEAR_ENTRY_KIND, gbp._year_entry_key(2005)
            ).exists()
        )
        self.assertIsNone(gbp._archive_records_cache)
        self.assertEqual(gbp._year_records_cache, {})
        self.assertTrue((self.cache_dir / 'booker.json').is_file())

    def test_nominiert_to_archive_replaces_same_logical_year_entry(self):
        self._prime_complete_disk(stale_current=True)
        current_key = gbp._year_entry_key(_CURRENT)
        before_files = list((self.cache_dir / gbp.SOURCE_KEY / gbp.YEAR_ENTRY_KIND).glob('*.json'))
        pages = _pages(current_archive=official_year_html(_CURRENT))
        tracker = _HttpTracker(pages)
        with cache.lookup_refresh_budget():
            results = self._lookup(
                'Stub Winner 2008',
                'Stub Winner Author 2008',
                tracker,
            )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, 'Winner')
        self.assertEqual(results[0].source_url, gbp._canonical_year_url(_CURRENT))
        after = cache.load_cache_entry(
            gbp.SOURCE_KEY,
            gbp.YEAR_ENTRY_KIND,
            current_key,
            gbp.CACHE_VERSION,
        )
        self.assertEqual(after['coverage']['source_kind'], 'archive')
        self.assertEqual(after['coverage']['recognized_state'], 'winner')
        after_files = list((self.cache_dir / gbp.SOURCE_KEY / gbp.YEAR_ENTRY_KIND).glob('*.json'))
        self.assertEqual(len(after_files), len(before_files))

    def test_year_becomes_historical_rejects_nominiert_snapshot(self):
        _save_index((2005, 2006))
        _save_completed(2005, _completed_records(2005))
        _save_current(
            gbp._YearSnapshot(
                award_year=2006,
                records=(),
                source_kind='nominiert',
                recognized_state='longlist_only',
                source_url=gbp.CURRENT_NOMINEES_URL,
            )
        )
        self.assertIsNone(gbp._load_persistent_completed_year(2006))
        tracker = _HttpTracker(_pages(current_year=2007))
        results = self._lookup(
            'Stub Winner 2006',
            'Stub Winner Author 2006',
            tracker,
            current_year=2007,
        )
        self.assertEqual(len(results), 1)
        self.assertIn(gbp._canonical_year_url(2006), tracker.calls)
        persisted = cache.load_cache_entry(
            gbp.SOURCE_KEY,
            gbp.YEAR_ENTRY_KIND,
            gbp._year_entry_key(2006),
            gbp.CACHE_VERSION,
        )
        self.assertEqual(persisted['coverage']['kind'], 'completed_year')
        self.assertEqual(persisted['coverage']['source_kind'], 'archive')
        self.assertEqual(persisted['source_urls'], [gbp._canonical_year_url(2006)])

    def test_year_cache_not_in_index_is_not_used_as_coverage(self):
        _save_index((2005, 2006))
        for year in (2005, 2006, 2007):
            _save_completed(year, _completed_records(year))
        _save_current(_empty_current_snapshot())
        tracker = _HttpTracker(_pages())
        self._lookup('Es geht uns gut', 'Arno Geiger', tracker)
        self.assertIn(gbp.ARCHIVE_INDEX_URL, tracker.calls)


if __name__ == '__main__':
    unittest.main()
