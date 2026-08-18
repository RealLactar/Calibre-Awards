"""Offline unittest coverage for the World Fantasy Award Novel source."""

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


class WorldFantasyParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = _sample_records()

    def test_forgotten_beasts_is_1975_winner(self):
        matches = _find(
            self.records,
            title='The Forgotten Beasts of Eld',
            author='Patricia A. McKillip',
        )
        self.assertEqual(len(matches), 1)
        record = matches[0]
        self.assertEqual(record.award_year, 1975)
        self.assertEqual(record.status, 'Winner')
        self.assertEqual(record.work_title, 'The Forgotten Beasts of Eld')
        self.assertEqual(record.source_url, world_fantasy.WINNERS_URL)

    def test_salems_lot_is_1976_nominee(self):
        matches = _find(
            self.records, title="Salem's Lot", author='Stephen King'
        )
        self.assertEqual(len(matches), 1)
        record = matches[0]
        self.assertEqual(record.award_year, 1976)
        self.assertEqual(record.status, 'Nominee')
        self.assertEqual(record.source_url, world_fantasy.NOMINEES_URL)

    def test_watchtower_duplicate_rows_collapse(self):
        matches = _find(
            self.records, title='Watchtower', author='Elizabeth A. Lynn'
        )
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].award_year, 1980)
        self.assertEqual(matches[0].status, 'Winner')

    def test_sword_of_the_lictor_recovers_malformed_row(self):
        matches = _find(
            self.records,
            title='The Sword of the Lictor',
            author='Gene Wolfe',
        )
        self.assertEqual(len(matches), 1)
        record = matches[0]
        self.assertEqual(record.award_year, 1983)
        self.assertEqual(record.status, 'Nominee')
        self.assertEqual(record.work_title, 'The Sword of the Lictor')

    def test_bridge_of_birds_uses_winners_table_authority(self):
        matches = _find(
            self.records, title='Bridge of Birds', author='Barry Hughart'
        )
        self.assertEqual(len(matches), 1)
        record = matches[0]
        self.assertEqual(record.award_year, 1985)
        self.assertEqual(record.status, 'Winner')
        self.assertEqual(record.source_url, world_fantasy.WINNERS_URL)

    def test_good_omens_collapses_coauthors(self):
        matches = _find(self.records, title='Good Omens')
        self.assertEqual(len(matches), 1)
        record = matches[0]
        self.assertEqual(record.award_year, 1991)
        self.assertEqual(record.status, 'Nominee')
        self.assertEqual(
            record.work_author, 'Terry Pratchett and Neil Gaiman'
        )
        self.assertTrue(
            world_fantasy._record_matches(
                record, 'Good Omens', 'Terry Pratchett and Neil Gaiman'
            )
        )
        self.assertTrue(
            world_fantasy._record_matches(record, 'Good Omens', 'Neil Gaiman')
        )
        self.assertTrue(
            world_fantasy._record_matches(
                record, 'Good Omens', 'Terry Pratchett'
            )
        )

    def test_last_call_winner_without_nominees_slate(self):
        matches = _find(
            self.records, title='Last Call', author='Tim Powers'
        )
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].award_year, 1993)
        self.assertEqual(matches[0].status, 'Winner')
        self.assertEqual(matches[0].source_url, world_fantasy.WINNERS_URL)

    def test_jonathan_strange_winner_without_nominees_slate(self):
        matches = _find(
            self.records,
            title='Jonathan Strange & Mr Norrell',
            author='Susanna Clarke',
        )
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].award_year, 2005)
        self.assertEqual(matches[0].status, 'Winner')

    def test_jonathan_strange_and_query_matches_ampersand_winner(self):
        matches = _find(
            self.records,
            title='Jonathan Strange and Mr Norrell',
            author='Susanna Clarke',
        )
        self.assertEqual(len(matches), 1)
        record = matches[0]
        self.assertEqual(record.award_year, 2005)
        self.assertEqual(record.status, 'Winner')
        self.assertEqual(record.work_title, 'Jonathan Strange & Mr Norrell')

    def test_alif_the_unseen_is_exactly_one_2013_winner(self):
        matches = _find(
            self.records, title='Alif the Unseen', author='G. Willow Wilson'
        )
        self.assertEqual(len(matches), 1)
        record = matches[0]
        self.assertEqual(record.award_year, 2013)
        self.assertEqual(record.status, 'Winner')
        self.assertEqual(record.source_url, world_fantasy.WINNERS_URL)
        self.assertNotEqual(record.source_url, world_fantasy.NOMINEES_URL)

    def test_killing_moon_is_2013_nominee_not_2012(self):
        matches = _find(
            self.records, title='The Killing Moon', author='N.K. Jemisin'
        )
        self.assertEqual(len(matches), 1)
        record = matches[0]
        self.assertEqual(record.award_year, 2013)
        self.assertEqual(record.status, 'Nominee')
        self.assertEqual(record.source_url, world_fantasy.ANNUAL_2013_URL)

    def test_2013_correction_also_moves_remaining_slate(self):
        drowning = _find(
            self.records,
            title='The Drowning Girl',
            author='Caitlin R. Kiernan',
        )
        self.assertEqual(len(drowning), 1)
        self.assertEqual(drowning[0].award_year, 2013)
        self.assertEqual(drowning[0].status, 'Nominee')
        self.assertTrue(
            world_fantasy._record_matches(
                drowning[0], 'The Drowning Girl', 'Caitlín R. Kiernan'
            )
        )

    def test_legitimate_2012_nominee_is_kept(self):
        matches = _find(
            self.records,
            title='Those Across the River',
            author='Christopher Buehlman',
        )
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].award_year, 2012)
        self.assertEqual(matches[0].status, 'Nominee')

    def test_uprooted_is_2016_nominee_not_winner(self):
        matches = _find(
            self.records, title='Uprooted', author='Naomi Novik'
        )
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].award_year, 2016)
        self.assertEqual(matches[0].status, 'Nominee')
        self.assertEqual(matches[0].source_url, world_fantasy.NOMINEES_URL)

    def test_the_chimes_is_2016_winner(self):
        matches = _find(
            self.records, title='The Chimes', author='Anna Smaill'
        )
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].award_year, 2016)
        self.assertEqual(matches[0].status, 'Winner')
        self.assertEqual(matches[0].source_url, world_fantasy.WINNERS_URL)

    def test_2018_tied_winners_are_both_winners(self):
        changeling = _find(
            self.records, title='The Changeling', author='Victor LaValle'
        )
        jade = _find(self.records, title='Jade City', author='Fonda Lee')
        self.assertEqual(len(changeling), 1)
        self.assertEqual(len(jade), 1)
        self.assertEqual(changeling[0].award_year, 2018)
        self.assertEqual(jade[0].award_year, 2018)
        self.assertEqual(changeling[0].status, 'Winner')
        self.assertEqual(jade[0].status, 'Winner')
        self.assertIsNone(_to_rank(changeling[0]))
        self.assertIsNone(_to_rank(jade[0]))

    def test_witchmark_uses_winners_table_authority(self):
        matches = _find(
            self.records, title='Witchmark', author='C.L. Polk'
        )
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].award_year, 2019)
        self.assertEqual(matches[0].status, 'Winner')
        self.assertTrue(
            world_fantasy._record_matches(
                matches[0], 'Witchmark', 'C. L. Polk'
            )
        )

    def test_djeli_clark_accent_insensitive_author_match(self):
        matches = _find(
            self.records,
            title='A Master of Djinn',
            author='P. Djèlí Clark',
        )
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].award_year, 2022)
        self.assertEqual(matches[0].status, 'Nominee')
        self.assertTrue(
            world_fantasy._record_matches(
                matches[0], 'A Master of Djinn', 'P. Djeli Clark'
            )
        )

    def test_harrow_markup_artifact_is_removed(self):
        matches = _find(
            self.records,
            title='The Ten Thousand Doors of January',
            author='Alix E. Harrow',
        )
        self.assertEqual(len(matches), 1)
        record = matches[0]
        self.assertEqual(record.award_year, 2020)
        self.assertEqual(record.status, 'Nominee')
        self.assertEqual(
            record.work_title, 'The Ten Thousand Doors of January'
        )
        self.assertNotIn('/em>', record.work_title)

    def test_2024_winner_and_nominee(self):
        winner = _find(
            self.records, title='The Reformatory', author='Tananarive Due'
        )
        nominee = _find(
            self.records, title='Witch King', author='Martha Wells'
        )
        self.assertEqual(len(winner), 1)
        self.assertEqual(len(nominee), 1)
        self.assertEqual(winner[0].award_year, 2024)
        self.assertEqual(winner[0].status, 'Winner')
        self.assertEqual(winner[0].source_url, world_fantasy.ANNUAL_2024_URL)
        self.assertEqual(nominee[0].award_year, 2024)
        self.assertEqual(nominee[0].status, 'Nominee')
        self.assertEqual(nominee[0].source_url, world_fantasy.ANNUAL_2024_URL)
        reformatory_count = len(_find(self.records, title='The Reformatory'))
        self.assertEqual(reformatory_count, 1)

    def test_2025_winner_and_nominee(self):
        winner = _find(
            self.records,
            title='The Tainted Cup',
            author='Robert Jackson Bennett',
        )
        nominee = _find(
            self.records, title='The Fox Wife', author='Yangsze Choo'
        )
        self.assertEqual(len(winner), 1)
        self.assertEqual(len(nominee), 1)
        self.assertEqual(winner[0].award_year, 2025)
        self.assertEqual(winner[0].status, 'Winner')
        self.assertEqual(winner[0].source_url, world_fantasy.ANNUAL_2025_URL)
        self.assertEqual(nominee[0].award_year, 2025)
        self.assertEqual(nominee[0].status, 'Nominee')

    def test_hobbit_does_not_match(self):
        self.assertEqual(
            _find(self.records, title='The Hobbit', author='J.R.R. Tolkien'),
            [],
        )

    def test_truncated_sound_of_does_not_fuzzy_match(self):
        truncated = _find(
            self.records, title='The Sound of', author='Charles L. Grant'
        )
        self.assertEqual(len(truncated), 1)
        self.assertEqual(truncated[0].work_title, 'The Sound of')
        self.assertEqual(
            _find(
                self.records,
                title='The Sound of Midnight',
                author='Charles L. Grant',
            ),
            [],
        )

    def test_category_isolation_excludes_novella_and_long_fiction(self):
        self.assertEqual(
            _find(
                self.records,
                title='The Unlicensed Magician',
                author='Kelly Barnhill',
            ),
            [],
        )
        self.assertEqual(
            _find(
                self.records,
                title='Beyond Any Measure',
                author='Karl Edward Wagner',
            ),
            [],
        )
        self.assertEqual(
            _find(
                self.records,
                title='The Emperor’s Soul',
                author='Brandon Sanderson',
            ),
            [],
        )
        self.assertEqual(
            _find(
                self.records,
                title='Yoke of Stars',
                author='R.B. Lemberg',
            ),
            [],
        )

    def test_standalone_ampersand_matches_and(self):
        self.assertTrue(
            world_fantasy._titles_equivalent(
                'Jonathan Strange and Mr Norrell',
                'Jonathan Strange & Mr Norrell',
            )
        )
        self.assertTrue(
            world_fantasy._titles_equivalent(
                'Jonathan Strange & Mr Norrell',
                'Jonathan Strange and Mr Norrell',
            )
        )
        self.assertTrue(
            world_fantasy._titles_equivalent('Smith & Jones', 'Smith and Jones')
        )

    def test_city_prefix_does_not_match(self):
        self.assertFalse(
            world_fantasy._titles_equivalent(
                'The City', 'The City & The City'
            )
        )

    def test_no_2026_source_url(self):
        self.assertTrue(
            all('2026' not in url for url in world_fantasy.SOURCE_PAGE_URLS)
        )
        self.assertEqual(
            world_fantasy.SOURCE_PAGE_URLS,
            (
                world_fantasy.NOMINEES_URL,
                world_fantasy.WINNERS_URL,
                world_fantasy.ANNUAL_2013_URL,
                world_fantasy.ANNUAL_2024_URL,
                world_fantasy.ANNUAL_2025_URL,
            ),
        )
        self.assertFalse(
            any(record.award_year == 2026 for record in self.records)
        )

    def test_award_result_fields_and_qualification(self):
        winner = _to_result(
            _find(
                self.records,
                title='The Forgotten Beasts of Eld',
                author='Patricia A. McKillip',
            )[0]
        )
        nominee = _to_result(
            _find(
                self.records, title="Salem's Lot", author='Stephen King'
            )[0]
        )
        self.assertEqual(winner.award_name, 'World Fantasy Award')
        self.assertEqual(winner.category, 'Novel')
        self.assertIsNone(winner.rank)
        self.assertEqual(winner.source_name, 'World Fantasy Awards')
        self.assertEqual(
            qualify_award_result(winner).decision,
            QualificationDecision.QUALIFIES,
        )
        self.assertEqual(
            qualify_award_result(nominee).decision,
            QualificationDecision.REVIEW,
        )
        self.assertEqual(
            format_award_result(winner),
            'Winner - 1975 World Fantasy Award - Novel',
        )
        self.assertEqual(
            format_award_result(nominee),
            'Nominee - 1976 World Fantasy Award - Novel',
        )

    def test_2018_winners_remain_unranked(self):
        jade = _to_result(
            _find(self.records, title='Jade City', author='Fonda Lee')[0]
        )
        self.assertIsNone(jade.rank)
        self.assertEqual(
            format_award_result(jade),
            'Winner - 2018 World Fantasy Award - Novel',
        )


def _to_result(record):
    return world_fantasy._to_award_result(record)


def _to_rank(record):
    return _to_result(record).rank


class WorldFantasyHttpAndCacheTests(unittest.TestCase):
    def setUp(self):
        world_fantasy._reset_runtime_state()

    def tearDown(self):
        world_fantasy._reset_runtime_state()

    def test_decode_utf8_then_cp1252_fallback(self):
        utf8_text = 'P. Djèlí Clark'
        self.assertEqual(
            world_fantasy._decode_html_bytes(utf8_text.encode('utf-8')),
            utf8_text,
        )
        cp1252_raw = utf8_text.encode('cp1252')
        with self.assertRaises(UnicodeDecodeError):
            cp1252_raw.decode('utf-8')
        self.assertEqual(
            world_fantasy._decode_html_bytes(cp1252_raw),
            utf8_text,
        )

    def test_lookup_uses_cached_records(self):
        world_fantasy._records_cache = _sample_records()
        results = world_fantasy.lookup(
            'The Forgotten Beasts of Eld', 'Patricia A. McKillip'
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, 'Winner')
        self.assertEqual(results[0].award_year, 1975)
        self.assertIsNone(results[0].rank)

    def test_lookup_rejects_empty_fields(self):
        with self.assertRaises(ValueError):
            world_fantasy.lookup(' ', 'Author')
        with self.assertRaises(ValueError):
            world_fantasy.lookup('Title', ' ')

    def test_http_failure_raises_and_does_not_cache(self):
        with patch.object(
            world_fantasy,
            '_fetch_html',
            side_effect=world_fantasy.WorldFantasySourceError('blocked'),
        ):
            with self.assertRaises(world_fantasy.WorldFantasySourceError):
                world_fantasy._get_records()
        self.assertIsNone(world_fantasy._records_cache)

    def test_empty_parse_raises_and_does_not_cache(self):
        empty = world_fantasy._FetchedPages(
            nominees_html='<html></html>',
            winners_html='<html></html>',
            annual_2013_html='<html></html>',
            annual_2024_html='<html></html>',
            annual_2025_html='<html></html>',
        )
        with patch.object(
            world_fantasy, '_fetch_source_pages', return_value=empty
        ):
            with self.assertRaises(world_fantasy.WorldFantasySourceError) as ctx:
                world_fantasy._get_records()
        self.assertIsNone(world_fantasy._records_cache)
        self.assertIn('nominees table produced no Novel works', str(ctx.exception))

    def test_broken_nominees_page_raises_and_does_not_cache(self):
        pages = _sample_pages(nominees_html='<html><p>no table</p></html>')
        with patch.object(
            world_fantasy, '_fetch_source_pages', return_value=pages
        ):
            with self.assertRaises(world_fantasy.WorldFantasySourceError) as ctx:
                world_fantasy._get_records()
        self.assertIsNone(world_fantasy._records_cache)
        self.assertIn('nominees table produced no Novel works', str(ctx.exception))

    def test_broken_winners_page_raises_and_does_not_cache(self):
        pages = _sample_pages(winners_html='<html><p>no table</p></html>')
        with patch.object(
            world_fantasy, '_fetch_source_pages', return_value=pages
        ):
            with self.assertRaises(world_fantasy.WorldFantasySourceError) as ctx:
                world_fantasy._get_records()
        self.assertIsNone(world_fantasy._records_cache)
        self.assertIn('winners table produced no Novel works', str(ctx.exception))

    def test_broken_2013_page_raises_and_does_not_cache(self):
        pages = _sample_pages(annual_2013_html='<html><p>Novel missing</p></html>')
        with patch.object(
            world_fantasy, '_fetch_source_pages', return_value=pages
        ):
            with self.assertRaises(world_fantasy.WorldFantasySourceError) as ctx:
                world_fantasy._get_records()
        self.assertIsNone(world_fantasy._records_cache)
        self.assertIn('2013 annual page', str(ctx.exception))

    def test_broken_2024_page_raises_and_does_not_cache(self):
        pages = _sample_pages(annual_2024_html='<html><p>NOVEL missing</p></html>')
        with patch.object(
            world_fantasy, '_fetch_source_pages', return_value=pages
        ):
            with self.assertRaises(world_fantasy.WorldFantasySourceError) as ctx:
                world_fantasy._get_records()
        self.assertIsNone(world_fantasy._records_cache)
        self.assertIn('2024 annual page', str(ctx.exception))

    def test_broken_2025_page_raises_and_does_not_cache(self):
        pages = _sample_pages(annual_2025_html='<html><p>Best Novel missing</p></html>')
        with patch.object(
            world_fantasy, '_fetch_source_pages', return_value=pages
        ):
            with self.assertRaises(world_fantasy.WorldFantasySourceError) as ctx:
                world_fantasy._get_records()
        self.assertIsNone(world_fantasy._records_cache)
        self.assertIn('2025 annual page', str(ctx.exception))

    def test_get_records_caches_after_success(self):
        pages = _sample_pages()
        with patch.object(
            world_fantasy, '_fetch_source_pages', return_value=pages
        ) as fetch:
            first = world_fantasy._get_records()
            second = world_fantasy._get_records()
        self.assertIs(first, second)
        fetch.assert_called_once()


if __name__ == '__main__':
    unittest.main()
