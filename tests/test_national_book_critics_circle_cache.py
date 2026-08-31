"""Offline coverage for National Book Critics Circle keyed year cache."""

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
from awards.sources import hugo, national_book_critics_circle as nbcc
from tests.test_national_book_critics_circle_parser import (
    _classic_core,
    _core_1975,
    _modern_core,
    _modern_li,
    _modern_list,
    _page,
    _url,
)

_UTC = timezone.utc
_STALE_AT = datetime(2020, 1, 1, tzinfo=_UTC)


def _entry_path(cache_dir: Path, entry_kind: str, entry_key: str) -> Path:
    digest = hashlib.sha256(entry_key.encode('utf-8')).hexdigest()
    return cache_dir / nbcc.SOURCE_KEY / entry_kind / f'{digest}.json'


def _index_json(years) -> str:
    return json.dumps(
        [
            {'slug': str(year), 'link': _url(year)}
            for year in years
        ]
    )


class _HttpTracker:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def fetch_response(self, url: str):
        self.calls.append(url)
        body = self.pages.get(url)
        if body == 'FAIL':
            raise nbcc.NationalBookCriticsCircleSourceError(f'HTTP failed for {url}')
        if body == '404' or body is None:
            return 404, ''
        if isinstance(body, tuple):
            return body
        return 200, body


def _save_index(years, *, generated_at=None, ttl_seconds=None, version=None):
    cache.save_cache_entry(
        nbcc.SOURCE_KEY,
        nbcc.INDEX_ENTRY_KIND,
        nbcc.INDEX_ENTRY_KEY,
        nbcc.INDEX_CACHE_VERSION if version is None else version,
        records=[{'award_year': year} for year in years],
        source_urls=[nbcc.YEAR_INDEX_URL],
        coverage=nbcc._index_coverage(tuple(years)),
        ttl_seconds=(
            nbcc.CURRENT_CACHE_TTL_SECONDS if ttl_seconds is None else ttl_seconds
        ),
        generated_at=generated_at,
    )


def _save_year(snapshot, *, generated_at=None, ttl_seconds=None, version=None):
    source_urls = [snapshot.source_url] if snapshot.source_url else []
    cache.save_cache_entry(
        nbcc.SOURCE_KEY,
        nbcc.YEAR_ENTRY_KIND,
        nbcc._year_entry_key(snapshot.award_year),
        nbcc.YEAR_CACHE_VERSION if version is None else version,
        records=[nbcc._record_to_cache_dict(record) for record in snapshot.records],
        source_urls=source_urls,
        coverage=nbcc._year_coverage(snapshot.award_year, snapshot.state),
        ttl_seconds=(
            nbcc._year_ttl_seconds(snapshot.state)
            if ttl_seconds is None
            else ttl_seconds
        ),
        generated_at=generated_at,
    )


def _completed_1975():
    html = _page(1975, _core_1975())
    records, _saw = nbcc._parse_year_html(html, 1975, _url(1975))
    return nbcc._YearSnapshot(
        award_year=1975,
        state='completed',
        source_url=_url(1975),
        records=records,
    )


def _completed_1976():
    html = _page(1976, _classic_core())
    records, _saw = nbcc._parse_year_html(html, 1976, _url(1976))
    return nbcc._YearSnapshot(
        award_year=1976,
        state='completed',
        source_url=_url(1976),
        records=records,
    )


def _completed_modern(year):
    html = _page(year, _modern_core(), modern=True)
    records, _saw = nbcc._parse_year_html(html, year, _url(year))
    return nbcc._YearSnapshot(
        award_year=year,
        state='completed',
        source_url=_url(year),
        records=records,
    )


def _seed_index_through(max_year):
    years = [1975] if max_year == 1975 else [1975, max_year]
    _save_index(years)
    _save_year(_completed_1975())
    if max_year >= 2017:
        _save_year(_completed_modern(max_year))
    elif max_year == 1976:
        _save_year(_completed_1976())


class NbccCacheTests(unittest.TestCase):
    def setUp(self):
        self._temp = TemporaryDirectory()
        self.cache_dir = Path(self._temp.name)
        cache.set_cache_directory(self.cache_dir)
        nbcc._reset_runtime_state()
        hugo._reset_runtime_state()

    def tearDown(self):
        nbcc._reset_runtime_state()
        hugo._reset_runtime_state()
        cache.set_cache_directory(None)
        self._temp.cleanup()

    def _lookup(self, pages, title, author, *, calendar=1976):
        tracker = _HttpTracker(pages)
        with patch.object(nbcc, '_current_calendar_year', return_value=calendar):
            with patch.object(nbcc, '_fetch_response', side_effect=tracker.fetch_response):
                results = nbcc.lookup(title, author)
        return results, tracker

    def test_cold_historical_year_one_get_plus_index(self):
        pages = {
            nbcc.YEAR_INDEX_URL: _index_json([1975]),
            _url(1975): _page(1975, _core_1975()),
        }
        results, tracker = self._lookup(pages, 'Ragtime', 'E.L. Doctorow', calendar=1975)
        self.assertEqual(results[0].status, 'Winner')
        self.assertEqual(
            tracker.calls,
            [nbcc.YEAR_INDEX_URL, _url(1975)],
        )

    def test_fresh_historical_zero_http(self):
        snapshot = _completed_1975()
        _save_index([1975])
        _save_year(snapshot)
        pages = {nbcc.YEAR_INDEX_URL: 'FAIL', _url(1975): 'FAIL'}
        results, tracker = self._lookup(pages, 'Ragtime', 'E.L. Doctorow', calendar=1975)
        self.assertEqual(results[0].work_title, 'Ragtime')
        self.assertEqual(tracker.calls, [])

    def test_ram_reset_fresh_disk_zero_http(self):
        snapshot = _completed_1975()
        _save_index([1975])
        _save_year(snapshot)
        nbcc._reset_runtime_state()
        pages = {nbcc.YEAR_INDEX_URL: 'FAIL', _url(1975): 'FAIL'}
        results, tracker = self._lookup(pages, 'Ragtime', 'E.L. Doctorow', calendar=1975)
        self.assertEqual(len(results), 1)
        self.assertEqual(tracker.calls, [])

    def test_stale_completed_slot_won_refreshes_one_year(self):
        snapshot = _completed_1975()
        _save_index([1975, 1976])
        _save_year(snapshot, generated_at=_STALE_AT)
        _save_year(_completed_1976(), generated_at=_STALE_AT)
        pages = {
            _url(1975): _page(1975, _core_1975()),
            _url(1976): 'FAIL',
        }
        with cache.lookup_refresh_budget():
            results, tracker = self._lookup(
                pages,
                'Ragtime',
                'E.L. Doctorow',
                calendar=1976,
            )
        self.assertEqual(results[0].status, 'Winner')
        self.assertEqual(tracker.calls, [_url(1975)])

    def test_stale_completed_slot_denied_zero_http(self):
        _save_index([1975])
        _save_year(_completed_1975(), generated_at=_STALE_AT)
        pages = {_url(1975): 'FAIL'}
        with cache.lookup_refresh_budget():
            self.assertTrue(cache.try_claim_stale_refresh())
            results, tracker = self._lookup(
                pages,
                'Ragtime',
                'E.L. Doctorow',
                calendar=1975,
            )
        self.assertEqual(results[0].work_title, 'Ragtime')
        self.assertEqual(tracker.calls, [])

    def test_stale_refresh_failure_keeps_stale(self):
        _save_index([1975])
        _save_year(_completed_1975(), generated_at=_STALE_AT)
        path = _entry_path(self.cache_dir, nbcc.YEAR_ENTRY_KIND, '1975')
        before = path.read_text(encoding='utf-8')
        pages = {_url(1975): 'FAIL'}
        with cache.lookup_refresh_budget():
            results, tracker = self._lookup(
                pages,
                'Ragtime',
                'E.L. Doctorow',
                calendar=1975,
            )
        self.assertEqual(results[0].work_title, 'Ragtime')
        self.assertEqual(tracker.calls, [_url(1975)])
        self.assertEqual(path.read_text(encoding='utf-8'), before)

    def test_missing_historical_required_get(self):
        _save_index([1975])
        pages = {_url(1975): _page(1975, _core_1975())}
        results, tracker = self._lookup(pages, 'Ragtime', 'E.L. Doctorow', calendar=1975)
        self.assertEqual(len(results), 1)
        self.assertEqual(tracker.calls, [_url(1975)])

    def test_malformed_historical_live(self):
        _save_index([1975])
        cache.save_cache_entry(
            nbcc.SOURCE_KEY,
            nbcc.YEAR_ENTRY_KIND,
            '1975',
            nbcc.YEAR_CACHE_VERSION,
            records=[{'bad': True}],
            source_urls=[_url(1975)],
            coverage={'award_year': 1975, 'state': 'completed'},
            ttl_seconds=nbcc.HISTORICAL_YEAR_CACHE_TTL_SECONDS,
        )
        pages = {_url(1975): _page(1975, _core_1975())}
        results, tracker = self._lookup(pages, 'Ragtime', 'E.L. Doctorow', calendar=1975)
        self.assertEqual(len(results), 1)
        self.assertEqual(tracker.calls, [_url(1975)])

    def test_version_mismatch_live(self):
        _save_index([1975])
        _save_year(_completed_1975(), version=99)
        pages = {_url(1975): _page(1975, _core_1975())}
        results, tracker = self._lookup(pages, 'Ragtime', 'E.L. Doctorow', calendar=1975)
        self.assertEqual(len(results), 1)
        self.assertEqual(tracker.calls, [_url(1975)])

    def test_wrong_identity_does_not_save(self):
        _save_index([1975])
        html = _page(1975, _core_1975()).replace(
            'National Book Critics Circle',
            'Some Other Circle',
        )
        pages = {_url(1975): html}
        results, tracker = self._lookup(pages, 'Ragtime', 'E.L. Doctorow', calendar=1975)
        self.assertEqual(results, [])
        self.assertFalse(
            _entry_path(self.cache_dir, nbcc.YEAR_ENTRY_KIND, '1975').exists()
        )
        self.assertEqual(tracker.calls, [_url(1975)])

    def test_non_work_category_list_not_saved_as_completed_records(self):
        _save_index([1975])
        html = _page(
            1975,
            '<h3>Winners</h3><ul><li>Ivan Sandrof: Frances FitzGerald</li></ul>',
        )
        pages = {_url(1975): html}
        results, _tracker = self._lookup(
            pages,
            'Frances FitzGerald',
            'Frances FitzGerald',
            calendar=1975,
        )
        self.assertEqual(results, [])
        self.assertFalse(
            _entry_path(self.cache_dir, nbcc.YEAR_ENTRY_KIND, '1975').exists()
        )

    def test_indexed_historical_404_is_failure_not_absent(self):
        _save_index([1975])
        pages = {_url(1975): '404'}
        results, _tracker = self._lookup(pages, 'Ragtime', 'E.L. Doctorow', calendar=1975)
        self.assertEqual(results, [])
        loaded = cache.load_cache_entry(
            nbcc.SOURCE_KEY,
            nbcc.YEAR_ENTRY_KIND,
            '1975',
            nbcc.YEAR_CACHE_VERSION,
        )
        self.assertIsNone(loaded)

    def test_current_2026_404_absent_cache(self):
        _seed_index_through(2025)
        pages = {_url(2026): '404'}
        results, tracker = self._lookup(
            pages,
            'Ragtime',
            'E.L. Doctorow',
            calendar=2026,
        )
        self.assertEqual(results[0].work_title, 'Ragtime')
        self.assertIn(_url(2026), tracker.calls)
        payload = cache.load_cache_entry(
            nbcc.SOURCE_KEY,
            nbcc.YEAR_ENTRY_KIND,
            '2026',
            nbcc.YEAR_CACHE_VERSION,
        )
        self.assertEqual(payload['coverage']['state'], 'absent')
        self.assertEqual(payload['records'], [])
        self.assertEqual(payload['ttl_seconds'], nbcc.CURRENT_CACHE_TTL_SECONDS)

    def test_fresh_absent_zero_http(self):
        _seed_index_through(2025)
        _save_year(
            nbcc._YearSnapshot(
                award_year=2026,
                state='absent',
                source_url='',
                records=(),
            )
        )
        pages = {_url(2026): 'FAIL'}
        _results, tracker = self._lookup(
            pages,
            'Ragtime',
            'E.L. Doctorow',
            calendar=2026,
        )
        self.assertEqual(tracker.calls, [])

    def test_stale_absent_optional_refresh(self):
        _seed_index_through(2025)
        _save_year(
            nbcc._YearSnapshot(
                award_year=2026,
                state='absent',
                source_url='',
                records=(),
            ),
            generated_at=_STALE_AT,
        )
        pages = {_url(2026): '404'}
        with cache.lookup_refresh_budget():
            _results, tracker = self._lookup(
                pages,
                'Ragtime',
                'E.L. Doctorow',
                calendar=2026,
            )
        self.assertEqual(tracker.calls, [_url(2026)])

    def test_in_progress_short_ttl_completed_180d(self):
        in_progress_html = _page(
            2026,
            _modern_list(
                'Fiction',
                _modern_li('Finalist', 'Karen Russell', 'The Antidote'),
            ),
            modern=True,
        )
        _seed_index_through(2025)
        pages = {_url(2026): in_progress_html}
        _results, _tracker = self._lookup(
            pages,
            'The Antidote',
            'Karen Russell',
            calendar=2026,
        )
        payload = cache.load_cache_entry(
            nbcc.SOURCE_KEY,
            nbcc.YEAR_ENTRY_KIND,
            '2026',
            nbcc.YEAR_CACHE_VERSION,
        )
        self.assertEqual(payload['coverage']['state'], 'in_progress')
        self.assertEqual(payload['ttl_seconds'], nbcc.CURRENT_CACHE_TTL_SECONDS)
        completed = cache.load_cache_entry(
            nbcc.SOURCE_KEY,
            nbcc.YEAR_ENTRY_KIND,
            '1975',
            nbcc.YEAR_CACHE_VERSION,
        )
        self.assertEqual(
            completed['ttl_seconds'],
            nbcc.HISTORICAL_YEAR_CACHE_TTL_SECONDS,
        )

    def test_in_progress_later_winners_refresh_to_completed(self):
        _save_index([1975, 2025])
        _save_year(_completed_1975())
        _save_year(
            nbcc._YearSnapshot(
                award_year=2025,
                state='in_progress',
                source_url=_url(2025),
                records=(),
            ),
            generated_at=_STALE_AT,
            ttl_seconds=nbcc.CURRENT_CACHE_TTL_SECONDS,
        )
        pages = {_url(2025): _page(2025, _modern_core(), modern=True)}
        with cache.lookup_refresh_budget():
            results, tracker = self._lookup(
                pages,
                'Improvement',
                'Joan Silber',
                calendar=2025,
            )
        self.assertEqual(results[0].status, 'Winner')
        self.assertEqual(tracker.calls, [_url(2025)])
        payload = cache.load_cache_entry(
            nbcc.SOURCE_KEY,
            nbcc.YEAR_ENTRY_KIND,
            '2025',
            nbcc.YEAR_CACHE_VERSION,
        )
        self.assertEqual(payload['coverage']['state'], 'completed')
        self.assertEqual(
            payload['ttl_seconds'],
            nbcc.HISTORICAL_YEAR_CACHE_TTL_SECONDS,
        )

    def test_per_year_independence_and_failed_year(self):
        _save_index([1975, 1976])
        _save_year(_completed_1975())
        pages = {_url(1976): 'FAIL'}
        results, _tracker = self._lookup(
            pages,
            'Ragtime',
            'E.L. Doctorow',
            calendar=1976,
        )
        self.assertEqual(results[0].work_title, 'Ragtime')
        self.assertTrue(
            _entry_path(self.cache_dir, nbcc.YEAR_ENTRY_KIND, '1975').exists()
        )
        self.assertFalse(
            _entry_path(self.cache_dir, nbcc.YEAR_ENTRY_KIND, '1976').exists()
        )

    def test_no_raw_html_longlist_or_honors_or_translators_persisted(self):
        extras = (
            _modern_list(
                'Fiction',
                _modern_li('Longlist', 'Lily King', 'Heart the Lover', 'Grove')
                + _modern_li(
                    'Winner',
                    'Han Kang, translated from the Korean by e. yaewon and Paige Aniyah Morris',
                    'We Do Not Part',
                    'Hogarth',
                ),
            )
            + _modern_list(
                'Ivan Sandrof Lifetime Achievement Award',
                '<li class="Winner">Frances FitzGerald</li>',
            )
        )
        html = _page(2025, _modern_core(extras=extras), modern=True)
        _save_index([1975, 2025])
        _save_year(_completed_1975())
        pages = {_url(2025): html}
        results, _tracker = self._lookup(
            pages,
            'We Do Not Part',
            'Han Kang',
            calendar=2025,
        )
        self.assertEqual(results[0].work_author, 'Han Kang')
        raw = _entry_path(
            self.cache_dir, nbcc.YEAR_ENTRY_KIND, '2025'
        ).read_text(encoding='utf-8')
        self.assertNotIn('<li', raw)
        self.assertNotIn('Heart the Lover', raw)
        self.assertNotIn('Frances FitzGerald', raw)
        self.assertNotIn('e. yaewon', raw)
        payload = json.loads(raw)
        statuses = {item['status'] for item in payload['records']}
        self.assertEqual(statuses, {'Winner'})
        authors = {item['work_author'] for item in payload['records']}
        self.assertNotIn('Lily King', authors)

    def test_manual_refresh_clears_keyed_entries_ram_and_is_zero_http(self):
        _save_index([1975])
        _save_year(_completed_1975())
        cache.save_source_cache(
            hugo.SOURCE_KEY,
            hugo.CACHE_VERSION,
            records=[],
            source_urls=[hugo._archive_url()],
            coverage={'kind': 'archive'},
            ttl_seconds=hugo.CACHE_TTL_SECONDS,
        )
        hugo._archive_records_cache = ()
        pages = {
            nbcc.YEAR_INDEX_URL: 'FAIL',
            _url(1975): 'FAIL',
        }
        tracker = _HttpTracker(pages)
        with patch.object(nbcc, '_fetch_response', side_effect=tracker.fetch_response):
            self.assertTrue(refresh_award_source_cache(nbcc.SOURCE_KEY))
        self.assertEqual(tracker.calls, [])
        self.assertIsNone(
            cache.load_cache_entry(
                nbcc.SOURCE_KEY,
                nbcc.INDEX_ENTRY_KIND,
                nbcc.INDEX_ENTRY_KEY,
                nbcc.INDEX_CACHE_VERSION,
            )
        )
        self.assertIsNone(
            cache.load_cache_entry(
                nbcc.SOURCE_KEY,
                nbcc.YEAR_ENTRY_KIND,
                '1975',
                nbcc.YEAR_CACHE_VERSION,
            )
        )
        self.assertIsNone(nbcc._index_years_cache)
        self.assertEqual(nbcc._year_snapshot_cache, {})
        self.assertTrue((self.cache_dir / 'hugo.json').is_file())
        self.assertEqual(hugo._archive_records_cache, ())

    def test_rest_index_discovers_1975_through_listed_years_not_1974(self):
        years = list(range(1975, 2026))
        tracker = _HttpTracker({nbcc.YEAR_INDEX_URL: _index_json(years)})
        with patch.object(nbcc, '_fetch_response', side_effect=tracker.fetch_response):
            discovered = nbcc._get_index_years()
        self.assertEqual(discovered[0], 1975)
        self.assertEqual(discovered[-1], 2025)
        self.assertNotIn(1974, discovered)
        self.assertEqual(len(discovered), 51)
        self.assertEqual(tracker.calls, [nbcc.YEAR_INDEX_URL])

    def test_future_indexed_finalists_only_in_progress_then_completed(self):
        _save_index([1975, 2026])
        _save_year(_completed_1975())
        pages = {
            _url(2026): _page(
                2026,
                _modern_list(
                    'Fiction',
                    _modern_li('Finalist', 'Karen Russell', 'The Antidote'),
                ),
                modern=True,
            )
        }
        _results, _tracker = self._lookup(
            pages,
            'The Antidote',
            'Karen Russell',
            calendar=2026,
        )
        payload = cache.load_cache_entry(
            nbcc.SOURCE_KEY,
            nbcc.YEAR_ENTRY_KIND,
            '2026',
            nbcc.YEAR_CACHE_VERSION,
        )
        self.assertEqual(payload['coverage']['state'], 'in_progress')
        nbcc._reset_runtime_state()
        _save_year(
            nbcc._snapshot_from_payload(payload, 2026, indexed=True),
            generated_at=_STALE_AT,
            ttl_seconds=nbcc.CURRENT_CACHE_TTL_SECONDS,
        )
        pages = {_url(2026): _page(2026, _modern_core(), modern=True)}
        with cache.lookup_refresh_budget():
            results, tracker = self._lookup(
                pages,
                'Improvement',
                'Joan Silber',
                calendar=2026,
            )
        self.assertEqual(results[0].status, 'Winner')
        self.assertEqual(tracker.calls, [_url(2026)])
        later = cache.load_cache_entry(
            nbcc.SOURCE_KEY,
            nbcc.YEAR_ENTRY_KIND,
            '2026',
            nbcc.YEAR_CACHE_VERSION,
        )
        self.assertEqual(later['coverage']['state'], 'completed')


if __name__ == '__main__':
    unittest.main()
