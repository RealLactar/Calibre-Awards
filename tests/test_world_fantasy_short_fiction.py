"""Offline unittest coverage for the World Fantasy Award Short Fiction source."""

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


def _full_history_winner_works(*, skip_short_fiction=None):
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
        if year == skip_short_fiction:
            continue
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


class WorldFantasyShortFictionParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = _sample_records()

    def test_1975_pages_from_a_young_girls_journal_is_winner(self):
        matches = _find(
            self.records,
            title="Pages From a Young Girl's Journal",
            author='Robert Aickman',
        )
        self.assertEqual(len(matches), 1)
        record = matches[0]
        self.assertEqual(record.category, 'Short Fiction')
        self.assertEqual(record.award_year, 1975)
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
            'Winner - 1975 World Fantasy Award - Short Fiction',
        )

    def test_1982_restored_short_fiction_slate_exists(self):
        nominee = _find(
            self.records, title='Coin of the Realm', author='Charles L. Grant'
        )
        self.assertEqual(len(nominee), 1)
        self.assertEqual(nominee[0].category, 'Short Fiction')
        self.assertEqual(nominee[0].award_year, 1982)
        self.assertEqual(nominee[0].status, 'Nominee')
        self.assertEqual(
            nominee[0].source_url, world_fantasy.CONVENTION_1982_URL
        )

    def test_1982_tied_winners_both_survive(self):
        dark_country = _find(
            self.records, title='The Dark Country', author='Dennis Etchison'
        )
        dead_sing = _find(
            self.records, title='Do the Dead Sing?', author='Stephen King'
        )
        self.assertEqual(len(dark_country), 1)
        self.assertEqual(len(dead_sing), 1)
        self.assertEqual(dark_country[0].award_year, 1982)
        self.assertEqual(dead_sing[0].award_year, 1982)
        self.assertEqual(dark_country[0].category, 'Short Fiction')
        self.assertEqual(dead_sing[0].category, 'Short Fiction')
        self.assertEqual(dark_country[0].status, 'Winner')
        self.assertEqual(dead_sing[0].status, 'Winner')
        self.assertIsNone(_to_result(dark_country[0]).rank)
        self.assertIsNone(_to_result(dead_sing[0]).rank)
        self.assertEqual(
            dark_country[0].source_url, world_fantasy.WINNERS_URL
        )
        self.assertEqual(dead_sing[0].source_url, world_fantasy.WINNERS_URL)

    def test_1993_restored_short_fiction_nominee_slate_exists(self):
        winner = _find(
            self.records,
            title="This Year's Class Picture",
            author='Dan Simmons',
        )
        nominee = _find(self.records, title='Graves', author='Joe Haldeman')
        self.assertEqual(len(winner), 1)
        self.assertEqual(winner[0].status, 'Winner')
        self.assertEqual(winner[0].source_url, world_fantasy.WINNERS_URL)
        self.assertEqual(len(nominee), 1)
        self.assertEqual(nominee[0].award_year, 1993)
        self.assertEqual(nominee[0].category, 'Short Fiction')
        self.assertEqual(nominee[0].status, 'Nominee')
        self.assertEqual(
            nominee[0].source_url, world_fantasy.CONVENTION_1993_URL
        )

    def test_2013_short_story_heading_canonicalizes_to_short_fiction(self):
        heading_map = world_fantasy._annual_heading_map()
        self.assertEqual(heading_map['short story'], 'Short Fiction')
        self.assertEqual(heading_map['short fiction'], 'Short Fiction')
        self.assertEqual(heading_map['best short fiction'], 'Short Fiction')
        self.assertNotIn('best short story', heading_map)
        matches = _find(
            self.records,
            title='A Natural History of Autumn',
            author='Jeffrey Ford',
        )
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].category, 'Short Fiction')
        self.assertEqual(matches[0].award_year, 2013)
        self.assertNotEqual(matches[0].category, 'Short Story')

    def test_2013_the_telling_is_winner(self):
        matches = _find(
            self.records, title='The Telling', author='Gregory Norman Bossert'
        )
        thirteen = [record for record in matches if record.award_year == 2013]
        self.assertEqual(len(thirteen), 1)
        record = thirteen[0]
        self.assertEqual(record.category, 'Short Fiction')
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
            'Winner - 2013 World Fantasy Award - Short Fiction',
        )

    def test_the_telling_has_no_misfiled_2012_copy(self):
        matches = _find(
            self.records, title='The Telling', author='Gregory Norman Bossert'
        )
        years = sorted(record.award_year for record in matches)
        self.assertNotIn(2012, years)
        self.assertFalse(
            any(record.award_year == 2012 for record in matches)
        )

    def test_2013_correction_keeps_same_identity_in_another_year(self):
        matches = _find(
            self.records, title='The Telling', author='Gregory Norman Bossert'
        )
        years = sorted(record.award_year for record in matches)
        self.assertEqual(years, [2010, 2013])
        by_year = {record.award_year: record for record in matches}
        self.assertEqual(by_year[2010].status, 'Nominee')
        self.assertEqual(by_year[2010].source_url, world_fantasy.NOMINEES_URL)
        self.assertEqual(by_year[2013].status, 'Winner')

    def test_2024_kraken_is_nominee(self):
        matches = _find(
            self.records,
            title='How to Raise a Kraken in Your Bathtub',
            author='P. Djèlí Clark',
        )
        self.assertEqual(len(matches), 1)
        record = matches[0]
        self.assertEqual(record.category, 'Short Fiction')
        self.assertEqual(record.award_year, 2024)
        self.assertEqual(record.status, 'Nominee')
        self.assertEqual(record.source_url, world_fantasy.ANNUAL_2024_URL)
        result = _to_result(record)
        self.assertIsNone(result.rank)
        self.assertEqual(
            qualify_award_result(result).decision,
            QualificationDecision.REVIEW,
        )
        self.assertEqual(
            format_award_result(result),
            'Nominee - 2024 World Fantasy Award - Short Fiction',
        )

    def test_2025_raptor_is_winner(self):
        matches = _find(
            self.records, title='Raptor', author='Maura McHugh'
        )
        self.assertEqual(len(matches), 1)
        record = matches[0]
        self.assertEqual(record.category, 'Short Fiction')
        self.assertEqual(record.award_year, 2025)
        self.assertEqual(record.status, 'Winner')
        self.assertEqual(record.source_url, world_fantasy.ANNUAL_2025_URL)
        result = _to_result(record)
        self.assertIsNone(result.rank)
        self.assertEqual(
            qualify_award_result(result).decision,
            QualificationDecision.QUALIFIES,
        )
        self.assertEqual(
            format_award_result(result),
            'Winner - 2025 World Fantasy Award - Short Fiction',
        )

    def test_winner_and_nominee_qualification_semantics(self):
        winner = _to_result(
            _find(
                self.records,
                title="Pages From a Young Girl's Journal",
                author='Robert Aickman',
            )[0]
        )
        nominee = _to_result(
            _find(
                self.records,
                title='How to Raise a Kraken in Your Bathtub',
                author='P. Djèlí Clark',
            )[0]
        )
        self.assertEqual(
            qualify_award_result(winner).decision,
            QualificationDecision.QUALIFIES,
        )
        self.assertEqual(
            qualify_award_result(nominee).decision,
            QualificationDecision.REVIEW,
        )

    def test_2025_internal_comma_title_is_preserved(self):
        matches = _find(
            self.records, title='The V*mpire,', author='PH Lee'
        )
        self.assertEqual(len(matches), 1)
        record = matches[0]
        self.assertEqual(record.work_title, 'The V*mpire,')
        self.assertEqual(record.work_author, 'PH Lee')
        self.assertEqual(record.category, 'Short Fiction')
        self.assertEqual(record.award_year, 2025)
        self.assertEqual(record.status, 'Nominee')
        self.assertNotIn('Reactor', record.work_author)
        self.assertTrue(
            world_fantasy._record_matches(record, 'The V*mpire,', 'PH Lee')
        )

    def test_venue_is_not_included_in_work_author(self):
        telling = _find(
            self.records, title='The Telling', author='Gregory Norman Bossert'
        )
        raptor = _find(self.records, title='Raptor', author='Maura McHugh')
        vampire = _find(self.records, title='The V*mpire,', author='PH Lee')
        kraken = _find(
            self.records,
            title='How to Raise a Kraken in Your Bathtub',
            author='P. Djèlí Clark',
        )
        self.assertEqual(telling[0].work_author, 'Gregory Norman Bossert')
        self.assertEqual(raptor[0].work_author, 'Maura McHugh')
        self.assertEqual(vampire[0].work_author, 'PH Lee')
        self.assertEqual(kraken[0].work_author, 'P. Djèlí Clark')
        for record in (telling[0], raptor[0], vampire[0], kraken[0]):
            self.assertNotIn('(', record.work_author)
            self.assertNotIn('Reactor', record.work_author)
            self.assertNotIn('Heartwood', record.work_author)
            self.assertNotIn('Uncanny', record.work_author)
            self.assertNotIn('Ceaseless', record.work_author)

    def test_ambiguous_quoted_citation_fails_closed(self):
        self.assertIsNone(
            world_fantasy._parse_quoted_story_citation(
                'The Telling, Gregory Norman Bossert '
                '(Beneath Ceaseless Skies 11/29/12)'
            )
        )
        self.assertIsNone(
            world_fantasy._parse_quoted_story_citation(
                '“Raptor”, Maura McHugh (Heartwood) '
                '“The V*mpire,”, PH Lee (Reactor)'
            )
        )
        self.assertIsNone(
            world_fantasy._parse_quoted_story_citation(
                '“Raptor” (Heartwood: A Mythago Wood Anthology)'
            )
        )
        parsed = world_fantasy._parse_quoted_story_citation(
            'WINNER: “Raptor”, Maura McHugh '
            '(Heartwood: A Mythago Wood Anthology)'
        )
        self.assertEqual(parsed, ('Raptor', 'Maura McHugh'))

    def test_same_title_year_does_not_merge_across_categories(self):
        matches = _find(self.records, title='Category Isolation Title')
        categories = sorted(record.category for record in matches)
        self.assertEqual(categories, ['Novel', 'Short Fiction'])
        self.assertEqual({record.award_year for record in matches}, {2000})
        novel = [record for record in matches if record.category == 'Novel'][0]
        short = [
            record for record in matches if record.category == 'Short Fiction'
        ][0]
        self.assertEqual(novel.work_author, 'Fixture Novel')
        self.assertEqual(short.work_author, 'Fixture Short Fiction')


class WorldFantasyShortFictionHistoryTests(unittest.TestCase):
    def test_complete_synthetic_short_fiction_history_passes(self):
        world_fantasy._validate_full_archive_history(_full_history_winner_works())

    def test_missing_short_fiction_master_year_fails_closed(self):
        with self.assertRaises(world_fantasy.WorldFantasySourceError) as ctx:
            world_fantasy._validate_full_archive_history(
                _full_history_winner_works(skip_short_fiction=2000)
            )
        self.assertIn('Short Fiction', str(ctx.exception))
        self.assertIn('2000', str(ctx.exception))

    def test_exception_page_winner_cannot_mask_missing_master_year(self):
        winner_works = _full_history_winner_works(skip_short_fiction=1982)
        exception_1982_winner = world_fantasy._make_record(
            1982,
            world_fantasy.CATEGORY_SHORT_FICTION,
            'Winner',
            'The Dark Country',
            ('Dennis Etchison',),
            world_fantasy.CONVENTION_1982_URL,
        )
        self.assertEqual(exception_1982_winner.status, 'Winner')
        self.assertEqual(exception_1982_winner.award_year, 1982)
        self.assertEqual(exception_1982_winner.category, 'Short Fiction')
        self.assertNotIn(
            1982,
            {
                work.award_year
                for work in winner_works
                if work.category == world_fantasy.CATEGORY_SHORT_FICTION
            },
        )
        with self.assertRaises(world_fantasy.WorldFantasySourceError) as ctx:
            world_fantasy._validate_full_archive_history(winner_works)
        self.assertIn('Short Fiction', str(ctx.exception))
        self.assertIn('1982', str(ctx.exception))


class WorldFantasyShortFictionCacheTests(unittest.TestCase):
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
            any(record.category == 'Short Fiction' for record in first)
        )


if __name__ == '__main__':
    unittest.main()
