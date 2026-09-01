"""Offline coverage for International Prize for Arabic Fiction parsers."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from awards.engine import assess_award_result
from awards.qualifier import QualificationDecision
from awards.sources import ipaf as src


def _year_url(year: int) -> str:
    return src._year_page_url(year)


def _index_url() -> str:
    return src.PRIZE_YEARS_INDEX_URL


def _profile_url() -> str:
    return src.WINNER_2020_PROFILE_URL


def _card(title: str, author: str) -> str:
    return (
        '<article class="Card_root__x">'
        f'<h4 class="NodeBookCard_title__x">{title}</h4>'
        f'<span class="NodeBookCard_authors__x">{author}</span>'
        '</article>'
    )


def _winner_block(year: int, title: str, author: str) -> str:
    return (
        '<div class="ParagraphFeaturedBook_root__x">'
        f'<h2 class="ParagraphFeaturedBook_superTitle__x">'
        f'<span>Winner<!-- --> <!-- -->{year}</span></h2>'
        f'<h2 class="ParagraphFeaturedBook_title__x">{title}</h2>'
        f'<p class="ParagraphFeaturedBook_author__x">{author}</p>'
        '<img alt="I Resist the River&#x27;s Course" />'
        '</div>'
    )


def _year_page(
    year: int,
    *,
    winner: tuple[str, str] | None,
    shortlist: list[tuple[str, str]],
    heading: str = 'Shortlist',
    longlist: list[tuple[str, str]] | None = None,
    judges: tuple[str, ...] = ('Maya Abu Al-Hayyat',),
    extra: str = '',
    title: str | None = None,
    h1: str | None = None,
) -> str:
    winner_html = _winner_block(year, *winner) if winner else ''
    shortlist_html = ''.join(_card(title, author) for title, author in shortlist)
    longlist = longlist or [
        ("Grandma Touma's Cord", 'Abdelouahab Aissaoui'),
        ('Life Is Not a Novel', 'Abdo Wazen'),
    ]
    longlist_html = ''.join(_card(title, author) for title, author in longlist)
    judges_html = ''.join(f'<h2>{name}</h2>' for name in judges)
    page_title = title or f'IPAF {year} | The International Prize for Arabic Fiction'
    heading_text = h1 if h1 is not None else f'IPAF {year}'
    return (
        '<html><head>'
        f'<title>{page_title}</title>'
        '</head><body>'
        '<header>IPAF 2026 Features &amp; Updates</header>'
        f'<h1>{heading_text}</h1>'
        f'{extra}'
        f'{winner_html}'
        '<div class="ParagraphShortlistBookBlock_root__x">'
        f'<h2 class="ParagraphShortlistBookBlock_heading__x">{heading}</h2>'
        f'<div class="ParagraphShortlistBookBlock_grid__x">{shortlist_html}</div>'
        '</div>'
        '<div class="ParagraphLonglistBookBlock_root__x">'
        '<h2>Longlist</h2>'
        f'{longlist_html}'
        '</div>'
        '<h2>Judges</h2>'
        f'{judges_html}'
        '<div class="OtherPrizeYears_root__x">'
        '<h2>Other Prize Years</h2>'
        '<h2>IPAF 2022</h2>'
        '</div>'
        '<script>self.__next_f.push([1,"{\\"title\\":\\"RSC Winner\\",'
        '\\"author\\":\\"RSC Author\\"}"])</script>'
        '</body></html>'
    )


def _empty_shell() -> str:
    return (
        '<html><head><title>The International Prize for Arabic Fiction</title>'
        '</head><body>'
        '<nav>IPAF 2026 Features &amp; Updates How to submit</nav>'
        '<footer>Copyright © 2009 - 2026 International Prize for Arabic Fiction'
        '</footer></body></html>'
    )


def _homepage() -> str:
    return (
        '<html><head><title>The International Prize for Arabic Fiction</title>'
        '</head><body>'
        '<h1>The International Prize for Arabic Fiction</h1>'
        + _winner_block(2026, 'Swimming Against the Tide', 'Said Khatibi')
        + '</body></html>'
    )


def _profile_page(
    *,
    title: str = 'The Spartan Court',
    heading: str = 'Prize Winner 2020',
    author: str = 'Abdelouahab Aissaoui',
    page_title: str | None = None,
) -> str:
    head = page_title or f'{title} | The International Prize for Arabic Fiction'
    return (
        '<html><head>'
        f'<title>{head}</title>'
        '</head><body>'
        '<article>'
        '<header>'
        f'<h1>{title}</h1>'
        f'<h2>{heading}</h2>'
        f'<span class="NodeBook_author__x">{author}</span>'
        '<span class="NodeBook_publisher__x">Dar Min</span>'
        '</header>'
        '<h2>About the Author</h2>'
        '<p>Abdelouahab Aissaoui is an Algerian novelist.</p>'
        '<h2>See more 2020 books</h2>'
        '<h2>2020 Shortlist</h2>'
        + _card('Firewood of Sarajevo', 'Said Khatibi')
        + '<h2>2020 Longlist</h2>'
        + _card("Grandma Touma's Cord", 'Abdelouahab Aissaoui')
        + '</article></body></html>'
    )


def _index_page(years: list[int]) -> str:
    cards = []
    for year in years:
        cards.append(
            f'<a href="/prize-years/ipaf-{year}">'
            f'<h2 class="NodePrizeYearCard_title__x">IPAF {year}</h2>'
            '<h3>Winner</h3>'
            '<span class="NodePrizeYearCard_bookTitle__x">Index Title Only</span>'
            '<h3>Shortlist</h3>'
            '</a>'
        )
    return (
        '<html><head>'
        '<title>The International Prize for Arabic Fiction Prize Years | '
        'The International Prize for Arabic Fiction</title>'
        '</head><body>'
        '<h1>Prize Years</h1>'
        f'{"".join(cards)}'
        '</body></html>'
    )


SHORTLIST_2020 = [
    ('The Russian Quarter', 'Khalil Alrez'),
    ('The King of India', 'Jabbour Douaihy'),
    ('Firewood of Sarajevo', 'Said Khatibi'),
    ('The Tank', 'Alia Mamdouh'),
    (
        'Fardeqan – the Detention of the Great Sheikh',
        'Youssef Ziedan',
    ),
]
SHORTLIST_2021 = [
    ('The Eye of Hammurabi', 'Abdulatif Ould Abdullah'),
    ('Calamity of the Nobility', 'Amira Ghenim'),
    ('The Bird Tattoo', 'Dunya Mikhail'),
    ('File 42', 'Abdelmajid Sebbata'),
    ('Longing for the Woman Next Door', 'Habib Selmi'),
]
SHORTLIST_2022 = [
    ("Rose's Diary", 'Reem al-Kamali'),
    ('The White Line of Night', 'Khalid Al-Nassrallah'),
    ('Cairo Maquette', 'Tareq Imam'),
    ('Dilshad', 'Bushra Khalfan'),
    ('The Prisoner of the Portuguese', 'Mohsine Loukili'),
]
SHORTLIST_2023 = [
    ('The Highest Part of the Horizon', 'Fatima Abdulhamid'),
    ('Tales from the Town of Rising Sun', 'Miral al-Tahawy'),
    ('Concerto Qurina Eduardo', 'Najwa Binshatwan'),
    ('Drought', 'Siddik Hadj-Ahmed'),
    ('The Stone of Happiness', 'Azher Jirjees'),
]
SHORTLIST_2024 = [
    ('The Seventh Heaven of Jerusalem', 'Osama Al-Eissa'),
    ('Gambling on the Honour of Lady Mitzi', 'Ahmed al-Morsi'),
    ('Bahbel: Makkah Multiverse 1945-2009', 'Raja Alem'),
    ("Suleima's Ring", 'Rima Bali'),
    ('The Mosaicist', 'Eissa Nasiri'),
]
SHORTLIST_2025 = [
    ("The Women's Covenant", 'Haneen Al-Sayegh'),
    ('Danishmand', 'Ahmed Fal Al Din'),
    ('The Valley of the Butterflies', 'Azher Jirjees'),
    ('The Andalusian Messiah', 'Taissier Khalaf'),
    ('The Touch of Light', 'Nadia Najar'),
]
SHORTLIST_2026 = [
    ('The Origin of Species', 'Ahmad Abdulatif'),
    ('The Absence of Mai', 'Najwa Barakat'),
    ('A Cloud Above My Head', 'Doaa Ibrahim'),
    ('The Seer', 'Diaa Jubaili'),
    ('Siesta Dream', 'Amin Zaoui'),
]

WINNERS = {
    2021: ('Notebooks of the Bookseller', 'Jalal Barjas'),
    2022: ("Bread on Uncle Milad's Table", 'Mohamed Alnaas'),
    2023: ('The Water Diviner', 'Zahran Alqasmi'),
    2024: ('A Mask, the Colour of the Sky', 'Basim Khandaqji'),
    2025: ('The Prayer of Anxiety', 'Mohamed Samir Nada'),
    2026: ('Swimming Against the Tide', 'Said Khatibi'),
}

SHORTLISTS = {
    2020: SHORTLIST_2020,
    2021: SHORTLIST_2021,
    2022: SHORTLIST_2022,
    2023: SHORTLIST_2023,
    2024: SHORTLIST_2024,
    2025: SHORTLIST_2025,
    2026: SHORTLIST_2026,
}


def _completed_year_html(year: int) -> str:
    heading = 'The shortlist' if year == 2024 else 'Shortlist'
    return _year_page(
        year,
        winner=WINNERS[year],
        shortlist=SHORTLISTS[year],
        heading=heading,
    )


def _year_2020_html() -> str:
    return _year_page(2020, winner=None, shortlist=SHORTLIST_2020)


def _parse_year(html: str, year: int):
    url = _year_url(year)
    src._require_year_page_identity(html, url, year)
    return src._parse_year_page(html, year, url)


def _status(records, title: str) -> str | None:
    for record in records:
        if record.work_title == title:
            return record.status
    return None


class YearPageIdentityTests(unittest.TestCase):
    def test_populated_page_identity_accepted(self):
        html = _completed_year_html(2026)
        official = src._require_year_page_identity(html, _year_url(2026), 2026)
        self.assertEqual(official, _year_url(2026))

    def test_soft_200_generic_shell_rejected(self):
        with self.assertRaises(src.IpafSourceError):
            src._require_year_page_identity(_empty_shell(), _year_url(2026), 2026)

    def test_wrong_year_page_rejected(self):
        html = _completed_year_html(2025)
        with self.assertRaises(src.IpafSourceError):
            src._require_year_page_identity(html, _year_url(2026), 2026)

    def test_homepage_canonicalization_rejected(self):
        with self.assertRaises(src.IpafSourceError):
            src._require_year_page_identity(_homepage(), src.SOURCE_HOME_URL, 2026)

    def test_arabic_host_rejected(self):
        with self.assertRaises(src.IpafSourceError):
            src._require_year_page_identity(
                _completed_year_html(2026),
                'https://ar.arabicfiction.org/prize-years/ipaf-2026',
                2026,
            )


class YearPageParserTests(unittest.TestCase):
    def test_verified_winners_2021_through_2026(self):
        for year, (title, author) in WINNERS.items():
            parsed = _parse_year(_completed_year_html(year), year)
            self.assertIsNotNone(parsed.winner, year)
            self.assertEqual(parsed.winner.work_title, title)
            self.assertEqual(parsed.winner.work_author, author)
            self.assertEqual(parsed.winner.status, 'Winner')
            self.assertEqual(parsed.winner.award_year, year)
            self.assertIsNone(src._to_award_result(parsed.winner).rank)
            self.assertEqual(len(parsed.shortlisted), 5, year)

    def test_heading_variant_the_shortlist(self):
        parsed = _parse_year(_completed_year_html(2024), 2024)
        self.assertEqual(len(parsed.shortlisted), 5)
        titles = [item.work_title for item in parsed.shortlisted]
        self.assertIn('Bahbel: Makkah Multiverse 1945-2009', titles)

    def test_judges_and_longlist_and_other_years_ignored(self):
        parsed = _parse_year(_completed_year_html(2026), 2026)
        titles = {item.work_title for item in parsed.shortlisted}
        if parsed.winner is not None:
            titles.add(parsed.winner.work_title)
        self.assertNotIn("Grandma Touma's Cord", titles)
        self.assertNotIn('Life Is Not a Novel', titles)
        self.assertNotIn('Maya Abu Al-Hayyat', titles)
        authors = {item.work_author for item in parsed.shortlisted}
        self.assertNotIn('Maya Abu Al-Hayyat', authors)
        self.assertNotIn('RSC Winner', titles)
        self.assertNotIn('RSC Author', authors)

    def test_image_alt_is_not_used_as_title(self):
        parsed = _parse_year(_completed_year_html(2026), 2026)
        self.assertEqual(parsed.winner.work_title, 'Swimming Against the Tide')
        self.assertNotEqual(parsed.winner.work_title, "I Resist the River's Course")

    def test_2020_year_page_parses_five_shortlisted_without_inventing_winner(self):
        parsed = _parse_year(_year_2020_html(), 2020)
        self.assertIsNone(parsed.winner)
        self.assertEqual(len(parsed.shortlisted), 5)
        firewood = [
            item
            for item in parsed.shortlisted
            if item.work_title == 'Firewood of Sarajevo'
        ]
        self.assertEqual(len(firewood), 1)
        self.assertEqual(firewood[0].work_author, 'Said Khatibi')
        self.assertEqual(firewood[0].status, 'Shortlisted')
        self.assertEqual(firewood[0].source_url, _year_url(2020))

    def test_required_shortlisted_fixtures(self):
        fixtures = {
            2020: ('Firewood of Sarajevo', 'Said Khatibi'),
            2022: ("Rose's Diary", 'Reem al-Kamali'),
            2024: ('Bahbel: Makkah Multiverse 1945-2009', 'Raja Alem'),
            2025: ("The Women's Covenant", 'Haneen Al-Sayegh'),
            2026: ('The Origin of Species', 'Ahmad Abdulatif'),
        }
        for year, (title, author) in fixtures.items():
            html = (
                _year_2020_html() if year == 2020 else _completed_year_html(year)
            )
            parsed = _parse_year(html, year)
            match = [
                item
                for item in parsed.shortlisted
                if item.work_title == title
            ]
            self.assertEqual(len(match), 1, year)
            self.assertEqual(match[0].work_author, author)
            self.assertEqual(match[0].status, 'Shortlisted')
            self.assertIsNone(src._to_award_result(match[0]).rank)

    def test_2026_seer_shortlisted(self):
        parsed = _parse_year(_completed_year_html(2026), 2026)
        seer = [
            item for item in parsed.shortlisted if item.work_title == 'The Seer'
        ]
        self.assertEqual(seer[0].work_author, 'Diaa Jubaili')

    def test_title_precedence_does_not_use_announcement_variants(self):
        parsed = _parse_year(_completed_year_html(2026), 2026)
        self.assertEqual(parsed.winner.work_title, 'Swimming Against the Tide')
        self.assertEqual(parsed.winner.work_author, 'Said Khatibi')
        parsed = _parse_year(_completed_year_html(2022), 2022)
        self.assertEqual(
            parsed.winner.work_title, "Bread on Uncle Milad's Table"
        )
        self.assertEqual(parsed.winner.work_author, 'Mohamed Alnaas')
        parsed = _parse_year(_completed_year_html(2023), 2023)
        self.assertEqual(parsed.winner.work_title, 'The Water Diviner')
        parsed = _parse_year(_completed_year_html(2025), 2025)
        titles = [item.work_title for item in parsed.shortlisted]
        self.assertIn("The Women's Covenant", titles)
        self.assertNotIn("The Women's Charter", titles)

    def test_author_romanization_preserved(self):
        parsed = _parse_year(_completed_year_html(2022), 2022)
        authors = {item.work_author for item in parsed.shortlisted}
        self.assertIn('Reem al-Kamali', authors)
        self.assertIn('Khalid Al-Nassrallah', authors)
        self.assertEqual(parsed.winner.work_author, 'Mohamed Alnaas')

    def test_shortlisted_qualifies_via_policy(self):
        parsed = _parse_year(_completed_year_html(2026), 2026)
        result = src._to_award_result(parsed.shortlisted[0])
        self.assertEqual(
            assess_award_result(result).qualification.decision,
            QualificationDecision.QUALIFIES,
        )
        winner = src._to_award_result(parsed.winner)
        self.assertEqual(
            assess_award_result(winner).qualification.decision,
            QualificationDecision.QUALIFIES,
        )


class WinnerProfileParserTests(unittest.TestCase):
    def test_2020_profile_parses_winner(self):
        html = _profile_page()
        official = src._require_winner_profile_identity(html, _profile_url(), 2020)
        record = src._parse_winner_profile(html, 2020, official)
        self.assertEqual(record.work_title, 'The Spartan Court')
        self.assertEqual(record.work_author, 'Abdelouahab Aissaoui')
        self.assertEqual(record.status, 'Winner')
        self.assertEqual(record.award_year, 2020)
        self.assertEqual(record.source_url, _profile_url())
        self.assertEqual(src._to_award_result(record).identity_kind, 'work')

    def test_profile_does_not_emit_carousel_shortlist_or_longlist(self):
        html = _profile_page()
        record = src._parse_winner_profile(html, 2020, _profile_url())
        self.assertEqual(record.work_title, 'The Spartan Court')
        self.assertNotEqual(record.work_title, 'Firewood of Sarajevo')
        self.assertNotEqual(record.work_title, "Grandma Touma's Cord")

    def test_profile_wrong_year_rejected(self):
        html = _profile_page(heading='Prize Winner 2021')
        with self.assertRaises(src.IpafSourceError):
            src._require_winner_profile_identity(html, _profile_url(), 2020)

    def test_profile_wrong_status_rejected(self):
        html = _profile_page(heading='2020 Shortlist')
        with self.assertRaises(src.IpafSourceError):
            src._require_winner_profile_identity(html, _profile_url(), 2020)


class YearAcquireSpecialCaseTests(unittest.TestCase):
    def test_2020_profile_failure_keeps_shortlisted(self):
        pages = {
            _year_url(2020): _year_2020_html(),
            _profile_url(): 'FAIL',
        }

        def fetch_response(url: str):
            body = pages.get(url)
            if body == 'FAIL':
                raise src.IpafSourceError('profile failed')
            return 200, body, url

        with patch.object(src, '_fetch_response', fetch_response):
            snapshot = src._acquire_live_year(2020)
        self.assertEqual(snapshot.state, 'shortlisted')
        self.assertEqual(len(snapshot.records), 5)
        self.assertTrue(all(item.status == 'Shortlisted' for item in snapshot.records))
        self.assertEqual(snapshot.source_urls, (_year_url(2020),))

    def test_2020_profile_success_completes_winner(self):
        pages = {
            _year_url(2020): _year_2020_html(),
            _profile_url(): _profile_page(),
        }

        def fetch_response(url: str):
            return 200, pages[url], url

        with patch.object(src, '_fetch_response', fetch_response):
            snapshot = src._acquire_live_year(2020)
        self.assertEqual(snapshot.state, 'winner')
        winners = [item for item in snapshot.records if item.status == 'Winner']
        self.assertEqual(len(winners), 1)
        self.assertEqual(winners[0].work_title, 'The Spartan Court')
        self.assertEqual(winners[0].source_url, _profile_url())
        shortlisted = [
            item for item in snapshot.records if item.status == 'Shortlisted'
        ]
        self.assertEqual(len(shortlisted), 5)
        self.assertTrue(
            all(item.source_url == _year_url(2020) for item in shortlisted)
        )


class IndexParserTests(unittest.TestCase):
    def test_index_discovers_2020_through_2026(self):
        html = _index_page(list(range(2020, 2027)))
        src._require_index_identity(html, _index_url())
        years = src._parse_index_years(html)
        self.assertEqual(years, tuple(range(2020, 2027)))

    def test_2008_2019_placeholders_are_not_supported(self):
        html = _index_page([2008, 2009, 2019, 2020, 2026])
        years = src._parse_index_years(html)
        self.assertNotIn(2008, years)
        self.assertNotIn(2009, years)
        self.assertNotIn(2019, years)
        self.assertIn(2020, years)
        self.assertEqual(
            src._supported_years_from_index(years),
            tuple(range(2020, 2027)),
        )

    def test_future_2027_index_entry_is_accepted(self):
        html = _index_page(list(range(2020, 2028)))
        years = src._parse_index_years(html)
        self.assertIn(2027, years)
        self.assertEqual(
            src._supported_years_from_index(years)[-1],
            2027,
        )

    def test_index_does_not_create_award_results_from_titles(self):
        html = _index_page([2026])
        years = src._parse_index_years(html)
        self.assertEqual(years, (2026,))
        snapshot = src._IndexSnapshot(supported_years=years, source_url=_index_url())
        self.assertEqual(snapshot.supported_years, (2026,))

    def test_index_soft_200_rejected(self):
        with self.assertRaises(src.IpafSourceError):
            src._require_index_identity(_empty_shell(), _index_url())


class MergeTests(unittest.TestCase):
    def test_winner_outranks_shortlisted_same_identity(self):
        winner = src._make_record(
            2027,
            'Winner',
            'Future Winner',
            'Future Author',
            _year_url(2027),
        )
        shortlisted = src._make_record(
            2027,
            'Shortlisted',
            'Future Winner',
            'Future Author',
            _year_url(2027),
        )
        merged = src._dedupe_records([shortlisted, winner])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].status, 'Winner')

    def test_no_author_only_or_title_only_merge(self):
        left = src._make_record(
            2026, 'Winner', 'Swimming Against the Tide', 'Said Khatibi', _year_url(2026)
        )
        right = src._make_record(
            2026,
            'Shortlisted',
            "I Resist the River's Course",
            'Said Khatibi',
            _year_url(2026),
        )
        merged = src._dedupe_records([left, right])
        self.assertEqual(len(merged), 2)
