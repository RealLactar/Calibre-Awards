"""Offline coverage for the official International Booker Prize archive parser."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from awards.engine import assess_award_result
from awards.qualifier import QualificationDecision
from awards.registry import BOOKER_POLICY, INTERNATIONAL_BOOKER_SHORTLIST_POLICY, find_award_policy
from awards.sources import international_booker as ib

TAIWAN = 'Taiwan Travelogue'
YANG = 'Y\u00e1ng Shu\u0101ng-z\u01d0'
NDIAYE = 'Marie NDiaye'
GAUZ = "GauZ'"
VEGETARIAN = 'The Vegetarian'
CELESTIAL = 'Celestial Bodies'
HEAVEN = 'Heaven'
HEART_LAMP = 'Heart Lamp'
GREENGAGE = 'The Enlightenment of the Greengage Tree'
DEATH_BY_WATER = 'Death by Water'

TAIWAN_URL = (
    'https://thebookerprizes.com/the-booker-library/books/taiwan-travelogue'
)
YEAR_2026_URL = (
    'https://thebookerprizes.com/the-booker-library/prize-years/international/2026'
)
VEGETARIAN_URL = (
    'https://thebookerprizes.com/the-booker-library/books/the-vegetarian'
)

_ARCHIVE_TITLE = (
    'Full list of International Booker Prize winners, nominated authors, '
    'translators and books'
)
_BOOKER_ARCHIVE_TITLE = (
    'Full list of Booker Prize winners, shortlisted and longlisted authors '
    'and their books'
)

_2026_WINNER = (
    TAIWAN,
    YANG,
    'Lin King',
    'taiwan-travelogue',
)
_2026_SHORTLIST = (
    (
        'The Nights Are Quiet in Tehran',
        'Shida Bazyar',
        'Ruth Martin',
        'the-nights-are-quiet-in-tehran',
    ),
    (
        'She Who Remains',
        'Rene Karabash',
        'Izidora Angel',
        'she-who-remains',
    ),
    (
        'The Director',
        'Daniel Kehlmann',
        'Ross Benjamin',
        'the-director',
    ),
    (
        'On Earth As It Is Beneath',
        'Ana Paula Maia',
        'Padma Viswanathan',
        'on-earth-as-it-is-beneath',
    ),
    (
        'The Witch',
        NDIAYE,
        'Jordan Stump',
        'the-witch',
    ),
)

_KNOWN_YEARS = {
    2016: {
        'winner': (
            VEGETARIAN,
            'Han Kang',
            'Deborah Smith',
            'the-vegetarian',
        ),
        'shortlist': (
            (
                'A Whole Life',
                'Robert Seethaler',
                'Charlotte Collins',
                'a-whole-life',
            ),
            (
                'The Story of the Lost Child',
                'Elena Ferrante',
                'Ann Goldstein',
                'the-story-of-the-lost-child',
            ),
            (
                DEATH_BY_WATER,
                'Kenzaburo Oe',
                'Deborah Boliver Boehm',
                'death-by-water',
            ),
            (
                'A Strangeness in My Mind',
                'Orhan Pamuk',
                'Ekin Oklap',
                'a-strangeness-in-my-mind',
            ),
            (
                'The Four Books',
                'Yan Lianke',
                'Carlos Rojas',
                'the-four-books',
            ),
        ),
    },
    2018: {
        'winner': (
            'Flights',
            'Olga Tokarczuk',
            'Jennifer Croft',
            'flights',
        ),
        'shortlist': (
            (
                'The White Book',
                'Olga Tokarczuk',
                'Jennifer Croft',
                'the-white-book',
            ),
            (
                'The World Goes On',
                'L\u00e1szl\u00f3 Krasznahorkai',
                'Ottilie Mulzet and John Batki',
                'the-world-goes-on',
            ),
            (
                'Stub Short 2018-3',
                'Stub Short Author 2018-3',
                'Stub Translator 2018-3',
                'stub-short-2018-3',
            ),
            (
                'Stub Short 2018-4',
                'Stub Short Author 2018-4',
                'Stub Translator 2018-4',
                'stub-short-2018-4',
            ),
            (
                'Stub Short 2018-5',
                'Stub Short Author 2018-5',
                'Stub Translator 2018-5',
                'stub-short-2018-5',
            ),
        ),
    },
    2019: {
        'winner': (
            CELESTIAL,
            'Jokha Alharthi',
            'Marilyn Booth',
            'celestial-bodies',
        ),
        'shortlist': tuple(
            (
                f'Stub Short 2019-{n}',
                f'Stub Short Author 2019-{n}',
                f'Stub Translator 2019-{n}',
                f'stub-short-2019-{n}',
            )
            for n in range(1, 6)
        ),
    },
    2020: {
        'winner': (
            'The Discomfort of Evening',
            'Marieke Lucas Rijneveld',
            'Michele Hutchison',
            'the-discomfort-of-evening',
        ),
        'shortlist': (
            (
                GREENGAGE,
                'Shokoofeh Azar',
                'Anonymous',
                'the-enlightenment-of-the-greengage-tree',
            ),
            *(
                (
                    f'Stub Short 2020-{n}',
                    f'Stub Short Author 2020-{n}',
                    f'Stub Translator 2020-{n}',
                    f'stub-short-2020-{n}',
                )
                for n in range(2, 6)
            ),
        ),
    },
    2022: {
        'winner': (
            'Tomb of Sand',
            'Geetanjali Shree',
            'Daisy Rockwell',
            'tomb-of-sand',
        ),
        'shortlist': (
            (
                HEAVEN,
                'Mieko Kawakami',
                'Sam Bett and David Boyd',
                'heaven',
            ),
            *(
                (
                    f'Stub Short 2022-{n}',
                    f'Stub Short Author 2022-{n}',
                    f'Stub Translator 2022-{n}',
                    f'stub-short-2022-{n}',
                )
                for n in range(2, 6)
            ),
        ),
    },
    2023: {
        'winner': (
            'Time Shelter',
            'Georgi Gospodinov',
            'Angela Rodel',
            'time-shelter',
        ),
        'shortlist': (
            (
                'Standing Heavy',
                GAUZ,
                'Frank Wynne',
                'standing-heavy',
            ),
            *(
                (
                    f'Stub Short 2023-{n}',
                    f'Stub Short Author 2023-{n}',
                    f'Stub Translator 2023-{n}',
                    f'stub-short-2023-{n}',
                )
                for n in range(2, 6)
            ),
        ),
    },
    2025: {
        'winner': (
            HEART_LAMP,
            'Banu Mushtaq',
            'Deepa Bhasthi',
            'heart-lamp',
            'Kannada',
        ),
        'shortlist': tuple(
            (
                f'Stub Short 2025-{n}',
                f'Stub Short Author 2025-{n}',
                f'Stub Translator 2025-{n}',
                f'stub-short-2025-{n}',
            )
            for n in range(1, 6)
        ),
    },
}


def _book_href(slug: str, *, node: int | None = None) -> str:
    if node is not None:
        return f'/node/{node}'
    return f'/the-booker-library/books/{slug}'


def _work_paragraph(
    title: str,
    author: str,
    translator: str,
    slug: str,
    *,
    node: int | None = None,
    from_language: str | None = None,
    publisher: str = 'Publisher',
) -> str:
    href = _book_href(slug, node=node)
    if from_language:
        translated = f'translated from {from_language} by {translator}'
    else:
        translated = f'translated by {translator}'
    return (
        f'<p><a href="{href}"><em>{title}</em></a> by '
        f'<a href="/the-booker-library/authors/{slug}-author">{author}</a>, '
        f'{translated} ({publisher})</p>\n'
    )


def _work_tuple_paragraph(item, *, node: int | None = None) -> str:
    from_language = item[4] if len(item) > 4 else None
    return _work_paragraph(
        item[0],
        item[1],
        item[2],
        item[3],
        node=node,
        from_language=from_language,
    )


def _stub_winner(year: int) -> tuple[str, str, str, str]:
    return (
        f'Stub Winner {year}',
        f'Stub Winner Author {year}',
        f'Stub Translator {year}',
        f'stub-winner-{year}',
    )


def _stub_short(year: int, index: int) -> tuple[str, str, str, str]:
    return (
        f'Stub Short {year}-{index}',
        f'Stub Short Author {year}-{index}',
        f'Stub Translator {year}-{index}',
        f'stub-short-{year}-{index}',
    )


def _year_works(year: int) -> tuple[tuple, tuple]:
    if year == 2026:
        return (_2026_WINNER, _2026_SHORTLIST)
    known = _KNOWN_YEARS.get(year)
    if known is not None:
        return (known['winner'], known['shortlist'])
    return (
        _stub_winner(year),
        tuple(_stub_short(year, index) for index in range(1, 6)),
    )


def _year_block(
    year: int,
    *,
    include_winner_in_shortlist=True,
    include_longlist=True,
    include_judges=True,
    node_shortlist=False,
    omit_winner=False,
    extra_shortlist=(),
    extra_longlist=(),
) -> str:
    winner, shortlist = _year_works(year)
    parts = [f'<h2>{year}</h2>\n']
    if not omit_winner:
        parts.append('<p><strong>Winner:</strong></p>\n')
        node = 5800 + year if node_shortlist else None
        parts.append(_work_tuple_paragraph(winner, node=node))
    parts.append('<p><strong>Shortlist:</strong></p>\n')
    short_rows = []
    if include_winner_in_shortlist and not omit_winner:
        short_rows.append(winner)
    short_rows.extend(shortlist)
    short_rows.extend(extra_shortlist)
    for index, item in enumerate(short_rows):
        node = 5900 + year * 10 + index if node_shortlist else None
        parts.append(_work_tuple_paragraph(item, node=node))
    if include_longlist:
        parts.append('<p><strong>Longlist:</strong></p>\n')
        long_rows = []
        if not omit_winner:
            long_rows.append(winner)
        long_rows.extend(shortlist)
        long_rows.extend(extra_longlist)
        for item in long_rows:
            parts.append(_work_tuple_paragraph(item))
        parts.append(
            _work_paragraph(
                f'Longlist Only {year}',
                f'Longlist Author {year}',
                f'Longlist Translator {year}',
                f'longlist-only-{year}',
            )
        )
        if year == 2021:
            parts.append(
                _work_paragraph(
                    'The Perfect Nine',
                    'Ngugi wa Thiong\'o',
                    'the author',
                    'the-perfect-nine',
                )
            )
    if include_judges:
        parts.append(
            '<p><strong>Judges:</strong> A chair and four readers.</p>\n'
        )
    return ''.join(parts)


def _legacy_author_block(year: int, label: str) -> str:
    return (
        f'<h2>{year}</h2>\n'
        '<p><strong>Winner:</strong></p>\n'
        f'<p><a href="/the-booker-library/authors/legacy-{year}">'
        f'Legacy Winner {year}</a></p>\n'
        f'<p><strong>{label}</strong></p>\n'
        f'<p><a href="/the-booker-library/authors/legacy-finalist-{year}">'
        f'Legacy Finalist {year}</a></p>\n'
    )


def _translator_prize_2015() -> str:
    return (
        '<p>The \u00a315,000 translator\u2019s prize was awarded to '
        'George Szirtes and Ottilie Mulzet.</p>\n'
    )


def _related_and_other_chrome() -> str:
    return (
        '<h2>Related content</h2>\n'
        '<p><a href="/the-booker-library/books/flesh"><em>Flesh</em></a> '
        'by <a href="/the-booker-library/authors/david-szalay">'
        'David Szalay</a></p>\n'
        '<h2>The Booker Prize</h2>\n'
        '<p><strong>Winner:</strong></p>\n'
        + _work_paragraph(
            'Flesh',
            'David Szalay',
            'Nobody',
            'flesh',
        )
        + '<h2>The Children\'s Booker Prize</h2>\n'
        '<p><strong>Winner:</strong></p>\n'
        + _work_paragraph(
            'Children Stub',
            'Children Author',
            'Children Translator',
            'children-stub',
        )
    )


def _2027_block() -> str:
    winner = (
        'Bukhman Stub Winner',
        'Bukhman Winner Author',
        'Bukhman Winner Translator',
        'bukhman-stub-winner',
    )
    shortlist = tuple(
        (
            f'Bukhman Stub Short {n}',
            f'Bukhman Short Author {n}',
            f'Bukhman Short Translator {n}',
            f'bukhman-stub-short-{n}',
        )
        for n in range(1, 6)
    )
    parts = ['<h2>2027</h2>\n', '<p><strong>Winner:</strong></p>\n']
    parts.append(_work_tuple_paragraph(winner))
    parts.append('<p><strong>Shortlist:</strong></p>\n')
    parts.append(_work_tuple_paragraph(winner))
    for item in shortlist:
        parts.append(_work_tuple_paragraph(item))
    return ''.join(parts)


def archive_html(
    *,
    include_legacy=True,
    include_2027=False,
    include_chrome=True,
    node_2026=True,
    omit_year=None,
    truncated_2026=False,
    skip_identity=False,
) -> str:
    title = 'Unrelated listing' if skip_identity else _ARCHIVE_TITLE
    parts = [
        '<!doctype html><html><head>',
        f'<title>{title} | The Booker Prizes</title>',
        '</head><body>',
        f'<h1>{title}</h1>\n',
    ]
    for year in range(2026, ib.ARCHIVE_MIN_YEAR - 1, -1):
        if omit_year == year:
            continue
        if year == 2026 and truncated_2026:
            parts.append(
                '<h2>2026</h2>\n'
                '<p><strong>Winner:</strong></p>\n'
                + _work_tuple_paragraph(_2026_WINNER, node=5863)
                + '<p><strong>Shortlist:</strong></p>\n'
                + _work_tuple_paragraph(_2026_WINNER, node=5863)
                + _work_tuple_paragraph(_2026_SHORTLIST[0], node=5864)
            )
            continue
        parts.append(
            _year_block(
                year,
                node_shortlist=(year == 2026 and node_2026),
            )
        )
    if include_legacy:
        parts.append(_legacy_author_block(2015, 'The finalists:'))
        parts.append(_translator_prize_2015())
        parts.append(_legacy_author_block(2013, 'Finalists:'))
        parts.append(_legacy_author_block(2009, 'Nominees:'))
        parts.append(_legacy_author_block(2005, 'Winner:'))
    if include_2027:
        parts.append(_2027_block())
    if include_chrome:
        parts.append(_related_and_other_chrome())
    parts.append('</body></html>')
    return ''.join(parts)


def _parse(html: str):
    return ib._parse_archive_html(html)


def _load(html: str):
    ib._require_archive_identity(html)
    records, years = _parse(html)
    ib._validate_archive(records, years)
    ib._archive_records_cache = records
    return records, years


def _lookup_from_html(html: str, title: str, author: str):
    _load(html)
    return ib.lookup(title, author)


class InternationalBookerParserTests(unittest.TestCase):
    def setUp(self):
        ib._reset_runtime_state()

    def tearDown(self):
        ib._reset_runtime_state()

    def test_supported_year_boundary_is_2016_through_2026(self):
        self.assertEqual(ib.ARCHIVE_MIN_YEAR, 2016)
        self.assertEqual(ib.ARCHIVE_MAX_YEAR, 2026)
        self.assertEqual(ib.SUPPORTED_YEARS, frozenset(range(2016, 2027)))
        self.assertTrue(ib._year_is_supported(2016))
        self.assertTrue(ib._year_is_supported(2026))
        self.assertFalse(ib._year_is_supported(2015))
        self.assertFalse(ib._year_is_supported(2027))

    def test_2026_qualifying_results_after_winner_precedence(self):
        records, _years = _load(archive_html())
        year_2026 = [record for record in records if record.award_year == 2026]
        self.assertEqual(len(year_2026), 6)
        winners = [record for record in year_2026 if record.status == 'Winner']
        shortlisted = [
            record for record in year_2026 if record.status == 'Shortlisted'
        ]
        self.assertEqual(len(winners), 1)
        self.assertEqual(len(shortlisted), 5)
        winner = winners[0]
        self.assertEqual(winner.work_title, TAIWAN)
        self.assertEqual(winner.work_author, YANG)
        self.assertEqual(winner.notes, 'Translated by Lin King')
        self.assertEqual(winner.source_url, TAIWAN_URL)
        expected_short = [
            (
                'The Nights Are Quiet in Tehran',
                'Shida Bazyar',
                'Translated by Ruth Martin',
            ),
            (
                'She Who Remains',
                'Rene Karabash',
                'Translated by Izidora Angel',
            ),
            (
                'The Director',
                'Daniel Kehlmann',
                'Translated by Ross Benjamin',
            ),
            (
                'On Earth As It Is Beneath',
                'Ana Paula Maia',
                'Translated by Padma Viswanathan',
            ),
            (
                'The Witch',
                NDIAYE,
                'Translated by Jordan Stump',
            ),
        ]
        actual_short = [
            (record.work_title, record.work_author, record.notes)
            for record in shortlisted
        ]
        self.assertEqual(actual_short, expected_short)
        self.assertNotIn(
            (TAIWAN, YANG, 'Translated by Lin King'),
            actual_short,
        )

    def test_2026_lookup_returns_canonical_book_url_from_same_document(self):
        result = _lookup_from_html(archive_html(), TAIWAN, YANG)[0]
        self.assertEqual(result.status, 'Winner')
        self.assertEqual(result.source_url, TAIWAN_URL)
        self.assertNotIn('/node/', result.source_url)

    def test_2026_node_url_without_canonical_same_document_uses_year_url(self):
        html = archive_html(node_2026=True)
        html = html.replace('/the-booker-library/books/taiwan-travelogue', '/node/5863')
        records, years = _parse(html)
        ib._validate_archive(records, years)
        taiwan = [
            record
            for record in records
            if record.work_title == TAIWAN and record.award_year == 2026
        ]
        self.assertEqual(len(taiwan), 1)
        self.assertEqual(taiwan[0].source_url, YEAR_2026_URL)
        self.assertNotIn('taiwan-travelogue', taiwan[0].source_url)

    def test_never_uses_ordinary_booker_year_url(self):
        self.assertIsNone(
            ib._official_book_url(
                'https://thebookerprizes.com/the-booker-library/prize-years/2026'
            )
        )
        ordinary = (
            'https://thebookerprizes.com/the-booker-library/prize-years/2026'
        )
        self.assertFalse(ib._source_url_is_usable(ordinary, 2026))
        self.assertTrue(ib._source_url_is_usable(YEAR_2026_URL, 2026))
        self.assertFalse(ib._source_url_is_usable(YEAR_2026_URL, 2025))

    def test_award_result_schema(self):
        result = _lookup_from_html(archive_html(), TAIWAN, YANG)[0]
        self.assertEqual(result.work_title, TAIWAN)
        self.assertEqual(result.work_author, YANG)
        self.assertEqual(result.award_name, 'International Booker Prize')
        self.assertEqual(result.award_year, 2026)
        self.assertIsNone(result.category)
        self.assertEqual(result.status, 'Winner')
        self.assertIsNone(result.rank)
        self.assertEqual(result.source_name, 'The Booker Prizes')
        self.assertEqual(result.source_url, TAIWAN_URL)
        self.assertEqual(result.notes, 'Translated by Lin King')
        self.assertEqual(result.identity_kind, 'work')
        self.assertFalse(result.is_specifically_cited_work)

    def test_help_fiction_category_is_not_copied_onto_results(self):
        self.assertEqual(ib.SOURCEINFO_CATEGORIES, ('Fiction',))
        result = _lookup_from_html(archive_html(), TAIWAN, YANG)[0]
        self.assertIsNone(result.category)

    def test_2016_first_work_level_cycle(self):
        result = _lookup_from_html(archive_html(), VEGETARIAN, 'Han Kang')[0]
        self.assertEqual(result.award_year, 2016)
        self.assertEqual(result.status, 'Winner')
        self.assertEqual(result.award_name, 'International Booker Prize')
        self.assertEqual(result.notes, 'Translated by Deborah Smith')
        self.assertEqual(result.source_url, VEGETARIAN_URL)

    def test_2016_through_2019_are_canonicalized_to_international_booker_prize(self):
        html = archive_html()
        vegetarian = _lookup_from_html(html, VEGETARIAN, 'Han Kang')[0]
        flights = ib.lookup('Flights', 'Olga Tokarczuk')[0]
        celestial = ib.lookup(CELESTIAL, 'Jokha Alharthi')[0]
        for result, year in (
            (vegetarian, 2016),
            (flights, 2018),
            (celestial, 2019),
        ):
            with self.subTest(year=year):
                self.assertEqual(result.award_name, 'International Booker Prize')
                self.assertNotIn('Man Booker', result.award_name)
                self.assertEqual(result.award_year, year)

    def test_2019_is_not_treated_as_post_man_booker_rename(self):
        result = _lookup_from_html(archive_html(), CELESTIAL, 'Jokha Alharthi')[0]
        self.assertEqual(result.award_year, 2019)
        self.assertEqual(result.award_name, 'International Booker Prize')

    def test_multiple_translators_are_preserved(self):
        result = _lookup_from_html(
            archive_html(),
            'The World Goes On',
            'L\u00e1szl\u00f3 Krasznahorkai',
        )[0]
        self.assertEqual(result.status, 'Shortlisted')
        self.assertEqual(
            result.notes,
            'Translated by Ottilie Mulzet and John Batki',
        )
        heaven = ib.lookup(HEAVEN, 'Mieko Kawakami')[0]
        self.assertEqual(
            heaven.notes,
            'Translated by Sam Bett and David Boyd',
        )

    def test_anonymous_translator_is_preserved(self):
        result = _lookup_from_html(
            archive_html(),
            GREENGAGE,
            'Shokoofeh Azar',
        )[0]
        self.assertEqual(result.notes, 'Translated by Anonymous')
        self.assertEqual(result.work_author, 'Shokoofeh Azar')

    def test_translated_from_language_by_keeps_translator_only_in_notes(self):
        result = _lookup_from_html(archive_html(), HEART_LAMP, 'Banu Mushtaq')[0]
        self.assertEqual(result.status, 'Winner')
        self.assertEqual(result.notes, 'Translated by Deepa Bhasthi')
        self.assertNotIn('Kannada', result.notes)
        self.assertNotIn('Kannada', result.work_author)

    def test_unusual_author_punctuation_is_preserved(self):
        result = _lookup_from_html(archive_html(), 'Standing Heavy', GAUZ)[0]
        self.assertEqual(result.work_author, GAUZ)
        self.assertEqual(result.notes, 'Translated by Frank Wynne')

    def test_title_with_by_is_not_split_naively(self):
        result = _lookup_from_html(
            archive_html(),
            DEATH_BY_WATER,
            'Kenzaburo Oe',
        )[0]
        self.assertEqual(result.work_title, DEATH_BY_WATER)
        self.assertEqual(result.work_author, 'Kenzaburo Oe')
        self.assertEqual(result.notes, 'Translated by Deborah Boliver Boehm')

    def test_winner_precedes_repeated_shortlist_row(self):
        records, _years = _load(archive_html())
        taiwan = [
            record
            for record in records
            if record.work_title == TAIWAN and record.award_year == 2026
        ]
        self.assertEqual(len(taiwan), 1)
        self.assertEqual(taiwan[0].status, 'Winner')

    def test_every_supported_year_has_six_qualifying_results(self):
        records, years = _load(archive_html())
        self.assertTrue(ib.SUPPORTED_YEARS.issubset(set(years)))
        self.assertEqual(len(records), 11 * 6)
        for year in sorted(ib.SUPPORTED_YEARS):
            year_records = [
                record for record in records if record.award_year == year
            ]
            with self.subTest(year=year):
                self.assertEqual(len(year_records), 6)
                self.assertEqual(
                    sum(1 for record in year_records if record.status == 'Winner'),
                    1,
                )
                self.assertEqual(
                    sum(
                        1
                        for record in year_records
                        if record.status == 'Shortlisted'
                    ),
                    5,
                )

    def test_translator_is_never_work_author_or_second_result(self):
        results = _lookup_from_html(archive_html(), TAIWAN, 'Lin King')
        self.assertEqual(results, [])
        author_results = ib.lookup(TAIWAN, YANG)
        self.assertEqual(len(author_results), 1)
        self.assertEqual(author_results[0].work_author, YANG)

    def test_matching_is_normalized_exact_title_and_author(self):
        html = archive_html()
        self.assertEqual(
            len(_lookup_from_html(html, 'taiwan travelogue', YANG)),
            1,
        )
        self.assertEqual(ib.lookup(TAIWAN, 'Someone Else'), [])
        self.assertEqual(ib.lookup('Other Title', YANG), [])

    def test_shortlisted_qualifies_under_international_booker_policy(self):
        result = _lookup_from_html(
            archive_html(),
            'The Witch',
            NDIAYE,
        )[0]
        assessment = assess_award_result(result)
        self.assertIs(
            assessment.qualification.decision,
            QualificationDecision.QUALIFIES,
        )
        self.assertIsNone(result.rank)
        self.assertIs(
            find_award_policy(result),
            INTERNATIONAL_BOOKER_SHORTLIST_POLICY,
        )

    def test_winner_qualifies_without_inventing_rank(self):
        result = _lookup_from_html(archive_html(), TAIWAN, YANG)[0]
        assessment = assess_award_result(result)
        self.assertIs(
            assessment.qualification.decision,
            QualificationDecision.QUALIFIES,
        )
        self.assertIsNone(result.rank)

    def test_booker_policy_does_not_apply_to_international_booker_results(self):
        result = _lookup_from_html(archive_html(), TAIWAN, YANG)[0]
        with self.assertRaises(ValueError) as raised:
            from awards.qualifier import qualify_award_result

            qualify_award_result(result, BOOKER_POLICY)
        self.assertIn('does not apply', str(raised.exception))


class InternationalBookerNegativeTests(unittest.TestCase):
    def setUp(self):
        ib._reset_runtime_state()

    def tearDown(self):
        ib._reset_runtime_state()

    def test_legacy_2005_2015_author_rows_are_not_emitted(self):
        records, _years = _load(archive_html())
        self.assertFalse(
            any(record.award_year < 2016 for record in records)
        )
        self.assertEqual(ib.lookup('Legacy Winner 2015', 'Legacy Winner 2015'), [])
        self.assertEqual(ib.lookup('L\u00e1szl\u00f3 Krasznahorkai', 'L\u00e1szl\u00f3 Krasznahorkai'), [])

    def test_2015_translator_prize_is_not_emitted(self):
        records, _years = _load(archive_html())
        self.assertFalse(
            any('Szirtes' in record.notes for record in records)
        )
        self.assertFalse(
            any(record.work_author == 'George Szirtes' for record in records)
        )

    def test_longlisted_only_works_are_not_emitted(self):
        html = archive_html()
        self.assertEqual(
            _lookup_from_html(html, 'Longlist Only 2026', 'Longlist Author 2026'),
            [],
        )
        self.assertEqual(
            ib.lookup('The Perfect Nine', 'Ngugi wa Thiong\'o'),
            [],
        )

    def test_judges_are_not_emitted(self):
        records, _years = _load(archive_html())
        self.assertFalse(
            any('chair' in record.work_title.casefold() for record in records)
        )
        self.assertFalse(
            any('readers' in record.work_author.casefold() for record in records)
        )

    def test_2027_competitive_fixture_does_not_emit_an_award(self):
        records, years = _load(archive_html(include_2027=True))
        self.assertIn(2027, years)
        self.assertFalse(any(record.award_year == 2027 for record in records))
        self.assertEqual(
            ib.lookup('Bukhman Stub Winner', 'Bukhman Winner Author'),
            [],
        )
        self.assertEqual(
            ib.lookup('Bukhman Stub Short 1', 'Bukhman Short Author 1'),
            [],
        )

    def test_ordinary_booker_archive_fails_identity(self):
        html = (
            f'<html><head><title>{_BOOKER_ARCHIVE_TITLE}</title></head>'
            f'<body><h1>{_BOOKER_ARCHIVE_TITLE}</h1>'
            '<h2>2025</h2>'
            '<p><strong>Winner:</strong></p>'
            + _work_paragraph('Flesh', 'David Szalay', 'Nobody', 'flesh')
            + '</body></html>'
        )
        with self.assertRaises(ib.InternationalBookerSourceError):
            ib._require_archive_identity(html)

    def test_ordinary_booker_and_childrens_content_are_not_emitted(self):
        records, _years = _load(archive_html())
        titles = {record.work_title for record in records}
        self.assertNotIn('Flesh', titles)
        self.assertNotIn('Children Stub', titles)

    def test_related_content_is_not_emitted(self):
        records, _years = _load(archive_html())
        self.assertFalse(
            any(record.work_title == 'Flesh' for record in records)
        )

    def test_missing_identity_fails_closed(self):
        with self.assertRaises(ib.InternationalBookerSourceError):
            ib._require_archive_identity('<html><h1>Unrelated page</h1></html>')

    def test_wrong_identity_complete_looking_html_fails_closed(self):
        html = archive_html(skip_identity=True)
        with self.assertRaises(ib.InternationalBookerSourceError):
            ib._require_archive_identity(html)

    def test_missing_supported_year_heading_fails_closed(self):
        html = archive_html(omit_year=2020)
        _records, years = _parse(html)
        with self.assertRaises(ib.InternationalBookerSourceError) as raised:
            ib._validate_archive(_records, years)
        self.assertIn('2020', str(raised.exception))

    def test_truncated_2026_shortlist_fails_closed(self):
        html = archive_html(truncated_2026=True)
        records, years = _parse(html)
        with self.assertRaises(ib.InternationalBookerSourceError) as raised:
            ib._validate_archive(records, years)
        self.assertIn('2026', str(raised.exception))

    def test_malformed_winner_row_without_translator_fails_closed(self):
        html = archive_html().replace(
            'translated by Lin King (Publisher)',
            '(And Other Stories)',
        )
        records, years = _parse(html)
        with self.assertRaises(ib.InternationalBookerSourceError):
            ib._validate_archive(records, years)

    def test_empty_title_and_author_are_rejected_by_lookup(self):
        ib._archive_records_cache = ()
        with self.assertRaises(ValueError):
            ib.lookup('  ', YANG)
        with self.assertRaises(ValueError):
            ib.lookup(TAIWAN, '  ')


class InternationalBookerUrlHelperTests(unittest.TestCase):
    def test_node_paths_are_not_official_book_urls(self):
        self.assertIsNone(ib._official_book_url('/node/5863'))
        self.assertIsNone(
            ib._official_book_url(
                'https://thebookerprizes.com/node/5863'
            )
        )

    def test_slug_is_never_guessed_from_title(self):
        self.assertIsNone(ib._official_book_url('taiwan-travelogue'))
        self.assertIsNone(
            ib._official_book_url('/the-booker-library/books/')
        )

    def test_prize_year_url_rejects_unsupported_years(self):
        self.assertIsNone(ib._official_prize_year_url(2015))
        self.assertIsNone(ib._official_prize_year_url(2027))
        self.assertEqual(
            ib._official_prize_year_url(2016),
            'https://thebookerprizes.com/the-booker-library/prize-years/international/2016',
        )


if __name__ == '__main__':
    unittest.main()
