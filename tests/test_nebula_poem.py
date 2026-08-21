"""Offline coverage for Nebula Best Poem parsing and year validation."""

from __future__ import annotations

import unittest
from pathlib import Path

from awards.formatter import format_award_result
from awards.qualifier import QualificationDecision, qualify_award_result
from awards.sources import nebula

FIXTURES = Path(__file__).resolve().parent / 'fixtures' / 'nebula'


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding='utf-8')


class NebulaPoemTests(unittest.TestCase):
    def test_2025_winner_and_nominee(self):
        records = nebula._parse_category_html(
            _load('best_poem_2025.html'), nebula._BEST_POEM_CONFIG
        )
        by_title = {record.work_title: record for record in records}
        winner = by_title['The World To Come']
        self.assertEqual(winner.status, 'Winner')
        self.assertEqual(winner.work_author, 'Jennifer Hudak')
        self.assertEqual(winner.award_year, 2025)
        self.assertEqual(winner.award_name, 'Nebula Award')
        self.assertEqual(winner.category, 'Best Poem')
        result = nebula._to_award_result(winner)
        self.assertEqual(result.identity_kind, 'work')
        self.assertIsNone(result.rank)
        self.assertEqual(
            format_award_result(result),
            'Winner - 2025 Nebula Award - Best Poem',
        )
        self.assertEqual(
            qualify_award_result(result).decision,
            QualificationDecision.QUALIFIES,
        )
        nominee = by_title['Care for Lightning']
        self.assertEqual(nominee.status, 'Nominated')
        self.assertEqual(nominee.work_author, 'Mari Ness')
        nominee_result = nebula._to_award_result(nominee)
        self.assertEqual(
            format_award_result(nominee_result),
            'Nominated - 2025 Nebula Award - Best Poem',
        )
        self.assertEqual(
            qualify_award_result(nominee_result).decision,
            QualificationDecision.REVIEW,
        )

    def test_poem_year_validation_starts_at_2025(self):
        self.assertEqual(nebula._BEST_POEM_CONFIG.first_year, 2025)
        pages = [
            (
                'https://nebulas.sfwa.org/award/best-poem/',
                _load('best_poem_2025.html'),
            )
        ]
        records = nebula._records_from_pages(nebula._BEST_POEM_CONFIG, pages)
        nebula._validate_category_archive(nebula._BEST_POEM_CONFIG, pages, records)
        self.assertEqual({record.award_year for record in records}, {2025})


if __name__ == '__main__':
    unittest.main()
