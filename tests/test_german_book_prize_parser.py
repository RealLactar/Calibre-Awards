"""Offline coverage for the Deutscher Buchpreis G1 parser and lookup."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from awards.engine import assess_award_result
from awards.qualifier import QualificationDecision
from awards.registry import GERMAN_BOOK_PRIZE_POLICY
from awards.sources import german_book_prize as gbp

SITE = gbp.SITE_ORIGIN


def _page_shell(title: str, canonical: str, body: str) -> str:
    return (
        '<!DOCTYPE html><html><head>'
        f'<title>Deutscher Buchpreis: {title}</title>'
        f'<link rel="canonical" href="{canonical}" />'
        '<meta name="description" content="Mit dem Deutschen Buchpreis '
        'zeichnet die Stiftung Buchkultur und Leseförderung den '
        'deutschsprachigen Roman des Jahres aus." />'
        '</head><body>'
        '<a class="brand" href="/">Deutscher Buchpreis</a>'
        f'{body}'
        '</body></html>'
    )


def _winner_block(year: int, title: str, author: str, *, label: str = 'Autor') -> str:
    return (
        f'<figure class="single-book single-book--winner">'
        f'<img alt="{title}" /></figure>'
        f'<article class="row--intro__content">'
        f'<h4>Roman des Jahres {year}</h4>'
        f'<h2 class="bold">{title}</h2>'
        f'<h4>Begründung der Jury</h4>'
        f'<div>Jury prose about {title} must not become a book.</div>'
        f'<h4 data-author="Nextmotion\\Archive\\Domain\\Model\\Author:1">{label}</h4>'
        f'<p><a href="/archiv/autor/example/">{author}</a></p>'
        f'<h4>Verlag</h4>'
        f'<p><a href="/archiv/verlag/hanser/">Carl Hanser Verlag</a></p>'
        f'</article>'
    )


def _shortlist_tile(book_id: str, title: str) -> str:
    return (
        f'<section class="grid-2">'
        f'<a href="#{book_id}" class="media-with-details media-with-details--is-book">'
        f'<figure class="single-book"><img alt="{title}" /></figure>'
        f'</a></section>'
    )


def _book_panel(
    book_id: str,
    title: str,
    author: str,
    *,
    label: str = 'Autor',
) -> str:
    return (
        f'<section class="grid-12 hidden" id="{book_id}">'
        f'<h3>{title}</h3>'
        f'<h4>Kommentar der Jury</h4>'
        f'<div>Panel jury commentary is not a book.</div>'
        f'<h4 data-author="ignored-typo3-id">{label}</h4>'
        f'<p><a href="/archiv/autor/example/">{author}</a></p>'
        f'<h4>Verlag</h4>'
        f'<p><a href="/archiv/verlag/example/">Example Verlag</a></p>'
        f'</section>'
    )


def _jury_block() -> str:
    return (
        '<section class="cf toggle-list fn-tab-content hidden" id="jury">'
        '<a href="#jury-1" class="media-with-details">'
        '<span>Volker Hage</span></a>'
        '</section>'
        '<section id="jury-1"><h3>Volker Hage</h3>'
        '<p>Begründung der Jury biography is not a book.</p></section>'
    )


def year_page_html(
    year: int,
    *,
    winner=None,
    extra_winners=(),
    shortlist=(),
    longlist=(),
    include_shortlist_section=True,
    include_identity=True,
    page_year=None,
    roman_year=None,
    canonical=None,
    heading_year=None,
) -> str:
    heading = year if heading_year is None else heading_year
    roman = year if roman_year is None else roman_year
    page_h1 = year if page_year is None else page_year
    canonical_url = canonical or gbp._canonical_year_url(year)
    intro = f'<h1 class="bold">{page_h1}</h1>'
    if winner is not None:
        title, author, label = _triple(winner)
        intro += _winner_block(roman, title, author, label=label)
    for extra in extra_winners:
        title, author, label = _triple(extra)
        intro += _winner_block(roman, title, author, label=label)
    tabs = (
        '<nav class="tab-nav">'
        f'<a href="{gbp._canonical_year_url(year)}#tab-shortlist">Shortlist</a>'
        f'<a href="{gbp._canonical_year_url(year)}#tab-longlist">Longlist</a>'
        f'<a href="{gbp._canonical_year_url(year)}#tab-jury">Jury</a>'
        '</nav>'
    )
    short_html = ''
    if include_shortlist_section:
        tiles = ''.join(
            _shortlist_tile(book_id, title)
            for title, _author, book_id, *_rest in (
                _quad(item) for item in shortlist
            )
        )
        short_html = (
            f'<section class="cf toggle-list fn-tab-content" id="shortlist">'
            f'{tiles}</section>'
        )
    long_tiles = ''.join(
        _shortlist_tile(book_id, title)
        for title, _author, book_id, *_rest in (_quad(item) for item in longlist)
    )
    long_html = (
        f'<section class="cf toggle-list fn-tab-content hidden" id="longlist">'
        f'{long_tiles}</section>'
    )
    panels = ''.join(
        _book_panel(book_id, title, author, label=label)
        for title, author, book_id, label in (
            [_quad(item) for item in list(shortlist) + list(longlist)]
        )
    )
    body = (
        f'{intro}{tabs}{short_html}{long_html}{_jury_block()}{panels}'
        '<a href="/videos/">Videos</a>'
        '<a href="/news/">News</a>'
        '<a href="/gaestebuch/">Gästebuch</a>'
        '<a href="/partner/">Partner</a>'
        '<a href="/downloads/2026/">Downloads</a>'
    )
    if include_identity:
        return _page_shell(str(heading), canonical_url, body)
    return (
        f'<!DOCTYPE html><html><head><title>Other site {heading}</title></head>'
        f'<body>{body}</body></html>'
    )


def _triple(item):
    if len(item) == 2:
        return item[0], item[1], 'Autor'
    return item[0], item[1], item[2]


def _quad(item):
    if len(item) == 3:
        return item[0], item[1], item[2], 'Autor'
    return item[0], item[1], item[2], item[3]


# Official facts confirmed from deutscher-buchpreis.de year pages.
YEAR_2005_WINNER = ('Es geht uns gut', 'Arno Geiger', 'book-28')
YEAR_2005_SHORTLIST = (
    YEAR_2005_WINNER,
    ('Die Vermessung der Welt', 'Daniel Kehlmann', 'book-61'),
    ('42', 'Thomas Lehr', 'book-83'),
    ('Dunkle Gesellschaft', 'Gert Loschütz', 'book-92'),
    ('So sind wir', 'Gila Lustiger', 'book-94', 'Autorin'),
    ('Und ich schüttelte einen Liebling', 'Friederike Mayröcker', 'book-100', 'Autorin'),
)
YEAR_2005_LONGLIST = (
    ('Das Geschäftsjahr 1968/69', 'Longlist Only Author', 'book-13'),
)

YEAR_2010_WINNER = ('Tauben fliegen auf', 'Melinda Nadj Abonji', 'book-201', 'Autorin')
YEAR_2010_SHORTLIST = (
    YEAR_2010_WINNER,
    ('Short 2010 B', 'Author 2010 B', 'book-202'),
    ('Short 2010 C', 'Author 2010 C', 'book-203'),
    ('Short 2010 D', 'Author 2010 D', 'book-204'),
    ('Short 2010 E', 'Author 2010 E', 'book-205'),
    ('Short 2010 F', 'Author 2010 F', 'book-206'),
)

YEAR_2024_WINNER = (
    'Hey guten Morgen, wie geht es dir?',
    'Martina Hefter',
    'book-241',
    'Autorin',
)
YEAR_2024_SHORTLIST = (
    YEAR_2024_WINNER,
    ('Short 2024 B', 'Author 2024 B', 'book-242'),
    ('Short 2024 C', 'Author 2024 C', 'book-243'),
    ('Short 2024 D', 'Author 2024 D', 'book-244'),
    ('Short 2024 E', 'Author 2024 E', 'book-245'),
    ('Short 2024 F', 'Author 2024 F', 'book-246'),
)

YEAR_2025_WINNER = ('Die Holländerinnen', 'Dorothee Elmiger', 'book-251', 'Autorin')
YEAR_2025_SHORTLIST = (
    YEAR_2025_WINNER,
    ('ë', 'Jehona Kicaj', 'book-252', 'Autorin'),
    ('Short 2025 C', 'Author 2025 C', 'book-253'),
    ('Short 2025 D', 'Author 2025 D', 'book-254'),
    ('Short 2025 E', 'Author 2025 E', 'book-255'),
    ('Short 2025 F', 'Author 2025 F', 'book-256'),
)


def official_year_html(year: int) -> str:
    if year == 2005:
        return year_page_html(
            2005,
            winner=YEAR_2005_WINNER[:2] + ('Autor',),
            shortlist=YEAR_2005_SHORTLIST,
            longlist=YEAR_2005_LONGLIST,
        )
    if year == 2010:
        return year_page_html(
            2010,
            winner=YEAR_2010_WINNER[:2] + (YEAR_2010_WINNER[3],),
            shortlist=YEAR_2010_SHORTLIST,
        )
    if year == 2024:
        return year_page_html(
            2024,
            winner=YEAR_2024_WINNER[:2] + (YEAR_2024_WINNER[3],),
            shortlist=YEAR_2024_SHORTLIST,
        )
    if year == 2025:
        return year_page_html(
            2025,
            winner=YEAR_2025_WINNER[:2] + (YEAR_2025_WINNER[3],),
            shortlist=YEAR_2025_SHORTLIST,
        )
    winner = (f'Stub Winner {year}', f'Stub Winner Author {year}', 'Autor')
    shortlist = [
        (f'Stub Winner {year}', f'Stub Winner Author {year}', f'book-{year}1'),
        (f'Stub Short {year} B', f'Stub Short Author {year} B', f'book-{year}2'),
        (f'Stub Short {year} C', f'Stub Short Author {year} C', f'book-{year}3'),
        (f'Stub Short {year} D', f'Stub Short Author {year} D', f'book-{year}4'),
        (f'Stub Short {year} E', f'Stub Short Author {year} E', f'book-{year}5'),
        (f'Stub Short {year} F', f'Stub Short Author {year} F', f'book-{year}6'),
    ]
    return year_page_html(year, winner=winner, shortlist=shortlist)


def archive_index_html(
    years,
    *,
    include_hash_duplicates=True,
    extra_links=(),
) -> str:
    options = []
    links = []
    for year in years:
        options.append(f'<option value="/archiv/jahr/{year}/">{year}</option>')
        links.append(f'<a href="/archiv/jahr/{year}/">{year}</a>')
        if include_hash_duplicates and year == 2005:
            links.append(
                f'<a href="/archiv/jahr/{year}/#tab-shortlist">Shortlist</a>'
            )
            links.append(
                f'<a href="/archiv/jahr/{year}/#tab-longlist">Longlist</a>'
            )
            links.append(
                f'<a href="https://www.deutscher-buchpreis.de/archiv/jahr/{year}/'
                f'#tab-jury">Jury</a>'
            )
    extras = ''.join(extra_links)
    body = (
        '<select><option value="">Jahr wählen...</option>'
        f'{"".join(options)}</select>'
        f'{"".join(links)}'
        '<a href="/nominiert/">Nominierte</a>'
        '<a href="/die-jury/">Die Jury</a>'
        '<a href="/videos/">Videos</a>'
        f'{extras}'
    )
    return _page_shell('Archiv', f'{SITE}/archiv/', body)


def nominiert_longlist_only_html(
    year: int = 2026,
    *,
    title='Die Lücken',
    author='Shida Bazyar',
) -> str:
    body = (
        f'<section class="cf toggle-list" id="section_longlist">'
        f'<h3>{year}</h3><h1>Longlist</h1>'
        f'<p>Die nominierten Titel für den Deutschen Buchpreis {year}</p>'
        f'<a href="#booklist-84-1" class="media-with-details--is-book">'
        f'<img alt="{title}" /></a>'
        f'<a href="#booklist-84-2" class="media-with-details--is-book">'
        f'<img alt="Anti Müller" /></a>'
        f'</section>'
        f'<section id="booklist-84-1"><h3>{title}</h3>'
        f'<h4>Autorin</h4><p>{author}</p>'
        f'<h4>Verlag</h4><p><a href="https://example.com/pub">Verlag</a></p>'
        f'</section>'
        f'<section id="booklist-84-2"><h3>Anti Müller</h3>'
        f'<h4>Autorin</h4><p>Yade Yasemin Önder</p></section>'
    )
    return _page_shell('Nominierte', gbp.CURRENT_NOMINEES_URL, body)


def nominiert_shortlist_html(year: int, shortlist, *, winner=None) -> str:
    """Structural current-year /nominiert/ fixture. Not real 2026 facts."""
    intro = f'<h3>{year}</h3><h1>Shortlist</h1>'
    if winner is not None:
        title, author, label = _triple(winner)
        intro = (
            f'<h3>{year}</h3>'
            + _winner_block(year, title, author, label=label)
            + '<h1>Shortlist</h1>'
        )
    tiles = ''.join(
        _shortlist_tile(book_id, title)
        for title, _author, book_id, *_rest in (_quad(item) for item in shortlist)
    )
    panels = ''.join(
        _book_panel(book_id, title, author, label=label)
        for title, author, book_id, label in (_quad(item) for item in shortlist)
    )
    body = (
        f'{intro}'
        f'<section id="shortlist">{tiles}</section>'
        f'{panels}'
    )
    return _page_shell('Nominierte', gbp.CURRENT_NOMINEES_URL, body)


def _record(year, status, title, author, source_url=None):
    return gbp._ParsedRecord(
        award_year=year,
        category=gbp.CATEGORY,
        status=status,
        work_title=title,
        work_author=author,
        source_url=source_url or gbp._canonical_year_url(year),
    )


class ArchiveIndexDiscoveryTests(unittest.TestCase):
    def test_hash_duplicates_collapse_to_one_canonical_year(self):
        html = archive_index_html([2005, 2006], include_hash_duplicates=True)
        years = gbp._discover_archive_years(html)
        self.assertEqual(years, (2005, 2006))

    def test_contiguous_years_from_2005_are_accepted(self):
        html = archive_index_html(range(2005, 2026))
        years = gbp._discover_archive_years(html)
        gbp._validate_discovered_years(years, current_year=2026)
        self.assertEqual(years[0], 2005)
        self.assertEqual(years[-1], 2025)
        self.assertNotIn(2026, years)

    def test_missing_middle_year_fails(self):
        html = archive_index_html([2005, 2006, 2008])
        years = gbp._discover_archive_years(html)
        with self.assertRaises(gbp.DeutscherBuchpreisSourceError) as caught:
            gbp._validate_discovered_years(years, current_year=2009)
        self.assertIn('2007', str(caught.exception))

    def test_non_year_links_are_ignored(self):
        html = archive_index_html(
            [2005, 2006],
            extra_links=(
                '<a href="/news/">News</a>',
                '<a href="/partner/">Partner</a>',
                '<a href="#tab-shortlist">Shortlist tab</a>',
            ),
        )
        self.assertEqual(gbp._discover_archive_years(html), (2005, 2006))

    def test_pre_2005_links_are_ignored(self):
        html = archive_index_html(
            [2005, 2006],
            extra_links=('<a href="/archiv/jahr/2004/">2004</a>',),
        )
        years = gbp._discover_archive_years(html)
        self.assertEqual(years, (2005, 2006))
        gbp._validate_discovered_years(years, current_year=2007)

    def test_current_year_absent_from_index_is_valid(self):
        html = archive_index_html(range(2005, 2026))
        years = gbp._discover_archive_years(html)
        gbp._validate_discovered_years(years, current_year=2026)
        self.assertNotIn(2026, years)

    def test_current_year_present_in_index_is_valid(self):
        html = archive_index_html(range(2005, 2027))
        years = gbp._discover_archive_years(html)
        gbp._validate_discovered_years(years, current_year=2026)
        self.assertIn(2026, years)

    def test_no_permanent_max_year_is_encoded(self):
        self.assertFalse(hasattr(gbp, 'ARCHIVE_MAX_YEAR'))
        html = archive_index_html(range(2005, 2031))
        years = gbp._discover_archive_years(html)
        gbp._validate_discovered_years(years, current_year=2031)
        self.assertEqual(years[-1], 2030)


class HistoricalYearParserTests(unittest.TestCase):
    def test_2005_winner_and_shortlisted_kehlmann(self):
        records = gbp.parse_year_page(official_year_html(2005), 2005, completed=True)
        winner = [r for r in records if r.status == 'Winner']
        self.assertEqual(len(winner), 1)
        self.assertEqual(winner[0].work_title, 'Es geht uns gut')
        self.assertEqual(winner[0].work_author, 'Arno Geiger')
        self.assertEqual(winner[0].source_url, gbp._canonical_year_url(2005))
        kehlmann = [
            r for r in records if r.work_title == 'Die Vermessung der Welt'
        ]
        self.assertEqual(len(kehlmann), 1)
        self.assertEqual(kehlmann[0].status, 'Shortlisted')
        self.assertEqual(kehlmann[0].work_author, 'Daniel Kehlmann')
        self.assertEqual(len(records), 6)

    def test_2010_winner_nadj_abonji(self):
        records = gbp.parse_year_page(official_year_html(2010), 2010, completed=True)
        winner = records[0] if records[0].status == 'Winner' else [
            r for r in records if r.status == 'Winner'
        ][0]
        self.assertEqual(winner.work_title, 'Tauben fliegen auf')
        self.assertEqual(winner.work_author, 'Melinda Nadj Abonji')

    def test_2024_winner_hefter_confirmed_from_official_page(self):
        records = gbp.parse_year_page(official_year_html(2024), 2024, completed=True)
        winner = [r for r in records if r.status == 'Winner'][0]
        self.assertEqual(winner.work_title, 'Hey guten Morgen, wie geht es dir?')
        self.assertEqual(winner.work_author, 'Martina Hefter')

    def test_2025_winner_and_e_diaeresis_title(self):
        records = gbp.parse_year_page(official_year_html(2025), 2025, completed=True)
        winner = [r for r in records if r.status == 'Winner'][0]
        self.assertEqual(winner.work_title, 'Die Holländerinnen')
        self.assertEqual(winner.work_author, 'Dorothee Elmiger')
        unusual = [r for r in records if r.work_title == 'ë']
        self.assertEqual(len(unusual), 1)
        self.assertEqual(unusual[0].work_author, 'Jehona Kicaj')
        self.assertEqual(unusual[0].status, 'Shortlisted')

    def test_autorin_label_is_accepted(self):
        records = gbp.parse_year_page(official_year_html(2025), 2025, completed=True)
        self.assertTrue(any(r.work_author == 'Dorothee Elmiger' for r in records))

    def test_source_url_is_canonical_year_page_not_book_fragment(self):
        records = gbp.parse_year_page(official_year_html(2005), 2005, completed=True)
        for record in records:
            self.assertEqual(record.source_url, gbp._canonical_year_url(2005))
            self.assertNotIn('#book-', record.source_url)

    def test_jury_and_chrome_are_not_books(self):
        records = gbp.parse_year_page(official_year_html(2005), 2005, completed=True)
        titles = {record.work_title for record in records}
        self.assertNotIn('Volker Hage', titles)
        self.assertNotIn('Carl Hanser Verlag', titles)
        authors = {record.work_author for record in records}
        self.assertNotIn('Volker Hage', authors)


class LonglistAndPrecedenceTests(unittest.TestCase):
    def test_longlist_only_work_is_omitted(self):
        records = gbp.parse_year_page(official_year_html(2005), 2005, completed=True)
        titles = {record.work_title for record in records}
        self.assertNotIn('Das Geschäftsjahr 1968/69', titles)

    def test_winner_plus_shortlist_plus_longlist_keeps_winner(self):
        records = gbp.parse_year_page(official_year_html(2005), 2005, completed=True)
        geiger = [r for r in records if r.work_author == 'Arno Geiger']
        self.assertEqual(len(geiger), 1)
        self.assertEqual(geiger[0].status, 'Winner')

    def test_shortlist_plus_longlist_keeps_shortlisted(self):
        records = gbp.parse_year_page(official_year_html(2005), 2005, completed=True)
        kehlmann = [r for r in records if r.work_author == 'Daniel Kehlmann']
        self.assertEqual(len(kehlmann), 1)
        self.assertEqual(kehlmann[0].status, 'Shortlisted')

    def test_apply_precedence_winner_over_shortlisted(self):
        year_url = gbp._canonical_year_url(2005)
        records = gbp._apply_status_precedence(
            [
                _record(2005, 'Shortlisted', 'Es geht uns gut', 'Arno Geiger'),
                _record(2005, 'Winner', 'Es geht uns gut', 'Arno Geiger'),
            ]
        )
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].status, 'Winner')
        self.assertEqual(records[0].source_url, year_url)

    def test_different_works_same_year_remain_separate(self):
        records = gbp._apply_status_precedence(
            [
                _record(2005, 'Winner', 'Es geht uns gut', 'Arno Geiger'),
                _record(
                    2005,
                    'Shortlisted',
                    'Die Vermessung der Welt',
                    'Daniel Kehlmann',
                ),
            ]
        )
        self.assertEqual(len(records), 2)

    def test_longlist_only_precedence_emits_nothing(self):
        self.assertEqual(gbp._apply_status_precedence([]), [])


class FailClosedHistoricalTests(unittest.TestCase):
    def test_zero_winners_fails(self):
        html = year_page_html(
            2005,
            winner=None,
            shortlist=YEAR_2005_SHORTLIST[1:],
        )
        with self.assertRaises(gbp.DeutscherBuchpreisSourceError):
            gbp.parse_year_page(html, 2005, completed=True)

    def test_one_winner_is_valid(self):
        records = gbp.parse_year_page(official_year_html(2005), 2005, completed=True)
        self.assertEqual(sum(1 for r in records if r.status == 'Winner'), 1)

    def test_two_winners_fails(self):
        html = year_page_html(
            2005,
            winner=('Es geht uns gut', 'Arno Geiger', 'Autor'),
            extra_winners=(('Other Winner', 'Other Author', 'Autor'),),
            shortlist=YEAR_2005_SHORTLIST,
        )
        with self.assertRaises(gbp.DeutscherBuchpreisSourceError) as caught:
            gbp.parse_year_page(html, 2005, completed=True)
        self.assertIn('Winner', str(caught.exception))

    def test_no_shortlist_section_fails(self):
        html = year_page_html(
            2005,
            winner=('Es geht uns gut', 'Arno Geiger', 'Autor'),
            shortlist=YEAR_2005_SHORTLIST,
            include_shortlist_section=False,
        )
        with self.assertRaises(gbp.DeutscherBuchpreisSourceError):
            gbp.parse_year_page(html, 2005, completed=True)

    def test_malformed_empty_author_fails(self):
        bad_short = (
            YEAR_2005_WINNER,
            ('Die Vermessung der Welt', '', 'book-61'),
            ('42', 'Thomas Lehr', 'book-83'),
            ('Dunkle Gesellschaft', 'Gert Loschütz', 'book-92'),
            ('So sind wir', 'Gila Lustiger', 'book-94', 'Autorin'),
            (
                'Und ich schüttelte einen Liebling',
                'Friederike Mayröcker',
                'book-100',
                'Autorin',
            ),
        )
        html = year_page_html(
            2005,
            winner=('Es geht uns gut', 'Arno Geiger', 'Autor'),
            shortlist=bad_short,
        )
        with self.assertRaises(gbp.DeutscherBuchpreisSourceError):
            gbp.parse_year_page(html, 2005, completed=True)

    def test_wrong_year_fails(self):
        html = official_year_html(2005)
        with self.assertRaises(gbp.DeutscherBuchpreisSourceError):
            gbp.parse_year_page(html, 2006, completed=True)

    def test_broken_official_identity_fails(self):
        html = year_page_html(
            2005,
            winner=('Es geht uns gut', 'Arno Geiger', 'Autor'),
            shortlist=YEAR_2005_SHORTLIST,
            include_identity=False,
        )
        with self.assertRaises(gbp.DeutscherBuchpreisSourceError):
            gbp.parse_year_page(html, 2005, completed=True)


class CurrentYearNominiertTests(unittest.TestCase):
    def test_2026_longlist_only_is_valid_empty(self):
        records = gbp.parse_nominiert_page(nominiert_longlist_only_html(), 2026)
        self.assertEqual(records, ())

    def test_longlist_titles_are_not_emitted(self):
        records = gbp.parse_nominiert_page(
            nominiert_longlist_only_html(
                title='Anti Müller',
                author='Yade Yasemin Önder',
            ),
            2026,
        )
        self.assertEqual(records, ())

    def test_structural_current_shortlist_without_winner(self):
        shortlist = (
            ('Synthetic Short A', 'Synthetic Author A', 'book-1', 'Autorin'),
            ('Synthetic Short B', 'Synthetic Author B', 'book-2'),
            ('Synthetic Short C', 'Synthetic Author C', 'book-3'),
        )
        html = nominiert_shortlist_html(2026, shortlist)
        records = gbp.parse_nominiert_page(html, 2026)
        self.assertEqual(len(records), 3)
        self.assertTrue(all(record.status == 'Shortlisted' for record in records))
        self.assertTrue(all(record.source_url == gbp.CURRENT_NOMINEES_URL for record in records))
        self.assertTrue(all(record.award_year == 2026 for record in records))

    def test_structural_current_shortlist_and_winner_precedence(self):
        winner = ('Synthetic Winner', 'Synthetic Winner Author', 'Autorin')
        shortlist = (
            ('Synthetic Winner', 'Synthetic Winner Author', 'book-1', 'Autorin'),
            ('Synthetic Finalist B', 'Synthetic Author B', 'book-2'),
            ('Synthetic Finalist C', 'Synthetic Author C', 'book-3'),
        )
        html = nominiert_shortlist_html(2026, shortlist, winner=winner)
        records = gbp.parse_nominiert_page(html, 2026)
        winner_rows = [r for r in records if r.status == 'Winner']
        self.assertEqual(len(winner_rows), 1)
        self.assertEqual(winner_rows[0].work_title, 'Synthetic Winner')
        self.assertEqual(
            [r.status for r in records if r.work_title != 'Synthetic Winner'],
            ['Shortlisted', 'Shortlisted'],
        )
        self.assertTrue(all(r.source_url == gbp.CURRENT_NOMINEES_URL for r in records))

    def test_unrecognized_nominiert_structure_fails_closed(self):
        html = _page_shell(
            'Nominierte',
            gbp.CURRENT_NOMINEES_URL,
            '<h1>Something new</h1><p>No official list markers.</p>',
        )
        with self.assertRaises(gbp.DeutscherBuchpreisSourceError):
            gbp.parse_nominiert_page(html, 2026)


class AcquisitionTests(unittest.TestCase):
    def setUp(self):
        gbp._reset_runtime_state()

    def tearDown(self):
        gbp._reset_runtime_state()

    def _pages(self, current_year=2007, fail_year=None, nominiert=None, archive_2026=None):
        index_years = list(range(2005, current_year))
        pages = {
            gbp.ARCHIVE_INDEX_URL: archive_index_html(index_years),
        }
        for year in index_years:
            pages[gbp._canonical_year_url(year)] = official_year_html(year)
        if fail_year is not None:
            pages[gbp._canonical_year_url(fail_year)] = 'FAIL'
        pages[gbp._canonical_year_url(current_year)] = archive_2026
        pages[gbp.CURRENT_NOMINEES_URL] = nominiert or nominiert_longlist_only_html(
            current_year
        )
        return pages

    def test_one_historical_http_failure_fails_whole_source(self):
        pages = self._pages(current_year=2007)

        def fetch(url):
            if url == gbp._canonical_year_url(2006):
                raise gbp.DeutscherBuchpreisSourceError(
                    'Deutscher Buchpreis request failed with HTTP 500'
                )
            if url not in pages or pages[url] is None:
                raise gbp.DeutscherBuchpreisSourceError(f'missing {url}')
            if pages[url] == 'FAIL':
                raise gbp.DeutscherBuchpreisSourceError('fail')
            return pages[url]

        def fetch_response(url):
            if url == gbp._canonical_year_url(2007):
                return 404, ''
            return 200, fetch(url)

        with (
            patch.object(gbp, '_current_calendar_year', return_value=2007),
            patch.object(gbp, '_fetch_html', side_effect=fetch),
            patch.object(gbp, '_fetch_response', side_effect=fetch_response),
        ):
            with self.assertRaises(gbp.DeutscherBuchpreisSourceError):
                gbp._acquire_complete_records()

    def test_current_archive_404_and_valid_nominiert_succeeds(self):
        pages = self._pages(current_year=2007)

        def fetch(url):
            if url == gbp._canonical_year_url(2007):
                raise AssertionError('current archive 404 must not use _fetch_html')
            return pages[url]

        def fetch_response(url):
            if url == gbp._canonical_year_url(2007):
                return 404, ''
            return 200, pages[url]

        with (
            patch.object(gbp, '_current_calendar_year', return_value=2007),
            patch.object(gbp, '_fetch_html', side_effect=fetch),
            patch.object(gbp, '_fetch_response', side_effect=fetch_response),
        ):
            records = gbp._acquire_complete_records()
        self.assertTrue(any(r.award_year == 2005 for r in records))
        self.assertFalse(any(r.award_year == 2007 for r in records))

    def test_current_year_network_failure_fails_whole_source(self):
        pages = self._pages(current_year=2007)

        def fetch(url):
            if url == gbp.CURRENT_NOMINEES_URL:
                raise gbp.DeutscherBuchpreisSourceError(
                    'Deutscher Buchpreis request failed for nominees'
                )
            return pages[url]

        def fetch_response(url):
            if url == gbp._canonical_year_url(2007):
                return 404, ''
            return 200, pages[url]

        with (
            patch.object(gbp, '_current_calendar_year', return_value=2007),
            patch.object(gbp, '_fetch_html', side_effect=fetch),
            patch.object(gbp, '_fetch_response', side_effect=fetch_response),
        ):
            with self.assertRaises(gbp.DeutscherBuchpreisSourceError):
                gbp._acquire_complete_records()


class MatchingAndLookupTests(unittest.TestCase):
    def setUp(self):
        gbp._reset_runtime_state()
        records = []
        for year in (2005, 2010, 2024, 2025):
            records.extend(
                gbp.parse_year_page(official_year_html(year), year, completed=True)
            )
        records.append(
            _record(2015, 'Winner', 'Gehen, ging, gegangen', 'Jenny Erpenbeck')
        )
        gbp._archive_records_cache = gbp._sort_records(records)

    def tearDown(self):
        gbp._reset_runtime_state()

    def test_lookup_requires_nonempty_title_and_author(self):
        with self.assertRaises(ValueError):
            gbp.lookup(' ', 'Arno Geiger')
        with self.assertRaises(ValueError):
            gbp.lookup('Es geht uns gut', '')

    def test_lookup_ignores_series(self):
        result = gbp.lookup(
            'Es geht uns gut',
            'Arno Geiger',
            series='Ignored Series',
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].status, 'Winner')

    def test_award_result_schema(self):
        result = gbp.lookup('Es geht uns gut', 'Arno Geiger')[0]
        self.assertEqual(result.award_name, 'Deutscher Buchpreis')
        self.assertEqual(result.category, 'Fiction')
        self.assertEqual(result.status, 'Winner')
        self.assertIsNone(result.rank)
        self.assertEqual(result.source_name, 'Deutscher Buchpreis')
        self.assertEqual(result.source_url, gbp._canonical_year_url(2005))
        self.assertEqual(result.identity_kind, 'work')
        self.assertEqual(result.work_title, 'Es geht uns gut')
        self.assertEqual(result.work_author, 'Arno Geiger')

    def test_shortlisted_lookup(self):
        result = gbp.lookup('Die Vermessung der Welt', 'Daniel Kehlmann')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].status, 'Shortlisted')
        self.assertIsNone(result[0].rank)

    def test_longlisted_only_lookup_is_empty(self):
        self.assertEqual(
            gbp.lookup('Das Geschäftsjahr 1968/69', 'Longlist Only Author'),
            [],
        )

    def test_preserves_official_spellings(self):
        cases = (
            ('Es geht uns gut', 'Arno Geiger'),
            ('Die Vermessung der Welt', 'Daniel Kehlmann'),
            ('Tauben fliegen auf', 'Melinda Nadj Abonji'),
            ('Hey guten Morgen, wie geht es dir?', 'Martina Hefter'),
            ('Die Holländerinnen', 'Dorothee Elmiger'),
            ('ë', 'Jehona Kicaj'),
            ('Gehen, ging, gegangen', 'Jenny Erpenbeck'),
        )
        for title, author in cases:
            result = gbp.lookup(title, author)
            self.assertEqual(len(result), 1, msg=title)
            self.assertEqual(result[0].work_title, title)
            self.assertEqual(result[0].work_author, author)

    def test_does_not_transliterate_umlauts(self):
        self.assertEqual(
            gbp.lookup('Die Hollaenderinnen', 'Dorothee Elmiger'),
            [],
        )
        self.assertEqual(
            gbp._normalize_text('ä'),
            gbp._normalize_text('ä'),
        )
        self.assertNotEqual(gbp._normalize_text('ä'), gbp._normalize_text('ae'))
        self.assertNotEqual(gbp._normalize_text('ß'), gbp._normalize_text('ss'))

    def test_quote_and_ampersand_normalization(self):
        gbp._archive_records_cache = (
            _record(2011, 'Winner', 'Night & Day', 'J. G. Example'),
        )
        result = gbp.lookup('Night and Day', 'J.G. Example')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].work_title, 'Night & Day')

    def test_curly_quotes_match_straight(self):
        gbp._archive_records_cache = (
            _record(2012, 'Winner', 'Hey “there”', 'Author'),
        )
        result = gbp.lookup('Hey "there"', 'Author')
        self.assertEqual(len(result), 1)

    def test_deterministic_year_order(self):
        gbp._archive_records_cache = gbp._sort_records(
            [
                _record(2010, 'Winner', 'Tauben fliegen auf', 'Melinda Nadj Abonji'),
                _record(2005, 'Winner', 'Es geht uns gut', 'Arno Geiger'),
            ]
        )
        # Same author would not match both; check sort helper instead.
        ordered = gbp._sort_records(list(gbp._archive_records_cache))
        self.assertEqual(
            [record.award_year for record in ordered],
            [2005, 2010],
        )

    def test_qualifier_winner_and_shortlisted(self):
        winner = gbp.lookup('Es geht uns gut', 'Arno Geiger')[0]
        shortlisted = gbp.lookup('Die Vermessung der Welt', 'Daniel Kehlmann')[0]
        self.assertEqual(
            assess_award_result(winner).qualification.decision,
            QualificationDecision.QUALIFIES,
        )
        self.assertEqual(
            assess_award_result(shortlisted).qualification.decision,
            QualificationDecision.QUALIFIES,
        )
        self.assertEqual(GERMAN_BOOK_PRIZE_POLICY.award_name, 'Deutscher Buchpreis')


if __name__ == '__main__':
    unittest.main()
