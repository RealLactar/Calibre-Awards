"""Offline unittest coverage for the World Fantasy Award Novella source."""

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


class WorldFantasyNovellaParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = _sample_records()

    def test_1982_fire_when_it_comes_is_winner(self):
        matches = _find(
            self.records,
            title='The Fire When It Comes',
            author='Parke Godwin',
        )
        self.assertEqual(len(matches), 1)
        record = matches[0]
        self.assertEqual(record.category, 'Novella')
        self.assertEqual(record.award_year, 1982)
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
            'Winner - 1982 World Fantasy Award - Novella',
        )

    def test_1982_novella_nominee_comes_from_convention_page(self):
        matches = _find(
            self.records,
            title='The Unicorn Tapestry',
            author='Suzy McKee Charnas',
        )
        self.assertEqual(len(matches), 1)
        record = matches[0]
        self.assertEqual(record.category, 'Novella')
        self.assertEqual(record.award_year, 1982)
        self.assertEqual(record.status, 'Nominee')
        self.assertEqual(record.source_url, world_fantasy.CONVENTION_1982_URL)
        result = _to_result(record)
        self.assertIsNone(result.rank)
        self.assertEqual(
            qualify_award_result(result).decision,
            QualificationDecision.REVIEW,
        )

    def test_beyond_any_measure_uses_winners_table_authority(self):
        matches = _find(
            self.records,
            title='Beyond Any Measure',
            author='Karl Edward Wagner',
        )
        self.assertEqual(len(matches), 1)
        record = matches[0]
        self.assertEqual(record.category, 'Novella')
        self.assertEqual(record.award_year, 1983)
        self.assertEqual(record.status, 'Winner')
        self.assertEqual(record.source_url, world_fantasy.WINNERS_URL)
        result = _to_result(record)
        self.assertEqual(
            format_award_result(result),
            'Winner - 1983 World Fantasy Award - Novella',
        )
        self.assertEqual(
            qualify_award_result(result).decision,
            QualificationDecision.QUALIFIES,
        )

    def test_ragthorn_groups_both_authors(self):
        matches = _find(self.records, title='The Ragthorn')
        self.assertEqual(len(matches), 1)
        record = matches[0]
        self.assertEqual(record.category, 'Novella')
        self.assertEqual(record.award_year, 1992)
        self.assertEqual(record.status, 'Winner')
        self.assertEqual(
            record.work_author, 'Robert Holdstock and Garry Kilworth'
        )
        self.assertTrue(
            world_fantasy._record_matches(
                record, 'The Ragthorn', 'Robert Holdstock and Garry Kilworth'
            )
        )
        self.assertTrue(
            world_fantasy._record_matches(
                record, 'The Ragthorn', 'Robert Holdstock'
            )
        )
        self.assertTrue(
            world_fantasy._record_matches(
                record, 'The Ragthorn', 'Garry Kilworth'
            )
        )

    def test_1993_novella_slate_from_convention_page(self):
        winner = _find(
            self.records, title='The Ghost Village', author='Peter Straub'
        )
        nominee = _find(
            self.records, title='The Wishing Well', author='Charles de Lint'
        )
        self.assertEqual(len(winner), 1)
        self.assertEqual(winner[0].status, 'Winner')
        self.assertEqual(winner[0].source_url, world_fantasy.WINNERS_URL)
        self.assertEqual(len(nominee), 1)
        self.assertEqual(nominee[0].award_year, 1993)
        self.assertEqual(nominee[0].status, 'Nominee')
        self.assertEqual(nominee[0].category, 'Novella')
        self.assertEqual(
            nominee[0].source_url, world_fantasy.CONVENTION_1993_URL
        )

    def test_2005_growlimb_and_tainaron_from_convention_page(self):
        winner = _find(
            self.records, title='The Growlimb', author='Michael Shea'
        )
        nominee = _find(
            self.records,
            title='Tainaron: Mail from Another City',
            author='Leena Krohn',
        )
        self.assertEqual(len(winner), 1)
        self.assertEqual(winner[0].award_year, 2005)
        self.assertEqual(winner[0].status, 'Winner')
        self.assertEqual(winner[0].category, 'Novella')
        self.assertEqual(len(nominee), 1)
        self.assertEqual(nominee[0].award_year, 2005)
        self.assertEqual(nominee[0].status, 'Nominee')
        self.assertEqual(
            nominee[0].source_url, world_fantasy.CONVENTION_2005_URL
        )

    def test_emperors_soul_is_2013_nominee_not_2012(self):
        matches = _find(
            self.records,
            title="The Emperor's Soul",
            author='Brandon Sanderson',
        )
        self.assertEqual(len(matches), 1)
        record = matches[0]
        self.assertEqual(record.category, 'Novella')
        self.assertEqual(record.award_year, 2013)
        self.assertEqual(record.status, 'Nominee')
        self.assertEqual(record.source_url, world_fantasy.ANNUAL_2013_URL)
        result = _to_result(record)
        self.assertIsNone(result.rank)
        self.assertEqual(
            qualify_award_result(result).decision,
            QualificationDecision.REVIEW,
        )
        self.assertEqual(
            format_award_result(result),
            'Nominee - 2013 World Fantasy Award - Novella',
        )
        self.assertFalse(
            any(
                record.award_year == 2012
                for record in _find(
                    self.records,
                    title="The Emperor's Soul",
                    author='Brandon Sanderson',
                )
            )
        )

    def test_legitimate_2012_novella_is_kept(self):
        matches = _find(
            self.records,
            title='Silently and Very Fast',
            author='Catherynne M. Valente',
        )
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].award_year, 2012)
        self.assertEqual(matches[0].status, 'Nominee')
        self.assertEqual(matches[0].category, 'Novella')

    def test_2013_let_maps_to_others_is_winner(self):
        matches = _find(
            self.records, title='Let Maps to Others', author='K.J. Parker'
        )
        self.assertEqual(len(matches), 1)
        record = matches[0]
        self.assertEqual(record.category, 'Novella')
        self.assertEqual(record.award_year, 2013)
        self.assertEqual(record.status, 'Winner')
        self.assertEqual(record.source_url, world_fantasy.WINNERS_URL)
        self.assertEqual(
            format_award_result(_to_result(record)),
            'Winner - 2013 World Fantasy Award - Novella',
        )

    def test_unlicensed_magician_is_2016_novella_not_long_fiction(self):
        matches = _find(
            self.records,
            title='The Unlicensed Magician',
            author='Kelly Barnhill',
        )
        self.assertEqual(len(matches), 1)
        record = matches[0]
        self.assertEqual(record.category, 'Novella')
        self.assertEqual(record.award_year, 2016)
        self.assertEqual(record.status, 'Winner')
        result = _to_result(record)
        self.assertEqual(result.category, 'Novella')
        self.assertNotEqual(result.category, 'Long Fiction')
        self.assertEqual(
            format_award_result(result),
            'Winner - 2016 World Fantasy Award - Novella',
        )
        self.assertFalse(
            any(item.category == 'Long Fiction' for item in self.records)
        )

    def test_2015_and_2019_remain_novella_in_sample_tables(self):
        fifteen = _find(
            self.records,
            title='We Are All Completely Fine',
            author='Daryl Gregory',
        )
        nineteen = _find(
            self.records,
            title='The Privilege of the Happy Ending',
            author='Kij Johnson',
        )
        self.assertEqual(fifteen[0].award_year, 2015)
        self.assertEqual(fifteen[0].category, 'Novella')
        self.assertEqual(nineteen[0].award_year, 2019)
        self.assertEqual(nineteen[0].category, 'Novella')

    def test_2024_half_the_house_is_haunted(self):
        winner = _find(
            self.records,
            title='Half the House Is Haunted',
            author='Josh Malerman',
        )
        nominee = _find(
            self.records, title='Thornhedge', author='T. Kingfisher'
        )
        self.assertEqual(len(winner), 1)
        self.assertEqual(winner[0].category, 'Novella')
        self.assertEqual(winner[0].award_year, 2024)
        self.assertEqual(winner[0].status, 'Winner')
        self.assertEqual(winner[0].source_url, world_fantasy.ANNUAL_2024_URL)
        self.assertEqual(
            format_award_result(_to_result(winner[0])),
            'Winner - 2024 World Fantasy Award - Novella',
        )
        self.assertEqual(len(nominee), 1)
        self.assertEqual(nominee[0].status, 'Nominee')
        self.assertEqual(
            len(_find(self.records, title='A Sorceress Comes to Call')),
            0,
        )

    def test_2025_yoke_of_stars(self):
        winner = _find(
            self.records, title='Yoke of Stars', author='R.B. Lemberg'
        )
        nominee = _find(
            self.records,
            title='Crypt of the Moon Spider',
            author='Nathan Ballingrud',
        )
        self.assertEqual(len(winner), 1)
        self.assertEqual(winner[0].category, 'Novella')
        self.assertEqual(winner[0].award_year, 2025)
        self.assertEqual(winner[0].status, 'Winner')
        self.assertEqual(winner[0].source_url, world_fantasy.ANNUAL_2025_URL)
        result = _to_result(winner[0])
        self.assertIsNone(result.rank)
        self.assertEqual(
            qualify_award_result(result).decision,
            QualificationDecision.QUALIFIES,
        )
        self.assertEqual(
            format_award_result(result),
            'Winner - 2025 World Fantasy Award - Novella',
        )
        self.assertEqual(len(nominee), 1)
        self.assertEqual(nominee[0].status, 'Nominee')
        self.assertEqual(
            qualify_award_result(_to_result(nominee[0])).decision,
            QualificationDecision.REVIEW,
        )

    def test_same_title_year_does_not_merge_across_categories(self):
        matches = _find(self.records, title='Identical Collision Title')
        categories = sorted(record.category for record in matches)
        self.assertEqual(categories, ['Novel', 'Novella'])
        self.assertEqual({record.award_year for record in matches}, {2000})
        novel = [record for record in matches if record.category == 'Novel'][0]
        novella = [
            record for record in matches if record.category == 'Novella'
        ][0]
        self.assertEqual(novel.work_author, 'Fixture Novel')
        self.assertEqual(novella.work_author, 'Fixture Novella')

    def test_same_work_in_two_years_is_not_deduped(self):
        matches = _find(
            self.records, title='Repeat Work', author='Fixture Author'
        )
        years = sorted(record.award_year for record in matches)
        self.assertEqual(years, [2000, 2001])
        self.assertTrue(all(record.category == 'Novella' for record in matches))
        self.assertTrue(all(record.status == 'Nominee' for record in matches))

    def test_2013_correction_suppresses_only_2012_copy(self):
        matches = _find(
            self.records,
            title='Correction Survivor Work',
            author='Fixture Author',
        )
        years = sorted(record.award_year for record in matches)
        self.assertEqual(years, [2010, 2013])
        by_year = {record.award_year: record for record in matches}
        self.assertEqual(by_year[2010].status, 'Nominee')
        self.assertEqual(by_year[2010].source_url, world_fantasy.NOMINEES_URL)
        self.assertEqual(by_year[2013].status, 'Nominee')
        self.assertEqual(by_year[2013].source_url, world_fantasy.ANNUAL_2013_URL)
        self.assertNotIn(2012, years)


class WorldFantasyNovellaFailClosedTests(unittest.TestCase):
    def test_long_fiction_outside_2016_2018_fails_closed(self):
        extra = (
            '\n<tr>'
            '<td>Bad</td><td>Year</td><td>2015</td>'
            '<td>Long Fiction</td>'
            '<td>Should Not Parse</td><td>Winner</td>'
            '</tr>\n'
        )
        pages = _sample_pages(
            winners_html=_sample_pages().winners_html.replace(
                '</table>', extra + '</table>'
            )
        )
        with self.assertRaises(world_fantasy.WorldFantasySourceError) as ctx:
            world_fantasy._build_records_from_pages(pages)
        self.assertIn('Long Fiction', str(ctx.exception))
        self.assertIn('2015', str(ctx.exception))

    def test_2013_page_without_novella_fails_closed(self):
        pages = _sample_pages(
            annual_2013_html=(
                '<p><strong>Novel</strong></p><ul>'
                '<li><strong><em>Alif the Unseen</em>, G. Willow Wilson'
                '</strong></li>'
                '<li><em>The Killing Moon</em>, N.K. Jemisin</li>'
                '</ul>'
            )
        )
        with self.assertRaises(world_fantasy.WorldFantasySourceError) as ctx:
            world_fantasy._build_records_from_pages(pages)
        self.assertIn('2013 annual page', str(ctx.exception))
        self.assertIn('Novella', str(ctx.exception))


def _full_history_winner_works(
    *,
    skip_novel=None,
    skip_novella=None,
    official_overrides=None,
):
    official_overrides = official_overrides or {}
    works = []
    for year in sorted(world_fantasy.NOVEL_MASTER_WINNER_YEARS):
        if year == skip_novel:
            continue
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
        if year == skip_novella:
            continue
        if year in official_overrides:
            official = official_overrides[year]
        elif year in world_fantasy.LONG_FICTION_YEARS:
            official = 'Long Fiction'
        else:
            official = 'Novella'
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
    return works


class WorldFantasyFullArchiveValidationTests(unittest.TestCase):
    def test_valid_complete_history_passes(self):
        world_fantasy._validate_full_archive_history(_full_history_winner_works())

    def test_missing_novel_year_fails_closed(self):
        with self.assertRaises(world_fantasy.WorldFantasySourceError) as ctx:
            world_fantasy._validate_full_archive_history(
                _full_history_winner_works(skip_novel=2000)
            )
        self.assertIn('Novel', str(ctx.exception))
        self.assertIn('2000', str(ctx.exception))

    def test_missing_novella_year_fails_closed(self):
        with self.assertRaises(world_fantasy.WorldFantasySourceError) as ctx:
            world_fantasy._validate_full_archive_history(
                _full_history_winner_works(skip_novella=2000)
            )
        self.assertIn('Novella', str(ctx.exception))
        self.assertIn('2000', str(ctx.exception))

    def test_2016_novella_label_instead_of_long_fiction_fails_closed(self):
        with self.assertRaises(world_fantasy.WorldFantasySourceError) as ctx:
            world_fantasy._validate_full_archive_history(
                _full_history_winner_works(official_overrides={2016: 'Novella'})
            )
        self.assertIn('2016', str(ctx.exception))
        self.assertIn('long fiction', str(ctx.exception).casefold())

    def test_exception_page_winner_cannot_mask_missing_master_year(self):
        winner_works = _full_history_winner_works(skip_novel=1982)
        exception_1982_novel_winner = world_fantasy._make_record(
            1982,
            world_fantasy.CATEGORY_NOVEL,
            'Winner',
            'Little, Big',
            ('John Crowley',),
            world_fantasy.CONVENTION_1982_URL,
        )
        self.assertEqual(exception_1982_novel_winner.status, 'Winner')
        self.assertEqual(exception_1982_novel_winner.award_year, 1982)
        self.assertNotIn(
            1982,
            {
                work.award_year
                for work in winner_works
                if work.category == world_fantasy.CATEGORY_NOVEL
            },
        )
        with self.assertRaises(world_fantasy.WorldFantasySourceError) as ctx:
            world_fantasy._validate_full_archive_history(winner_works)
        self.assertIn('Novel', str(ctx.exception))
        self.assertIn('1982', str(ctx.exception))

    def test_long_fiction_is_not_an_annual_heading_alias(self):
        heading_map = world_fantasy._annual_heading_map()
        self.assertNotIn('long fiction', heading_map)
        novella = [
            config
            for config in world_fantasy._CATEGORY_CONFIGS
            if config.canonical == world_fantasy.CATEGORY_NOVELLA
        ][0]
        self.assertEqual(
            {alias.casefold() for alias in novella.annual_heading_aliases},
            {'novella', 'best novella'},
        )


class WorldFantasyNovellaCacheTests(unittest.TestCase):
    def setUp(self):
        world_fantasy._reset_runtime_state()

    def tearDown(self):
        world_fantasy._reset_runtime_state()

    def test_lookup_uses_cached_novel_and_novella_records(self):
        world_fantasy._records_cache = _sample_records()
        novel = world_fantasy.lookup(
            'The Forgotten Beasts of Eld', 'Patricia A. McKillip'
        )
        novella = world_fantasy.lookup(
            'The Fire When It Comes', 'Parke Godwin'
        )
        self.assertEqual(len(novel), 1)
        self.assertEqual(novel[0].category, 'Novel')
        self.assertEqual(len(novella), 1)
        self.assertEqual(novella[0].category, 'Novella')

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
        self.assertTrue(any(record.category == 'Novel' for record in first))
        self.assertTrue(any(record.category == 'Novella' for record in first))

    def test_get_records_runs_full_archive_validation_before_cache(self):
        pages = _sample_pages()
        with patch.object(
            world_fantasy, '_fetch_source_pages', return_value=pages
        ):
            with patch.object(
                world_fantasy,
                '_validate_full_archive_history',
                side_effect=world_fantasy.WorldFantasySourceError(
                    'truncated archive'
                ),
            ):
                with self.assertRaises(
                    world_fantasy.WorldFantasySourceError
                ) as ctx:
                    world_fantasy._get_records()
        self.assertIsNone(world_fantasy._records_cache)
        self.assertIn('truncated archive', str(ctx.exception))


if __name__ == '__main__':
    unittest.main()
