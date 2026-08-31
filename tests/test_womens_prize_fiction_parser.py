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

    def test_winner_qualifies_with_source_policy_still_generic(self):
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
        self.assertTrue(
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
            with patch.object(wpf, '_get_shortlisted_records', return_value=()):
                homes = wpf.lookup('May We Be Forgiven', 'A. M. Homes')
                ofarrell = wpf.lookup('Hamnet', "Maggie O’Farrell")
                obreht = wpf.lookup("The Tiger's Wife", 'Téa Obreht')
        self.assertEqual(len(homes), 1)
        self.assertEqual(homes[0].work_author, 'A.M. Homes')
        self.assertEqual(len(ofarrell), 1)
        self.assertEqual(ofarrell[0].work_author, "Maggie O'Farrell")
        self.assertEqual(len(obreht), 1)
        self.assertEqual(obreht[0].work_author, 'Téa Obreht')


def _shortlist_article(heading: str, body: str, *, extra='') -> str:
    return (
        '<html><body>'
        f'<h1 class="product_title entry-title">{heading}</h1>'
        '<div class="main-content">'
        f'{body}'
        '<nav class="navigation post-navigation" aria-label="Posts"></nav>'
        '</div>'
        '<h5><a href="https://womensprize.com/announcing-the-2026-discoveries-shortlist/">'
        'Announcing the 2026 Discoveries shortlist</a></h5>'
        f'{extra}'
        '</body></html>'
    )


def _wysiwyg(inner: str) -> str:
    return f'<section class="wysiwyg-layout"><div>{inner}</div></section>'


def _feature_card(title: str, author: str, slug: str) -> str:
    return (
        '<section class="book-feature-layout">'
        '<div class="feature-book-card">'
        f'<div class="book"></div>'
        '<div class="book-content">'
        f'<h2>{title}</h2><p>by {author}</p>'
        f'<a href="https://womensprize.com/library/{slug}/" class="explore-link">'
        'Find out more</a>'
        '</div></div></section>'
    )


def _html_2017() -> str:
    return _shortlist_article(
        'Revealing the 2017 Shortlist…',
        _wysiwyg(
            '<p>We’re absolutely thrilled to reveal the 2017 Baileys Women’s '
            'Prize for Fiction shortlist.</p>'
            '<p><strong>The shortlisted books are as follows:</strong></p>'
            '<p>'
            '<a href="https://womensprize.com/books/stay-with-me/">'
            '<em>Stay With Me</em></a> by Ayọ̀bámi Adébáyọ̀̀<br />'
            '<a href="https://womensprize.com/books/the-power/">'
            '<em>The Power</em></a>  Naomi Alderman<br />'
            '<a href="https://womensprize.com/books/the-dark-circle/">'
            '<em>The Dark Circle</em></a> by Linda Grant<br />'
            '<a href="https://womensprize.com/books/the-sport-of-kings/">'
            '<em>The Sport of Kings</em></a> by C.E. Morgan<br />'
            '<a href="https://womensprize.com/books/797/">'
            '<em>First Love</em></a> by Gwendoline Riley<br />'
            '<a href="https://womensprize.com/books/do-not-say-we-have-nothing/">'
            '<em>Do Not Say We Have Nothing</em></a> by Madeleine Thien</p>'
        ),
    )


def _html_2018() -> str:
    return _shortlist_article(
        'Revealing the 2018 Women’s Prize shortlist…',
        _wysiwyg(
            '<h3>We’re absolutely delighted to reveal the six books which '
            'make up the 2018 Women’s Prize for Fiction shortlist!</h3>'
            '<p>The shortlist is as follows:</p>'
            '<p>Elif Batuman, '
            '<a href="https://womensprize.com/books/the-idiot/">The Idiot</a><br />'
            'Imogen Hermes Gowar, '
            '<a href="https://womensprize.com/books/the-mermaid-and-mrs-hancock/">'
            'The Mermaid and Mrs Hancock</a><br />'
            'Jessie Greengrass, '
            '<a href="https://womensprize.com/books/sight/">Sight</a><br />'
            'Meena Kandasamy, '
            '<a href="https://womensprize.com/books/when-i-hit-you-or-a-portrait-of-the-writer-as-a-young-wife/">'
            'When I Hit You: Or, A Portrait of the Writer as a Young Wife</a><br />'
            'Kamila Shamsie, '
            '<a href="https://womensprize.com/books/home-fire/">Home Fire</a><br />'
            'Jesmyn Ward, '
            '<a href="https://womensprize.com/books/sing-unburied-sing/">'
            'Sing, Unburied, Sing</a></p>'
        ),
    )


def _html_2019() -> str:
    return _shortlist_article(
        'Revealing the 2019 Women’s Prize for Fiction Shortlist',
        _wysiwyg(
            '<h3>We’re delighted to reveal this year’s Women’s Prize for '
            'Fiction shortlist, as chosen by our 2019 judges.</h3>'
            '<p><em><a href="https://womensprize.com/books/the-silence-of-the-girls/">'
            'The Silence of the Girls</a></em> by Pat Barker</p>'
            '<p><em><a href="https://womensprize.com/books/my-sister-the-serial-killer/">'
            'My Sister, the Serial Killer</a></em> by Oyinkan Braithwaite</p>'
            '<p><em><a href="https://womensprize.com/books/milkman/">'
            'Milkman</a></em> by Anna Burns</p>'
            '<p><em><a href="https://womensprize.com/books/ordinary-people/">'
            'Ordinary People</a></em> by Diana Evans</p>'
            '<p><em><a href="https://womensprize.com/books/an-american-marriage/">'
            'An American Marriage</a></em> by Tayari Jones</p>'
            '<p><em><a href="https://womensprize.com/books/circe/">'
            'Circe</a></em> by Madeline Miller</p>'
        ),
    )


def _html_2020() -> str:
    return _shortlist_article(
        'Announcing the 2020 Women’s Prize for Fiction shortlist',
        _wysiwyg(
            '<p>We are absolutely thrilled to reveal this year’s Women’s Prize '
            'for Fiction shortlist.</p>'
            '<p>The 2020 shortlist is as follows.</p>'
            '<p>'
            '<a href="https://womensprize.com/books/dominicana/">Dominicana</a> '
            'by Angie Cruz<br />'
            '<a href="https://womensprize.com/books/girl-woman-other/">'
            'Girl, Woman, Other</a> by Bernardine Evaristo<br />'
            '<a href="https://womensprize.com/books/a-thousand-ships/">'
            'A Thousand Ships</a> by Natalie Haynes<br />'
            '<a href="https://womensprize.com/books/the-mirror-and-the-light/">'
            'The Mirror and the Light</a> by Hilary Mantel<br />'
            '<a href="https://womensprize.com/books/hamnet/">Hamnet</a> '
            'by Maggie O’ Farrell<br />'
            '<a href="https://womensprize.com/books/weather/">Weather</a> '
            'by Jenny Offill</p>'
            '<p>Our brilliant judging panel will now whittle these 16 books '
            'down to a shortlist of just 6 novels, announced on April 22nd.</p>'
        ),
    )


def _html_2021() -> str:
    body = _wysiwyg(
        '<p>We are delighted to reveal this year’s Women’s Prize for Fiction '
        'shortlist.</p>'
        '<p>The six shortlisted books are as follows:</p>'
    )
    body += ''.join([
        _feature_card('The Vanishing Half', 'Brit Bennett', 'the-vanishing-half'),
        _feature_card('Piranesi', 'Susanna Clarke', 'piranesi'),
        _feature_card('Unsettled Ground', 'Claire Fuller', 'unsettled-ground'),
        _feature_card('Transcendent Kingdom', 'Yaa Gyasi', 'transcendent-kingdom'),
        _feature_card(
            'How the One-Armed Sister Sweeps Her House',
            'Cherie Jones',
            'how-the-one-armed-sister-sweeps-her-house',
        ),
        _feature_card(
            'No One is Talking about This',
            'Patricia Lockwood',
            'no-one-is-talking-about-this',
        ),
    ])
    return _shortlist_article(
        'Announcing the 2021 Women’s Prize shortlist',
        body,
    )


def _html_2022() -> str:
    return _shortlist_article(
        'Announcing the 2022 Women’s Prize shortlist!',
        _wysiwyg(
            '<p>The six shortlisted books are as follows:</p>'
            '<p><a href="https://womensprize.com/books/great-circle/">'
            '<em>Great Circle</em></a> by Maggie Shipstead</p>'
            '<p><a href="https://womensprize.com/books/sorrow-and-bliss/">'
            '<em>Sorrow and Bliss</em></a> by Meg Mason</p>'
            '<p><a href="https://womensprize.com/books/the-book-of-form-and-emptiness/">'
            '<em>The Book of Form and Emptiness</em></a> by Ruth Ozeki</p>'
            '<p><em><a href="https://womensprize.com/books/the-bread-the-devil-knead/">'
            'The Bread the Devil Knead</a></em> by Lisa Allen-Agostini</p>'
            '<p><a href="https://womensprize.com/books/the-island-of-missing-trees/">'
            '<em>The Island of Missing Trees</em></a> by Elif Shafak</p>'
            '<p><a href="https://womensprize.com/books/the-sentence/">'
            '<em>The Sentence</em></a> by Louise Erdrich</p>'
            '<p>The winner of this year’s Women’s Prize for Fiction will be '
            'awarded on Wednesday 15 June 2022.</p>'
        ),
    )


def _html_2023() -> str:
    return _shortlist_article(
        'Announcing the 2023 Women’s Prize shortlist',
        _wysiwyg(
            '<p>We are delighted to share with you the 2023 Women’s Prize for '
            'Fiction shortlist!</p>'
            '<p>The six shortlisted books are as follows:</p>'
            '<p><a href="https://womensprize.com/books/black-butterflies/">'
            '<em>Black Butterflies</em></a> by Priscilla Morris</p>'
            '<p><a href="https://womensprize.com/books/pod/"><em>Pod</em></a> '
            'by Laline Paull</p>'
            '<p><a href="https://womensprize.com/books/fire-rush/">'
            '<em>Fire Rush</em></a> by Jacqueline Crooks</p>'
            '<p><a href="https://womensprize.com/books/trespasses/">'
            '<em>Trespasses</em></a> by Louise Kennedy</p>'
            '<p><a href="https://womensprize.com/books/the-marriage-portrait/">'
            '<em>The Marriage Portrait</em></a> by Maggie O\'Farrell</p>'
            '<p><a href="https://womensprize.com/books/demon-copperhead/">'
            '<em>Demon Copperhead</em></a> by Barbara Kingsolver</p>'
        ),
    )


def _html_2024() -> str:
    return _shortlist_article(
        'Announcing the 2024 Women&#8217;s Prize for Fiction shortlist!',
        _wysiwyg(
            '<p>The full list in alphabetical order by author surname is:</p>'
            '<ul>'
            '<li><em><a href="https://womensprize.com/library/the-wren-the-wren/">'
            'The Wren, The Wren</a></em> by Anne Enright, published by Jonathan Cape</li>'
            '<li><em><a href="https://womensprize.com/library/brotherless-night/">'
            'Brotherless Night</a></em> by V. V. Ganeshananthan, published by Viking</li>'
            '<li><em><a href="https://womensprize.com/library/restless-dolly-maunder/">'
            'Restless Dolly Maunder</a></em> by Kate Grenville, published by Canongate Books</li>'
            '<li><em><a href="https://womensprize.com/library/enter-ghost/">'
            'Enter Ghost</a></em> by Isabella Hammad, published by Jonathan Cape</li>'
            '<li><em><a href="https://womensprize.com/library/soldier-sailor/">'
            'Soldier Sailor</a></em> by Claire Kilroy, published by Faber &amp; Faber</li>'
            '<li><em><a href="https://womensprize.com/library/river-east-river-west/">'
            'River East, River West</a></em> by Aube Rey Lescure, published by Duckworth</li>'
            '</ul>'
        ),
    )


def _html_2025() -> str:
    carousel = (
        '<a class="book_card" href="https://womensprize.com/library/good-girl/">'
        '<img alt="Good Girl" /></a>'
        '<a class="book_card" href="https://womensprize.com/library/all-fours/">'
        '<img alt="All Fours" /></a>'
        '<a class="book_card" href="https://womensprize.com/library/the-persians/">'
        '<img alt="The Persians" /></a>'
        '<a class="book_card" href="https://womensprize.com/library/tell-me-everything/">'
        '<img alt="Tell Me Everything" /></a>'
        '<a class="book_card" href="https://womensprize.com/library/the-safekeep/">'
        '<img alt="The Safekeep" /></a>'
        '<a class="book_card" href="https://womensprize.com/library/fundamentally/">'
        '<img alt="Fundamentally" /></a>'
        '<a class="book_card" href="https://womensprize.com/library/an-extra-seventh/">'
        '<img alt="Seventh Fake" /></a>'
    )
    return _shortlist_article(
        'Announcing the 2025 Women&#8217;s Prize for Fiction shortlist!',
        carousel + _wysiwyg(
            '<p>The 2025 shortlisted titles for the Women’s Prize for Fiction '
            'are as follows (alphabetical by authors surname):</p>'
            '<ul>'
            '<li><em><a href="https://womensprize.com/library/good-girl/">'
            'Good Girl</a></em> by Aria Aber (published by Bloomsbury Publishing)</li>'
            '<li><em><a href="https://womensprize.com/library/all-fours/">'
            'All Fours</a></em> by Miranda July (published by Canongate Books)</li>'
            '<li><em><a href="https://womensprize.com/library/the-persians/">'
            'The Persians</a></em> by Sanam Mahloudji '
            '(published by 4th Estate, HarperCollins)</li>'
            '<li><em><a href="https://womensprize.com/library/tell-me-everything/">'
            'Tell Me Everything</a></em> by Elizabeth Strout '
            '(published by Viking, Penguin General, Penguin Random House)</li>'
            '<li><em><a href="https://womensprize.com/library/the-safekeep/">'
            'The Safekeep</a></em> by Yael van der Wouden '
            '(published by Viking, Penguin General, Penguin Random House)</li>'
            '<li><em><a href="https://womensprize.com/library/fundamentally/">'
            'Fundamentally</a></em> by Nussaibah Younis '
            '(published by Weidenfeld &amp; Nicolson)</li>'
            '</ul>'
        ),
    )


def _html_2026() -> str:
    return _shortlist_article(
        'Revealing the 2026 Women’s Prize for Fiction Shortlist',
        _wysiwyg(
            '<p>We are delighted to reveal the six books that make up the 2026 '
            'Women’s Prize for Fiction shortlist.</p>'
            '<p>The full list in alphabetical order by author surname is:</p>'
            '<ul>'
            '<li><em><a href="https://womensprize.com/library/flashlight/">'
            'Flashlight</a></em> by Susan Choi '
            '(Jonathan Cape, Vintage, Penguin Random House UK)</li>'
            '<li><em><a href="https://womensprize.com/library/dominion/">'
            'Dominion</a></em> by Addie E. Citchens '
            '(Corsair, Little, Brown Book Group)</li>'
            '<li><em><a href="https://womensprize.com/library/the-correspondent/">'
            'The Correspondent</a></em> by Virginia Evans (Penguin)</li>'
            '<li><em><a href="https://womensprize.com/library/the-mercy-step/">'
            'The Mercy Step</a></em> by Marcia Hutchinson '
            '(Michael Joseph, Penguin Random House UK)</li>'
            '<li><em><a href="https://womensprize.com/library/kingfisher/">'
            'Kingfisher</a></em> by Rozie Kelly (Saraband)</li>'
            '<li><em><a href="https://womensprize.com/library/heart-the-lover/">'
            'Heart the Lover</a></em> by Lily King (Grove Press)</li>'
            '</ul>'
        ),
    )


def _parse_year(year: int, html: str, url: str | None = None):
    if url is None:
        url = wpf.VERIFIED_SHORTLIST_URLS[year]
    return wpf._parse_shortlist_article(html, year, url)


def _titles(records):
    return [record.work_title for record in records]


def _authors(records):
    return [record.work_author for record in records]


class WomensPrizeFictionShortlistParserTests(unittest.TestCase):
    def test_2017_six_and_missing_by_fallback(self):
        records = _parse_year(2017, _html_2017())
        self.assertEqual(len(records), 6)
        self.assertEqual(
            _titles(records)[0:2],
            ['Stay With Me', 'The Power'],
        )
        self.assertEqual(records[0].work_author, 'Ayọ̀bámi Adébáyọ̀̀')
        self.assertEqual(records[1].work_author, 'Naomi Alderman')
        self.assertEqual(records[1].source_url, 'https://womensprize.com/books/the-power/')
        self.assertTrue(all(record.status == 'Shortlisted' for record in records))
        self.assertTrue(all(record.rank is None for record in (
            wpf._to_award_result(record) for record in records
        )))

    def test_2018_author_comma_title_keeps_title_commas(self):
        records = _parse_year(2018, _html_2018())
        self.assertEqual(len(records), 6)
        kandasamy = [r for r in records if r.work_author == 'Meena Kandasamy'][0]
        self.assertEqual(
            kandasamy.work_title,
            'When I Hit You: Or, A Portrait of the Writer as a Young Wife',
        )
        self.assertEqual(records[0].work_author, 'Elif Batuman')
        self.assertEqual(records[0].work_title, 'The Idiot')

    def test_2019_title_by_author(self):
        records = _parse_year(2019, _html_2019())
        self.assertEqual(len(records), 6)
        self.assertEqual(records[0].work_title, 'The Silence of the Girls')
        self.assertEqual(records[0].work_author, 'Pat Barker')

    def test_2020_ignores_leftover_sixteen_books_sentence(self):
        records = _parse_year(2020, _html_2020())
        self.assertEqual(len(records), 6)
        hamnet = [r for r in records if r.work_title == 'Hamnet'][0]
        self.assertEqual(hamnet.work_author, 'Maggie O’ Farrell')
        self.assertNotIn('16', ' '.join(_titles(records)))
        self.assertEqual(len(records), 6)

    def test_2021_feature_book_cards(self):
        records = _parse_year(2021, _html_2021())
        self.assertEqual(len(records), 6)
        piranesi = [r for r in records if r.work_title == 'Piranesi'][0]
        self.assertEqual(piranesi.work_author, 'Susanna Clarke')
        self.assertEqual(
            piranesi.source_url,
            'https://womensprize.com/library/piranesi/',
        )

    def test_2022_book_of_form_and_emptiness(self):
        records = _parse_year(2022, _html_2022())
        self.assertEqual(len(records), 6)
        ozeki = [r for r in records if r.work_author == 'Ruth Ozeki'][0]
        self.assertEqual(ozeki.work_title, 'The Book of Form and Emptiness')

    def test_2023_marriage_portrait(self):
        records = _parse_year(2023, _html_2023())
        self.assertEqual(len(records), 6)
        portrait = [r for r in records if 'Marriage Portrait' in r.work_title][0]
        self.assertEqual(portrait.work_author, "Maggie O'Farrell")

    def test_2024_modern_list_items(self):
        records = _parse_year(2024, _html_2024())
        self.assertEqual(len(records), 6)
        enright = [r for r in records if r.work_author == 'Anne Enright'][0]
        self.assertEqual(enright.work_title, 'The Wren, The Wren')
        self.assertEqual(
            enright.source_url,
            'https://womensprize.com/library/the-wren-the-wren/',
        )

    def test_2025_ignores_title_only_carousel(self):
        records = _parse_year(2025, _html_2025())
        self.assertEqual(len(records), 6)
        aber = [r for r in records if r.work_author == 'Aria Aber'][0]
        self.assertEqual(aber.work_title, 'Good Girl')
        self.assertNotIn('Seventh Fake', _titles(records))

    def test_2026_includes_correspondent_and_kingfisher(self):
        records = _parse_year(2026, _html_2026())
        self.assertEqual(len(records), 6)
        self.assertIn('The Correspondent', _titles(records))
        self.assertIn('Kingfisher', _titles(records))
        kelly = [r for r in records if r.work_title == 'Kingfisher'][0]
        self.assertEqual(kelly.work_author, 'Rozie Kelly')

    def test_2015_and_2016_incomplete_pages_rejected(self):
        incomplete_2015 = _shortlist_article(
            'Baileys Women’s prize for Fiction announce 2015 shortlist',
            _wysiwyg(
                '<p>The Baileys Women’s Prize for Fiction is delighted to '
                'announce the 2015 shortlist. This year’s six shortlisted '
                'books were whittled down from a twenty-strong longlist.</p>'
            ),
        )
        incomplete_2016 = _shortlist_article(
            "Bailey's Women's Prize for Fiction 2016 shortlist",
            _wysiwyg(
                '<p>The Baileys Women’s Prize for Fiction today announces '
                'the 2016 shortlist.</p>'
            ),
        )
        with self.assertRaises(wpf.WomensPrizeFictionSourceError):
            wpf._parse_shortlist_article(
                incomplete_2015,
                2017,
                wpf.VERIFIED_SHORTLIST_URLS[2017],
            )
        with self.assertRaises(wpf.WomensPrizeFictionSourceError):
            wpf._parse_shortlist_article(
                incomplete_2016,
                2017,
                wpf.VERIFIED_SHORTLIST_URLS[2017],
            )

    def test_non_fiction_and_discoveries_pages_rejected(self):
        nf = _shortlist_article(
            'Announcing the 2024 Women’s Prize for Non-Fiction shortlist!',
            _wysiwyg('<p>The Women’s Prize for Non-Fiction shortlist.</p>'),
        )
        discoveries = _shortlist_article(
            'Announcing the 2026 Discoveries shortlist',
            _wysiwyg('<p>The Discoveries shortlist.</p>'),
        )
        with self.assertRaises(wpf.WomensPrizeFictionSourceError):
            wpf._parse_shortlist_article(
                nf,
                2024,
                'https://womensprize.com/announcing-the-2024-womens-prize-for-non-fiction-shortlist/',
            )
        with self.assertRaises(wpf.WomensPrizeFictionSourceError):
            wpf._parse_shortlist_article(
                discoveries,
                2026,
                'https://womensprize.com/announcing-the-2026-discoveries-shortlist/',
            )

    def test_wrong_count_is_rejected(self):
        five = _shortlist_article(
            'Announcing the 2024 Women’s Prize for Fiction shortlist!',
            _wysiwyg(
                '<ul>'
                '<li><em><a href="https://womensprize.com/library/a/">A</a></em> by One</li>'
                '<li><em><a href="https://womensprize.com/library/b/">B</a></em> by Two</li>'
                '<li><em><a href="https://womensprize.com/library/c/">C</a></em> by Three</li>'
                '<li><em><a href="https://womensprize.com/library/d/">D</a></em> by Four</li>'
                '<li><em><a href="https://womensprize.com/library/e/">E</a></em> by Five</li>'
                '</ul>'
            ),
        )
        with self.assertRaises(wpf.WomensPrizeFictionSourceError):
            _parse_year(2024, five)

    def test_related_discoveries_teaser_is_ignored(self):
        records = _parse_year(2024, _html_2024())
        self.assertEqual(len(records), 6)
        self.assertNotIn('Discoveries', ' '.join(_titles(records)))

    def test_ofarrell_author_compare_collapses_space_after_apostrophe(self):
        self.assertTrue(
            wpf._authors_match("Maggie O'Farrell", 'Maggie O’ Farrell')
        )
        self.assertTrue(
            wpf._authors_match("Maggie O' Farrell", "Maggie O'Farrell")
        )

    def test_winner_overlay_keeps_winner_spelling(self):
        winners = (
            wpf._ParsedRecord(
                award_year=2020,
                category='Fiction',
                status='Winner',
                work_title='Hamnet',
                work_author="Maggie O'Farrell",
                source_url='https://womensprize.com/library/hamnet/',
            ),
            wpf._ParsedRecord(
                award_year=2024,
                category='Fiction',
                status='Winner',
                work_title='Brotherless Night',
                work_author='V. V. Ganeshananthan',
                source_url='https://womensprize.com/library/brotherless-night/',
            ),
            wpf._ParsedRecord(
                award_year=2025,
                category='Fiction',
                status='Winner',
                work_title='The Safekeep',
                work_author='Yael van der Wouden',
                source_url='https://womensprize.com/library/the-safekeep/',
            ),
            wpf._ParsedRecord(
                award_year=2026,
                category='Fiction',
                status='Winner',
                work_title='The Correspondent',
                work_author='Virginia Evans',
                source_url='https://womensprize.com/library/the-correspondent/',
            ),
        )
        shortlisted = (
            wpf._ParsedRecord(
                award_year=2020,
                category='Fiction',
                status='Shortlisted',
                work_title='Hamnet',
                work_author='Maggie O’ Farrell',
                source_url='https://womensprize.com/books/hamnet/',
            ),
            wpf._ParsedRecord(
                award_year=2024,
                category='Fiction',
                status='Shortlisted',
                work_title='Brotherless Night',
                work_author='V. V. Ganeshananthan',
                source_url='https://womensprize.com/library/brotherless-night/',
            ),
            wpf._ParsedRecord(
                award_year=2025,
                category='Fiction',
                status='Shortlisted',
                work_title='The Safekeep',
                work_author='Yael van der Wouden',
                source_url='https://womensprize.com/library/the-safekeep/',
            ),
            wpf._ParsedRecord(
                award_year=2026,
                category='Fiction',
                status='Shortlisted',
                work_title='The Correspondent',
                work_author='Virginia Evans',
                source_url='https://womensprize.com/library/the-correspondent/',
            ),
            wpf._ParsedRecord(
                award_year=2025,
                category='Fiction',
                status='Shortlisted',
                work_title='Good Girl',
                work_author='Aria Aber',
                source_url='https://womensprize.com/library/good-girl/',
            ),
        )
        merged = wpf._merge_winners_and_shortlisted(winners, shortlisted)
        hamnets = [r for r in merged if r.work_title == 'Hamnet']
        self.assertEqual(len(hamnets), 1)
        self.assertEqual(hamnets[0].status, 'Winner')
        self.assertEqual(hamnets[0].work_author, "Maggie O'Farrell")
        for title in (
            'Brotherless Night',
            'The Safekeep',
            'The Correspondent',
        ):
            rows = [r for r in merged if r.work_title == title]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].status, 'Winner')
        good = [r for r in merged if r.work_title == 'Good Girl'][0]
        result = wpf._to_award_result(good)
        assessment = assess_award_result(result)
        self.assertEqual(result.status, 'Shortlisted')
        self.assertIsNone(result.rank)
        self.assertEqual(
            assessment.qualification.decision,
            QualificationDecision.QUALIFIES,
        )

    def test_pre_2017_synthetic_shortlisted_does_not_use_policy(self):
        result = wpf._to_award_result(
            wpf._ParsedRecord(
                award_year=2013,
                category='Fiction',
                status='Shortlisted',
                work_title='Life After Life',
                work_author='Kate Atkinson',
                source_url='https://womensprize.com/books/life-after-life/',
            )
        )
        assessment = assess_award_result(result)
        self.assertEqual(
            assessment.qualification.decision,
            QualificationDecision.REVIEW,
        )

    def test_lookup_merge_and_longlist_negative(self):
        winners = (
            wpf._ParsedRecord(
                award_year=2020,
                category='Fiction',
                status='Winner',
                work_title='Hamnet',
                work_author="Maggie O'Farrell",
                source_url='https://womensprize.com/library/hamnet/',
            ),
            wpf._ParsedRecord(
                award_year=2026,
                category='Fiction',
                status='Winner',
                work_title='The Correspondent',
                work_author='Virginia Evans',
                source_url='https://womensprize.com/library/the-correspondent/',
            ),
        )
        shortlisted = _parse_year(2026, _html_2026()) + (
            wpf._ParsedRecord(
                award_year=2025,
                category='Fiction',
                status='Shortlisted',
                work_title='Good Girl',
                work_author='Aria Aber',
                source_url='https://womensprize.com/library/good-girl/',
            ),
            wpf._ParsedRecord(
                award_year=2020,
                category='Fiction',
                status='Shortlisted',
                work_title='Hamnet',
                work_author='Maggie O’ Farrell',
                source_url='https://womensprize.com/books/hamnet/',
            ),
        )
        with patch.object(wpf, '_get_archive_records', return_value=winners):
            with patch.object(
                wpf, '_get_shortlisted_records', return_value=shortlisted
            ):
                correspondent = wpf.lookup(
                    'The Correspondent', 'Virginia Evans'
                )
                kingfisher = wpf.lookup('Kingfisher', 'Rozie Kelly')
                good = wpf.lookup('Good Girl', 'Aria Aber')
                hamnet = wpf.lookup('Hamnet', "Maggie O'Farrell")
                others = wpf.lookup('The Others', 'Sheena Kalayil')
        self.assertEqual(len(correspondent), 1)
        self.assertEqual(correspondent[0].status, 'Winner')
        self.assertEqual(len(kingfisher), 1)
        self.assertEqual(kingfisher[0].status, 'Shortlisted')
        self.assertIsNone(kingfisher[0].rank)
        self.assertEqual(
            assess_award_result(kingfisher[0]).qualification.decision,
            QualificationDecision.QUALIFIES,
        )
        self.assertEqual(good[0].status, 'Shortlisted')
        self.assertEqual(
            assess_award_result(good[0]).qualification.decision,
            QualificationDecision.QUALIFIES,
        )
        self.assertEqual(len(hamnet), 1)
        self.assertEqual(hamnet[0].status, 'Winner')
        self.assertEqual(others, [])


if __name__ == '__main__':
    unittest.main()
