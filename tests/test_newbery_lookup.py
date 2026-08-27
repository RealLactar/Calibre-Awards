"""Offline coverage for Newbery archive fetch, validation, cache, and lookup."""

from __future__ import annotations

import io
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from awards.sources import newbery
from awards.sources.newbery import (
    ARCHIVE_MAX_YEAR,
    ARCHIVE_MIN_YEAR,
    ARCHIVE_URL_1930_1991,
    ARCHIVE_URL_1992_2003,
    ARCHIVE_URL_2004_2023,
    NewberySourceError,
    _authors_match,
)

CRISPIN_URL = 'https://www.ala.org/winner/crispin-cross-lead'
ATUAN_URL = 'https://www.ala.org/winner/tombs-atuan'
SMITH_URL = 'https://www.ala.org/winner/smith-jones'
SHARED_A_URL = 'https://www.ala.org/winner/shared-title-a'
SHARED_B_URL = 'https://www.ala.org/winner/shared-title-b'
FUTURE_URL = 'https://www.ala.org/winner/future-book'


def _listing_row(title: str, year: int, status: str, slug: str) -> str:
    return (
        '<tr>'
        f'<td class="views-field-title-1">'
        f'<a href="/winner/{slug}">{title}</a></td>'
        f'<td class="views-field-field-winner-rank">'
        f'{year} - {status}(s)</td>'
        '</tr>'
    )


def _year_html(
    year: int,
    winner_title: str,
    winner_slug: str,
    honors: tuple[tuple[str, str], ...] = (),
    *,
    include_winner: bool = True,
    extra_winner: tuple[str, str] | None = None,
) -> str:
    rows: list[str] = []
    if include_winner:
        rows.append(_listing_row(winner_title, year, 'Winner', winner_slug))
    if extra_winner is not None:
        rows.append(
            _listing_row(extra_winner[0], year, 'Winner', extra_winner[1])
        )
    for honor_title, honor_slug in honors:
        rows.append(_listing_row(honor_title, year, 'Honor', honor_slug))
    return (
        '<div class="accordion-item">'
        f'<h3 class="accordion-item__heading"><button>{year}</button></h3>'
        '<table class="views-table"><thead><tr>'
        '<th class="views-field-title-1">Title</th>'
        '<th class="views-field-field-winner-rank">Year</th>'
        f'</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
    )


def _default_year(year: int) -> str:
    return _year_html(year, f'Archive Winner {year}', f'archive-winner-{year}')


def _page_html(
    start: int,
    end: int,
    *,
    skip_years: frozenset[int] = frozenset(),
    replacements: dict[int, str] | None = None,
    extra_html: str = '',
) -> str:
    replacements = replacements or {}
    sections: list[str] = []
    for year in range(start, end + 1):
        if year in skip_years:
            continue
        sections.append(replacements.get(year, _default_year(year)))
    return (
        '<div class="view view-winners-opportunities">'
        + ''.join(sections)
        + extra_html
        + '</div>'
    )


def _detail_page(title: str, byline: str | None, body: str = 'About the book.') -> str:
    byline_html = f'<p>{byline}</p>' if byline is not None else ''
    return (
        f'<h1>{title}</h1>'
        f'<div class="font-bitter text-center">{byline_html}</div>'
        f'<h2>About</h2><p>{body}</p>'
    )


def _valid_archives(*, extra_2024: bool = False) -> dict[str, str]:
    replacements_1930 = {
        1972: _year_html(
            1972,
            'Mrs. Frisby and the Rats of NIMH',
            'mrs-frisby',
            honors=(('The Tombs of Atuan', 'tombs-atuan'),),
        ),
    }
    replacements_1992 = {
        2000: _year_html(
            2000,
            'Smith & Jones',
            'smith-jones',
        ),
        2001: _year_html(
            2001,
            'Shared Title',
            'shared-title-a',
        ),
        2002: _year_html(
            2002,
            'Shared Title',
            'shared-title-b',
        ),
        2003: _year_html(
            2003,
            'Crispin: The Cross of Lead',
            'crispin-cross-lead',
        ),
    }
    extra = ''
    if extra_2024:
        extra = _year_html(2024, 'Future Book', 'future-book')
    return {
        ARCHIVE_URL_1930_1991: _page_html(
            1930, 1991, replacements=replacements_1930
        ),
        ARCHIVE_URL_1992_2003: _page_html(
            1992, 2003, replacements=replacements_1992
        ),
        ARCHIVE_URL_2004_2023: _page_html(
            2004, 2023, extra_html=extra
        ),
    }


def _detail_html(url: str) -> str:
    known = {
        CRISPIN_URL: _detail_page(
            'Crispin: The Cross of Lead',
            'by Avi, and published by Hyperion',
        ),
        ATUAN_URL: _detail_page(
            'The Tombs of Atuan',
            'Written by Ursula K. LeGuin. Published by Atheneum.',
        ),
        SMITH_URL: _detail_page(
            'Smith & Jones',
            'by Pat Author, and published by Example Press',
        ),
        SHARED_A_URL: _detail_page(
            'Shared Title',
            'by Alice Author. Published by One Press.',
        ),
        SHARED_B_URL: _detail_page(
            'Shared Title',
            'by Bob Author. Published by Two Press.',
        ),
        FUTURE_URL: _detail_page(
            'Future Book',
            'by Future Author. Published by Future Press.',
        ),
        'https://www.ala.org/winner/mrs-frisby': _detail_page(
            'Mrs. Frisby and the Rats of NIMH',
            'by Robert C. OBrien. Published by Atheneum.',
        ),
    }
    if url in known:
        return known[url]
    slug = url.rsplit('/', 1)[-1]
    if slug.startswith('archive-winner-'):
        year = slug.rsplit('-', 1)[-1]
        return _detail_page(
            f'Archive Winner {year}',
            f'by Default Author {year}. Published by ALA.',
        )
    raise AssertionError(f'unexpected detail URL {url}')


class _FakeResponse:
    def __init__(self, url: str, status: int, body: str) -> None:
        self._url = url
        self.status = status
        self._body = body.encode('utf-8')

    def getcode(self):
        return self.status

    def read(self):
        return self._body

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class NewberyAuthorMatchingTests(unittest.TestCase):
    def test_exact_normalized_author_matches(self):
        self.assertTrue(_authors_match('Avi', 'Avi'))
        self.assertTrue(_authors_match('ursula k. le guin', 'Ursula K. Le Guin'))

    def test_leguin_alias_matches_spaced_le_guin_both_ways(self):
        self.assertTrue(
            _authors_match('Ursula K. LeGuin', 'Ursula K. Le Guin')
        )
        self.assertTrue(
            _authors_match('Ursula K. Le Guin', 'Ursula K. LeGuin')
        )

    def test_leguin_alias_does_not_match_truncated_or_unrelated_names(self):
        self.assertFalse(_authors_match('Ursula K. LeGuin', 'Ursula Guin'))
        self.assertFalse(_authors_match('Ursula K. LeGuin', 'Ursula K. Guin'))
        self.assertFalse(_authors_match('Ursula K. LeGuin', 'Ursula Le Guin'))
        self.assertFalse(_authors_match('Mary McCarthy', 'Mary Mc Carthy'))
        self.assertFalse(_authors_match('Mary Mc Carthy', 'Mary McCarthy'))

    def test_omitted_middle_name_does_not_match(self):
        self.assertFalse(
            _authors_match('Donna Higuera', 'Donna Barba Higuera')
        )


class NewberyLookupTests(unittest.TestCase):
    def setUp(self):
        newbery._reset_runtime_state()
        self.fetched: list[str] = []
        self.pages = _valid_archives()

    def tearDown(self):
        newbery._reset_runtime_state()

    def _fetch(self, opener, url: str) -> str:
        self.fetched.append(url)
        if url in self.pages:
            return self.pages[url]
        return _detail_html(url)

    def _lookup(self, title: str, author: str):
        with patch.object(newbery, '_fetch_html', side_effect=self._fetch):
            return newbery.lookup(title, author)

    def test_all_three_archive_pages_are_fetched(self):
        results = self._lookup('Crispin: The Cross of Lead', 'Avi')
        self.assertEqual(len(results), 1)
        self.assertEqual(
            self.fetched[:3],
            [
                ARCHIVE_URL_1930_1991,
                ARCHIVE_URL_1992_2003,
                ARCHIVE_URL_2004_2023,
            ],
        )

    def test_required_coverage_succeeds(self):
        self._lookup('Crispin: The Cross of Lead', 'Avi')
        records = newbery._listing_records_cache
        self.assertIsNotNone(records)
        years = {record.award_year for record in records}
        self.assertEqual(
            years,
            set(range(ARCHIVE_MIN_YEAR, ARCHIVE_MAX_YEAR + 1)),
        )
        winners = [
            record for record in records if record.status == 'Winner'
        ]
        self.assertEqual(len(winners), ARCHIVE_MAX_YEAR - ARCHIVE_MIN_YEAR + 1)

    def test_missing_required_year_fails_closed_and_is_not_cached(self):
        self.pages[ARCHIVE_URL_1930_1991] = _page_html(
            1930, 1991, skip_years=frozenset({1980})
        )
        with self.assertRaises(NewberySourceError) as caught:
            self._lookup('Crispin: The Cross of Lead', 'Avi')
        self.assertIn('missing required years', str(caught.exception))
        self.assertIn('1980', str(caught.exception))
        self.assertIsNone(newbery._listing_records_cache)

    def test_year_with_zero_honors_is_valid(self):
        results = self._lookup('Archive Winner 1931', 'Default Author 1931')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, 'Winner')
        honors_1931 = [
            record
            for record in newbery._listing_records_cache
            if record.award_year == 1931 and record.status == 'Honor'
        ]
        self.assertEqual(honors_1931, [])

    def test_year_with_zero_winners_fails_closed(self):
        self.pages[ARCHIVE_URL_1930_1991] = _page_html(
            1930,
            1991,
            replacements={
                1972: _year_html(
                    1972,
                    'The Tombs of Atuan',
                    'tombs-atuan',
                    honors=(('The Tombs of Atuan', 'tombs-atuan'),),
                    include_winner=False,
                )
            },
        )
        with self.assertRaises(NewberySourceError) as caught:
            self._lookup('The Tombs of Atuan', 'Ursula K. Le Guin')
        self.assertIn('no Winner for 1972', str(caught.exception))
        self.assertIsNone(newbery._listing_records_cache)

    def test_year_with_two_winners_fails_closed(self):
        self.pages[ARCHIVE_URL_1992_2003] = _page_html(
            1992,
            2003,
            replacements={
                2003: _year_html(
                    2003,
                    'Crispin: The Cross of Lead',
                    'crispin-cross-lead',
                    extra_winner=('Other Winner', 'other-winner-2003'),
                )
            },
        )
        with self.assertRaises(NewberySourceError) as caught:
            self._lookup('Crispin: The Cross of Lead', 'Avi')
        self.assertIn('2 Winners for 2003', str(caught.exception))
        self.assertIsNone(newbery._listing_records_cache)

    def test_malformed_required_page_is_not_cached(self):
        self.pages[ARCHIVE_URL_2004_2023] = '<p>About the Newbery Medal</p>'
        with self.assertRaises(NewberySourceError):
            self._lookup('Crispin: The Cross of Lead', 'Avi')
        self.assertIsNone(newbery._listing_records_cache)

    def test_http_failure_is_not_cached(self):
        def _fail(opener, url: str) -> str:
            self.fetched.append(url)
            if url == ARCHIVE_URL_1992_2003:
                raise NewberySourceError(
                    f'Newbery request failed with HTTP 500 for {url}'
                )
            if url in self.pages:
                return self.pages[url]
            return _detail_html(url)

        with patch.object(newbery, '_fetch_html', side_effect=_fail):
            with self.assertRaises(NewberySourceError):
                newbery.lookup('Crispin: The Cross of Lead', 'Avi')
        self.assertIsNone(newbery._listing_records_cache)

    def test_successful_archive_is_reused_on_second_lookup(self):
        self._lookup('Crispin: The Cross of Lead', 'Avi')
        first_count = len(self.fetched)
        self._lookup('The Tombs of Atuan', 'Ursula K. Le Guin')
        extra = self.fetched[first_count:]
        self.assertNotIn(ARCHIVE_URL_1930_1991, extra)
        self.assertNotIn(ARCHIVE_URL_1992_2003, extra)
        self.assertNotIn(ARCHIVE_URL_2004_2023, extra)
        self.assertEqual(extra, [ATUAN_URL])

    def test_future_2024_row_does_not_break_or_return(self):
        self.pages = _valid_archives(extra_2024=True)
        results = self._lookup('Future Book', 'Future Author')
        self.assertEqual(results, [])
        self.assertIsNotNone(newbery._listing_records_cache)
        years = {record.award_year for record in newbery._listing_records_cache}
        self.assertNotIn(2024, years)
        self.assertIn(2023, years)
        self.assertNotIn(FUTURE_URL, self.fetched)

    def test_title_miss_fetches_zero_detail_pages(self):
        results = self._lookup('Unrelated Book', 'Some Author')
        self.assertEqual(results, [])
        self.assertEqual(
            self.fetched,
            [
                ARCHIVE_URL_1930_1991,
                ARCHIVE_URL_1992_2003,
                ARCHIVE_URL_2004_2023,
            ],
        )

    def test_one_title_candidate_fetches_only_that_detail_page(self):
        self._lookup('Crispin: The Cross of Lead', 'Avi')
        detail_fetches = [
            url for url in self.fetched if url.startswith('https://www.ala.org/winner/')
        ]
        self.assertEqual(detail_fetches, [CRISPIN_URL])

    def test_multiple_same_title_candidates_are_author_confirmed(self):
        results = self._lookup('Shared Title', 'Bob Author')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].work_author, 'Bob Author')
        self.assertEqual(results[0].award_year, 2002)
        self.assertEqual(results[0].source_url, SHARED_B_URL)
        self.assertEqual(
            [
                url
                for url in self.fetched
                if url.startswith('https://www.ala.org/winner/')
            ],
            [SHARED_A_URL, SHARED_B_URL],
        )

    def test_detail_http_failure_raises(self):
        def _fail_detail(opener, url: str) -> str:
            self.fetched.append(url)
            if url == CRISPIN_URL:
                raise NewberySourceError(
                    f'Newbery request failed with HTTP 500 for {url}'
                )
            if url in self.pages:
                return self.pages[url]
            return _detail_html(url)

        with patch.object(newbery, '_fetch_html', side_effect=_fail_detail):
            with self.assertRaises(NewberySourceError):
                newbery.lookup('Crispin: The Cross of Lead', 'Avi')
        self.assertNotIn(CRISPIN_URL, newbery._detail_author_cache)

    def test_detail_page_without_author_raises_and_is_not_cached(self):
        def _missing_author(opener, url: str) -> str:
            self.fetched.append(url)
            if url == CRISPIN_URL:
                return _detail_page(
                    'Crispin: The Cross of Lead',
                    None,
                    'Starr LaTronica praised the novel.',
                )
            if url in self.pages:
                return self.pages[url]
            return _detail_html(url)

        with patch.object(newbery, '_fetch_html', side_effect=_missing_author):
            with self.assertRaises(NewberySourceError) as caught:
                newbery.lookup('Crispin: The Cross of Lead', 'Avi')
        self.assertIn('usable author byline', str(caught.exception))
        self.assertNotIn(CRISPIN_URL, newbery._detail_author_cache)

    def test_parsed_author_mismatch_returns_empty(self):
        results = self._lookup('Crispin: The Cross of Lead', 'Not Avi')
        self.assertEqual(results, [])
        self.assertIn(CRISPIN_URL, newbery._detail_author_cache)

    def test_successful_detail_author_is_cached(self):
        self._lookup('Crispin: The Cross of Lead', 'Avi')
        self.assertEqual(newbery._detail_author_cache[CRISPIN_URL], 'Avi')
        self.fetched.clear()
        results = self._lookup('Crispin: The Cross of Lead', 'Avi')
        self.assertEqual(len(results), 1)
        self.assertEqual(self.fetched, [])

    def test_crispin_winner_award_result(self):
        results = self._lookup('Crispin: The Cross of Lead', 'Avi')
        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertEqual(result.work_title, 'Crispin: The Cross of Lead')
        self.assertEqual(result.work_author, 'Avi')
        self.assertEqual(result.award_name, 'Newbery Medal')
        self.assertEqual(result.category, "Children's Literature")
        self.assertEqual(result.award_year, 2003)
        self.assertEqual(result.status, 'Winner')
        self.assertIsNone(result.rank)
        self.assertEqual(result.source_name, 'John Newbery Medal')
        self.assertEqual(result.source_url, CRISPIN_URL)
        self.assertEqual(result.identity_kind, 'work')

    def test_tombs_of_atuan_honor_award_result(self):
        results = self._lookup('The Tombs of Atuan', 'Ursula K. Le Guin')
        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertEqual(result.work_title, 'The Tombs of Atuan')
        self.assertEqual(result.work_author, 'Ursula K. LeGuin')
        self.assertEqual(result.award_year, 1972)
        self.assertEqual(result.status, 'Honor')
        self.assertIsNone(result.rank)
        self.assertEqual(result.source_url, ATUAN_URL)

    def test_author_mismatch_produces_no_result(self):
        self.assertEqual(
            self._lookup('The Tombs of Atuan', 'Madeleine L\'Engle'),
            [],
        )

    def test_subtitle_fallback_works_through_lookup(self):
        results = self._lookup('Crispin', 'Avi')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].work_title, 'Crispin: The Cross of Lead')

    def test_ampersand_and_conjunction_works_through_lookup(self):
        results = self._lookup('Smith and Jones', 'Pat Author')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].work_title, 'Smith & Jones')

    def test_omitted_middle_name_misses_through_lookup(self):
        def _higuera(opener, url: str) -> str:
            self.fetched.append(url)
            if url == CRISPIN_URL:
                return _detail_page(
                    'Crispin: The Cross of Lead',
                    '"Crispin" written by Donna Barba Higuera. Published by X.',
                )
            if url in self.pages:
                return self.pages[url]
            return _detail_html(url)

        with patch.object(newbery, '_fetch_html', side_effect=_higuera):
            results = newbery.lookup('Crispin: The Cross of Lead', 'Donna Higuera')
        self.assertEqual(results, [])

    def test_lookup_rejects_empty_title_or_author(self):
        with self.assertRaises(ValueError):
            newbery.lookup('  ', 'Avi')
        with self.assertRaises(ValueError):
            newbery.lookup('Crispin', '  ')

    def test_reset_clears_listing_and_detail_caches(self):
        self._lookup('Crispin: The Cross of Lead', 'Avi')
        self.assertIsNotNone(newbery._listing_records_cache)
        self.assertTrue(newbery._detail_author_cache)
        newbery._reset_runtime_state()
        self.assertIsNone(newbery._listing_records_cache)
        self.assertEqual(newbery._detail_author_cache, {})


class NewberyFetchHtmlTests(unittest.TestCase):
    def test_http_error_becomes_source_error(self):
        opener = Mock()

        def _open(request, timeout=None):
            raise HTTPError(
                request.full_url,
                500,
                'Error',
                hdrs=None,
                fp=io.BytesIO(b'nope'),
            )

        opener.open.side_effect = _open
        with self.assertRaises(NewberySourceError) as caught:
            newbery._fetch_html(opener, ARCHIVE_URL_1992_2003)
        self.assertIn('HTTP 500', str(caught.exception))

    def test_non_200_becomes_source_error(self):
        opener = Mock()
        opener.open.return_value = _FakeResponse(
            ARCHIVE_URL_1992_2003, 203, '<html></html>'
        )
        with self.assertRaises(NewberySourceError) as caught:
            newbery._fetch_html(opener, ARCHIVE_URL_1992_2003)
        self.assertIn('HTTP 203', str(caught.exception))


if __name__ == '__main__':
    unittest.main()
