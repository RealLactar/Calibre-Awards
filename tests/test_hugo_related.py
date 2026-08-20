"""Offline coverage for Hugo Related Book categories and membership matching."""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from awards.formatter import format_award_result
from awards.qualifier import QualificationDecision, qualify_award_result
from awards.sources import hugo

URL_1991 = 'https://www.thehugoawards.org/hugo-history/1991-hugo-awards/'
URL_1998 = 'https://www.thehugoawards.org/hugo-history/1998-hugo-awards/'
URL_1999 = 'https://www.thehugoawards.org/hugo-history/1999-hugo-awards/'
URL_2000 = 'https://www.thehugoawards.org/hugo-history/2000-hugo-awards/'
URL_2002 = 'https://www.thehugoawards.org/hugo-history/2002-hugo-awards/'
URL_2003 = 'https://www.thehugoawards.org/hugo-history/2003-hugo-awards/'
URL_2006 = 'https://www.thehugoawards.org/hugo-history/2006-hugo-awards/'
URL_2007 = 'https://www.thehugoawards.org/hugo-history/2007-hugo-awards/'
URL_2009 = 'https://www.thehugoawards.org/hugo-history/2009-hugo-awards/'
URL_2010 = 'https://www.thehugoawards.org/hugo-history/2010-hugo-awards/'
URL_2017 = 'https://www.thehugoawards.org/hugo-history/2017-hugo-awards/'
URL_2024 = 'https://www.thehugoawards.org/hugo-history/2024-hugo-awards/'

HTML_WRITTEN = """
<p><strong>Best Novel</strong></p>
<ul>
<li class="winner"><em>Some Novel</em> by A Author</li>
</ul>
<p><strong>Best Novella</strong></p>
<ul>
<li class="winner"><em>Some Novella</em> by A Author</li>
</ul>
<p><strong>Best Novelette</strong></p>
<ul>
<li class="winner">“Some Novelette” by A Author</li>
</ul>
<p><strong>Best Short Story</strong></p>
<ul>
<li class="winner">“Some Story” by A Author</li>
</ul>
"""

HTML_1991 = """
<p><strong>Best Related Non-Fiction Book</strong></p>
<ul>
<li class="winner"><em>How to Write Science Fiction and Fantasy</em> by Orson Scott Card [Writer’s Digest, 1990]</li>
<li><em>Science Fiction in the Real World</em> by Norman Spinrad [Southern Illinois University Press, 1990]</li>
</ul>
"""

HTML_1998 = """
<p><strong>Best Related Non-Fiction Book</strong></p>
<ul>
<li class="winner"><em>The Encyclopedia of Fantasy</em> by John Clute and John Grant [Orbit, 1997; St. Martin’s, 1997]</li>
</ul>
"""

HTML_1999 = """
<p><strong>Best Related Book</strong></p>
<ul>
<li class="winner"><em>The Dreams Our Stuff Is Made of: How Science Fiction Conquered the World</em> by Thomas M. Disch [Free Press, 1998]</li>
</ul>
"""

HTML_2000 = """
<p><strong>Best Related Book</strong></p>
<ul>
<li class="winner"><em>Science Fiction of the 20th Century</em> by Frank M. Robinson [Collector’s Press, 1999]</li>
<li><em>The Sandman: The Dream Hunters</em> by Neil Gaiman and Yoshitaka Amano [DC/Vertigo, 1999]</li>
</ul>
"""

HTML_2002 = """
<p><strong>Best Related Book</strong></p>
<ul>
<li class="winner"><em>The Art of Chesley Bonestell</em> by Ron Miller and Frederick C. Durant III with Melvin H. Schuetz [Paper Tiger, 2001]</li>
<li><em>Being Gardner Dozois</em> by Michael Swanwick [Old Earth Books, 2001]</li>
</ul>
"""

HTML_2003 = """
<p><strong>Best Related Non-Fiction Book</strong></p>
<ul>
<li class="winner"><em>Better to Have Loved: The Life of Judith Merril</em> by Judith Merril and Emily Pohl-Weary [Between the Lines, 2002]</li>
</ul>
"""

HTML_2006 = """
<p><strong>Best Related Non-Fiction Book</strong></p>
<ul>
<li class="winner"><em>Storyteller: Writing Lessons and More from 27 Years of the Clarion Writers’ Workshop</em> by Kate Wilhelm [Small Beer Press, 2005]</li>
</ul>
"""

HTML_2007 = """
<p><strong>Best Related Book</strong></p>
<ul>
<li class="winner"><em>James Tiptree, Jr.: The Double Life of Alice B Sheldon</em> by Julie Phillips [St. Martin’s Press, 2006]</li>
<li><em>Worldcon Guest of Honor Speeches</em> by Mike Resnick and Joe Siclari, eds. [ISFiC Press, 2006]</li>
</ul>
"""

HTML_2009 = """
<p><strong>Best Related Book</strong></p>
<ul>
<li class="winner"><em>Your Hate Mail Will be Graded: A Decade of Whatever, 1998-2008</em> by John Scalzi (Subterranean Press)</li>
<li><em>The Vorkosigan Companion: The Universe of Lois McMaster Bujold</em> by Lillian Stewart Carl &amp; John Helfers, eds. (Baen)</li>
<li><em>Spectrum 15: The Best in Contemporary Fantastic Art</em> by Cathy &amp; Arnie Fenner, eds. (Underwood Books)</li>
</ul>
"""

HTML_2010 = """
<p><strong>Best Related Work</strong></p>
<ul>
<li class="winner"><em>This is Me, Jack Vance!</em>, Jack Vance (Subterranean)</li>
</ul>
<p><strong>Best Graphic Story</strong></p>
<ul>
<li class="winner"><em>Girl Genius, Volume 9</em> Written by Kaja and Phil Foglio</li>
</ul>
"""

HTML_2008_COMPLEX = """
<p><strong>Best Related Book</strong></p>
<ul>
<li class="winner"><em>Brave New Words: The Oxford Dictionary of Science Fiction</em> by Jeff Prucher (Oxford University Press)</li>
<li><em>The Company They Keep: C.S. Lewis and J.R.R. Tolkien as Writers in Community</em> by Diana Glyer; appendix by David Bratman (Kent State University Press)</li>
<li><em>Emshwiller: Infinity x Two</em> by Luis Ortiz, intro. by Carol Emshwiller, fwd. by Alex Eisenstien (Nonstop)</li>
</ul>
"""

HTML_SERIES = """
<p><strong>Best Series</strong></p>
<ul>
<li class="winner"><em>The Vorkosigan Saga</em>, by Lois McMaster Bujold (Baen)</li>
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


def _related_record(
    *,
    year: int,
    category: str,
    title: str,
    author: str,
    status: str = 'Winner',
    url: str = URL_1998,
):
    return hugo._ParsedRecord(
        award_year=year,
        category=category,
        status=status,
        work_title=title,
        work_author=author,
        source_url=url,
        match_titles=(title,),
    )


class HugoRelatedParserTests(unittest.TestCase):
    def test_category_constants_are_historically_exact(self):
        self.assertEqual(
            hugo.CATEGORY_BEST_RELATED_NON_FICTION_BOOK,
            'Best Related Non-Fiction Book',
        )
        self.assertEqual(
            hugo.CATEGORY_BEST_RELATED_BOOK,
            'Best Related Book',
        )
        self.assertNotEqual(
            hugo.CATEGORY_BEST_RELATED_NON_FICTION_BOOK,
            hugo.CATEGORY_BEST_RELATED_BOOK,
        )
        self.assertIn(
            hugo.CATEGORY_BEST_RELATED_NON_FICTION_BOOK,
            hugo._SUPPORTED_CATEGORIES,
        )
        self.assertIn(
            hugo.CATEGORY_BEST_RELATED_BOOK,
            hugo._SUPPORTED_CATEGORIES,
        )

    def test_1991_nfb_winner(self):
        records = hugo._parse_category_html(
            HTML_1991,
            1991,
            URL_1991,
            hugo.CATEGORY_BEST_RELATED_NON_FICTION_BOOK,
        )
        winner = _find(
            records,
            title='How to Write Science Fiction and Fantasy',
            author='Orson Scott Card',
        )
        self.assertEqual(len(winner), 1)
        self.assertEqual(winner[0].status, 'Winner')
        self.assertEqual(winner[0].category, 'Best Related Non-Fiction Book')
        result = hugo._to_award_result(winner[0])
        self.assertEqual(result.identity_kind, 'work')
        self.assertIsNone(result.rank)
        self.assertEqual(
            format_award_result(result),
            'Winner - 1991 Hugo Award - Best Related Non-Fiction Book',
        )

    def test_2000_related_book_winner(self):
        records = hugo._parse_category_html(
            HTML_2000,
            2000,
            URL_2000,
            hugo.CATEGORY_BEST_RELATED_BOOK,
        )
        winner = _find(
            records,
            title='Science Fiction of the 20th Century',
            author='Frank M. Robinson',
        )
        self.assertEqual(len(winner), 1)
        self.assertEqual(winner[0].status, 'Winner')
        self.assertEqual(winner[0].category, 'Best Related Book')
        result = hugo._to_award_result(winner[0])
        self.assertEqual(result.identity_kind, 'work')
        self.assertIsNone(result.rank)
        self.assertEqual(
            format_award_result(result),
            'Winner - 2000 Hugo Award - Best Related Book',
        )

    def test_related_work_and_graphic_are_not_parsed(self):
        records = hugo._parse_supported_categories_html(
            HTML_2010, 2010, URL_2010
        )
        self.assertEqual(records, [])
        with self.assertRaises(ValueError):
            hugo._parse_category_html(
                HTML_2010, 2010, URL_2010, 'Best Related Work'
            )


class HugoRelatedYearTests(unittest.TestCase):
    def test_nfb_required_years(self):
        for year in range(1980, 1999):
            self.assertTrue(
                hugo._year_requires_best_related_non_fiction_book(year),
                year,
            )
        for year in (2003, 2004, 2005, 2006):
            self.assertTrue(
                hugo._year_requires_best_related_non_fiction_book(year)
            )
        self.assertEqual(
            len(hugo._BEST_RELATED_NON_FICTION_BOOK_YEARS),
            23,
        )

    def test_related_book_required_years(self):
        for year in (1999, 2000, 2001, 2002, 2007, 2008, 2009):
            self.assertTrue(hugo._year_requires_best_related_book(year))
        self.assertEqual(len(hugo._BEST_RELATED_BOOK_YEARS), 7)

    def test_transition_boundaries(self):
        self.assertTrue(hugo._year_requires_best_related_non_fiction_book(1998))
        self.assertFalse(hugo._year_requires_best_related_book(1998))
        self.assertFalse(hugo._year_requires_best_related_non_fiction_book(1999))
        self.assertTrue(hugo._year_requires_best_related_book(1999))

        self.assertTrue(hugo._year_requires_best_related_book(2002))
        self.assertFalse(hugo._year_requires_best_related_non_fiction_book(2002))
        self.assertTrue(hugo._year_requires_best_related_non_fiction_book(2003))
        self.assertFalse(hugo._year_requires_best_related_book(2003))

        self.assertTrue(hugo._year_requires_best_related_non_fiction_book(2006))
        self.assertFalse(hugo._year_requires_best_related_book(2006))
        self.assertFalse(hugo._year_requires_best_related_non_fiction_book(2007))
        self.assertTrue(hugo._year_requires_best_related_book(2007))

        self.assertTrue(hugo._year_requires_best_related_book(2009))
        self.assertFalse(hugo._year_requires_best_related_non_fiction_book(2010))
        self.assertFalse(hugo._year_requires_best_related_book(2010))
        self.assertFalse(hugo._year_requires_best_related_book(2026))

    def test_parsed_headings_follow_transitions(self):
        cases = (
            (HTML_1998, 1998, URL_1998, 'Best Related Non-Fiction Book', 0),
            (HTML_1999, 1999, URL_1999, 'Best Related Book', 0),
            (HTML_2002, 2002, URL_2002, 'Best Related Book', 0),
            (HTML_2003, 2003, URL_2003, 'Best Related Non-Fiction Book', 0),
            (HTML_2006, 2006, URL_2006, 'Best Related Non-Fiction Book', 0),
            (HTML_2007, 2007, URL_2007, 'Best Related Book', 0),
            (HTML_2009, 2009, URL_2009, 'Best Related Book', 0),
        )
        for html, year, url, expected, other_count in cases:
            records = hugo._parse_supported_categories_html(html, year, url)
            categories = {record.category for record in records}
            self.assertEqual(categories, {expected}, year)
            opposite = (
                hugo.CATEGORY_BEST_RELATED_BOOK
                if expected == 'Best Related Non-Fiction Book'
                else hugo.CATEGORY_BEST_RELATED_NON_FICTION_BOOK
            )
            opposite_records = hugo._parse_category_html(
                html, year, url, opposite
            )
            self.assertEqual(len(opposite_records), other_count, year)


class HugoRelatedFailClosedTests(unittest.TestCase):
    def _records_from_body(self, body: str):
        hugo._archive_records_cache = None
        headers = {'X-WP-Total': '1', 'X-WP-TotalPages': '1'}
        with patch.object(
            hugo,
            '_fetch_archive_response',
            return_value=(200, headers, body),
        ):
            return hugo._get_archive_records()

    def tearDown(self):
        hugo._archive_records_cache = None

    def test_1991_without_nfb_fails_closed(self):
        body = json.dumps(
            [
                _archive_item(
                    '1991 Hugo Awards',
                    URL_1991,
                    HTML_WRITTEN,
                    '1991-hugo-awards',
                )
            ]
        )
        with self.assertRaises(hugo.HugoSourceError) as ctx:
            self._records_from_body(body)
        self.assertIsNone(hugo._archive_records_cache)
        self.assertIn(
            'no Best Related Non-Fiction Book records could be parsed',
            str(ctx.exception),
        )

    def test_1999_without_related_book_fails_closed(self):
        body = json.dumps(
            [
                _archive_item(
                    '1999 Hugo Awards',
                    URL_1999,
                    HTML_WRITTEN,
                    '1999-hugo-awards',
                )
            ]
        )
        with self.assertRaises(hugo.HugoSourceError) as ctx:
            self._records_from_body(body)
        self.assertIn(
            'no Best Related Book records could be parsed',
            str(ctx.exception),
        )

    def test_2010_does_not_require_related_books(self):
        body = json.dumps(
            [
                _archive_item(
                    '2010 Hugo Awards',
                    URL_2010,
                    HTML_WRITTEN + HTML_2010,
                    '2010-hugo-awards',
                )
            ]
        )
        records = self._records_from_body(body)
        self.assertNotIn(
            'Best Related Work',
            [record.category for record in records],
        )
        self.assertNotIn(
            'Best Related Non-Fiction Book',
            [record.category for record in records],
        )
        self.assertNotIn(
            'Best Related Book',
            [record.category for record in records],
        )
        self.assertNotIn(
            'Best Graphic Story',
            [record.category for record in records],
        )


class HugoRelatedMembershipTests(unittest.TestCase):
    def test_title_still_required(self):
        record = _related_record(
            year=2000,
            category=hugo.CATEGORY_BEST_RELATED_BOOK,
            title='The Sandman: The Dream Hunters',
            author='Neil Gaiman',
        )
        self.assertFalse(
            hugo._record_matches(
                record,
                'Some Other Title',
                'Neil Gaiman (ed) & Author One & Author Two',
            )
        )
        self.assertTrue(
            hugo._record_matches(
                record,
                'The Sandman: The Dream Hunters',
                'Neil Gaiman (ed) & Author One & Author Two',
            )
        )

    def test_clute_and_grant_calibre_ampersand(self):
        record = _related_record(
            year=1998,
            category=hugo.CATEGORY_BEST_RELATED_NON_FICTION_BOOK,
            title='The Encyclopedia of Fantasy',
            author='John Clute and John Grant',
        )
        self.assertTrue(
            hugo._record_matches(
                record,
                'The Encyclopedia of Fantasy',
                'John Clute & John Grant',
            )
        )

    def test_missing_required_person_does_not_match(self):
        record = _related_record(
            year=1998,
            category=hugo.CATEGORY_BEST_RELATED_NON_FICTION_BOOK,
            title='The Encyclopedia of Fantasy',
            author='John Clute and John Grant',
        )
        self.assertFalse(
            hugo._record_matches(
                record,
                'The Encyclopedia of Fantasy',
                'John Clute & Unrelated Person',
            )
        )

    def test_editor_role_and_extra_calibre_authors(self):
        record = _related_record(
            year=2000,
            category=hugo.CATEGORY_BEST_RELATED_BOOK,
            title='The Sandman: The Dream Hunters',
            author='Neil Gaiman',
        )
        self.assertTrue(
            hugo._record_matches(
                record,
                'The Sandman: The Dream Hunters',
                'Neil Gaiman (ed) & Author One & Author Two',
            )
        )

    def test_official_eds_suffix_membership(self):
        record = _related_record(
            year=2007,
            category=hugo.CATEGORY_BEST_RELATED_BOOK,
            title='Worldcon Guest of Honor Speeches',
            author='Mike Resnick and Joe Siclari, eds.',
        )
        self.assertEqual(
            record.work_author,
            'Mike Resnick and Joe Siclari, eds.',
        )
        self.assertTrue(
            hugo._record_matches(
                record,
                'Worldcon Guest of Honor Speeches',
                'Mike Resnick (ed) & Joe Siclari (ed) & Author One',
            )
        )

    def test_missing_one_editor_does_not_match(self):
        record = _related_record(
            year=2007,
            category=hugo.CATEGORY_BEST_RELATED_BOOK,
            title='Worldcon Guest of Honor Speeches',
            author='Mike Resnick and Joe Siclari, eds.',
        )
        self.assertFalse(
            hugo._record_matches(
                record,
                'Worldcon Guest of Honor Speeches',
                'Mike Resnick (ed) & Author One',
            )
        )

    def test_whole_string_and_path_still_matches(self):
        record = _related_record(
            year=1998,
            category=hugo.CATEGORY_BEST_RELATED_NON_FICTION_BOOK,
            title='The Encyclopedia of Fantasy',
            author='John Clute and John Grant',
        )
        self.assertTrue(
            hugo._record_matches(
                record,
                'The Encyclopedia of Fantasy',
                'John Clute and John Grant',
            )
        )

    def test_literal_ampersand_is_not_an_author_separator(self):
        self.assertEqual(
            hugo._split_calibre_author_query('Cathy && Arnie Fenner'),
            ('Cathy & Arnie Fenner',),
        )
        self.assertEqual(
            hugo._split_calibre_author_query(
                'Smith && Jones & Other Person'
            ),
            ('Smith & Jones', 'Other Person'),
        )

    def test_shared_surname_is_not_inferred(self):
        self.assertIsNone(
            hugo._parse_related_book_people('Cathy & Arnie Fenner, eds.')
        )
        record = _related_record(
            year=2009,
            category=hugo.CATEGORY_BEST_RELATED_BOOK,
            title='Spectrum 15: The Best in Contemporary Fantastic Art',
            author='Cathy & Arnie Fenner, eds.',
        )
        self.assertFalse(
            hugo._record_matches(
                record,
                'Spectrum 15: The Best in Contemporary Fantastic Art',
                'Cathy Fenner & Arnie Fenner',
            )
        )

    def test_complex_with_credit_refuses_membership_parse(self):
        self.assertIsNone(
            hugo._parse_related_book_people(
                'Ron Miller and Frederick C. Durant III with Melvin H. Schuetz'
            )
        )

    def test_semicolon_appendix_credit_refuses_membership_parse(self):
        self.assertIsNone(
            hugo._parse_related_book_people(
                'Diana Glyer; appendix by David Bratman'
            )
        )

    def test_intro_fwd_credit_refuses_membership_parse(self):
        self.assertIsNone(
            hugo._parse_related_book_people(
                'Luis Ortiz, intro. by Carol Emshwiller, fwd. by Alex Eisenstien'
            )
        )

    def test_confident_simple_lists_parse(self):
        self.assertEqual(
            hugo._parse_related_book_people('John Clute and John Grant'),
            ('John Clute', 'John Grant'),
        )
        self.assertEqual(
            hugo._parse_related_book_people(
                'Mike Resnick and Joe Siclari, eds.'
            ),
            ('Mike Resnick', 'Joe Siclari'),
        )
        self.assertEqual(
            hugo._parse_related_book_people(
                'Lillian Stewart Carl & John Helfers, eds.'
            ),
            ('Lillian Stewart Carl', 'John Helfers'),
        )
        self.assertEqual(
            hugo._parse_related_book_people(
                'Cathy Fenner, Arnie Fenner and Jim Loehr'
            ),
            ('Cathy Fenner', 'Arnie Fenner', 'Jim Loehr'),
        )
        self.assertEqual(
            hugo._parse_related_book_people(
                'Leo Dillon, Diane Dillon and Byron Preiss'
            ),
            ('Leo Dillon', 'Diane Dillon', 'Byron Preiss'),
        )
        self.assertEqual(
            hugo._parse_related_book_people(
                'Perry A. Chapdelaine, Sr., Tony Chapdelaine and George Hay'
            ),
            (
                'Perry A. Chapdelaine, Sr.',
                'Tony Chapdelaine',
                'George Hay',
            ),
        )
        self.assertEqual(
            hugo._parse_related_book_people(
                'Joy Chant, Ian Ballantine, Betty Ballantine, '
                'George Sharp and David Larkin'
            ),
            (
                'Joy Chant',
                'Ian Ballantine',
                'Betty Ballantine',
                'George Sharp',
                'David Larkin',
            ),
        )
        self.assertEqual(
            hugo._parse_related_book_people('Harry Warner, Jr.'),
            ('Harry Warner, Jr.',),
        )

    def test_aka_parenthetical_is_not_stripped_for_membership(self):
        self.assertFalse(
            hugo._related_person_matches(
                'William Tenn (aka: Philip Klass)',
                'William Tenn',
            )
        )

    def test_fiction_category_does_not_use_membership(self):
        record = hugo._ParsedRecord(
            award_year=2024,
            category=hugo.CATEGORY_BEST_NOVEL,
            status='Winner',
            work_title='Some Desperate Glory',
            work_author='Emily Tesh',
            source_url=URL_2024,
            match_titles=('Some Desperate Glory',),
        )
        self.assertTrue(
            hugo._record_matches(
                record, 'Some Desperate Glory', 'Emily Tesh'
            )
        )
        self.assertFalse(
            hugo._record_matches(
                record,
                'Some Desperate Glory',
                'Emily Tesh & Extra Person',
            )
        )

    def test_best_series_still_uses_whole_string_author(self):
        records = hugo._parse_best_series_html(HTML_SERIES, 2017, URL_2017)
        winner = _find(records, title='The Vorkosigan Saga')[0]
        self.assertTrue(
            hugo._series_record_matches(
                winner, 'Vorkosigan Saga', 'Lois McMaster Bujold'
            )
        )
        self.assertFalse(
            hugo._series_record_matches(
                winner,
                'Vorkosigan Saga',
                'Lois McMaster Bujold & Extra Person',
            )
        )
        self.assertFalse(
            hugo._record_matches(
                winner,
                'The Vorkosigan Saga',
                'Lois McMaster Bujold & Extra Person',
            )
        )


class HugoRelatedLookupTests(unittest.TestCase):
    def setUp(self):
        hugo._archive_records_cache = tuple(
            hugo._parse_supported_categories_html(HTML_1991, 1991, URL_1991)
            + hugo._parse_supported_categories_html(HTML_1998, 1998, URL_1998)
            + hugo._parse_supported_categories_html(HTML_2000, 2000, URL_2000)
            + hugo._parse_supported_categories_html(HTML_2007, 2007, URL_2007)
            + hugo._parse_supported_categories_html(
                HTML_2008_COMPLEX, 2008, URL_2000
            )
        )

    def tearDown(self):
        hugo._archive_records_cache = None

    def test_lookup_1991_card_winner(self):
        results = hugo.lookup(
            'How to Write Science Fiction and Fantasy',
            'Orson Scott Card',
        )
        related = [
            result
            for result in results
            if result.category == 'Best Related Non-Fiction Book'
        ]
        self.assertEqual(len(related), 1)
        result = related[0]
        self.assertEqual(result.award_year, 1991)
        self.assertEqual(result.status, 'Winner')
        self.assertEqual(result.identity_kind, 'work')
        self.assertIsNone(result.rank)
        self.assertEqual(
            qualify_award_result(result).decision,
            QualificationDecision.QUALIFIES,
        )
        self.assertEqual(
            format_award_result(result),
            'Winner - 1991 Hugo Award - Best Related Non-Fiction Book',
        )

    def test_lookup_2000_robinson_winner(self):
        results = hugo.lookup(
            'Science Fiction of the 20th Century',
            'Frank M. Robinson',
        )
        related = [
            result
            for result in results
            if result.category == 'Best Related Book'
        ]
        self.assertEqual(len(related), 1)
        result = related[0]
        self.assertEqual(result.award_year, 2000)
        self.assertEqual(result.status, 'Winner')
        self.assertEqual(result.identity_kind, 'work')
        self.assertIsNone(result.rank)
        self.assertEqual(
            qualify_award_result(result).decision,
            QualificationDecision.QUALIFIES,
        )
        self.assertEqual(
            format_award_result(result),
            'Winner - 2000 Hugo Award - Best Related Book',
        )

    def test_lookup_encyclopedia_with_calibre_ampersand(self):
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
        self.assertEqual(related[0].award_year, 1998)
        self.assertEqual(related[0].status, 'Winner')
        self.assertEqual(
            related[0].work_author,
            'John Clute and John Grant',
        )

    def test_lookup_resnick_speeches_with_editor_convention(self):
        results = hugo.lookup(
            'Worldcon Guest of Honor Speeches',
            'Mike Resnick (ed) & Joe Siclari (ed) & Author One',
        )
        related = [
            result
            for result in results
            if result.category == 'Best Related Book'
        ]
        self.assertEqual(len(related), 1)
        self.assertEqual(related[0].status, 'Finalist')
        self.assertEqual(
            related[0].work_author,
            'Mike Resnick and Joe Siclari, eds.',
        )
        self.assertEqual(
            qualify_award_result(related[0]).decision,
            QualificationDecision.REVIEW,
        )


if __name__ == '__main__':
    unittest.main()
