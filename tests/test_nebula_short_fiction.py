"""Offline coverage for Nebula novella, novelette, and short story parsing."""

from __future__ import annotations

import unittest
from pathlib import Path

from awards.formatter import format_award_result
from awards.qualifier import QualificationDecision, qualify_award_result
from awards.sources import nebula

FIXTURES = Path(__file__).resolve().parent / 'fixtures' / 'nebula'


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding='utf-8')


def _parse(html: str, config):
    return nebula._parse_category_html(html, config)


def _find(records, title: str):
    return [record for record in records if record.work_title == title]


class NebulaNovellaTests(unittest.TestCase):
    def test_historical_quoted_title_and_1965_tie(self):
        records = _parse(_load('best_novella_1965.html'), nebula._BEST_NOVELLA_CONFIG)
        titles = {record.work_title for record in records}
        self.assertEqual(
            titles,
            {'The Saliva Tree', 'He Who Shapes', 'The Ballad of Beta-2'},
        )
        saliva = _find(records, 'The Saliva Tree')[0]
        shapes = _find(records, 'He Who Shapes')[0]
        self.assertEqual(saliva.status, 'Winner')
        self.assertEqual(shapes.status, 'Winner')
        self.assertEqual(saliva.work_author, 'Brian W. Aldiss')
        self.assertEqual(shapes.work_author, 'Roger Zelazny')
        self.assertEqual(saliva.category, 'Best Novella')
        self.assertEqual(saliva.award_name, 'Nebula Award')

    def test_2025_compact_quoted_citation(self):
        records = _parse(_load('best_novella_2025.html'), nebula._BEST_NOVELLA_CONFIG)
        river = _find(records, 'The River Has Roots')[0]
        self.assertEqual(river.status, 'Winner')
        self.assertEqual(river.work_author, 'Amal El-Mohtar')
        self.assertEqual(river.award_year, 2025)
        result = nebula._to_award_result(river)
        self.assertEqual(
            format_award_result(result),
            'Winner - 2025 Nebula Award - Best Novella',
        )
        self.assertEqual(
            qualify_award_result(result).decision,
            QualificationDecision.QUALIFIES,
        )
        nominee = [record for record in records if record.work_author == 'Renan Bernardo'][0]
        self.assertEqual(nominee.status, 'Nominated')
        self.assertIn("Kap", nominee.work_title)
        self.assertIn("Needle", nominee.work_title)
        self.assertEqual(
            qualify_award_result(nebula._to_award_result(nominee)).decision,
            QualificationDecision.REVIEW,
        )

    def test_1990_hemingway_hoax_uses_official_nominated_work_author(self):
        # Official 1990 winner line omits the author link; author comes from
        # the nominated-work page rather than an invented byline.
        records = _parse(_load('best_novella_1990.html'), nebula._BEST_NOVELLA_CONFIG)
        winner = [record for record in records if record.status == 'Winner'][0]
        self.assertEqual(winner.work_title, 'The Hemingway Hoax')
        self.assertEqual(winner.work_author, 'Joe Haldeman')
        self.assertEqual(winner.award_year, 1990)
        self.assertEqual(winner.category, 'Best Novella')
        result = nebula._to_award_result(winner)
        self.assertEqual(result.identity_kind, 'work')
        self.assertIsNone(result.rank)
        self.assertEqual(
            format_award_result(result),
            'Winner - 1990 Nebula Award - Best Novella',
        )
        self.assertEqual(
            qualify_award_result(result).decision,
            QualificationDecision.QUALIFIES,
        )
        nominee = _find(records, 'Bones')[0]
        self.assertEqual(nominee.status, 'Nominated')
        self.assertEqual(nominee.work_author, 'Pat Murphy')

    def test_missing_author_override_does_not_replace_parsed_author(self):
        # Negative: the Hemingway workaround must not replace a linked author.
        html = """
        <h2>1990</h2><ul class="award_list"><li>
        <i class="fa fa-star" alt="Winner" title="Winner"></i>
        <a href="https://nebulas.sfwa.org/nominated-work/hemingway-hoax/">
        &ldquo;The Hemingway Hoax&rdquo;</a>
        by <a href="https://nebulas.sfwa.org/nominees/someone-else/">Someone Else</a>.
        Winner, Best Novella in 1990
        </li></ul>
        """
        winner = _parse(html, nebula._BEST_NOVELLA_CONFIG)[0]
        self.assertEqual(winner.work_author, 'Someone Else')

    def test_hemingway_hoax_lookup_returns_the_novella_winner(self):
        nebula._clear_caches_for_tests()
        for config in nebula._AWARD_CONFIGS:
            nebula._records_cache[config.key] = ()
        pages = (
            (
                'https://nebulas.sfwa.org/award/best-novella/',
                _load('best_novella_1990.html'),
            ),
        )
        nebula._records_cache[nebula._BEST_NOVELLA_CONFIG.key] = tuple(
            nebula._records_from_pages(nebula._BEST_NOVELLA_CONFIG, pages)
        )
        try:
            results = nebula.lookup('The Hemingway Hoax', 'Joe Haldeman')
            self.assertEqual(len(results), 1)
            result = results[0]
            self.assertEqual(result.status, 'Winner')
            self.assertEqual(result.award_year, 1990)
            self.assertEqual(result.award_name, 'Nebula Award')
            self.assertEqual(result.category, 'Best Novella')
            self.assertIsNone(result.rank)
            self.assertEqual(result.identity_kind, 'work')
            self.assertEqual(
                format_award_result(result),
                'Winner - 1990 Nebula Award - Best Novella',
            )
            self.assertEqual(
                qualify_award_result(result).decision,
                QualificationDecision.QUALIFIES,
            )
        finally:
            nebula._clear_caches_for_tests()

    def test_time_war_matches_calibre_and_official_author_forms(self):
        nebula._clear_caches_for_tests()
        for config in nebula._AWARD_CONFIGS:
            nebula._records_cache[config.key] = ()
        pages = (
            (
                'https://nebulas.sfwa.org/award/best-novella/',
                _load('best_novella_2019.html'),
            ),
        )
        nebula._records_cache[nebula._BEST_NOVELLA_CONFIG.key] = tuple(
            nebula._records_from_pages(nebula._BEST_NOVELLA_CONFIG, pages)
        )
        try:
            calibre = nebula.lookup(
                'This Is How You Lose the Time War',
                'Amal El-Mohtar & Max Gladstone',
            )
            official = nebula.lookup(
                'This Is How You Lose the Time War',
                'Amal El-Mohtar and Max Gladstone',
            )
            self.assertEqual(len(calibre), 1)
            self.assertEqual(len(official), 1)
            self.assertEqual(
                format_award_result(calibre[0]),
                'Winner - 2019 Nebula Award - Best Novella',
            )
            self.assertEqual(
                format_award_result(official[0]),
                'Winner - 2019 Nebula Award - Best Novella',
            )
            self.assertEqual(
                qualify_award_result(calibre[0]).decision,
                QualificationDecision.QUALIFIES,
            )
        finally:
            nebula._clear_caches_for_tests()


class NebulaNoveletteTests(unittest.TestCase):
    def test_historical_quoted_title(self):
        records = _parse(
            _load('best_novelette_1965.html'), nebula._BEST_NOVELETTE_CONFIG
        )
        winner = _find(records, 'The Doors of His Face, the Lamps of His Mouth')[0]
        self.assertEqual(winner.status, 'Winner')
        self.assertEqual(winner.work_author, 'Roger Zelazny')
        self.assertEqual(
            format_award_result(nebula._to_award_result(winner)),
            'Winner - 1965 Nebula Award - Best Novelette',
        )
        nominee = _find(records, '102 H-Bombs')[0]
        self.assertEqual(nominee.status, 'Nominated')
        self.assertEqual(
            qualify_award_result(nebula._to_award_result(nominee)).decision,
            QualificationDecision.REVIEW,
        )

    def test_2025_compact_quoted_citation(self):
        records = _parse(
            _load('best_novelette_2025.html'), nebula._BEST_NOVELETTE_CONFIG
        )
        winner = _find(records, 'Uncertain Sons')[0]
        self.assertEqual(winner.status, 'Winner')
        self.assertEqual(winner.work_author, 'Thomas Ha')
        nominee = _find(records, 'Our Echoes Drifting Through the Marsh')[0]
        self.assertEqual(nominee.status, 'Nominated')
        self.assertEqual(nominee.work_author, 'Marie Croke')


class NebulaShortStoryTests(unittest.TestCase):
    def test_historical_quoted_title_nominee(self):
        records = _parse(
            _load('best_short_story_1965.html'), nebula._BEST_SHORT_STORY_CONFIG
        )
        simak = _find(records, 'Over the River and Through the Woods')[0]
        self.assertEqual(simak.status, 'Nominated')
        self.assertEqual(simak.work_author, 'Clifford D. Simak')
        result = nebula._to_award_result(simak)
        self.assertEqual(
            format_award_result(result),
            'Nominated - 1965 Nebula Award - Best Short Story',
        )
        self.assertEqual(
            qualify_award_result(result).decision,
            QualificationDecision.REVIEW,
        )

    def test_2010_tie_and_winner_formatting(self):
        records = _parse(
            _load('best_short_story_2010.html'), nebula._BEST_SHORT_STORY_CONFIG
        )
        winners = [record for record in records if record.status == 'Winner']
        self.assertEqual(
            {record.work_title for record in winners},
            {'Ponies', 'How Interesting: A Tiny Man'},
        )
        ponies = _find(records, 'Ponies')[0]
        self.assertEqual(ponies.work_author, 'Kij Johnson')
        self.assertEqual(
            format_award_result(nebula._to_award_result(ponies)),
            'Winner - 2010 Nebula Award - Best Short Story',
        )
        pages = [('https://example.test/2010', _load('best_short_story_2010.html'))]
        records = nebula._records_from_pages(
            nebula._BEST_SHORT_STORY_CONFIG, pages
        )
        self.assertEqual(
            len([record for record in records if record.status == 'Winner']),
            2,
        )

    def test_1970_no_award_is_not_a_work_and_is_an_exact_exception(self):
        self.assertEqual(
            nebula._BEST_SHORT_STORY_CONFIG.no_work_winner_years,
            frozenset({1970}),
        )
        records = _parse(
            _load('best_short_story_1970.html'), nebula._BEST_SHORT_STORY_CONFIG
        )
        self.assertEqual(
            [record.work_title for record in records],
            ['A Dream at Noonday'],
        )
        self.assertTrue(all(record.status == 'Nominated' for record in records))
        config = nebula._NebulaAwardConfig(
            key='best-short-story',
            archive_url=nebula.BEST_SHORT_STORY_URL,
            award_name=nebula.AWARD_NAME_NEBULA,
            category=nebula.CATEGORY_BEST_SHORT_STORY,
            status_labels=(nebula.CATEGORY_BEST_SHORT_STORY,),
            first_year=1970,
            no_work_winner_years=frozenset({1970}),
        )
        pages = [
            ('https://example.test/1970', _load('best_short_story_1970.html'))
        ]
        nebula._validate_category_archive(
            config,
            pages,
            nebula._records_from_pages(config, pages),
        )

    def test_1990_authorless_winner_satisfies_fail_closed(self):
        config = nebula._NebulaAwardConfig(
            key='best-novella',
            archive_url=nebula.BEST_NOVELLA_URL,
            award_name=nebula.AWARD_NAME_NEBULA,
            category=nebula.CATEGORY_BEST_NOVELLA,
            status_labels=(nebula.CATEGORY_BEST_NOVELLA,),
            first_year=1990,
        )
        pages = [
            ('https://example.test/1990', _load('best_novella_1990.html'))
        ]
        nebula._validate_category_archive(
            config,
            pages,
            nebula._records_from_pages(config, pages),
        )


if __name__ == '__main__':
    unittest.main()
