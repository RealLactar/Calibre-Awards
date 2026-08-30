"""Offline coverage for the Women's Prize for Fiction Phase-1 parsers."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from awards.engine import assess_award_result
from awards.qualifier import QualificationDecision
from awards.registry import AWARD_POLICIES
from awards.sources import womens_prize_fiction as wpf


# Official previous-prizes spelling and library slugs, newest-first when
# iterated from 2025 down to 1996.
_OFFICIAL = {
    1996: ('A Spell of Winter', 'Helen Dunmore', 'a-spell-of-winter'),
    1997: ('Fugitive Pieces', 'Anne Michaels', 'fugitive-pieces'),
    1998: ("Larry's Party", 'Carol Shields', 'larrys-party'),
    1999: ('A Crime in the Neighborhood', 'Suzanne Berne', 'a-crime-in-the-neighborhood'),
    2000: ('When I Lived in Modern Times', 'Linda Grant', 'when-i-lived-in-modern-times'),
    2001: ('The Idea of Perfection', 'Kate Grenville', 'the-idea-of-perfection'),
    2002: ('Bel Canto', 'Ann Patchett', 'bel-canto'),
    2003: ('Property', 'Valerie Martin', 'property'),
    2004: ('Small Island', 'Andrea Levy', 'small-island'),
    2005: ('We Need to Talk About Kevin', 'Lionel Shriver', 'we-need-to-talk-about-kevin'),
    2006: ('On Beauty', 'Zadie Smith', 'on-beauty'),
    2007: ('Half of a Yellow Sun', 'Chimamanda Ngozi Adichie', 'half-of-a-yellow-sun'),
    2008: ('The Road Home', 'Rose Tremain', 'the-road-home'),
    2009: ('Home', 'Marilynne Robinson', 'home'),
    2010: ('The Lacuna', 'Barbara Kingsolver', 'the-lacuna'),
    2011: ("The Tiger's Wife", 'Téa Obreht', 'the-tigers-wife'),
    2012: ('The Song of Achilles', 'Madeline Miller', 'the-song-of-achilles'),
    2013: ('May We Be Forgiven', 'A.M. Homes', 'may-we-be-forgiven'),
    2014: ('A Girl is a Half-Formed Thing', 'Eimear McBride', 'a-girl-is-a-half-formed-thing'),
    2015: ('How to be Both', 'Ali Smith', 'how-to-be-both'),
    2016: ('The Glorious Heresies', 'Lisa McInerney', 'the-glorious-heresies'),
    2017: ('The Power', 'Naomi Alderman', 'the-power'),
    2018: ('Home Fire', 'Kamila Shamsie', 'home-fire'),
    2019: ('An American Marriage', 'Tayari Jones', 'an-american-marriage'),
    2020: ('Hamnet', "Maggie O'Farrell", 'hamnet'),
    2021: ('Piranesi', 'Susanna Clarke', 'piranesi'),
    2022: ('The Book of Form and Emptiness', 'Ruth Ozeki', 'the-book-of-form-and-emptiness'),
    2023: ('Demon Copperhead', 'Barbara Kingsolver', 'demon-copperhead'),
    2024: ('Brotherless Night', 'V. V. Ganeshananthan', 'brotherless-night'),
    2025: ('The Safekeep', 'Yael van der Wouden', 'the-safekeep'),
    2026: ('The Correspondent', 'Virginia Evans', 'the-correspondent'),
}


def _card(title: str, author: str, slug: str) -> str:
    return (
        '<div class="archive-column">'
        '<div class="post-card post-card--book card has-extras">'
        f'<a href="https://womensprize.com/library/{slug}/">'
        '<span class="post-card__content">'
        f'<h5>{title}</h5>'
        f'<p>{author}</p>'
        '</span></a></div></div>'
    )


def _cards_through(max_year: int) -> str:
    parts = []
    for year in range(max_year, wpf.ARCHIVE_MIN_YEAR - 1, -1):
        title, author, slug = _OFFICIAL[year]
        parts.append(_card(title, author, slug))
    return ''.join(parts)


def archive_html(*, max_year: int = 2025) -> str:
    return (
        '<html><head>'
        '<link rel="canonical" href="https://womensprize.com/prizes/'
        'womens-prize-for-fiction/previous-prizes/" />'
        '</head><body>'
        '<h1>The Women\'s Prize for Fiction</h1>'
        '<h2>Previous winners of the Women\'s Prize for Fiction</h2>'
        '<section class="book-grid">'
        f'{_cards_through(max_year)}'
        '</section>'
        '</body></html>'
    )


def home_html(
    *,
    title='The Correspondent',
    author='Virginia Evans',
    year=2026,
    slug='the-correspondent',
    include_winner_block=True,
    include_year_sentence=True,
    include_library_link=True,
    extra='',
) -> str:
    won = ''
    if include_year_sentence:
        won = (
            f'<p><em>{title}</em> by {author} has won the {year} '
            "Women's Prize for Fiction.</p>"
        )
    winner = ''
    if include_winner_block:
        link = ''
        if include_library_link:
            link = (
                f'<a href="https://womensprize.com/library/{slug}/" '
                f'class="btn btn_more">{title}</a>'
            )
        winner = (
            '<p class="eyebrow">Winner</p>'
            f'<h3 class="h1"><strong>{title} by {author}</strong></h3>'
            f'{link}'
        )
    return (
        '<html><head>'
        '<link rel="canonical" href="https://womensprize.com/prizes/'
        'womens-prize-for-fiction/" />'
        '</head><body>'
        '<h1>Women\'s Prize for Fiction</h1>'
        f'{won}{winner}'
        '<div class="previous_winners">'
        '<h3>Previous Winners</h3>'
        '<p><em><a href="https://womensprize.com/library/piranesi/">'
        'Piranesi</a></em><br />Susannah Clarke</p>'
        '<p><em><a href="https://womensprize.com/library/'
        'the-book-of-form-and-emptiness/">'
        'The Book of Form &amp; Emptiness</a></em><br />Ruth Ozeki</p>'
        '</div>'
        '<h2>The 2025 Women\'s Prize for Fiction shortlist</h2>'
        '<a href="https://womensprize.com/library/fundamentally/" '
        'class="book_card"><img alt="Fundamentally" /></a>'
        '<h2>The 2025 Women\'s Prize for Fiction longlist</h2>'
        '<p>Women\'s Prize for Non-Fiction</p>'
        f'{extra}'
        '</body></html>'
    )


def _merged(archive, home, *, current_year=2026):
    with patch.object(wpf, '_current_calendar_year', return_value=current_year):
        wpf._require_archive_identity(archive)
        cards = wpf._parse_previous_prizes_html(archive)
        archive_records, archive_max = wpf._assign_archive_years(cards)
        wpf._validate_archive_records(archive_records, archive_max)
        current = None
        try:
            wpf._require_home_identity(home)
            current = wpf._parse_current_winner(home)
        except wpf.WomensPrizeFictionSourceError:
            current = None
        merged = wpf._merge_records(archive_records, current)
        wpf._validate_merged_records(merged, archive_max)
        return merged, archive_records, current, archive_max


class WomensPrizeFictionIdentityTests(unittest.TestCase):
    def test_previous_prizes_page_identity(self):
        wpf._require_archive_identity(archive_html())

    def test_main_fiction_page_identity(self):
        wpf._require_home_identity(home_html())

    def test_non_fiction_page_identity_is_rejected(self):
        html = (
            '<html><h1>Women\'s Prize for Non-Fiction</h1>'
            '<p>Women\'s Prize for Fiction</p></html>'
        )
        with self.assertRaises(wpf.WomensPrizeFictionSourceError):
            wpf._require_home_identity(html)

    def test_unrelated_page_identity_is_rejected(self):
        with self.assertRaises(wpf.WomensPrizeFictionSourceError):
            wpf._require_archive_identity('<html><h1>Unrelated</h1></html>')
        with self.assertRaises(wpf.WomensPrizeFictionSourceError):
            wpf._require_home_identity('<html><h1>Unrelated</h1></html>')


class WomensPrizeFictionArchiveParserTests(unittest.TestCase):
    def test_historical_winner_card_extraction_and_order(self):
        cards = wpf._parse_previous_prizes_html(archive_html())
        self.assertEqual(len(cards), 30)
        self.assertEqual(cards[0].work_title, 'The Safekeep')
        self.assertEqual(cards[0].work_author, 'Yael van der Wouden')
        self.assertEqual(
            cards[0].source_url,
            'https://womensprize.com/library/the-safekeep/',
        )
        self.assertEqual(cards[-1].work_title, 'A Spell of Winter')
        self.assertEqual(cards[-1].work_author, 'Helen Dunmore')

    def test_year_derivation_from_card_count(self):
        with patch.object(wpf, '_current_calendar_year', return_value=2026):
            thirty, max_thirty = wpf._assign_archive_years(
                wpf._parse_previous_prizes_html(archive_html(max_year=2025))
            )
            thirty_one, max_thirty_one = wpf._assign_archive_years(
                wpf._parse_previous_prizes_html(archive_html(max_year=2026))
            )
        self.assertEqual(max_thirty, 2025)
        self.assertEqual(thirty[0].award_year, 2025)
        self.assertEqual(thirty[-1].award_year, 1996)
        self.assertEqual(max_thirty_one, 2026)
        self.assertEqual(thirty_one[0].award_year, 2026)
        self.assertEqual(thirty_one[0].work_title, 'The Correspondent')
        self.assertEqual(thirty_one[-1].award_year, 1996)
        self.assertEqual(thirty[0].work_title, 'The Safekeep')

    def test_oldest_permanent_anchor(self):
        with patch.object(wpf, '_current_calendar_year', return_value=2026):
            records, archive_max = wpf._assign_archive_years(
                wpf._parse_previous_prizes_html(archive_html())
            )
            wpf._validate_archive_records(records, archive_max)
        oldest = records[-1]
        self.assertEqual(oldest.award_year, 1996)
        self.assertEqual(oldest.work_title, 'A Spell of Winter')
        self.assertEqual(oldest.work_author, 'Helen Dunmore')

    def test_missing_1996_anchor_is_rejected(self):
        html = archive_html().replace(
            _card('A Spell of Winter', 'Helen Dunmore', 'a-spell-of-winter'),
            _card('Wrong Oldest', 'Someone Else', 'wrong-oldest'),
        )
        with patch.object(wpf, '_current_calendar_year', return_value=2026):
            records, archive_max = wpf._assign_archive_years(
                wpf._parse_previous_prizes_html(html)
            )
            with self.assertRaises(wpf.WomensPrizeFictionSourceError):
                wpf._validate_archive_records(records, archive_max)

    def test_archive_growth_is_accepted_without_hardcoded_first_card_year(self):
        with patch.object(wpf, '_current_calendar_year', return_value=2026):
            grown, archive_max = wpf._assign_archive_years(
                wpf._parse_previous_prizes_html(archive_html(max_year=2026))
            )
            wpf._validate_archive_records(grown, archive_max)
        self.assertEqual(archive_max, 2026)
        self.assertEqual(grown[0].work_title, 'The Correspondent')
        self.assertEqual(grown[1].work_title, 'The Safekeep')
        self.assertEqual(grown[1].award_year, 2025)


class WomensPrizeFictionCurrentPageTests(unittest.TestCase):
    def test_current_winner_from_official_block(self):
        record = wpf._parse_current_winner(home_html())
        self.assertIsNotNone(record)
        self.assertEqual(record.work_title, 'The Correspondent')
        self.assertEqual(record.work_author, 'Virginia Evans')
        self.assertEqual(record.award_year, 2026)
        self.assertEqual(record.status, 'Winner')
        self.assertEqual(
            record.source_url,
            'https://womensprize.com/library/the-correspondent/',
        )

    def test_current_page_uses_explicit_year_not_utc_clock(self):
        with patch.object(wpf, '_current_calendar_year', return_value=2027):
            record = wpf._parse_current_winner(home_html(year=2026))
        self.assertEqual(record.award_year, 2026)
        self.assertNotEqual(record.award_year, 2027)

    def test_winner_without_determinable_year_fails_enrichment(self):
        with self.assertRaises(wpf.WomensPrizeFictionSourceError):
            wpf._parse_current_winner(home_html(include_year_sentence=False))

    def test_absent_winner_block_is_not_a_winner(self):
        self.assertIsNone(
            wpf._parse_current_winner(home_html(include_winner_block=False))
        )


class WomensPrizeFictionMergeTests(unittest.TestCase):
    def test_archive_and_main_duplicate_winner_is_one_record(self):
        merged, archive, current, _archive_max = _merged(
            archive_html(max_year=2026),
            home_html(),
        )
        self.assertEqual(len(archive), 31)
        self.assertIsNotNone(current)
        self.assertEqual(current.award_year, 2026)
        correspondents = [
            record for record in merged if record.award_year == 2026
        ]
        self.assertEqual(len(correspondents), 1)
        self.assertEqual(len(merged), 31)

    def test_archive_spelling_wins_over_sidebar_disagreement(self):
        merged, _archive, _current, _archive_max = _merged(
            archive_html(),
            home_html(),
        )
        piranesi = [
            record for record in merged if record.work_title == 'Piranesi'
        ][0]
        self.assertEqual(piranesi.work_author, 'Susanna Clarke')
        self.assertNotEqual(piranesi.work_author, 'Susannah Clarke')
        emptiness = [
            record
            for record in merged
            if 'Form' in record.work_title and 'Emptiness' in record.work_title
        ][0]
        self.assertEqual(emptiness.work_title, 'The Book of Form and Emptiness')
        self.assertNotIn('&', emptiness.work_title)

    def test_main_page_only_supplies_2026_when_archive_ends_2025(self):
        merged, archive, current, _archive_max = _merged(
            archive_html(max_year=2025),
            home_html(),
        )
        self.assertEqual(len(archive), 30)
        self.assertEqual(archive[0].award_year, 2025)
        self.assertEqual(current.award_year, 2026)
        self.assertEqual(len(merged), 31)
        self.assertEqual(
            [record.award_year for record in merged],
            list(range(1996, 2027)),
        )

    def test_january_rollover_keeps_official_2026_winner(self):
        merged, _archive, current, _archive_max = _merged(
            archive_html(max_year=2025),
            home_html(year=2026),
            current_year=2027,
        )
        self.assertEqual(current.award_year, 2026)
        self.assertEqual(merged[-1].award_year, 2026)
        self.assertEqual(merged[-1].work_title, 'The Correspondent')
        self.assertFalse(any(record.award_year == 2027 for record in merged))


class WomensPrizeFictionMatchingTests(unittest.TestCase):
    def test_initial_spacing_a_m_homes(self):
        self.assertTrue(wpf._authors_match('A. M. Homes', 'A.M. Homes'))
        self.assertTrue(wpf._authors_match('A.M. Homes', 'A.M. Homes'))

    def test_apostrophe_maggie_ofarrell(self):
        self.assertTrue(
            wpf._authors_match("Maggie O'Farrell", "Maggie O’Farrell")
        )
        self.assertTrue(
            wpf._titles_match('Hamnet', 'Hamnet')
        )

    def test_diacritic_tea_obreht_preserved(self):
        self.assertTrue(wpf._authors_match('Téa Obreht', 'Téa Obreht'))
        self.assertFalse(wpf._authors_match('Tea Obreht', 'Téa Obreht'))

    def test_v_v_ganeshananthan_initials(self):
        self.assertTrue(
            wpf._authors_match('V.V. Ganeshananthan', 'V. V. Ganeshananthan')
        )


class WomensPrizeFictionResultSchemaTests(unittest.TestCase):
    def test_exact_winner_awardresult_schema(self):
        merged, _archive, _current, _archive_max = _merged(
            archive_html(),
            home_html(),
        )
        by_year = {record.award_year: record for record in merged}
        locked = {
            1996: ('A Spell of Winter', 'Helen Dunmore'),
            1997: ('Fugitive Pieces', 'Anne Michaels'),
            2005: ('We Need to Talk About Kevin', 'Lionel Shriver'),
            2006: ('On Beauty', 'Zadie Smith'),
            2010: ('The Lacuna', 'Barbara Kingsolver'),
            2011: ("The Tiger's Wife", 'Téa Obreht'),
            2012: ('The Song of Achilles', 'Madeline Miller'),
            2013: ('May We Be Forgiven', 'A.M. Homes'),
            2014: ('A Girl is a Half-Formed Thing', 'Eimear McBride'),
            2017: ('The Power', 'Naomi Alderman'),
            2020: ('Hamnet', "Maggie O'Farrell"),
            2024: ('Brotherless Night', 'V. V. Ganeshananthan'),
            2025: ('The Safekeep', 'Yael van der Wouden'),
            2026: ('The Correspondent', 'Virginia Evans'),
        }
        for year, (title, author) in locked.items():
            record = by_year[year]
            result = wpf._to_award_result(record)
            self.assertEqual(result.work_title, title)
            self.assertEqual(result.work_author, author)
            self.assertEqual(result.award_name, "Women's Prize for Fiction")
            self.assertEqual(result.award_year, year)
            self.assertEqual(result.category, 'Fiction')
            self.assertEqual(result.status, 'Winner')
            self.assertIsNone(result.rank)
            self.assertEqual(result.source_name, "Women's Prize for Fiction")
            self.assertTrue(
                result.source_url.startswith('https://womensprize.com/library/')
            )
            self.assertIsNone(result.notes)
            self.assertEqual(result.identity_kind, 'work')

    def test_no_shortlisted_or_longlist_results(self):
        merged, _archive, _current, _archive_max = _merged(
            archive_html(),
            home_html(),
        )
        self.assertTrue(all(record.status == 'Winner' for record in merged))
        titles = {record.work_title for record in merged}
        self.assertNotIn('Fundamentally', titles)
        self.assertEqual(len(merged), 31)
        for record in merged:
            result = wpf._to_award_result(record)
            self.assertNotEqual(result.status, 'Shortlisted')
            self.assertIsNone(result.rank)

    def test_non_fiction_and_carousel_are_ignored(self):
        merged, _archive, _current, _archive_max = _merged(
            archive_html(),
            home_html(),
        )
        authors = {record.work_author for record in merged}
        self.assertNotIn('Susannah Clarke', authors)
        titles = {record.work_title for record in merged}
        self.assertNotIn('The Book of Form & Emptiness', titles)
        self.assertNotIn('Fundamentally', titles)

    def test_historical_orange_years_use_current_award_name(self):
        merged, _archive, _current, _archive_max = _merged(
            archive_html(),
            home_html(),
        )
        for record in merged:
            result = wpf._to_award_result(record)
            self.assertEqual(result.award_name, "Women's Prize for Fiction")
            self.assertNotEqual(result.award_name, 'Orange Prize for Fiction')
            self.assertNotEqual(
                result.award_name,
                "Baileys Women's Prize for Fiction",
            )

    def test_winner_qualifies_without_source_policy(self):
        merged, _archive, _current, _archive_max = _merged(
            archive_html(),
            home_html(),
        )
        result = wpf._to_award_result(merged[-1])
        assessment = assess_award_result(result)
        self.assertEqual(
            assessment.qualification.decision,
            QualificationDecision.QUALIFIES,
        )
        self.assertFalse(
            hasattr(__import__('awards.registry', fromlist=['x']),
                    'WOMENS_PRIZE_FICTION_POLICY')
        )
        self.assertFalse(
            any(
                policy.award_name == "Women's Prize for Fiction"
                for policy in AWARD_POLICIES
            )
        )

    def test_lookup_uses_initial_spacing_and_apostrophe(self):
        merged, _archive, _current, _archive_max = _merged(
            archive_html(),
            home_html(),
        )
        with patch.object(wpf, '_get_archive_records', return_value=merged):
            homes = wpf.lookup('May We Be Forgiven', 'A. M. Homes')
            ofarrell = wpf.lookup('Hamnet', "Maggie O’Farrell")
            obreht = wpf.lookup("The Tiger's Wife", 'Téa Obreht')
        self.assertEqual(len(homes), 1)
        self.assertEqual(homes[0].work_author, 'A.M. Homes')
        self.assertEqual(len(ofarrell), 1)
        self.assertEqual(ofarrell[0].work_author, "Maggie O'Farrell")
        self.assertEqual(len(obreht), 1)
        self.assertEqual(obreht[0].work_author, 'Téa Obreht')


if __name__ == '__main__':
    unittest.main()
