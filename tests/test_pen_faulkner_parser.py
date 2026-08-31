"""Offline coverage for PEN/Faulkner Award for Fiction parsers."""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from awards.engine import assess_award_result
from awards.qualifier import QualificationDecision
from awards.sources import pen_faulkner as pf


def _landing_url() -> str:
    return pf.SOURCE_HOME_URL


def _winner_url(year: int) -> str:
    return pf.VERIFIED_YEAR_URLS[year]['winner']


def _finalists_url(year: int) -> str:
    return pf.VERIFIED_YEAR_URLS[year]['finalists']


def _article(title: str, body: str) -> str:
    return (
        '<html><head>'
        f'<title>{title} | The PEN/Faulkner Foundation</title>'
        '</head><body>'
        f'<div class="entry-content">{body}</div>'
        '</body></html>'
    )


def _year_block(year: int, winner: tuple[str, str], finalists: list[tuple[str, str]], *, em: bool = True) -> str:
    def _work(author: str, title: str) -> str:
        if em:
            return f'{author}, <em>{title}</em>'
        return f'{author}, {title}'

    winner_html = _work(winner[1], winner[0])
    finalist_html = '<br />'.join(_work(author, title) for title, author in finalists)
    return (
        f'<h2>{year}</h2>'
        f'<p><strong>WINNER:</strong><br />{winner_html}</p>'
        f'<p><strong>FINALISTS:</strong><br />{finalist_html}</p>'
    )


_SPECIAL_YEARS = {
    1981: (
        ('How German Is It?', 'Walter Abish'),
        [
            ('The Transit of Venus', 'Shirley Hazzard'),
            ('The Second Coming', 'Walker Percy'),
            ('Aberration of Starlight', 'Gilbert Sorrentino'),
            ('A Confederacy of Dunces', 'John Kennedy Toole'),
        ],
    ),
    1982: (
        ('The Chaneysville Incident', 'David Bradley'),
        [
            ('Sixty Stories', 'Donald Barthelme'),
            ('Take Me Back', 'Richard Bausch'),
            ('Ellis Island and Other Stories', 'Mark Helprin'),
            ('Housekeeping', 'Marilynne Robinson'),
            ('A Flag for Sunrise', 'Robert Stone'),
        ],
    ),
    1984: (
        ('Sent for You Yesterday', 'John Edgar Wideman'),
        [
            (
                'The Assasination of Jesse James by the Coward Robert Ford',
                'Ron Hansen',
            ),
            ('Ironweed', 'William Kennedy'),
            ('At the Bottom of the River', 'Jamaica Kincaid'),
            ('The Stories', 'Bernard Malamud'),
            ('The Cannibal Galaxy', 'Cynthia Ozick'),
        ],
    ),
    1986: (
        ('The Old Forest and Other Stories', 'Peter Taylor'),
        [
            ('Carpenter’s Gothic', 'William Gaddis'),
            ('Lonesome Dove', 'Larry McMurtry'),
            ('The Tree of Life', 'Hugh Nissenson'),
            ('The Christmas Wife', 'Helen Norris'),
            ('Later the Same Day', 'Grace Paley'),
        ],
    ),
    1989: (
        ('Dusk', 'James Salter'),
        [
            ('Vanished', 'Mary McGarry Morris'),
            ('The Corner of Rife and Pacific', 'Thomas Savage'),
            ('The Death of Methuselah', 'Isaac Bashevis Singer'),
        ],
    ),
    1990: (
        ('Billy Bathgate', 'E.L. Doctorow'),
        [
            ('Affliction', 'Russell Banks'),
            ('The Jump-Off Creek', 'Molly Gloss'),
            ('On the Island', 'Josephine Jacobsen'),
            ('Leaving Brooklyn', 'Lynne Sharon Schwartz'),
        ],
    ),
    2000: (
        ('Waiting', 'Ha Jin'),
        [
            ('The Night Inspector', 'Frederick Busch'),
            ('Pu-239 And Other Russian Fantasies', 'Ken Kalfus'),
            ('Amy and Isabelle', 'Elizabeth Strout'),
            ('Siam, or the Woman Who Shot a Man', 'Lily Tuck'),
        ],
    ),
    2004: (
        ('The Early Stories 1953–1975', 'John Updike'),
        [
            ('Elroy Nights', 'Frederick Barthelme'),
            ('Drinking Coffee Elsewhere', 'ZZ Packer'),
            ('A Distant Shore', 'Caryl Phillips'),
            ('Old School', 'Tobias Wolff'),
        ],
    ),
    2011: (
        ('The Collected Stories of Deborah Eisenberg', 'Deborah Eisenberg'),
        [
            ('A Visit From the Goon Squad', 'Jennifer Egan'),
            ('Lord of Misrule', 'Jaimy Gordon'),
            ('Model Home', 'Eric Puchner'),
            ('Aliens in the Prime of Their Lives', 'Brad Watson'),
        ],
    ),
    2013: (
        ('Everything Begins & Ends at the Kentucky Club', 'Benjamin Alire Sáenz'),
        [
            ('Threats', 'Amelia Gray'),
            ('Kind One', 'Laird Hunt'),
            ('Hold It ‘Til It Hurts', 'T. Geronimo Johnson'),
            ('Watergate', 'Thomas Mallon'),
        ],
    ),
    2016: (
        ('Delicious Foods', 'James Hannaham'),
        [
            ('Mr. and Mrs. Doctor', 'Julie Iromuanya'),
            ('The Sympathizer', 'Viet Thanh Nguyen'),
            ('Mendocino Fire', 'Elizabeth Tallent'),
            ('The Water Museum', 'Luis Alberto Urrea'),
        ],
    ),
    2017: (
        ('Behold the Dreamers', 'Imbolo Mbue'),
        [
            ('After Disasters', 'Viet Dinh'),
            ('LaRose', 'Louise Erdrich'),
            ('What Belongs to You', 'Garth Greenwell'),
            ('Your Heart Is a Muscle the Size of a Fist', 'Sunil Yapa'),
        ],
    ),
    2018: (
        ('Improvement', 'Joan Silber'),
        [
            ('In The Distance', 'Hernán Diaz'),
            ('The Dark Dark', 'Samantha Hunt'),
            ('The Tower of the Antilles', 'Achy Obejas'),
            ('Sing, Unburied, Sing', 'Jesmyn Ward'),
        ],
    ),
}


def _default_year(year: int) -> tuple[tuple[str, str], list[tuple[str, str]]]:
    winner = (f'Winner Title {year}', f'Winner Author {year}')
    finalists = [
        (f'Finalist Title {year}-{index}', f'Finalist Author {year}-{index}')
        for index in range(1, 5)
    ]
    return winner, finalists


def _historical_landing(*, skip_year: int | None = None, extra: str = '') -> str:
    blocks = [extra]
    for year in range(pf.ARCHIVE_MIN_YEAR, pf.HISTORICAL_ARCHIVE_MAX_YEAR + 1):
        if year == skip_year:
            continue
        if year in _SPECIAL_YEARS:
            winner, finalists = _SPECIAL_YEARS[year]
        else:
            winner, finalists = _default_year(year)
        em = year != 2016
        blocks.append(_year_block(year, winner, finalists, em=em))
    return (
        '<html><head><title>PEN/Faulkner Award for Fiction | '
        'The PEN/Faulkner Foundation</title></head>'
        f'<body><div class="entry-content">{"".join(blocks)}</div></body></html>'
    )


def _finalists_article(year: int, pairs: list[tuple[str, str, str]], *, style: str) -> str:
    if style == 'colon_lines':
        items = ''.join(
            f'<p>{title} by {author} ({publisher})</p>'
            for title, author, publisher in pairs
        )
        body = (
            f'<p>Judges have selected the five finalists for the {year} '
            f'PEN/Faulkner Award for Fiction:</p>{items}'
        )
    elif style == 'author_for':
        joined = ', '.join(
            f'{author} for {title} ({publisher})'
            for title, author, publisher in pairs
        )
        body = (
            f'<p>Judges have selected the five finalists for the {year} '
            f'PEN/Faulkner Award for Fiction, America’s largest peer-juried '
            f'prize for fiction. The finalists are: {joined}.</p>'
            '<h3>About the Finalists</h3>'
            '<p>She has published fiction in All about Skin: Short Fiction '
            'by Women of Color, as well as Obsidian (ix).</p>'
        )
    else:
        joined = ', '.join(
            f'{title} by {author} ({publisher})'
            for title, author, publisher in pairs
        )
        body = (
            f'<p>Judges have selected the five finalists for the {year} '
            f'PEN/Faulkner Award for Fiction, America’s most prestigious '
            f'peer-juried literary prize. The finalists are {joined}.</p>'
            '<p>About the Authors</p>'
        )
    return _article(
        f'Announcing the Finalists for the {year} PEN/Faulkner Award for Fiction',
        body,
    )


def _winner_article(
    year: int,
    title: str,
    author: str,
    others: list[tuple[str, str]] | None = None,
) -> str:
    others = others or []
    other_clause = ''
    if others:
        named = '; '.join(f'{name}, for {book}' for book, name in others)
        other_clause = (
            f'<p>The authors of each of the other finalists—'
            f'{named}—will receive $5,000.</p>'
        )
    body = (
        f'<p>{author}’s {title} (Test Press) has been selected as the winner '
        f'of the {year} PEN/Faulkner Award for Fiction.</p>'
        f'{other_clause}'
    )
    return _article(
        f'Announcing the Winner of the {year} PEN/Faulkner Award for Fiction',
        body,
    )


_PAIRS_2019 = [
    ('Tomb of the Unknown Racist', 'Blanche McCrary Boyd', 'Counterpoint'),
    ('The Overstory', 'Richard Powers', 'W.W. Norton'),
    ('Love War Stories', 'Ivelisse Rodriguez', 'Feminist Press New York'),
    ('Call Me Zebra', 'Azareen Van der Vliet Oloomi', 'Houghton Mifflin Harcourt'),
    ('Don’t Skip Out on Me', 'Willy Vlautin', 'Harper Perennial'),
]
_PAIRS_2025 = [
    ('Ghostroots', '’Pemi Aguda', 'W.W. Norton & Company'),
    ('Behind You Is the Sea', 'Susan Muaddi Darraj', 'Harpervia'),
    ('James', 'Percival Everett', 'Doubleday'),
    ('Small Rain', 'Garth Greenwell', 'Farrar, Straus and Giroux'),
    ('Colored Television', 'Danzy Senna', 'Riverhead'),
]
_PAIRS_2026 = [
    ('Dominion', 'Addie E. Citchens', 'Farrar, Straus and Giroux'),
    ('The White Hot', 'Quiara Alegría Hudes', 'One World'),
    ('The Sisters', 'Jonas Hassen Khemiri', 'Farrar, Straus and Giroux'),
    ('Heart the Lover', 'Lily King', 'Grove Press'),
    ('Small Scale Sinners', 'Mahreen Sohail', 'A Public Space Books'),
]


def _status(records, title: str) -> str | None:
    for record in records:
        if record.work_title == title:
            return record.status
    return None


class HistoricalLandingParserTests(unittest.TestCase):
    def test_1981_winner_and_finalist(self):
        records = pf._parse_landing_html(_historical_landing(), _landing_url())
        pf._validate_historical_records(records)
        by_title = {record.work_title: record for record in records if record.award_year == 1981}
        self.assertEqual(by_title['How German Is It?'].status, 'Winner')
        self.assertEqual(by_title['How German Is It?'].work_author, 'Walter Abish')
        self.assertEqual(by_title['The Transit of Venus'].status, 'Finalist')
        self.assertEqual(by_title['The Transit of Venus'].work_author, 'Shirley Hazzard')
        self.assertEqual(by_title['How German Is It?'].source_url, _landing_url())
        result = pf._to_award_result(by_title['The Transit of Venus'])
        self.assertEqual(
            assess_award_result(result).qualification.decision,
            QualificationDecision.QUALIFIES,
        )

    def test_1982_five_named_nonwinning_finalists(self):
        records = [item for item in pf._parse_landing_html(_historical_landing(), _landing_url()) if item.award_year == 1982]
        self.assertEqual(sum(1 for item in records if item.status == 'Winner'), 1)
        self.assertEqual(sum(1 for item in records if item.status == 'Finalist'), 5)
        self.assertEqual(_status(records, 'The Chaneysville Incident'), 'Winner')

    def test_1984_official_typo_preserved(self):
        records = pf._parse_landing_html(_historical_landing(), _landing_url())
        match = [
            item
            for item in records
            if item.work_title.startswith('The Assasination of Jesse James')
        ]
        self.assertEqual(len(match), 1)
        self.assertEqual(match[0].work_author, 'Ron Hansen')
        self.assertEqual(match[0].status, 'Finalist')
        self.assertNotIn('Assassination', match[0].work_title)

    def test_1986_collection_winner(self):
        records = pf._parse_landing_html(_historical_landing(), _landing_url())
        match = [
            item
            for item in records
            if item.work_title == 'The Old Forest and Other Stories'
        ]
        self.assertEqual(match[0].work_author, 'Peter Taylor')
        self.assertEqual(match[0].status, 'Winner')
        self.assertEqual(match[0].award_year, 1986)

    def test_1989_three_named_finalists(self):
        records = [
            item
            for item in pf._parse_landing_html(_historical_landing(), _landing_url())
            if item.award_year == 1989
        ]
        self.assertEqual(_status(records, 'Dusk'), 'Winner')
        self.assertEqual(sum(1 for item in records if item.status == 'Finalist'), 3)
        pf._validate_historical_records(pf._parse_landing_html(_historical_landing(), _landing_url()))

    def test_1990_winner_and_finalist(self):
        records = [
            item
            for item in pf._parse_landing_html(_historical_landing(), _landing_url())
            if item.award_year == 1990
        ]
        self.assertEqual(_status(records, 'Billy Bathgate'), 'Winner')
        self.assertEqual(_status(records, 'Affliction'), 'Finalist')
        banks = [item for item in records if item.work_title == 'Affliction'][0]
        self.assertEqual(banks.work_author, 'Russell Banks')

    def test_2000_and_2004_and_2011_and_2013(self):
        records = pf._parse_landing_html(_historical_landing(), _landing_url())
        waiting = [item for item in records if item.work_title == 'Waiting'][0]
        self.assertEqual(waiting.work_author, 'Ha Jin')
        self.assertEqual(waiting.status, 'Winner')
        updike = [
            item
            for item in records
            if item.work_title == 'The Early Stories 1953–1975'
        ][0]
        self.assertEqual(updike.work_author, 'John Updike')
        eisenberg = [
            item
            for item in records
            if 'Collected Stories of Deborah Eisenberg' in item.work_title
        ][0]
        self.assertEqual(eisenberg.status, 'Winner')
        egan = [
            item
            for item in records
            if item.work_title == 'A Visit From the Goon Squad'
        ][0]
        self.assertEqual(egan.status, 'Finalist')
        saenz = [
            item
            for item in records
            if item.work_title == 'Everything Begins & Ends at the Kentucky Club'
        ][0]
        self.assertEqual(saenz.work_author, 'Benjamin Alire Sáenz')
        self.assertEqual(saenz.status, 'Winner')

    def test_2016_title_without_em(self):
        records = [
            item
            for item in pf._parse_landing_html(_historical_landing(), _landing_url())
            if item.award_year == 2016
        ]
        self.assertEqual(_status(records, 'Delicious Foods'), 'Winner')
        hannaham = [item for item in records if item.work_title == 'Delicious Foods'][0]
        self.assertEqual(hannaham.work_author, 'James Hannaham')

    def test_2017_winner_uses_landing_source_url(self):
        records = [
            item
            for item in pf._parse_landing_html(_historical_landing(), _landing_url())
            if item.work_title == 'Behold the Dreamers'
        ]
        self.assertEqual(records[0].work_author, 'Imbolo Mbue')
        self.assertEqual(records[0].source_url, _landing_url())
        self.assertEqual(records[0].award_year, 2017)

    def test_2018_winner_and_hernan_diaz(self):
        records = [
            item
            for item in pf._parse_landing_html(_historical_landing(), _landing_url())
            if item.award_year == 2018
        ]
        self.assertEqual(_status(records, 'Improvement'), 'Winner')
        diaz = [item for item in records if item.work_title == 'In The Distance'][0]
        self.assertEqual(diaz.work_author, 'Hernán Diaz')
        self.assertEqual(diaz.status, 'Finalist')


class HistoricalArchiveValidationTests(unittest.TestCase):
    def test_exact_year_range_1981_2018(self):
        records = pf._parse_landing_html(_historical_landing(), _landing_url())
        pf._validate_historical_records(records)
        years = {item.award_year for item in records}
        self.assertEqual(years, set(range(1981, 2019)))
        for year in years:
            winners = [
                item
                for item in records
                if item.award_year == year and item.status == 'Winner'
            ]
            self.assertEqual(len(winners), 1, year)

    def test_missing_year_rejects_historical_archive(self):
        html = _historical_landing(skip_year=1995)
        records = pf._parse_landing_html(html, _landing_url())
        with self.assertRaises(pf.PenFaulknerSourceError):
            pf._validate_historical_records(records)

    def test_missing_winner_rejects_historical_archive(self):
        html = _historical_landing().replace(
            '<p><strong>WINNER:</strong><br />Ha Jin, <em>Waiting</em></p>',
            '<p><strong>WINNER:</strong><br /></p>',
            1,
        )
        records = pf._parse_landing_html(html, _landing_url())
        with self.assertRaises(pf.PenFaulknerSourceError):
            pf._validate_historical_records(records)

    def test_finalist_count_varies_safely(self):
        records = pf._parse_landing_html(_historical_landing(), _landing_url())
        pf._validate_historical_records(records)
        counts = {}
        for year in (1982, 1989, 1990):
            counts[year] = sum(
                1
                for item in records
                if item.award_year == year and item.status == 'Finalist'
            )
        self.assertEqual(counts[1982], 5)
        self.assertEqual(counts[1989], 3)
        self.assertEqual(counts[1990], 4)

    def test_duplicate_identity_is_rejected(self):
        html = _historical_landing()
        records = pf._parse_landing_html(html, _landing_url())
        duplicated = records + tuple(
            item for item in records if item.award_year == 1990
        )
        with self.assertRaises(pf.PenFaulknerSourceError):
            pf._validate_historical_records(duplicated)

    def test_modern_cards_bad_alts_and_other_programs_are_ignored(self):
        extra = (
            '<h3>2026 Winner</h3>'
            '<img alt="THE BOOK OF GOOSE Book Cover" '
            'title="Small Scale Sinners" />'
            '<h2>The PEN/Hemingway Award for Debut Novel</h2>'
            '<p>WINNER:<br />Someone, A Debut</p>'
            '<h2>Elizabeth McCracken Wins the 2026 PEN/Bernard and Ann '
            'Malamud Award</h2>'
            '<h2>Willee Lewis is our 2026 PEN/Faulkner Literary Champion</h2>'
        )
        records = pf._parse_landing_html(
            _historical_landing(extra=extra),
            _landing_url(),
        )
        pf._validate_historical_records(records)
        self.assertFalse(any(item.award_year == 2026 for item in records))
        self.assertFalse(
            any(item.work_title == 'Small Scale Sinners' for item in records)
        )
        self.assertFalse(any('Hemingway' in item.work_title for item in records))
        self.assertFalse(any(item.work_author == 'Willee Lewis' for item in records))


class ModernParserTests(unittest.TestCase):
    def test_2019_author_for_title_finalists(self):
        html = _finalists_article(2019, _PAIRS_2019, style='author_for')
        records = pf._parse_finalists_html(html, 2019, _finalists_url(2019))
        self.assertEqual(len(records), 5)
        self.assertEqual(records[0].work_title, 'Tomb of the Unknown Racist')
        self.assertEqual(records[3].work_title, 'Call Me Zebra')
        self.assertFalse(
            any('Women of Color' in item.work_title for item in records)
        )

    def test_2020_title_by_author_despite_missing_space(self):
        pairs = [
            ('Sea Monsters', 'Chloe Arijdis', 'Catapult'),
            ('Where Reasons End', 'Yiyun Li', 'Random House'),
            ('Night Swimmers', 'Peter Rock', 'Soho Press'),
            ('We Cast a Shadow', 'Maurice Carlos Ruffin', 'One World'),
            ('On Earth We’re Briefly Gorgeous', 'Ocean Vuong', 'Penguin Press'),
        ]
        html = _finalists_article(2020, pairs, style='prose')
        html = html.replace('Chloe Arijdis (Catapult)', 'Chloe Arijdis(Catapult)')
        records = pf._parse_finalists_html(html, 2020, _finalists_url(2020))
        self.assertEqual(len(records), 5)
        self.assertEqual(records[0].work_author, 'Chloe Arijdis')

    def test_2020_winner_spelling_replaces_finalist_typo(self):
        pairs = [
            ('Sea Monsters', 'Chloe Arijdis', 'Catapult'),
            ('Where Reasons End', 'Yiyun Li', 'Random House'),
            ('Night Swimmers', 'Peter Rock', 'Soho Press'),
            ('We Cast a Shadow', 'Maurice Carlos Ruffin', 'One World'),
            ('On Earth We’re Briefly Gorgeous', 'Ocean Vuong', 'Penguin Press'),
        ]
        finalists = pf._parse_finalists_html(
            _finalists_article(2020, pairs, style='prose'),
            2020,
            _finalists_url(2020),
        )
        winner = pf._parse_winner_html(
            _winner_article(2020, 'Sea Monsters', 'Chloe Aridjis'),
            2020,
            _winner_url(2020),
        )
        merged = pf._dedupe_records(list(finalists) + [winner])
        pf._validate_modern_records(merged, 2020, 'winner')
        sea = [item for item in merged if item.work_title == 'Sea Monsters']
        self.assertEqual(len(sea), 1)
        self.assertEqual(sea[0].status, 'Winner')
        self.assertEqual(sea[0].work_author, 'Chloe Aridjis')
        self.assertEqual(sea[0].source_url, _winner_url(2020))
        self.assertEqual(sum(1 for item in merged if item.status == 'Finalist'), 4)
        rock = [item for item in merged if item.work_author == 'Peter Rock'][0]
        self.assertEqual(rock.work_title, 'Night Swimmers')
        self.assertEqual(rock.status, 'Finalist')
        self.assertTrue(pf._record_matches(sea[0], 'Sea Monsters', 'Chloe Aridjis'))
        self.assertTrue(pf._record_matches(sea[0], 'Sea Monsters', 'Chloe Arijdis'))
        self.assertTrue(pf._record_matches(rock, 'Night Swimmers', 'Peter Rock'))
        self.assertTrue(pf._record_matches(rock, 'The Night Swimmers', 'Peter Rock'))


class TwentyTwentyAliasTests(unittest.TestCase):
    def _record(self, year, title, author, status, url):
        return pf._ParsedRecord(
            award_year=year,
            category='Fiction',
            status=status,
            work_title=title,
            work_author=author,
            source_url=url,
        )

    def test_same_title_different_author_is_not_merged(self):
        winner = self._record(
            2020,
            'Shared Title',
            'Alice Author',
            'Winner',
            _winner_url(2020),
        )
        finalist = self._record(
            2020,
            'Shared Title',
            'Zed Other',
            'Finalist',
            _finalists_url(2020),
        )
        merged = pf._dedupe_records([finalist, winner])
        self.assertEqual(len(merged), 2)
        self.assertEqual(
            {(item.status, item.work_author) for item in merged},
            {('Winner', 'Alice Author'), ('Finalist', 'Zed Other')},
        )

    def test_sea_monsters_author_alias_does_not_apply_to_another_year(self):
        winner = self._record(
            2021,
            'Sea Monsters',
            'Chloe Aridjis',
            'Winner',
            _winner_url(2021),
        )
        finalist = self._record(
            2021,
            'Sea Monsters',
            'Chloe Arijdis',
            'Finalist',
            _winner_url(2021),
        )
        merged = pf._dedupe_records([finalist, winner])
        self.assertEqual(len(merged), 2)
        self.assertFalse(pf._record_matches(winner, 'Sea Monsters', 'Chloe Arijdis'))
        self.assertTrue(pf._record_matches(winner, 'Sea Monsters', 'Chloe Aridjis'))

    def test_aliases_do_not_apply_to_unrelated_title_or_author(self):
        other_author = self._record(
            2020,
            'Sea Monsters',
            'Other Author',
            'Winner',
            _winner_url(2020),
        )
        other_title = self._record(
            2020,
            'Other Book',
            'Peter Rock',
            'Finalist',
            _finalists_url(2020),
        )
        other_swimmer_author = self._record(
            2020,
            'Night Swimmers',
            'Jane Doe',
            'Finalist',
            _finalists_url(2020),
        )
        self.assertFalse(
            pf._record_matches(other_author, 'Sea Monsters', 'Chloe Arijdis')
        )
        self.assertFalse(
            pf._record_matches(other_title, 'The Night Swimmers', 'Peter Rock')
        )
        self.assertFalse(
            pf._record_matches(other_swimmer_author, 'The Night Swimmers', 'Jane Doe')
        )
        self.assertFalse(
            pf._record_matches(other_swimmer_author, 'The Night Swimmers', 'Peter Rock')
        )

    def test_night_swimmers_title_alias_does_not_apply_to_another_year(self):
        record = self._record(
            2021,
            'Night Swimmers',
            'Peter Rock',
            'Finalist',
            _winner_url(2021),
        )
        self.assertTrue(pf._record_matches(record, 'Night Swimmers', 'Peter Rock'))
        self.assertFalse(
            pf._record_matches(record, 'The Night Swimmers', 'Peter Rock')
        )


class ModernParserEraTests(unittest.TestCase):
    def test_2025_and_2026_merge_winner_once(self):
        finalists_2025 = pf._parse_finalists_html(
            _finalists_article(2025, _PAIRS_2025, style='prose'),
            2025,
            _finalists_url(2025),
        )
        winner_2025 = pf._parse_winner_html(
            _winner_article(
                2025,
                'Small Rain',
                'Garth Greenwell',
                [
                    ('Ghostroots', '’Pemi Aguda'),
                    ('Behind You Is the Sea', 'Susan Muaddi Darraj'),
                    ('James', 'Percival Everett'),
                    ('Colored Television', 'Danzy Senna'),
                ],
            ),
            2025,
            _winner_url(2025),
        )
        merged_2025 = pf._dedupe_records(list(finalists_2025) + [winner_2025])
        pf._validate_modern_records(merged_2025, 2025, 'winner')
        self.assertEqual(
            sum(1 for item in merged_2025 if item.status == 'Winner'),
            1,
        )
        self.assertEqual(
            sum(1 for item in merged_2025 if item.status == 'Finalist'),
            4,
        )
        rain = [item for item in merged_2025 if item.work_title == 'Small Rain'][0]
        self.assertEqual(rain.status, 'Winner')
        self.assertEqual(rain.source_url, _winner_url(2025))
        ghost = [item for item in merged_2025 if item.work_title == 'Ghostroots'][0]
        self.assertEqual(ghost.work_author, '’Pemi Aguda')

        finalists_2026 = pf._parse_finalists_html(
            _finalists_article(2026, _PAIRS_2026, style='colon_lines'),
            2026,
            _finalists_url(2026),
        )
        winner_2026 = pf._parse_winner_html(
            _winner_article(2026, 'Small Scale Sinners', 'Mahreen Sohail'),
            2026,
            _winner_url(2026),
        )
        merged_2026 = pf._dedupe_records(list(finalists_2026) + [winner_2026])
        pf._validate_modern_records(merged_2026, 2026, 'winner')
        self.assertEqual(len(merged_2026), 5)
        sinners = [
            item
            for item in merged_2026
            if item.work_title == 'Small Scale Sinners'
        ][0]
        self.assertEqual(sinners.status, 'Winner')
        hudes = [
            item for item in merged_2026 if item.work_title == 'The White Hot'
        ][0]
        self.assertEqual(hudes.work_author, 'Quiara Alegría Hudes')
        self.assertEqual(hudes.status, 'Finalist')

    def test_2022_through_2024_prose_era(self):
        pairs_by_year = {
            2022: [
                ('The Wrong End of the Telescope', 'Rabih Alameddine', 'Grove Press'),
                ('The Love Songs of W.E.B. Du Bois', 'Honorée Fanonne Jeffers', 'Harper'),
                ('The Prophets', 'Robert Jones, Jr.', 'G.P. Putnam’s Sons'),
                ('The Other Black Girl', 'Zakiya Dalila Harris', 'Atria Books'),
                ('Big Girl, Small Town', 'Michelle Gallen', 'Algonquin'),
            ],
            2023: [
                ('The Book of Goose', 'Yiyun Li', 'Farrar, Straus and Giroux'),
                ('If I Survive You', 'Jonathan Escoffery', 'MCD'),
                ('The Haunting of Hajji Hotak', 'Jamil Jan Kochai', 'Viking'),
                ('The Hero of This Book', 'Elizabeth McCracken', 'Ecco'),
                ('Bottoms Up and the Devil Laughs', 'Kerry Howley', 'Knopf'),
            ],
            2024: [
                ('What Happened to Ruthy Ramirez', 'Claire Jiménez', 'Grand Central'),
                ('This Other Eden', 'Paul Harding', 'W.W. Norton'),
                ('Wednesday’s Child', 'Yiyun Li', 'Farrar, Straus and Giroux'),
                ('The Heaven & Earth Grocery Store', 'James McBride', 'Riverhead'),
                ('Absolution', 'Alice McDermott', 'Farrar, Straus and Giroux'),
            ],
        }
        for year, pairs in pairs_by_year.items():
            html = _finalists_article(year, pairs, style='prose')
            records = pf._parse_finalists_html(html, year, _finalists_url(year))
            self.assertEqual(len(records), 5, year)
            self.assertEqual(records[0].work_title, pairs[0][0])
            winner = pf._parse_winner_html(
                _winner_article(year, pairs[0][0], pairs[0][1]),
                year,
                _winner_url(year),
            )
            merged = pf._dedupe_records(list(records) + [winner])
            pf._validate_modern_records(merged, year, 'winner')
            self.assertEqual(_status(merged, pairs[0][0]), 'Winner')

    def test_2021_other_finalists_from_winner_page(self):
        html = _winner_article(
            2021,
            'The Secret Lives of Church Ladies',
            'Deesha Philyaw',
            [
                ('Disappear Doppelgänger Disappear', 'Matthew Salesses'),
                ('The Knockout Queen', 'Rufi Thorpe'),
                ('Mother Daughter Widow Wife', 'Robin Wasserman'),
                ('Scattered Lights–', 'Steve Wiegenstein'),
            ],
        )
        winner = pf._parse_winner_html(html, 2021, _winner_url(2021))
        others = pf._parse_other_finalists_from_winner_body(
            html, 2021, _winner_url(2021)
        )
        merged = pf._dedupe_records([winner, *others])
        pf._validate_modern_records(merged, 2021, 'winner')
        self.assertEqual(winner.work_author, 'Deesha Philyaw')
        self.assertEqual(len(others), 4)
        lights = [
            item for item in others if 'Scattered Lights' in item.work_title
        ][0]
        self.assertEqual(lights.work_title, 'Scattered Lights')

    def test_2021_rest_title_is_not_award_year(self):
        payload = [
            {
                'title': {
                    'rendered': 'Announcing the Finalists for the 2022 PEN/Faulkner Award for Fiction'
                },
                'slug': 'announcing-the-finalists-for-2021-pen-faulkner-award-for-fiction',
                'link': (
                    'https://www.penfaulkner.org/2021/03/02/'
                    'announcing-the-finalists-for-2021-pen-faulkner-award-for-fiction/'
                ),
            }
        ]
        discovered = pf._discover_year_urls(2021, payload)
        self.assertEqual(
            discovered.get('finalists'),
            payload[0]['link'],
        )
        redirected = _finalists_article(2022, _PAIRS_2026, style='prose')
        with self.assertRaises(pf.PenFaulknerSourceError):
            pf._require_official_html(
                redirected,
                'https://www.penfaulkner.org/2022/03/02/announcing-the-finalists-for-the-2022-pen-faulkner-award-for-fiction/',
                award_year=2021,
            )

    def test_url_body_year_disagreement_fails_closed(self):
        html = _winner_article(2022, 'The Wrong End of the Telescope', 'Rabih Alameddine')
        with self.assertRaises(pf.PenFaulknerSourceError):
            pf._require_official_html(html, _winner_url(2021), award_year=2021)

    def test_longlist_is_not_parsed_from_finalists_chunk(self):
        html = _article(
            'Announcing the Longlist for the 2026 PEN/Faulkner Award for Fiction',
            '<p>The longlist includes King of Ashes by S.A. Cosby (Pine &amp; Cedar).</p>',
        )
        records = pf._parse_finalists_html(html, 2026, _finalists_url(2026))
        self.assertEqual(records, ())

    def test_pemi_variants_match(self):
        record = pf._ParsedRecord(
            award_year=2025,
            category='Fiction',
            status='Finalist',
            work_title='Ghostroots',
            work_author='’Pemi Aguda',
            source_url=_finalists_url(2025),
        )
        self.assertTrue(pf._record_matches(record, 'Ghostroots', '‘Pemi Aguda'))
        self.assertTrue(pf._record_matches(record, 'Ghostroots', "'Pemi Aguda"))

    def test_accents_are_not_stripped(self):
        record = pf._ParsedRecord(
            award_year=2026,
            category='Fiction',
            status='Finalist',
            work_title='The White Hot',
            work_author='Quiara Alegría Hudes',
            source_url=_finalists_url(2026),
        )
        self.assertTrue(
            pf._record_matches(record, 'The White Hot', 'Quiara Alegría Hudes')
        )
        self.assertFalse(
            pf._record_matches(record, 'The White Hot', 'Quiara Alegria Hudes')
        )


class DiscoveryFilterTests(unittest.TestCase):
    def test_hemingway_champion_and_longlist_are_rejected(self):
        payload = [
            {
                'title': {'rendered': 'Announcing the Winner of the 2027 PEN/Hemingway Award for Debut Novel'},
                'slug': 'announcing-the-winner-of-the-2027-pen-hemingway-award-for-debut-novel',
                'link': 'https://www.penfaulkner.org/2027/04/01/announcing-the-winner-of-the-2027-pen-hemingway-award-for-debut-novel/',
            },
            {
                'title': {'rendered': 'Willee Lewis is our 2027 PEN/Faulkner Literary Champion'},
                'slug': 'willee-lewis-is-our-2027-pen-faulkner-literary-champion',
                'link': 'https://www.penfaulkner.org/2027/10/01/willee-lewis-is-our-2027-pen-faulkner-literary-champion/',
            },
            {
                'title': {'rendered': 'Announcing the Longlist for the 2027 PEN/Faulkner Award for Fiction'},
                'slug': 'announcing-the-longlist-for-the-2027-pen-faulkner-award-for-fiction',
                'link': 'https://www.penfaulkner.org/2027/02/02/announcing-the-longlist-for-the-2027-pen-faulkner-award-for-fiction/',
            },
            {
                'title': {'rendered': 'Announcing the Finalists for the 2027 PEN/Faulkner Award for Fiction'},
                'slug': 'announcing-the-finalists-for-the-2027-pen-faulkner-award-for-fiction',
                'link': 'https://www.penfaulkner.org/2027/03/02/announcing-the-finalists-for-the-2027-pen-faulkner-award-for-fiction/',
            },
        ]
        discovered = pf._discover_year_urls(2027, payload)
        self.assertEqual(
            discovered,
            {
                'finalists': payload[3]['link'],
            },
        )

    def test_ambiguous_finalists_fail_closed(self):
        payload = [
            {
                'title': {'rendered': 'Announcing the Finalists for the 2027 PEN/Faulkner Award for Fiction'},
                'slug': 'announcing-the-finalists-for-the-2027-pen-faulkner-award-for-fiction',
                'link': 'https://www.penfaulkner.org/2027/03/02/announcing-the-finalists-for-the-2027-pen-faulkner-award-for-fiction/',
            },
            {
                'title': {'rendered': 'Announcing the Finalists for the 2027 PEN/Faulkner Award for Fiction'},
                'slug': 'announcing-the-finalists-for-the-2027-pen-faulkner-award-for-fiction-2',
                'link': 'https://www.penfaulkner.org/2027/03/03/announcing-the-finalists-for-the-2027-pen-faulkner-award-for-fiction-2/',
            },
        ]
        with self.assertRaises(pf.PenFaulknerSourceError):
            pf._discover_year_urls(2027, payload)

    def test_rest_content_is_not_used_as_facts(self):
        payload = [
            {
                'title': {'rendered': 'Announcing the Winner of the 2027 PEN/Faulkner Award for Fiction'},
                'slug': 'announcing-the-winner-of-the-2027-pen-faulkner-award-for-fiction',
                'link': 'https://www.penfaulkner.org/2027/04/06/announcing-the-winner-of-the-2027-pen-faulkner-award-for-fiction/',
                'content': {
                    'rendered': '<p>King of Ashes by S.A. Cosby has been selected as the winner of the 2027 PEN/Faulkner Award for Fiction.</p>'
                },
            }
        ]
        discovered = pf._discover_year_urls(2027, payload)
        self.assertEqual(
            discovered['winner'],
            payload[0]['link'],
        )
        self.assertNotIn('King of Ashes', json.dumps(discovered))


if __name__ == '__main__':
    unittest.main()
