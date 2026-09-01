"""Offline coverage for IPAF keyed index and year cache."""

from __future__ import annotations

import hashlib
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from awards import cache
from awards.cache_control import refresh_award_source_cache
from awards.sources import hugo, ipaf as src
from tests.test_ipaf_parser import (
    SHORTLIST_2020,
    SHORTLIST_2026,
    WINNERS,
    _completed_year_html,
    _empty_shell,
    _index_page,
    _index_url,
    _profile_page,
    _profile_url,
    _year_2020_html,
    _year_page,
    _year_url,
)

_UTC = timezone.utc
_STALE_AT = datetime(2020, 1, 1, tzinfo=_UTC)


def _entry_path(cache_dir: Path, entry_kind: str, entry_key: str) -> Path:
    digest = hashlib.sha256(entry_key.encode('utf-8')).hexdigest()
    return cache_dir / src.SOURCE_KEY / entry_kind / f'{digest}.json'


class _HttpTracker:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def fetch_response(self, url: str):
        self.calls.append(url)
        body = self.pages.get(url)
        if body == 'FAIL':
            raise src.IpafSourceError(f'HTTP failed for {url}')
        if body is None:
            raise src.IpafSourceError(f'missing {url}')
        if isinstance(body, tuple):
            return body
        return 200, body, url


def _save_index(years, *, generated_at=None, ttl_seconds=None, version=None):
    cache.save_cache_entry(
        src.SOURCE_KEY,
        src.INDEX_ENTRY_KIND,
        src.INDEX_ENTRY_KEY,
        src.INDEX_CACHE_VERSION if version is None else version,
        records=[],
        source_urls=[src.PRIZE_YEARS_INDEX_URL],
        coverage=src._index_coverage(tuple(years)),
        ttl_seconds=(
            src.CURRENT_CACHE_TTL_SECONDS if ttl_seconds is None else ttl_seconds
        ),
        generated_at=generated_at,
    )


def _save_year(snapshot, *, generated_at=None, ttl_seconds=None, version=None):
    cache.save_cache_entry(
        src.SOURCE_KEY,
        src.YEAR_ENTRY_KIND,
        src._year_entry_key(snapshot.award_year),
        src.YEAR_CACHE_VERSION if version is None else version,
        records=[src._record_to_cache_dict(record) for record in snapshot.records],
        source_urls=list(snapshot.source_urls),
        coverage=src._year_coverage(snapshot.award_year, snapshot.state),
        ttl_seconds=(
            src._year_ttl_seconds(snapshot.state)
            if ttl_seconds is None
            else ttl_seconds
        ),
        generated_at=generated_at,
    )


def _completed_pages():
    pages = {_index_url(): _index_page(list(range(2020, 2027)))}
    pages[_year_url(2020)] = _year_2020_html()
    pages[_profile_url()] = _profile_page()
    for year in range(2021, 2027):
        pages[_year_url(year)] = _completed_year_html(year)
    return pages


def _year_snapshot_from_html(year: int):
    html = _year_2020_html() if year == 2020 else _completed_year_html(year)
    parsed = src._parse_year_page(html, year, _year_url(year))
    records = list(parsed.shortlisted)
    urls = [_year_url(year)]
    if year == 2020:
        winner = src._parse_winner_profile(_profile_page(), 2020, _profile_url())
        records.append(winner)
        urls.append(_profile_url())
    elif parsed.winner is not None:
        records.append(parsed.winner)
    merged = src._dedupe_records(records)
    state = src._classify_year_state(merged)
    src._validate_year_records(merged, year, state)
    return src._YearSnapshot(
        award_year=year,
        state=state,
        source_urls=tuple(urls),
        records=merged,
    )


def _seed_completed_disk() -> None:
    _save_index(list(range(2020, 2027)))
    for year in range(2020, 2027):
        _save_year(_year_snapshot_from_html(year))


class IpafCacheTests(unittest.TestCase):
    def setUp(self):
        self._temp = TemporaryDirectory()
        self.cache_dir = Path(self._temp.name)
        cache.set_cache_directory(self.cache_dir)
        src._reset_runtime_state()
        hugo._reset_runtime_state()

    def tearDown(self):
        src._reset_runtime_state()
        hugo._reset_runtime_state()
        cache.set_cache_directory(None)
        self._temp.cleanup()

    def _lookup(self, pages, title, author, utc_year=2026):
        tracker = _HttpTracker(pages)
        with patch.object(src, '_fetch_response', tracker.fetch_response), patch.object(
            src, '_current_calendar_year', return_value=utc_year
        ):
            results = src.lookup(title, author)
        return results, tracker

    def test_cold_fill_is_nine_gets(self):
        results, tracker = self._lookup(
            _completed_pages(),
            'Swimming Against the Tide',
            'Said Khatibi',
        )
        self.assertEqual(len(tracker.calls), 9)
        self.assertEqual(tracker.calls[0], _index_url())
        self.assertIn(_year_url(2020), tracker.calls)
        self.assertIn(_profile_url(), tracker.calls)
        for year in range(2021, 2027):
            self.assertIn(_year_url(year), tracker.calls)
        self.assertEqual(results[0].status, 'Winner')
        self.assertEqual(results[0].award_year, 2026)
        payload = cache.load_cache_entry(
            src.SOURCE_KEY,
            src.YEAR_ENTRY_KIND,
            '2026',
            src.YEAR_CACHE_VERSION,
        )
        self.assertNotIn('html', payload)
        self.assertTrue(all('html' not in item for item in payload['records']))
        self.assertNotIn('rsc', str(payload).casefold())
        titles = [item['work_title'] for item in payload['records']]
        self.assertNotIn("Grandma Touma's Cord", titles)

    def test_fresh_is_zero_http(self):
        _seed_completed_disk()
        results, tracker = self._lookup(
            {}, 'The Spartan Court', 'Abdelouahab Aissaoui'
        )
        self.assertEqual(tracker.calls, [])
        self.assertEqual(results[0].status, 'Winner')
        self.assertEqual(results[0].award_year, 2020)

    def test_ram_reset_fresh_disk_is_zero_http(self):
        _seed_completed_disk()
        src._reset_runtime_state()
        results, tracker = self._lookup(
            {}, "Bread on Uncle Milad's Table", 'Mohamed Alnaas'
        )
        self.assertEqual(tracker.calls, [])
        self.assertEqual(results[0].award_year, 2022)

    def test_completed_year_ttl_is_180_days(self):
        self.assertEqual(src.HISTORICAL_CACHE_TTL_SECONDS, 180 * 24 * 60 * 60)
        self.assertEqual(src._year_ttl_seconds('winner'), src.HISTORICAL_CACHE_TTL_SECONDS)

    def test_index_and_shortlisted_ttl_is_7_days_plus_15h(self):
        self.assertEqual(src.CURRENT_CACHE_REFRESH_OFFSET_SECONDS, 15 * 60 * 60)
        self.assertEqual(
            src.CURRENT_CACHE_TTL_SECONDS,
            7 * 24 * 60 * 60 + 15 * 60 * 60,
        )
        self.assertEqual(src._year_ttl_seconds('shortlisted'), src.CURRENT_CACHE_TTL_SECONDS)
        self.assertEqual(src._year_ttl_seconds('absent'), src.CURRENT_CACHE_TTL_SECONDS)

    def test_stale_year_slot_won_refreshes_only_that_year(self):
        _seed_completed_disk()
        _save_year(
            _year_snapshot_from_html(2026),
            generated_at=_STALE_AT,
            ttl_seconds=60,
        )
        pages = _completed_pages()
        with cache.lookup_refresh_budget():
            results, tracker = self._lookup(
                pages, 'Swimming Against the Tide', 'Said Khatibi'
            )
        self.assertEqual(results[0].status, 'Winner')
        self.assertEqual(tracker.calls, [_year_url(2026)])

    def test_stale_index_slot_won_refreshes_only_index(self):
        _seed_completed_disk()
        _save_index(
            list(range(2020, 2027)),
            generated_at=_STALE_AT,
            ttl_seconds=60,
        )
        pages = _completed_pages()
        with cache.lookup_refresh_budget():
            _results, tracker = self._lookup(
                pages, 'The Prayer of Anxiety', 'Mohamed Samir Nada'
            )
        self.assertEqual(tracker.calls, [_index_url()])

    def test_slot_denied_uses_stale_zero_http(self):
        _seed_completed_disk()
        _save_year(
            _year_snapshot_from_html(2025),
            generated_at=_STALE_AT,
            ttl_seconds=60,
        )
        with cache.lookup_refresh_budget():
            self.assertTrue(cache.try_claim_stale_refresh())
            results, tracker = self._lookup(
                {_year_url(2025): 'FAIL'},
                'The Prayer of Anxiety',
                'Mohamed Samir Nada',
            )
        self.assertEqual(tracker.calls, [])
        self.assertEqual(results[0].award_year, 2025)

    def test_stale_refresh_failure_preserves_stale(self):
        _seed_completed_disk()
        snapshot = _year_snapshot_from_html(2024)
        _save_year(snapshot, generated_at=_STALE_AT, ttl_seconds=60)
        pages = _completed_pages()
        pages[_year_url(2024)] = 'FAIL'
        with cache.lookup_refresh_budget():
            results, tracker = self._lookup(
                pages, 'A Mask, the Colour of the Sky', 'Basim Khandaqji'
            )
        self.assertEqual(tracker.calls, [_year_url(2024)])
        self.assertEqual(results[0].status, 'Winner')
        payload = cache.load_cache_entry(
            src.SOURCE_KEY, src.YEAR_ENTRY_KIND, '2024', src.YEAR_CACHE_VERSION
        )
        self.assertEqual(payload['generated_at'], _STALE_AT.isoformat().replace('+00:00', 'Z'))

    def test_malformed_version_mismatch_is_required_live(self):
        _seed_completed_disk()
        _save_year(_year_snapshot_from_html(2026), version=99)
        results, tracker = self._lookup(
            _completed_pages(),
            'Swimming Against the Tide',
            'Said Khatibi',
        )
        self.assertIn(_year_url(2026), tracker.calls)
        self.assertEqual(results[0].status, 'Winner')

    def test_one_broken_year_does_not_invalidate_siblings(self):
        pages = _completed_pages()
        pages[_year_url(2023)] = 'FAIL'
        results, tracker = self._lookup(
            pages, 'Notebooks of the Bookseller', 'Jalal Barjas'
        )
        self.assertTrue(results)
        self.assertEqual(results[0].award_year, 2021)
        sibling = cache.load_cache_entry(
            src.SOURCE_KEY, src.YEAR_ENTRY_KIND, '2021', src.YEAR_CACHE_VERSION
        )
        self.assertIsNotNone(sibling)
        self.assertIsNone(
            cache.load_cache_entry(
                src.SOURCE_KEY, src.YEAR_ENTRY_KIND, '2023', src.YEAR_CACHE_VERSION
            )
        )

    def test_2020_profile_failure_shortlisted_short_ttl(self):
        pages = _completed_pages()
        pages[_profile_url()] = 'FAIL'
        results, tracker = self._lookup(
            pages, 'Firewood of Sarajevo', 'Said Khatibi'
        )
        self.assertEqual(results[0].status, 'Shortlisted')
        self.assertEqual(results[0].award_year, 2020)
        payload = cache.load_cache_entry(
            src.SOURCE_KEY, src.YEAR_ENTRY_KIND, '2020', src.YEAR_CACHE_VERSION
        )
        self.assertEqual(payload['coverage']['state'], 'shortlisted')
        self.assertEqual(payload['ttl_seconds'], src.CURRENT_CACHE_TTL_SECONDS)
        self.assertIn(_profile_url(), tracker.calls)

    def test_later_2020_profile_success_becomes_winner_180d(self):
        pages = _completed_pages()
        pages[_profile_url()] = 'FAIL'
        self._lookup(pages, 'Firewood of Sarajevo', 'Said Khatibi')
        src._reset_runtime_state()
        pages[_profile_url()] = _profile_page()
        _save_year(
            src._YearSnapshot(
                award_year=2020,
                state='shortlisted',
                source_urls=(_year_url(2020),),
                records=src._parse_year_page(
                    _year_2020_html(), 2020, _year_url(2020)
                ).shortlisted,
            ),
            generated_at=_STALE_AT,
            ttl_seconds=60,
        )
        with cache.lookup_refresh_budget():
            results, tracker = self._lookup(
                pages, 'The Spartan Court', 'Abdelouahab Aissaoui'
            )
        self.assertEqual(results[0].status, 'Winner')
        payload = cache.load_cache_entry(
            src.SOURCE_KEY, src.YEAR_ENTRY_KIND, '2020', src.YEAR_CACHE_VERSION
        )
        self.assertEqual(payload['coverage']['state'], 'winner')
        self.assertEqual(payload['ttl_seconds'], src.HISTORICAL_CACHE_TTL_SECONDS)
        self.assertIn(_profile_url(), tracker.calls)

    def test_no_longlist_or_raw_html_or_arabic_persisted(self):
        self._lookup(_completed_pages(), 'The Seer', 'Diaa Jubaili')
        for year in range(2020, 2027):
            payload = cache.load_cache_entry(
                src.SOURCE_KEY,
                src.YEAR_ENTRY_KIND,
                str(year),
                src.YEAR_CACHE_VERSION,
            )
            blob = str(payload)
            self.assertNotIn('html', payload)
            self.assertNotIn('<div', blob)
            self.assertNotIn('Grandma Touma', blob)
            self.assertNotIn('ar.arabicfiction.org', blob)
            self.assertNotIn('__next_f', blob)
            statuses = {item['status'] for item in payload['records']}
            self.assertTrue(statuses <= {'Winner', 'Shortlisted'})

    def test_manual_refresh_clears_index_years_and_ram_zero_http(self):
        _seed_completed_disk()
        src._store_index_snapshot(
            src._IndexSnapshot(supported_years=(2020,), source_url=_index_url())
        )
        src._store_year_snapshot(_year_snapshot_from_html(2026))
        cache.save_source_cache(
            'hugo',
            1,
            records=[{'title': 'sibling'}],
            source_urls=['https://example.test/h'],
            coverage={'source': 'hugo'},
            ttl_seconds=3600,
        )
        self.assertTrue(refresh_award_source_cache('ipaf'))
        self.assertIsNone(src._ram_index())
        self.assertIsNone(src._ram_year(2026))
        self.assertIsNone(
            cache.load_cache_entry(
                src.SOURCE_KEY, src.INDEX_ENTRY_KIND, src.INDEX_ENTRY_KEY, 1
            )
        )
        self.assertIsNone(
            cache.load_cache_entry(src.SOURCE_KEY, src.YEAR_ENTRY_KIND, '2026', 1)
        )
        self.assertIsNotNone(cache.load_source_cache('hugo', 1))

    def test_predictable_future_url_without_index_is_not_fetched(self):
        pages = _completed_pages()
        pages[_year_url(2027)] = _year_page(
            2027,
            winner=None,
            shortlist=SHORTLIST_2026,
        )
        _results, tracker = self._lookup(
            pages, 'The Origin of Species', 'Ahmad Abdulatif', utc_year=2027
        )
        self.assertNotIn(_year_url(2027), tracker.calls)

    def test_future_shortlist_only_is_short_ttl(self):
        pages = _completed_pages()
        pages[_index_url()] = _index_page(list(range(2020, 2028)))
        six = list(SHORTLIST_2026) + [('Future Sixth', 'Future Author')]
        pages[_year_url(2027)] = _year_page(
            2027, winner=None, shortlist=six
        )
        results, tracker = self._lookup(
            pages, 'Future Sixth', 'Future Author', utc_year=2027
        )
        self.assertIn(_year_url(2027), tracker.calls)
        self.assertEqual(results[0].status, 'Shortlisted')
        payload = cache.load_cache_entry(
            src.SOURCE_KEY, src.YEAR_ENTRY_KIND, '2027', src.YEAR_CACHE_VERSION
        )
        self.assertEqual(payload['coverage']['state'], 'shortlisted')
        self.assertEqual(payload['ttl_seconds'], src.CURRENT_CACHE_TTL_SECONDS)

    def test_future_winner_merges_and_completes(self):
        pages = _completed_pages()
        pages[_index_url()] = _index_page(list(range(2020, 2028)))
        six = list(SHORTLIST_2026) + [
            ('Swimming Against the Tide', 'Said Khatibi')
        ]
        pages[_year_url(2027)] = _year_page(
            2027,
            winner=('Swimming Against the Tide', 'Said Khatibi'),
            shortlist=six,
        )
        results, _tracker = self._lookup(
            pages, 'Swimming Against the Tide', 'Said Khatibi', utc_year=2027
        )
        years = {item.award_year for item in results}
        self.assertIn(2026, years)
        self.assertIn(2027, years)
        match_2027 = [item for item in results if item.award_year == 2027]
        self.assertEqual(len(match_2027), 1)
        self.assertEqual(match_2027[0].status, 'Winner')
        payload = cache.load_cache_entry(
            src.SOURCE_KEY, src.YEAR_ENTRY_KIND, '2027', src.YEAR_CACHE_VERSION
        )
        self.assertEqual(payload['coverage']['state'], 'winner')
        self.assertEqual(payload['ttl_seconds'], src.HISTORICAL_CACHE_TTL_SECONDS)
        statuses = [
            (item['work_title'], item['status']) for item in payload['records']
        ]
        self.assertEqual(
            [status for title, status in statuses if title == 'Swimming Against the Tide'],
            ['Winner'],
        )

    def test_future_soft_200_is_not_cached_absent(self):
        pages = _completed_pages()
        pages[_index_url()] = _index_page(list(range(2020, 2028)))
        pages[_year_url(2027)] = _empty_shell()
        _results, tracker = self._lookup(
            pages, 'Swimming Against the Tide', 'Said Khatibi', utc_year=2027
        )
        self.assertIn(_year_url(2027), tracker.calls)
        self.assertIsNone(
            cache.load_cache_entry(
                src.SOURCE_KEY, src.YEAR_ENTRY_KIND, '2027', src.YEAR_CACHE_VERSION
            )
        )

    def test_longlist_only_2026_does_not_match(self):
        _seed_completed_disk()
        results, tracker = self._lookup(
            {}, "Grandma Touma's Cord", 'Abdelouahab Aissaoui'
        )
        self.assertEqual(results, [])
        self.assertEqual(tracker.calls, [])
        winner, _tracker = self._lookup(
            {}, 'The Spartan Court', 'Abdelouahab Aissaoui'
        )
        self.assertEqual(winner[0].award_year, 2020)
        self.assertEqual(winner[0].status, 'Winner')
