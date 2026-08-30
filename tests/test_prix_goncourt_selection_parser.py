"""Offline coverage for Prix Goncourt 3ème sélection parsing and merge."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from awards.engine import assess_award_result
from awards.qualifier import QualificationDecision
from awards.registry import PRIX_GONCOURT_POLICY, find_award_policy
from awards.sources import prix_goncourt as pg

_PAGE_TITLE = 'Sélections du prix et lauréats par année | Académie Goncourt'

# Official 2018-2025 3ème sélection works (visible selection-page spelling).
_OFFICIAL_THIRD = {
    2018: (
        ('Frère d’âme', 'David DIOP'),
        ('Maîtres et esclaves', 'Paul GREVEILLAC'),
        ('Leurs enfants après eux', 'Nicolas MATHIEU'),
        ('L’Hiver du mécontentement', 'Thomas B. REVERDY'),
    ),
    2019: (
        ('La part du fils', 'Jean-Luc COATALEM'),
        (
            "Tous les hommes n'habitent pas le monde de la même façon",
            'Jean-Paul DUBOIS',
        ),
        ('Soif', 'Amélie NOTHOMB'),
        ('Extérieur monde', 'Olivier ROLIN'),
    ),
    2020: (
        ('Les impatientes', 'Djaïli AMADOU AMAL'),
        ("L'anomalie", 'Hervé LE TELLIER'),
        ("L'historiographe du Royaume", 'Maël RENOUARD'),
        ('Thésée, sa vie nouvelle', 'Camille de TOLEDO'),
    ),
    2021: (
        ("Le Voyage dans l'Est", 'Christine ANGOT'),
        ('Enfant de salaud', 'Sorj CHALANDON'),
        ('Milwaukee Blues', 'Louis-Philippe DALEMBERT'),
        ('La plus secrète mémoire des hommes', 'Mohamed Mbougar SARR'),
    ),
    2022: (
        ('Le Mage du Kremlin', 'Giuliano da EMPOLI'),
        ('Vivre vite', 'Brigitte GIRAUD'),
        ('Les Presque Sœurs', 'Cloé KORMAN'),
        ('Une somme humaine', 'Makenzy ORCEL'),
    ),
    2023: (
        ('Veiller sur elle', 'Jean-Baptiste ANDREA'),
        ('Humus', 'Gaspard KŒNIG'),
        ("Sarah, Susanne et l'écrivain", 'Éric REINHARDT'),
        ('Triste tigre', 'Neige SINNO'),
    ),
    2024: (
        ("Madelaine avant l'aube", 'Sandrine COLLETTE'),
        ('Houris', 'Kamel DAOUD'),
        ('Jacaranda', 'Gaël FAYE'),
        ('Archipels', 'Hélène GAUDY'),
    ),
    2025: (
        ('La nuit au cœur', 'Nathacha APPANAH'),
        ('Kolkhoze', 'Emmanuel CARRÈRE'),
        ('Le bel obscur', 'Caroline LAMARCHE'),
        ('La maison vide', 'Laurent MAUVIGNIER'),
    ),
}

_WINNER_MARKERS = {
    2018: ('Leurs enfants après eux', 'Nicolas MATHIEU'),
    2019: (
        "Tous les hommes n'habitent pas le monde de la même façon",
        'Jean-Paul DUBOIS',
    ),
    2020: ("L'Anomalie", 'Hervé LE TELLIER'),
    2021: ('La plus secrète mémoire des hommes', 'Mohamed Mbougar Sarr'),
    2022: ('Vivre vite', 'Brigitte GIRAUD'),
    2023: ('Veiller sur elle', 'Jean-Baptiste ANDREA'),
    2024: ('Houris', 'Kamel DAOUD'),
    2025: ('La Maison vide', 'Laurent MAUVIGNIER'),
}

# Nonchronological official-like year presentation order.
_YEAR_ORDER = (
    2024,
    2025,
    2018,
    2023,
    2016,
    2022,
    2021,
    2020,
    2019,
    2017,
)


def _italic_row(author: str, title: str, publisher: str = 'Gallimard') -> str:
    return (
        f'{author}, '
        f'<span style="font-style:italic;">{title}</span> '
        f'({publisher})<br>\n'
    )


def _plain_row(author: str, title: str, publisher: str = 'Gallimard') -> str:
    return f'{author}, {title} ({publisher})<br>\n'


def _year_block(
    year: int,
    *,
    stages: tuple[str, ...] = ('1', '2', '3'),
    third=None,
    winner=None,
    first_rows=(),
    second_rows=(),
    extra_third_html: str = '',
    use_plain_third: bool = False,
) -> str:
    parts = [f'<h3>{year}</h3>\n']
    if winner is not None:
        title, author = winner
        parts.append(_italic_row(author, title))
    stage_rows = {
        '1': first_rows,
        '2': second_rows,
        '3': third if third is not None else (),
    }
    labels = {
        '1': '1ère sélection',
        '2': '2ème sélection',
        '3': '3ème sélection',
    }
    for stage in stages:
        parts.append(f'<p>{labels[stage]}</p>\n')
        for title, author in stage_rows.get(stage, ()):
            if stage == '3' and use_plain_third:
                parts.append(_plain_row(author, title))
            else:
                parts.append(_italic_row(author, title))
        if stage == '3':
            parts.append(extra_third_html)
    parts.append(f'<p>{year}</p>\n')
    return ''.join(parts)


def official_selections_html(
    *,
    years=_YEAR_ORDER,
    include_2016_ambiguous: bool = True,
    current_year_html: str = '',
    extra_before: str = '',
    extra_after: str = '',
    omit_third_years: frozenset[int] = frozenset(),
    corrupt_third_year: int | None = None,
    duplicate_hidden_2023: bool = False,
    title_with_comma: bool = False,
    nonstandard_2018_stages: bool = True,
) -> str:
    parts = [
        '<!doctype html><html><head>',
        f'<title>{_PAGE_TITLE}</title>',
        '</head><body>',
        '<h1>Le Prix GONCOURT: Sélections et Lauréats par année</h1>',
        extra_before,
    ]
    for year in years:
        if year == 2016 and include_2016_ambiguous:
            parts.append(
                '<h5>2016</h5>'
                '<p>Leïla SLIMANI, '
                '<span style="font-style:italic;">Chanson douce</span> '
                'Gallimard</p>'
                '<p>3ème sélection</p>'
                '<p>Author Title Publisher</p>'
                '<p>1ère sélection</p>'
                '<p>2016</p>'
            )
            continue
        if year == 2017:
            parts.append(
                '<h5>2017</h5>'
                '<p>3ème sélection</p>'
                '<p>Someone Something House</p>'
                '<p>2017</p>'
            )
            continue
        if year not in _OFFICIAL_THIRD:
            continue
        stages = ('3', '1', '2') if year == 2018 and nonstandard_2018_stages else (
            '1',
            '2',
            '3',
        )
        extra_third = ''
        if year == 2023 and duplicate_hidden_2023:
            extra_third = _italic_row('Neige SINNO', 'Triste tigre')
        if year == 2020 and title_with_comma:
            extra_third = _plain_row(
                'Camille de TOLEDO',
                'Thésée, sa vie nouvelle',
                'Verdier',
            )
        if year == corrupt_third_year:
            extra_third += '<p>Ambiguous Trusted Row Without Shape</p>\n'
        third = () if year in omit_third_years else _OFFICIAL_THIRD[year]
        parts.append(
            _year_block(
                year,
                stages=stages,
                third=third,
                winner=_WINNER_MARKERS.get(year),
                first_rows=(('Ignored First', 'Auteur Un'),),
                second_rows=(('Ignored Second', 'Auteur Deux'),),
                extra_third_html=extra_third,
                use_plain_third=(year == 2025),
            )
        )
    parts.append(current_year_html)
    parts.append(extra_after)
    parts.append('</body></html>')
    return ''.join(parts)


def _parse(html: str):
    return pg._parse_selections_html(html)


def _canonical_winners():
    return (
        pg._ParsedRecord(
            award_year=2023,
            category=pg.CATEGORY,
            status='Winner',
            work_title='Veiller sur elle',
            work_author='Jean-Baptiste Andréa',
            source_url=pg.WINNERS_URL,
        ),
        pg._ParsedRecord(
            award_year=2025,
            category=pg.CATEGORY,
            status='Winner',
            work_title='La Maison vide',
            work_author='Laurent Mauvignier',
            source_url=pg.WINNERS_URL,
        ),
        pg._ParsedRecord(
            award_year=2020,
            category=pg.CATEGORY,
            status='Winner',
            work_title="L'Anomalie",
            work_author='Hervé LE TELLIER',
            source_url=pg.WINNERS_URL,
        ),
        pg._ParsedRecord(
            award_year=2018,
            category=pg.CATEGORY,
            status='Winner',
            work_title='Leurs enfants après eux',
            work_author='Nicolas MATHIEU',
            source_url=pg.WINNERS_URL,
        ),
    )


class PrixGoncourtSelectionIdentityTests(unittest.TestCase):
    def test_selection_constants(self):
        self.assertEqual(
            pg.SELECTIONS_URL,
            'https://www.academiegoncourt.com/prix-goncourt-et-selection-annee',
        )
        self.assertEqual(pg.FINALIST_MIN_YEAR, 2018)
        self.assertEqual(pg.SELECTION_ENTRY_KIND, 'selections')
        self.assertEqual(pg.SELECTION_CACHE_VERSION, 1)
        self.assertEqual(pg.SELECTION_CACHE_TTL_SECONDS, 633600)
        self.assertEqual(
            pg.SELECTION_CACHE_TTL_SECONDS,
            pg.SELECTION_CACHE_BASE_TTL_SECONDS
            + pg.SELECTION_CACHE_REFRESH_OFFSET_SECONDS,
        )

    def test_page_identity_is_required(self):
        html = '<html><title>Unrelated</title><body>Prix Femina</body></html>'
        with self.assertRaises(pg.PrixGoncourtSourceError) as raised:
            pg._require_selection_identity(html)
        self.assertIn('official year listing', str(raised.exception).casefold())


class PrixGoncourtSelectionCoverageTests(unittest.TestCase):
    def test_trusted_range_begins_2018_and_ignores_pre_2018(self):
        html = official_selections_html()
        with patch.object(pg, '_current_calendar_year', return_value=2026):
            records, markers, snapshot = _parse(html)
            coverage = pg._coverage_from_selection_parse(snapshot)
            pg._validate_selection_archive(
                records,
                coverage,
                snapshot=snapshot,
                winner_records=_canonical_winners(),
            )
        years = {record.award_year for record in records}
        self.assertEqual(min(years), 2018)
        self.assertEqual(max(years), 2025)
        self.assertNotIn(2016, years)
        self.assertNotIn(2017, years)
        self.assertFalse(any(record.award_year < 2018 for record in records))

    def test_every_2018_2025_year_has_four_official_finalists(self):
        html = official_selections_html()
        with patch.object(pg, '_current_calendar_year', return_value=2026):
            records, _markers, snapshot = _parse(html)
        for year, expected in _OFFICIAL_THIRD.items():
            got = [
                (record.work_title, record.work_author)
                for record in records
                if record.award_year == year
            ]
            with self.subTest(year=year):
                self.assertEqual(len(got), 4)
                self.assertEqual(set(got), set(expected))
                self.assertEqual(len(got), len(set(got)))

    def test_first_and_second_selection_rows_are_ignored(self):
        html = official_selections_html()
        records, _markers, _snapshot = _parse(html)
        titles = {record.work_title for record in records}
        self.assertNotIn('Ignored First', titles)
        self.assertNotIn('Ignored Second', titles)
        self.assertTrue(all(record.status == 'Finalist' for record in records))

    def test_nonchronological_year_and_stage_order_still_binds(self):
        html = official_selections_html()
        records, _markers, _snapshot = _parse(html)
        diop = [
            record
            for record in records
            if record.award_year == 2018 and record.work_author == 'David DIOP'
        ]
        self.assertEqual(len(diop), 1)
        self.assertEqual(diop[0].work_title, 'Frère d’âme')

    def test_pre_2018_ambiguous_row_does_not_break_archive(self):
        html = official_selections_html(include_2016_ambiguous=True)
        with patch.object(pg, '_current_calendar_year', return_value=2026):
            records, _markers, snapshot = _parse(html)
            coverage = pg._coverage_from_selection_parse(snapshot)
            pg._validate_selection_archive(records, coverage, snapshot=snapshot)
        self.assertFalse(any(record.award_year == 2016 for record in records))
        self.assertFalse(
            any('Author Title' in record.work_title for record in records)
        )

    def test_ambiguous_trusted_row_rejects_finalist_dataset(self):
        html = official_selections_html(corrupt_third_year=2024)
        with self.assertRaises(pg.PrixGoncourtSourceError) as raised:
            _parse(html)
        self.assertIn('ambiguous', str(raised.exception).casefold())

    def test_hidden_duplicate_is_deduped(self):
        html = official_selections_html(duplicate_hidden_2023=True)
        records, _markers, _snapshot = _parse(html)
        sinno = [
            record
            for record in records
            if record.award_year == 2023 and record.work_author == 'Neige SINNO'
        ]
        self.assertEqual(len(sinno), 1)

    def test_plain_row_title_may_contain_comma(self):
        author, title = pg._parse_plain_book_row(
            'Author, A title, with commas (Publisher)'
        )
        self.assertEqual(author, 'Author')
        self.assertEqual(title, 'A title, with commas')

    def test_italic_and_plain_2025_rows(self):
        html = official_selections_html()
        records, _markers, _snapshot = _parse(html)
        lamarche = [
            record
            for record in records
            if record.work_author == 'Caroline LAMARCHE'
        ]
        self.assertEqual(len(lamarche), 1)
        self.assertEqual(lamarche[0].work_title, 'Le bel obscur')
        self.assertEqual(lamarche[0].award_year, 2025)
        self.assertIsNone(getattr(lamarche[0], 'rank', None))


class PrixGoncourtCurrentYearSelectionTests(unittest.TestCase):
    def test_absent_2026_block_is_valid(self):
        html = official_selections_html()
        with patch.object(pg, '_current_calendar_year', return_value=2026):
            records, _markers, snapshot = _parse(html)
            coverage = pg._coverage_from_selection_parse(snapshot)
            pg._validate_selection_archive(records, coverage, snapshot=snapshot)
        self.assertEqual(coverage['current_year_state'], 'absent')
        self.assertFalse(any(record.award_year == 2026 for record in records))

    def test_synthetic_2026_first_only_is_pre_final(self):
        current = (
            '<h3>2026</h3>'
            '<p>1ère sélection</p>'
            + _italic_row('Auteur Synthétique', 'Livre premier')
            + '<p>2026</p>'
        )
        html = official_selections_html(current_year_html=current)
        with patch.object(pg, '_current_calendar_year', return_value=2026):
            records, _markers, snapshot = _parse(html)
            coverage = pg._coverage_from_selection_parse(snapshot)
            pg._validate_selection_archive(records, coverage, snapshot=snapshot)
        self.assertEqual(coverage['current_year_state'], 'pre_final')
        self.assertFalse(any(record.award_year == 2026 for record in records))

    def test_synthetic_2026_first_and_second_is_pre_final(self):
        current = (
            '<h3>2026</h3>'
            '<p>1ère sélection</p>'
            + _italic_row('Auteur Synthétique', 'Livre premier')
            + '<p>2ème sélection</p>'
            + _italic_row('Auteur Synthétique', 'Livre second')
            + '<p>2026</p>'
        )
        html = official_selections_html(current_year_html=current)
        with patch.object(pg, '_current_calendar_year', return_value=2026):
            records, _markers, snapshot = _parse(html)
            coverage = pg._coverage_from_selection_parse(snapshot)
            pg._validate_selection_archive(records, coverage, snapshot=snapshot)
        self.assertEqual(coverage['current_year_state'], 'pre_final')
        self.assertFalse(any(record.award_year == 2026 for record in records))

    def test_synthetic_2026_third_emits_finalists_without_rank(self):
        current = (
            '<h3>2026</h3>'
            '<p>3ème sélection</p>'
            + _italic_row('Auteur Synthétique', 'Livre final')
            + _italic_row('Autre Auteur', 'Autre livre')
            + '<p>2026</p>'
        )
        html = official_selections_html(current_year_html=current)
        with patch.object(pg, '_current_calendar_year', return_value=2026):
            records, _markers, snapshot = _parse(html)
            coverage = pg._coverage_from_selection_parse(snapshot)
            pg._validate_selection_archive(records, coverage, snapshot=snapshot)
        self.assertEqual(coverage['current_year_state'], 'final_selection')
        current_rows = [record for record in records if record.award_year == 2026]
        self.assertEqual(len(current_rows), 2)
        self.assertTrue(all(record.status == 'Finalist' for record in current_rows))
        result = pg._to_award_result(current_rows[0])
        self.assertIsNone(result.rank)

    def test_synthetic_2026_third_plus_winner_marker_is_winner_state(self):
        current = (
            '<h3>2026</h3>'
            + _italic_row('Auteur Synthétique', 'Livre vainqueur')
            + '<p>3ème sélection</p>'
            + _italic_row('Auteur Synthétique', 'Livre vainqueur')
            + _italic_row('Autre Auteur', 'Autre livre')
            + '<p>2026</p>'
        )
        html = official_selections_html(current_year_html=current)
        with patch.object(pg, '_current_calendar_year', return_value=2026):
            records, markers, snapshot = _parse(html)
            coverage = pg._coverage_from_selection_parse(snapshot)
            pg._validate_selection_archive(records, coverage, snapshot=snapshot)
        self.assertEqual(coverage['current_year_state'], 'winner')
        self.assertEqual(markers[2026], 'Livre vainqueur')


class PrixGoncourtWinnerPrecedenceTests(unittest.TestCase):
    def setUp(self):
        pg._reset_runtime_state()

    def tearDown(self):
        pg._reset_runtime_state()

    def test_2025_canonical_winner_spelling_wins(self):
        winners = (
            pg._ParsedRecord(
                award_year=2025,
                category=pg.CATEGORY,
                status='Winner',
                work_title='La Maison vide',
                work_author='Laurent Mauvignier',
                source_url=pg.WINNERS_URL,
            ),
        )
        finalists = (
            pg._ParsedRecord(
                award_year=2025,
                category=pg.CATEGORY,
                status='Finalist',
                work_title='La maison vide',
                work_author='Laurent MAUVIGNIER',
                source_url=pg.SELECTIONS_URL,
            ),
            pg._ParsedRecord(
                award_year=2025,
                category=pg.CATEGORY,
                status='Finalist',
                work_title='Le bel obscur',
                work_author='Caroline LAMARCHE',
                source_url=pg.SELECTIONS_URL,
            ),
        )
        coverage = {
            'kind': 'finalist_archive',
            'min_year': 2018,
            'max_completed_year': 2025,
            'current_year': 2026,
            'current_year_state': 'absent',
            'winner_marker_titles': {'2025': 'La Maison vide'},
        }
        with patch.object(pg, '_current_calendar_year', return_value=2026):
            results = pg._merge_lookup_results(
                winners,
                finalists,
                coverage,
                'La Maison vide',
                'Laurent Mauvignier',
            )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, 'Winner')
        self.assertEqual(results[0].work_title, 'La Maison vide')
        self.assertEqual(results[0].work_author, 'Laurent Mauvignier')
        self.assertEqual(results[0].source_url, pg.WINNERS_URL)
        self.assertIsNone(results[0].rank)

    def test_2023_author_accent_drift_does_not_duplicate(self):
        winners = (
            pg._ParsedRecord(
                award_year=2023,
                category=pg.CATEGORY,
                status='Winner',
                work_title='Veiller sur elle',
                work_author='Jean-Baptiste Andréa',
                source_url=pg.WINNERS_URL,
            ),
        )
        finalists = (
            pg._ParsedRecord(
                award_year=2023,
                category=pg.CATEGORY,
                status='Finalist',
                work_title='Veiller sur elle',
                work_author='Jean-Baptiste ANDREA',
                source_url=pg.SELECTIONS_URL,
            ),
            pg._ParsedRecord(
                award_year=2023,
                category=pg.CATEGORY,
                status='Finalist',
                work_title='Triste tigre',
                work_author='Neige SINNO',
                source_url=pg.SELECTIONS_URL,
            ),
        )
        coverage = {
            'kind': 'finalist_archive',
            'min_year': 2018,
            'max_completed_year': 2025,
            'current_year': 2026,
            'current_year_state': 'absent',
            'winner_marker_titles': {'2023': 'Veiller sur elle'},
        }
        results = pg._merge_lookup_results(
            winners,
            finalists,
            coverage,
            'Veiller sur elle',
            'Jean-Baptiste Andréa',
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, 'Winner')
        self.assertEqual(results[0].work_author, 'Jean-Baptiste Andréa')
        andrea_query = pg._merge_lookup_results(
            winners,
            finalists,
            coverage,
            'Veiller sur elle',
            'Jean-Baptiste ANDREA',
        )
        self.assertEqual(andrea_query, [])

    def test_nonwinner_finalist_awardresult_schema(self):
        html = official_selections_html()
        records, _markers, _snapshot = _parse(html)
        sinno = [
            record
            for record in records
            if record.work_author == 'Neige SINNO'
        ][0]
        result = pg._to_award_result(sinno)
        self.assertEqual(result.work_title, 'Triste tigre')
        self.assertEqual(result.work_author, 'Neige SINNO')
        self.assertEqual(result.award_name, 'Prix Goncourt')
        self.assertEqual(result.award_year, 2023)
        self.assertEqual(result.category, 'Fiction')
        self.assertEqual(result.status, 'Finalist')
        self.assertIsNone(result.rank)
        self.assertEqual(result.source_name, 'Prix Goncourt')
        self.assertEqual(result.source_url, pg.SELECTIONS_URL)
        self.assertEqual(result.identity_kind, 'work')
        self.assertIsNone(result.notes)
        assessment = assess_award_result(result)
        self.assertIs(find_award_policy(result), PRIX_GONCOURT_POLICY)
        self.assertIs(
            assessment.qualification.decision,
            QualificationDecision.QUALIFIES,
        )

    def test_conflicting_winner_title_rejects_enrichment(self):
        html = official_selections_html()
        with patch.object(pg, '_current_calendar_year', return_value=2026):
            records, _markers, snapshot = _parse(html)
            coverage = pg._coverage_from_selection_parse(snapshot)
            conflicting = (
                pg._ParsedRecord(
                    award_year=2025,
                    category=pg.CATEGORY,
                    status='Winner',
                    work_title='A Completely Different Book',
                    work_author='Laurent Mauvignier',
                    source_url=pg.WINNERS_URL,
                ),
            )
            with self.assertRaises(pg.PrixGoncourtSourceError) as raised:
                pg._validate_selection_archive(
                    records,
                    coverage,
                    snapshot=snapshot,
                    winner_records=conflicting,
                )
        self.assertIn('conflict', str(raised.exception).casefold())


if __name__ == '__main__':
    unittest.main()
