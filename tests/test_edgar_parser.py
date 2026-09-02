"""Offline coverage for the Edgar Awards Participants Database parser."""

from __future__ import annotations

import math
import unittest

from awards.engine import assess_award_result
from awards.model import AwardResult
from awards.qualifier import QualificationDecision
from awards.registry import EDGAR_NOMINEE_POLICY, find_award_policy
from awards.sources import edgar as src


def _td(field: str, text: str, *, winner: bool = False) -> str:
    marker = ' edgar-winner' if winner else ' '
    return f'<td class="{field}-field{marker}">{text}</td>'


def _row(
    year,
    category,
    title,
    author,
    *,
    winner=False,
    publisher='',
    notes='',
) -> str:
    return (
        '<tr>'
        + _td('award_year', str(year), winner=winner)
        + _td('award_category', category, winner=winner)
        + _td('title', title, winner=winner)
        + _td('authors_name', author, winner=winner)
        + _td('publisherproducer', publisher, winner=winner)
        + _td('notes', notes, winner=winner)
        + '</tr>'
    )


def _blank_row() -> str:
    return _row('', '', '', '', winner=False)


def database_html(
    rows,
    *,
    total=None,
    per_page=100,
    last_page=None,
    include_identity=True,
    include_columns=True,
    caption=True,
) -> str:
    row_html = ''.join(rows)
    count = total if total is not None else max(len(rows), 1)
    pages = last_page
    if pages is None:
        pages = max(1, math.ceil(count / per_page)) if per_page else 1
    pagination = ''
    if pages > 1:
        pagination = (
            '<div class="pagination pdb-pagination">'
            f'<a href="/search-the-database/?listpage={pages}&amp;instance=1"'
            f' title="Last">{pages}</a></div>'
        )
    list_id = 'participants-list-1' if include_identity else 'other-list'
    if include_columns:
        headers = (
            '<th class="award_year">Award Year</th>'
            '<th class="award_category">Award Category</th>'
            '<th class="title">Title</th>'
            "<th class=\"authors_name\">Author's Name</th>"
            '<th class="publisherproducer">Publisher/Producer</th>'
            '<th class="notes">Notes</th>'
        )
    else:
        headers = '<th>Unrelated</th>'
    caption_html = ''
    if caption:
        caption_html = (
            '<caption class="pdb-list-count">'
            f'<span class="list-display-count">Total Records Found: {count}, '
            f'showing {per_page} per page</span></caption>'
        )
    return (
        '<!DOCTYPE html><html><head><title>Search the Edgars Database!</title>'
        '</head><body>'
        f'<div class="wrap pdb-list" id="{list_id}">'
        f'<table class="wp-list-table">{caption_html}'
        f'<thead><tr>{headers}</tr></thead>'
        f'<tbody>{row_html}</tbody></table>{pagination}</div>'
        '</body></html>'
    )


def _parse(html: str):
    return src._parse_database_html(html)


class EdgarParserCoreTests(unittest.TestCase):
    def test_winner_and_nominee_from_edgar_winner_class_not_row_order(self):
        html = database_html(
            [
                _row(
                    2026,
                    'Best Novel',
                    'Fagin the Thief',
                    'Allison Epstein',
                    winner=False,
                ),
                _row(
                    2026,
                    'Best Novel',
                    'The Big Empty',
                    'Robert Crais',
                    winner=True,
                ),
            ]
        )
        parsed = _parse(html)
        by_title = {record.work_title: record for record in parsed.records}
        self.assertEqual(by_title['The Big Empty'].status, 'Winner')
        self.assertEqual(by_title['Fagin the Thief'].status, 'Nominee')
        self.assertIsNone(src._to_award_result(by_title['The Big Empty']).rank)
        self.assertIsNone(src._to_award_result(by_title['Fagin the Thief']).rank)
        self.assertEqual(by_title['The Big Empty'].award_year, 2026)
        self.assertEqual(by_title['Fagin the Thief'].award_year, 2026)

    def test_list_order_does_not_create_a_winner(self):
        html = database_html(
            [
                _row(2026, 'Best Novel', 'First Listed', 'A Author', winner=False),
                _row(2026, 'Best Novel', 'Second Listed', 'B Author', winner=False),
            ]
        )
        parsed = _parse(html)
        self.assertEqual({record.status for record in parsed.records}, {'Nominee'})

    def test_all_blank_pdb_row_is_skipped(self):
        html = database_html(
            [
                _blank_row(),
                _row(
                    2026,
                    'Best Novel',
                    'The Big Empty',
                    'Robert Crais',
                    winner=True,
                ),
                _blank_row(),
            ]
        )
        parsed = _parse(html)
        self.assertEqual(parsed.blank_row_count, 2)
        self.assertEqual([record.work_title for record in parsed.records], ['The Big Empty'])

    def test_unknown_category_emits_nothing(self):
        html = database_html(
            [
                _row(
                    2026,
                    'Best Podcast',
                    'A Future Category Work',
                    'Some Author',
                    winner=True,
                )
            ]
        )
        parsed = _parse(html)
        self.assertEqual(parsed.records, ())
        self.assertIn('Best Podcast', parsed.unknown_categories)

    def test_malformed_table_without_expected_columns_fails_closed(self):
        html = database_html(
            [_row(2026, 'Best Novel', 'The Big Empty', 'Robert Crais', winner=True)],
            include_columns=False,
        )
        with self.assertRaises(src.EdgarSourceError):
            _parse(html)

    def test_challenge_html_fails_closed(self):
        html = '<html><body>Just a moment... checking your browser</body></html>'
        with self.assertRaises(src.EdgarSourceError):
            _parse(html)

    def test_wordpress_error_page_fails_closed(self):
        html = (
            '<html><body>There has been a critical error on this website.'
            '</body></html>'
        )
        with self.assertRaises(src.EdgarSourceError):
            _parse(html)

    def test_missing_included_title_does_not_emit(self):
        html = database_html(
            [_row(2026, 'Best Novel', '', 'Robert Crais', winner=True)]
        )
        self.assertEqual(_parse(html).records, ())

    def test_missing_included_author_does_not_emit(self):
        html = database_html(
            [_row(2026, 'Best Novel', 'The Big Empty', '', winner=True)]
        )
        self.assertEqual(_parse(html).records, ())

    def test_html_entities_and_whitespace_are_cleaned(self):
        html = database_html(
            [
                _row(
                    2026,
                    'Best Novel',
                    '  The&nbsp;Big   Empty  ',
                    'Robert&amp; Crais',
                    winner=True,
                )
            ]
        )
        record = _parse(html).records[0]
        self.assertEqual(record.work_title, 'The Big Empty')
        self.assertEqual(record.work_author, 'Robert& Crais')

    def test_ceremony_year_is_preserved(self):
        html = database_html(
            [
                _row(
                    2026,
                    'Best Novel',
                    'The Big Empty',
                    'Robert Crais',
                    winner=True,
                )
            ]
        )
        record = _parse(html).records[0]
        self.assertEqual(record.award_year, 2026)
        result = src._to_award_result(record)
        self.assertEqual(result.award_year, 2026)
        self.assertEqual(result.award_name, 'Edgar Award')
        self.assertEqual(result.source_name, 'Mystery Writers of America')
        self.assertEqual(result.source_url, src.SEARCH_DATABASE_URL)
        self.assertEqual(result.identity_kind, 'work')
        self.assertIsNone(result.rank)


class EdgarIncludedCategoryTests(unittest.TestCase):
    def _assert_included(self, category, title='A Title', author='An Author'):
        html = database_html(
            [_row(2026, category, title, author, winner=True)]
        )
        parsed = _parse(html)
        self.assertEqual(len(parsed.records), 1, category)
        record = parsed.records[0]
        expected = src._canonical_category(category)
        self.assertEqual(record.category, expected)
        self.assertEqual(record.status, 'Winner')
        return record

    def test_all_twelve_included_categories(self):
        self._assert_included('Best Novel')
        self._assert_included('Best First Novel')
        self._assert_included('Best Paperback Original')
        self._assert_included('Best Fact Crime')
        self._assert_included('Best Critical/Biographical Work')
        self._assert_included('Best Short Story', '"Story" - Venue')
        self._assert_included('Best Juvenile')
        self._assert_included('Best Young Adult')
        self._assert_included('The Robert L. Fish Memorial Award', '"Story" - EQMM')
        self._assert_included('Mary Higgins Clark Award')
        record = self._assert_included(
            "G.P. Putnam's Sons Sue Grafton Memoriam Award"
        )
        self.assertEqual(
            record.category,
            "G.P. Putnam's Sons Sue Grafton Memorial Award",
        )
        self._assert_included('The Lilian Jackson Braun Memorial Award')


class EdgarExcludedCategoryTests(unittest.TestCase):
    def _assert_excluded(self, category, title='A Title', author='An Author'):
        html = database_html(
            [_row(2026, category, title, author, winner=True)]
        )
        parsed = _parse(html)
        self.assertEqual(parsed.records, (), category)
        self.assertGreaterEqual(parsed.excluded_row_count, 1, category)

    def test_media_person_service_and_special_categories_are_excluded(self):
        self._assert_excluded('Best Episode in a TV Series', 'End of the Line')
        self._assert_excluded('Best Episode in a TV Seriers', 'End of the Line')
        self._assert_excluded('Best Episode in a TV Seriess', 'End of the Line')
        self._assert_excluded('Best Motion Picture')
        self._assert_excluded('Best Play')
        self._assert_excluded('Best Radio Drama')
        self._assert_excluded('Best TV Feature or MiniSeries')
        self._assert_excluded('Best Foreign film')
        self._assert_excluded('The Grand Master', '', 'Donna Andrews')
        self._assert_excluded('The Raven Award', '', 'Book Passage')
        self._assert_excluded('The Ellery Queen Award')
        self._assert_excluded("The President's Award")
        self._assert_excluded('Outstanding Mystery Criticism')
        self._assert_excluded('Special Edgars')
        self._assert_excluded('Book Jacket Award')

    def test_tv_typos_are_not_normalized_into_an_included_category(self):
        self.assertEqual(
            src._classify_category('Best Episode in a TV Seriers'),
            'excluded',
        )
        self.assertEqual(
            src._classify_category('Best Episode in a TV Seriess'),
            'excluded',
        )
        self.assertEqual(
            src._canonical_category('Best Episode in a TV Seriers'),
            'Best Episode in a TV Seriers',
        )


class EdgarGraftonCanonicalizationTests(unittest.TestCase):
    def test_memoriam_typo_becomes_memorial_for_awardresult_category(self):
        html = database_html(
            [
                _row(
                    2026,
                    "G.P. Putnam's Sons Sue Grafton Memoriam Award",
                    'A Grafton Book',
                    'A Grafton Author',
                    winner=True,
                )
            ]
        )
        record = _parse(html).records[0]
        self.assertEqual(
            record.category,
            "G.P. Putnam's Sons Sue Grafton Memorial Award",
        )
        result = src._to_award_result(record)
        self.assertEqual(
            result.category,
            "G.P. Putnam's Sons Sue Grafton Memorial Award",
        )

    def test_no_other_memoriam_spelling_is_rewritten(self):
        html = database_html(
            [
                _row(
                    2026,
                    'Some Other Memoriam Award',
                    'A Book',
                    'An Author',
                    winner=True,
                )
            ]
        )
        parsed = _parse(html)
        self.assertEqual(parsed.records, ())
        self.assertIn('Some Other Memoriam Award', parsed.unknown_categories)
        self.assertEqual(
            src._canonical_category('Some Other Memoriam Award'),
            'Some Other Memoriam Award',
        )


class EdgarShortStoryTitleTests(unittest.TestCase):
    def test_modern_quoted_story_and_venue(self):
        html = database_html(
            [
                _row(
                    2026,
                    'Best Short Story',
                    '"Julius Katz Draws a Straight Flush" - AHMM September-October',
                    'Dave Zeltserman',
                    winner=True,
                )
            ]
        )
        record = _parse(html).records[0]
        self.assertEqual(record.work_title, 'Julius Katz Draws a Straight Flush')
        self.assertEqual(record.notes, 'AHMM September-October')
        self.assertNotIn('AHMM', record.work_title)

    def test_curly_quotes_are_supported(self):
        html = database_html(
            [
                _row(
                    2026,
                    'Best Short Story',
                    '\u201cJulius Katz Draws a Straight Flush\u201d \u2013 AHMM',
                    'Dave Zeltserman',
                    winner=True,
                )
            ]
        )
        record = _parse(html).records[0]
        self.assertEqual(record.work_title, 'Julius Katz Draws a Straight Flush')
        self.assertEqual(record.notes, 'AHMM')

    def test_historical_plain_story_title_is_unchanged(self):
        html = database_html(
            [
                _row(
                    1954,
                    'Best Short Story',
                    'Diagnosis: Homicide',
                    'Lawrence G. Blochman',
                    winner=True,
                )
            ]
        )
        record = _parse(html).records[0]
        self.assertEqual(record.work_title, 'Diagnosis: Homicide')
        self.assertIsNone(record.notes)

    def test_unquoted_dashed_title_is_not_split(self):
        html = database_html(
            [
                _row(
                    2026,
                    'Best Novel',
                    'Murderland: Crime and Bloodlust in the Time of Serial Killers',
                    'Caroline Fraser',
                    winner=True,
                )
            ]
        )
        record = _parse(html).records[0]
        self.assertEqual(
            record.work_title,
            'Murderland: Crime and Bloodlust in the Time of Serial Killers',
        )

    def test_robert_l_fish_uses_the_same_quoted_venue_logic(self):
        html = database_html(
            [
                _row(
                    2026,
                    'The Robert L. Fish Memorial Award',
                    '"How It Happened" - EQMM',
                    'Billie Kay Fern',
                    winner=True,
                )
            ]
        )
        record = _parse(html).records[0]
        self.assertEqual(record.work_title, 'How It Happened')
        self.assertEqual(record.notes, 'EQMM')
        self.assertEqual(record.category, 'The Robert L. Fish Memorial Award')


class EdgarContributorTests(unittest.TestCase):
    def test_first_last_is_preserved(self):
        html = database_html(
            [_row(2026, 'Best Novel', 'The Big Empty', 'Robert Crais', winner=True)]
        )
        self.assertEqual(_parse(html).records[0].work_author, 'Robert Crais')

    def test_comma_separated_contributors_are_not_inverted(self):
        html = database_html(
            [
                _row(
                    2026,
                    'Best Novel',
                    'A Joint Book',
                    'Declan Burke, John Connolly',
                    winner=True,
                )
            ]
        )
        self.assertEqual(
            _parse(html).records[0].work_author,
            'Declan Burke, John Connolly',
        )
        self.assertNotEqual(
            _parse(html).records[0].work_author,
            'John Connolly Declan Burke',
        )

    def test_ampersand_credit_is_kept(self):
        html = database_html(
            [_row(2026, 'Best Novel', 'A Book', 'A & B', winner=True)]
        )
        self.assertEqual(_parse(html).records[0].work_author, 'A & B')

    def test_suffix_and_credential_are_kept(self):
        html = database_html(
            [_row(2026, 'Best Novel', 'A Book', 'D.P. Lyle, MD', winner=True)]
        )
        self.assertEqual(_parse(html).records[0].work_author, 'D.P. Lyle, MD')


class EdgarCrossCategoryTests(unittest.TestCase):
    def test_invisible_city_both_2015_categories_survive(self):
        html = database_html(
            [
                _row(
                    2015,
                    'Best First Novel',
                    'Invisible City',
                    'Julia Dahl',
                    winner=False,
                ),
                _row(
                    2015,
                    'Mary Higgins Clark Award',
                    'Invisible City',
                    'Julia Dahl',
                    winner=False,
                ),
            ]
        )
        records = _parse(html).records
        self.assertEqual(len(records), 2)
        categories = {record.category for record in records}
        self.assertEqual(
            categories,
            {'Best First Novel', 'Mary Higgins Clark Award'},
        )

    def test_the_catch_short_story_and_fish_survive(self):
        html = database_html(
            [
                _row(
                    2008,
                    'Best Short Story',
                    'The Catch',
                    'Mark Ammons',
                    winner=False,
                ),
                _row(
                    2008,
                    'The Robert L. Fish Memorial Award',
                    'The Catch',
                    'Mark Ammons',
                    winner=True,
                ),
            ]
        )
        records = _parse(html).records
        self.assertEqual(len(records), 2)
        by_category = {record.category: record for record in records}
        self.assertEqual(by_category['Best Short Story'].status, 'Nominee')
        self.assertEqual(
            by_category['The Robert L. Fish Memorial Award'].status,
            'Winner',
        )

    def test_the_green_stone_first_novel_and_novel_survive(self):
        html = database_html(
            [
                _row(
                    1962,
                    'Best First Novel',
                    'The Green Stone',
                    'Suzanne Blanc',
                    winner=True,
                ),
                _row(
                    1962,
                    'Best Novel',
                    'The Green Stone',
                    'Suzanne Blanc',
                    winner=False,
                ),
            ]
        )
        records = _parse(html).records
        self.assertEqual(len(records), 2)
        by_category = {record.category: record for record in records}
        self.assertEqual(by_category['Best First Novel'].status, 'Winner')
        self.assertEqual(by_category['Best Novel'].status, 'Nominee')

    def test_same_category_duplicate_prefers_winner(self):
        html = database_html(
            [
                _row(2026, 'Best Novel', 'Same Book', 'Same Author', winner=False),
                _row(2026, 'Best Novel', 'Same Book', 'Same Author', winner=True),
            ]
        )
        records = _parse(html).records
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].status, 'Winner')

    def test_multiple_winners_in_one_category_year_are_preserved(self):
        html = database_html(
            [
                _row(2026, 'Best Novel', 'Winner One', 'Author One', winner=True),
                _row(2026, 'Best Novel', 'Winner Two', 'Author Two', winner=True),
            ]
        )
        records = _parse(html).records
        self.assertEqual(len(records), 2)
        self.assertEqual({record.status for record in records}, {'Winner'})
        for record in records:
            self.assertIsNone(src._to_award_result(record).rank)

    def test_nominee_is_not_promoted_when_winner_is_absent(self):
        html = database_html(
            [
                _row(
                    2027,
                    'Best Novel',
                    'Future Nominee',
                    'Future Author',
                    winner=False,
                )
            ]
        )
        records = _parse(html).records
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].status, 'Nominee')


class EdgarPaginationDiscoveryTests(unittest.TestCase):
    def test_page_count_follows_live_banner_not_a_hardcoded_38(self):
        html = database_html(
            [_row(2026, 'Best Novel', 'A', 'B', winner=True)],
            total=250,
            per_page=100,
        )
        self.assertEqual(src._discover_page_count(html), 3)
        html_one = database_html(
            [_row(2026, 'Best Novel', 'A', 'B', winner=True)],
            total=12,
            per_page=100,
        )
        self.assertEqual(src._discover_page_count(html_one), 1)


class EdgarPolicyTests(unittest.TestCase):
    def _result(self, **overrides):
        values = {
            'work_title': 'The Big Empty',
            'work_author': 'Robert Crais',
            'award_name': 'Edgar Award',
            'award_year': 2026,
            'category': 'Best Novel',
            'status': 'Winner',
            'rank': None,
            'source_name': 'Mystery Writers of America',
            'source_url': src.SEARCH_DATABASE_URL,
            'identity_kind': 'work',
        }
        values.update(overrides)
        return AwardResult(**values)

    def test_winner_qualifies(self):
        winner = self._result()
        self.assertIs(find_award_policy(winner), EDGAR_NOMINEE_POLICY)
        assessment = assess_award_result(winner)
        self.assertEqual(
            assessment.qualification.decision,
            QualificationDecision.QUALIFIES,
        )
        self.assertIsNone(winner.rank)

    def test_nominee_qualifies_with_no_rank(self):
        nominee = self._result(
            work_title='Fagin the Thief',
            work_author='Allison Epstein',
            status='Nominee',
        )
        self.assertIs(find_award_policy(nominee), EDGAR_NOMINEE_POLICY)
        self.assertEqual(
            EDGAR_NOMINEE_POLICY.qualifying_statuses,
            frozenset({'nominee'}),
        )
        self.assertIsNone(EDGAR_NOMINEE_POLICY.category)
        self.assertEqual(EDGAR_NOMINEE_POLICY.start_year, 1946)
        assessment = assess_award_result(nominee)
        self.assertEqual(
            assessment.qualification.decision,
            QualificationDecision.QUALIFIES,
        )
        self.assertIsNone(nominee.rank)

    def test_unrelated_nominee_does_not_gain_edgar_policy(self):
        hugo = AwardResult(
            work_title='The Graveyard Book',
            work_author='Neil Gaiman',
            award_name='Hugo Award',
            award_year=2009,
            category='Best Novel',
            status='Nominee',
            rank=None,
            source_name='The Hugo Awards',
            source_url='https://www.thehugoawards.org/hugo-history/2009-hugo-awards/',
        )
        self.assertIsNone(find_award_policy(hugo))
        assessment = assess_award_result(hugo)
        self.assertEqual(
            assessment.qualification.decision,
            QualificationDecision.REVIEW,
        )


if __name__ == '__main__':
    unittest.main()
