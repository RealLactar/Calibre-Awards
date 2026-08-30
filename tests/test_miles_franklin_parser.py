"""Offline coverage for the official Miles Franklin history-page parser."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from awards.engine import assess_award_result
from awards.qualifier import QualificationDecision
from awards.registry import MILES_FRANKLIN_POLICY
from awards.sources import miles_franklin as mf


def _page(inner: str) -> str:
    return (
        '<html><head><title>Miles Franklin judges and history of recipients'
        '</title></head><body>'
        '<h1>Miles Franklin Literary Award</h1>'
        f'{inner}'
        '</body></html>'
    )


def _stub_year(year: int) -> str:
    return (
        f'<h2>{year} Miles Franklin Literary Award</h2>\n'
        f'<p><strong>{year} Winner - Stub Author {year}</strong></p>\n'
        f'<p><strong>Stub Author {year} - Winner</strong></p>\n'
        f'<p><em>Stub Winner {year}</em></p>\n'
        f'<p><strong>Stub Finalist {year} - Finalist</strong></p>\n'
        f'<p><em>Stub Finalist Work {year}</em></p>\n'
    )


def _year_2007() -> str:
    return """
    <h2>2007 Miles Franklin Literary Award</h2>
    <p><strong>2007 Winner - Alexis Wright</strong></p>
    <p><strong>Alexis Wright - Winner</strong></p>
    <p><strong><em>Carpentaria</em></strong></p>
    <p><strong>Biography:</strong></p>
    <p>A long biography that must not replace the card title even when it
    mentions The Eye of the Sheep or other novels at great length for padding
    so the parser treats this paragraph as prose rather than a work title.</p>
    <p>2007 Longlist</p>
    <p><strong>Peter Carey - Finalist</strong></p>
    <p><em>Theft: A Love Story</em></p>
    <p>_____</p>
    <p><strong>Gail Jones - Finalist</strong></p>
    <p><em>Dreams of Speaking</em></p>
    <p>_____</p>
    <p><strong>Deborah Robertson - Finalist</strong></p>
    <p><em>Careless</em></p>
    <p>_____</p>
    <p>John Charalamous</p>
    <p>Silent Parts</p>
    """


def _year_2013() -> str:
    return """
    <h2>2013 Miles Franklin Literary Award</h2>
    <button type="button"><span>Michelle de Kretser - Winner</span></button>
    <p><em>Questions of Travel</em></p>
    <p>2013 Longlist</p>
    <p><strong>Romy Ash - Finalist</strong></p>
    <p><em>Floundering</em></p>
    """


def _year_2014() -> str:
    return """
    <h2>2014 Miles Franklin Literary Award</h2>
    <p><strong>2014 Winner - Evie Wyld</strong></p>
    <p><strong>Evie Wyld - Winner</strong></p>
    <p><em>All The Birds, Singing</em></p>
    """


def _year_2015() -> str:
    return """
    <h2>2015 Miles Franklin Literary Award</h2>
    <p><strong>2015 Winner - Sofie Laguna</strong></p>
    <p><strong>Sofie Laguna - Winner</strong></p>
    <p><em>Eye of the Sheep</em></p>
    <p><strong>Biography:</strong></p>
    <p>In The Eye of the Sheep, her great originality and talent will again
    amaze and move readers with a surprisingly long biographical paragraph
    that uses a different article than the official work card title.</p>
    """


def _year_2016() -> str:
    return """
    <h2>2016 Miles Franklin Literary Award</h2>
    <p><strong>2016 Winner - A.S. Patrić</strong></p>
    <p><strong>A.S. Patrić - Winner</strong></p>
    <p><em>Black Rock White City</em></p>
    """


def _year_2017() -> str:
    return """
    <h2>2017 Miles Franklin Literary Award</h2>
    <p><strong>2017 Winner - Josephine Wilson</strong></p>
    <p><strong>Josephine Wilson -&nbsp;Winner</strong></p>
    <p><em>Extinctions</em></p>
    <p>2017 Longlist</p>
    <p><strong>Mark O’Flynn -&nbsp;Finalist</strong></p>
    <p><em>The Last Days of Ava Langdon</em></p>
    """


def _year_2018() -> str:
    return """
    <h2>2018 Miles Franklin Literary Award</h2>
    <button type="button">2018 Winner - Michelle de Kretser</button>
    <p>Michelle de Kretser</p>
    <p><em>The Life to Come</em></p>
    <p>2018 Shortlist and Longlist</p>
    <p><strong>Felicity Castagna - Finalist</strong></p>
    <p><em>No More Boats</em></p>
    """


def _year_2019() -> str:
    return """
    <h2>2019 Miles Franklin Literary Award</h2>
    <button type="button">2019 Winner - Melissa Lucashenko</button>
    <p>Melissa Lucashenko</p>
    <p><em>Too Much Lip</em></p>
    <button type="button">2020 Shortlist and Longlist</button>
    <p><strong>Michael Mohammed Ahmad - Finalist</strong></p>
    <p><em>The Lebs</em></p>
    """


def _year_2020() -> str:
    return """
    <h2>2020 Miles Franklin Literary Award</h2>
    <button type="button">2020 Winner - Tara June Winch</button>
    <p><em>The Yield</em></p>
    <p>Author photo credit: Tara June Winch</p>
    <p>Penguin Random House Australia</p>
    """


def _year_2022() -> str:
    return """
    <h2>2022 Miles Franklin Literary Award</h2>
    <button type="button"><span>2022 Winner - Jennifer Down</span></button>
    <p><strong>Jennifer Down -&nbsp;</strong><strong>Winner</strong></p>
    <p><em>Bodies of Light</em></p>
    <table class="table-responsive"><tr><td>
    <img src="/photo.jpg" alt="Ignore this photo caption as a title"/>
    </td></tr></table>
    <p>2022 Shortlist and Longlist</p>
    <p><strong>Michael Mohammed Ahmad -&nbsp; Finalist</strong></p>
    <p><em>The Other Half of You</em></p>
    """


def _year_2024() -> str:
    return """
    <h2>2024 Miles Franklin Literary Award</h2>
    <p><strong>2024 Winner - Alexis Wright</strong></p>
    <p><strong>Alexis Wright - Winner</strong></p>
    <p><strong><em>Praiseworthy</em></strong></p>
    <p>2024 Shortlist &amp; Longlist</p>
    <p><strong>Hossein Asgari (Finalist)</strong></p>
    <p><strong><em>Only Sound Remains</em></strong></p>
    """


def _year_2025() -> str:
    return """
    <h2>2025 Miles Franklin Literary Award</h2>
    <button type="button"><span>2025 Winner – Siang Lu</span></button>
    <p><strong>Siang</strong> <strong>Lu (winner)</strong></p>
    <p><strong><em>Ghost</em></strong> <strong><em>Cities</em></strong></p>
    <p>2025 Short &amp; Longlist</p>
    <p><strong>Brian Castro</strong></p>
    <p><em>Chinese Postman</em></p>
    <p>_______</p>
    <p><strong>Tim Winton</strong></p>
    <p><em>Juice</em></p>
    """


def _year_2026() -> str:
    return """
    <h2>2026 Miles Franklin Literary Award</h2>
    <button type="button">2026 Winner</button>
    <p><strong>Omar Musa - Winner</strong></p>
    <p><strong><em>Fierceland</em></strong></p>
    <button type="button">2026 Shortlist and Longlist</button>
    <p><strong>Randa Abdel-Fattah (Shortlist)</strong></p>
    <p><strong><em>Discipline</em></strong></p>
    <p>_______</p>
    <p><strong>I Want Everything</strong></p>
    <p>Dominic Amerena</p>
    <p>_______</p>
    <p><strong>Lyn Dickens</strong></p>
    <p><em>Salt Upon the Water</em></p>
    <p>_______</p>
    <p><strong>Toni Jordan</strong></p>
    <p><em>Tenderfoot</em></p>
    <p>_______</p>
    <p><strong>Steve MinOn (Shortlist)</strong></p>
    <p><em>First Name Second Name</em></p>
    <p>_______</p>
    <p><strong>Madeleine Watts</strong></p>
    <p><em>Elegy, Southwest</em></p>
    <p>_______</p>
    <p><strong>Sean Wilson (Shortlist)</strong></p>
    <p><em>You Must Remember This</em></p>
    <p>_______</p>
    <p><strong>Konrad Muller (Shortlist)</strong></p>
    <p><em>My Heart At Evening</em></p>
    <p>_______</p>
    <p><strong>Josephine Rowe (Shortlist)</strong></p>
    <p><em>Little World</em></p>
    <h2>Judges for the 2026 Award</h2>
    <p><strong>Richard Neville</strong></p>
    <p><strong>Jumana Bayeh</strong></p>
    <p><strong>Dr Mridula Nath Chakraborty</strong></p>
    """


_DETAILED_YEARS = {
    2007: _year_2007,
    2013: _year_2013,
    2014: _year_2014,
    2015: _year_2015,
    2016: _year_2016,
    2017: _year_2017,
    2018: _year_2018,
    2019: _year_2019,
    2020: _year_2020,
    2022: _year_2022,
    2024: _year_2024,
    2025: _year_2025,
    2026: _year_2026,
}


def archive_html(*, max_year: int = 2026) -> str:
    parts = []
    for year in range(mf.ARCHIVE_MIN_YEAR, max_year + 1):
        builder = _DETAILED_YEARS.get(year)
        parts.append(builder() if builder is not None else _stub_year(year))
    parts.append('<h2>News Archive</h2>')
    return _page(''.join(parts))


def _records_for(html: str):
    return mf._parse_archive_html(html).records


def _by_year_status(records, year, status):
    return [
        record
        for record in records
        if record.award_year == year and record.status == status
    ]


class MilesFranklinIdentityTests(unittest.TestCase):
    def test_official_page_identity_is_accepted(self):
        mf._require_archive_identity(archive_html())

    def test_generic_perpetual_page_is_rejected(self):
        with self.assertRaises(mf.MilesFranklinSourceError):
            mf._require_archive_identity(
                '<html><h1>Perpetual</h1><p>Wealth management</p></html>'
            )


class MilesFranklinParserFixtureTests(unittest.TestCase):
    def setUp(self):
        self.html = archive_html(max_year=2026)
        with patch.object(mf, '_current_calendar_year', return_value=2026):
            self.snapshot = mf._parse_archive_html(self.html)
            mf._validate_archive(self.snapshot)
        self.records = self.snapshot.records

    def test_year_headings_are_contiguous_from_2007(self):
        self.assertEqual(
            self.snapshot.year_headings,
            tuple(range(2007, 2027)),
        )

    def test_no_pre_2007_records(self):
        self.assertTrue(all(record.award_year >= 2007 for record in self.records))

    def test_2007_winner(self):
        winners = _by_year_status(self.records, 2007, 'Winner')
        self.assertEqual(len(winners), 1)
        self.assertEqual(winners[0].work_author, 'Alexis Wright')
        self.assertEqual(winners[0].work_title, 'Carpentaria')
        self.assertIsNone(mf._to_award_result(winners[0]).rank)

    def test_2007_finalist_colon_title(self):
        finalists = _by_year_status(self.records, 2007, 'Finalist')
        carey = [item for item in finalists if item.work_author == 'Peter Carey']
        self.assertEqual(len(carey), 1)
        self.assertEqual(carey[0].work_title, 'Theft: A Love Story')
        self.assertEqual(carey[0].status, 'Finalist')

    def test_2007_unlabeled_longlist_is_ignored(self):
        titles = {record.work_title for record in self.records if record.award_year == 2007}
        self.assertNotIn('Silent Parts', titles)

    def test_2013_winner_without_year_winner_heading(self):
        winners = _by_year_status(self.records, 2013, 'Winner')
        self.assertEqual(winners[0].work_author, 'Michelle de Kretser')
        self.assertEqual(winners[0].work_title, 'Questions of Travel')

    def test_2014_comma_title(self):
        winners = _by_year_status(self.records, 2014, 'Winner')
        self.assertEqual(winners[0].work_author, 'Evie Wyld')
        self.assertEqual(winners[0].work_title, 'All The Birds, Singing')

    def test_2015_card_title_not_biography_variant(self):
        winners = _by_year_status(self.records, 2015, 'Winner')
        self.assertEqual(winners[0].work_title, 'Eye of the Sheep')
        self.assertNotEqual(winners[0].work_title, 'The Eye of the Sheep')

    def test_2016_initials_and_diacritic(self):
        winners = _by_year_status(self.records, 2016, 'Winner')
        self.assertEqual(winners[0].work_author, 'A.S. Patrić')
        self.assertEqual(winners[0].work_title, 'Black Rock White City')

    def test_2017_apostrophe_finalist(self):
        finalists = _by_year_status(self.records, 2017, 'Finalist')
        self.assertEqual(finalists[0].work_author, "Mark O’Flynn")
        self.assertEqual(finalists[0].work_title, 'The Last Days of Ava Langdon')

    def test_2018_winner_heading_author_line_omits_winner(self):
        winners = _by_year_status(self.records, 2018, 'Winner')
        self.assertEqual(winners[0].work_author, 'Michelle de Kretser')
        self.assertEqual(winners[0].work_title, 'The Life to Come')

    def test_2019_inner_heading_year_is_ignored(self):
        winners = _by_year_status(self.records, 2019, 'Winner')
        self.assertEqual(winners[0].work_author, 'Melissa Lucashenko')
        finalists = _by_year_status(self.records, 2019, 'Finalist')
        self.assertEqual(finalists[0].work_author, 'Michael Mohammed Ahmad')
        self.assertEqual(finalists[0].award_year, 2019)
        self.assertFalse(
            any(
                record.award_year == 2020 and record.work_title == 'The Lebs'
                for record in self.records
            )
        )

    def test_2020_winner_heading_then_title(self):
        winners = _by_year_status(self.records, 2020, 'Winner')
        self.assertEqual(winners[0].work_author, 'Tara June Winch')
        self.assertEqual(winners[0].work_title, 'The Yield')

    def test_2022_split_winner_strong_and_table_ignored(self):
        winners = _by_year_status(self.records, 2022, 'Winner')
        self.assertEqual(winners[0].work_author, 'Jennifer Down')
        self.assertEqual(winners[0].work_title, 'Bodies of Light')
        titles = {record.work_title for record in self.records}
        self.assertNotIn('Ignore this photo caption as a title', titles)

    def test_2024_paren_finalist(self):
        winners = _by_year_status(self.records, 2024, 'Winner')
        self.assertEqual(winners[0].work_title, 'Praiseworthy')
        finalists = _by_year_status(self.records, 2024, 'Finalist')
        self.assertEqual(finalists[0].work_author, 'Hossein Asgari')
        self.assertEqual(finalists[0].work_title, 'Only Sound Remains')
        self.assertEqual(finalists[0].status, 'Finalist')

    def test_2025_fragmented_winner_and_no_unlabeled_finalists(self):
        winners = _by_year_status(self.records, 2025, 'Winner')
        self.assertEqual(len(winners), 1)
        self.assertEqual(winners[0].work_author, 'Siang Lu')
        self.assertEqual(winners[0].work_title, 'Ghost Cities')
        self.assertEqual(_by_year_status(self.records, 2025, 'Finalist'), [])
        titles = {record.work_title for record in self.records if record.award_year == 2025}
        self.assertNotIn('Chinese Postman', titles)
        self.assertNotIn('Juice', titles)

    def test_2026_winner_and_shortlist_and_longlist(self):
        winners = _by_year_status(self.records, 2026, 'Winner')
        self.assertEqual(len(winners), 1)
        self.assertEqual(winners[0].work_author, 'Omar Musa')
        self.assertEqual(winners[0].work_title, 'Fierceland')
        finalists = _by_year_status(self.records, 2026, 'Finalist')
        pairs = {(item.work_author, item.work_title) for item in finalists}
        self.assertIn(('Randa Abdel-Fattah', 'Discipline'), pairs)
        self.assertIn(('Steve MinOn', 'First Name Second Name'), pairs)
        self.assertIn(('Sean Wilson', 'You Must Remember This'), pairs)
        self.assertIn(('Konrad Muller', 'My Heart At Evening'), pairs)
        self.assertIn(('Josephine Rowe', 'Little World'), pairs)
        self.assertNotIn(('Omar Musa', 'Fierceland'), pairs)
        titles = {record.work_title for record in self.records if record.award_year == 2026}
        self.assertNotIn('I Want Everything', titles)
        self.assertNotIn('Salt Upon the Water', titles)
        self.assertNotIn('Tenderfoot', titles)
        self.assertNotIn('Elegy, Southwest', titles)
        authors = {record.work_author for record in self.records}
        self.assertNotIn('Richard Neville', authors)
        self.assertNotIn('Dominic Amerena', authors)
        self.assertNotIn('Randa Abel-Fattah', authors)

    def test_no_longlist_status_and_rank_always_none(self):
        self.assertTrue(all(record.status in {'Winner', 'Finalist'} for record in self.records))
        for record in self.records:
            result = mf._to_award_result(record)
            self.assertIsNone(result.rank)
            self.assertEqual(result.identity_kind, 'work')
            self.assertEqual(result.award_name, 'Miles Franklin Literary Award')
            self.assertEqual(result.source_url, mf.HISTORY_URL)
            self.assertEqual(result.category, 'Fiction')

    def test_exactly_one_winner_per_year_2007_2026(self):
        for year in range(2007, 2027):
            winners = _by_year_status(self.records, year, 'Winner')
            with self.subTest(year=year):
                self.assertEqual(len(winners), 1)

    def test_current_year_state_is_winner(self):
        self.assertEqual(
            mf._state_from_records(
                self.records,
                2026,
                heading_present=self.snapshot.current_year_heading,
            ),
            'winner',
        )


class MilesFranklinPrecedenceTests(unittest.TestCase):
    def test_winner_suppresses_duplicate_finalist(self):
        html = _page(
            _stub_year(2007).replace(
                'Stub Winner 2007',
                'Shared Work',
            )
            + """
            <h2>2008 Miles Franklin Literary Award</h2>
            <p><strong>2008 Winner - Same Author</strong></p>
            <p><strong>Same Author - Winner</strong></p>
            <p><em>Shared Title</em></p>
            <p><strong>Same Author (Shortlist)</strong></p>
            <p><em>Shared Title</em></p>
            """
            + ''.join(_stub_year(year) for year in range(2009, 2026))
        )
        with patch.object(mf, '_current_calendar_year', return_value=2026):
            records = _records_for(html)
        shared = [
            record
            for record in records
            if record.award_year == 2008 and record.work_title == 'Shared Title'
        ]
        self.assertEqual(len(shared), 1)
        self.assertEqual(shared[0].status, 'Winner')


class MilesFranklinLookupQualificationTests(unittest.TestCase):
    def test_lookup_matches_normalized_title_and_author(self):
        html = archive_html()
        with patch.object(mf, '_current_calendar_year', return_value=2026):
            snapshot = mf._parse_archive_html(html)
            mf._validate_archive(snapshot)
        with patch.object(mf, '_get_archive_records', return_value=snapshot.records):
            results = mf.lookup('fierceland', 'omar musa')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, 'Winner')
        self.assertIsNone(results[0].rank)
        assessment = assess_award_result(results[0])
        self.assertEqual(assessment.qualification.decision, QualificationDecision.QUALIFIES)

    def test_finalist_qualifies_via_policy(self):
        html = archive_html()
        with patch.object(mf, '_current_calendar_year', return_value=2026):
            records = _records_for(html)
        discipline = [
            mf._to_award_result(record)
            for record in records
            if record.work_title == 'Discipline'
        ][0]
        assessment = assess_award_result(discipline)
        self.assertEqual(assessment.qualification.decision, QualificationDecision.QUALIFIES)
        self.assertIs(assessment.qualification.reason.startswith('Award-specific'), True)
        self.assertIsNone(discipline.rank)
        self.assertEqual(MILES_FRANKLIN_POLICY.qualifying_statuses, frozenset({'finalist'}))

    def test_ampersand_title_conjunction_normalization(self):
        self.assertTrue(
            mf._titles_match('Theory and Practice', 'Theory & Practice')
        )


class MilesFranklinCurrentYearStateTests(unittest.TestCase):
    def test_current_year_absent_without_heading(self):
        html = archive_html(max_year=2025)
        with patch.object(mf, '_current_calendar_year', return_value=2026):
            snapshot = mf._parse_archive_html(html)
            mf._validate_archive(snapshot)
            self.assertFalse(snapshot.current_year_heading)
            self.assertEqual(
                mf._state_from_records(
                    snapshot.records,
                    2026,
                    heading_present=False,
                ),
                'absent',
            )

    def test_current_year_longlist_heading_without_labels(self):
        inner_years = []
        for year in range(2007, 2026):
            builder = _DETAILED_YEARS.get(year)
            inner_years.append(builder() if builder else _stub_year(year))
        inner_years.append(
            '<h2>2026 Miles Franklin Literary Award</h2>'
            '<p>2026 Shortlist and Longlist</p>'
            '<p>Unlabeled Author</p>'
            '<p><em>Unlabeled Novel</em></p>'
        )
        html = _page(''.join(inner_years))
        with patch.object(mf, '_current_calendar_year', return_value=2026):
            snapshot = mf._parse_archive_html(html)
            mf._validate_archive(snapshot)
            self.assertTrue(snapshot.current_year_heading)
            self.assertEqual(
                mf._state_from_records(
                    snapshot.records,
                    2026,
                    heading_present=True,
                ),
                'longlist',
            )
            self.assertFalse(
                any(record.award_year == 2026 for record in snapshot.records)
            )

    def test_current_year_shortlist_without_winner(self):
        inner = []
        for year in range(2007, 2026):
            builder = _DETAILED_YEARS.get(year)
            inner.append(builder() if builder else _stub_year(year))
        inner.append(
            '<h2>2026 Miles Franklin Literary Award</h2>'
            '<p><strong>Randa Abdel-Fattah (Shortlist)</strong></p>'
            '<p><em>Discipline</em></p>'
        )
        html = _page(''.join(inner))
        with patch.object(mf, '_current_calendar_year', return_value=2026):
            snapshot = mf._parse_archive_html(html)
            mf._validate_archive(snapshot)
            self.assertEqual(
                mf._state_from_records(
                    snapshot.records,
                    2026,
                    heading_present=True,
                ),
                'shortlist',
            )


if __name__ == '__main__':
    unittest.main()
