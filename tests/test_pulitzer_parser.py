"""Offline unittest coverage for the Pulitzer HTML parser and match/convert helpers."""

from __future__ import annotations

import unittest
from pathlib import Path

from awards.sources.pulitzer import (
    _parse_category_html,
    _record_matches,
    _titles_match,
    _to_award_result,
)

FIXTURES = Path(__file__).resolve().parent / 'fixtures' / 'pulitzer'
FICTION_URL = 'https://www.pulitzer.org/prize-winners-by-category/219'
NOVEL_URL = 'https://www.pulitzer.org/prize-winners-by-category/261'


def _load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding='utf-8')


def _find_records(records, *, title: str, author: str):
    return [
        record
        for record in records
        if record.work_title == title and record.work_author == author
    ]


class PulitzerParserFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fiction_html = _load_fixture('fiction_excerpt.html')
        cls.novel_html = _load_fixture('novel_excerpt.html')
        cls.fiction_records = _parse_category_html(
            cls.fiction_html,
            'Fiction',
            FICTION_URL,
        )
        cls.novel_records = _parse_category_html(
            cls.novel_html,
            'Novel',
            NOVEL_URL,
        )

    def test_beloved_winner_parses_once(self):
        matches = _find_records(
            self.fiction_records,
            title='Beloved',
            author='Toni Morrison',
        )
        self.assertEqual(len(matches), 1)
        record = matches[0]
        self.assertEqual(record.award_year, 1988)
        self.assertEqual(record.category, 'Fiction')
        self.assertEqual(record.status, 'Winner')
        self.assertEqual(record.work_title, 'Beloved')
        self.assertEqual(record.work_author, 'Toni Morrison')

    def test_things_they_carried_finalist_deduped_to_once(self):
        matches = _find_records(
            self.fiction_records,
            title='The Things They Carried',
            author="Tim O'Brien",
        )
        self.assertEqual(len(matches), 1)
        record = matches[0]
        self.assertEqual(record.award_year, 1991)
        self.assertEqual(record.category, 'Fiction')
        self.assertEqual(record.status, 'Finalist')
        self.assertEqual(record.work_title, 'The Things They Carried')
        self.assertEqual(record.work_author, "Tim O'Brien")

    def test_grapes_of_wrath_winner_parses_once(self):
        matches = _find_records(
            self.novel_records,
            title='The Grapes of Wrath',
            author='John Steinbeck',
        )
        self.assertEqual(len(matches), 1)
        record = matches[0]
        self.assertEqual(record.award_year, 1940)
        self.assertEqual(record.category, 'Novel')
        self.assertEqual(record.status, 'Winner')
        self.assertEqual(record.work_title, 'The Grapes of Wrath')
        self.assertEqual(record.work_author, 'John Steinbeck')

    def test_fiction_record_keys_are_unique(self):
        keys = [
            (
                record.award_year,
                record.status,
                record.work_title.casefold(),
                record.work_author.casefold(),
            )
            for record in self.fiction_records
        ]
        self.assertEqual(len(keys), len(set(keys)))

    def test_record_matches_for_expected_pairs(self):
        beloved = _find_records(
            self.fiction_records,
            title='Beloved',
            author='Toni Morrison',
        )[0]
        things = _find_records(
            self.fiction_records,
            title='The Things They Carried',
            author="Tim O'Brien",
        )[0]
        grapes = _find_records(
            self.novel_records,
            title='The Grapes of Wrath',
            author='John Steinbeck',
        )[0]

        self.assertTrue(_record_matches(beloved, 'Beloved', 'Toni Morrison'))
        self.assertTrue(
            _record_matches(things, 'The Things They Carried', "Tim O'Brien")
        )
        self.assertTrue(
            _record_matches(grapes, 'The Grapes of Wrath', 'John Steinbeck')
        )

    def test_to_award_result_conversion(self):
        beloved = _find_records(
            self.fiction_records,
            title='Beloved',
            author='Toni Morrison',
        )[0]
        things = _find_records(
            self.fiction_records,
            title='The Things They Carried',
            author="Tim O'Brien",
        )[0]
        grapes = _find_records(
            self.novel_records,
            title='The Grapes of Wrath',
            author='John Steinbeck',
        )[0]

        beloved_result = _to_award_result(beloved)
        self.assertEqual(beloved_result.award_name, 'Pulitzer Prize')
        self.assertEqual(beloved_result.source_name, 'Pulitzer Prizes')
        self.assertEqual(beloved_result.category, 'Fiction')
        self.assertEqual(beloved_result.award_year, 1988)
        self.assertEqual(beloved_result.status, 'Winner')
        self.assertEqual(beloved_result.source_url, FICTION_URL)
        self.assertEqual(beloved_result.work_title, 'Beloved')
        self.assertEqual(beloved_result.work_author, 'Toni Morrison')

        things_result = _to_award_result(things)
        self.assertEqual(things_result.award_name, 'Pulitzer Prize')
        self.assertEqual(things_result.source_name, 'Pulitzer Prizes')
        self.assertEqual(things_result.category, 'Fiction')
        self.assertEqual(things_result.award_year, 1991)
        self.assertEqual(things_result.status, 'Finalist')
        self.assertEqual(things_result.source_url, FICTION_URL)

        grapes_result = _to_award_result(grapes)
        self.assertEqual(grapes_result.award_name, 'Pulitzer Prize')
        self.assertEqual(grapes_result.source_name, 'Pulitzer Prizes')
        self.assertEqual(grapes_result.category, 'Novel')
        self.assertEqual(grapes_result.award_year, 1940)
        self.assertEqual(grapes_result.status, 'Winner')
        self.assertEqual(grapes_result.source_url, NOVEL_URL)

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
