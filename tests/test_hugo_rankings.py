"""Offline tests for curated Hugo Best Novel rankings and HTML enrichment."""

from __future__ import annotations

import unittest

from awards.formatter import format_award_result
from awards.qualifier import QualificationDecision, qualify_award_result
from awards.sources import hugo
from awards.sources.hugo_rankings import (
    HUGO_BEST_NOVEL_RANKINGS,
    STATS_2015,
    STATS_2017,
    STATS_2024,
    STATS_2025,
    HugoRanking,
    validate_hugo_rankings,
)

URL_1956 = 'https://www.thehugoawards.org/hugo-history/1956-hugo-awards/'
URL_1966 = 'https://www.thehugoawards.org/hugo-history/1966-hugo-awards/'
URL_1967 = 'https://www.thehugoawards.org/hugo-history/1967-hugo-awards/'
URL_1990 = 'https://www.thehugoawards.org/hugo-history/1990-hugo-awards/'
URL_1993 = 'https://www.thehugoawards.org/hugo-history/1993-hugo-awards/'
URL_2015 = 'https://www.thehugoawards.org/hugo-history/2015-hugo-awards/'
URL_2017 = 'https://www.thehugoawards.org/hugo-history/2017-hugo-awards/'
URL_2023 = 'https://www.thehugoawards.org/hugo-history/2023-hugo-awards/'
URL_2024 = 'https://www.thehugoawards.org/hugo-history/2024-hugo-awards/'
URL_2025 = 'https://www.thehugoawards.org/hugo-history/2025-hugo-awards/'
URL_2026 = 'https://www.thehugoawards.org/hugo-history/2026-hugo-awards/'

HTML_1956 = """
<p><strong>Best Novel</strong></p>
<ul>
<li class="winner"><em>Double Star</em> by Robert A. Heinlein [Astounding Feb,Mar,Apr 1956]</li>
<li><em>Call Him Dead</em>, by Eric Frank Russell</li>
<li><em>The End of Eternity</em>, by Isaac Asimov</li>
<li><em>Not this August</em>, by Cyril Kornbluth</li>
<li><em>The Long Tomorrow</em>, by Leigh Brackett</li>
</ul>
"""

HTML_1966 = """
<p><strong>Best Novel</strong></p>
<ul>
<li class="winner"><em>Dune</em> by Frank Herbert [Chilton, 1965] (tie)</li>
<li class="winner"><em>...And Call Me Conrad (alt: This Immortal)</em> by Roger Zelazny</li>
<li><em>The Squares of the City</em> by John Brunner [Ballantine, 1965]</li>
<li><em>The Moon is a Harsh Mistress</em> by Robert A. Heinlein</li>
<li><em>Skylark DuQuesne</em> by Edward E. Smith</li>
</ul>
"""

HTML_1967 = """
<p><strong>Best Novel</strong></p>
<ul>
<li class="winner"><em>The Moon is a Harsh Mistress</em> by Robert A. Heinlein</li>
<li><em>Babel-17</em> by Samuel R. Delany [Ace, 1966]</li>
</ul>
"""

HTML_1990 = """
<p><strong>Best Novel</strong></p>
<ul>
<li class="winner"><em>Hyperion</em> by Dan Simmons [Doubleday Foundation, 1989]</li>
<li><em>A Fire in the Sun</em> by George Alec Effinger</li>
<li><em>Prentice Alvin</em> by Orson Scott Card</li>
<li><em>The Boat of a Million Years</em> by Poul Anderson</li>
<li><em>Grass</em> by Sheri S. Tepper</li>
</ul>
"""

HTML_1993 = """
<p><strong>Best Novel</strong></p>
<ul>
<li class="winner"><em>A Fire Upon the Deep</em> by Vernor Vinge [Tor, 1992] (tie)</li>
<li class="winner"><em>Doomsday Book</em> by Connie Willis [Bantam Spectra, 1992] (tie)</li>
<li><em>Red Mars</em> by Kim Stanley Robinson</li>
</ul>
"""

HTML_2015 = """
<p><strong>Best Novel</strong> (5653 final ballots, 1827 nominating ballots, 587 entries, range 212-387)</p>
<ul>
<li class="winner"><strong>The Three Body Problem</strong>, Cixin Liu, Ken Liu translator (Tor Books)</li>
<li><strong>The Goblin Emperor</strong>, Katherine Addison (Sarah Monette) (Tor Books)</li>
<li><strong>Ancillary Sword</strong>, Ann Leckie (Orbit US/Orbit UK)</li>
<li><strong>No Award</strong></li>
<li><strong>Skin Game</strong>, Jim Butcher (Orbit UK/Roc Books)</li>
<li><strong>The Dark Between the Stars</strong>, Kevin J. Anderson (Tor Books)</li>
</ul>
"""

HTML_2017 = """
<p><strong>Best Novel</strong></p>
<ul>
<li class="winner"><em>The Obelisk Gate</em> by N. K. Jemisin (Orbit)</li>
<li><em>All the Birds in the Sky</em> by Charlie Jane Anders (Tor / Titan)</li>
<li><em>Ninefox Gambit</em> by Yoon Ha Lee (Solaris)</li>
<li><em>A Closed and Common Orbit</em> by Becky Chambers (Hodder &amp; Stoughton / Harper Voyager US)</li>
<li><em>Too Like the Lightning</em> by Ada Palmer (Tor)</li>
<li><em>Death’s End</em> by Cixin Liu, translated by Ken Liu (Tor / Head of Zeus)</li>
</ul>
"""

HTML_2023 = """
<p><strong>Best Novel</strong></p>
<ul>
<li class="winner"><em>Nettle &amp; Bone</em> by T. Kingfisher (Tor Books)</li>
<li><em>The Daughter of Doctor Moreau</em> by Silvia Moreno-Garcia (Del Rey)</li>
<li><em>The Kaiju Preservation Society</em> by John Scalzi (Tor Books)</li>
<li><em>Legends &amp; Lattes</em> by Travis Baldree (Tor Books)</li>
<li><em>Nona the Ninth</em> by Tamsyn Muir (Tordotcom)</li>
<li><em>The Spare Man</em> by Mary Robinette Kowal (Tor Books)</li>
</ul>
"""

HTML_2024 = """
<p><strong>Best Novel</strong></p>
<ul>
<li class="winner"><em>Some Desperate Glory</em> by Emily Tesh (Tordotcom, Orbit UK)</li>
<li><em>The Adventures of Amina al-Sirafi</em> by Shannon Chakraborty (Harper Voyager)</li>
<li><em>The Saint of Bright Doors</em> by Vajra Chandrasekera (Tordotcom)</li>
<li><em>Starter Villain</em> by John Scalzi (Tor, Tor UK)</li>
<li><em>Translation State</em> by Ann Leckie (Orbit US, Orbit UK)</li>
<li><em>Witch King</em> by Martha Wells (Tordotcom)</li>
</ul>
"""

HTML_2025 = """
<p><strong>Best Novel</strong></p>
<ul>
<li class="winner"><em>The Tainted Cup</em> by Robert Jackson Bennett (Del Rey, Hodderscape UK)</li>
<li><em>A Sorceress Comes to Call</em> by T. Kingfisher (Tor)</li>
<li><em>Alien Clay</em> by Adrian Tchaikovsky (Orbit US, Tor UK)</li>
<li><em>Someone You Can Build a Nest In</em> by John Wiswell (DAW)</li>
<li><em>The Ministry of Time</em> by Kaliane Bradley (Avid Reader Press, Sceptre)</li>
<li><em>Service Model</em> by Adrian Tchaikovsky (Tordotcom)</li>
</ul>
"""

HTML_2026 = """
<p><strong>Best Novel</strong></p>
<ul>
<li><em>A Drop of Corruption</em> by Robert Jackson Bennett (Del Rey; Hodderscape)</li>
<li><em>Death of the Author</em> by Nnedi Okorafor (William Morrow; Gollancz)</li>
</ul>
"""


def _seed_archive(*parsed: tuple[str, int, str]) -> None:
    records = []
    for page_html, year, url in parsed:
        records.extend(hugo._parse_best_novel_html(page_html, year, url))
    hugo._archive_records_cache = tuple(records)


def _lookup_year(title: str, author: str, year: int):
    return [
        result
        for result in hugo.lookup(title, author)
        if result.award_year == year
    ]


class HugoRankingDataTests(unittest.TestCase):
    def test_production_rankings_validate(self):
        validate_hugo_rankings()

    def test_supported_years_are_exactly_the_allowlist(self):
        years = {record.award_year for record in HUGO_BEST_NOVEL_RANKINGS}
        self.assertEqual(years, {1972, 1980, 1996, 2000, 2006, 2015, 2017, 2024, 2025})

    def test_record_counts_by_year(self):
        counts = {}
        for record in HUGO_BEST_NOVEL_RANKINGS:
            counts[record.award_year] = counts.get(record.award_year, 0) + 1
        self.assertEqual(
            counts,
            {
                1972: 5,
                1980: 5,
                1996: 5,
                2000: 5,
                2006: 5,
                2015: 5,
                2017: 6,
                2024: 6,
                2025: 6,
            },
        )

    def test_no_award_is_not_a_work_entry(self):
        self.assertFalse(
            any(
                'no award' in record.work_title.casefold()
                or 'no award' in record.work_author.casefold()
                for record in HUGO_BEST_NOVEL_RANKINGS
            )
        )
        self.assertFalse(
            any(record.award_year == 2015 and record.rank == 4 for record in HUGO_BEST_NOVEL_RANKINGS)
        )

    def test_1989_and_unranked_years_are_absent(self):
        years = {record.award_year for record in HUGO_BEST_NOVEL_RANKINGS}
        for year in (1964, 1965, 1966, 1967, 1989, 1990, 1993, 2023, 2026):
            self.assertNotIn(year, years)

    def test_validate_rejects_duplicate_work(self):
        record = HugoRanking(2024, 'Some Desperate Glory', 'Emily Tesh', 1, STATS_2024)
        with self.assertRaises(ValueError):
            validate_hugo_rankings((record, record))

    def test_validate_rejects_no_award_work(self):
        with self.assertRaises(ValueError):
            HugoRanking(2015, 'No Award', 'None', 4, STATS_2015)

    def test_validate_rejects_shared_rank_without_tie_flag(self):
        left = HugoRanking(1993, 'A Fire Upon the Deep', 'Vernor Vinge', 1, STATS_2024)
        right = HugoRanking(1993, 'Doomsday Book', 'Connie Willis', 1, STATS_2024)
        with self.assertRaises(ValueError):
            validate_hugo_rankings((left, right))

    def test_validate_allows_explicit_tied_shared_rank(self):
        left = HugoRanking(
            1993, 'A Fire Upon the Deep', 'Vernor Vinge', 1, STATS_2024, tied=True
        )
        right = HugoRanking(
            1993, 'Doomsday Book', 'Connie Willis', 1, STATS_2024, tied=True
        )
        validate_hugo_rankings((left, right))


class HugoRankEnrichmentTests(unittest.TestCase):
    def setUp(self):
        hugo._archive_records_cache = None
        _seed_archive(
            (HTML_1956, 1956, URL_1956),
            (HTML_1966, 1966, URL_1966),
            (HTML_1967, 1967, URL_1967),
            (HTML_1990, 1990, URL_1990),
            (HTML_1993, 1993, URL_1993),
            (HTML_2015, 2015, URL_2015),
            (HTML_2017, 2017, URL_2017),
            (HTML_2023, 2023, URL_2023),
            (HTML_2024, 2024, URL_2024),
            (HTML_2025, 2025, URL_2025),
            (HTML_2026, 2026, URL_2026),
        )

    def tearDown(self):
        hugo._archive_records_cache = None

    def test_2024_ranks_follow_statistics_not_html_order(self):
        glory = _lookup_year('Some Desperate Glory', 'Emily Tesh', 2024)[0]
        translation = _lookup_year('Translation State', 'Ann Leckie', 2024)[0]
        amina = _lookup_year(
            'The Adventures of Amina al-Sirafi', 'Shannon Chakraborty', 2024
        )[0]
        saint = _lookup_year(
            'The Saint of Bright Doors', 'Vajra Chandrasekera', 2024
        )[0]
        starter = _lookup_year('Starter Villain', 'John Scalzi', 2024)[0]
        self.assertEqual(glory.status, 'Winner')
        self.assertEqual(glory.rank, 1)
        self.assertEqual(glory.source_url, STATS_2024)
        self.assertEqual(translation.status, 'Finalist')
        self.assertEqual(translation.rank, 2)
        self.assertEqual(amina.rank, 3)
        self.assertEqual(saint.rank, 5)
        self.assertEqual(starter.status, 'Finalist')
        self.assertEqual(starter.rank, 6)
        self.assertEqual(starter.source_url, STATS_2024)
        self.assertEqual(glory.source_name, 'Hugo Awards')

    def test_2024_qualification_and_formatter_use_rank(self):
        glory = _lookup_year('Some Desperate Glory', 'Emily Tesh', 2024)[0]
        translation = _lookup_year('Translation State', 'Ann Leckie', 2024)[0]
        saint = _lookup_year(
            'The Saint of Bright Doors', 'Vajra Chandrasekera', 2024
        )[0]
        starter = _lookup_year('Starter Villain', 'John Scalzi', 2024)[0]
        self.assertEqual(
            qualify_award_result(glory).decision,
            QualificationDecision.QUALIFIES,
        )
        self.assertEqual(
            qualify_award_result(translation).decision,
            QualificationDecision.QUALIFIES,
        )
        self.assertEqual(
            qualify_award_result(saint).decision,
            QualificationDecision.QUALIFIES,
        )
        self.assertEqual(
            qualify_award_result(starter).decision,
            QualificationDecision.DOES_NOT_QUALIFY,
        )
        self.assertEqual(
            format_award_result(glory),
            '1st - 2024 Hugo Award - Best Novel',
        )
        self.assertEqual(
            format_award_result(translation),
            '2nd - 2024 Hugo Award - Best Novel',
        )
        self.assertEqual(
            format_award_result(saint),
            '5th - 2024 Hugo Award - Best Novel',
        )

    def test_goblin_emperor_matches_plain_katherine_addison_query(self):
        goblin = _lookup_year('The Goblin Emperor', 'Katherine Addison', 2015)[0]
        self.assertEqual(goblin.status, 'Finalist')
        self.assertEqual(goblin.rank, 2)
        self.assertEqual(goblin.work_author, 'Katherine Addison (Sarah Monette)')
        self.assertEqual(goblin.source_url, STATS_2015)
        self.assertEqual(
            _lookup_year('The Goblin Emperor', 'Katherine', 2015),
            [],
        )
        self.assertEqual(
            _lookup_year('The Goblin Emperor', 'Jim Butcher', 2015),
            [],
        )
        self.assertEqual(
            _lookup_year('The Goblin Emperor', 'Sarah Monette', 2015),
            [],
        )

    def test_deaths_end_matches_cixin_liu_without_translator_query(self):
        death = _lookup_year("Death's End", 'Cixin Liu', 2017)[0]
        self.assertEqual(death.status, 'Finalist')
        self.assertEqual(death.rank, 6)
        self.assertEqual(death.work_author, 'Cixin Liu, translated by Ken Liu')
        self.assertNotIn('Ken Liu', hugo._canonical_author(death.work_author))
        self.assertEqual(_lookup_year("Death's End", 'Ken Liu', 2017), [])
        self.assertEqual(
            qualify_award_result(death).decision,
            QualificationDecision.DOES_NOT_QUALIFY,
        )

    def test_three_body_hyphen_and_plain_title_resolve_to_same_2015_winner(self):
        spaced = _lookup_year('The Three Body Problem', 'Cixin Liu', 2015)[0]
        hyphenated = _lookup_year('The Three-Body Problem', 'Cixin Liu', 2015)[0]
        self.assertEqual(spaced.status, 'Winner')
        self.assertEqual(spaced.rank, 1)
        self.assertEqual(hyphenated.status, spaced.status)
        self.assertEqual(hyphenated.rank, spaced.rank)
        self.assertEqual(hyphenated.work_title, spaced.work_title)
        self.assertEqual(hyphenated.source_url, STATS_2015)
        self.assertEqual(
            _lookup_year('The Three', 'Cixin Liu', 2015),
            [],
        )
        self.assertEqual(
            _lookup_year('The Three-Body Problem', 'Ann Leckie', 2015),
            [],
        )

    def test_2015_no_award_does_not_renumber_later_places(self):
        skin = _lookup_year('Skin Game', 'Jim Butcher', 2015)[0]
        dark = _lookup_year(
            'The Dark Between the Stars', 'Kevin J. Anderson', 2015
        )[0]
        three_body = _lookup_year(
            'The Three Body Problem', 'Cixin Liu, Ken Liu translator', 2015
        )[0]
        self.assertEqual(three_body.status, 'Winner')
        self.assertEqual(three_body.rank, 1)
        self.assertEqual(skin.status, 'Finalist')
        self.assertEqual(skin.rank, 5)
        self.assertEqual(skin.source_url, STATS_2015)
        self.assertEqual(dark.rank, 6)
        self.assertEqual(
            qualify_award_result(skin).decision,
            QualificationDecision.QUALIFIES,
        )
        self.assertEqual(
            qualify_award_result(dark).decision,
            QualificationDecision.DOES_NOT_QUALIFY,
        )
        goblin_records = [
            record
            for record in hugo._parse_best_novel_html(HTML_2015, 2015, URL_2015)
            if record.work_title == 'The Goblin Emperor'
        ]
        self.assertEqual(len(goblin_records), 1)
        goblin = hugo._to_award_result(goblin_records[0])
        self.assertEqual(goblin.rank, 2)
        self.assertEqual(goblin.status, 'Finalist')
        self.assertFalse(
            any(result.work_title.casefold() == 'no award' for result in hugo.lookup('Skin Game', 'Jim Butcher'))
        )

    def test_2017_includes_sixth_place_and_translator_author_html(self):
        obelisk = _lookup_year('The Obelisk Gate', 'N. K. Jemisin', 2017)[0]
        death = _lookup_year(
            "Death's End", 'Cixin Liu, translated by Ken Liu', 2017
        )[0]
        self.assertEqual(obelisk.rank, 1)
        self.assertEqual(obelisk.source_url, STATS_2017)
        self.assertEqual(death.status, 'Finalist')
        self.assertEqual(death.rank, 6)
        self.assertEqual(death.work_author, 'Cixin Liu, translated by Ken Liu')
        self.assertEqual(
            qualify_award_result(death).decision,
            QualificationDecision.DOES_NOT_QUALIFY,
        )

    def test_2025_ranks_follow_runoff_not_html_order(self):
        tainted = _lookup_year('The Tainted Cup', 'Robert Jackson Bennett', 2025)[0]
        service = _lookup_year('Service Model', 'Adrian Tchaikovsky', 2025)[0]
        ministry = _lookup_year('The Ministry of Time', 'Kaliane Bradley', 2025)[0]
        self.assertEqual(tainted.rank, 1)
        self.assertEqual(tainted.source_url, STATS_2025)
        self.assertEqual(service.rank, 5)
        self.assertEqual(ministry.rank, 6)

    def test_hyperion_1990_remains_unranked_winner(self):
        results = hugo.lookup('Hyperion', 'Dan Simmons')
        self.assertEqual(len(results), 1)
        hyperion = results[0]
        self.assertEqual(hyperion.award_year, 1990)
        self.assertEqual(hyperion.status, 'Winner')
        self.assertIsNone(hyperion.rank)
        self.assertEqual(hyperion.source_url, URL_1990)
        self.assertEqual(
            qualify_award_result(hyperion).decision,
            QualificationDecision.QUALIFIES,
        )

    def test_moon_is_a_harsh_mistress_keeps_both_unranked_years(self):
        results = hugo.lookup('The Moon is a Harsh Mistress', 'Robert A. Heinlein')
        years = {result.award_year: result for result in results}
        self.assertEqual(set(years), {1966, 1967})
        self.assertEqual(years[1966].status, 'Finalist')
        self.assertIsNone(years[1966].rank)
        self.assertEqual(years[1966].source_url, URL_1966)
        self.assertEqual(years[1967].status, 'Winner')
        self.assertIsNone(years[1967].rank)
        self.assertEqual(years[1967].source_url, URL_1967)
        self.assertEqual(
            qualify_award_result(years[1966]).decision,
            QualificationDecision.REVIEW,
        )
        self.assertEqual(
            qualify_award_result(years[1967]).decision,
            QualificationDecision.QUALIFIES,
        )

    def test_2023_does_not_use_nominating_place(self):
        winner = _lookup_year('Nettle & Bone', 'T. Kingfisher', 2023)[0]
        legends = _lookup_year('Legends & Lattes', 'Travis Baldree', 2023)[0]
        self.assertEqual(winner.status, 'Winner')
        self.assertIsNone(winner.rank)
        self.assertEqual(winner.source_url, URL_2023)
        self.assertEqual(legends.status, 'Finalist')
        self.assertIsNone(legends.rank)

    def test_2026_finalists_remain_unranked(self):
        results = hugo.lookup('A Drop of Corruption', 'Robert Jackson Bennett')
        self.assertEqual(len(results), 1)
        drop = results[0]
        self.assertEqual(drop.award_year, 2026)
        self.assertEqual(drop.status, 'Finalist')
        self.assertIsNone(drop.rank)
        self.assertEqual(drop.source_url, URL_2026)

    def test_1956_does_not_infer_rank_from_list_order(self):
        winner = _lookup_year('Double Star', 'Robert A. Heinlein', 1956)[0]
        second_listed = _lookup_year('Call Him Dead', 'Eric Frank Russell', 1956)[0]
        self.assertEqual(winner.status, 'Winner')
        self.assertIsNone(winner.rank)
        self.assertEqual(second_listed.status, 'Finalist')
        self.assertIsNone(second_listed.rank)
        self.assertEqual(second_listed.source_url, URL_1956)

    def test_1993_tied_winners_remain_unranked(self):
        fire = _lookup_year('A Fire Upon the Deep', 'Vernor Vinge', 1993)[0]
        doomsday = _lookup_year('Doomsday Book', 'Connie Willis', 1993)[0]
        self.assertEqual(fire.status, 'Winner')
        self.assertEqual(doomsday.status, 'Winner')
        self.assertIsNone(fire.rank)
        self.assertIsNone(doomsday.rank)
        self.assertIsNone(fire.notes)
        self.assertEqual(fire.source_url, URL_1993)

    def test_unranked_finalist_remains_review(self):
        fire = _lookup_year('A Fire in the Sun', 'George Alec Effinger', 1990)[0]
        self.assertEqual(fire.status, 'Finalist')
        self.assertIsNone(fire.rank)
        self.assertEqual(
            qualify_award_result(fire).decision,
            QualificationDecision.REVIEW,
        )

    def test_html_finalist_is_not_promoted_to_winner_by_rank_one(self):
        record = hugo._ParsedRecord(
            award_year=2024,
            category=hugo.CATEGORY_BEST_NOVEL,
            status='Finalist',
            work_title='Some Desperate Glory',
            work_author='Emily Tesh',
            source_url=URL_2024,
            match_titles=('Some Desperate Glory',),
        )
        result = hugo._to_award_result(record)
        self.assertEqual(result.status, 'Finalist')
        self.assertIsNone(result.rank)
        self.assertEqual(result.source_url, URL_2024)

    def test_html_winner_is_not_given_a_non_first_rank(self):
        record = hugo._ParsedRecord(
            award_year=2024,
            category=hugo.CATEGORY_BEST_NOVEL,
            status='Winner',
            work_title='Translation State',
            work_author='Ann Leckie',
            source_url=URL_2024,
            match_titles=('Translation State',),
        )
        result = hugo._to_award_result(record)
        self.assertEqual(result.status, 'Winner')
        self.assertIsNone(result.rank)
        self.assertEqual(result.source_url, URL_2024)

    def test_related_title_does_not_take_another_work_rank(self):
        record = hugo._ParsedRecord(
            award_year=2024,
            category=hugo.CATEGORY_BEST_NOVEL,
            status='Finalist',
            work_title='Some Other Glory',
            work_author='Emily Tesh',
            source_url=URL_2024,
            match_titles=('Some Other Glory',),
        )
        result = hugo._to_award_result(record)
        self.assertIsNone(result.rank)
        self.assertEqual(result.source_url, URL_2024)

    def test_best_novella_never_receives_best_novel_rank(self):
        record = hugo._ParsedRecord(
            award_year=2024,
            category=hugo.CATEGORY_BEST_NOVELLA,
            status='Winner',
            work_title='Some Desperate Glory',
            work_author='Emily Tesh',
            source_url=URL_2024,
            match_titles=('Some Desperate Glory',),
        )
        result = hugo._to_award_result(record)
        self.assertEqual(result.category, 'Best Novella')
        self.assertEqual(result.status, 'Winner')
        self.assertIsNone(result.rank)
        self.assertEqual(result.source_url, URL_2024)
        self.assertIsNone(result.notes)

    def test_best_novelette_never_receives_best_novel_rank(self):
        record = hugo._ParsedRecord(
            award_year=2024,
            category=hugo.CATEGORY_BEST_NOVELETTE,
            status='Winner',
            work_title='Some Desperate Glory',
            work_author='Emily Tesh',
            source_url=URL_2024,
            match_titles=('Some Desperate Glory',),
        )
        result = hugo._to_award_result(record)
        self.assertEqual(result.category, 'Best Novelette')
        self.assertEqual(result.status, 'Winner')
        self.assertIsNone(result.rank)
        self.assertEqual(result.source_url, URL_2024)
        self.assertIsNone(result.notes)

    def test_best_short_story_never_receives_best_novel_rank(self):
        record = hugo._ParsedRecord(
            award_year=2024,
            category=hugo.CATEGORY_BEST_SHORT_STORY,
            status='Winner',
            work_title='Some Desperate Glory',
            work_author='Emily Tesh',
            source_url=URL_2024,
            match_titles=('Some Desperate Glory',),
        )
        result = hugo._to_award_result(record)
        self.assertEqual(result.category, 'Best Short Story')
        self.assertEqual(result.status, 'Winner')
        self.assertIsNone(result.rank)
        self.assertEqual(result.source_url, URL_2024)
        self.assertIsNone(result.notes)

    def test_short_fiction_never_receives_best_novel_rank(self):
        record = hugo._ParsedRecord(
            award_year=1966,
            category=hugo.CATEGORY_SHORT_FICTION,
            status='Winner',
            work_title='Some Desperate Glory',
            work_author='Emily Tesh',
            source_url=URL_1966,
            match_titles=('Some Desperate Glory',),
        )
        result = hugo._to_award_result(record)
        self.assertEqual(result.category, 'Short Fiction')
        self.assertEqual(result.status, 'Winner')
        self.assertIsNone(result.rank)
        self.assertEqual(result.source_url, URL_1966)
        self.assertIsNone(result.notes)

    def test_best_novel_or_novelette_never_receives_best_novel_rank(self):
        record = hugo._ParsedRecord(
            award_year=2024,
            category=hugo.CATEGORY_BEST_NOVEL_OR_NOVELETTE,
            status='Winner',
            work_title='Some Desperate Glory',
            work_author='Emily Tesh',
            source_url=URL_2024,
            match_titles=('Some Desperate Glory',),
        )
        result = hugo._to_award_result(record)
        self.assertEqual(result.category, 'Best Novel or Novelette')
        self.assertEqual(result.status, 'Winner')
        self.assertIsNone(result.rank)
        self.assertEqual(result.source_url, URL_2024)
        self.assertIsNone(result.notes)


if __name__ == '__main__':
    unittest.main()
