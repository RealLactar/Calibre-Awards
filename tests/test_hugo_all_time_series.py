"""Offline coverage for Hugo Best All-Time Series parsing and matching."""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from awards.formatter import format_award_result
from awards.qualifier import QualificationDecision, qualify_award_result
from awards.sources import hugo

URL_1965 = 'https://www.thehugoawards.org/hugo-history/1965-hugo-awards/'
URL_1966 = 'https://www.thehugoawards.org/hugo-history/1966-hugo-awards/'
URL_1967 = 'https://www.thehugoawards.org/hugo-history/1967-hugo-awards/'
URL_1998 = 'https://www.thehugoawards.org/hugo-history/1998-hugo-awards/'
URL_2017 = 'https://www.thehugoawards.org/hugo-history/2017-hugo-awards/'
URL_2025 = 'https://www.thehugoawards.org/hugo-history/2025-hugo-awards/'

HTML_1966_ALL_TIME = """
<p><strong>Best Novel</strong></p>
<ul>
<li class="winner"><em>Dune</em> by Frank Herbert [Chilton, 1965]</li>
</ul>
<p><strong>Short Fiction</strong></p>
<ul>
<li class="winner">&#8220;&#8216;Repent, Harlequin!&#8217; Said the Ticktockman&#8221; by Harlan Ellison</li>
</ul>
<p><strong>Best All-Time Series</strong></p>
<ul>
<li class="winner"><strong>Foundation</strong> series by Isaac Asimov</li>
<li><strong>Barsoom</strong> series by Edgar Rice Burroughs</li>
<li><strong>Future History</strong> series by Robert A. Heinlein</li>
<li><strong>Lensmen</strong> series by Edward E. Smith</li>
<li><strong>The Lord of the Rings</strong> by J. R. R. Tolkien</li>
</ul>
"""

HTML_1966_WITHOUT_ALL_TIME = """
<p><strong>Best Novel</strong></p>
<ul>
<li class="winner"><em>Dune</em> by Frank Herbert [Chilton, 1965]</li>
</ul>
<p><strong>Short Fiction</strong></p>
<ul>
<li class="winner">&#8220;&#8216;Repent, Harlequin!&#8217; Said the Ticktockman&#8221; by Harlan Ellison</li>
</ul>
"""

HTML_1965 = """
<p><strong>Best Novel</strong></p>
<ul>
<li class="winner"><em>The Wanderer</em> by Fritz Leiber [Ballantine, 1964]</li>
</ul>
<p><strong>Short Fiction</strong></p>
<ul>
<li class="winner">&#8220;Soldier, Ask Not&#8221; by Gordon R. Dickson</li>
</ul>
"""

HTML_1967 = """
<p><strong>Best Novel</strong></p>
<ul>
<li class="winner"><em>The Moon is a Harsh Mistress</em> by Robert A. Heinlein</li>
</ul>
<p><strong>Best Novelette</strong></p>
<ul>
<li class="winner"><em>The Last Castle</em> by Jack Vance</li>
</ul>
<p><strong>Best Short Story</strong></p>
<ul>
<li class="winner"><em>Neutron Star</em> by Larry Niven</li>
</ul>
"""

HTML_2017_SERIES = """
<p><strong>Best Novel</strong></p>
<ul>
<li class="winner"><em>The Obelisk Gate</em>, by N.K. Jemisin (Orbit US / Orbit UK)</li>
</ul>
<p><strong>Best Novella</strong></p>
<ul>
<li class="winner"><em>Every Heart a Doorway</em> by Seanan McGuire (Tor.com)</li>
</ul>
<p><strong>Best Novelette</strong></p>
<ul>
<li class="winner">“The Tomato Thief” by Ursula Vernon</li>
</ul>
<p><strong>Best Short Story</strong></p>
<ul>
<li class="winner">“Seasons of Glass and Iron” by Amal El-Mohtar</li>
</ul>
<p><strong>Best Series</strong></p>
<ul>
<li class="winner"><em>The Vorkosigan Saga</em>, by Lois McMaster Bujold (Baen)</li>
<li><em>The Expanse</em>, by James S.A. Corey (Orbit US / Orbit UK)</li>
</ul>
"""

HTML_1998_RELATED = """
<p><strong>Best Novel</strong></p>
<ul>
<li class="winner"><em>Forever Peace</em> by Joe Haldeman (Ace)</li>
</ul>
<p><strong>Best Novella</strong></p>
<ul>
<li class="winner"><em>...Where Angels Fear To Tread</em> by Allen Steele</li>
</ul>
<p><strong>Best Novelette</strong></p>
<ul>
<li class="winner">“We Will Drink a Fish Together” by Bill Johnson</li>
</ul>
<p><strong>Best Short Story</strong></p>
<ul>
<li class="winner">“The 43 Antarean Dynasties” by Mike Resnick</li>
</ul>
<p><strong>Best Related Non-Fiction Book</strong></p>
<ul>
<li class="winner"><em>The Encyclopedia of Fantasy</em> by John Clute &amp; John Grant (Orbit; St. Martin’s)</li>
</ul>
"""

HTML_2025_POEM = """
<p><strong>Best Novel</strong></p>
<ul>
<li class="winner"><em>The Tainted Cup</em> by Robert Jackson Bennett (Del Rey)</li>
</ul>
<p><strong>Best Novella</strong></p>
<ul>
<li class="winner"><em>The Tusks of Extinction</em> by Ray Nayler (Tordotcom)</li>
</ul>
<p><strong>Best Novelette</strong></p>
<ul>
<li class="winner">“The Four Sisters Overlooking the Sea” by Naomi Kritzer</li>
</ul>
<p><strong>Best Short Story</strong></p>
<ul>
<li class="winner">“Stitched to Skin like Family Is” by Nghi Vo</li>
</ul>
<p><strong>Best Series</strong></p>
<ul>
<li class="winner"><em>Between Earth and Sky</em> by Rebecca Roanhorse (Saga Press)</li>
</ul>
<p><strong>Best Poem</strong></p>
<ul>
<li class="winner">“A War of Words” by Marie Brennan (<em>Strange Horizons</em>, September 2024)</li>
</ul>
"""


def _archive_item(title: str, link: str, content: str, slug: str = 'unused'):
    return {
        'title': {'rendered': title},
        'link': link,
        'slug': slug,
        'content': {'rendered': content},
    }


def _find(records, *, title: str, author: str | None = None):
    matches = [record for record in records if record.work_title == title]
    if author is not None:
        matches = [record for record in matches if record.work_author == author]
    return matches


class HugoAllTimeSeriesConstantTests(unittest.TestCase):
    def test_exact_category_constant(self):
        self.assertEqual(
            hugo.CATEGORY_BEST_ALL_TIME_SERIES, 'Best All-Time Series'
        )
        self.assertNotEqual(
            hugo.CATEGORY_BEST_ALL_TIME_SERIES, hugo.CATEGORY_BEST_SERIES
        )
        self.assertEqual(hugo.CATEGORY_BEST_SERIES, 'Best Series')

    def test_1966_is_required(self):
        self.assertTrue(hugo._year_requires_best_all_time_series(1966))
        self.assertEqual(hugo._BEST_ALL_TIME_SERIES_YEARS, frozenset({1966}))

    def test_nearby_years_are_not_required(self):
        self.assertFalse(hugo._year_requires_best_all_time_series(1965))
        self.assertFalse(hugo._year_requires_best_all_time_series(1967))
        self.assertFalse(hugo._year_requires_best_all_time_series(2017))


class HugoAllTimeSeriesParseTests(unittest.TestCase):
    def test_official_shape_parses_all_five_ballot_rows(self):
        records = hugo._parse_series_category_html(
            HTML_1966_ALL_TIME,
            1966,
            URL_1966,
            hugo.CATEGORY_BEST_ALL_TIME_SERIES,
        )
        self.assertEqual(len(records), 5)
        self.assertEqual(
            [record.work_title for record in records],
            [
                'Foundation series',
                'Barsoom series',
                'Future History series',
                'Lensmen series',
                'The Lord of the Rings',
            ],
        )
        self.assertEqual(
            [record.work_author for record in records],
            [
                'Isaac Asimov',
                'Edgar Rice Burroughs',
                'Robert A. Heinlein',
                'Edward E. Smith',
                'J. R. R. Tolkien',
            ],
        )
        self.assertEqual(
            [record.status for record in records],
            ['Winner', 'Finalist', 'Finalist', 'Finalist', 'Finalist'],
        )
        self.assertTrue(
            all(
                record.category == 'Best All-Time Series' for record in records
            )
        )

    def test_foundation_winner_keeps_official_series_identity(self):
        records = hugo._parse_series_category_html(
            HTML_1966_ALL_TIME,
            1966,
            URL_1966,
            hugo.CATEGORY_BEST_ALL_TIME_SERIES,
        )
        foundation = _find(
            records, title='Foundation series', author='Isaac Asimov'
        )[0]
        self.assertEqual(foundation.status, 'Winner')
        self.assertEqual(foundation.work_title, 'Foundation series')
        self.assertEqual(foundation.work_author, 'Isaac Asimov')

    def test_lord_of_the_rings_parses_without_trailing_series(self):
        parsed = hugo._split_series_name_and_author(
            'The Lord of the Rings by J. R. R. Tolkien'
        )
        self.assertEqual(
            parsed, ('The Lord of the Rings', 'J. R. R. Tolkien')
        )
        records = hugo._parse_series_category_html(
            HTML_1966_ALL_TIME,
            1966,
            URL_1966,
            hugo.CATEGORY_BEST_ALL_TIME_SERIES,
        )
        lotr = _find(
            records,
            title='The Lord of the Rings',
            author='J. R. R. Tolkien',
        )[0]
        self.assertEqual(lotr.status, 'Finalist')
        self.assertEqual(lotr.work_title, 'The Lord of the Rings')

    def test_best_series_parser_does_not_consume_all_time_series(self):
        records = hugo._parse_best_series_html(
            HTML_1966_ALL_TIME, 1966, URL_1966
        )
        self.assertEqual(records, [])

    def test_direct_work_parser_rejects_all_time_series(self):
        with self.assertRaises(ValueError):
            hugo._parse_category_html(
                HTML_1966_ALL_TIME,
                1966,
                URL_1966,
                hugo.CATEGORY_BEST_ALL_TIME_SERIES,
            )

    def test_supported_categories_html_parses_all_time_series(self):
        records = hugo._parse_supported_categories_html(
            HTML_1966_ALL_TIME, 1966, URL_1966
        )
        categories = {record.category for record in records}
        self.assertIn('Best All-Time Series', categories)
        self.assertNotIn('Best Series', categories)
        self.assertIn('Best Novel', categories)


class HugoAllTimeSeriesResultTests(unittest.TestCase):
    def test_award_result_is_series_with_no_rank(self):
        record = hugo._parse_series_category_html(
            HTML_1966_ALL_TIME,
            1966,
            URL_1966,
            hugo.CATEGORY_BEST_ALL_TIME_SERIES,
        )[0]
        result = hugo._to_award_result(record)
        self.assertEqual(result.award_name, 'Hugo Award')
        self.assertEqual(result.category, 'Best All-Time Series')
        self.assertEqual(result.identity_kind, 'series')
        self.assertIsNone(result.rank)
        self.assertEqual(result.status, 'Winner')
        self.assertEqual(result.source_name, 'Hugo Awards')
        self.assertEqual(result.source_url, URL_1966)
        self.assertEqual(
            qualify_award_result(result).decision,
            QualificationDecision.QUALIFIES,
        )
        self.assertEqual(
            format_award_result(result),
            'Winner - 1966 Hugo Award - Best All-Time Series [Foundation series]',
        )

    def test_finalists_are_review_unchecked(self):
        records = hugo._parse_series_category_html(
            HTML_1966_ALL_TIME,
            1966,
            URL_1966,
            hugo.CATEGORY_BEST_ALL_TIME_SERIES,
        )
        for record in records[1:]:
            result = hugo._to_award_result(record)
            assessment = qualify_award_result(result)
            self.assertEqual(result.status, 'Finalist')
            self.assertEqual(result.identity_kind, 'series')
            self.assertIsNone(result.rank)
            self.assertEqual(assessment.decision, QualificationDecision.REVIEW)


class HugoAllTimeSeriesMatchingTests(unittest.TestCase):
    def test_calibre_foundation_matches_official_foundation_series(self):
        record = hugo._parse_series_category_html(
            HTML_1966_ALL_TIME,
            1966,
            URL_1966,
            hugo.CATEGORY_BEST_ALL_TIME_SERIES,
        )[0]
        self.assertTrue(
            hugo._series_record_matches(
                record, 'Foundation', 'Isaac Asimov'
            )
        )

    def test_unrelated_calibre_series_does_not_match(self):
        record = hugo._parse_series_category_html(
            HTML_1966_ALL_TIME,
            1966,
            URL_1966,
            hugo.CATEGORY_BEST_ALL_TIME_SERIES,
        )[0]
        self.assertFalse(
            hugo._series_record_matches(
                record, 'Barsoom', 'Isaac Asimov'
            )
        )
        self.assertFalse(
            hugo._series_record_matches(
                record, 'Vorkosigan Saga', 'Isaac Asimov'
            )
        )

    def test_matching_author_is_required(self):
        record = hugo._parse_series_category_html(
            HTML_1966_ALL_TIME,
            1966,
            URL_1966,
            hugo.CATEGORY_BEST_ALL_TIME_SERIES,
        )[0]
        self.assertFalse(
            hugo._series_record_matches(
                record, 'Foundation', 'Edgar Rice Burroughs'
            )
        )

    def test_direct_work_matching_rejects_series_category(self):
        record = hugo._parse_series_category_html(
            HTML_1966_ALL_TIME,
            1966,
            URL_1966,
            hugo.CATEGORY_BEST_ALL_TIME_SERIES,
        )[0]
        self.assertFalse(
            hugo._record_matches(record, 'Foundation', 'Isaac Asimov')
        )
        self.assertFalse(
            hugo._record_matches(
                record, 'Foundation series', 'Isaac Asimov'
            )
        )

    def test_best_series_still_parses_and_matches(self):
        records = hugo._parse_best_series_html(
            HTML_2017_SERIES, 2017, URL_2017
        )
        winner = _find(records, title='The Vorkosigan Saga')[0]
        self.assertEqual(winner.category, 'Best Series')
        self.assertTrue(
            hugo._series_record_matches(
                winner, 'Vorkosigan Saga', 'Lois McMaster Bujold'
            )
        )
        all_time = hugo._parse_series_category_html(
            HTML_2017_SERIES,
            2017,
            URL_2017,
            hugo.CATEGORY_BEST_ALL_TIME_SERIES,
        )
        self.assertEqual(all_time, [])
        mixed = hugo._parse_supported_categories_html(
            HTML_2017_SERIES, 2017, URL_2017
        )
        self.assertIn('Best Series', [record.category for record in mixed])
        self.assertNotIn(
            'Best All-Time Series', [record.category for record in mixed]
        )


class HugoAllTimeSeriesLookupTests(unittest.TestCase):
    def setUp(self):
        hugo._archive_records_cache = tuple(
            hugo._parse_supported_categories_html(
                HTML_1966_ALL_TIME, 1966, URL_1966
            )
            + hugo._parse_supported_categories_html(
                HTML_2017_SERIES, 2017, URL_2017
            )
            + hugo._parse_supported_categories_html(
                HTML_1998_RELATED, 1998, URL_1998
            )
            + hugo._parse_supported_categories_html(
                HTML_2025_POEM, 2025, URL_2025
            )
        )

    def tearDown(self):
        hugo._archive_records_cache = None

    def test_foundation_lookup_uses_series_not_title(self):
        results = hugo.lookup(
            'Foundation',
            'Isaac Asimov',
            series='Foundation',
        )
        all_time = [
            result
            for result in results
            if result.category == 'Best All-Time Series'
        ]
        self.assertEqual(len(all_time), 1)
        result = all_time[0]
        self.assertEqual(result.work_title, 'Foundation series')
        self.assertEqual(result.work_author, 'Isaac Asimov')
        self.assertEqual(result.status, 'Winner')
        self.assertEqual(result.award_year, 1966)
        self.assertEqual(result.identity_kind, 'series')
        self.assertIsNone(result.rank)
        self.assertEqual(
            format_award_result(result),
            'Winner - 1966 Hugo Award - Best All-Time Series [Foundation series]',
        )
        title_only = hugo.lookup('Foundation', 'Isaac Asimov')
        self.assertFalse(
            any(
                result.category == 'Best All-Time Series'
                for result in title_only
            )
        )

    def test_best_series_lookup_regression(self):
        results = hugo.lookup(
            'Shards of Honor',
            'Lois McMaster Bujold',
            series='Vorkosigan Saga',
        )
        series_results = [
            result for result in results if result.category == 'Best Series'
        ]
        self.assertEqual(len(series_results), 1)
        self.assertEqual(series_results[0].status, 'Winner')
        self.assertEqual(series_results[0].award_year, 2017)
        self.assertEqual(
            series_results[0].work_title, 'The Vorkosigan Saga'
        )

    def test_related_book_lookup_regression(self):
        results = hugo.lookup(
            'The Encyclopedia of Fantasy',
            'John Clute & John Grant',
        )
        related = [
            result
            for result in results
            if result.category == 'Best Related Non-Fiction Book'
        ]
        self.assertEqual(len(related), 1)
        self.assertEqual(related[0].status, 'Winner')
        self.assertEqual(related[0].award_year, 1998)
        self.assertEqual(related[0].identity_kind, 'work')

    def test_best_poem_lookup_regression(self):
        results = hugo.lookup('A War of Words', 'Marie Brennan')
        poems = [
            result for result in results if result.category == 'Best Poem'
        ]
        self.assertEqual(len(poems), 1)
        self.assertEqual(poems[0].status, 'Winner')
        self.assertEqual(poems[0].award_year, 2025)
        self.assertEqual(poems[0].identity_kind, 'work')


class HugoAllTimeSeriesFailClosedTests(unittest.TestCase):
    def setUp(self):
        hugo._archive_records_cache = None

    def tearDown(self):
        hugo._archive_records_cache = None

    def test_1966_missing_all_time_series_fails_closed(self):
        body = json.dumps(
            [
                _archive_item(
                    '1966 Hugo Awards',
                    URL_1966,
                    HTML_1966_WITHOUT_ALL_TIME,
                    '1966-hugo-awards',
                )
            ]
        )
        headers = {'X-WP-Total': '1', 'X-WP-TotalPages': '1'}
        with patch.object(
            hugo,
            '_fetch_archive_response',
            return_value=(200, headers, body),
        ):
            with self.assertRaises(hugo.HugoSourceError) as ctx:
                hugo._get_archive_records()
        self.assertIsNone(hugo._archive_records_cache)
        self.assertIn(
            'no Best All-Time Series records could be parsed',
            str(ctx.exception),
        )

    def test_1965_does_not_require_all_time_series(self):
        body = json.dumps(
            [
                _archive_item(
                    '1965 Hugo Awards',
                    URL_1965,
                    HTML_1965,
                    '1965-hugo-awards',
                )
            ]
        )
        headers = {'X-WP-Total': '1', 'X-WP-TotalPages': '1'}
        with patch.object(
            hugo,
            '_fetch_archive_response',
            return_value=(200, headers, body),
        ):
            records = hugo._get_archive_records()
        self.assertNotIn(
            'Best All-Time Series', [record.category for record in records]
        )
        self.assertIn('Best Novel', [record.category for record in records])

    def test_1967_does_not_require_all_time_series(self):
        body = json.dumps(
            [
                _archive_item(
                    '1967 Hugo Awards',
                    URL_1967,
                    HTML_1967,
                    '1967-hugo-awards',
                )
            ]
        )
        headers = {'X-WP-Total': '1', 'X-WP-TotalPages': '1'}
        with patch.object(
            hugo,
            '_fetch_archive_response',
            return_value=(200, headers, body),
        ):
            records = hugo._get_archive_records()
        self.assertNotIn(
            'Best All-Time Series', [record.category for record in records]
        )
        self.assertIn('Best Novel', [record.category for record in records])
        self.assertIn('Best Novelette', [record.category for record in records])
        self.assertIn(
            'Best Short Story', [record.category for record in records]
        )

    def test_1966_with_all_time_series_succeeds_without_best_series(self):
        body = json.dumps(
            [
                _archive_item(
                    '1966 Hugo Awards',
                    URL_1966,
                    HTML_1966_ALL_TIME,
                    '1966-hugo-awards',
                )
            ]
        )
        headers = {'X-WP-Total': '1', 'X-WP-TotalPages': '1'}
        with patch.object(
            hugo,
            '_fetch_archive_response',
            return_value=(200, headers, body),
        ):
            records = hugo._get_archive_records()
        categories = {record.category for record in records}
        self.assertIn('Best All-Time Series', categories)
        self.assertNotIn('Best Series', categories)


if __name__ == '__main__':
    unittest.main()
