"""Offline coverage for National Book Critics Circle year-page parsers."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from awards.engine import assess_award_result
from awards.qualifier import QualificationDecision
from awards.sources import national_book_critics_circle as nbcc


def _url(year: int) -> str:
    return nbcc._canonical_year_url(year)


def _page(year: int, inner: str, *, modern: bool = False) -> str:
    if modern:
        facts = (
            '<div class="content-regular"></div>'
            f'<div class="award-year-list-wrapper">{inner}</div>'
        )
    else:
        facts = (
            f'<div class="content-regular">{inner}</div>'
            '<div class="award-year-list-wrapper"></div>'
        )
    return (
        '<html><head>'
        f'<title>{year} - National Book Critics Circle</title>'
        '</head>'
        f'<body class="award-template-default single single-award award-{year}">'
        '<div class="entry-content">'
        '<p>Each year, the National Book Critics Circle presents awards for '
        'the finest books published in English in six categories: '
        '<strong>Fiction</strong>, <strong>Nonfiction</strong>, '
        '<strong>Biography</strong>, <strong>Autobiography</strong>, '
        '<strong>Poetry</strong>, and <strong>Criticism</strong>.</p>'
        '<p>We also award the Ivan Sandrof Lifetime Achievement Award and '
        'the Nona Balakian Citation for Excellence in Reviewing.</p>'
        '</div>'
        '<div id="child-content">'
        '<div class="entry-content award-finalists-inner">'
        f'<h2 class="entry-title">{year} Winners &amp; Finalists</h2>'
        f'{facts}'
        '</div></div></body></html>'
    )


def _li(author: str, title: str, publisher: str | None = 'Knopf', *, em: bool = True) -> str:
    title_html = f'<em>{title}</em>' if em else title
    pub = f' ({publisher})' if publisher else ''
    return f'<li>{author}, {title_html}{pub}</li>'


def _classic_block(heading: str, items: str) -> str:
    return f'<h3>{heading}</h3><ul>{items}</ul>'


def _modern_list(category: str, items: str) -> str:
    return f'<ul class="award-year-list"><h3>{category}</h3>{items}</ul>'


def _modern_li(status: str, author: str, title: str, publisher: str = 'Knopf') -> str:
    return (
        f'<li class="{status}">{author}, <em>{title}</em> ({publisher})</li>'
    )


def _core_1975() -> str:
    return (
        '<h3>Winners</h3><ul>'
        '<li>Fiction: E.L. Doctorow, <em>Ragtime</em></li>'
        '<li>General Nonfiction: R.W.B. Lewis, '
        '<em>Edith Wharton: A Biography</em> (Harper &amp; Row)</li>'
        '<li>Poetry: John Ashbery, '
        '<em>Self-Portrait in a Convex Mirror</em> (Viking)</li>'
        '<li>Criticism: Paul Fussell, '
        '<em>The Great War and Modern Memory</em> (Oxford University Press)</li>'
        '</ul>'
    )


def _classic_core(
    *,
    fiction_winner=('John Gardner', 'October Light'),
    extra='',
    include_bio_auto=False,
    include_biography=False,
    include_autobiography=False,
    autobiography_heading='Autobiography/Memoir Winner',
    general_nonfiction='General Nonfiction',
) -> str:
    parts = [
        _classic_block('Fiction Winner', _li(*fiction_winner)),
        _classic_block(
            'Fiction Finalists',
            _li('Other Author', 'Other Novel', 'Other Press'),
        ),
        _classic_block(
            f'{general_nonfiction} Winner',
            _li('Maxine Hong Kingston', 'The Woman Warrior'),
        ),
        _classic_block('Poetry Winner', _li('Elizabeth Bishop', 'Geography III')),
        _classic_block(
            'Criticism Winner',
            _li('Bruno Bettelheim', 'The Uses of Enchantment'),
        ),
    ]
    if include_bio_auto:
        parts.append(
            _classic_block(
                'Biography/Autobiography Winner',
                _li('Joyce Johnson', 'Minor Characters', 'Houghton Mifflin'),
            )
        )
    if include_biography:
        parts.append(
            _classic_block(
                'Biography Winner',
                _li('Sarah Bakewell', 'How To Live'),
            )
        )
    if include_autobiography:
        parts.append(
            _classic_block(
                autobiography_heading,
                _li('Darin Strauss', 'Half a Life', "McSweeney's"),
            )
        )
    return ''.join(parts) + extra


def _modern_core(
    *,
    fiction_winner=('Joan Silber', 'Improvement', 'Counterpoint'),
    extras='',
    include_leonard=False,
    include_barrios=False,
    winners=True,
) -> str:
    def cat(name, winner_pair, extra_items=''):
        items = ''
        if winners:
            items += _modern_li('Winner', winner_pair[0], winner_pair[1], winner_pair[2])
        return _modern_list(name, items + extra_items)

    parts = [
        cat('Fiction', fiction_winner),
        cat('Nonfiction', ('Karen Hao', 'Empire of AI', 'Penguin Press')),
        cat('Biography', ('Alex Green', 'A Perfect Turmoil', 'Bellevue')),
        cat('Autobiography', ('Arundhati Roy', 'Mother Mary Comes to Me', 'Scribner')),
        cat('Poetry', ('Kevin Young', 'Night Watch', 'Knopf')),
        cat('Criticism', ('Quinn Slobodian', "Hayek's Bastards", 'Zone Books')),
    ]
    if include_leonard:
        parts.append(
            cat(
                'John Leonard Prize',
                ('Nicholas Boggs', 'Baldwin: A Love Story', 'Farrar, Straus and Giroux'),
            )
        )
    if include_barrios:
        parts.append(
            _modern_list(
                'Gregg Barrios Book in Translation',
                _modern_li(
                    'Winner',
                    'Neige Sinno, translated from the French by Natasha Lehrer',
                    'Sad Tiger',
                    'Seven Stories',
                ),
            )
        )
    return ''.join(parts) + extras


def _parse(year: int, html: str):
    nbcc._require_year_page_identity(html, year, _url(year))
    return nbcc._parse_year_html(html, year, _url(year))


def _by_title(records, title: str):
    return [record for record in records if record.work_title == title]


class IdentityTests(unittest.TestCase):
    def test_year_page_requires_nbcc_identity_and_year(self):
        html = _page(1977, _classic_core(fiction_winner=('Toni Morrison', 'Song of Solomon')))
        nbcc._require_year_page_identity(html, 1977, _url(1977))
        with self.assertRaises(nbcc.NationalBookCriticsCircleSourceError):
            nbcc._require_year_page_identity(
                html.replace('National Book Critics Circle', 'Other'),
                1977,
                _url(1977),
            )
        with self.assertRaises(nbcc.NationalBookCriticsCircleSourceError):
            nbcc._require_year_page_identity(html, 1978, _url(1978))


class Parser1975Tests(unittest.TestCase):
    def test_four_winners_and_zero_finalists(self):
        records, saw_longlist = _parse(1975, _page(1975, _core_1975()))
        self.assertFalse(saw_longlist)
        self.assertEqual(len(records), 4)
        self.assertTrue(all(record.status == 'Winner' for record in records))
        self.assertTrue(all(record.award_year == 1975 for record in records))
        ragtime = _by_title(records, 'Ragtime')[0]
        self.assertEqual(ragtime.work_author, 'E.L. Doctorow')
        self.assertEqual(ragtime.category, 'Fiction')
        self.assertEqual(ragtime.status, 'Winner')
        self.assertEqual(
            {record.category for record in records},
            {'Fiction', 'General Nonfiction', 'Poetry', 'Criticism'},
        )
        self.assertEqual(
            nbcc._classify_year_state(1975, records, False, indexed=True),
            'completed',
        )

    def test_category_prefix_is_not_author_text(self):
        records, _saw = _parse(1975, _page(1975, _core_1975()))
        for record in records:
            self.assertFalse(record.work_author.startswith('Fiction'))
            self.assertNotIn(':', record.work_author)


class ClassicParserTests(unittest.TestCase):
    def test_1976_fiction_winner(self):
        records, _saw = _parse(1976, _page(1976, _classic_core()))
        winner = _by_title(records, 'October Light')[0]
        self.assertEqual(winner.work_author, 'John Gardner')
        self.assertEqual(winner.status, 'Winner')
        self.assertEqual(winner.category, 'Fiction')

    def test_1977_song_of_solomon(self):
        html = _page(
            1977,
            _classic_core(fiction_winner=('Toni Morrison', 'Song of Solomon')),
        )
        records, _saw = _parse(1977, html)
        winner = _by_title(records, 'Song of Solomon')[0]
        self.assertEqual(winner.work_author, 'Toni Morrison')
        self.assertEqual(winner.award_year, 1977)

    def test_1978_two_general_nonfiction_winners(self):
        extra = _classic_block(
            'General Nonfiction Winners',
            _li('Maureen Howard', 'Facts of Life', 'Little, Brown')
            + _li(
                'Garry Willis',
                "Inventing America: Jefferson's Declaration of Independence",
                'Doubleday',
            ),
        )
        inner = (
            _classic_block('Fiction Winner', _li('Author', 'Novel'))
            + extra
            + _classic_block('Poetry Winner', _li('Poet', 'Poems'))
            + _classic_block('Criticism Winner', _li('Critic', 'Essays'))
        )
        records, _saw = _parse(1978, _page(1978, inner))
        gnf = [
            record
            for record in records
            if record.category == 'General Nonfiction' and record.status == 'Winner'
        ]
        self.assertEqual(len(gnf), 2)
        titles = {record.work_title for record in gnf}
        self.assertEqual(
            titles,
            {
                'Facts of Life',
                "Inventing America: Jefferson's Declaration of Independence",
            },
        )
        authors = {record.work_author for record in gnf}
        self.assertEqual(authors, {'Maureen Howard', 'Garry Willis'})
        self.assertTrue(all(record.rank is None for record in [
            nbcc._to_award_result(item) for item in gnf
        ]))

    def test_1983_biography_autobiography_category(self):
        html = _page(1983, _classic_core(include_bio_auto=True))
        records, _saw = _parse(1983, html)
        winner = _by_title(records, 'Minor Characters')[0]
        self.assertEqual(winner.category, 'Biography/Autobiography')
        self.assertEqual(winner.work_author, 'Joyce Johnson')
        self.assertTrue(
            nbcc._year_has_required_core_winners(1983, records)
        )

    def test_1990_fiction_winner_and_finalist(self):
        extra = _classic_block(
            'Fiction Finalists',
            _li(
                "Tim O'Brien",
                'The Things They Carried',
                'Seymour Lawrence/Houghton Mifflin',
            ),
        )
        inner = _classic_core(
            fiction_winner=('John Updike', 'Rabbit at Rest'),
            extra=extra,
            include_bio_auto=True,
        )
        records, _saw = _parse(1990, _page(1990, inner))
        winner = _by_title(records, 'Rabbit at Rest')[0]
        finalist = _by_title(records, 'The Things They Carried')[0]
        self.assertEqual(winner.work_author, 'John Updike')
        self.assertEqual(winner.status, 'Winner')
        self.assertEqual(finalist.work_author, "Tim O'Brien")
        self.assertEqual(finalist.status, 'Finalist')
        self.assertIsNone(nbcc._to_award_result(finalist).rank)

    def test_2004_biography_coauthors_ampersand_preserved(self):
        extra = _classic_block(
            'Biography Winner',
            _li(
                'Mark Stevens & Annalyn Swan',
                'De Kooning: An American Master',
            ),
        )
        inner = _classic_core(include_biography=True, extra=extra)
        records, _saw = _parse(2004, _page(2004, inner))
        winner = _by_title(records, 'De Kooning: An American Master')[0]
        self.assertEqual(winner.work_author, 'Mark Stevens & Annalyn Swan')
        self.assertEqual(winner.category, 'Biography')

    def test_2008_two_poetry_winners(self):
        extra = _classic_block(
            'Poetry Winners',
            _li('Juan Felipe Herrera', 'Half the World in Light', 'University of Arizona Press')
            + _li(
                'August Kleinzahler',
                'Sleeping It Off in Rapid City',
                'Farrar, Straus & Giroux',
            ),
        )
        inner = (
            _classic_block('Fiction Winner', _li('Author', 'Novel'))
            + _classic_block(
                'General Nonfiction Winner',
                _li('NF Author', 'NF Book'),
            )
            + extra
            + _classic_block('Criticism Winner', _li('Critic', 'Essays'))
            + _classic_block('Biography Winner', _li('Bio', 'Life'))
            + _classic_block('Autobiography', _li('Memoist', 'Memoir'))
        )
        records, _saw = _parse(2008, _page(2008, inner))
        poetry = [
            record
            for record in records
            if record.category == 'Poetry' and record.status == 'Winner'
        ]
        self.assertEqual(len(poetry), 2)
        self.assertEqual(
            {record.work_title for record in poetry},
            {'Half the World in Light', 'Sleeping It Off in Rapid City'},
        )

    def test_2010_classic_traps(self):
        extra = (
            _classic_block(
                'Fiction Finalists',
                _li('Jonathan Franzen', 'Freedom', 'Farrar, Straus & Giroux')
                + '<li>David Grossman, To the End of the Land (Knopf)</li>',
            )
            + _classic_block(
                'General Nonfiction Winner',
                _li(
                    'Isabel Wilkerson',
                    "The Warmth of Other Suns: The Epic Story of America's Great Migration",
                    'Random House',
                ),
            )
            + _classic_block(
                'Autobiography',
                _li('Darin Strauss', 'Half a Life', "McSweeney's"),
            )
            + _classic_block(
                'Poetry Winner',
                "<li>C. D. Wright's <em>One with Others: [a little book of her days]</em> (Copper Canyon)</li>",
            )
        )
        inner = (
            _classic_block(
                'Fiction Winner',
                _li('Jennifer Egan', 'A Visit from the Goon Squad'),
            )
            + _classic_block(
                'Criticism Winner',
                _li('Clare Cavanagh', 'Lyric Poetry and Modern Politics'),
            )
            + _classic_block(
                'Biography Winner',
                _li('Sarah Bakewell', 'How To Live'),
            )
            + extra
        )
        records, _saw = _parse(2010, _page(2010, inner))
        self.assertEqual(
            _by_title(records, 'A Visit from the Goon Squad')[0].work_author,
            'Jennifer Egan',
        )
        freedom = _by_title(records, 'Freedom')[0]
        self.assertEqual(freedom.work_author, 'Jonathan Franzen')
        self.assertEqual(freedom.status, 'Finalist')
        land = _by_title(records, 'To the End of the Land')[0]
        self.assertEqual(land.work_author, 'David Grossman')
        warmth = _by_title(
            records,
            "The Warmth of Other Suns: The Epic Story of America's Great Migration",
        )[0]
        self.assertEqual(warmth.category, 'General Nonfiction')
        self.assertEqual(warmth.work_author, 'Isabel Wilkerson')
        auto = _by_title(records, 'Half a Life')[0]
        self.assertEqual(auto.category, 'Autobiography')
        self.assertEqual(auto.status, 'Winner')
        self.assertEqual(auto.work_author, 'Darin Strauss')
        wright = [
            record for record in records if record.work_title.startswith('One with Others')
        ][0]
        self.assertEqual(wright.work_author, 'C. D. Wright')
        self.assertEqual(
            wright.work_title,
            'One with Others: [a little book of her days]',
        )

    def test_2013_john_leonard_without_em(self):
        extra = _classic_block(
            'John Leonard Prize',
            '<li>Anthony Marra, A Constellation Of Vital Phenomena (Hogarth)</li>',
        )
        inner = _classic_core(
            fiction_winner=('Chimamanda Ngozi Adichie', 'Americanah'),
            include_biography=True,
            include_autobiography=True,
            autobiography_heading='Autobiography',
            extra=extra,
        )
        records, _saw = _parse(2013, _page(2013, inner))
        leonard = _by_title(records, 'A Constellation Of Vital Phenomena')[0]
        self.assertEqual(leonard.work_author, 'Anthony Marra')
        self.assertEqual(leonard.category, 'John Leonard Prize')
        self.assertEqual(leonard.status, 'Winner')


class ModernParserTests(unittest.TestCase):
    def test_2017_fiction_nonfiction_and_leonard(self):
        extras = _modern_list(
            'John Leonard Prize',
            _modern_li(
                'Winner',
                'Carmen Maria Machado',
                'Her Body and Other Parties',
                'Graywolf',
            ),
        )
        inner = _modern_core(
            fiction_winner=('Joan Silber', 'Improvement', 'Counterpoint'),
            extras=extras,
        )
        # replace default Nonfiction winner for this year
        inner = inner.replace(
            'Karen Hao',
            'Frances FitzGerald',
        ).replace(
            'Empire of AI',
            'The Evangelicals: The Struggle to Shape America',
        )
        records, _saw = _parse(2017, _page(2017, inner, modern=True))
        self.assertEqual(
            _by_title(records, 'Improvement')[0].work_author,
            'Joan Silber',
        )
        self.assertEqual(
            _by_title(records, 'The Evangelicals: The Struggle to Shape America')[0].category,
            'Nonfiction',
        )
        leonard = _by_title(records, 'Her Body and Other Parties')[0]
        self.assertEqual(leonard.work_author, 'Carmen Maria Machado')
        self.assertEqual(leonard.category, 'John Leonard Prize')

    def test_2020_hamnet_apostrophe(self):
        inner = _modern_core(
            fiction_winner=('Maggie O’Farrell', 'Hamnet', 'Knopf'),
        )
        records, _saw = _parse(2020, _page(2020, inner, modern=True))
        winner = _by_title(records, 'Hamnet')[0]
        self.assertEqual(winner.work_author, 'Maggie O’Farrell')

    def test_2021_diacritic_author(self):
        inner = _modern_core(
            fiction_winner=(
                'Honorée Fanonne Jeffers',
                'The Love Songs of W.E.B DuBois',
                'Harper',
            ),
        )
        records, _saw = _parse(2021, _page(2021, inner, modern=True))
        winner = _by_title(records, 'The Love Songs of W.E.B DuBois')[0]
        self.assertEqual(winner.work_author, 'Honorée Fanonne Jeffers')

    def test_2022_story_collection_and_barrios(self):
        extras = _modern_list(
            'Gregg Barrios Book in Translation',
            _modern_li(
                'Winner',
                'Andrey Kurkov trans. by Boris Dralyuk',
                'Grey Bees',
                'Deep Vellum',
            ),
        )
        inner = _modern_core(
            fiction_winner=('Ling Ma', 'Bliss Montage: Stories', 'Farrar, Straus and Giroux'),
            extras=extras,
            include_barrios=False,
        )
        records, _saw = _parse(2022, _page(2022, inner, modern=True))
        self.assertEqual(
            _by_title(records, 'Bliss Montage: Stories')[0].work_author,
            'Ling Ma',
        )
        bees = _by_title(records, 'Grey Bees')[0]
        self.assertEqual(bees.work_author, 'Andrey Kurkov')
        self.assertEqual(bees.category, 'Gregg Barrios Book in Translation')

    def test_wrapped_barrios_heading_collapses_whitespace(self):
        extras = (
            '<ul class="award-year-list">'
            '<h3>Gregg Barrios Book in Translation\n</h3>'
            + _modern_li(
                'Winner',
                'Neige Sinno, translated from the French by Natasha Lehrer',
                'Sad Tiger',
                'Seven Stories',
            )
            + '</ul>'
        )
        inner = _modern_core(extras=extras)
        records, _saw = _parse(2025, _page(2025, inner, modern=True))
        tiger = _by_title(records, 'Sad Tiger')[0]
        self.assertEqual(tiger.category, 'Gregg Barrios Book in Translation')
        self.assertEqual(tiger.work_author, 'Neige Sinno')


class Fixtures2025Tests(unittest.TestCase):
    def _2025_html(self) -> str:
        inner = (
            _modern_list(
                'Fiction',
                _modern_li('Finalist', 'Karen Russell', 'The Antidote')
                + _modern_li('Finalist', 'Katie Kitamura', 'Audition', 'Riverhead')
                + _modern_li('Longlist', 'Lily King', 'Heart the Lover', 'Grove')
                + _modern_li(
                    'Longlist',
                    'Ayşegül Savaş',
                    'Long Distance',
                    'Bloomsbury',
                )
                + _modern_li(
                    'Finalist',
                    'Solvej Balle, translated from the Danish by Sophia Hersi Smith and Jennifer Russell',
                    'On the Calculation of Volume (Book III)',
                    'New Directions',
                )
                + _modern_li(
                    'Winner',
                    'Han Kang, translated from the Korean by e. yaewon and Paige Aniyah Morris',
                    'We Do Not Part',
                    'Hogarth',
                ),
            )
            + _modern_list(
                'Nonfiction',
                _modern_li(
                    'Winner',
                    'Karen Hao',
                    "Empire of AI: Dreams and Nightmares in Sam Altman's OpenAI",
                    'Penguin Press',
                ),
            )
            + _modern_list(
                'Biography',
                _modern_li(
                    'Winner',
                    'Alex Green',
                    "A Perfect Turmoil: Walter E. Fernald and the Struggle to Care for America's Disabled",
                    'Bellevue Literary Press',
                ),
            )
            + _modern_list(
                'Autobiography',
                _modern_li(
                    'Winner',
                    'Arundhati Roy',
                    'Mother Mary Comes to Me',
                    'Scribner',
                ),
            )
            + _modern_list(
                'Poetry',
                _modern_li('Winner', 'Kevin Young', 'Night Watch'),
            )
            + _modern_list(
                'Criticism',
                _modern_li(
                    'Winner',
                    'Quinn Slobodian',
                    "Hayek's Bastards: Race, Gold, IQ, and the Capitalism of the Far Right",
                    'Zone Books',
                ),
            )
            + _modern_list(
                'John Leonard Prize',
                _modern_li(
                    'Winner',
                    'Nicholas Boggs',
                    'Baldwin: A Love Story',
                    'Farrar, Straus and Giroux',
                ),
            )
            + _modern_list(
                'Gregg Barrios Book in Translation',
                _modern_li(
                    'Winner',
                    'Neige Sinno, translated from the French by Natasha Lehrer',
                    'Sad Tiger',
                    'Seven Stories',
                ),
            )
            + _modern_list(
                'Nona Balakian Citation for Excellence in Reviewing',
                '<li class="Finalist">Edna Bonhomme</li>'
                '<li class="Winner">James Marcus</li>',
            )
            + _modern_list(
                'Ivan Sandrof Lifetime Achievement Award',
                '<li class="Winner">Frances FitzGerald</li>',
            )
            + _modern_list(
                'Toni Morrison Achievement Award',
                '<li class="Winner">NPR and PBS</li>',
            )
            + _modern_list(
                'NBCC Service Award',
                '<li class="Winner">Elizabeth Taylor</li>',
            )
        )
        return _page(2025, inner, modern=True)

    def test_2025_core_winners(self):
        records, saw_longlist = _parse(2025, self._2025_html())
        self.assertTrue(saw_longlist)
        by_cat = {
            record.category: record
            for record in records
            if record.status == 'Winner'
        }
        self.assertEqual(by_cat['Fiction'].work_title, 'We Do Not Part')
        self.assertEqual(by_cat['Fiction'].work_author, 'Han Kang')
        self.assertEqual(
            by_cat['Nonfiction'].work_title,
            "Empire of AI: Dreams and Nightmares in Sam Altman's OpenAI",
        )
        self.assertEqual(by_cat['Biography'].work_author, 'Alex Green')
        self.assertEqual(
            by_cat['Biography'].work_title,
            "A Perfect Turmoil: Walter E. Fernald and the Struggle to Care for America's Disabled",
        )
        self.assertEqual(by_cat['Autobiography'].work_title, 'Mother Mary Comes to Me')
        self.assertEqual(by_cat['Poetry'].work_title, 'Night Watch')
        self.assertEqual(
            by_cat['Criticism'].work_title,
            "Hayek's Bastards: Race, Gold, IQ, and the Capitalism of the Far Right",
        )
        self.assertEqual(by_cat['John Leonard Prize'].work_title, 'Baldwin: A Love Story')
        self.assertEqual(by_cat['Gregg Barrios Book in Translation'].work_title, 'Sad Tiger')

    def test_2025_finalist_and_longlist_and_honors(self):
        records, _saw = _parse(2025, self._2025_html())
        antidote = _by_title(records, 'The Antidote')[0]
        self.assertEqual(antidote.status, 'Finalist')
        self.assertEqual(antidote.work_author, 'Karen Russell')
        self.assertEqual(_by_title(records, 'Heart the Lover'), [])
        self.assertEqual(_by_title(records, 'Long Distance'), [])
        authors = {record.work_author for record in records}
        self.assertNotIn('Frances FitzGerald', authors)
        self.assertNotIn('NPR and PBS', authors)
        self.assertNotIn('Elizabeth Taylor', authors)
        self.assertNotIn('Edna Bonhomme', authors)
        self.assertNotIn('James Marcus', authors)
        self.assertNotIn('Lily King', authors)

    def test_translator_patterns(self):
        records, _saw = _parse(2025, self._2025_html())
        self.assertEqual(_by_title(records, 'We Do Not Part')[0].work_author, 'Han Kang')
        volume = _by_title(records, 'On the Calculation of Volume (Book III)')[0]
        self.assertEqual(volume.work_author, 'Solvej Balle')
        self.assertEqual(
            volume.work_title,
            'On the Calculation of Volume (Book III)',
        )
        martory_html = _page(
            2008,
            _classic_block(
                'Poetry Finalists',
                '<li>Pierre Martory (trans. John Ashbery), '
                '<em>The Landscapist</em> (Sheep Meadow Press)</li>',
            )
            + _classic_core(),
        )
        classic, _saw = _parse(2008, martory_html)
        land = _by_title(classic, 'The Landscapist')[0]
        self.assertEqual(land.work_author, 'Pierre Martory')
        navalny_html = _page(
            2024,
            _modern_core(
                extras=_modern_list(
                    'Autobiography',
                    _modern_li(
                        'Winner',
                        'Alexei Navalny, translation by Arch Tait with Stephen Dalziel',
                        'Patriot: A Memoir',
                    ),
                )
            ),
            modern=True,
        )
        modern, _saw = _parse(2024, navalny_html)
        patriot = _by_title(modern, 'Patriot: A Memoir')[0]
        self.assertEqual(patriot.work_author, 'Alexei Navalny')


class CompletionStateTests(unittest.TestCase):
    def test_1975_winners_only_completed(self):
        records, _saw = _parse(1975, _page(1975, _core_1975()))
        self.assertEqual(
            nbcc._classify_year_state(1975, records, False, indexed=True),
            'completed',
        )

    def test_1982_requires_four_core_categories(self):
        records, _saw = _parse(1982, _page(1982, _classic_core()))
        self.assertTrue(nbcc._year_has_required_core_winners(1982, records))
        incomplete = tuple(
            record for record in records if record.category != 'Criticism'
        )
        self.assertFalse(nbcc._year_has_required_core_winners(1982, incomplete))

    def test_1983_requires_biography_autobiography(self):
        without = _parse(1983, _page(1983, _classic_core()))[0]
        self.assertFalse(nbcc._year_has_required_core_winners(1983, without))
        with_bio = _parse(1983, _page(1983, _classic_core(include_bio_auto=True)))[0]
        self.assertTrue(nbcc._year_has_required_core_winners(1983, with_bio))

    def test_2003_requires_biography_not_autobiography(self):
        records, _saw = _parse(
            2003,
            _page(2003, _classic_core(include_biography=True)),
        )
        self.assertTrue(nbcc._year_has_required_core_winners(2003, records))
        self.assertFalse(
            any(record.category.startswith('Autobiography') for record in records)
        )

    def test_2005_requires_autobiography_family(self):
        without = _parse(2005, _page(2005, _classic_core(include_biography=True)))[0]
        self.assertFalse(nbcc._year_has_required_core_winners(2005, without))
        with_auto = _parse(
            2005,
            _page(
                2005,
                _classic_core(
                    include_biography=True,
                    include_autobiography=True,
                ),
            ),
        )[0]
        self.assertTrue(nbcc._year_has_required_core_winners(2005, with_auto))

    def test_2017_requires_modern_six(self):
        records, _saw = _parse(2017, _page(2017, _modern_core(), modern=True))
        self.assertTrue(nbcc._year_has_required_core_winners(2017, records))

    def test_modern_finalists_only_in_progress(self):
        inner = _modern_list(
            'Fiction',
            _modern_li('Finalist', 'Karen Russell', 'The Antidote'),
        )
        records, saw = _parse(2026, _page(2026, inner, modern=True))
        self.assertEqual(
            nbcc._classify_year_state(2026, records, saw, indexed=False),
            'in_progress',
        )

    def test_modern_longlist_and_finalists_without_winners_in_progress(self):
        inner = _modern_list(
            'Fiction',
            _modern_li('Longlist', 'Lily King', 'Heart the Lover', 'Grove')
            + _modern_li('Finalist', 'Karen Russell', 'The Antidote'),
        )
        records, saw = _parse(2026, _page(2026, inner, modern=True))
        self.assertTrue(saw)
        self.assertEqual(
            nbcc._classify_year_state(2026, records, saw, indexed=False),
            'in_progress',
        )

    def test_modern_core_winners_completed(self):
        records, saw = _parse(2025, _page(2025, _modern_core(), modern=True))
        self.assertEqual(
            nbcc._classify_year_state(2025, records, saw, indexed=True),
            'completed',
        )

    def test_missing_leonard_or_barrios_does_not_block_completion(self):
        records, saw = _parse(2025, _page(2025, _modern_core(), modern=True))
        self.assertTrue(nbcc._year_has_required_core_winners(2025, records))
        self.assertFalse(
            any(record.category == 'John Leonard Prize' for record in records)
        )
        self.assertFalse(
            any(
                record.category == 'Gregg Barrios Book in Translation'
                for record in records
            )
        )

    def test_person_honors_do_not_affect_completion(self):
        extras = _modern_list(
            'Ivan Sandrof Lifetime Achievement Award',
            '<li class="Winner">Frances FitzGerald</li>',
        )
        inner = _modern_core(winners=False, extras=extras)
        records, saw = _parse(2025, _page(2025, inner, modern=True))
        self.assertFalse(nbcc._year_has_required_core_winners(2025, records))
        self.assertEqual(records, ())


class LookupAndPolicyTests(unittest.TestCase):
    def setUp(self):
        nbcc._reset_runtime_state()

    def tearDown(self):
        nbcc._reset_runtime_state()

    def _index_and_year(self, year, html):
        years = [1975] if year == 1975 else [1975, year]
        index_body = '[' + ','.join(
            f'{{"slug":"{item}","link":"{_url(item)}"}}' for item in years
        ) + ']'
        pages = {
            nbcc.YEAR_INDEX_URL: (200, index_body),
            _url(year): (200, html),
        }
        if year != 1975:
            pages[_url(1975)] = (200, _page(1975, _core_1975()))

        def fake_fetch(url):
            if url not in pages:
                return 404, ''
            return pages[url]

        return fake_fetch

    def test_lookup_1975_winner(self):
        fetch = self._index_and_year(1975, _page(1975, _core_1975()))
        with patch.object(nbcc, '_current_calendar_year', return_value=1975):
            with patch.object(nbcc, '_fetch_response', side_effect=fetch):
                results = nbcc.lookup('Ragtime', 'E.L. Doctorow')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, 'Winner')
        self.assertEqual(results[0].award_year, 1975)
        self.assertEqual(results[0].award_name, nbcc.AWARD_NAME)
        self.assertIsNone(results[0].rank)
        self.assertEqual(
            assess_award_result(results[0]).qualification.decision,
            QualificationDecision.QUALIFIES,
        )

    def test_lookup_finalist_qualifies_and_longlist_is_absent(self):
        extras = _modern_list(
            'Fiction',
            _modern_li('Finalist', 'Karen Russell', 'The Antidote')
            + _modern_li('Longlist', 'Lily King', 'Heart the Lover', 'Grove')
            + _modern_li(
                'Winner',
                'Han Kang, translated from the Korean by e. yaewon and Paige Aniyah Morris',
                'We Do Not Part',
                'Hogarth',
            ),
        )
        html = _page(2025, _modern_core(extras=extras), modern=True)
        fetch = self._index_and_year(2025, html)
        with patch.object(nbcc, '_current_calendar_year', return_value=2025):
            with patch.object(nbcc, '_fetch_response', side_effect=fetch):
                finalist = nbcc.lookup('The Antidote', 'Karen Russell')
                longlist = nbcc.lookup('Heart the Lover', 'Lily King')
                winner = nbcc.lookup('We Do Not Part', 'Han Kang')
                translator = nbcc.lookup('We Do Not Part', 'e. yaewon')
        self.assertEqual(finalist[0].status, 'Finalist')
        self.assertEqual(
            assess_award_result(finalist[0]).qualification.decision,
            QualificationDecision.QUALIFIES,
        )
        self.assertIsNone(finalist[0].rank)
        self.assertEqual(longlist, [])
        self.assertEqual(winner[0].status, 'Winner')
        self.assertEqual(winner[0].work_author, 'Han Kang')
        self.assertEqual(translator, [])

    def test_winner_outranks_same_work_finalist(self):
        extras = _modern_list(
            'Fiction',
            _modern_li('Finalist', 'Joan Silber', 'Improvement', 'Counterpoint')
            + _modern_li('Winner', 'Joan Silber', 'Improvement', 'Counterpoint'),
        )
        html = _page(2017, _modern_core(extras=extras), modern=True)
        records, _saw = _parse(2017, html)
        improvement = _by_title(records, 'Improvement')
        self.assertEqual(len(improvement), 1)
        self.assertEqual(improvement[0].status, 'Winner')


if __name__ == '__main__':
    unittest.main()
