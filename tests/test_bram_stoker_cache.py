"""Offline coverage for Bram Stoker keyed index and year cache."""

from __future__ import annotations

import hashlib
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from awards import cache
from awards.cache_control import refresh_award_source_cache
from awards.sources import bram_stoker as src
from awards.sources import hugo
from tests.test_bram_stoker_parser import (
    Inaugural1987Tests,
    Modern2025Tests,
    Structure2022Tests,
    _page,
)

_UTC = timezone.utc
_STALE_AT = datetime(2020, 1, 1, tzinfo=_UTC)
_FIXTURE_YEARS = (1987, 2000, 2022, 2025)
_BALLOT_2026 = src.SITE_ORIGIN + '/news/2026-final-ballot/'
_WINNERS_2026 = src.SITE_ORIGIN + '/news/2026-winners/'
_PRELIM_2026 = src.SITE_ORIGIN + '/news/2026-preliminary-ballot/'
_PRELIM_2025 = src.SITE_ORIGIN + '/news/2025-preliminary-ballot/'


def _census(year: int) -> str:
    return src.SITE_ORIGIN + src.HISTORICAL_CENSUS_PATHS[year]


def _fixture_year_urls() -> dict[int, str]:
    return {year: _census(year) for year in _FIXTURE_YEARS}


def _html_1987() -> str:
    return _page(
        Inaugural1987Tests()._html(),
        '1987 Bram Stoker Award Nominees & Winner',
        1987,
    )


def _html_2000() -> str:
    body = '''
    <h3>Novel</h3>
    The Indifference of Heaven by Gary A. Braunbeck<br>
    The Licking Valley Coon Hunters Club by Brian A. Hopkins<br>
    The Traveling Vampire Show by Richard Laymon, Winner
    <h3>First Novel</h3>
    Nailed by the Heart by Simon Clark<br>
    The Licking Valley Coon Hunters Club by Brian A. Hopkins, Winner<br>
    Run by Douglas E. Winter
    '''
    return _page(body, '2000 Bram Stoker Award Winners & Nominees', 2000)


def _html_2022_ballot() -> str:
    return _page(
        Structure2022Tests()._ballot_body(),
        'The 2022 Bram Stoker Awards® Final Ballot',
        2022,
    )


def _html_2025() -> str:
    return _page(
        Modern2025Tests()._html(),
        'The 2025 Bram Stoker Award® Winners',
        2025,
    )


def _html_2026_ballot(*, winners: bool) -> str:
    winner_mark = ' – WINNER' if winners else ''
    body = f'''
    <h3>Superior Achievement in a Novel</h3>
    <p>Author, One— First Book (Press){winner_mark}</p>
    <p>Author, Two— Second Book (Press)</p>
    <p>Author, Three— Third Book (Press)</p>
    <p>Author, Four— Fourth Book (Press)</p>
    <p>Author, Five— Fifth Book (Press)</p>
    <h3>Superior Achievement in a First Novel</h3>
    <p>Debut, One— Debut Book (Press)</p>
    <p>Debut, Two— Other Debut (Press){winner_mark}</p>
    <p>Debut, Three— Third Debut (Press)</p>
    '''
    title = (
        'The 2026 Bram Stoker Awards® Winners'
        if winners
        else 'The 2026 Bram Stoker Awards® Final Ballot'
    )
    return _page(body, title, 2026)


def _html_2026_winners_only() -> str:
    body = '''
    <h3>Superior Achievement in a Novel</h3>
    <p>Author, One— First Book (Press) – WINNER</p>
    <h3>Superior Achievement in a First Novel</h3>
    <p>Debut, Two— Other Debut (Press) – WINNER</p>
    <h3>Superior Achievement in Long Fiction</h3>
    <p>Long, Author— A Novella (Press) – WINNER</p>
    '''
    return _page(body, 'The 2026 Bram Stoker Award winners', 2026)


def _html_preliminary(year: int, url_title: str) -> str:
    body = '''
    <h3>Superior Achievement in a Novel</h3>
    <p>Baker, Kylie Lee— Bat Eater and Other Names for Cora Zeng (Press)</p>
    <p>Tingle, Chuck— Lucky Day (Press)</p>
    '''
    return _page(body, url_title, year)


def _entry_path(cache_dir: Path, entry_kind: str, entry_key: str) -> Path:
    digest = hashlib.sha256(entry_key.encode('utf-8')).hexdigest()
    return cache_dir / src.SOURCE_KEY / entry_kind / f'{digest}.json'


class _HttpTracker:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def fetch_response(self, url: str, headers=None):
        self.calls.append(url)
        body = self.pages.get(url)
        if body == 'FAIL':
            raise src.BramStokerSourceError(f'HTTP failed for {url}')
        if body is None:
            raise src.BramStokerSourceError(f'missing {url}')
        if isinstance(body, tuple):
            return body
        return 200, body, url


def _year_html(year: int) -> str:
    if year == 1987:
        return _html_1987()
    if year == 2000:
        return _html_2000()
    if year == 2022:
        return _html_2022_ballot()
    if year == 2025:
        return _html_2025()
    raise AssertionError(f'no fixture html for {year}')


def _year_snapshot(year: int) -> src._YearSnapshot:
    url = _census(year)
    records = src._parse_year_page(_year_html(year), year, url)
    state = src._classify_year_state(records)
    src._validate_year_records(records, year, state)
    return src._YearSnapshot(
        award_year=year,
        state=state,
        source_urls=(url,),
        records=records,
    )


def _index_snapshot(year_urls=None, winner_urls=None) -> src._IndexSnapshot:
    return src._IndexSnapshot(
        year_urls=dict(year_urls or _fixture_year_urls()),
        latest_completed_year=src.MAX_VERIFIED_YEAR,
        winner_urls=dict(winner_urls or {}),
    )


def _save_index(snapshot=None, *, generated_at=None, ttl_seconds=None, version=None):
    snapshot = snapshot or _index_snapshot()
    cache.save_cache_entry(
        src.SOURCE_KEY,
        src.INDEX_ENTRY_KIND,
        src.INDEX_ENTRY_KEY,
        src.INDEX_CACHE_VERSION if version is None else version,
        records=[],
        source_urls=[src.SOURCE_HOME_URL],
        coverage=src._index_coverage(snapshot),
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


def _seed_completed_disk() -> None:
    _save_index()
    for year in _FIXTURE_YEARS:
        _save_year(_year_snapshot(year))


def _completed_pages() -> dict[str, str]:
    pages = {_census(year): _year_html(year) for year in _FIXTURE_YEARS}
    pages[_PRELIM_2025] = _html_preliminary(
        2025,
        'The 2025 Bram Stoker Awards® Preliminary Ballot Announced',
    )
    return pages


class BramStokerCacheTests(unittest.TestCase):
    def setUp(self):
        self._temp = TemporaryDirectory()
        self.cache_dir = Path(self._temp.name)
        cache.set_cache_directory(self.cache_dir)
        src._reset_runtime_state()
        hugo._reset_runtime_state()
        self._year_urls_patch = patch.object(
            src, '_historical_year_urls', _fixture_year_urls
        )
        self._year_urls_patch.start()

    def tearDown(self):
        self._year_urls_patch.stop()
        src._reset_runtime_state()
        hugo._reset_runtime_state()
        cache.set_cache_directory(None)
        self._temp.cleanup()

    def _lookup(
        self,
        pages,
        title,
        author,
        utc_year=2025,
        discover=None,
    ):
        tracker = _HttpTracker(pages)
        fetch_patch = patch.object(src, '_fetch_response', tracker.fetch_response)
        year_patch = patch.object(
            src, '_current_calendar_year', return_value=utc_year
        )
        discover_patch = (
            patch.object(src, '_discover_future_year_urls', side_effect=discover)
            if discover is not None
            else None
        )
        with fetch_patch, year_patch:
            if discover_patch is not None:
                with discover_patch:
                    results = src.lookup(title, author)
            else:
                results = src.lookup(title, author)
        return results, tracker

    def test_cold_historical_fill_uses_validated_year_map(self):
        results, tracker = self._lookup(
            _completed_pages(), 'Misery', 'Stephen King'
        )
        self.assertEqual(results[0].status, 'Winner')
        self.assertEqual(results[0].award_year, 1987)
        self.assertEqual(set(tracker.calls), set(_fixture_year_urls().values()))
        self.assertEqual(len(tracker.calls), 4)
        self.assertTrue(
            any(
                src.HISTORICAL_CENSUS_PATHS[2022] in url
                for url in tracker.calls
            )
        )
        self.assertFalse(any('preliminary' in url for url in tracker.calls))
        self.assertFalse(any('wp-json' in url for url in tracker.calls))

    def test_fresh_historical_cache_is_zero_http(self):
        _seed_completed_disk()
        results, tracker = self._lookup(
            {}, 'The Traveling Vampire Show', 'Richard Laymon'
        )
        self.assertEqual(tracker.calls, [])
        self.assertEqual(results[0].status, 'Winner')
        self.assertEqual(results[0].award_year, 2000)

    def test_ram_reset_fresh_disk_is_zero_http(self):
        _seed_completed_disk()
        src._reset_runtime_state()
        results, tracker = self._lookup(
            {}, 'The Buffalo Hunter Hunter', 'Stephen Graham Jones'
        )
        self.assertEqual(tracker.calls, [])
        self.assertEqual(results[0].award_year, 2025)

    def test_completed_year_ttl_is_180_days(self):
        self.assertEqual(src.HISTORICAL_CACHE_TTL_SECONDS, 180 * 24 * 60 * 60)
        self.assertEqual(
            src._year_ttl_seconds('winner'),
            src.HISTORICAL_CACHE_TTL_SECONDS,
        )

    def test_current_finalist_and_absent_ttl_is_7_days_plus_16h(self):
        self.assertEqual(src.CURRENT_CACHE_REFRESH_OFFSET_SECONDS, 16 * 60 * 60)
        self.assertEqual(
            src.CURRENT_CACHE_TTL_SECONDS,
            7 * 24 * 60 * 60 + 16 * 60 * 60,
        )
        self.assertEqual(
            src._year_ttl_seconds('finalist'),
            src.CURRENT_CACHE_TTL_SECONDS,
        )
        self.assertEqual(
            src._year_ttl_seconds('absent'),
            src.CURRENT_CACHE_TTL_SECONDS,
        )

    def test_stale_current_year_claims_one_refresh(self):
        _seed_completed_disk()
        _save_year(
            _year_snapshot(2025),
            generated_at=_STALE_AT,
            ttl_seconds=60,
        )
        with cache.lookup_refresh_budget():
            results, tracker = self._lookup(
                _completed_pages(),
                'The Buffalo Hunter Hunter',
                'Stephen Graham Jones',
            )
        self.assertEqual(results[0].status, 'Winner')
        self.assertEqual(tracker.calls, [_census(2025)])

    def test_stale_historical_year_claims_at_most_one_refresh(self):
        _seed_completed_disk()
        _save_year(
            _year_snapshot(1987),
            generated_at=_STALE_AT,
            ttl_seconds=60,
        )
        _save_year(
            _year_snapshot(2000),
            generated_at=_STALE_AT,
            ttl_seconds=60,
        )
        with cache.lookup_refresh_budget():
            results, tracker = self._lookup(
                _completed_pages(), 'Misery', 'Stephen King'
            )
        self.assertEqual(results[0].status, 'Winner')
        self.assertEqual(len(tracker.calls), 1)
        self.assertIn(tracker.calls[0], {_census(1987), _census(2000)})

    def test_slot_denied_uses_stale_zero_http(self):
        _seed_completed_disk()
        _save_year(
            _year_snapshot(2025),
            generated_at=_STALE_AT,
            ttl_seconds=60,
        )
        with cache.lookup_refresh_budget():
            self.assertTrue(cache.try_claim_stale_refresh())
            results, tracker = self._lookup(
                {_census(2025): 'FAIL'},
                'Witchcraft for Wayward Girls',
                'Grady Hendrix',
            )
        self.assertEqual(tracker.calls, [])
        self.assertEqual(results[0].award_year, 2025)

    def test_stale_refresh_failure_preserves_stale(self):
        _seed_completed_disk()
        _save_year(
            _year_snapshot(2025),
            generated_at=_STALE_AT,
            ttl_seconds=60,
        )
        pages = _completed_pages()
        pages[_census(2025)] = 'FAIL'
        with cache.lookup_refresh_budget():
            results, tracker = self._lookup(
                pages, 'The Buffalo Hunter Hunter', 'Stephen Graham Jones'
            )
        self.assertEqual(tracker.calls, [_census(2025)])
        self.assertEqual(results[0].status, 'Winner')
        payload = cache.load_cache_entry(
            src.SOURCE_KEY, src.YEAR_ENTRY_KIND, '2025', src.YEAR_CACHE_VERSION
        )
        self.assertEqual(
            payload['generated_at'],
            _STALE_AT.isoformat().replace('+00:00', 'Z'),
        )

    def test_malformed_version_mismatch_is_required_live(self):
        _seed_completed_disk()
        _save_year(_year_snapshot(2025), version=99)
        results, tracker = self._lookup(
            _completed_pages(),
            'The Buffalo Hunter Hunter',
            'Stephen Graham Jones',
        )
        self.assertIn(_census(2025), tracker.calls)
        self.assertEqual(results[0].status, 'Winner')

    def test_one_broken_year_does_not_invalidate_siblings(self):
        pages = _completed_pages()
        pages[_census(2000)] = 'FAIL'
        results, tracker = self._lookup(pages, 'Misery', 'Stephen King')
        self.assertTrue(results)
        self.assertEqual(results[0].award_year, 1987)
        sibling = cache.load_cache_entry(
            src.SOURCE_KEY, src.YEAR_ENTRY_KIND, '1987', src.YEAR_CACHE_VERSION
        )
        self.assertIsNotNone(sibling)
        self.assertIsNone(
            cache.load_cache_entry(
                src.SOURCE_KEY, src.YEAR_ENTRY_KIND, '2000', src.YEAR_CACHE_VERSION
            )
        )
        self.assertIn(_census(2000), tracker.calls)

    def test_2022_uses_complete_final_ballot_census(self):
        results, tracker = self._lookup(
            _completed_pages(), 'The Fervor', 'Alma Katsu'
        )
        self.assertEqual(results[0].status, 'Finalist')
        self.assertEqual(results[0].award_year, 2022)
        self.assertTrue(
            any('final-ballot' in url for url in tracker.calls)
        )
        payload = cache.load_cache_entry(
            src.SOURCE_KEY, src.YEAR_ENTRY_KIND, '2022', src.YEAR_CACHE_VERSION
        )
        titles = [item['work_title'] for item in payload['records']]
        self.assertIn('The Fervor', titles)
        self.assertIn('The Devil Takes You Home', titles)
        self.assertGreater(
            sum(1 for item in payload['records'] if item['status'] == 'Finalist'),
            1,
        )

    def test_no_preliminary_recommendation_or_excluded_categories_persisted(self):
        _results, tracker = self._lookup(
            _completed_pages(), 'Misery', 'Stephen King'
        )
        self.assertNotIn(_PRELIM_2025, tracker.calls)
        for year in _FIXTURE_YEARS:
            payload = cache.load_cache_entry(
                src.SOURCE_KEY,
                src.YEAR_ENTRY_KIND,
                str(year),
                src.YEAR_CACHE_VERSION,
            )
            blob = str(payload).casefold()
            self.assertNotIn('html', payload)
            self.assertNotIn('<div', blob)
            self.assertNotIn('<h3', blob)
            self.assertNotIn('preliminary', blob)
            self.assertNotIn('recommendation', blob)
            self.assertNotIn('reading list', blob)
            self.assertNotIn('sinners', blob)
            self.assertNotIn('lifetime achievement', blob)
            self.assertNotIn('specialty press', blob)
            self.assertNotIn('silver hammer', blob)
            self.assertNotIn("president's award", blob)
            self.assertNotIn('mentor of the year', blob)
            self.assertNotIn('bat eater', blob)
            statuses = {item['status'] for item in payload['records']}
            self.assertTrue(statuses <= {'Winner', 'Finalist'})
            categories = {item['category'] for item in payload['records']}
            self.assertNotIn('Screenplay', categories)

    def test_cross_category_duplicate_survives_serialization(self):
        self._lookup(_completed_pages(), 'Misery', 'Stephen King')
        payload = cache.load_cache_entry(
            src.SOURCE_KEY, src.YEAR_ENTRY_KIND, '2000', src.YEAR_CACHE_VERSION
        )
        club = [
            item for item in payload['records']
            if item['work_title'] == 'The Licking Valley Coon Hunters Club'
        ]
        self.assertEqual(
            {(item['category'], item['status']) for item in club},
            {('Novel', 'Finalist'), ('First Novel', 'Winner')},
        )
        src._reset_runtime_state()
        results, tracker = self._lookup(
            {},
            'The Licking Valley Coon Hunters Club',
            'Brian A. Hopkins',
        )
        self.assertEqual(tracker.calls, [])
        self.assertEqual(
            {(item.category, item.status) for item in results},
            {('Novel', 'Finalist'), ('First Novel', 'Winner')},
        )

    def test_multiple_winner_tie_survives_serialization(self):
        self._lookup(_completed_pages(), 'Misery', 'Stephen King')
        payload = cache.load_cache_entry(
            src.SOURCE_KEY, src.YEAR_ENTRY_KIND, '1987', src.YEAR_CACHE_VERSION
        )
        novel_winners = [
            item for item in payload['records']
            if item['category'] == 'Novel' and item['status'] == 'Winner'
        ]
        self.assertEqual(
            {item['work_title'] for item in novel_winners},
            {'Misery', 'Swan Song'},
        )
        src._reset_runtime_state()
        results, tracker = self._lookup({}, 'Misery', 'Stephen King')
        self.assertEqual(tracker.calls, [])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, 'Winner')
        swan, _tracker = self._lookup({}, 'Swan Song', 'Robert R. McCammon')
        self.assertEqual(swan[0].status, 'Winner')

    def test_manual_refresh_clears_index_years_and_ram_zero_http(self):
        _seed_completed_disk()
        src._store_index_snapshot(_index_snapshot())
        src._store_year_snapshot(_year_snapshot(2025))
        cache.save_source_cache(
            'hugo',
            1,
            records=[{'title': 'sibling'}],
            source_urls=['https://example.test/h'],
            coverage={'source': 'hugo'},
            ttl_seconds=3600,
        )
        with patch.object(src, '_fetch_response') as fetch:
            self.assertTrue(refresh_award_source_cache('bram_stoker'))
            fetch.assert_not_called()
        self.assertIsNone(src._ram_index())
        self.assertIsNone(src._ram_year(2025))
        self.assertIsNone(
            cache.load_cache_entry(
                src.SOURCE_KEY, src.INDEX_ENTRY_KIND, src.INDEX_ENTRY_KEY, 1
            )
        )
        self.assertIsNone(
            cache.load_cache_entry(src.SOURCE_KEY, src.YEAR_ENTRY_KIND, '2025', 1)
        )
        self.assertFalse(_entry_path(self.cache_dir, 'index', 'years').exists())
        self.assertIsNotNone(cache.load_source_cache('hugo', 1))

    def test_2026_preliminary_only_is_absent(self):
        pages = _completed_pages()
        pages[_PRELIM_2026] = _html_preliminary(
            2026,
            'The 2026 Bram Stoker Awards® Preliminary Ballot',
        )
        results, tracker = self._lookup(
            pages,
            'Bat Eater and Other Names for Cora Zeng',
            'Kylie Lee Baker',
            utc_year=2026,
            discover=lambda year: (None, None),
        )
        self.assertEqual(results, [])
        self.assertNotIn(_PRELIM_2026, tracker.calls)
        self.assertIsNone(
            cache.load_cache_entry(
                src.SOURCE_KEY, src.YEAR_ENTRY_KIND, '2026', src.YEAR_CACHE_VERSION
            )
        )

    def test_2026_final_ballot_is_finalist_short_ttl(self):
        pages = _completed_pages()
        pages[_BALLOT_2026] = _html_2026_ballot(winners=False)
        results, tracker = self._lookup(
            pages,
            'Second Book',
            'Two Author',
            utc_year=2026,
            discover=lambda year: (_BALLOT_2026, None),
        )
        self.assertIn(_BALLOT_2026, tracker.calls)
        self.assertEqual(results[0].status, 'Finalist')
        self.assertEqual(results[0].award_year, 2026)
        payload = cache.load_cache_entry(
            src.SOURCE_KEY, src.YEAR_ENTRY_KIND, '2026', src.YEAR_CACHE_VERSION
        )
        self.assertEqual(payload['coverage']['state'], 'finalist')
        self.assertEqual(payload['ttl_seconds'], src.CURRENT_CACHE_TTL_SECONDS)
        self.assertTrue(all(item['status'] == 'Finalist' for item in payload['records']))

    def test_2026_winners_complete_the_cycle(self):
        pages = _completed_pages()
        pages[_BALLOT_2026] = _html_2026_ballot(winners=True)
        results, _tracker = self._lookup(
            pages,
            'First Book',
            'One Author',
            utc_year=2026,
            discover=lambda year: (_BALLOT_2026, None),
        )
        self.assertEqual(results[0].status, 'Winner')
        payload = cache.load_cache_entry(
            src.SOURCE_KEY, src.YEAR_ENTRY_KIND, '2026', src.YEAR_CACHE_VERSION
        )
        self.assertEqual(payload['coverage']['state'], 'winner')
        self.assertEqual(payload['ttl_seconds'], src.HISTORICAL_CACHE_TTL_SECONDS)
        self.assertIn(
            'Second Book',
            [
                item['work_title']
                for item in payload['records']
                if item['status'] == 'Finalist'
            ],
        )

    def test_2026_winners_only_merges_into_existing_ballot(self):
        pages = _completed_pages()
        pages[_BALLOT_2026] = _html_2026_ballot(winners=False)
        pages[_WINNERS_2026] = _html_2026_winners_only()
        results, tracker = self._lookup(
            pages,
            'Second Book',
            'Two Author',
            utc_year=2026,
            discover=lambda year: (_BALLOT_2026, _WINNERS_2026),
        )
        self.assertIn(_BALLOT_2026, tracker.calls)
        self.assertIn(_WINNERS_2026, tracker.calls)
        self.assertEqual(results[0].status, 'Finalist')
        winner, _tracker = self._lookup(
            pages,
            'First Book',
            'One Author',
            utc_year=2026,
            discover=lambda year: (_BALLOT_2026, _WINNERS_2026),
        )
        self.assertEqual(winner[0].status, 'Winner')
        payload = cache.load_cache_entry(
            src.SOURCE_KEY, src.YEAR_ENTRY_KIND, '2026', src.YEAR_CACHE_VERSION
        )
        self.assertEqual(payload['coverage']['state'], 'winner')
        titles = {item['work_title'] for item in payload['records']}
        self.assertIn('Second Book', titles)
        self.assertIn('First Book', titles)


if __name__ == '__main__':
    unittest.main()
