"""Offline coverage for Hugo Best Poem parsing, lookup, and fail-closed years."""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from awards.formatter import format_award_result
from awards.qualifier import QualificationDecision, qualify_award_result
from awards.sources import hugo

URL_2024 = 'https://www.thehugoawards.org/hugo-history/2024-hugo-awards/'
URL_2025 = 'https://www.thehugoawards.org/hugo-history/2025-hugo-awards/'
URL_2026 = 'https://www.thehugoawards.org/hugo-history/2026-hugo-awards/'

HTML_2025 = """
<p><strong>Best Poem</strong></p>
<ul>
<li class="winner">“A War of Words” by Marie Brennan (<em>Strange Horizons</em>, September 2024)</li>
<li><em>Calypso </em>by Oliver K. Langmead (Titan)</li>
<li>“there are no taxis for the dead” by Angela Liu (<em>Uncanny Magazine</em>, Issue 58)</li>
<li>“Your Visiting Dragon” by Devan Barlow (<em>Strange Horizons</em>, Fund Drive 2024)</li>
<li>“Ever Noir” by Mari Ness (<em>Haven Spec Magazine</em>, Issue 16, July 2024)</li>
<li>“We Drink Lava” by Ai Jiang (<em>Uncanny Magazine</em>, Issue 56)</li>
</ul>
<p>219 ballots cast for 266 nominees, finalists range 11 to 26.</p>
"""

HTML_2026 = """
<p><strong>Best Poem</strong></p>
<ul>
<li>“Care for Lightning” by Mari Ness (<em>Uncanny Magazine</em>, Issue 62)</li>
<li>“Hex Supply Customer Support Log” by Elis Montgomery (<em>Strange Horizons</em>, Issue 25 August 2025)</li>
<li>“How to Become a Sea Witch” by Theodora Goss (<em>The Orange &#038; Bee</em>, Issue 5)</li>
<li>“Landing: Seattle” by Brandon O&#8217;Brien (Seattle Worldcon 2025 Opening Ceremony)</li>
<li>“The Mourning Robot” by Angela Liu (<em>Uncanny Magazine</em>, Issue 66)</li>
<li>“The World to Come” by Jennifer Hudak (<em>Strange Horizons</em>, Issue 22 December 2025)</li>
</ul>
<p>202 ballots cast for 229 nominees. Finalists range 12-35.</p>
"""

HTML_2025_OTHER_CATEGORIES = """
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
"""

HTML_2025_ARCHIVE = HTML_2025_OTHER_CATEGORIES + HTML_2025
HTML_2026_ARCHIVE = HTML_2025_OTHER_CATEGORIES + HTML_2026


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


class HugoBestPoemParserTests(unittest.TestCase):
    def test_2025_winner_strips_curly_quotes_and_publication(self):
        records = hugo._parse_category_html(
            HTML_2025, 2025, URL_2025, hugo.CATEGORY_BEST_POEM
        )
        winner = _find(
            records, title='A War of Words', author='Marie Brennan'
        )
        self.assertEqual(len(winner), 1)
        self.assertEqual(winner[0].category, 'Best Poem')
        self.assertEqual(winner[0].status, 'Winner')
        self.assertNotIn('Strange Horizons', winner[0].work_author)
        result = hugo._to_award_result(winner[0])
        self.assertEqual(result.identity_kind, 'work')
        self.assertIsNone(result.rank)
        self.assertEqual(result.work_title, 'A War of Words')

    def test_2025_unquoted_calypso_dialect(self):
        records = hugo._parse_category_html(
            HTML_2025, 2025, URL_2025, hugo.CATEGORY_BEST_POEM
        )
        calypso = _find(
            records, title='Calypso', author='Oliver K. Langmead'
        )
        self.assertEqual(len(calypso), 1)
        self.assertEqual(calypso[0].status, 'Finalist')
        self.assertNotIn('Titan', calypso[0].work_author)

    def test_quoted_lowercase_title_without_surrounding_quotes(self):
        records = hugo._parse_category_html(
            HTML_2025, 2025, URL_2025, hugo.CATEGORY_BEST_POEM
        )
        taxis = _find(
            records,
            title='there are no taxis for the dead',
            author='Angela Liu',
        )
        self.assertEqual(len(taxis), 1)
        self.assertEqual(taxis[0].work_title, 'there are no taxis for the dead')
        self.assertNotIn('\u201c', taxis[0].work_title)
        self.assertNotIn('"', taxis[0].work_title)

    def test_2026_all_finalists_no_invented_winner(self):
        records = hugo._parse_category_html(
            HTML_2026, 2026, URL_2026, hugo.CATEGORY_BEST_POEM
        )
        self.assertEqual(len(records), 6)
        self.assertTrue(all(record.status == 'Finalist' for record in records))
        care = _find(
            records, title='Care for Lightning', author='Mari Ness'
        )
        self.assertEqual(len(care), 1)
        self.assertIsNone(hugo._to_award_result(care[0]).rank)


class HugoBestPoemLookupTests(unittest.TestCase):
    def setUp(self):
        hugo._archive_records_cache = tuple(
            hugo._parse_supported_categories_html(HTML_2025, 2025, URL_2025)
            + hugo._parse_supported_categories_html(HTML_2026, 2026, URL_2026)
        )

    def tearDown(self):
        hugo._archive_records_cache = None

    def test_lookup_2025_winner(self):
        results = hugo.lookup('A War of Words', 'Marie Brennan')
        poems = [
            result for result in results if result.category == 'Best Poem'
        ]
        self.assertEqual(len(poems), 1)
        result = poems[0]
        self.assertEqual(result.award_year, 2025)
        self.assertEqual(result.status, 'Winner')
        self.assertEqual(result.identity_kind, 'work')
        self.assertIsNone(result.rank)
        self.assertEqual(
            qualify_award_result(result).decision,
            QualificationDecision.QUALIFIES,
        )
        self.assertEqual(
            format_award_result(result),
            'Winner - 2025 Hugo Award - Best Poem',
        )

    def test_lookup_2025_finalist_is_review(self):
        results = hugo.lookup('Calypso', 'Oliver K. Langmead')
        poems = [
            result for result in results if result.category == 'Best Poem'
        ]
        self.assertEqual(len(poems), 1)
        self.assertEqual(poems[0].status, 'Finalist')
        self.assertEqual(
            qualify_award_result(poems[0]).decision,
            QualificationDecision.REVIEW,
        )

    def test_lookup_2026_finalist(self):
        results = hugo.lookup('Care for Lightning', 'Mari Ness')
        poems = [
            result for result in results if result.category == 'Best Poem'
        ]
        self.assertEqual(len(poems), 1)
        result = poems[0]
        self.assertEqual(result.award_year, 2026)
        self.assertEqual(result.category, 'Best Poem')
        self.assertEqual(result.status, 'Finalist')
        self.assertIsNone(result.rank)
        self.assertEqual(result.identity_kind, 'work')
        self.assertEqual(
            qualify_award_result(result).decision,
            QualificationDecision.REVIEW,
        )
        self.assertEqual(
            format_award_result(result),
            'Finalist - 2026 Hugo Award - Best Poem',
        )


class HugoBestPoemCoverageTests(unittest.TestCase):
    def test_required_only_in_2025_and_2026(self):
        self.assertTrue(hugo._year_requires_best_poem(2025))
        self.assertTrue(hugo._year_requires_best_poem(2026))
        self.assertFalse(hugo._year_requires_best_poem(2024))
        self.assertFalse(hugo._year_requires_best_poem(2027))
        self.assertFalse(hugo._year_requires_best_poem(2028))

    def test_2025_archive_without_poem_fails_closed(self):
        hugo._archive_records_cache = None
        body = json.dumps(
            [
                _archive_item(
                    '2025 Hugo Awards',
                    URL_2025,
                    HTML_2025_OTHER_CATEGORIES,
                    '2025-hugo-awards',
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
                'no Best Poem records could be parsed',
                str(ctx.exception),
            )
        finally:
            hugo._archive_records_cache = None

    def test_2026_archive_without_poem_fails_closed(self):
        hugo._archive_records_cache = None
        body = json.dumps(
            [
                _archive_item(
                    '2026 Hugo Awards',
                    URL_2026,
                    HTML_2025_OTHER_CATEGORIES,
                    '2026-hugo-awards',
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
                'no Best Poem records could be parsed',
                str(ctx.exception),
            )
        finally:
            hugo._archive_records_cache = None

    def test_2025_archive_with_poem_succeeds(self):
        hugo._archive_records_cache = None
        body = json.dumps(
            [
                _archive_item(
                    '2025 Hugo Awards',
                    URL_2025,
                    HTML_2025_ARCHIVE,
                    '2025-hugo-awards',
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
            poems = [
                record
                for record in records
                if record.category == 'Best Poem'
            ]
            self.assertEqual(poems[0].work_title, 'A War of Words')
            self.assertEqual(poems[0].status, 'Winner')
        finally:
            hugo._archive_records_cache = None

    def test_2024_archive_does_not_require_best_poem(self):
        hugo._archive_records_cache = None
        body = json.dumps(
            [
                _archive_item(
                    '2024 Hugo Awards',
                    URL_2024,
                    HTML_2025_OTHER_CATEGORIES,
                    '2024-hugo-awards',
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
                'Best Poem', [record.category for record in records]
            )
        finally:
            hugo._archive_records_cache = None


if __name__ == '__main__':
    unittest.main()
