"""Offline coverage for the official Prix Goncourt winners archive parser."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from awards.engine import assess_award_result
from awards.qualifier import QualificationDecision
from awards.sources import prix_goncourt as pg

_ARCHIVE_TITLE = 'Tous les lauréats | Académie Goncourt'

_KNOWN_WINNERS = {
    1903: ('Force ennemie', 'John-Antoine NAU'),
    1906: ("Dingley, l'illustre écrivain", 'Jérôme et Jean THARAUD'),
    1907: (
        'Terres lorraines et Jean des Brebis ou le livre de la misère',
        'Émile MOSELLY',
    ),
    1914: ("L'Appel du sol", 'Adrien BERTRAND'),
    1922: ("Le Vitriol de Lune et Le Martyre de l'obèse", 'Henri BÉRAUD'),
    1951: ('Le Rivage des Syrtes', 'Julien GRACQ'),
    1954: ('Les Mandarins', 'Simone de BEAUVOIR'),
    1960: ('Dieu est né en exil', 'Vintila HORIA'),
    1975: ('La Vie devant soi', 'Émile AJAR (Romain Gary)'),
    1984: ("L'Amant", 'Marguerite DURAS'),
    2010: ('La Carte et le Territoire', 'Michel HOUELLEBECQ'),
    2016: ('Chanson douce', 'Leïla SLIMANI'),
    2020: ("L'Anomalie", 'Hervé LE TELLIER'),
    2023: ('Veiller sur elle', 'Jean-Baptiste Andréa'),
    2025: ('La Maison vide', 'Laurent Mauvignier'),
}

_LINE_NOTES = {
    1914: ' (Calmann-Lévy) (décerné en 1916)',
    1951: ' (José Corti), refusé par l\'auteur',
    1960: ' (Fayard), attribué, mais non décerné.',
}


def _winner_line(
    year: int,
    title: str,
    author: str,
    *,
    italic_title: str | None = None,
    publisher: str = 'Gallimard',
    suffix: str = '',
) -> str:
    shown = title if italic_title is None else italic_title
    return (
        f'{year} - {author}, '
        f'<span style="font-style:italic;">{shown}</span>, '
        f'{publisher}{suffix}<br>\n'
    )


def official_winners_html(
    *,
    max_year: int = 2025,
    skip_year: int | None = None,
    duplicate_year: int | None = None,
    extra_before: str = '',
    extra_after: str = '',
    include_sibling_nav: bool = True,
    italic_overrides: dict[int, str] | None = None,
) -> str:
    parts = [
        '<!doctype html><html><head>',
        f'<title>{_ARCHIVE_TITLE}</title>',
        '</head><body>',
        '<h1>Tous les lauréats</h1>',
        '<p>Prix Goncourt</p>',
    ]
    if include_sibling_nav:
        parts.append(
            '<nav>'
            '<a href="/goncourt-des-lyceens">Goncourt des Lycéens</a>'
            '<a href="/goncourt-du-premier-roman">Goncourt du premier roman</a>'
            '<a href="/goncourt-de-la-nouvelle">Goncourt de la nouvelle</a>'
            '<a href="/goncourt-de-la-poesie">Goncourt de la poésie</a>'
            '<a href="/goncourt-de-la-biographie">Goncourt de la biographie</a>'
            '<a href="/goncourt-des-detenus">Goncourt des détenus</a>'
            '<a href="/choix-goncourt-internationaux">Choix Goncourt internationaux</a>'
            '<a href="/1903-une-double-naissance">1903: une double naissance</a>'
            '</nav>'
        )
        parts.append('<p>Annonce Goncourt de printemps</p>')
    parts.append('<div class="wixui-rich-text">')
    parts.append(extra_before)
    overrides = italic_overrides or {}
    for year in range(max_year, pg.ARCHIVE_MIN_YEAR - 1, -1):
        if year == skip_year:
            continue
        known = _KNOWN_WINNERS.get(year)
        if known:
            title, author = known
        else:
            title, author = f'Stub Title {year}', f'Stub Author {year}'
        italic = overrides.get(year)
        suffix = _LINE_NOTES.get(year, '')
        line = _winner_line(
            year,
            title,
            author,
            italic_title=italic,
            suffix=suffix,
        )
        parts.append(line)
        if year == duplicate_year:
            parts.append(line)
    parts.append(extra_after)
    parts.append('</div></body></html>')
    return ''.join(parts)


def _parse(html: str):
    return pg._parse_winners_html(html)


def _winners_for(records, year: int):
    return [record for record in records if record.award_year == year]


class PrixGoncourtIdentityAndCoverageTests(unittest.TestCase):
    def test_source_constants(self):
        self.assertEqual(pg.SOURCE_KEY, 'prix_goncourt')
        self.assertEqual(pg.AWARD_NAME, 'Prix Goncourt')
        self.assertEqual(pg.SOURCE_NAME, 'Prix Goncourt')
        self.assertEqual(pg.CATEGORY, 'Fiction')
        self.assertEqual(pg.ARCHIVE_MIN_YEAR, 1903)
        self.assertEqual(pg.SITE_ORIGIN, 'https://www.academiegoncourt.com')
        self.assertEqual(
            pg.WINNERS_URL,
            'https://www.academiegoncourt.com/tous-les-laureats-prix-goncourt',
        )
        self.assertEqual(
            pg.SOURCE_HOME_URL,
            'https://www.academiegoncourt.com/presentation-prix-goncourt',
        )
        self.assertEqual(pg.CACHE_TTL_SECONDS, 633600)

    def test_page_identity_is_required(self):
        html = '<html><title>Unrelated</title><body>Prix Femina</body></html>'
        with self.assertRaises(pg.PrixGoncourtSourceError) as raised:
            pg._require_archive_identity(html)
        self.assertIn('official laureates', str(raised.exception))

    def test_complete_official_shaped_archive_is_valid(self):
        html = official_winners_html(max_year=2025)
        records, years = _parse(html)
        with patch.object(pg, '_current_calendar_year', return_value=2026):
            pg._validate_archive(records, years)
        self.assertEqual(min(years), 1903)
        self.assertEqual(max(years), 2025)
        self.assertEqual(len(set(years)), 123)
        self.assertEqual(len(years), 123)

    def test_1903_is_the_earliest_year(self):
        html = official_winners_html(max_year=2025)
        records, years = _parse(html)
        self.assertEqual(min(years), 1903)
        winner = _winners_for(records, 1903)[0]
        self.assertEqual(winner.work_title, 'Force ennemie')
        self.assertEqual(winner.work_author, 'John-Antoine NAU')

    def test_gap_fails_closed(self):
        html = official_winners_html(max_year=2025, skip_year=1950)
        records, years = _parse(html)
        with patch.object(pg, '_current_calendar_year', return_value=2026):
            with self.assertRaises(pg.PrixGoncourtSourceError) as raised:
                pg._validate_archive(records, years)
        self.assertIn('contiguous', str(raised.exception).casefold())

    def test_duplicate_laureate_year_fails(self):
        html = official_winners_html(max_year=2025, duplicate_year=2010)
        records, years = _parse(html)
        with patch.object(pg, '_current_calendar_year', return_value=2026):
            with self.assertRaises(pg.PrixGoncourtSourceError) as raised:
                pg._validate_archive(records, years)
        self.assertIn('2010', str(raised.exception))
        self.assertIn('laureate', str(raised.exception).casefold())

    def test_malformed_empty_author_fails(self):
        html = official_winners_html(max_year=2025)
        html = html.replace(
            '2016 - Leïla SLIMANI, <span style="font-style:italic;">Chanson douce</span>',
            '2016 - <span style="font-style:italic;">Chanson douce</span>',
        )
        records, years = _parse(html)
        with patch.object(pg, '_current_calendar_year', return_value=2026):
            with self.assertRaises(pg.PrixGoncourtSourceError) as raised:
                pg._validate_archive(records, years)
        self.assertIn('empty author', str(raised.exception).casefold())

    def test_malformed_empty_title_fails(self):
        html = official_winners_html(max_year=2025)
        html = html.replace(
            '<span style="font-style:italic;">Chanson douce</span>',
            '<span>Chanson douce</span>',
        )
        records, years = _parse(html)
        with patch.object(pg, '_current_calendar_year', return_value=2026):
            with self.assertRaises(pg.PrixGoncourtSourceError) as raised:
                pg._validate_archive(records, years)
        self.assertIn('empty title', str(raised.exception).casefold())

    def test_current_year_absent_is_valid(self):
        html = official_winners_html(max_year=2025)
        records, years = _parse(html)
        with patch.object(pg, '_current_calendar_year', return_value=2026):
            pg._validate_archive(records, years)
        self.assertFalse(any(record.award_year == 2026 for record in records))

    def test_current_year_present_is_valid(self):
        html = official_winners_html(max_year=2026)
        records, years = _parse(html)
        with patch.object(pg, '_current_calendar_year', return_value=2026):
            pg._validate_archive(records, years)
        self.assertEqual(max(years), 2026)

    def test_stale_historical_max_after_year_rollover_is_invalid(self):
        html = official_winners_html(max_year=2025)
        records, years = _parse(html)
        with patch.object(pg, '_current_calendar_year', return_value=2027):
            with self.assertRaises(pg.PrixGoncourtSourceError) as raised:
                pg._validate_archive(records, years)
        self.assertIn('2025', str(raised.exception))

    def test_source_url_is_the_official_winners_page(self):
        html = official_winners_html(max_year=2025)
        records, _years = _parse(html)
        self.assertTrue(records)
        for record in records:
            self.assertEqual(record.source_url, pg.WINNERS_URL)
            self.assertTrue(pg._source_url_is_usable(record.source_url))


class PrixGoncourtFixtureFactTests(unittest.TestCase):
    def setUp(self):
        html = official_winners_html(
            max_year=2025,
            italic_overrides={2023: 'Veiller sur elle,'},
        )
        self.records, self.years = _parse(html)

    def _winner(self, year: int) -> pg._ParsedRecord:
        matches = _winners_for(self.records, year)
        self.assertEqual(len(matches), 1, year)
        return matches[0]

    def test_known_official_winners(self):
        for year, (title, author) in _KNOWN_WINNERS.items():
            record = self._winner(year)
            with self.subTest(year=year):
                self.assertEqual(record.work_title, title)
                self.assertEqual(record.work_author, author)
                self.assertEqual(record.status, 'Winner')
                self.assertEqual(record.category, 'Fiction')

    def test_2023_trailing_separator_comma_is_stripped(self):
        record = self._winner(2023)
        self.assertEqual(record.work_title, 'Veiller sur elle')
        self.assertFalse(record.work_title.endswith(','))

    def test_internal_punctuation_is_preserved(self):
        self.assertEqual(self._winner(1906).work_title, "Dingley, l'illustre écrivain")
        self.assertEqual(self._winner(2020).work_title, "L'Anomalie")
        self.assertEqual(self._winner(1984).work_title, "L'Amant")

    def test_1914_award_year_stays_1914(self):
        record = self._winner(1914)
        self.assertEqual(record.award_year, 1914)
        self.assertEqual(record.work_author, 'Adrien BERTRAND')
        self.assertEqual(record.work_title, "L'Appel du sol")

    def test_1951_refused_annotation_remains_winner(self):
        record = self._winner(1951)
        self.assertEqual(record.status, 'Winner')
        self.assertEqual(record.work_author, 'Julien GRACQ')

    def test_1960_attributed_not_awarded_remains_winner(self):
        record = self._winner(1960)
        self.assertEqual(record.status, 'Winner')
        self.assertEqual(record.work_author, 'Vintila HORIA')

    def test_1975_parenthetical_author_is_preserved(self):
        record = self._winner(1975)
        self.assertEqual(record.work_author, 'Émile AJAR (Romain Gary)')

    def test_1906_multi_author_string_is_preserved(self):
        record = self._winner(1906)
        self.assertEqual(record.work_author, 'Jérôme et Jean THARAUD')

    def test_1907_and_1922_are_one_combined_official_title(self):
        self.assertEqual(len(_winners_for(self.records, 1907)), 1)
        self.assertEqual(len(_winners_for(self.records, 1922)), 1)
        self.assertEqual(
            self._winner(1907).work_title,
            'Terres lorraines et Jean des Brebis ou le livre de la misère',
        )
        self.assertEqual(
            self._winner(1922).work_title,
            "Le Vitriol de Lune et Le Martyre de l'obèse",
        )

    def test_two_italic_titles_on_one_laureate_line_emit_two_works(self):
        extra = (
            '1922 - Henri BÉRAUD, '
            '<span style="font-style:italic;">Le Vitriol de Lune</span> et '
            '<span style="font-style:italic;">Le Martyre de l\'obèse</span> '
            '(Albin Michel)<br>\n'
        )
        html = official_winners_html(max_year=2025, skip_year=1922, extra_after=extra)
        records, years = _parse(html)
        works = _winners_for(records, 1922)
        self.assertEqual(years.count(1922), 1)
        self.assertEqual(len(works), 2)
        self.assertEqual(works[0].work_title, 'Le Vitriol de Lune')
        self.assertEqual(works[1].work_title, "Le Martyre de l'obèse")
        self.assertEqual(works[0].work_author, 'Henri BÉRAUD')
        self.assertEqual(works[1].work_author, 'Henri BÉRAUD')
        with patch.object(pg, '_current_calendar_year', return_value=2026):
            pg._validate_archive(records, years)


class PrixGoncourtMatchingTests(unittest.TestCase):
    def setUp(self):
        pg._reset_runtime_state()
        self.html = official_winners_html(max_year=2025)
        self.records, self.years = _parse(self.html)

    def tearDown(self):
        pg._reset_runtime_state()

    def test_lookup_returns_official_spelling(self):
        with patch.object(pg, '_load_live_archive', return_value=self.records):
            with patch.object(pg, '_current_calendar_year', return_value=2026):
                results = pg.lookup('la maison vide', 'laurent mauvignier')
        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertEqual(result.work_title, 'La Maison vide')
        self.assertEqual(result.work_author, 'Laurent Mauvignier')
        self.assertEqual(result.award_name, 'Prix Goncourt')
        self.assertEqual(result.award_year, 2025)
        self.assertEqual(result.category, 'Fiction')
        self.assertEqual(result.status, 'Winner')
        self.assertIsNone(result.rank)
        self.assertEqual(result.source_name, 'Prix Goncourt')
        self.assertEqual(result.source_url, pg.WINNERS_URL)
        self.assertEqual(result.identity_kind, 'work')
        self.assertIsNone(result.notes)

    def test_curly_apostrophe_matches_straight(self):
        with patch.object(pg, '_load_live_archive', return_value=self.records):
            results = pg.lookup('L\u2019Anomalie', 'Hervé LE TELLIER')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].work_title, "L'Anomalie")

    def test_accents_are_required_and_not_transliterated(self):
        with patch.object(pg, '_load_live_archive', return_value=self.records):
            self.assertEqual(pg.lookup('Chanson douce', 'Leila Slimani'), [])
            matches = pg.lookup('Chanson douce', 'Leïla Slimani')
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].work_author, 'Leïla SLIMANI')

    def test_official_unaccented_archive_forms_are_not_aliased(self):
        html = official_winners_html(max_year=2025)
        html = html.replace('Stub Title 2015', 'Boussole').replace(
            'Stub Author 2015',
            'Mathias ENARD',
        )
        records, _years = _parse(html)
        with patch.object(pg, '_get_archive_records', return_value=records):
            self.assertEqual(pg.lookup('Boussole', 'Mathias Énard'), [])
            matches = pg.lookup('Boussole', 'Mathias ENARD')
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].work_author, 'Mathias ENARD')

    def test_invented_2026_title_does_not_match(self):
        with patch.object(pg, '_load_live_archive', return_value=self.records):
            self.assertEqual(
                pg.lookup('Un roman imaginaire', 'Auteur Inventé'),
                [],
            )

    def test_series_is_ignored(self):
        with patch.object(pg, '_load_live_archive', return_value=self.records):
            results = pg.lookup(
                'La Maison vide',
                'Laurent Mauvignier',
                series='Ignored Series',
            )
        self.assertEqual(len(results), 1)

    def test_empty_title_or_author_raises(self):
        with self.assertRaises(ValueError):
            pg.lookup('   ', 'Laurent Mauvignier')
        with self.assertRaises(ValueError):
            pg.lookup('La Maison vide', '  ')

    def test_winner_qualifies_without_award_specific_policy(self):
        with patch.object(pg, '_load_live_archive', return_value=self.records):
            results = pg.lookup('La Maison vide', 'Laurent Mauvignier')
        assessment = assess_award_result(results[0])
        self.assertIs(
            assessment.qualification.decision,
            QualificationDecision.QUALIFIES,
        )

    def test_sibling_prize_text_is_not_ingested(self):
        lycéen = [
            record
            for record in self.records
            if 'lycéen' in record.work_title.casefold()
            or 'lycéen' in record.work_author.casefold()
        ]
        self.assertEqual(lycéen, [])
        self.assertFalse(any(record.award_year == 1903 and record.work_title == 'une double naissance' for record in self.records))


if __name__ == '__main__':
    unittest.main()
