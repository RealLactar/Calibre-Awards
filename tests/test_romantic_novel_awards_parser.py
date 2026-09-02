"""Offline coverage for the Romantic Novel of the Year Awards parser."""

from __future__ import annotations

import json
import unittest
import urllib.parse
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from awards import cache
from awards.engine import assess_award_result
from awards.model import AwardResult
from awards.qualifier import QualificationDecision
from awards.registry import RONA_SHORTLIST_POLICY, find_award_policy
from awards.sources import romantic_novel_awards as src


SITE = src.SITE_ORIGIN
ARCHIVE = src.WINNERS_ARCHIVE_URL
RONA_FAMILY = 'the-romantic-novel-of-the-year-awards'
SHORTLIST_2026 = SITE + '/news/rna-reveals-2026-shortlists/'
WINNERS_2026 = SITE + '/news/rna-announces-the-2026-winners/'
SHORTLIST_2018 = SITE + '/news/2018-rona-shortlists-announced/'
SHORTLIST_2020 = SITE + '/news/rna-announces-2020-shortlists/'
WINNERS_2020 = SITE + '/news/rna-announces-the-2020-winners/'
WINNERS_2022 = SITE + '/news/rna-announces-the-2022-winners/'
WINNERS_2025 = SITE + '/news/rna-announces-the-2025-winners/'
SHORTLIST_2019 = SITE + '/news/2019-rona-shortlists-announced/'
NEWS_CAT_ID = 812


def _card(
    title,
    author,
    year,
    slug,
    *,
    family=RONA_FAMILY,
    families=None,
    family_label='Romantic Novel of the Year',
    category_slug='',
    category_label='',
    publisher='HQ',
    relative_href=False,
):
    href = f'/past-winners/{slug}' if relative_href else f'{ARCHIVE}/{slug}'
    family_html = ''
    family_slugs = list(families) if families is not None else ([family] if family else [])
    for fam in family_slugs:
        label = family_label if fam == RONA_FAMILY else fam.replace('-', ' ').title()
        family_html += (
            f'<li><strong><a href="{SITE}/past_winners_awards/{fam}">'
            f'{label}</a></strong></li>'
        )
    cat_html = ''
    if category_slug:
        cat_html = (
            f'<li><a href="{SITE}/past_winners_award_categories/{category_slug}">'
            f'{category_label}</a></li>'
        )
    year_html = ''
    if year is not None:
        year_html = (
            f'<li><a href="{SITE}/past_winners_years/{year}">{year}</a></li>'
        )
    return (
        '<li>'
        f'<h2><a href="{href}">{title}</a></h2>'
        f'<h2>{author}</h2>'
        f'<ul class="info"><li>{publisher}</li></ul>'
        f'<ul class="tags">{family_html}{cat_html}{year_html}</ul>'
        '</li>'
    )


def archive_html(
    cards,
    *,
    page=1,
    of_pages=1,
    identity=True,
    extra='',
):
    links = ''.join(
        f'<a href="/past-winners/page/{number}/">{number}</a>'
        for number in range(1, of_pages + 1)
    )
    body_class = 'post-type-archive-past_winners' if identity else 'page error404'
    title = 'Past winners' if identity else 'Page not found'
    heading = 'Past winners' if identity else 'Nothing found'
    novelists = "Romantic Novelists' Association" if identity else ''
    return (
        '<!DOCTYPE html><html><head>'
        f'<title>{title}</title></head>'
        f'<body class="{body_class}">'
        f'<h1>{heading}</h1><p>{novelists}</p>'
        f'<p>Page {page} of {of_pages}</p>{links}'
        f'<ul>{"".join(cards)}</ul>{extra}'
        '</body></html>'
    )


def _records_from_html(html):
    parsed = src._parse_archive_page(html)
    records = []
    for card in parsed.cards:
        record = src._winner_card_to_record(card)
        if record is not None:
            records.append(record)
    return parsed, tuple(records)


def _accordion_section(heading, books):
    parts = [f'<h2>{heading}</h2><div class="panel">']
    for title, author, winner, slug in books:
        if winner:
            href = f'{ARCHIVE}/{slug}' if slug else ''
            if href:
                parts.append(
                    f'<h2>WINNER: <a href="{href}"><em>{title}</em> by {author}</a></h2>'
                )
            else:
                parts.append(f'<h2>WINNER: {title} by {author}</h2>')
        else:
            parts.append(f'<h3>{title} by {author}</h3>')
    parts.append('</div>')
    return ''.join(parts)


def accordion_html(sections):
    body = ''.join(_accordion_section(heading, books) for heading, books in sections)
    return (
        '<!DOCTYPE html><html><body>'
        f'<section class="accordion">{body}</section>'
        '</body></html>'
    )


def comma_list_html(sections, *, intro='The Category Shortlists'):
    parts = [f'<p>{intro}</p>']
    for heading, books in sections:
        parts.append(f'<h2>{heading}</h2>')
        for title, author, publisher in books:
            parts.append(f'<p>{title}, {author}, {publisher}</p>')
    return '<!DOCTYPE html><html><body>' + ''.join(parts) + '</body></html>'


def winner_list_html(sections):
    parts = []
    for heading, books in sections:
        parts.append(f'<h2>{heading}</h2>')
        for title, author in books:
            parts.append(f'<p>{title} by {author}</p>')
    return '<!DOCTYPE html><html><body>' + ''.join(parts) + '</body></html>'


def winner_marked_html(sections):
    parts = []
    for heading, books in sections:
        parts.append(f'<h2>{heading}</h2>')
        for title, author in books:
            parts.append(f'<p>WINNER: {title} by {author}</p>')
    return '<!DOCTYPE html><html><body>' + ''.join(parts) + '</body></html>'


def _unstructured_2023_winner_html():
    return (
        '<!DOCTYPE html><html><body>'
        "<h1>ROMANTIC NOVELISTS' ASSOCIATION ROMANTIC NOVEL AWARDS 2023</h1>"
        '<p>Press release</p>'
        '<p>Jackie Collins was a creative force in romantic fiction for decades.</p>'
        '<p>Jackie Collins, Queen of the Bonkbusters, remains an inspiration.</p>'
        '<h2>The Historical Romance Award</h2>'
        '<p>The Forgotten Village by Lorna Cook</p>'
        '<p>Lorna Cook, The Forgotten Village</p>'
        '<p>Lorna Cook</p>'
        '<p>The Forgotten Village</p>'
        '<h2>About the award sponsors:</h2>'
        '<p>Writing Better Romance by ProWritingAid</p>'
        '<p>ProWritingAid uses AI to check your writing for style issues.</p>'
        '<p>ProWritingAid, Sponsor Partner, advert</p>'
        '</body></html>'
    )


def _rest_title(text):
    return {'rendered': text}


def _news_item(post_id, title, slug, date, year):
    return {
        'id': post_id,
        'date': date,
        'slug': slug,
        'link': f'{SITE}/news/{slug}/',
        'title': _rest_title(title),
    }


def _taxonomy_payload(category_id=NEWS_CAT_ID):
    return [
        {
            'id': category_id,
            'slug': src.NEWS_CATEGORY_SLUG,
            'name': 'The Romantic Novel Awards',
        }
    ]


_DEBUT = 'Debut Romance Novel Award'
_ROMANTASY = 'Romantasy/Romantic Fantasy Award'
_THRILLER = 'The Romantic Thriller Award'
_FESTIVE = 'The Festive/Holiday Romance Novel Award'
_SHORTER = 'The Shorter Romance Novel Award'
_SAGA = 'The Saga Romance Award'
_HISTORICAL = 'The Historical Romance Award'
_CONTEMPORARY = 'The Contemporary Romance Novel Award'
_SPICY = 'The Contemporary Spicy Romance Novel Award'
_COMEDY = 'The Romantic Comedy Award'
_BESTSELLER = 'The Romance Bestseller Award'


def _2026_shortlist_sections():
    return [
        (
            _DEBUT,
            [
                ('Any Trope But You', 'Victoria Lavine', True, 'any-trope-but-you'),
                ('To Hell With It', 'Claire Frances', False, None),
                ('Debut Three', 'Author Three', False, None),
                ('Debut Four', 'Author Four', False, None),
                ('Debut Five', 'Author Five', False, None),
                ('Debut Six', 'Author Six', False, None),
            ],
        ),
        (
            _ROMANTASY,
            [
                ('Wooing the Witch Queen', 'Stephanie Burgis', True, 'wooing-the-witch-queen'),
                ('Onyx Storm', 'Rebecca Yarros', False, None),
                ('Romantasy Three', 'Author R3', False, None),
                ('Romantasy Four', 'Author R4', False, None),
                ('Romantasy Five', 'Author R5', False, None),
                ('Romantasy Six', 'Author R6', False, None),
                ('Romantasy Seven', 'Author R7', False, None),
            ],
        ),
        (
            _THRILLER,
            [
                ('He’s To Die For', 'Erin Dunn', True, 'hes-to-die-for'),
                ('The Greek House', 'Dinah Jefferies', False, None),
                ('Thriller Three', 'Author T3', False, None),
                ('Thriller Four', 'Author T4', False, None),
                ('Thriller Five', 'Author T5', False, None),
                ('Thriller Six', 'Author T6', False, None),
            ],
        ),
        (
            _FESTIVE,
            [
                ('Christmas Fling', 'Lindsey Kelk', True, 'christmas-fling'),
                ('Just a Taste', 'Anise Starre', False, None),
                ('Festive Three', 'Author F3', False, None),
                ('Festive Four', 'Author F4', False, None),
                ('Festive Five', 'Author F5', False, None),
                ('Festive Six', 'Author F6', False, None),
            ],
        ),
        (
            _SHORTER,
            [
                ('Filthy Rich Temptation', 'Rachael Stewart', True, 'filthy-rich-temptation'),
                ('Greek’s Kidnapped Princess', 'Heidi Rice', False, None),
                ('Shorter Three', 'Author S3', False, None),
                ('Shorter Four', 'Author S4', False, None),
                ('Shorter Five', 'Author S5', False, None),
                ('Shorter Six', 'Author S6', False, None),
            ],
        ),
        (
            _SAGA,
            [
                ('The Lost Diamond', 'Kathleen McGurl', True, 'the-lost-diamond'),
                ('New Horizons for the Woolworth Girls', 'Elaine Everest', False, None),
                ('Saga Three', 'Author G3', False, None),
                ('Saga Four', 'Author G4', False, None),
                ('Saga Five', 'Author G5', False, None),
                ('Saga Six', 'Author G6', False, None),
            ],
        ),
        (
            _HISTORICAL,
            [
                ('The Earl’s Unlikely Bride', 'Ella Matthews', True, 'the-earls-unlikely-bride'),
                ('The Maid’s Masquerade', 'Catherine Tinley', False, None),
                ('Historical Three', 'Author H3', False, None),
                ('Historical Four', 'Author H4', False, None),
                ('Historical Five', 'Author H5', False, None),
                ('Historical Six', 'Author H6', False, None),
            ],
        ),
        (
            _CONTEMPORARY,
            [
                ('Finding Home in Hartfell', 'Suzanne Snow', True, 'finding-home-in-hartfell'),
                ('First-Time Caller', 'B.K. Borison', False, None),
                ('Contemporary Three', 'Author C3', False, None),
                ('Contemporary Four', 'Author C4', False, None),
                ('Contemporary Five', 'Author C5', False, None),
                ('Contemporary Six', 'Author C6', False, None),
            ],
        ),
        (
            _SPICY,
            [
                ('Hot To Go', 'Kristen Bailey', True, 'hot-to-go'),
                ('Left of Forever', 'Tarah DeWitt', False, None),
                ('Spicy Three', 'Author P3', False, None),
                ('Spicy Four', 'Author P4', False, None),
                ('Spicy Five', 'Author P5', False, None),
                ('Spicy Six', 'Author P6', False, None),
            ],
        ),
        (
            _COMEDY,
            [
                ('Cover Story', 'Mhairi McFarlane', True, 'cover-story'),
                ('Gloves Off', 'Stephanie Archer', False, None),
                ('Comedy Three', 'Author Y3', False, None),
                ('Comedy Four', 'Author Y4', False, None),
                ('Comedy Five', 'Author Y5', False, None),
                ('Comedy Six', 'Author Y6', False, None),
            ],
        ),
        (
            _BESTSELLER,
            [
                ('An Almost Perfect Summer', 'Jill Mansell', True, 'an-almost-perfect-summer'),
                ('Say You’ll Remember Me', 'Abby Jimenez', False, None),
                ('Bestseller Three', 'Author B3', False, None),
                ('Bestseller Four', 'Author B4', False, None),
                ('Bestseller Five', 'Author B5', False, None),
                ('Bestseller Six', 'Author B6', False, None),
            ],
        ),
    ]


def _2026_shortlist_html():
    sections = []
    for heading, books in _2026_shortlist_sections():
        sections.append((heading, [(title, author, False, slug) for title, author, _win, slug in books]))
    return accordion_html(sections)


def _2026_winner_html():
    sections = []
    for heading, books in _2026_shortlist_sections():
        winner = next(book for book in books if book[2])
        sections.append((heading, [(winner[0], winner[1], True, winner[3])]))
    return accordion_html(sections)


def _2018_shortlist_html():
    return comma_list_html(
        [
            (
                'Epic Romantic Novel',
                [
                    ('This Love', 'Dani Atkins', 'Simon & Schuster'),
                    ('What Was Rescued', 'Jane Bailey', 'Lake Union Publishing'),
                ],
            ),
            (
                'Young Adult Romantic Novel',
                [
                    ('Margot and Me', 'Juno Dawson', 'Hot Key Books'),
                    ('YA Two', 'Author YA', 'Publisher'),
                ],
            ),
        ]
    )


def _2020_shortlist_html(*, truncate_popular=True):
    debut = [
        ('The Flatshare', "Beth O'Leary", 'Quercus'),
        ('Debut Two', 'Author D2', 'Publisher'),
    ]
    popular_visible = [
        ('The Flatshare', "Beth O'Leary", 'Quercus'),
        ('Popular Two', 'Author P2', 'Publisher'),
    ]
    epic = [
        (
            'The Ghost Garden',
            'Catherine Curzon and Eleanor Harkstead',
            'Publisher',
        ),
        ('Meet Me in Monaco', 'Hazel Gaynor and Heather Webb', 'Publisher'),
    ]
    popular_block = popular_visible if truncate_popular else popular_visible + [
        ('Popular Three', 'Author P3', 'Publisher'),
    ]
    return comma_list_html(
        [
            ('Debut Romantic Novel', debut),
            ('Popular Romantic Fiction', popular_block),
            ('Epic Romantic Novel', epic),
        ]
    )


def _historical_archive_cards():
    return [
        _card('More Than Friendship', 'Mary Howard', 1960, 'more-than-friendship'),
        _card(
            'The Future is Foreve',
            'Jean Innes',
            1968,
            'the-future-is-foreve',
        ),
        _card('First 1970 Winner', 'Author A', 1970, 'first-1970-winner'),
        _card('Second 1970 Winner', 'Author B', 1970, 'second-1970-winner'),
        _card(
            'Historical 1976',
            'Author Hist',
            1976,
            'historical-1976',
            category_slug='best-historical',
            category_label='Best historical',
        ),
        _card(
            'Modern 1976',
            'Author Mod',
            1976,
            'modern-1976',
            category_slug='best-modern',
            category_label='Best modern',
        ),
        _card(
            'Pillow Talk',
            'Freya North',
            2008,
            'pillow-talk',
            family='',
            families=[],
        ),
        _card(
            'This Love',
            'Dani Atkins',
            2018,
            'this-love',
            category_slug='romantic-novel-of-the-year',
            category_label='Romantic Novel of the Year',
        ),
        _card(
            'Any Trope But You',
            'Victoria Lavine',
            2026,
            'any-trope-but-you',
            category_slug='the-debut-romantic-novel-award',
            category_label='The Debut Romantic Novel Award',
        ),
        _card(
            'Finding Home in Hartfell',
            'Suzanne Snow',
            2026,
            'finding-home-in-hartfell',
            category_slug='the-contemporary-romance-novel-award',
            category_label='The Contemporary Romance Novel Award',
        ),
        _card(
            'Wooing the Witch Queen',
            'Stephanie Burgis',
            2026,
            'wooing-the-witch-queen',
            category_slug='the-romantasy-romantic-fantasy-award',
            category_label='The Romantasy/Romantic Fantasy Award',
        ),
        _card(
            'An Almost Perfect Summer',
            'Jill Mansell',
            2026,
            'an-almost-perfect-summer',
            category_slug='the-romance-bestseller-award',
            category_label='The Romance Bestseller Award',
        ),
        _card(
            'The Last Song of Winter',
            'Author One',
            2025,
            'the-last-song-of-winter',
            category_slug='the-historical-romance-award',
            category_label='The Historical Romance Award',
        ),
        _card(
            'The Wicked Lady',
            'Elena Collins',
            2025,
            'the-wicked-lady',
            category_slug='the-historical-romance-award',
            category_label='The Historical Romance Award',
        ),
        _card(
            'Mr Right Across the Street',
            'Author Comedy One',
            2022,
            'mr-right-across-the-street',
            category_slug='the-romantic-comedy-award',
            category_label='The Romantic Comedy Award',
        ),
        _card(
            'The Promise of Summer',
            'Author Comedy Two',
            2022,
            'the-promise-of-summer',
            category_slug='the-romantic-comedy-award',
            category_label='The Romantic Comedy Award',
        ),
    ]


def _excluded_archive_cards():
    return [
        _card(
            'Industry Winner Book',
            'Someone',
            2024,
            'industry-winner-book',
            family='the-rna-industry-awards',
            family_label='The RNA Industry Awards',
            category_slug='agent-of-the-year',
            category_label='Agent of the Year',
        ),
        _card(
            'Love &amp; Other Liabilities',
            'Author JHA',
            2024,
            'love-other-liabilities',
            family='joan-hessayon-award',
            family_label='The Joan Hessayon Award',
            category_slug='the-joan-hessayon-award',
            category_label='The Joan Hessayon Award',
        ),
        _card(
            'Love Rebooted',
            'Author Dual',
            2023,
            'love-rebooted',
            families=['joan-hessayon-award', RONA_FAMILY],
            category_slug='the-joan-hessayon-award',
            category_label='The Joan Hessayon Award',
        ),
        _card(
            'Jilly Cooper Tribute',
            'Jilly Cooper',
            2024,
            'jilly-cooper',
            category_slug='outstanding-achievement-award',
            category_label='Outstanding Achievement Award',
        ),
        _card(
            'Untagged Unknown',
            'Mystery Author',
            2009,
            'untagged-unknown',
            family='',
            families=[],
        ),
        _card(
            'RNA Agent of the Year Person',
            'An Agent',
            2026,
            'rna-agent-of-the-year',
            family='the-rna-industry-awards',
            category_slug='agent-of-the-year',
            category_label='Agent of the Year',
        ),
    ]


class ArchiveParserTests(unittest.TestCase):
    def test_historical_overall_winner_has_category_none(self):
        html = archive_html(
            [_card('More Than Friendship', 'Mary Howard', 1960, 'more-than-friendship')]
        )
        _parsed, records = _records_from_html(html)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].work_title, 'More Than Friendship')
        self.assertEqual(records[0].work_author, 'Mary Howard')
        self.assertEqual(records[0].award_year, 1960)
        self.assertIsNone(records[0].category)
        self.assertEqual(records[0].status, 'Winner')
        self.assertEqual(records[0].source_url, f'{ARCHIVE}/more-than-friendship')

    def test_romantic_novel_of_the_year_archive_category_is_overall(self):
        html = archive_html(
            [
                _card(
                    'This Love',
                    'Dani Atkins',
                    2018,
                    'this-love',
                    category_slug='romantic-novel-of-the-year',
                    category_label='Romantic Novel of the Year',
                )
            ]
        )
        _parsed, records = _records_from_html(html)
        self.assertIsNone(records[0].category)

    def test_best_historical_and_best_modern_preserved(self):
        html = archive_html(
            [
                _card(
                    'Historical 1976',
                    'Author Hist',
                    1976,
                    'historical-1976',
                    category_slug='best-historical',
                    category_label='Best historical',
                ),
                _card(
                    'Modern 1976',
                    'Author Mod',
                    1976,
                    'modern-1976',
                    category_slug='best-modern',
                    category_label='Best modern',
                ),
            ]
        )
        _parsed, records = _records_from_html(html)
        by_title = {record.work_title: record for record in records}
        self.assertEqual(by_title['Historical 1976'].category, 'Best historical')
        self.assertEqual(by_title['Modern 1976'].category, 'Best modern')

    def test_industry_joan_hessayon_and_outstanding_achievement_excluded(self):
        html = archive_html(_excluded_archive_cards())
        _parsed, records = _records_from_html(html)
        titles = {record.work_title for record in records}
        self.assertFalse(titles)
        self.assertNotIn('Love & Other Liabilities', titles)
        self.assertNotIn('Love Rebooted', titles)
        self.assertNotIn('Jilly Cooper Tribute', titles)

    def test_untagged_unknown_record_excluded(self):
        html = archive_html(
            [
                _card(
                    'Untagged Unknown',
                    'Mystery Author',
                    2009,
                    'untagged-unknown',
                    family='',
                    families=[],
                )
            ]
        )
        _parsed, records = _records_from_html(html)
        self.assertEqual(records, ())

    def test_pillow_talk_2008_exception_included(self):
        html = archive_html(
            [
                _card(
                    'Pillow Talk',
                    'Freya North',
                    2008,
                    'pillow-talk',
                    family='',
                    families=[],
                )
            ]
        )
        _parsed, records = _records_from_html(html)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].work_title, 'Pillow Talk')
        self.assertEqual(records[0].award_year, 2008)
        self.assertIsNone(records[0].category)
        self.assertEqual(records[0].status, 'Winner')
        self.assertEqual(records[0].source_url, f'{ARCHIVE}/pillow-talk')

    def test_truncated_1968_title_is_preserved(self):
        html = archive_html(
            [_card('The Future is Foreve', 'Jean Innes', 1968, 'the-future-is-foreve')]
        )
        _parsed, records = _records_from_html(html)
        self.assertEqual(records[0].work_title, 'The Future is Foreve')
        self.assertNotEqual(records[0].work_title, 'The Future is Forever')

    def test_multiple_uncategorized_winners_preserved(self):
        html = archive_html(
            [
                _card('First 1970 Winner', 'Author A', 1970, 'first-1970-winner'),
                _card('Second 1970 Winner', 'Author B', 1970, 'second-1970-winner'),
            ]
        )
        _parsed, records = _records_from_html(html)
        self.assertEqual(len(records), 2)
        self.assertTrue(all(record.category is None for record in records))

    def test_multiple_categorized_winners_preserved(self):
        html = archive_html(
            [
                _card(
                    'The Last Song of Winter',
                    'Author One',
                    2025,
                    'the-last-song-of-winter',
                    category_slug='the-historical-romance-award',
                    category_label='The Historical Romance Award',
                ),
                _card(
                    'The Wicked Lady',
                    'Elena Collins',
                    2025,
                    'the-wicked-lady',
                    category_slug='the-historical-romance-award',
                    category_label='The Historical Romance Award',
                ),
            ]
        )
        _parsed, records = _records_from_html(html)
        self.assertEqual(len(records), 2)
        self.assertEqual({record.work_author for record in records}, {'Author One', 'Elena Collins'})

    def test_malformed_archive_fails_closed(self):
        with self.assertRaises(src.RomanticNovelAwardsSourceError):
            src._require_archive_identity('<html><body>Random blog</body></html>')

    def test_challenge_page_fails_closed(self):
        with self.assertRaises(src.RomanticNovelAwardsSourceError):
            src._reject_challenge_or_error(
                '<html>Just a moment Cloudflare checking your browser</html>',
                ARCHIVE,
            )

    def test_wordpress_error_page_fails_closed(self):
        with self.assertRaises(src.RomanticNovelAwardsSourceError):
            src._reject_challenge_or_error(
                'There has been a critical error on this website',
                ARCHIVE,
            )

    def test_html_entities_and_exact_author_form(self):
        html = archive_html(
            [
                _card(
                    'Love &amp; Other Stories',
                    'B.K. Borison',
                    2021,
                    'love-other-stories',
                    category_slug='the-debut-romantic-novel-award',
                    category_label='The Debut Romantic Novel Award',
                )
            ]
        )
        _parsed, records = _records_from_html(html)
        self.assertEqual(records[0].work_title, 'Love & Other Stories')
        self.assertEqual(records[0].work_author, 'B.K. Borison')

    def test_relative_per_record_url_is_canonicalized(self):
        html = archive_html(
            [
                _card(
                    'More Than Friendship',
                    'Mary Howard',
                    1960,
                    'more-than-friendship',
                    relative_href=True,
                )
            ]
        )
        parsed, records = _records_from_html(html)
        self.assertEqual(records[0].source_url, f'{ARCHIVE}/more-than-friendship')
        self.assertEqual(parsed.cards[0].slug, 'more-than-friendship')

    def test_pagination_is_discovered_dynamically(self):
        page1 = archive_html(
            [_card('Book One', 'Author One', 1960, 'book-one')],
            page=1,
            of_pages=3,
        )
        parsed = src._parse_archive_page(page1)
        self.assertEqual(src._discover_archive_page_count(page1, parsed), 3)
        self.assertNotEqual(src._discover_archive_page_count(page1, parsed), 9)

    def test_publisher_is_not_part_of_work_identity(self):
        html = archive_html(
            [_card('More Than Friendship', 'Mary Howard', 1960, 'more-than-friendship', publisher='Mills & Boon')]
        )
        _parsed, records = _records_from_html(html)
        result = src._to_award_result(records[0])
        self.assertNotIn('Mills', result.source_url)
        self.assertEqual(result.identity_kind, 'work')
        self.assertNotIn('publisher', src._record_to_cache_dict(records[0]))


class NewsIndexTests(unittest.TestCase):
    def test_taxonomy_discovered_by_slug_not_hardcoded_id(self):
        seen = []

        def fetch_json(url):
            seen.append(url)
            self.assertIn(f'slug={src.NEWS_CATEGORY_SLUG}', url)
            self.assertNotIn('497', url)
            return _taxonomy_payload(812)

        with patch.object(src, '_fetch_json', side_effect=fetch_json):
            self.assertEqual(src._discover_news_category_id(), 812)
        self.assertTrue(seen)

    def test_news_rest_paginates_without_embed(self):
        pages = []

        def fetch_json(url):
            pages.append(url)
            self.assertIn('_fields=id,date,slug,link,title', url)
            self.assertNotIn('_embed', url)
            parsed = urllib.parse.urlparse(url)
            page = int(urllib.parse.parse_qs(parsed.query).get('page', ['1'])[0])
            if page == 1:
                return [
                    _news_item(
                        index,
                        'RNA reveals 2026 shortlists',
                        'rna-reveals-2026-shortlists',
                        '2026-02-01T00:00:00',
                        2026,
                    )
                    for index in range(1, 101)
                ]
            if page == 2:
                return [
                    _news_item(
                        101,
                        'RNA announces the 2026 winners',
                        'rna-announces-the-2026-winners',
                        '2026-03-01T00:00:00',
                        2026,
                    )
                ]
            raise AssertionError(url)

        with patch.object(src, '_fetch_json', side_effect=fetch_json):
            posts = src._enumerate_news_posts(812)
        self.assertEqual(len(pages), 2)
        self.assertEqual(len(posts), 101)

    def test_duplicate_rest_post_ids_are_deduped(self):
        item = _news_item(
            9,
            'RNA reveals 2026 shortlists',
            'rna-reveals-2026-shortlists',
            '2026-02-01T00:00:00',
            2026,
        )
        with patch.object(src, '_fetch_json', return_value=[item, dict(item)]):
            posts = src._enumerate_news_posts(812)
        self.assertEqual(len(posts), 1)

    def test_shortlist_and_finalist_and_winner_classification(self):
        shortlist = src._classify_news_post(
            post_id=1,
            title='RNA reveals 2026 shortlists',
            slug='rna-reveals-2026-shortlists',
            url=SHORTLIST_2026,
            date='2026-02-01',
        )
        finalist = src._classify_news_post(
            post_id=2,
            title='2020 RoNA Finalists announced',
            slug='2020-rona-finalists-announced',
            url=SITE + '/news/2020-rona-finalists-announced/',
            date='2020-02-01',
        )
        winner = src._classify_news_post(
            post_id=3,
            title='RNA announces the 2026 winners',
            slug='rna-announces-the-2026-winners',
            url=WINNERS_2026,
            date='2026-03-01',
        )
        self.assertEqual(shortlist.kind, 'shortlist')
        self.assertEqual(finalist.kind, 'shortlist')
        self.assertEqual(winner.kind, 'winner')
        self.assertTrue(shortlist.combined)
        self.assertTrue(winner.combined)

    def test_entry_marketing_and_profile_posts_are_ignored(self):
        ignored = [
            ('Entries now open for the 2027 awards', 'entries-open-2027'),
            ('Marketing tips for romantic novelists', 'marketing-tips'),
            ('Register as a judge', 'register-as-a-judge'),
            ('Meet the finalist: an author profile', 'meet-the-finalist-profile'),
            ('The 2027 categories explained', '2027-categories-explained'),
            ('Elizabeth Goudge Trophy winner announced', 'elizabeth-goudge-trophy'),
            ('Joan Hessayon Award winner', 'joan-hessayon-award-winner'),
            ('RNA Agent of the Year shortlist', 'agent-of-the-year-shortlist'),
        ]
        for title, slug in ignored:
            self.assertIsNone(
                src._classify_news_post(
                    post_id=1,
                    title=title,
                    slug=slug,
                    url=f'{SITE}/news/{slug}/',
                    date='2026-01-01',
                ),
                title,
            )

    def test_malformed_rest_index_fails_closed(self):
        with patch.object(src, '_fetch_json', return_value={'not': 'a list'}):
            with self.assertRaises(src.RomanticNovelAwardsSourceError):
                src._enumerate_news_posts(812)
        with patch.object(src, '_fetch_json', return_value=[]):
            with self.assertRaises(src.RomanticNovelAwardsSourceError):
                src._discover_news_category_id()


class ShortlistParserTests(unittest.TestCase):
    def test_2018_comma_list_shortlisted_status_and_rank_none(self):
        records = src._parse_announcement_html(
            _2018_shortlist_html(),
            source_url=SHORTLIST_2018,
            award_year=2018,
            default_status='Shortlisted',
        )
        by_title = {record.work_title: record for record in records}
        self.assertEqual(by_title['This Love'].status, 'Shortlisted')
        self.assertEqual(by_title['This Love'].category, 'Epic Romantic Novel')
        self.assertEqual(by_title['Margot and Me'].category, 'Young Adult Romantic Novel')
        result = src._to_award_result(by_title['This Love'])
        self.assertIsNone(result.rank)
        self.assertEqual(result.status, 'Shortlisted')

    def test_finalist_wording_normalizes_to_shortlisted(self):
        html = comma_list_html(
            [('Debut Romantic Novel', [('The Flatshare', "Beth O'Leary", 'Quercus')])],
            intro='The 2020 RoNA Finalists',
        )
        records = src._parse_announcement_html(
            html,
            source_url=SHORTLIST_2020,
            award_year=2020,
            default_status='Shortlisted',
        )
        self.assertEqual(records[0].status, 'Shortlisted')
        self.assertNotEqual(records[0].status, 'Finalist')

    def test_multiple_accordion_sections_are_all_parsed(self):
        html = (
            '<html><body>'
            '<section class="accordion">'
            '<h2>Debut Romance Novel Award</h2>'
            '<h3>Any Trope But You by Victoria Lavine</h3>'
            '</section>'
            '<section class="accordion">'
            '<h2>Romantasy/Romantic Fantasy Award</h2>'
            '<h3>Onyx Storm by Rebecca Yarros</h3>'
            '</section>'
            '</body></html>'
        )
        records = src._parse_announcement_html(
            html,
            source_url=SHORTLIST_2026,
            award_year=2026,
            default_status='Shortlisted',
        )
        by_title = {record.work_title: record for record in records}
        self.assertEqual(by_title['Any Trope But You'].category, _DEBUT)
        self.assertEqual(by_title['Onyx Storm'].category, _ROMANTASY)
        self.assertEqual(by_title['Onyx Storm'].status, 'Shortlisted')

    def test_list_order_is_not_rank(self):
        records = src._parse_announcement_html(
            _2026_shortlist_html(),
            source_url=SHORTLIST_2026,
            award_year=2026,
            default_status='Shortlisted',
        )
        debut = [record for record in records if record.category == _DEBUT]
        romantasy = [record for record in records if record.category == _ROMANTASY]
        self.assertEqual(len(debut), 6)
        self.assertEqual(len(romantasy), 7)
        for record in debut + romantasy:
            self.assertEqual(record.status, 'Shortlisted')
            self.assertIsNone(src._to_award_result(record).rank)

    def test_winner_accordion_does_not_promote_the_rest_of_the_slate(self):
        html = accordion_html(
            [
                (
                    _DEBUT,
                    [
                        ('Any Trope But You', 'Victoria Lavine', True, 'any-trope-but-you'),
                        ('To Hell With It', 'Claire Frances', False, None),
                    ],
                )
            ]
        )
        records = src._parse_announcement_html(
            html,
            source_url=WINNERS_2026,
            award_year=2026,
            default_status='Shortlisted',
        )
        by_title = {record.work_title: record for record in records}
        self.assertEqual(by_title['Any Trope But You'].status, 'Winner')
        self.assertEqual(by_title['To Hell With It'].status, 'Shortlisted')

    def test_coauthors_preserved_as_one_credit(self):
        records = src._parse_announcement_html(
            _2020_shortlist_html(),
            source_url=SHORTLIST_2020,
            award_year=2020,
            default_status='Shortlisted',
        )
        by_title = {record.work_title: record for record in records}
        self.assertEqual(
            by_title['The Ghost Garden'].work_author,
            'Catherine Curzon and Eleanor Harkstead',
        )
        self.assertEqual(
            by_title['Meet Me in Monaco'].work_author,
            'Hazel Gaynor and Heather Webb',
        )
        credits = [record.work_author for record in records if record.work_title == 'The Ghost Garden']
        self.assertEqual(len(credits), 1)

    def test_2020_truncated_popular_emits_only_visible_facts(self):
        records = src._parse_announcement_html(
            _2020_shortlist_html(truncate_popular=True),
            source_url=SHORTLIST_2020,
            award_year=2020,
            default_status='Shortlisted',
        )
        popular = [record for record in records if 'Popular' in (record.category or '')]
        self.assertEqual(len(popular), 2)
        self.assertTrue(any(record.work_title == 'The Flatshare' for record in popular))
        debut = [record for record in records if 'Debut' in (record.category or '')]
        self.assertTrue(debut)


class LookupIntegrationTests(unittest.TestCase):
    def setUp(self):
        src._reset_runtime_state()
        cache._reset_runtime_state()
        self._temp = TemporaryDirectory()
        cache.set_cache_directory(Path(self._temp.name))

    def tearDown(self):
        src._reset_runtime_state()
        cache._reset_runtime_state()
        cache.set_cache_directory(None)
        self._temp.cleanup()

    def _pages(self):
        archive_cards = _historical_archive_cards() + _excluded_archive_cards()
        pages = {
            ARCHIVE: archive_html(archive_cards, page=1, of_pages=2),
            f'{ARCHIVE}/page/2/': archive_html(
                [
                    _card(
                        'Fantasy Historical',
                        'Author Fantasy',
                        2019,
                        'fantasy-historical',
                        category_slug='the-fantasy-romantic-novel-award',
                        category_label='The Fantasy Romantic Novel Award',
                    )
                ],
                page=2,
                of_pages=2,
            ),
            SHORTLIST_2026: _2026_shortlist_html(),
            WINNERS_2026: _2026_winner_html(),
            SHORTLIST_2018: _2018_shortlist_html(),
            SHORTLIST_2020: _2020_shortlist_html(),
            WINNERS_2020: winner_list_html(
                [
                    ('Debut Romantic Novel', [('The Flatshare', "Beth O'Leary")]),
                    ('Popular Romantic Fiction', [('The Flatshare', "Beth O'Leary")]),
                ]
            ),
            WINNERS_2022: winner_marked_html(
                [
                    (
                        'The Romantic Comedy Award',
                        [
                            ('Mr Right Across the Street', 'Author Comedy One'),
                            ('The Promise of Summer', 'Author Comedy Two'),
                        ],
                    )
                ]
            ),
            WINNERS_2025: winner_marked_html(
                [
                    (
                        'The Historical Romance Award',
                        [
                            ('The Last Song of Winter', 'Author One'),
                            ('The Wicked Lady', 'Elena Collins (Judy Leigh)'),
                        ],
                    )
                ]
            ),
            SHORTLIST_2019: comma_list_html(
                [
                    (
                        'The Fantasy Romantic Novel Award',
                        [('Fantasy Historical', 'Author Fantasy', 'Publisher')],
                    )
                ]
            ),
        }
        return pages

    def _news_posts(self):
        return [
            _news_item(1, 'RNA reveals 2026 shortlists', 'rna-reveals-2026-shortlists', '2026-02-01', 2026),
            _news_item(2, 'RNA announces the 2026 winners', 'rna-announces-the-2026-winners', '2026-03-01', 2026),
            _news_item(3, '2018 RoNA shortlists announced', '2018-rona-shortlists-announced', '2018-02-01', 2018),
            _news_item(4, 'RNA announces 2020 shortlists', 'rna-announces-2020-shortlists', '2020-02-01', 2020),
            _news_item(5, 'RNA announces the 2020 winners', 'rna-announces-the-2020-winners', '2020-03-01', 2020),
            _news_item(6, 'RNA announces the 2022 winners', 'rna-announces-the-2022-winners', '2022-03-01', 2022),
            _news_item(7, 'RNA announces the 2025 winners', 'rna-announces-the-2025-winners', '2025-03-01', 2025),
            _news_item(8, '2019 RoNA shortlists announced', '2019-rona-shortlists-announced', '2019-02-01', 2019),
            _news_item(9, 'Entries now open for 2027', 'entries-open-2027', '2026-09-01', 2027),
            _news_item(10, 'Marketing tips for authors', 'marketing-tips', '2026-01-01', 2026),
        ]

    def _fetch_html(self, url):
        pages = self._pages()
        if url not in pages:
            raise src.RomanticNovelAwardsSourceError(f'missing {url}')
        return pages[url]

    def _fetch_json(self, url):
        if '/news_categories' in url:
            self.assertIn(f'slug={src.NEWS_CATEGORY_SLUG}', url)
            return _taxonomy_payload(NEWS_CAT_ID)
        if '/wp-json/wp/v2/news' in url:
            self.assertNotIn('_embed', url)
            self.assertIn(f'news_categories={NEWS_CAT_ID}', url)
            return self._news_posts()
        raise AssertionError(url)

    def _lookup(self, title, author):
        with patch.object(src, '_fetch_html', side_effect=self._fetch_html), patch.object(
            src, '_fetch_json', side_effect=self._fetch_json
        ), patch.object(src, '_current_calendar_year', return_value=2026):
            return src.lookup(title, author)

    def test_2026_winners_use_announcement_category_wording(self):
        result = self._lookup('Any Trope But You', 'Victoria Lavine')[0]
        self.assertEqual(result.status, 'Winner')
        self.assertEqual(result.category, _DEBUT)
        self.assertNotEqual(result.category, 'The Debut Romantic Novel Award')
        self.assertEqual(result.award_year, 2026)
        self.assertIsNone(result.rank)

    def test_2026_all_eleven_category_winners(self):
        expected = [
            ('Any Trope But You', 'Victoria Lavine', _DEBUT),
            ('Wooing the Witch Queen', 'Stephanie Burgis', _ROMANTASY),
            ('He’s To Die For', 'Erin Dunn', _THRILLER),
            ('Christmas Fling', 'Lindsey Kelk', _FESTIVE),
            ('Filthy Rich Temptation', 'Rachael Stewart', _SHORTER),
            ('The Lost Diamond', 'Kathleen McGurl', _SAGA),
            ('The Earl’s Unlikely Bride', 'Ella Matthews', _HISTORICAL),
            ('Finding Home in Hartfell', 'Suzanne Snow', _CONTEMPORARY),
            ('Hot To Go', 'Kristen Bailey', _SPICY),
            ('Cover Story', 'Mhairi McFarlane', _COMEDY),
            ('An Almost Perfect Summer', 'Jill Mansell', _BESTSELLER),
        ]
        for title, author, category in expected:
            with self.subTest(title=title):
                results = self._lookup(title, author)
                winners = [item for item in results if item.status == 'Winner']
                self.assertEqual(len(winners), 1)
                self.assertEqual(winners[0].category, category)
                self.assertEqual(winners[0].award_year, 2026)

    def test_2026_nonwinning_shortlisted_qualify(self):
        examples = [
            ('To Hell With It', 'Claire Frances', _DEBUT),
            ('Onyx Storm', 'Rebecca Yarros', _ROMANTASY),
            ('The Greek House', 'Dinah Jefferies', _THRILLER),
            ('Just a Taste', 'Anise Starre', _FESTIVE),
            ('Greek’s Kidnapped Princess', 'Heidi Rice', _SHORTER),
            ('New Horizons for the Woolworth Girls', 'Elaine Everest', _SAGA),
            ('The Maid’s Masquerade', 'Catherine Tinley', _HISTORICAL),
            ('First-Time Caller', 'B.K. Borison', _CONTEMPORARY),
            ('Left of Forever', 'Tarah DeWitt', _SPICY),
            ('Gloves Off', 'Stephanie Archer', _COMEDY),
            ('Say You’ll Remember Me', 'Abby Jimenez', _BESTSELLER),
        ]
        for title, author, category in examples:
            with self.subTest(title=title):
                results = self._lookup(title, author)
                self.assertTrue(results)
                item = results[0]
                self.assertEqual(item.status, 'Shortlisted')
                self.assertEqual(item.category, category)
                self.assertIsNone(item.rank)
                assessed = assess_award_result(item)
                self.assertEqual(
                    assessed.qualification.decision,
                    QualificationDecision.QUALIFIES,
                )
                self.assertEqual(item.source_url, SHORTLIST_2026)

    def test_2018_this_love_dual_honor_and_no_invented_winners(self):
        results = self._lookup('This Love', 'Dani Atkins')
        statuses = {(item.status, item.category) for item in results}
        self.assertIn(('Winner', None), statuses)
        self.assertIn(('Shortlisted', 'Epic Romantic Novel'), statuses)
        self.assertEqual(len(results), 2)
        ya = self._lookup('Margot and Me', 'Juno Dawson')
        self.assertEqual(len(ya), 1)
        self.assertEqual(ya[0].status, 'Shortlisted')
        self.assertEqual(ya[0].category, 'Young Adult Romantic Novel')

    def test_2020_flatshare_cross_category_and_coauthors(self):
        results = self._lookup('The Flatshare', "Beth O'Leary")
        categories = {item.category for item in results}
        self.assertGreaterEqual(len(results), 2)
        self.assertTrue(any('Debut' in (category or '') for category in categories))
        self.assertTrue(any('Popular' in (category or '') for category in categories))
        garden = self._lookup('The Ghost Garden', 'Catherine Curzon and Eleanor Harkstead')
        self.assertEqual(len(garden), 1)
        self.assertIn('and', garden[0].work_author)

    def test_multiple_winners_survive(self):
        comedy_one = self._lookup('Mr Right Across the Street', 'Author Comedy One')
        comedy_two = self._lookup('The Promise of Summer', 'Author Comedy Two')
        self.assertEqual(comedy_one[0].status, 'Winner')
        self.assertEqual(comedy_two[0].status, 'Winner')
        self.assertIsNone(comedy_one[0].rank)
        hist_one = self._lookup('The Last Song of Winter', 'Author One')
        hist_two = self._lookup('The Wicked Lady', 'Elena Collins')
        self.assertEqual(hist_one[0].status, 'Winner')
        self.assertEqual(hist_two[0].status, 'Winner')
        self.assertEqual(hist_two[0].work_author, 'Elena Collins')
        self.assertNotIn('Judy Leigh', hist_two[0].work_author)
        self.assertFalse(self._lookup('The Wicked Lady', 'Judy Leigh'))

    def test_historical_winner_and_fantasy_wording(self):
        historical = self._lookup('More Than Friendship', 'Mary Howard')
        self.assertEqual(historical[0].status, 'Winner')
        self.assertIsNone(historical[0].category)
        self.assertEqual(historical[0].award_year, 1960)
        fantasy = self._lookup('Fantasy Historical', 'Author Fantasy')
        self.assertTrue(fantasy)
        self.assertIn('Fantasy', fantasy[0].category)
        self.assertNotIn('Romantasy', fantasy[0].category or '')

    def test_2026_contemporary_is_not_rewritten_to_fade_to_black(self):
        result = self._lookup('Finding Home in Hartfell', 'Suzanne Snow')[0]
        self.assertEqual(result.category, _CONTEMPORARY)
        self.assertNotIn('Fade-to-Black', result.category)

    def test_2026_romantasy_wording_preserved(self):
        result = self._lookup('Wooing the Witch Queen', 'Stephanie Burgis')[0]
        self.assertEqual(result.category, _ROMANTASY)

    def test_negative_lookups(self):
        self.assertEqual(self._lookup('Love & Other Liabilities', 'Author JHA'), [])
        self.assertEqual(self._lookup('Jilly Cooper Tribute', 'Jilly Cooper'), [])
        self.assertEqual(self._lookup('RNA Agent of the Year Person', 'An Agent'), [])
        self.assertEqual(self._lookup('Untagged Unknown', 'Mystery Author'), [])

    def test_award_result_schema(self):
        result = self._lookup('More Than Friendship', 'Mary Howard')[0]
        self.assertEqual(result.award_name, src.AWARD_NAME)
        self.assertEqual(result.source_name, src.SOURCE_NAME)
        self.assertEqual(result.identity_kind, 'work')
        self.assertIsNone(result.rank)
        self.assertTrue(result.source_url.startswith(ARCHIVE))


class PolicyTests(unittest.TestCase):
    def test_rona_shortlist_policy(self):
        result = src._to_award_result(
            src._ParsedRecord(
                award_year=2026,
                category=_ROMANTASY,
                status='Shortlisted',
                work_title='Onyx Storm',
                work_author='Rebecca Yarros',
                source_url=SHORTLIST_2026,
            )
        )
        hugo_nominee = AwardResult(
            work_title='The Graveyard Book',
            work_author='Neil Gaiman',
            award_name='Hugo Award',
            award_year=2009,
            category='Best Novel',
            status='Nominee',
            rank=None,
            source_name='The Hugo Awards',
            source_url='https://www.thehugoawards.org/hugo-history/2009-hugo-awards/',
        )
        booker_shortlisted = AwardResult(
            work_title='Empire of the Sun',
            work_author='J. G. Ballard',
            award_name='Booker Prize',
            award_year=1984,
            category='Fiction',
            status='Shortlisted',
            rank=None,
            source_name='The Booker Prize',
            source_url='https://thebookerprizes.com/the-booker-library/books/empire-of-the-sun',
        )
        self.assertIs(find_award_policy(result), RONA_SHORTLIST_POLICY)
        self.assertEqual(
            RONA_SHORTLIST_POLICY.qualifying_statuses,
            frozenset({'shortlisted'}),
        )
        self.assertEqual(RONA_SHORTLIST_POLICY.start_year, 2018)
        self.assertEqual(RONA_SHORTLIST_POLICY.award_name, src.AWARD_NAME)
        self.assertIsNone(RONA_SHORTLIST_POLICY.category)
        self.assertEqual(
            assess_award_result(result).qualification.decision,
            QualificationDecision.QUALIFIES,
        )
        pre_era = src._to_award_result(
            src._ParsedRecord(
                award_year=2017,
                category=None,
                status='Shortlisted',
                work_title='Imaginary',
                work_author='Nobody',
                source_url=src.SOURCE_HOME_URL,
            )
        )
        self.assertIsNone(find_award_policy(pre_era))
        self.assertIsNot(find_award_policy(booker_shortlisted), RONA_SHORTLIST_POLICY)
        self.assertIsNone(find_award_policy(hugo_nominee))


class CategoryAliasTests(unittest.TestCase):
    def test_aliases_are_source_local_and_matching_only(self):
        self.assertTrue(
            src._categories_equivalent(
                'The Debut Romantic Novel Award',
                'Debut Romance Novel Award',
            )
        )
        self.assertFalse(
            src._categories_equivalent(
                'The Fantasy Romantic Novel Award',
                'Romantasy/Romantic Fantasy Award',
            )
        )
        self.assertFalse(
            src._categories_equivalent(
                'The Contemporary Romance Novel Award',
                'The Contemporary Fade-to-Black Romance Award',
            )
        )
        self.assertFalse(
            src._categories_equivalent(
                'The Popular Romantic Fiction Award',
                'The Romance Bestseller Award',
            )
        )

    def test_elena_collins_match_only_alias_is_title_scoped(self):
        wicked = src._ParsedRecord(
            award_year=2025,
            category='The Historical Romance Award',
            status='Winner',
            work_title='The Wicked Lady',
            work_author='Elena Collins',
            source_url=f'{ARCHIVE}/the-wicked-lady',
        )
        self.assertTrue(
            src._record_matches(wicked, 'The Wicked Lady', 'Elena Collins (Judy Leigh)')
        )
        other = src._ParsedRecord(
            award_year=2025,
            category='The Historical Romance Award',
            status='Shortlisted',
            work_title='Example Title',
            work_author='Example Author (Some Distinction)',
            source_url=SHORTLIST_2019,
        )
        self.assertFalse(
            src._record_matches(other, 'Example Title', 'Example Author')
        )
        self.assertTrue(
            src._record_matches(
                other, 'Example Title', 'Example Author (Some Distinction)'
            )
        )


class HardeningRegressionTests(unittest.TestCase):
    def test_production_shaped_2023_page_title_is_never_a_category(self):
        heading = "ROMANTIC NOVELISTS' ASSOCIATION ROMANTIC NOVEL AWARDS 2023"
        html = (
            '<!DOCTYPE html><html><body>'
            f'<h1>{heading}</h1>'
            '<h2>The Historical Romance Award</h2>'
            '<p>The Forgotten Village by Lorna Cook</p>'
            '</body></html>'
        )
        records = src._parse_announcement_html(
            html,
            source_url=SITE + '/news/rna-announces-the-2023-winners/',
            award_year=2023,
            default_status='Shortlisted',
        )
        categories = {record.category for record in records}
        self.assertNotIn(heading, categories)
        self.assertFalse(
            any(
                'romantic novelists' in (category or '').casefold()
                for category in categories
            )
        )
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].work_title, 'The Forgotten Village')
        self.assertEqual(records[0].work_author, 'Lorna Cook')
        self.assertEqual(records[0].category, 'The Historical Romance Award')

    def test_unrelated_author_parenthetical_is_preserved(self):
        html = comma_list_html(
            [
                (
                    'The Historical Romance Award',
                    [
                        (
                            'Example Title',
                            'Example Author (Some Distinction)',
                            'Publisher',
                        )
                    ],
                )
            ]
        )
        records = src._parse_announcement_html(
            html,
            source_url=SHORTLIST_2019,
            award_year=2019,
            default_status='Shortlisted',
        )
        self.assertEqual(len(records), 1)
        self.assertEqual(
            records[0].work_author,
            'Example Author (Some Distinction)',
        )
        self.assertNotEqual(records[0].work_author, 'Example Author')

    def test_title_author_inversion_is_not_parsed(self):
        parsed = src._parse_title_author_line('Lorna Cook, The Forgotten Village')
        self.assertIsNone(parsed)
        parsed = src._parse_title_author_line(
            'The Forgotten Village by Lorna Cook'
        )
        self.assertEqual(parsed, ('The Forgotten Village', 'Lorna Cook'))

    def _overlay_pages(self, pages):
        def fetch_html(url):
            if url not in pages:
                raise src.RomanticNovelAwardsSourceError(f'missing {url}')
            return pages[url]
        return fetch_html

    def test_unstructured_winner_press_does_not_invent_winners(self):
        shortlist_url = SITE + '/news/2023-rona-shortlists-announced/'
        winner_url = SITE + '/news/rna-announces-the-2023-winners/'
        pages = {
            shortlist_url: comma_list_html(
                [
                    (
                        'The Historical Romance Award',
                        [
                            ('The Forgotten Village', 'Lorna Cook', 'Publisher'),
                            ('Another Historical', 'Other Author', 'Publisher'),
                        ],
                    )
                ]
            ),
            winner_url: _unstructured_2023_winner_html(),
        }
        archive = (
            src._ParsedRecord(
                award_year=2023,
                category='The Historical Romance Award',
                status='Winner',
                work_title='The Forgotten Village',
                work_author='Lorna Cook',
                source_url=f'{ARCHIVE}/the-forgotten-village',
            ),
        )
        with patch.object(src, '_fetch_html', side_effect=self._overlay_pages(pages)):
            snapshot = src._parse_year_pages(
                2023,
                [shortlist_url],
                [winner_url],
                archive,
            )
        results = snapshot.records
        categories = {record.category for record in results}
        titles = {record.work_title for record in results}
        authors = {record.work_author for record in results}
        self.assertNotIn(
            "ROMANTIC NOVELISTS' ASSOCIATION ROMANTIC NOVEL AWARDS 2023",
            categories,
        )
        self.assertFalse(
            any('romantic novelists' in (category or '').casefold() for category in categories)
        )
        self.assertNotIn('Jackie Collins', titles)
        self.assertNotIn('Jackie Collins', authors)
        self.assertFalse(any('ProWritingAid' in title for title in titles))
        self.assertFalse(any('ProWritingAid' in author for author in authors))
        self.assertNotIn('Lorna Cook', titles)
        winners = [record for record in results if record.status == 'Winner']
        self.assertEqual(len(winners), 1)
        self.assertEqual(winners[0].work_title, 'The Forgotten Village')
        self.assertEqual(winners[0].work_author, 'Lorna Cook')
        self.assertEqual(winners[0].category, 'The Historical Romance Award')
        self.assertTrue(winners[0].source_url.startswith(ARCHIVE))
        shortlisted = [
            record for record in results if record.work_title == 'Another Historical'
        ]
        self.assertEqual(len(shortlisted), 1)
        self.assertEqual(shortlisted[0].status, 'Shortlisted')

    def test_archive_missing_winner_without_strong_marker_stays_absent(self):
        shortlist_url = SITE + '/news/2021-rona-shortlists-announced/'
        winner_url = SITE + '/news/rna-announces-the-2021-winners/'
        pages = {
            shortlist_url: comma_list_html(
                [
                    (
                        'The Historical Romance Award',
                        [('Missing Historical', 'Some Author', 'Publisher')],
                    )
                ]
            ),
            winner_url: winner_list_html(
                [
                    (
                        'The Historical Romance Award',
                        [('Missing Historical', 'Some Author')],
                    )
                ]
            ),
        }
        with patch.object(src, '_fetch_html', side_effect=self._overlay_pages(pages)):
            snapshot = src._parse_year_pages(2021, [shortlist_url], [winner_url], ())
        self.assertEqual(len(snapshot.records), 1)
        self.assertEqual(snapshot.records[0].work_title, 'Missing Historical')
        self.assertEqual(snapshot.records[0].status, 'Shortlisted')

    def test_strong_winner_marker_may_establish_archive_missing_winner(self):
        shortlist_url = SITE + '/news/2021-rona-shortlists-announced/'
        winner_url = SITE + '/news/rna-announces-the-2021-winners/'
        pages = {
            shortlist_url: comma_list_html(
                [
                    (
                        'The Historical Romance Award',
                        [('Missing Historical', 'Some Author', 'Publisher')],
                    )
                ]
            ),
            winner_url: winner_marked_html(
                [
                    (
                        'The Historical Romance Award',
                        [('Missing Historical', 'Some Author')],
                    )
                ]
            ),
        }
        with patch.object(src, '_fetch_html', side_effect=self._overlay_pages(pages)):
            snapshot = src._parse_year_pages(2021, [shortlist_url], [winner_url], ())
        self.assertEqual(snapshot.records[0].status, 'Winner')
        self.assertEqual(snapshot.records[0].work_title, 'Missing Historical')
        self.assertEqual(snapshot.records[0].category, 'The Historical Romance Award')

    def test_winner_page_title_heading_cannot_create_category_winner(self):
        shortlist_url = SITE + '/news/2023-rona-shortlists-announced/'
        winner_url = SITE + '/news/rna-announces-the-2023-winners/'
        heading = "ROMANTIC NOVELISTS' ASSOCIATION ROMANTIC NOVEL AWARDS 2023"
        pages = {
            shortlist_url: comma_list_html(
                [
                    (
                        'The Historical Romance Award',
                        [('The Forgotten Village', 'Lorna Cook', 'Publisher')],
                    )
                ]
            ),
            winner_url: (
                '<!DOCTYPE html><html><body>'
                f'<h1>{heading}</h1>'
                f'<p>WINNER: Bogus Title by Bogus Author</p>'
                '</body></html>'
            ),
        }
        with patch.object(src, '_fetch_html', side_effect=self._overlay_pages(pages)):
            snapshot = src._parse_year_pages(2023, [shortlist_url], [winner_url], ())
        self.assertFalse(
            any(
                (record.category or '').casefold() == heading.casefold()
                for record in snapshot.records
            )
        )
        self.assertFalse(
            any(record.work_title == 'Bogus Title' for record in snapshot.records)
        )

    def test_elena_collins_archive_identity_wins_over_announcement_parenthetical(self):
        shortlist_url = SITE + '/news/2025-rona-shortlists-announced/'
        winner_url = WINNERS_2025
        pages = {
            shortlist_url: comma_list_html(
                [
                    (
                        'The Historical Romance Award',
                        [
                            ('The Last Song of Winter', 'Author One', 'Publisher'),
                            (
                                'The Wicked Lady',
                                'Elena Collins (Judy Leigh)',
                                'Publisher',
                            ),
                        ],
                    )
                ]
            ),
            winner_url: winner_marked_html(
                [
                    (
                        'The Historical Romance Award',
                        [
                            ('The Last Song of Winter', 'Author One'),
                            ('The Wicked Lady', 'Elena Collins (Judy Leigh)'),
                        ],
                    )
                ]
            ),
        }
        archive = (
            src._ParsedRecord(
                award_year=2025,
                category='The Historical Romance Award',
                status='Winner',
                work_title='The Last Song of Winter',
                work_author='Author One',
                source_url=f'{ARCHIVE}/the-last-song-of-winter',
            ),
            src._ParsedRecord(
                award_year=2025,
                category='The Historical Romance Award',
                status='Winner',
                work_title='The Wicked Lady',
                work_author='Elena Collins',
                source_url=f'{ARCHIVE}/the-wicked-lady',
            ),
        )
        with patch.object(src, '_fetch_html', side_effect=self._overlay_pages(pages)):
            snapshot = src._parse_year_pages(
                2025,
                [shortlist_url],
                [winner_url],
                archive,
            )
        wicked = [
            record for record in snapshot.records
            if record.work_title == 'The Wicked Lady'
        ]
        self.assertEqual(len(wicked), 1)
        self.assertEqual(wicked[0].status, 'Winner')
        self.assertEqual(wicked[0].work_author, 'Elena Collins')
        self.assertNotIn('Judy Leigh', wicked[0].work_author)
        self.assertFalse(
            any(record.work_author == 'Judy Leigh' for record in snapshot.records)
        )


if __name__ == '__main__':
    unittest.main()
