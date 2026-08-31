"""Offline coverage for PEN/Hemingway keyed landing and year cache."""

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
from awards.sources import hugo, pen_hemingway as ph
from tests.test_pen_hemingway_parser import (
    _PAIRS_2026,
    _finalists_article,
    _finalists_url,
    _historical_landing,
    _landing_url,
    _winner_article,
    _winner_url,
)

_UTC = timezone.utc
_STALE_AT = datetime(2020, 1, 1, tzinfo=_UTC)
_FINALISTS_2027 = (
    'https://www.penfaulkner.org/2027/02/17/announcing-the-finalists-for-the-2027-pen-hemingway-award-for-debut-novel/'
)
_WINNER_2027 = (
    'https://www.penfaulkner.org/2027/03/16/announcing-the-winner-of-the-2027-pen-hemingway-award-for-debut-novel/'
)


def _entry_path(cache_dir: Path, entry_kind: str, entry_key: str) -> Path:
    digest = hashlib.sha256(entry_key.encode('utf-8')).hexdigest()
    return cache_dir / ph.SOURCE_KEY / entry_kind / f'{digest}.json'


class _HttpTracker:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def fetch_response(self, url: str):
        self.calls.append(url)
        body = self.pages.get(url)
        if body == 'FAIL':
            raise ph.PenHemingwaySourceError(f'HTTP failed for {url}')
        if body == '404' or body is None:
            return 404, '', url
        if isinstance(body, tuple):
            return body
        return 200, body, url


def _save_landing(snapshot, *, generated_at=None, ttl_seconds=None, version=None):
    cache.save_cache_entry(
        ph.SOURCE_KEY,
        ph.ARCHIVE_ENTRY_KIND,
        ph.ARCHIVE_ENTRY_KEY,
        ph.ARCHIVE_CACHE_VERSION if version is None else version,
        records=[ph._record_to_cache_dict(record) for record in snapshot.records],
        source_urls=[ph.SOURCE_HOME_URL],
        coverage=ph._archive_coverage(),
        ttl_seconds=(
            ph.HISTORICAL_CACHE_TTL_SECONDS if ttl_seconds is None else ttl_seconds
        ),
        generated_at=generated_at,
    )


def _save_year(snapshot, *, generated_at=None, ttl_seconds=None, version=None):
    cache.save_cache_entry(
        ph.SOURCE_KEY,
        ph.YEAR_ENTRY_KIND,
        ph._year_entry_key(snapshot.award_year),
        ph.YEAR_CACHE_VERSION if version is None else version,
        records=[ph._record_to_cache_dict(record) for record in snapshot.records],
        source_urls=list(snapshot.source_urls),
        coverage=ph._year_coverage(snapshot.award_year, snapshot.state),
        ttl_seconds=(
            ph._year_ttl_seconds(snapshot.state)
            if ttl_seconds is None
            else ttl_seconds
        ),
        generated_at=generated_at,
    )


def _landing_snapshot():
    html = _historical_landing()
    records = ph._parse_landing_html(html, _landing_url())
    ph._validate_historical_records(records)
    return ph._ArchiveSnapshot(records=records, source_url=_landing_url())


def _completed_year(year: int, pairs, winner_title: str, winner_author: str):
    finalists_html = _finalists_article(year, pairs)
    winner_html = _winner_article(year, winner_title, winner_author)
    winner_url = (
        _winner_url(year) if year in ph.VERIFIED_YEAR_URLS else _WINNER_2027
    )
    finalists_url = (
        _finalists_url(year) if year in ph.VERIFIED_YEAR_URLS else _FINALISTS_2027
    )
    finalist_records = ph._parse_finalists_html(
        finalists_html, year, finalists_url
    )
    winner = ph._parse_winner_html(winner_html, year, winner_url)
    merged = ph._dedupe_records(list(finalist_records) + [winner])
    return ph._YearSnapshot(
        award_year=year,
        state='winner',
        source_urls=(winner_url, finalists_url),
        records=merged,
    ), {finalists_url: finalists_html, winner_url: winner_html}


def _finalist_only_year(year: int, pairs):
    html = _finalists_article(year, pairs)
    url = _finalists_url(year) if year in ph.VERIFIED_YEAR_URLS else _FINALISTS_2027
    records = ph._parse_finalists_html(html, year, url)
    return ph._YearSnapshot(
        award_year=year,
        state='finalist',
        source_urls=(url,),
        records=records,
    ), {url: html}


def _absent_year(year: int) -> ph._YearSnapshot:
    return ph._YearSnapshot(
        award_year=year,
        state='absent',
        source_urls=(),
        records=(),
    )


def _seed_unused_modern_years(live_years, utc_year: int) -> None:
    live = set(live_years)
    end = max(ph.MAX_VERIFIED_YEAR, utc_year)
    for year in range(ph.HISTORICAL_ARCHIVE_MAX_YEAR + 1, end + 1):
        if year in live:
            continue
        existing = cache.load_cache_entry(
            ph.SOURCE_KEY,
            ph.YEAR_ENTRY_KIND,
            ph._year_entry_key(year),
            ph.YEAR_CACHE_VERSION,
        )
        if existing is not None:
            continue
        _save_year(_absent_year(year))


def _live_years_from_pages(pages, utc_year: int) -> set[int]:
    live: set[int] = set()
    for year, urls in ph.VERIFIED_YEAR_URLS.items():
        if urls['winner'] in pages or urls['finalists'] in pages:
            live.add(year)
    for url in pages:
        path_year = ph._path_year(url)
        if path_year is not None and path_year > ph.HISTORICAL_ARCHIVE_MAX_YEAR:
            live.add(path_year)
    if ph.AWARD_NEWS_REST_URL in pages and utc_year > ph.MAX_VERIFIED_YEAR:
        live.add(utc_year)
    return live


class PenHemingwayCacheTests(unittest.TestCase):
    def setUp(self):
        self._temp = TemporaryDirectory()
        self.cache_dir = Path(self._temp.name)
        cache.set_cache_directory(self.cache_dir)
        ph._reset_runtime_state()
        hugo._reset_runtime_state()

    def tearDown(self):
        ph._reset_runtime_state()
        hugo._reset_runtime_state()
        cache.set_cache_directory(None)
        self._temp.cleanup()

    def _lookup(self, pages, title, author, utc_year=2026, live_years=None):
        if live_years is None:
            live_years = _live_years_from_pages(pages, utc_year)
        _seed_unused_modern_years(live_years, utc_year)
        tracker = _HttpTracker(pages)
        with patch.object(ph, '_fetch_response', tracker.fetch_response), patch.object(
            ph, '_current_calendar_year', return_value=utc_year
        ):
            results = ph.lookup(title, author)
        return results, tracker

    def test_cold_landing_is_one_get(self):
        pages = {_landing_url(): _historical_landing()}
        results, tracker = self._lookup(
            pages, 'Parthian Shot', 'Loyd Little', utc_year=2025
        )
        self.assertEqual(tracker.calls, [_landing_url()])
        self.assertEqual(results[0].status, 'Winner')
        self.assertEqual(results[0].award_year, 1976)
        payload = cache.load_cache_entry(
            ph.SOURCE_KEY,
            ph.ARCHIVE_ENTRY_KIND,
            ph.ARCHIVE_ENTRY_KEY,
            ph.ARCHIVE_CACHE_VERSION,
        )
        self.assertNotIn('html', payload)
        self.assertTrue(all('html' not in item for item in payload['records']))

    def test_fresh_landing_is_zero_http(self):
        _save_landing(_landing_snapshot())
        results, tracker = self._lookup(
            {}, 'Housekeeping', 'Marilynne Robinson', utc_year=2025
        )
        self.assertEqual(tracker.calls, [])
        self.assertEqual(results[0].status, 'Winner')

    def test_ram_reset_fresh_disk_is_zero_http(self):
        _save_landing(_landing_snapshot())
        ph._reset_runtime_state()
        results, tracker = self._lookup(
            {}, 'Interpreter of Maladies', 'Jhumpa Lahiri', utc_year=2025
        )
        self.assertEqual(tracker.calls, [])
        self.assertEqual(results[0].source_url, _landing_url())

    def test_stale_landing_slot_won_refreshes_once(self):
        _save_landing(_landing_snapshot(), generated_at=_STALE_AT, ttl_seconds=60)
        pages = {_landing_url(): _historical_landing()}
        with cache.lookup_refresh_budget():
            results, tracker = self._lookup(
                pages, 'The Yellow Birds', 'Kevin Powers', utc_year=2025
            )
        self.assertEqual(tracker.calls, [_landing_url()])
        self.assertEqual(results[0].status, 'Winner')

    def test_stale_landing_slot_denied_uses_stale(self):
        _save_landing(_landing_snapshot(), generated_at=_STALE_AT, ttl_seconds=60)
        with cache.lookup_refresh_budget():
            self.assertTrue(cache.try_claim_stale_refresh())
            results, tracker = self._lookup(
                {_landing_url(): 'FAIL'},
                'Early Sobrieties',
                'Michael Deagler',
                utc_year=2025,
            )
        self.assertEqual(tracker.calls, [])
        self.assertEqual(results[0].status, 'Winner')

    def test_stale_refresh_failure_keeps_stale(self):
        snapshot = _landing_snapshot()
        _save_landing(snapshot, generated_at=_STALE_AT, ttl_seconds=60)
        with cache.lookup_refresh_budget():
            results, tracker = self._lookup(
                {_landing_url(): 'FAIL'},
                'Native Speaker',
                'Chang-rae Lee',
                utc_year=2025,
            )
        self.assertEqual(tracker.calls, [_landing_url()])
        self.assertEqual(results[0].work_author, 'Chang-rae Lee')
        loaded = cache.load_cache_entry(
            ph.SOURCE_KEY,
            ph.ARCHIVE_ENTRY_KIND,
            ph.ARCHIVE_ENTRY_KEY,
            ph.ARCHIVE_CACHE_VERSION,
        )
        self.assertEqual(loaded['generated_at'], _STALE_AT.strftime('%Y-%m-%dT%H:%M:%SZ'))

    def test_missing_landing_fetches_live(self):
        pages = {_landing_url(): _historical_landing()}
        _results, tracker = self._lookup(
            pages, 'Shiloh and Other Stories', 'Bobbie Ann Mason', utc_year=2025
        )
        self.assertEqual(tracker.calls, [_landing_url()])

    def test_malformed_and_version_mismatch_fetch_live(self):
        path = _entry_path(self.cache_dir, ph.ARCHIVE_ENTRY_KIND, ph.ARCHIVE_ENTRY_KEY)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{not json', encoding='utf-8')
        pages = {_landing_url(): _historical_landing()}
        _results, tracker = self._lookup(
            pages, 'Parthian Shot', 'Loyd Little', utc_year=2025
        )
        self.assertEqual(tracker.calls, [_landing_url()])
        ph._reset_runtime_state()
        _save_landing(_landing_snapshot(), version=99)
        _results, tracker = self._lookup(
            pages, 'Parthian Shot', 'Loyd Little', utc_year=2025
        )
        self.assertEqual(tracker.calls, [_landing_url()])

    def test_failed_historical_validation_does_not_save(self):
        pages = {_landing_url(): _historical_landing(skip_year=1990)}
        with self.assertRaises(ph.PenHemingwaySourceError):
            self._lookup(
                pages,
                'The Ice at the Bottom of the World',
                'Mark Richard',
                utc_year=2025,
            )
        self.assertIsNone(
            cache.load_cache_entry(
                ph.SOURCE_KEY,
                ph.ARCHIVE_ENTRY_KIND,
                ph.ARCHIVE_ENTRY_KEY,
                ph.ARCHIVE_CACHE_VERSION,
            )
        )

    def test_cold_completed_year_fetches_winner_and_finalists(self):
        _save_landing(_landing_snapshot())
        snapshot, pages = _completed_year(
            2026, _PAIRS_2026, 'The Correspondent', 'Virginia Evans'
        )
        results, tracker = self._lookup(
            pages, 'The Correspondent', 'Virginia Evans'
        )
        self.assertEqual(set(tracker.calls), set(pages))
        self.assertEqual(len(tracker.calls), 2)
        self.assertEqual(results[0].status, 'Winner')
        self.assertEqual(results[0].award_year, 2026)
        self.assertEqual(results[0].source_url, _winner_url(2026))
        payload = cache.load_cache_entry(
            ph.SOURCE_KEY,
            ph.YEAR_ENTRY_KIND,
            '2026',
            ph.YEAR_CACHE_VERSION,
        )
        self.assertEqual(payload['coverage']['state'], 'winner')
        self.assertNotIn('html', payload)
        self.assertTrue(all('content' not in item for item in payload['records']))
        self.assertEqual(len(payload['records']), 3)

    def test_fresh_completed_year_is_zero_http(self):
        _save_landing(_landing_snapshot())
        snapshot, _pages = _completed_year(
            2026, _PAIRS_2026, 'The Correspondent', 'Virginia Evans'
        )
        _save_year(snapshot)
        results, tracker = self._lookup({}, 'Awake in the Floating City', 'Susanna Kwan')
        self.assertEqual(tracker.calls, [])
        self.assertEqual(results[0].status, 'Finalist')

    def test_stale_completed_year_slot_won_refreshes_only_that_year(self):
        _save_landing(_landing_snapshot())
        snap_2026, pages_2026 = _completed_year(
            2026, _PAIRS_2026, 'The Correspondent', 'Virginia Evans'
        )
        _save_year(snap_2026, generated_at=_STALE_AT, ttl_seconds=60)
        with cache.lookup_refresh_budget():
            _results, tracker = self._lookup(
                pages_2026, 'The Correspondent', 'Virginia Evans'
            )
        self.assertEqual(set(tracker.calls), set(pages_2026))
        self.assertNotIn(_landing_url(), tracker.calls)

    def test_stale_completed_slot_denied_uses_stale(self):
        _save_landing(_landing_snapshot())
        snapshot, pages = _completed_year(
            2026, _PAIRS_2026, 'The Correspondent', 'Virginia Evans'
        )
        _save_year(snapshot, generated_at=_STALE_AT, ttl_seconds=60)
        with cache.lookup_refresh_budget():
            self.assertTrue(cache.try_claim_stale_refresh())
            results, tracker = self._lookup(
                {url: 'FAIL' for url in pages},
                'Blob',
                'Maggie Su',
            )
        self.assertEqual(tracker.calls, [])
        self.assertEqual(results[0].status, 'Finalist')

    def test_stale_year_refresh_failure_keeps_stale(self):
        _save_landing(_landing_snapshot())
        snapshot, pages = _completed_year(
            2026, _PAIRS_2026, 'The Correspondent', 'Virginia Evans'
        )
        _save_year(snapshot, generated_at=_STALE_AT, ttl_seconds=60)
        with cache.lookup_refresh_budget():
            results, tracker = self._lookup(
                {url: 'FAIL' for url in pages},
                'Awake in the Floating City',
                'Susanna Kwan',
            )
        self.assertTrue(tracker.calls)
        self.assertEqual(results[0].work_title, 'Awake in the Floating City')
        loaded = cache.load_cache_entry(
            ph.SOURCE_KEY, ph.YEAR_ENTRY_KIND, '2026', ph.YEAR_CACHE_VERSION
        )
        self.assertEqual(loaded['generated_at'], _STALE_AT.strftime('%Y-%m-%dT%H:%M:%SZ'))

    def test_winner_absent_finalists_use_short_ttl(self):
        _save_landing(_landing_snapshot())
        snapshot, pages = _finalist_only_year(2026, _PAIRS_2026)
        results, tracker = self._lookup(pages, 'Blob', 'Maggie Su')
        self.assertEqual(results[0].status, 'Finalist')
        payload = cache.load_cache_entry(
            ph.SOURCE_KEY, ph.YEAR_ENTRY_KIND, '2026', ph.YEAR_CACHE_VERSION
        )
        self.assertEqual(payload['coverage']['state'], 'finalist')
        self.assertEqual(payload['ttl_seconds'], ph.CURRENT_CACHE_TTL_SECONDS)
        self.assertEqual(ph.CURRENT_CACHE_REFRESH_OFFSET_SECONDS, 14 * 60 * 60)

    def test_winner_later_becomes_completed(self):
        _save_landing(_landing_snapshot())
        finalist_snapshot, _finalist_pages = _finalist_only_year(2026, _PAIRS_2026)
        _save_year(finalist_snapshot, generated_at=_STALE_AT, ttl_seconds=60)
        _completed, pages = _completed_year(
            2026, _PAIRS_2026, 'The Correspondent', 'Virginia Evans'
        )
        with cache.lookup_refresh_budget():
            results, _tracker = self._lookup(
                pages, 'The Correspondent', 'Virginia Evans'
            )
        self.assertEqual(results[0].status, 'Winner')
        payload = cache.load_cache_entry(
            ph.SOURCE_KEY, ph.YEAR_ENTRY_KIND, '2026', ph.YEAR_CACHE_VERSION
        )
        self.assertEqual(payload['coverage']['state'], 'winner')
        self.assertEqual(payload['ttl_seconds'], ph.HISTORICAL_CACHE_TTL_SECONDS)

    def test_future_absent_uses_short_ttl(self):
        _save_landing(_landing_snapshot())
        rest = json.dumps([])
        pages = {ph.AWARD_NEWS_REST_URL: rest}
        results, tracker = self._lookup(
            pages, 'No Such Book', 'No Such Author', utc_year=2027
        )
        self.assertEqual(results, [])
        self.assertIn(ph.AWARD_NEWS_REST_URL, tracker.calls)
        payload = cache.load_cache_entry(
            ph.SOURCE_KEY, ph.YEAR_ENTRY_KIND, '2027', ph.YEAR_CACHE_VERSION
        )
        self.assertEqual(payload['coverage']['state'], 'absent')
        self.assertEqual(payload['ttl_seconds'], ph.CURRENT_CACHE_TTL_SECONDS)
        self.assertEqual(payload['records'], [])

    def test_fresh_absent_is_zero_discovery_http(self):
        _save_landing(_landing_snapshot())
        _save_year(_absent_year(2027))
        results, tracker = self._lookup(
            {ph.AWARD_NEWS_REST_URL: 'FAIL'},
            'No Such Book',
            'No Such Author',
            utc_year=2027,
        )
        self.assertEqual(results, [])
        self.assertEqual(tracker.calls, [])

    def test_modern_years_are_independent(self):
        _save_landing(_landing_snapshot())
        snap_2026, pages_2026 = _completed_year(
            2026, _PAIRS_2026, 'The Correspondent', 'Virginia Evans'
        )
        _save_year(snap_2026)
        results, tracker = self._lookup(
            {url: 'FAIL' for url in pages_2026},
            'Early Sobrieties',
            'Michael Deagler',
        )
        self.assertEqual(results[0].status, 'Winner')
        self.assertEqual(results[0].award_year, 2025)
        self.assertTrue(set(tracker.calls).isdisjoint(pages_2026))

    def test_failed_year_does_not_delete_sibling(self):
        _save_landing(_landing_snapshot())
        snap_2026, _pages = _completed_year(
            2026, _PAIRS_2026, 'The Correspondent', 'Virginia Evans'
        )
        _save_year(snap_2026)
        results, _tracker = self._lookup(
            {
                _winner_url(2026): 'FAIL',
                _finalists_url(2026): 'FAIL',
            },
            'Early Sobrieties',
            'Michael Deagler',
        )
        self.assertEqual(results[0].award_year, 2025)
        sibling = cache.load_cache_entry(
            ph.SOURCE_KEY, ph.YEAR_ENTRY_KIND, '2026', ph.YEAR_CACHE_VERSION
        )
        self.assertIsNotNone(sibling)

    def test_longlist_is_not_persisted(self):
        _save_landing(_landing_snapshot())
        _snapshot, pages = _completed_year(
            2026, _PAIRS_2026, 'The Correspondent', 'Virginia Evans'
        )
        results, _tracker = self._lookup(pages, 'Trip', 'Amie Barrodale')
        self.assertEqual(results, [])
        payload = cache.load_cache_entry(
            ph.SOURCE_KEY, ph.YEAR_ENTRY_KIND, '2026', ph.YEAR_CACHE_VERSION
        )
        titles = [item['work_title'] for item in payload['records']]
        self.assertNotIn('Trip', titles)
        authors = [item['work_author'] for item in payload['records']]
        self.assertNotIn('Amie Barrodale', authors)

    def test_foreign_hosts_are_not_persisted(self):
        _save_landing(_landing_snapshot())
        _snapshot, pages = _completed_year(
            2026, _PAIRS_2026, 'The Correspondent', 'Virginia Evans'
        )
        self._lookup(pages, 'The Correspondent', 'Virginia Evans')
        payload = cache.load_cache_entry(
            ph.SOURCE_KEY, ph.YEAR_ENTRY_KIND, '2026', ph.YEAR_CACHE_VERSION
        )
        blob = json.dumps(payload)
        self.assertNotIn('hemingwaysociety.org', blob)
        self.assertNotIn('pen.org', blob)
        self.assertNotIn('jfklibrary.org', blob)
        self.assertNotIn('pen-ne.org', blob)

    def test_manual_refresh_clears_archive_years_and_ram_with_zero_http(self):
        _save_landing(_landing_snapshot())
        snapshot, pages = _completed_year(
            2026, _PAIRS_2026, 'The Correspondent', 'Virginia Evans'
        )
        _save_year(snapshot)
        ph._store_landing_snapshot(_landing_snapshot())
        ph._store_year_snapshot(snapshot)
        hugo._archive_records_cache = ()
        cache.save_source_cache(
            'hugo',
            1,
            records=[{'title': 'hugo', 'year': 2020}],
            source_urls=['https://example.test/hugo'],
            coverage={'source': 'hugo'},
            ttl_seconds=3600,
        )
        tracker = _HttpTracker(pages)
        with patch.object(ph, '_fetch_response', tracker.fetch_response):
            self.assertTrue(refresh_award_source_cache('pen_hemingway'))
        self.assertEqual(tracker.calls, [])
        self.assertIsNone(ph._ram_landing())
        self.assertIsNone(ph._ram_year(2026))
        self.assertIsNone(
            cache.load_cache_entry(
                ph.SOURCE_KEY,
                ph.ARCHIVE_ENTRY_KIND,
                ph.ARCHIVE_ENTRY_KEY,
                ph.ARCHIVE_CACHE_VERSION,
            )
        )
        self.assertIsNone(
            cache.load_cache_entry(
                ph.SOURCE_KEY, ph.YEAR_ENTRY_KIND, '2026', ph.YEAR_CACHE_VERSION
            )
        )
        self.assertTrue((self.cache_dir / 'hugo.json').is_file())
        self.assertEqual(hugo._archive_records_cache, ())

    def test_discovery_then_finalist_then_winner(self):
        _save_landing(_landing_snapshot())
        rest_finalists = json.dumps(
            [
                {
                    'title': {
                        'rendered': 'Announcing the Winner of the 2027 PEN/Faulkner Award for Fiction'
                    },
                    'slug': 'announcing-the-winner-of-the-2027-pen-faulkner-award-for-fiction',
                    'link': 'https://www.penfaulkner.org/2027/04/06/announcing-the-winner-of-the-2027-pen-faulkner-award-for-fiction/',
                },
                {
                    'title': {
                        'rendered': 'Announcing the Longlist for the 2027 PEN/Hemingway Award for Debut Novel'
                    },
                    'slug': 'announcing-the-longlist-for-the-2027-pen-hemingway-award-for-fiction',
                    'link': 'https://www.penfaulkner.org/2027/01/20/announcing-the-longlist-for-the-2027-pen-hemingway-award-for-fiction/',
                },
                {
                    'title': {
                        'rendered': 'Announcing the Finalists for the 2027 PEN/Hemingway Award for Debut Novel'
                    },
                    'slug': 'announcing-the-finalists-for-the-2027-pen-hemingway-award-for-debut-novel',
                    'link': _FINALISTS_2027,
                },
                {
                    'title': {
                        'rendered': 'Elizabeth McCracken Wins the 2027 PEN/Bernard and Ann Malamud Award'
                    },
                    'slug': 'elizabeth-mccracken-wins-the-2027-pen-bernard-and-ann-malamud-award',
                    'link': 'https://www.penfaulkner.org/2027/05/01/elizabeth-mccracken-wins-the-2027-pen-bernard-and-ann-malamud-award/',
                },
                {
                    'title': {
                        'rendered': 'Willee Lewis is our 2027 PEN/Faulkner Literary Champion'
                    },
                    'slug': 'willee-lewis-is-our-2027-pen-faulkner-literary-champion',
                    'link': 'https://www.penfaulkner.org/2027/10/01/willee-lewis-is-our-2027-pen-faulkner-literary-champion/',
                },
                {
                    'title': {'rendered': 'Unrelated award news'},
                    'slug': 'unrelated-award-news',
                    'link': 'https://www.penfaulkner.org/2027/06/01/unrelated-award-news/',
                },
            ]
        )
        finalists_html = _finalists_article(2027, _PAIRS_2026)
        pages = {
            ph.AWARD_NEWS_REST_URL: rest_finalists,
            _FINALISTS_2027: finalists_html,
        }
        results, tracker = self._lookup(
            pages, 'Blob', 'Maggie Su', utc_year=2027
        )
        self.assertEqual(results[0].status, 'Finalist')
        self.assertIn(ph.AWARD_NEWS_REST_URL, tracker.calls)
        self.assertIn(_FINALISTS_2027, tracker.calls)
        payload = cache.load_cache_entry(
            ph.SOURCE_KEY, ph.YEAR_ENTRY_KIND, '2027', ph.YEAR_CACHE_VERSION
        )
        self.assertEqual(payload['coverage']['state'], 'finalist')
        self.assertNotIn('html', payload)
        self.assertNotIn('wp-json', json.dumps(payload['records']))

        ph._reset_runtime_state()
        rest_both = json.dumps(
            [
                {
                    'title': {
                        'rendered': 'Announcing the Finalists for the 2027 PEN/Hemingway Award for Debut Novel'
                    },
                    'slug': 'announcing-the-finalists-for-the-2027-pen-hemingway-award-for-debut-novel',
                    'link': _FINALISTS_2027,
                },
                {
                    'title': {
                        'rendered': 'Announcing the Winner of the 2027 PEN/Hemingway Award for Debut Novel'
                    },
                    'slug': 'announcing-the-winner-of-the-2027-pen-hemingway-award-for-debut-novel',
                    'link': _WINNER_2027,
                },
            ]
        )
        winner_html = _winner_article(2027, 'The Correspondent', 'Virginia Evans')
        pages = {
            ph.AWARD_NEWS_REST_URL: rest_both,
            _FINALISTS_2027: finalists_html,
            _WINNER_2027: winner_html,
        }
        _save_year(
            ph._YearSnapshot(
                award_year=2027,
                state='finalist',
                source_urls=(_FINALISTS_2027,),
                records=ph._parse_finalists_html(
                    finalists_html, 2027, _FINALISTS_2027
                ),
            ),
            generated_at=_STALE_AT,
            ttl_seconds=60,
        )
        with cache.lookup_refresh_budget():
            results, _tracker = self._lookup(
                pages, 'The Correspondent', 'Virginia Evans', utc_year=2027
            )
        self.assertEqual(results[0].status, 'Winner')
        payload = cache.load_cache_entry(
            ph.SOURCE_KEY, ph.YEAR_ENTRY_KIND, '2027', ph.YEAR_CACHE_VERSION
        )
        self.assertEqual(payload['coverage']['state'], 'winner')

    def test_malformed_year_fetches_live(self):
        _save_landing(_landing_snapshot())
        path = _entry_path(self.cache_dir, ph.YEAR_ENTRY_KIND, '2026')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{not json', encoding='utf-8')
        _snapshot, pages = _completed_year(
            2026, _PAIRS_2026, 'The Correspondent', 'Virginia Evans'
        )
        results, tracker = self._lookup(
            pages, 'The Correspondent', 'Virginia Evans', live_years={2026}
        )
        self.assertTrue(tracker.calls)
        self.assertEqual(results[0].status, 'Winner')

    def test_year_version_mismatch_fetches_live(self):
        _save_landing(_landing_snapshot())
        snapshot, pages = _completed_year(
            2026, _PAIRS_2026, 'The Correspondent', 'Virginia Evans'
        )
        _save_year(snapshot, version=99)
        results, tracker = self._lookup(
            pages, 'Blob', 'Maggie Su', live_years={2026}
        )
        self.assertTrue(tracker.calls)
        self.assertEqual(results[0].status, 'Finalist')

    def test_ambiguous_discovery_fails_closed(self):
        _save_landing(_landing_snapshot())
        rest = json.dumps(
            [
                {
                    'title': {
                        'rendered': 'Announcing the Finalists for the 2027 PEN/Hemingway Award for Debut Novel'
                    },
                    'slug': 'announcing-the-finalists-for-the-2027-pen-hemingway-award-for-debut-novel',
                    'link': _FINALISTS_2027,
                },
                {
                    'title': {
                        'rendered': 'Announcing the Finalists for the 2027 PEN/Hemingway Award for Debut Novel'
                    },
                    'slug': 'announcing-the-finalists-for-the-2027-pen-hemingway-award-for-debut-novel-2',
                    'link': 'https://www.penfaulkner.org/2027/02/18/announcing-the-finalists-for-the-2027-pen-hemingway-award-for-debut-novel-2/',
                },
            ]
        )
        results, _tracker = self._lookup(
            {ph.AWARD_NEWS_REST_URL: rest},
            'Blob',
            'Maggie Su',
            utc_year=2027,
        )
        self.assertEqual(results, [])
        self.assertIsNone(
            cache.load_cache_entry(
                ph.SOURCE_KEY, ph.YEAR_ENTRY_KIND, '2027', ph.YEAR_CACHE_VERSION
            )
        )

    def test_url_body_year_disagreement_does_not_cache_absent(self):
        _save_landing(_landing_snapshot())
        rest = json.dumps(
            [
                {
                    'title': {
                        'rendered': 'Announcing the Winner of the 2027 PEN/Hemingway Award for Debut Novel'
                    },
                    'slug': 'announcing-the-winner-of-the-2027-pen-hemingway-award-for-debut-novel',
                    'link': _WINNER_2027,
                }
            ]
        )
        html = _winner_article(2026, 'The Correspondent', 'Virginia Evans')
        pages = {
            ph.AWARD_NEWS_REST_URL: rest,
            _WINNER_2027: html,
        }
        results, _tracker = self._lookup(
            pages, 'The Correspondent', 'Virginia Evans', utc_year=2027
        )
        self.assertEqual(results, [])
        self.assertIsNone(
            cache.load_cache_entry(
                ph.SOURCE_KEY, ph.YEAR_ENTRY_KIND, '2027', ph.YEAR_CACHE_VERSION
            )
        )

    def test_rest_title_typo_does_not_control_year(self):
        _save_landing(_landing_snapshot())
        rest = json.dumps(
            [
                {
                    'title': {
                        'rendered': 'Announcing the Finalists for the 2028 PEN/Hemingway Award for Debut Novel'
                    },
                    'slug': 'announcing-the-finalists-for-the-2027-pen-hemingway-award-for-debut-novel',
                    'link': _FINALISTS_2027,
                }
            ]
        )
        html = _finalists_article(2027, _PAIRS_2026)
        pages = {
            ph.AWARD_NEWS_REST_URL: rest,
            _FINALISTS_2027: html,
        }
        results, tracker = self._lookup(
            pages, 'Blob', 'Maggie Su', utc_year=2027
        )
        self.assertEqual(results[0].award_year, 2027)
        self.assertIn(ph.AWARD_NEWS_REST_URL, tracker.calls)
        payload = cache.load_cache_entry(
            ph.SOURCE_KEY, ph.YEAR_ENTRY_KIND, '2027', ph.YEAR_CACHE_VERSION
        )
        self.assertEqual(payload['coverage']['state'], 'finalist')
        self.assertNotIn('html', json.dumps(payload))
        self.assertNotIn('wp-json', json.dumps(payload['records']))

    def test_partial_winner_failure_keeps_finalists(self):
        _save_landing(_landing_snapshot())
        finalists_html = _finalists_article(2026, _PAIRS_2026)
        pages = {
            _finalists_url(2026): finalists_html,
            _winner_url(2026): 'FAIL',
        }
        results, tracker = self._lookup(pages, 'The Correspondent', 'Virginia Evans')
        self.assertEqual(results[0].status, 'Finalist')
        payload = cache.load_cache_entry(
            ph.SOURCE_KEY, ph.YEAR_ENTRY_KIND, '2026', ph.YEAR_CACHE_VERSION
        )
        self.assertEqual(payload['coverage']['state'], 'finalist')
        self.assertEqual(payload['ttl_seconds'], ph.CURRENT_CACHE_TTL_SECONDS)
        self.assertIn(_finalists_url(2026), tracker.calls)


if __name__ == '__main__':
    unittest.main()
