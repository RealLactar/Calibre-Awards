"""Offline unittest coverage for the World Fantasy Award Collection source."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from awards.formatter import format_award_result
from awards.qualifier import QualificationDecision, qualify_award_result
from awards.sources import world_fantasy

FIXTURES = Path(__file__).resolve().parent / 'fixtures' / 'world_fantasy'


def _load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding='utf-8')


def _sample_pages(**overrides):
    pages = {
        'nominees_html': _load_fixture('nominees_sample.html'),
        'winners_html': _load_fixture('winners_sample.html'),
        'convention_1982_html': _load_fixture('convention_1982.html'),
        'convention_1993_html': _load_fixture('convention_1993.html'),
        'convention_2005_html': _load_fixture('convention_2005.html'),
        'annual_2013_html': _load_fixture('annual_2013.html'),
        'annual_2024_html': _load_fixture('annual_2024.html'),
        'annual_2025_html': _load_fixture('annual_2025.html'),
    }
    pages.update(overrides)
    return world_fantasy._FetchedPages(**pages)


def _sample_records():
    return world_fantasy._build_records_from_pages(_sample_pages())


def _find(records, *, title: str, author: str | None = None):
    matches = [
        record
        for record in records
        if world_fantasy._titles_equivalent(title, record.work_title)
    ]
    if author is not None:
        matches = [
            record
            for record in matches
            if world_fantasy._authors_match(author, record)
        ]
    return matches


def _to_result(record):
    return world_fantasy._to_award_result(record)


def _full_history_winner_works(*, skip_collection=None):
    works = []
    for year in sorted(world_fantasy.NOVEL_MASTER_WINNER_YEARS):
        works.append(
            world_fantasy._TableWork(
                award_year=year,
                category=world_fantasy.CATEGORY_NOVEL,
                official_category='Novel',
                work_title=f'Novel {year}',
                authors=('Archive Author',),
                status='Winner',
            )
        )
    for year in sorted(world_fantasy.NOVELLA_MASTER_WINNER_YEARS):
        official = (
            'Long Fiction'
            if year in world_fantasy.LONG_FICTION_YEARS
            else 'Novella'
        )
        works.append(
            world_fantasy._TableWork(
                award_year=year,
                category=world_fantasy.CATEGORY_NOVELLA,
                official_category=official,
                work_title=f'Novella {year}',
                authors=('Archive Author',),
                status='Winner',
            )
        )
    for year in sorted(world_fantasy.SHORT_FICTION_MASTER_WINNER_YEARS):
        works.append(
            world_fantasy._TableWork(
                award_year=year,
                category=world_fantasy.CATEGORY_SHORT_FICTION,
                official_category='Short Fiction',
                work_title=f'Short Fiction {year}',
                authors=('Archive Author',),
                status='Winner',
            )
        )
    for year in sorted(world_fantasy.COLLECTION_MASTER_WINNER_YEARS):
        if year == skip_collection:
            continue
        works.append(
            world_fantasy._TableWork(
                award_year=year,
                category=world_fantasy.CATEGORY_COLLECTION,
                official_category='Collection',
                work_title=f'Collection {year}',
                authors=('Archive Author',),
                status='Winner',
            )
        )
    return works


class WorldFantasyCollectionParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = _sample_records()

    def test_1988_jaguar_hunter_is_first_standalone_winner(self):
        matches = _find(
            self.records, title='The Jaguar Hunter', author='Lucius Shepard'
        )
        self.assertEqual(len(matches), 1)
        record = matches[0]
        self.assertEqual(record.category, 'Collection')
        self.assertEqual(record.award_year, 1988)
        self.assertEqual(record.status, 'Winner')
        self.assertEqual(record.source_url, world_fantasy.WINNERS_URL)
        result = _to_result(record)
        self.assertIsNone(result.rank)
        self.assertEqual(
            qualify_award_result(result).decision,
            QualificationDecision.QUALIFIES,
        )
        self.assertEqual(
            format_award_result(result),
            'Winner - 1988 World Fantasy Award - Collection',
        )

    def test_historical_collection_nominee_parses(self):
        matches = _find(
            self.records, title='Magic for Beginners', author='Kelly Link'
        )
        collection = [
            record for record in matches if record.category == 'Collection'
        ]
        self.assertEqual(len(collection), 1)
        record = collection[0]
        self.assertEqual(record.award_year, 2006)
        self.assertEqual(record.status, 'Nominee')
        self.assertEqual(record.source_url, world_fantasy.NOMINEES_URL)
        result = _to_result(record)
        self.assertIsNone(result.rank)
        self.assertEqual(
            qualify_award_result(result).decision,
            QualificationDecision.REVIEW,
        )
        self.assertEqual(
            format_award_result(result),
            'Nominee - 2006 World Fantasy Award - Collection',
        )

    def test_1993_collection_nominee_restored_from_convention_page(self):
        winner = _find(
            self.records,
            title='The Sons of Noah and Other Stories',
            author='Jack Cady',
        )
        nominee = _find(
            self.records, title="Bear's Fantasies", author='Greg Bear'
        )
        self.assertEqual(len(winner), 1)
        self.assertEqual(winner[0].status, 'Winner')
        self.assertEqual(winner[0].source_url, world_fantasy.WINNERS_URL)
        self.assertEqual(len(nominee), 1)
        self.assertEqual(nominee[0].category, 'Collection')
        self.assertEqual(nominee[0].award_year, 1993)
        self.assertEqual(nominee[0].status, 'Nominee')
        self.assertEqual(
            nominee[0].source_url, world_fantasy.CONVENTION_1993_URL
        )

    def test_2013_heading_canonicalizes_to_collection(self):
        heading_map = world_fantasy._annual_heading_map()
        self.assertEqual(heading_map['collection'], 'Collection')
        self.assertEqual(heading_map['best collection'], 'Collection')
        self.assertNotIn('anthology', heading_map)
        self.assertNotIn('collection/anthology', heading_map)
        matches = _find(
            self.records,
            title='At the Mouth of the River of Bees',
            author='Kij Johnson',
        )
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].category, 'Collection')
        self.assertEqual(matches[0].award_year, 2013)

    def test_2013_where_furnaces_burn_is_winner(self):
        matches = _find(
            self.records, title='Where Furnaces Burn', author='Joel Lane'
        )
        thirteen = [record for record in matches if record.award_year == 2013]
        self.assertEqual(len(thirteen), 1)
        record = thirteen[0]
        self.assertEqual(record.category, 'Collection')
        self.assertEqual(record.status, 'Winner')
        self.assertEqual(record.source_url, world_fantasy.WINNERS_URL)
        result = _to_result(record)
        self.assertIsNone(result.rank)
        self.assertEqual(
            qualify_award_result(result).decision,
            QualificationDecision.QUALIFIES,
        )
        self.assertEqual(
            format_award_result(result),
            'Winner - 2013 World Fantasy Award - Collection',
        )

    def test_2013_collection_nominee_is_correct(self):
        matches = _find(
            self.records,
            title='At the Mouth of the River of Bees',
            author='Kij Johnson',
        )
        self.assertEqual(len(matches), 1)
        record = matches[0]
        self.assertEqual(record.category, 'Collection')
        self.assertEqual(record.award_year, 2013)
        self.assertEqual(record.status, 'Nominee')
        self.assertEqual(record.source_url, world_fantasy.ANNUAL_2013_URL)
        result = _to_result(record)
        self.assertEqual(
            qualify_award_result(result).decision,
            QualificationDecision.REVIEW,
        )
        self.assertEqual(
            format_award_result(result),
            'Nominee - 2013 World Fantasy Award - Collection',
        )

    def test_where_furnaces_burn_has_no_misfiled_2012_copy(self):
        matches = _find(
            self.records, title='Where Furnaces Burn', author='Joel Lane'
        )
        years = sorted(record.award_year for record in matches)
        self.assertNotIn(2012, years)

    def test_2013_correction_keeps_same_identity_in_another_year(self):
        matches = _find(
            self.records, title='Where Furnaces Burn', author='Joel Lane'
        )
        years = sorted(record.award_year for record in matches)
        self.assertEqual(years, [2010, 2013])
        by_year = {record.award_year: record for record in matches}
        self.assertEqual(by_year[2010].status, 'Nominee')
        self.assertEqual(by_year[2010].source_url, world_fantasy.NOMINEES_URL)
        self.assertEqual(by_year[2013].status, 'Winner')

    def test_2024_collection_section_is_recognized_without_h4(self):
        winner = _find(
            self.records,
            title='No One Will Come Back for Us and Other Stories',
            author='Premee Mohamed',
        )
        self.assertEqual(len(winner), 1)
        self.assertEqual(winner[0].category, 'Collection')
        self.assertEqual(winner[0].award_year, 2024)
        self.assertFalse(
            any(
                record.category == 'Short Fiction'
                and 'No One Will Come Back' in record.work_title
                for record in self.records
            )
        )

    def test_2024_collection_winner(self):
        matches = _find(
            self.records,
            title='No One Will Come Back for Us and Other Stories',
            author='Premee Mohamed',
        )
        self.assertEqual(len(matches), 1)
        record = matches[0]
        self.assertEqual(record.status, 'Winner')
        self.assertEqual(record.source_url, world_fantasy.ANNUAL_2024_URL)
        self.assertEqual(
            format_award_result(_to_result(record)),
            'Winner - 2024 World Fantasy Award - Collection',
        )
        self.assertEqual(
            qualify_award_result(_to_result(record)).decision,
            QualificationDecision.QUALIFIES,
        )

    def test_2024_collection_nominee(self):
        matches = _find(
            self.records,
            title='The Essential Peter S. Beagle Volumes 1 & 2',
            author='Peter S. Beagle',
        )
        self.assertEqual(len(matches), 1)
        record = matches[0]
        self.assertEqual(record.category, 'Collection')
        self.assertEqual(record.award_year, 2024)
        self.assertEqual(record.status, 'Nominee')
        self.assertEqual(record.source_url, world_fantasy.ANNUAL_2024_URL)
        self.assertEqual(
            format_award_result(_to_result(record)),
            'Nominee - 2024 World Fantasy Award - Collection',
        )
        self.assertEqual(
            qualify_award_result(_to_result(record)).decision,
            QualificationDecision.REVIEW,
        )

    def test_2025_collection_winner(self):
        matches = _find(
            self.records,
            title='A Sunny Place for Shady People',
            author='Mariana Enríquez',
        )
        self.assertEqual(len(matches), 1)
        record = matches[0]
        self.assertEqual(record.category, 'Collection')
        self.assertEqual(record.award_year, 2025)
        self.assertEqual(record.status, 'Winner')
        self.assertEqual(record.work_author, 'Mariana Enríquez')
        self.assertNotIn('McDowell', record.work_author)
        self.assertNotIn('translated', record.work_author.casefold())
        self.assertEqual(record.source_url, world_fantasy.ANNUAL_2025_URL)
        result = _to_result(record)
        self.assertIsNone(result.rank)
        self.assertEqual(
            qualify_award_result(result).decision,
            QualificationDecision.QUALIFIES,
        )
        self.assertEqual(
            format_award_result(result),
            'Winner - 2025 World Fantasy Award - Collection',
        )

    def test_2025_collection_nominee(self):
        matches = _find(self.records, title='Ghostroots')
        self.assertEqual(len(matches), 1)
        record = matches[0]
        self.assertEqual(record.category, 'Collection')
        self.assertEqual(record.award_year, 2025)
        self.assertEqual(record.status, 'Nominee')
        self.assertEqual(record.source_url, world_fantasy.ANNUAL_2025_URL)
        self.assertTrue(
            world_fantasy._authors_match('\u2019Pemi Aguda', record)
        )
        result = _to_result(record)
        self.assertIsNone(result.rank)
        self.assertEqual(
            qualify_award_result(result).decision,
            QualificationDecision.REVIEW,
        )
        self.assertEqual(
            format_award_result(result),
            'Nominee - 2025 World Fantasy Award - Collection',
        )

    def test_collection_anthology_historical_rows_are_not_collection(self):
        self.assertIsNone(
            world_fantasy._resolve_table_category('Collection/Anthology', 1975)
        )
        self.assertIsNone(
            world_fantasy._resolve_table_category('Collection/Anthology', 1982)
        )
        matches = _find(
            self.records,
            title='Worse Things Waiting',
            author='Manly Wade Wellman',
        )
        self.assertEqual(matches, [])
        self.assertFalse(
            any(
                record.work_title == 'Worse Things Waiting'
                for record in self.records
            )
        )
        self.assertFalse(
            any(
                record.category == 'Collection/Anthology'
                for record in self.records
            )
        )

    def test_magic_for_beginners_does_not_merge_across_categories(self):
        matches = _find(
            self.records, title='Magic for Beginners', author='Kelly Link'
        )
        categories = sorted(record.category for record in matches)
        self.assertEqual(categories, ['Collection', 'Novella'])
        self.assertEqual({record.award_year for record in matches}, {2006})
        by_category = {record.category: record for record in matches}
        self.assertEqual(by_category['Novella'].status, 'Nominee')
        self.assertEqual(by_category['Collection'].status, 'Nominee')

    def test_tangled_lands_groups_both_authors(self):
        matches = _find(self.records, title='The Tangled Lands')
        self.assertEqual(len(matches), 1)
        record = matches[0]
        self.assertEqual(record.category, 'Collection')
        self.assertEqual(record.award_year, 2019)
        self.assertEqual(record.status, 'Winner')
        self.assertEqual(
            record.work_author, 'Paolo Bacigalupi and Tobias S. Buckell'
        )
        self.assertTrue(
            world_fantasy._record_matches(
                record, 'The Tangled Lands', 'Paolo Bacigalupi'
            )
        )
        self.assertTrue(
            world_fantasy._record_matches(
                record, 'The Tangled Lands', 'Tobias S. Buckell'
            )
        )

    def test_paragraph_containing_collection_is_not_a_heading(self):
        html = (
            '<h4><strong>NOVEL</strong></h4>'
            '<p><em>The Reformatory</em> by Tananarive Due (Saga)</p>'
            '<p>This paragraph mentions Collection awards in passing.</p>'
            '<p><em>Should Not Become Collection</em> by Wrong Author (Press)</p>'
        )
        records = world_fantasy._parse_2024_html(html)
        self.assertTrue(all(record.category == 'Novel' for record in records))
        self.assertFalse(any(record.category == 'Collection' for record in records))


class WorldFantasyCollectionHistoryTests(unittest.TestCase):
    def test_complete_synthetic_collection_history_passes(self):
        world_fantasy._validate_full_archive_history(_full_history_winner_works())

    def test_missing_collection_master_year_fails_closed(self):
        with self.assertRaises(world_fantasy.WorldFantasySourceError) as ctx:
            world_fantasy._validate_full_archive_history(
                _full_history_winner_works(skip_collection=2000)
            )
        self.assertIn('Collection', str(ctx.exception))
        self.assertIn('2000', str(ctx.exception))

    def test_exception_page_winner_cannot_mask_missing_master_year(self):
        winner_works = _full_history_winner_works(skip_collection=1993)
        exception_winner = world_fantasy._make_record(
            1993,
            world_fantasy.CATEGORY_COLLECTION,
            'Winner',
            'The Sons of Noah and Other Stories',
            ('Jack Cady',),
            world_fantasy.CONVENTION_1993_URL,
        )
        self.assertEqual(exception_winner.status, 'Winner')
        self.assertEqual(exception_winner.award_year, 1993)
        self.assertNotIn(
            1993,
            {
                work.award_year
                for work in winner_works
                if work.category == world_fantasy.CATEGORY_COLLECTION
            },
        )
        with self.assertRaises(world_fantasy.WorldFantasySourceError) as ctx:
            world_fantasy._validate_full_archive_history(winner_works)
        self.assertIn('Collection', str(ctx.exception))
        self.assertIn('1993', str(ctx.exception))


class WorldFantasyCollectionCacheTests(unittest.TestCase):
    def setUp(self):
        world_fantasy._reset_runtime_state()

    def tearDown(self):
        world_fantasy._reset_runtime_state()

    def test_second_get_records_does_not_refetch(self):
        pages = _sample_pages()
        with patch.object(
            world_fantasy, '_fetch_source_pages', return_value=pages
        ) as fetch:
            with patch.object(
                world_fantasy, '_validate_full_archive_history'
            ):
                first = world_fantasy._get_records()
                second = world_fantasy._get_records()
        self.assertIs(first, second)
        fetch.assert_called_once()
        self.assertTrue(
            any(record.category == 'Collection' for record in first)
        )


if __name__ == '__main__':
    unittest.main()
