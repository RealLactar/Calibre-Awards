"""Offline coverage for Andre Norton Award canonical naming and aliases."""

from __future__ import annotations

import unittest
from pathlib import Path

from awards.formatter import format_award_result
from awards.qualifier import QualificationDecision, qualify_award_result
from awards.sources import nebula

FIXTURES = Path(__file__).resolve().parent / 'fixtures' / 'nebula'


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding='utf-8')


class NebulaNortonTests(unittest.TestCase):
    def test_canonical_award_identity(self):
        self.assertEqual(nebula.NORTON_AWARD_NAME, 'Andre Norton Award')
        self.assertEqual(
            nebula.NORTON_CATEGORY, 'Middle Grade and Young Adult Fiction'
        )
        self.assertEqual(nebula._NORTON_CONFIG.award_name, 'Andre Norton Award')
        self.assertEqual(
            nebula._NORTON_CONFIG.category,
            'Middle Grade and Young Adult Fiction',
        )

    def test_2005_historical_row(self):
        records = nebula._parse_category_html(
            _load('norton_2005.html'), nebula._NORTON_CONFIG
        )
        winner = [record for record in records if record.status == 'Winner'][0]
        self.assertEqual(winner.work_title, 'Valiant: A Modern Tale of Faerie')
        self.assertEqual(winner.work_author, 'Holly Black')
        self.assertEqual(winner.award_year, 2005)
        self.assertEqual(winner.award_name, 'Andre Norton Award')
        self.assertEqual(
            winner.category, 'Middle Grade and Young Adult Fiction'
        )

    def test_modern_compact_row(self):
        records = nebula._parse_category_html(
            _load('norton_2025.html'), nebula._NORTON_CONFIG
        )
        winner = [record for record in records if record.status == 'Winner'][0]
        self.assertEqual(winner.work_title, 'Into the Wild Magic')
        self.assertEqual(winner.work_author, 'Michelle Knudsen')
        self.assertEqual(
            format_award_result(nebula._to_award_result(winner)),
            'Winner - 2025 Andre Norton Award - Middle Grade and Young Adult Fiction',
        )

    def test_2015_updraft_old_winner_wording(self):
        html = _load('best_novel_2015.html')
        norton = nebula._parse_category_html(html, nebula._NORTON_CONFIG)
        novel = nebula._parse_best_novel_html(html)
        updraft_norton = [
            record for record in norton if record.work_title == 'Updraft'
        ]
        updraft_novel = [
            record for record in novel if record.work_title == 'Updraft'
        ]
        self.assertEqual(len(updraft_norton), 1)
        self.assertEqual(len(updraft_novel), 1)
        self.assertEqual(updraft_norton[0].status, 'Winner')
        self.assertEqual(updraft_novel[0].status, 'Nominated')
        norton_result = nebula._to_award_result(updraft_norton[0])
        novel_result = nebula._to_award_result(updraft_novel[0])
        self.assertEqual(norton_result.award_name, 'Andre Norton Award')
        self.assertEqual(
            norton_result.category, 'Middle Grade and Young Adult Fiction'
        )
        self.assertEqual(novel_result.award_name, 'Nebula Award')
        self.assertEqual(novel_result.category, 'Best Novel')
        self.assertIsNone(norton_result.rank)
        self.assertEqual(norton_result.identity_kind, 'work')
        self.assertEqual(
            format_award_result(norton_result),
            'Winner - 2015 Andre Norton Award - Middle Grade and Young Adult Fiction',
        )
        self.assertEqual(
            format_award_result(novel_result),
            'Nominated - 2015 Nebula Award - Best Novel',
        )
        self.assertEqual(
            qualify_award_result(norton_result).decision,
            QualificationDecision.QUALIFIES,
        )
        self.assertEqual(
            qualify_award_result(novel_result).decision,
            QualificationDecision.REVIEW,
        )

    def test_lookup_returns_both_updraft_identities(self):
        html = _load('best_novel_2015.html')
        nebula._clear_caches_for_tests()
        for config in nebula._AWARD_CONFIGS:
            nebula._records_cache[config.key] = ()
        novel_pages = (
            ('https://nebulas.sfwa.org/award/best-novel/', html),
        )
        norton_pages = (
            ('https://nebulas.sfwa.org/award/andre-norton-award/', html),
        )
        nebula._records_cache[nebula._BEST_NOVEL_CONFIG.key] = tuple(
            nebula._records_from_pages(nebula._BEST_NOVEL_CONFIG, novel_pages)
        )
        nebula._records_cache[nebula._NORTON_CONFIG.key] = tuple(
            nebula._records_from_pages(nebula._NORTON_CONFIG, norton_pages)
        )
        try:
            results = nebula.lookup('Updraft', 'Fran Wilde')
            formatted = [format_award_result(result) for result in results]
            self.assertEqual(
                formatted,
                [
                    'Nominated - 2015 Nebula Award - Best Novel',
                    'Winner - 2015 Andre Norton Award - Middle Grade and Young Adult Fiction',
                ],
            )
        finally:
            nebula._clear_caches_for_tests()

    def test_norton_fail_closed_from_2005_through_latest(self):
        self.assertEqual(nebula._NORTON_CONFIG.first_year, 2005)
        pages = [
            (
                'https://nebulas.sfwa.org/award/andre-norton-award/',
                _load('norton_2025.html'),
            )
        ]
        records = nebula._records_from_pages(nebula._NORTON_CONFIG, pages)
        with self.assertRaises(nebula.NebulaSourceError) as ctx:
            nebula._validate_category_archive(
                nebula._NORTON_CONFIG, pages, records
            )
        self.assertIn('2005', str(ctx.exception))

    def test_norton_continuous_archive_validates(self):
        winner_2005 = _load('norton_2005.html')
        winner_2025 = _load('norton_2025.html').replace('<h2>2025</h2>', '<h2>2006</h2>').replace('in 2025', 'in 2006').replace('award-year/2025', 'award-year/2006')
        # Build 2005-2006 only as a tiny continuous span for the helper.
        pages = [
            ('https://example.test/norton', winner_2005 + winner_2025)
        ]
        records = nebula._records_from_pages(nebula._NORTON_CONFIG, pages)
        nebula._validate_category_archive(nebula._NORTON_CONFIG, pages, records)


if __name__ == '__main__':
    unittest.main()
