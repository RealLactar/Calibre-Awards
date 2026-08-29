"""Offline coverage for the official Booker Prize archive parser."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from awards.engine import assess_award_result
from awards.qualifier import QualificationDecision
from awards.registry import BOOKER_POLICY
from awards.sources import booker

MIDNIGHTS_CHILDREN = 'Midnight\u2019s Children'
FLAUBERTS_PARROT = 'Flaubert\u2019s Parrot'
TOIBIN = 'Colm T\u00f3ib\u00edn'

_ARCHIVE_TITLE = (
    'Full list of Booker Prize winners, shortlisted and longlisted authors '
    'and their books'
)

_KNOWN_WINNERS = {
    1969: (
        ('Something to Answer For', 'P. H. Newby', 'something-to-answer-for'),
    ),
    1970: (
        ('The Elected Member', 'Bernice Rubens', 'the-elected-member'),
    ),
    1972: (
        ('G.', 'John Berger', 'g'),
    ),
    1974: (
        ('The Conservationist', 'Nadine Gordimer', 'the-conservationist'),
        ('Holiday', 'Stanley Middleton', 'holiday'),
    ),
    1981: (
        (MIDNIGHTS_CHILDREN, 'Salman Rushdie', 'midnights-children'),
    ),
    1984: (
        ('Hotel du Lac', 'Anita Brookner', 'hotel-du-lac'),
    ),
    1992: (
        ('The English Patient', 'Michael Ondaatje', 'the-english-patient'),
        ('Sacred Hunger', 'Barry Unsworth', 'sacred-hunger'),
    ),
    1999: (
        ('Disgrace', 'J. M. Coetzee', 'disgrace'),
    ),
    2019: (
        ('Girl, Woman, Other', 'Bernardine Evaristo', 'girl-woman-other'),
        ('The Testaments', 'Margaret Atwood', 'the-testaments'),
    ),
    2022: (
        (
            'The Seven Moons of Maali Almeida',
            'Shehan Karunatilaka',
            'the-seven-moons-of-maali-almeida',
        ),
    ),
    2025: (
        ('Flesh', 'David Szalay', 'flesh'),
    ),
}

_KNOWN_SHORTLIST = {
    1984: (
        ('Empire of the Sun', 'J. G. Ballard', 'empire-of-the-sun'),
        (FLAUBERTS_PARROT, 'Julian Barnes', 'flauberts-parrot'),
    ),
    1999: (
        ('The Blackwater Lightship', TOIBIN, 'the-blackwater-lightship'),
    ),
    2022: (
        ('Oh William!', 'Elizabeth Strout', 'oh-william'),
    ),
}

_LOST_MAN_HTML = """
<h2>The Lost Man Booker Prize</h2>
<p><strong>Winner:</strong>
<a href="/the-booker-library/books/troubles"><em>Troubles</em></a>
by <a href="/the-booker-library/authors/jg-farrell">J.G Farrell</a>
(Phoenix)</p>
"""

_LONGLIST_2026 = (
    (
        'The Shadow of the Object',
        'Chloe Aridjis',
        'the-shadow-of-the-object',
    ),
)


def _book_paragraph(title: str, author: str, slug: str) -> str:
    return (
        f'<p><a href="/the-booker-library/books/{slug}">'
        f'<em>{title}</em></a> by '
        f'<a href="/the-booker-library/authors/{slug}-author">{author}</a> '
        f'(Publisher)</p>\n'
    )


def _stub_winner(year: int) -> tuple[str, str, str]:
    return (f'Stub Winner {year}', f'Stub Winner Author {year}', f'stub-winner-{year}')


def _stub_short(year: int) -> tuple[str, str, str]:
    return (f'Stub Short {year}', f'Stub Short Author {year}', f'stub-short-{year}')


def _year_block(
    year: int,
    *,
    winners=(),
    shortlist=(),
    longlist=(),
    include_winner_in_shortlist=True,
    winner_label=None,
    include_shortlist=True,
    include_judges=False,
) -> str:
    parts = [f'<h2>{year}</h2>\n']
    if winners:
        if winner_label is None:
            winner_label = 'Winners:' if len(winners) > 1 else 'Winner:'
            if year == 2019:
                winner_label = 'Winners'
        parts.append(f'<p><strong>{winner_label}</strong></p>\n')
        for item in winners:
            parts.append(_book_paragraph(*item))
    if include_shortlist and (winners or shortlist):
        parts.append('<p><strong>Shortlist:</strong></p>\n')
        if include_winner_in_shortlist:
            for item in winners:
                parts.append(_book_paragraph(*item))
        for item in shortlist:
            parts.append(_book_paragraph(*item))
    if longlist:
        parts.append('<p><strong>Longlist:</strong></p>\n')
        for item in longlist:
            parts.append(_book_paragraph(*item))
    if include_judges:
        parts.append('<p><strong>Judges:</strong> A chair and four readers.</p>\n')
    return ''.join(parts)


def archive_html(
    *,
    max_year=2026,
    current_winners=(),
    current_shortlist=(),
    current_longlist=_LONGLIST_2026,
    include_winner_in_shortlist=True,
    include_lost_man=True,
) -> str:
    parts = [
        '<!doctype html><html><head>',
        f'<title>{_ARCHIVE_TITLE} | The Booker Prizes</title>',
        '</head><body>',
        f'<h1>{_ARCHIVE_TITLE}</h1>\n',
    ]
    for year in range(max_year, booker.ARCHIVE_MIN_YEAR - 1, -1):
        if year == max_year and year >= 2026:
            parts.append(
                _year_block(
                    year,
                    winners=current_winners,
                    shortlist=current_shortlist,
                    longlist=current_longlist,
                    include_winner_in_shortlist=include_winner_in_shortlist,
                    include_shortlist=bool(current_shortlist or current_winners),
                )
            )
            continue
        winners = _KNOWN_WINNERS.get(year) or (_stub_winner(year),)
        shortlist = _KNOWN_SHORTLIST.get(year) or (_stub_short(year),)
        label = None
        if year == 2019:
            label = 'Winners'
        parts.append(
            _year_block(
                year,
                winners=winners,
                shortlist=shortlist,
                include_winner_in_shortlist=include_winner_in_shortlist,
                winner_label=label,
                include_judges=(year == 1981),
            )
        )
        if year == 1970 and include_lost_man:
            parts.append(_LOST_MAN_HTML)
    parts.append('<h2>Related features</h2>\n')
    parts.append('<h2>The Booker Prizes</h2>\n')
    parts.append('</body></html>')
    return ''.join(parts)


def _parse(html: str):
    return booker._parse_archive_html(html)


def _lookup_from_html(html: str, title: str, author: str):
    records, _years = _parse(html)
    booker._archive_records_cache = records
    return booker.lookup(title, author)


class BookerParserFixtureTests(unittest.TestCase):
    def setUp(self):
        booker._reset_runtime_state()
        self.html = archive_html()
        self.records, self.years = _parse(self.html)

    def tearDown(self):
        booker._reset_runtime_state()

    def _one(self, title, author):
        booker._archive_records_cache = self.records
        results = booker.lookup(title, author)
        self.assertEqual(len(results), 1, results)
        return results[0]

    def test_inaugural_1969_winner(self):
        result = self._one('Something to Answer For', 'P. H. Newby')
        self.assertEqual(result.award_year, 1969)
        self.assertEqual(result.status, 'Winner')
        self.assertEqual(result.work_author, 'P. H. Newby')

    def test_initials_spacing_matches_inaugural_author(self):
        result = self._one('Something to Answer For', 'P.H. Newby')
        self.assertEqual(result.work_author, 'P. H. Newby')

    def test_famous_1981_winner_preserves_curly_apostrophe(self):
        result = self._one(MIDNIGHTS_CHILDREN, 'Salman Rushdie')
        self.assertEqual(result.award_year, 1981)
        self.assertEqual(result.status, 'Winner')
        self.assertEqual(result.work_title, MIDNIGHTS_CHILDREN)
        self.assertIn('\u2019', result.work_title)

    def test_straight_apostrophe_query_matches_official_spelling(self):
        result = self._one("Midnight's Children", 'Salman Rushdie')
        self.assertEqual(result.work_title, MIDNIGHTS_CHILDREN)

    def test_1974_joint_winners_are_separate_winner_rows(self):
        first = self._one('The Conservationist', 'Nadine Gordimer')
        second = self._one('Holiday', 'Stanley Middleton')
        self.assertEqual(first.award_year, 1974)
        self.assertEqual(second.award_year, 1974)
        self.assertEqual(first.status, 'Winner')
        self.assertEqual(second.status, 'Winner')
        self.assertIsNone(first.rank)
        self.assertIsNone(second.rank)
        self.assertNotEqual(first.work_title, second.work_title)

    def test_1992_joint_winners_are_separate_winner_rows(self):
        first = self._one('The English Patient', 'Michael Ondaatje')
        second = self._one('Sacred Hunger', 'Barry Unsworth')
        self.assertEqual(first.status, 'Winner')
        self.assertEqual(second.status, 'Winner')
        self.assertEqual(first.award_year, 1992)

    def test_2019_joint_winners_use_visible_author_not_slug(self):
        first = self._one('Girl, Woman, Other', 'Bernardine Evaristo')
        second = self._one('The Testaments', 'Margaret Atwood')
        self.assertEqual(first.status, 'Winner')
        self.assertEqual(first.work_author, 'Bernardine Evaristo')
        self.assertNotIn('bernadine', first.work_author.casefold())
        self.assertEqual(second.status, 'Winner')

    def test_2025_winner_flesh(self):
        result = self._one('Flesh', 'David Szalay')
        self.assertEqual(result.award_year, 2025)
        self.assertEqual(result.status, 'Winner')

    def test_1984_shortlisted_non_winner(self):
        result = self._one('Empire of the Sun', 'J. G. Ballard')
        self.assertEqual(result.award_year, 1984)
        self.assertEqual(result.status, 'Shortlisted')
        self.assertIsNone(result.rank)
        compact = self._one('Empire of the Sun', 'J.G. Ballard')
        self.assertEqual(compact.work_author, 'J. G. Ballard')

    def test_2022_modern_shortlisted_non_winner(self):
        result = self._one('Oh William!', 'Elizabeth Strout')
        self.assertEqual(result.award_year, 2022)
        self.assertEqual(result.status, 'Shortlisted')

    def test_punctuation_title_g(self):
        result = self._one('G.', 'John Berger')
        self.assertEqual(result.award_year, 1972)
        self.assertEqual(result.work_title, 'G.')
        self.assertEqual(result.status, 'Winner')

    def test_flauberts_parrot_punctuation(self):
        result = self._one(FLAUBERTS_PARROT, 'Julian Barnes')
        self.assertEqual(result.status, 'Shortlisted')
        self.assertEqual(result.work_title, FLAUBERTS_PARROT)

    def test_unicode_toibin_author(self):
        result = self._one('The Blackwater Lightship', TOIBIN)
        self.assertEqual(result.work_author, TOIBIN)
        self.assertEqual(result.status, 'Shortlisted')


class BookerPrecedenceTests(unittest.TestCase):
    def setUp(self):
        booker._reset_runtime_state()

    def tearDown(self):
        booker._reset_runtime_state()

    def test_winner_plus_shortlist_duplicate_emits_winner_only(self):
        matches = [
            record
            for record in _parse(archive_html())[0]
            if record.work_title == 'Flesh'
        ]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].status, 'Winner')

    def test_winner_plus_shortlist_plus_ignored_longlist_emits_winner_only(self):
        html = archive_html()
        html = html.replace(
            '</body></html>',
            '<h2>2025</h2><p><strong>Longlist:</strong></p>'
            + _book_paragraph('Flesh', 'David Szalay', 'flesh')
            + '</body></html>',
        )
        matches = [
            record
            for record in _parse(html)[0]
            if record.work_title == 'Flesh'
        ]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].status, 'Winner')

    def test_shortlisted_plus_longlist_emits_shortlisted_only(self):
        matches = [
            record
            for record in _parse(archive_html())[0]
            if record.work_title == 'Empire of the Sun'
        ]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].status, 'Shortlisted')

    def test_longlist_only_emits_no_result(self):
        booker._archive_records_cache = _parse(archive_html())[0]
        self.assertEqual(
            booker.lookup('The Shadow of the Object', 'Chloe Aridjis'),
            [],
        )

    def test_joint_winner_identities_remain_separate(self):
        records = [
            record
            for record in _parse(archive_html())[0]
            if record.award_year == 2019 and record.status == 'Winner'
        ]
        titles = {record.work_title for record in records}
        self.assertEqual(titles, {'Girl, Woman, Other', 'The Testaments'})

    def test_known_historical_joint_years_have_exactly_two_winners(self):
        self.assertEqual(booker._JOINT_WINNER_YEARS, frozenset({1974, 1992, 2019}))
        records, _years = _parse(archive_html())
        for year in (1974, 1992, 2019):
            winners = [
                record
                for record in records
                if record.award_year == year and record.status == 'Winner'
            ]
            with self.subTest(year=year):
                self.assertEqual(len(winners), 2)
                self.assertEqual({record.status for record in winners}, {'Winner'})


class BookerLostManExclusionTests(unittest.TestCase):
    def setUp(self):
        booker._reset_runtime_state()
        self.records, _years = _parse(archive_html())
        booker._archive_records_cache = self.records

    def tearDown(self):
        booker._reset_runtime_state()

    def test_troubles_is_not_ordinary_1970_booker(self):
        self.assertEqual(booker.lookup('Troubles', 'J. G. Farrell'), [])
        self.assertEqual(booker.lookup('Troubles', 'J.G Farrell'), [])
        self.assertEqual(booker.lookup('Troubles', 'J.G. Farrell'), [])
        years = {
            record.award_year
            for record in self.records
            if record.work_title == 'Troubles'
        }
        self.assertEqual(years, set())

    def test_ordinary_1970_winner_is_the_elected_member(self):
        result = booker.lookup('The Elected Member', 'Bernice Rubens')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].award_year, 1970)
        self.assertEqual(result[0].status, 'Winner')
        self.assertEqual(result[0].work_title, 'The Elected Member')


class BookerCurrentYearTests(unittest.TestCase):
    def setUp(self):
        booker._reset_runtime_state()

    def tearDown(self):
        booker._reset_runtime_state()

    def test_current_year_longlist_only_is_valid_and_absent_from_output(self):
        html = archive_html(max_year=2026)
        with patch.object(booker, '_current_calendar_year', return_value=2026):
            records, years = _parse(html)
            booker._validate_archive(records, years)
        self.assertIn(2026, years)
        booker._archive_records_cache = records
        self.assertEqual(
            booker.lookup('The Shadow of the Object', 'Chloe Aridjis'),
            [],
        )
        self.assertFalse(any(record.award_year == 2026 for record in records))

    def test_current_year_shortlist_does_not_break_historical_validation(self):
        html = archive_html(
            max_year=2026,
            current_shortlist=_LONGLIST_2026[:1],
            current_longlist=_LONGLIST_2026,
        )
        with patch.object(booker, '_current_calendar_year', return_value=2026):
            records, years = _parse(html)
            booker._validate_archive(records, years)
        booker._archive_records_cache = records
        result = booker.lookup('The Shadow of the Object', 'Chloe Aridjis')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].status, 'Shortlisted')
        self.assertEqual(result[0].award_year, 2026)

    def test_current_year_winner_does_not_break_historical_validation(self):
        winner = (('Future Winner', 'Future Author', 'future-winner'),)
        html = archive_html(
            max_year=2026,
            current_winners=winner,
            current_shortlist=winner,
            current_longlist=_LONGLIST_2026,
        )
        with patch.object(booker, '_current_calendar_year', return_value=2026):
            records, years = _parse(html)
            booker._validate_archive(records, years)
        booker._archive_records_cache = records
        result = booker.lookup('Future Winner', 'Future Author')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].status, 'Winner')
        self.assertEqual(result[0].award_year, 2026)

    def test_year_completed_logic_is_patchable(self):
        current = booker._current_calendar_year()
        self.assertTrue(booker._year_is_completed(current - 1))
        self.assertFalse(booker._year_is_completed(current))
        with patch.object(booker, '_current_calendar_year', return_value=2025):
            self.assertFalse(booker._year_is_completed(2025))
            self.assertTrue(booker._year_is_completed(2024))

    def test_completed_year_winner_count_rules(self):
        self.assertTrue(booker._completed_year_winner_count_is_valid(1))
        self.assertTrue(booker._completed_year_winner_count_is_valid(2))
        self.assertFalse(booker._completed_year_winner_count_is_valid(0))
        self.assertFalse(booker._completed_year_winner_count_is_valid(3))


class BookerAwardResultAndValidationTests(unittest.TestCase):
    def setUp(self):
        booker._reset_runtime_state()

    def tearDown(self):
        booker._reset_runtime_state()

    def test_award_result_schema(self):
        result = _lookup_from_html(
            archive_html(),
            MIDNIGHTS_CHILDREN,
            'Salman Rushdie',
        )[0]
        self.assertEqual(result.award_name, 'Booker Prize')
        self.assertEqual(result.category, 'Fiction')
        self.assertEqual(result.source_name, 'The Booker Prize')
        self.assertEqual(result.status, 'Winner')
        self.assertIsNone(result.rank)
        self.assertEqual(result.identity_kind, 'work')
        self.assertEqual(
            result.source_url,
            'https://thebookerprizes.com/the-booker-library/books/midnights-children',
        )
        self.assertIsNone(result.notes)

    def test_shortlisted_qualifies_after_engine_assessment(self):
        result = _lookup_from_html(
            archive_html(),
            'Empire of the Sun',
            'J. G. Ballard',
        )[0]
        assessment = assess_award_result(result)
        self.assertIs(assessment.qualification.decision, QualificationDecision.QUALIFIES)
        self.assertIs(assessment.result, result)
        self.assertIsNone(result.rank)

    def test_winner_not_restated_in_shortlist_still_validates(self):
        html = archive_html(include_winner_in_shortlist=False)
        with patch.object(booker, '_current_calendar_year', return_value=2026):
            records, years = _parse(html)
            booker._validate_archive(records, years)
        flesh = [record for record in records if record.work_title == 'Flesh']
        self.assertEqual(len(flesh), 1)
        self.assertEqual(flesh[0].status, 'Winner')

    def test_shortlist_length_is_not_a_hard_failure(self):
        html = archive_html()
        with patch.object(booker, '_current_calendar_year', return_value=2026):
            records, years = _parse(html)
            booker._validate_archive(records, years)
        short_1984 = [
            record
            for record in records
            if record.award_year == 1984 and record.status == 'Shortlisted'
        ]
        self.assertNotEqual(len(short_1984), 6)

    def test_non_numeric_headings_are_ignored(self):
        _records, years = _parse(archive_html())
        self.assertNotIn(0, years)
        self.assertEqual(min(years), 1969)
        self.assertTrue(all(1969 <= year <= 2026 for year in years))

    def test_missing_identity_fails_closed(self):
        with self.assertRaises(booker.BookerSourceError):
            booker._require_archive_identity('<html><h1>Unrelated page</h1></html>')

    def test_gap_in_numeric_years_fails_closed(self):
        html = archive_html().replace('<h2>1973</h2>', '<h2>Skipped</h2>')
        _records, years = _parse(html)
        with self.assertRaises(booker.BookerSourceError):
            booker._validate_numeric_years(years)

    def test_section_labels_tolerate_missing_colon(self):
        html = (
            f'<html><head><title>{_ARCHIVE_TITLE}</title></head><body>'
            f'<h1>{_ARCHIVE_TITLE}</h1>'
            '<h2>1969</h2>'
            '<p><strong>Winner</strong></p>'
            + _book_paragraph(
                'Something to Answer For', 'P. H. Newby', 'something-to-answer-for'
            )
            + '</body></html>'
        )
        records, _years = _parse(html)
        self.assertEqual(records[0].status, 'Winner')

    def test_empty_title_or_author_is_rejected(self):
        with self.assertRaises(ValueError):
            booker.lookup('  ', 'Salman Rushdie')
        with self.assertRaises(ValueError):
            booker.lookup(MIDNIGHTS_CHILDREN, '  ')

    def test_winner_survives_in_paragraph_shortlist_label(self):
        html = (
            f'<html><head><title>{_ARCHIVE_TITLE}</title></head><body>'
            f'<h1>{_ARCHIVE_TITLE}</h1>'
            '<h2 id=section-3541-title class=" mb-scale-xl"> 1984</h2>'
            '<p><strong>Winner:</strong></p>'
            '<p><a href="/the-booker-library/books/hotel-du-lac"><em>Hotel du Lac</em></a> '
            'by <a href="/the-booker-library/authors/anita-brookner">Anita Brookner</a> '
            '(Jonathan Cape)<br>&nbsp;&nbsp; &nbsp;<br><strong>Shortlist</strong>:</p>'
            '<p><a href="/the-booker-library/books/empire-of-the-sun"><em>Empire of the Sun</em></a> '
            'by <a href="/the-booker-library/authors/jg-ballard">J. G. Ballard</a> '
            '(Gollancz)</p>'
            '</body></html>'
        )
        records, years = _parse(html)
        self.assertEqual(years, (1984,))
        winners = [record for record in records if record.status == 'Winner']
        self.assertEqual(len(winners), 1)
        self.assertEqual(winners[0].work_title, 'Hotel du Lac')
        shortlisted = [record for record in records if record.status == 'Shortlisted']
        self.assertEqual(shortlisted[0].work_title, 'Empire of the Sun')

    def test_title_is_taken_from_book_link_when_em_is_absent(self):
        html = (
            f'<html><head><title>{_ARCHIVE_TITLE}</title></head><body>'
            f'<h1>{_ARCHIVE_TITLE}</h1>'
            '<h2> 2025</h2>'
            '<p dir="ltr"><strong>Winner:</strong></p>'
            '<p dir="ltr"><a href="/the-booker-library/books/flesh">Flesh</a> '
            'by <a href="/the-booker-library/authors/david-szalay">David Szalay</a> '
            '(Jonathan Cape)</p>'
            '</body></html>'
        )
        records, _years = _parse(html)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].work_title, 'Flesh')
        self.assertEqual(records[0].status, 'Winner')

    def test_nbsp_winner_label_and_leading_year_space(self):
        html = (
            f'<html><head><title>{_ARCHIVE_TITLE}</title></head><body>'
            f'<h1>{_ARCHIVE_TITLE}</h1>'
            '<h2> 1969</h2>'
            '<p><strong>Winner:&nbsp;</strong></p>'
            + _book_paragraph(
                'Something to Answer For', 'P. H. Newby', 'something-to-answer-for'
            )
            + '</body></html>'
        )
        records, years = _parse(html)
        self.assertEqual(years, (1969,))
        self.assertEqual(records[0].status, 'Winner')
        self.assertEqual(records[0].work_title, 'Something to Answer For')


if __name__ == '__main__':
    unittest.main()
