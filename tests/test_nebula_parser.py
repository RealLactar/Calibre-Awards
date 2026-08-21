"""Offline unittest coverage for the Nebula Best Novel parser and helpers."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from awards.sources.nebula import (
    _best_novel_status,
    _parse_best_novel_html,
    _record_matches,
    _titles_match,
    _to_award_result,
)

FIXTURES = Path(__file__).resolve().parent / 'fixtures' / 'nebula'


def _load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding='utf-8')


def _find_records(records, *, title: str, author: str | None = None):
    matches = [record for record in records if record.work_title == title]
    if author is not None:
        matches = [record for record in matches if record.work_author == author]
    return matches


class NebulaParserFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html_1965 = _load_fixture('best_novel_1965.html')
        cls.html_2015 = _load_fixture('best_novel_2015.html')
        cls.html_2025 = _load_fixture('best_novel_2025.html')
        cls.records_1965 = _parse_best_novel_html(cls.html_1965)
        cls.records_2015 = _parse_best_novel_html(cls.html_2015)
        cls.records_2025 = _parse_best_novel_html(cls.html_2025)
        cls.all_records = (
            cls.records_1965 + cls.records_2015 + cls.records_2025
        )

    def test_dune_winner_parses_once(self):
        matches = _find_records(
            self.records_1965,
            title='Dune',
            author='Frank Herbert',
        )
        self.assertEqual(len(matches), 1)
        record = matches[0]
        self.assertEqual(record.award_year, 1965)
        self.assertEqual(record.status, 'Winner')
        self.assertEqual(record.work_title, 'Dune')
        self.assertEqual(record.work_author, 'Frank Herbert')

    def test_fifth_season_nominated_parses_once(self):
        matches = _find_records(
            self.records_2015,
            title='The Fifth Season',
            author='N.K. Jemisin',
        )
        self.assertEqual(len(matches), 1)
        record = matches[0]
        self.assertEqual(record.award_year, 2015)
        self.assertEqual(record.status, 'Nominated')
        self.assertEqual(record.work_title, 'The Fifth Season')
        self.assertEqual(record.work_author, 'N.K. Jemisin')

    def test_updraft_remains_nominated_despite_cross_category_star(self):
        # Fixture preserves Norton winner star/text alongside Best Novel Nominated.
        self.assertIn('fa-star', self.html_2015)
        self.assertIn('Winner', self.html_2015)
        self.assertIn(
            'Andre Norton Nebula Award for Middle Grade and Young Adult Fiction',
            self.html_2015,
        )

        matches = _find_records(
            self.records_2015,
            title='Updraft',
            author='Fran Wilde',
        )
        self.assertEqual(len(matches), 1)
        record = matches[0]
        self.assertEqual(record.award_year, 2015)
        self.assertEqual(record.status, 'Nominated')

        # Explicit: star + Norton Winner text are present, but Best Novel stays Nominated.
        href_at = self.html_2015.index('nominated-work/updraft/')
        li_start = self.html_2015.rfind('<li>', 0, href_at)
        li_end = self.html_2015.index('</li>', href_at) + len('</li>')
        updraft_li = self.html_2015[li_start:li_end]
        self.assertIn('fa fa-star', updraft_li)
        self.assertIn('Winner', updraft_li)
        self.assertIn('Andre Norton', updraft_li)
        # Collapse tags to approximate the parser's text-node view of this <li>.
        updraft_text = re.sub(r'<[^>]+>', ' ', updraft_li)
        updraft_text = re.sub(r'\s+', ' ', updraft_text).strip()
        self.assertEqual(_best_novel_status(updraft_text), 'Nominated')
        self.assertIsNone(
            re.search(r'Winner,\s*Best Novel\s+in\s+\d{4}', updraft_text, re.I)
        )

    def test_buffalo_hunter_hunter_winner_parses_once(self):
        matches = _find_records(
            self.records_2025,
            title='The Buffalo Hunter Hunter',
            author='Stephen Graham Jones',
        )
        self.assertEqual(len(matches), 1)
        record = matches[0]
        self.assertEqual(record.award_year, 2025)
        self.assertEqual(record.status, 'Winner')
        self.assertEqual(record.work_title, 'The Buffalo Hunter Hunter')
        self.assertEqual(record.work_author, 'Stephen Graham Jones')
        # Compact citation layout keeps title/author out of separate nominee links.
        self.assertIn(', by Stephen Graham Jones', self.html_2025)

    def test_record_matches_for_expected_pairs(self):
        dune = _find_records(
            self.records_1965, title='Dune', author='Frank Herbert'
        )[0]
        fifth = _find_records(
            self.records_2015,
            title='The Fifth Season',
            author='N.K. Jemisin',
        )[0]
        updraft = _find_records(
            self.records_2015, title='Updraft', author='Fran Wilde'
        )[0]
        buffalo = _find_records(
            self.records_2025,
            title='The Buffalo Hunter Hunter',
            author='Stephen Graham Jones',
        )[0]

        self.assertTrue(_record_matches(dune, 'Dune', 'Frank Herbert'))
        self.assertTrue(
            _record_matches(fifth, 'The Fifth Season', 'N.K. Jemisin')
        )
        self.assertTrue(_record_matches(updraft, 'Updraft', 'Fran Wilde'))
        self.assertTrue(
            _record_matches(
                buffalo,
                'The Buffalo Hunter Hunter',
                'Stephen Graham Jones',
            )
        )

    def test_to_award_result_conversion(self):
        dune = _find_records(
            self.records_1965, title='Dune', author='Frank Herbert'
        )[0]
        fifth = _find_records(
            self.records_2015,
            title='The Fifth Season',
            author='N.K. Jemisin',
        )[0]
        buffalo = _find_records(
            self.records_2025,
            title='The Buffalo Hunter Hunter',
            author='Stephen Graham Jones',
        )[0]

        dune_result = _to_award_result(dune)
        self.assertEqual(dune_result.award_name, 'Nebula Award')
        self.assertEqual(dune_result.category, 'Best Novel')
        self.assertEqual(dune_result.status, 'Winner')
        self.assertEqual(dune_result.identity_kind, 'work')
        self.assertIsNone(dune_result.rank)
        self.assertEqual(dune_result.source_name, 'Nebula Awards')
        self.assertTrue(
            dune_result.source_url.startswith('https://nebulas.sfwa.org/')
        )

        fifth_result = _to_award_result(fifth)
        self.assertEqual(fifth_result.award_name, 'Nebula Award')
        self.assertEqual(fifth_result.category, 'Best Novel')
        self.assertEqual(fifth_result.status, 'Nominated')
        self.assertIsNone(fifth_result.rank)
        self.assertEqual(fifth_result.source_name, 'Nebula Awards')
        self.assertTrue(
            fifth_result.source_url.startswith('https://nebulas.sfwa.org/')
        )

        buffalo_result = _to_award_result(buffalo)
        self.assertEqual(buffalo_result.award_name, 'Nebula Award')
        self.assertEqual(buffalo_result.category, 'Best Novel')
        self.assertEqual(buffalo_result.status, 'Winner')
        self.assertIsNone(buffalo_result.rank)
        self.assertEqual(buffalo_result.source_name, 'Nebula Awards')
        self.assertTrue(
            buffalo_result.source_url.startswith('https://nebulas.sfwa.org/')
        )

    def test_fixture_records_have_unique_keys(self):
        keys = [
            (
                record.award_year,
                record.status,
                record.work_title.casefold(),
                record.work_author.casefold(),
                record.source_url,
            )
            for record in self.all_records
        ]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(len(self.all_records), 4)

    def test_standalone_ampersand_matches_and(self):
        self.assertTrue(
            _titles_match(
                'Jonathan Strange and Mr Norrell',
                'Jonathan Strange & Mr Norrell',
            )
        )
        self.assertTrue(
            _titles_match(
                'Jonathan Strange & Mr Norrell',
                'Jonathan Strange and Mr Norrell',
            )
        )
        self.assertTrue(_titles_match('Smith & Jones', 'Smith and Jones'))
        self.assertFalse(_titles_match('The City', 'The City & The City'))


if __name__ == '__main__':
    unittest.main()
