"""Offline coverage for Hugo Best Series parsing, matching, and lookup."""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from awards.formatter import format_award_result
from awards.qualifier import QualificationDecision, qualify_award_result
from awards.sources import hugo

URL_1966 = 'https://www.thehugoawards.org/hugo-history/1966-hugo-awards/'
URL_2016 = 'https://www.thehugoawards.org/hugo-history/2016-hugo-awards/'
URL_2017 = 'https://www.thehugoawards.org/hugo-history/2017-hugo-awards/'
URL_2021 = 'https://www.thehugoawards.org/hugo-history/2021-hugo-awards/'
URL_2024 = 'https://www.thehugoawards.org/hugo-history/2024-hugo-awards/'
URL_2026 = 'https://www.thehugoawards.org/hugo-history/2026-hugo-awards/'

HTML_2017 = """
<p>Worldcon 75 elected to exercise its authority under the WSFS Constitution to add an additional category for 2017 only.</p>
<p><strong>Best Series</strong><br />
<small>A multi-volume science fiction or fantasy story, unified by elements such as plot, characters, setting, and presentation, appearing in at least three (3) volumes consisting in total of at least 240,000 words by the close of the previous calendar year, at least one volume of which was published in the previous calendar year. If any series and a subset series thereof both receive sufficient nominations to appear on the final ballot, only the version which received more nominations shall appear.</small></p>
<ul>
<li class="winner"><em>The Vorkosigan Saga</em>, by Lois McMaster Bujold (Baen)</li>
<li><em>The Expanse</em>, by James S.A. Corey (Orbit US / Orbit UK)</li>
<li>The <em>Temeraire</em> series, by Naomi Novik (Del Rey / Harper Voyager UK)</li>
<li><em>The Craft Sequence</em>, by Max Gladstone (Tor Books)</li>
<li>The <em>Peter Grant / Rivers of London</em> series, by Ben Aaronovitch (Gollancz / Del Rey / DAW / Subterranean)</li>
<li><em>The October Daye Books</em>, by Seanan McGuire (DAW / Corsair)</li>
</ul>
<p><strong>Best Novel</strong></p>
<ul>
<li class="winner"><em>The Obelisk Gate</em>, by N.K. Jemisin (Orbit US / Orbit UK)</li>
</ul>
"""

HTML_2018_WITH_ELIGIBILITY_NOTE = """
<p><strong>Best Series</strong></p>
<ul>
<li class="winner"><em>World of the Five Gods</em>, by Lois McMaster Bujold (Harper Voyager / Spectrum Literary Agency)</li>
<li><em>InCryptid</em>, by Seanan McGuire (DAW)</li>
</ul>
<p><strong>Best Novel</strong></p>
<ul>
<li class="winner"><em>The Stone Sky</em> by N.K. Jemisin (Orbit)</li>
</ul>
<p>The following series were determined to be ineligible:</p>
<p><strong>Best Series</strong>: <em>The Broken Earth</em> (Declined), <em>The Expanse</em>, <em>The Craft Sequence</em>, <em>October Daye</em> (Not enough words published since last appearance in this category.)</p>
<ul>
<li><em>Lady Astronaut</em>, by Mary Robinette Kowal (fewer than 240,000 new words since last appearance on the ballot)</li>
<li><em>The Singing Hills Cycle</em>, by Nghi Vo (fewer than 240,000 words in total)</li>
</ul>
"""

HTML_2019_PARTIAL_EM = """
<p><strong>Best Series</strong></p>
<ul>
<li class="winner"><em>Wayfarers</em>, by Becky Chambers (Hodder &#038; Stoughton / Harper Voyager)</li>
<li>The <em>October Daye</em> Series, by Seanan McGuire (most recently DAW)</li>
</ul>
"""

HTML_2020_PLANETFALL = """
<p><strong>Best Series</strong></p>
<ul>
<li class="winner"><em>The Expanse</em>, by James S. A. Corey (Orbit US; Orbit UK)</li>
<li><em>Planetfall</em> series, by Emma Newman (Ace; Gollancz)</li>
</ul>
"""

HTML_2021 = """
<p><strong>Best Series</strong><br />
1872 final ballots cast (79.3%)<br />
727 nominating ballots for 180 nominees, finalist range 300-87</p>
<ul>
<li class="winner"><em>The Murderbot Diaries</em>, Martha Wells (Tor.com)</li>
<li><em>The Lady Astronaut Universe</em>, Mary Robinette Kowal (Tor Books/Audible/<em>Magazine of Fantasy and Science Fiction</em>/Solaris)</li>
<li><em>October Daye</em>, Seanan McGuire (DAW)</li>
</ul>
"""

HTML_2024 = """
<p><strong>Best Series</strong></p>
<ul>
<li class="winner"><em>Imperial Radch</em> by Ann Leckie (Orbit US, Orbit UK)</li>
<li><em>The Final Architecture</em> by Adrian Tchaikovsky (Tor UK, Orbit US)</li>
</ul>
"""

HTML_2026 = """
<p><strong>Best Series</strong></p>
<ul>
<li><em>Emily Wilde</em> by Heather Fawcett (Del Rey US; Orbit UK)</li>
<li><em>October Daye</em> by Seanan McGuire (Tor US; DAW)</li>
<li><em>Old Man&#8217;s War</em> by John Scalzi (Tor US; Tor UK)</li>
</ul>
<p>687 ballots cast for 185 nominees. Finalists range 52-136.</p>
<p><strong>Best Series</strong>: </p>
<ul>
<li><em>Lady Astronaut</em>, by Mary Robinette Kowal (fewer than 240,000 new words since last appearance on the ballot)</li>
</ul>
"""

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
<li><strong>The Lord of the Rings</strong> by J. R. R. Tolkien</li>
</ul>
"""

HTML_2016_NO_SERIES = """
<p><strong>Best Novel</strong></p>
<ul>
<li class="winner"><em>The Fifth Season</em>, by N.K. Jemisin (Orbit)</li>
</ul>
<p><strong>Best Novella</strong></p>
<ul>
<li class="winner"><em>Binti</em> by Nnedi Okorafor (Tor.com)</li>
</ul>
<p><strong>Best Novelette</strong></p>
<ul>
<li class="winner">“Folding Beijing” by Hao Jingfang</li>
</ul>
<p><strong>Best Short Story</strong></p>
<ul>
<li class="winner">“Cat Pictures Please” by Naomi Kritzer</li>
</ul>
"""

HTML_2017_WRITTEN_WORKS_NO_SERIES = """
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
"""

HTML_2017_ARCHIVE = """
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
<p><strong>Best Series</strong><br />
<small>A multi-volume science fiction or fantasy story.</small></p>
<ul>
<li class="winner"><em>The Vorkosigan Saga</em>, by Lois McMaster Bujold (Baen)</li>
</ul>
"""

HTML_NO_AWARD_SERIES = """
<p><strong>Best Series</strong></p>
<ul>
<li class="winner"><strong>No Award</strong></li>
<li>No winner chosen</li>
<li><em>The Vorkosigan Saga</em>, by Lois McMaster Bujold (Baen)</li>
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


class HugoBestSeriesParserTests(unittest.TestCase):
    def test_2017_winner_and_definition_do_not_block_ballot(self):
        records = hugo._parse_best_series_html(HTML_2017, 2017, URL_2017)
        winner = _find(
            records,
            title='The Vorkosigan Saga',
            author='Lois McMaster Bujold',
        )
        self.assertEqual(len(winner), 1)
        self.assertEqual(winner[0].status, 'Winner')
        self.assertEqual(winner[0].category, 'Best Series')
        self.assertEqual(winner[0].award_year, 2017)
        definition_hits = [
            record
            for record in records
            if 'multi-volume' in record.work_title.casefold()
        ]
        self.assertEqual(definition_hits, [])

    def test_2017_finalists_and_partial_em_rows(self):
        records = hugo._parse_best_series_html(HTML_2017, 2017, URL_2017)
        expanse = _find(
            records, title='The Expanse', author='James S.A. Corey'
        )
        self.assertEqual(len(expanse), 1)
        self.assertEqual(expanse[0].status, 'Finalist')
        temeraire = _find(
            records, title='The Temeraire series', author='Naomi Novik'
        )
        self.assertEqual(len(temeraire), 1)
        self.assertEqual(temeraire[0].status, 'Finalist')
        rivers = _find(
            records,
            title='The Peter Grant / Rivers of London series',
            author='Ben Aaronovitch',
        )
        self.assertEqual(len(rivers), 1)
        october = _find(
            records,
            title='The October Daye Books',
            author='Seanan McGuire',
        )
        self.assertEqual(len(october), 1)
        self.assertEqual(
            [record.status for record in records if record.status == 'Winner'],
            ['Winner'],
        )

    def test_2019_partial_em_october_daye_series(self):
        records = hugo._parse_best_series_html(
            HTML_2019_PARTIAL_EM, 2019, URL_2017
        )
        october = _find(
            records,
            title='The October Daye Series',
            author='Seanan McGuire',
        )
        self.assertEqual(len(october), 1)

    def test_2020_planetfall_series_keeps_visible_series_phrase(self):
        records = hugo._parse_best_series_html(
            HTML_2020_PLANETFALL, 2020, URL_2017
        )
        planetfall = _find(
            records, title='Planetfall series', author='Emma Newman'
        )
        self.assertEqual(len(planetfall), 1)

    def test_2021_comma_author_and_nested_publisher_em(self):
        records = hugo._parse_best_series_html(HTML_2021, 2021, URL_2021)
        murderbot = _find(
            records, title='The Murderbot Diaries', author='Martha Wells'
        )
        self.assertEqual(len(murderbot), 1)
        self.assertEqual(murderbot[0].status, 'Winner')
        astronaut = _find(
            records,
            title='The Lady Astronaut Universe',
            author='Mary Robinette Kowal',
        )
        self.assertEqual(len(astronaut), 1)
        self.assertNotEqual(
            astronaut[0].work_title, 'Magazine of Fantasy and Science Fiction'
        )
        self.assertNotIn(
            'Magazine of Fantasy and Science Fiction',
            [record.work_title for record in records],
        )

    def test_2024_no_comma_before_by(self):
        records = hugo._parse_best_series_html(HTML_2024, 2024, URL_2024)
        radch = _find(records, title='Imperial Radch', author='Ann Leckie')
        self.assertEqual(len(radch), 1)
        self.assertEqual(radch[0].status, 'Winner')

    def test_2026_finalists_do_not_invent_a_winner(self):
        records = hugo._parse_best_series_html(HTML_2026, 2026, URL_2026)
        self.assertTrue(records)
        self.assertTrue(all(record.status == 'Finalist' for record in records))
        emily = _find(records, title='Emily Wilde', author='Heather Fawcett')
        self.assertEqual(len(emily), 1)
        self.assertNotIn(
            'Lady Astronaut', [record.work_title for record in records]
        )

    def test_later_eligibility_note_block_is_not_a_ballot(self):
        records = hugo._parse_best_series_html(
            HTML_2018_WITH_ELIGIBILITY_NOTE, 2018, URL_2017
        )
        titles = [record.work_title for record in records]
        self.assertEqual(
            titles, ['World of the Five Gods', 'InCryptid']
        )
        self.assertNotIn('The Broken Earth', titles)
        self.assertNotIn('The Singing Hills Cycle', titles)
        self.assertNotIn('Lady Astronaut', titles)

    def test_no_award_rows_are_skipped(self):
        records = hugo._parse_best_series_html(
            HTML_NO_AWARD_SERIES, 2017, URL_2017
        )
        self.assertEqual(
            [record.work_title for record in records],
            ['The Vorkosigan Saga'],
        )

    def test_1966_best_all_time_series_is_not_best_series(self):
        records = hugo._parse_best_series_html(
            HTML_1966_ALL_TIME, 1966, URL_1966
        )
        self.assertEqual(records, [])
        mixed = hugo._parse_supported_categories_html(
            HTML_1966_ALL_TIME, 1966, URL_1966
        )
        self.assertNotIn('Best Series', [record.category for record in mixed])
        all_time = [
            record
            for record in mixed
            if record.category == 'Best All-Time Series'
        ]
        self.assertTrue(all_time)
        self.assertEqual(all_time[0].work_title, 'Foundation series')
        self.assertNotIn(
            'Foundation', [record.work_title for record in mixed]
        )

    def test_book_title_parser_does_not_accept_best_series(self):
        with self.assertRaises(ValueError):
            hugo._parse_category_html(
                HTML_2017, 2017, URL_2017, hugo.CATEGORY_BEST_SERIES
            )

    def test_official_series_names_in_fixtures_contain_no_commas(self):
        pages = (
            (HTML_2017, 2017, URL_2017),
            (HTML_2018_WITH_ELIGIBILITY_NOTE, 2018, URL_2017),
            (HTML_2019_PARTIAL_EM, 2019, URL_2017),
            (HTML_2020_PLANETFALL, 2020, URL_2017),
            (HTML_2021, 2021, URL_2021),
            (HTML_2024, 2024, URL_2024),
            (HTML_2026, 2026, URL_2026),
        )
        names = []
        for page_html, year, url in pages:
            names.extend(
                record.work_title
                for record in hugo._parse_best_series_html(page_html, year, url)
            )
        self.assertTrue(names)
        comma_names = [name for name in names if ',' in name]
        self.assertEqual(comma_names, [])


class HugoSeriesMatchingTests(unittest.TestCase):
    def test_leading_the_and_trailing_series_books_wrappers(self):
        self.assertTrue(
            hugo._series_names_match('Vorkosigan Saga', 'The Vorkosigan Saga')
        )
        self.assertTrue(
            hugo._series_names_match('October Daye', 'The October Daye Series')
        )
        self.assertTrue(
            hugo._series_names_match('Planetfall', 'Planetfall series')
        )
        self.assertTrue(
            hugo._series_names_match('October Daye', 'The October Daye Books')
        )

    def test_conjunction_and_hyphen_normalization_still_apply(self):
        self.assertTrue(
            hugo._series_names_match(
                'Jonathan Strange and Mr Norrell',
                'Jonathan Strange & Mr Norrell',
            )
        )
        self.assertTrue(
            hugo._series_names_match('Old Man\'s War', 'Old Man’s War')
        )

    def test_internal_apostrophes_and_meaningful_words_are_kept(self):
        self.assertFalse(
            hugo._series_names_match("Don't Panic", 'Dont Panic')
        )
        self.assertFalse(
            hugo._series_names_match('The Craft Sequence', 'The Craft')
        )
        self.assertFalse(
            hugo._series_names_match('Wayfarers', 'Wayfarer')
        )

    def test_unrelated_and_substring_names_do_not_match(self):
        self.assertFalse(
            hugo._series_names_match('Vorkosigan Saga', 'The Expanse')
        )
        self.assertFalse(
            hugo._series_names_match(
                'Rivers of London',
                'The Peter Grant / Rivers of London series',
            )
        )
        self.assertFalse(
            hugo._series_names_match('Chalion', 'World of the Five Gods')
        )
        self.assertFalse(
            hugo._series_names_match('Vorkosigan', 'The Vorkosigan Saga')
        )

    def test_series_match_without_author_match_fails(self):
        records = hugo._parse_best_series_html(HTML_2017, 2017, URL_2017)
        winner = _find(records, title='The Vorkosigan Saga')[0]
        self.assertTrue(
            hugo._series_record_matches(
                winner, 'Vorkosigan Saga', 'Lois McMaster Bujold'
            )
        )
        self.assertFalse(
            hugo._series_record_matches(
                winner, 'Vorkosigan Saga', 'N.K. Jemisin'
            )
        )
        self.assertFalse(
            hugo._series_record_matches(
                winner, 'Vorkosigan Saga', 'James S.A. Corey'
            )
        )


class HugoSeriesLookupTests(unittest.TestCase):
    def setUp(self):
        hugo._archive_records_cache = tuple(
            hugo._parse_supported_categories_html(HTML_2017, 2017, URL_2017)
        )

    def tearDown(self):
        hugo._archive_records_cache = None

    def test_shards_of_honor_with_series_returns_2017_winner(self):
        results = hugo.lookup(
            'Shards of Honor',
            'Lois McMaster Bujold',
            series='Vorkosigan Saga',
        )
        series_results = [
            result for result in results if result.category == 'Best Series'
        ]
        self.assertEqual(len(series_results), 1)
        result = series_results[0]
        self.assertEqual(result.work_title, 'The Vorkosigan Saga')
        self.assertEqual(result.work_author, 'Lois McMaster Bujold')
        self.assertEqual(result.status, 'Winner')
        self.assertEqual(result.award_year, 2017)
        self.assertEqual(result.identity_kind, 'series')
        self.assertIsNone(result.rank)
        self.assertEqual(
            format_award_result(result),
            'Winner - 2017 Hugo Award - Best Series [The Vorkosigan Saga]',
        )
        self.assertEqual(
            qualify_award_result(result).decision,
            QualificationDecision.QUALIFIES,
        )

    def test_empty_series_does_not_return_best_series(self):
        results = hugo.lookup(
            'Shards of Honor',
            'Lois McMaster Bujold',
            series='',
        )
        self.assertFalse(
            any(result.category == 'Best Series' for result in results)
        )
        two_arg = hugo.lookup('Shards of Honor', 'Lois McMaster Bujold')
        self.assertFalse(
            any(result.category == 'Best Series' for result in two_arg)
        )

    def test_unrelated_series_does_not_return_best_series(self):
        results = hugo.lookup(
            'Shards of Honor',
            'Lois McMaster Bujold',
            series='The Expanse',
        )
        self.assertFalse(
            any(result.category == 'Best Series' for result in results)
        )

    def test_book_title_equal_to_series_name_is_not_enough(self):
        results = hugo.lookup(
            'The Vorkosigan Saga',
            'Lois McMaster Bujold',
            series='',
        )
        self.assertFalse(
            any(result.category == 'Best Series' for result in results)
        )
        self.assertFalse(
            any(result.identity_kind == 'series' for result in results)
        )

    def test_work_results_remain_identity_kind_work(self):
        results = hugo.lookup(
            'The Obelisk Gate',
            'N.K. Jemisin',
            series='Vorkosigan Saga',
        )
        self.assertTrue(results)
        self.assertTrue(
            all(result.identity_kind == 'work' for result in results)
        )
        self.assertNotIn(
            'Best Series', [result.category for result in results]
        )

    def test_corey_house_name_is_not_equated_to_other_authors(self):
        results = hugo.lookup(
            'Leviathan Wakes',
            'Daniel Abraham',
            series='The Expanse',
        )
        self.assertFalse(
            any(result.category == 'Best Series' for result in results)
        )


class HugoSeriesCoverageTests(unittest.TestCase):
    def test_best_series_required_from_2017_not_earlier(self):
        required = {2017, 2018, 2020, 2025, 2026}
        skipped = {1958, 1966, 2016}
        for year in required:
            with self.subTest(year=year):
                self.assertTrue(hugo._year_requires_best_series(year))
        for year in skipped:
            with self.subTest(year=year):
                self.assertFalse(hugo._year_requires_best_series(year))

    def test_2016_archive_does_not_require_best_series(self):
        hugo._archive_records_cache = None
        body = json.dumps(
            [
                _archive_item(
                    '2016 Hugo Awards',
                    URL_2016,
                    HTML_2016_NO_SERIES,
                    '2016-hugo-awards',
                )
            ]
        )
        headers = {'X-WP-Total': '1', 'X-WP-TotalPages': '1'}
        try:
            with patch.object(
                hugo,
                '_fetch_archive_response',
                return_value=(200, headers, body),
            ):
                records = hugo._get_archive_records()
            self.assertNotIn(
                'Best Series', [record.category for record in records]
            )
        finally:
            hugo._archive_records_cache = None

    def test_2017_archive_without_series_records_fails_closed(self):
        hugo._archive_records_cache = None
        body = json.dumps(
            [
                _archive_item(
                    '2017 Hugo Awards',
                    URL_2017,
                    HTML_2017_WRITTEN_WORKS_NO_SERIES,
                    '2017-hugo-awards',
                )
            ]
        )
        headers = {'X-WP-Total': '1', 'X-WP-TotalPages': '1'}
        try:
            with patch.object(
                hugo,
                '_fetch_archive_response',
                return_value=(200, headers, body),
            ):
                with self.assertRaises(hugo.HugoSourceError) as ctx:
                    hugo._get_archive_records()
            self.assertIsNone(hugo._archive_records_cache)
            self.assertIn(
                'no Best Series records could be parsed',
                str(ctx.exception),
            )
        finally:
            hugo._archive_records_cache = None

    def test_2017_definition_page_satisfies_fail_closed(self):
        hugo._archive_records_cache = None
        body = json.dumps(
            [
                _archive_item(
                    '2017 Hugo Awards',
                    URL_2017,
                    HTML_2017_ARCHIVE,
                    '2017-hugo-awards',
                )
            ]
        )
        headers = {'X-WP-Total': '1', 'X-WP-TotalPages': '1'}
        try:
            with patch.object(
                hugo,
                '_fetch_archive_response',
                return_value=(200, headers, body),
            ):
                records = hugo._get_archive_records()
            series = [
                record
                for record in records
                if record.category == 'Best Series'
            ]
            self.assertTrue(series)
            self.assertEqual(series[0].work_title, 'The Vorkosigan Saga')
        finally:
            hugo._archive_records_cache = None

    def test_1966_archive_with_all_time_series_does_not_require_best_series(self):
        hugo._archive_records_cache = None
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
        try:
            with patch.object(
                hugo,
                '_fetch_archive_response',
                return_value=(200, headers, body),
            ):
                records = hugo._get_archive_records()
            self.assertNotIn(
                'Best Series', [record.category for record in records]
            )
            self.assertIn(
                'Best All-Time Series',
                [record.category for record in records],
            )
        finally:
            hugo._archive_records_cache = None


if __name__ == '__main__':
    unittest.main()
