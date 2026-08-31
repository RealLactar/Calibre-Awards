"""Offline coverage for PEN/Hemingway Award for Debut Novel parsers."""

from __future__ import annotations

import json
import unittest

from awards.engine import assess_award_result
from awards.qualifier import QualificationDecision
from awards.sources import pen_hemingway as ph


def _landing_url() -> str:
    return ph.SOURCE_HOME_URL


def _winner_url(year: int) -> str:
    return ph.VERIFIED_YEAR_URLS[year]['winner']


def _finalists_url(year: int) -> str:
    return ph.VERIFIED_YEAR_URLS[year]['finalists']


def _article(title: str, body: str) -> str:
    return (
        '<html><head>'
        f'<title>{title} | The PEN/Faulkner Foundation</title>'
        '</head><body>'
        f'<div class="entry-content">{body}</div>'
        '</body></html>'
    )


_SPECIAL_YEARS = {
    1976: ('Parthian Shot', 'Loyd Little'),
    1978: ('A Way of Life, Like Any Other', 'Darcy O’Brien'),
    1982: ('Housekeeping', 'Marilynne Robinson'),
    1983: ('Shiloh and Other Stories', 'Bobbie Ann Mason'),
    1990: ('The Ice at the Bottom of the World', 'Mark Richard'),
    1994: ('The Magic of Blood', 'Dagobert Gilb'),
    1996: ('Native Speaker', 'Chang-rae Lee'),
    1999: ('Homestead', 'Rosina Lipini'),
    2000: ('Interpreter of Maladies', 'Jhumpa Lahiri'),
    2002: ('Mary and O’Neil', 'Justin Cronin'),
    2003: ('The Curious Case of Benjamin Button, Apt. 3W', 'George Brownstein'),
    2010: ('A Long Long Time Ago and Essentially True', 'Brigid Pasulka'),
    2013: ('The Yellow Birds', 'Kevin Powers'),
    2019: ('There There', 'Tommy Orange'),
    2020: ('A Prayer for Travelers', 'Ruchika Tomar'),
    2021: ('Sharks in the Time of Saviors: A Novel', 'Kawai Strong Washburn'),
    2023: ('Calling For a Blanket Dance', 'Oscar Hokeah'),
    2025: ('Early Sobrieties', 'Michael Deagler'),
}


def _default_year(year: int) -> tuple[str, str]:
    return (f'Winner Title {year}', f'Winner Author {year}')


def _winner_paragraph(year: int, title: str, author: str, *, wrapped: bool = False) -> str:
    inner = f'<strong>{year} </strong><em>{title}</em> by {author}'
    if wrapped:
        inner = f'<span>{inner}</span>'
    return f'<p>{inner}</p>'


def _historical_landing(*, skip_year: int | None = None, extra: str = '', trailer: str = '') -> str:
    blocks = [extra, '<h3>Past Winners</h3>']
    for year in range(ph.ARCHIVE_MIN_YEAR, ph.HISTORICAL_ARCHIVE_MAX_YEAR + 1):
        if year == skip_year:
            continue
        if year in _SPECIAL_YEARS:
            title, author = _SPECIAL_YEARS[year]
        else:
            title, author = _default_year(year)
        wrapped = year == 2021
        blocks.append(_winner_paragraph(year, title, author, wrapped=wrapped))
        if year == 2009:
            blocks.append('<p></p>')
    blocks.append(trailer)
    return (
        '<html><head><title>The PEN/Hemingway Award | '
        'The PEN/Faulkner Foundation</title></head>'
        '<body><div class="entry-content">'
        '<h2>The PEN/Hemingway Award for Debut Novel</h2>'
        f'{"".join(blocks)}</div></body></html>'
    )


_PAIRS_2026 = [
    ('The Correspondent', 'Virginia Evans', 'Crown'),
    ('Awake in the Floating City', 'Susanna Kwan', 'Pantheon'),
    ('Blob', 'Maggie Su', 'Harper'),
]


def _finalists_article(year: int, pairs: list[tuple[str, str, str]]) -> str:
    items = ''.join(
        f'<li>{title} by {author} ({publisher})</li>'
        for title, author, publisher in pairs
    )
    body = (
        f'<p>Judges have selected the finalists for the {year} '
        f'PEN/Hemingway Award for Debut Novel:</p>'
        f'<ul>{items}</ul>'
        f'<p>This year’s judges—Rachel Beanland, Dionne Irving, and '
        f'Taymour Soomro—considered 146 eligible novels.</p>'
    )
    return _article(
        f'Announcing the Finalists for the {year} PEN/Hemingway Award for Debut Novel',
        body,
    )


def _winner_article(year: int, title: str, author: str) -> str:
    body = (
        f'<p>{author}’s {title} (Crown) has been selected as the winner '
        f'of the {year} PEN/Hemingway Award for Debut Novel.</p>'
        '<p>This year’s judges—Rachel Beanland, Dionne Irving, and '
        'Taymour Soomro—considered 146 eligible novels by American authors '
        'published in the US during the 2025 calendar year.</p>'
    )
    return _article(
        f'Announcing the Winner of the {year} PEN/Hemingway Award for Debut Novel',
        body,
    )


def _status(records, title: str) -> str | None:
    for record in records:
        if record.work_title == title:
            return record.status
    return None


def _year_records(records, year: int):
    return [item for item in records if item.award_year == year]


class HistoricalLandingParserTests(unittest.TestCase):
    def test_1976_first_winner(self):
        records = ph._parse_landing_html(_historical_landing(), _landing_url())
        ph._validate_historical_records(records)
        match = _year_records(records, 1976)
        self.assertEqual(len(match), 1)
        self.assertEqual(match[0].work_title, 'Parthian Shot')
        self.assertEqual(match[0].work_author, 'Loyd Little')
        self.assertEqual(match[0].status, 'Winner')
        self.assertEqual(match[0].category, 'Fiction')
        self.assertEqual(match[0].source_url, _landing_url())
        result = ph._to_award_result(match[0])
        self.assertEqual(result.award_name, ph.AWARD_NAME)
        self.assertEqual(result.source_name, ph.SOURCE_NAME)
        self.assertIsNone(result.rank)
        self.assertEqual(result.identity_kind, 'work')
        self.assertEqual(
            assess_award_result(result).qualification.decision,
            QualificationDecision.QUALIFIES,
        )

    def test_required_historical_winner_fixtures(self):
        records = ph._parse_landing_html(_historical_landing(), _landing_url())
        ph._validate_historical_records(records)
        fixtures = {
            1982: ('Housekeeping', 'Marilynne Robinson'),
            1983: ('Shiloh and Other Stories', 'Bobbie Ann Mason'),
            1990: ('The Ice at the Bottom of the World', 'Mark Richard'),
            1996: ('Native Speaker', 'Chang-rae Lee'),
            2000: ('Interpreter of Maladies', 'Jhumpa Lahiri'),
            2010: (
                'A Long Long Time Ago and Essentially True',
                'Brigid Pasulka',
            ),
            2013: ('The Yellow Birds', 'Kevin Powers'),
            2020: ('A Prayer for Travelers', 'Ruchika Tomar'),
            2025: ('Early Sobrieties', 'Michael Deagler'),
        }
        by_year = {item.award_year: item for item in records}
        for year, (title, author) in fixtures.items():
            self.assertEqual(by_year[year].work_title, title)
            self.assertEqual(by_year[year].work_author, author)
            self.assertEqual(by_year[year].status, 'Winner')

    def test_every_year_1976_through_2025_has_exactly_one_winner(self):
        records = ph._parse_landing_html(_historical_landing(), _landing_url())
        ph._validate_historical_records(records)
        self.assertEqual(len(records), 50)
        years = {item.award_year for item in records}
        self.assertEqual(years, set(range(1976, 2026)))
        for year in years:
            winners = _year_records(records, year)
            self.assertEqual(len(winners), 1, year)
            self.assertEqual(winners[0].status, 'Winner')

    def test_official_spelling_is_preserved(self):
        records = ph._parse_landing_html(_historical_landing(), _landing_url())
        by_year = {item.award_year: item for item in records}
        self.assertEqual(by_year[1994].work_author, 'Dagobert Gilb')
        self.assertEqual(by_year[1994].work_title, 'The Magic of Blood')
        self.assertEqual(by_year[1999].work_author, 'Rosina Lipini')
        self.assertEqual(by_year[2003].work_author, 'George Brownstein')
        self.assertEqual(
            by_year[2021].work_title,
            'Sharks in the Time of Saviors: A Novel',
        )
        self.assertEqual(
            by_year[2023].work_title,
            'Calling For a Blanket Dance',
        )
        self.assertEqual(by_year[2019].work_title, 'There There')
        self.assertNotEqual(by_year[1994].work_author, 'Dagoberto Gilb')
        self.assertNotEqual(by_year[1999].work_author, 'Rosina Lippi')
        self.assertNotEqual(by_year[2003].work_author, 'Gabriel Brownstein')

    def test_2026_cards_and_award_news_chrome_are_ignored(self):
        extra = (
            '<h3>2026 Winner</h3>'
            '<p>Virginia Evans, author of The Correspondent</p>'
            '<h3>2026 Finalists</h3>'
            '<h2>Awake in the Floating City</h2>'
            '<p>2026 PEN/Hemingway Award FinalistSusanna Kwan is an artist.</p>'
            '<h2>Blob</h2>'
            '<p>2026 PEN/Hemingway Award FinalistMaggie Su is a writer.</p>'
        )
        trailer = (
            '<h3>PEN/Faulkner Award News</h3>'
            '<h2>Elizabeth McCracken Wins the 2026 PEN/Bernard and Ann '
            'Malamud Award</h2>'
            '<p>Elizabeth McCracken has been selected as the winner of the '
            '2026 PEN/Bernard and Ann Malamud Award.</p>'
            '<h2>Announcing the Winner of the 2026 PEN/Faulkner Award for '
            'Fiction</h2>'
            '<p>Mahreen Sohail’s Small Scale Sinners (A Public Space) has '
            'been selected as the winner of the 2026 PEN/Faulkner Award '
            'for Fiction.</p>'
            '<h2>Willee Lewis is our 2026 PEN/Faulkner Literary Champion</h2>'
        )
        records = ph._parse_landing_html(
            _historical_landing(extra=extra, trailer=trailer),
            _landing_url(),
        )
        ph._validate_historical_records(records)
        self.assertFalse(any(item.award_year == 2026 for item in records))
        self.assertFalse(
            any(item.work_title == 'The Correspondent' for item in records)
        )
        self.assertFalse(
            any(item.work_title == 'Small Scale Sinners' for item in records)
        )
        self.assertFalse(any(item.work_author == 'Maggie Su' for item in records))
        self.assertFalse(any(item.work_author == 'Willee Lewis' for item in records))
        self.assertFalse(
            any(item.work_author == 'Elizabeth McCracken' for item in records)
        )

    def test_missing_year_rejects_historical_archive(self):
        html = _historical_landing(skip_year=1995)
        records = ph._parse_landing_html(html, _landing_url())
        with self.assertRaises(ph.PenHemingwaySourceError):
            ph._validate_historical_records(records)

    def test_duplicate_winner_year_is_rejected(self):
        html = _historical_landing().replace(
            _winner_paragraph(2000, 'Interpreter of Maladies', 'Jhumpa Lahiri'),
            _winner_paragraph(2000, 'Interpreter of Maladies', 'Jhumpa Lahiri')
            + _winner_paragraph(2000, 'Another Book', 'Another Author'),
            1,
        )
        records = ph._parse_landing_html(html, _landing_url())
        with self.assertRaises(ph.PenHemingwaySourceError):
            ph._validate_historical_records(records)

    def test_empty_winner_year_is_rejected(self):
        html = _historical_landing().replace(
            _winner_paragraph(1990, 'The Ice at the Bottom of the World', 'Mark Richard'),
            '<p><strong>1990 </strong></p>',
            1,
        )
        records = ph._parse_landing_html(html, _landing_url())
        with self.assertRaises(ph.PenHemingwaySourceError):
            ph._validate_historical_records(records)

    def test_raw_html_is_not_on_parsed_records(self):
        records = ph._parse_landing_html(_historical_landing(), _landing_url())
        payload = [ph._record_to_cache_dict(item) for item in records]
        blob = json.dumps(payload)
        self.assertNotIn('<em>', blob)
        self.assertNotIn('html', blob)


class ModernParserTests(unittest.TestCase):
    def test_2026_finalists_are_three_li_works(self):
        html = _finalists_article(2026, _PAIRS_2026)
        records = ph._parse_finalists_html(html, 2026, _finalists_url(2026))
        self.assertEqual(len(records), 3)
        self.assertEqual(records[0].work_title, 'The Correspondent')
        self.assertEqual(records[0].work_author, 'Virginia Evans')
        self.assertEqual(records[1].work_title, 'Awake in the Floating City')
        self.assertEqual(records[1].work_author, 'Susanna Kwan')
        self.assertEqual(records[2].work_title, 'Blob')
        self.assertEqual(records[2].work_author, 'Maggie Su')
        self.assertTrue(all(item.status == 'Finalist' for item in records))
        self.assertFalse(any('Rachel Beanland' in item.work_author for item in records))

    def test_2026_winner_uses_explicit_winner_sentence(self):
        html = _winner_article(2026, 'The Correspondent', 'Virginia Evans')
        winner = ph._parse_winner_html(html, 2026, _winner_url(2026))
        self.assertIsNotNone(winner)
        self.assertEqual(winner.work_title, 'The Correspondent')
        self.assertEqual(winner.work_author, 'Virginia Evans')
        self.assertEqual(winner.award_year, 2026)
        self.assertEqual(winner.status, 'Winner')
        self.assertEqual(winner.category, 'Fiction')
        self.assertEqual(winner.source_url, _winner_url(2026))

    def test_winner_is_not_the_first_named_person_in_the_article(self):
        html = _article(
            'Announcing the Winner of the 2026 PEN/Hemingway Award for Debut Novel',
            '<p>Lauren Francis-Sharma praised the field.</p>'
            '<p>Virginia Evans’ The Correspondent (Crown) has been selected '
            'as the winner of the 2026 PEN/Hemingway Award for Debut Novel.</p>',
        )
        winner = ph._parse_winner_html(html, 2026, _winner_url(2026))
        self.assertEqual(winner.work_author, 'Virginia Evans')
        self.assertNotEqual(winner.work_author, 'Lauren Francis-Sharma')

    def test_2026_merge_is_one_winner_and_two_finalists(self):
        finalists = ph._parse_finalists_html(
            _finalists_article(2026, _PAIRS_2026),
            2026,
            _finalists_url(2026),
        )
        winner = ph._parse_winner_html(
            _winner_article(2026, 'The Correspondent', 'Virginia Evans'),
            2026,
            _winner_url(2026),
        )
        merged = ph._dedupe_records(list(finalists) + [winner])
        ph._validate_modern_records(merged, 2026, 'winner')
        self.assertEqual(len(merged), 3)
        self.assertEqual(
            sum(1 for item in merged if item.status == 'Winner'),
            1,
        )
        self.assertEqual(
            sum(1 for item in merged if item.status == 'Finalist'),
            2,
        )
        correspondent = [
            item for item in merged if item.work_title == 'The Correspondent'
        ]
        self.assertEqual(len(correspondent), 1)
        self.assertEqual(correspondent[0].status, 'Winner')
        self.assertEqual(correspondent[0].work_author, 'Virginia Evans')
        self.assertEqual(correspondent[0].source_url, _winner_url(2026))
        result = ph._to_award_result(correspondent[0])
        self.assertIsNone(result.rank)
        self.assertEqual(
            assess_award_result(result).qualification.decision,
            QualificationDecision.QUALIFIES,
        )
        kwan = [
            item for item in merged if item.work_title == 'Awake in the Floating City'
        ][0]
        self.assertEqual(kwan.status, 'Finalist')
        self.assertEqual(kwan.work_author, 'Susanna Kwan')
        blob = [item for item in merged if item.work_title == 'Blob'][0]
        self.assertEqual(blob.status, 'Finalist')
        self.assertEqual(
            assess_award_result(ph._to_award_result(kwan)).qualification.decision,
            QualificationDecision.QUALIFIES,
        )

    def test_longlist_page_is_not_parsed_as_finalists(self):
        html = _article(
            'Announcing the Longlist for the 2026 PEN/Hemingway Award for Debut Novel',
            '<p>We are thrilled to announce the longlist of books for the '
            '2026 PEN/Hemingway Award for Debut Novel:</p>'
            '<p>Trip by Amie Barrodale (Farrar, Straus and Giroux)</p>'
            '<p>From this longlist, the judges will select three finalists '
            'for the 2026 PEN/Hemingway Award for Debut Novel.</p>',
        )
        records = ph._parse_finalists_html(html, 2026, _finalists_url(2026))
        self.assertEqual(records, ())

    def test_faulkner_fiction_article_is_rejected(self):
        html = _article(
            'Announcing the Winner of the 2026 PEN/Faulkner Award for Fiction',
            '<p>Mahreen Sohail’s Small Scale Sinners (A Public Space) has '
            'been selected as the winner of the 2026 PEN/Faulkner Award '
            'for Fiction.</p>',
        )
        with self.assertRaises(ph.PenHemingwaySourceError):
            ph._require_official_html(html, _winner_url(2026), award_year=2026)

    def test_malamud_and_champion_titles_are_rejected(self):
        malamud = _article(
            'Elizabeth McCracken Wins the 2026 PEN/Bernard and Ann Malamud Award',
            '<p>The PEN/Hemingway Award for Debut Novel is mentioned in chrome.</p>',
        )
        champion = _article(
            'Willee Lewis is our 2026 PEN/Faulkner Literary Champion',
            '<p>The PEN/Hemingway Award for Debut Novel is mentioned in chrome.</p>',
        )
        with self.assertRaises(ph.PenHemingwaySourceError):
            ph._require_official_html(malamud, _winner_url(2026), award_year=2026)
        with self.assertRaises(ph.PenHemingwaySourceError):
            ph._require_official_html(champion, _winner_url(2026), award_year=2026)

    def test_accents_are_not_stripped(self):
        record = ph._ParsedRecord(
            award_year=2025,
            category='Fiction',
            status='Winner',
            work_title='Early Sobrieties',
            work_author='Samuel Kọ́láwọlé',
            source_url=_landing_url(),
        )
        self.assertTrue(
            ph._record_matches(record, 'Early Sobrieties', 'Samuel Kọ́láwọlé')
        )
        self.assertFalse(
            ph._record_matches(record, 'Early Sobrieties', 'Samuel Kolawole')
        )

    def test_apostrophe_author_matches_after_quote_normalization(self):
        record = ph._ParsedRecord(
            award_year=1978,
            category='Fiction',
            status='Winner',
            work_title='A Way of Life, Like Any Other',
            work_author='Darcy O’Brien',
            source_url=_landing_url(),
        )
        self.assertTrue(
            ph._record_matches(
                record, 'A Way of Life, Like Any Other', "Darcy O'Brien"
            )
        )


class DiscoveryFilterTests(unittest.TestCase):
    def test_only_hemingway_finalists_are_accepted_among_contaminated_news(self):
        payload = [
            {
                'title': {
                    'rendered': 'Announcing the Winner of the 2027 PEN/Faulkner Award for Fiction'
                },
                'slug': 'announcing-the-winner-of-the-2027-pen-faulkner-award-for-fiction',
                'link': 'https://www.penfaulkner.org/2027/04/06/announcing-the-winner-of-the-2027-pen-faulkner-award-for-fiction/',
            },
            {
                'title': {
                    'rendered': 'Announcing the Longlist for the 2027 PEN/Hemingway Award for Debut Novel'
                },
                'slug': 'announcing-the-longlist-for-the-2027-pen-hemingway-award-for-fiction',
                'link': 'https://www.penfaulkner.org/2027/01/20/announcing-the-longlist-for-the-2027-pen-hemingway-award-for-fiction/',
            },
            {
                'title': {
                    'rendered': 'Announcing the Finalists for the 2027 PEN/Hemingway Award for Debut Novel'
                },
                'slug': 'announcing-the-finalists-for-the-2027-pen-hemingway-award-for-debut-novel',
                'link': 'https://www.penfaulkner.org/2027/02/17/announcing-the-finalists-for-the-2027-pen-hemingway-award-for-debut-novel/',
            },
            {
                'title': {
                    'rendered': 'Elizabeth McCracken Wins the 2027 PEN/Bernard and Ann Malamud Award'
                },
                'slug': 'elizabeth-mccracken-wins-the-2027-pen-bernard-and-ann-malamud-award',
                'link': 'https://www.penfaulkner.org/2027/05/01/elizabeth-mccracken-wins-the-2027-pen-bernard-and-ann-malamud-award/',
            },
            {
                'title': {
                    'rendered': 'Willee Lewis is our 2027 PEN/Faulkner Literary Champion'
                },
                'slug': 'willee-lewis-is-our-2027-pen-faulkner-literary-champion',
                'link': 'https://www.penfaulkner.org/2027/10/01/willee-lewis-is-our-2027-pen-faulkner-literary-champion/',
            },
            {
                'title': {
                    'rendered': 'The PEN/Faulkner Foundation is the New Administrator of the PEN/Hemingway Award for Debut Novel'
                },
                'slug': 'the-pen-faulkner-foundation-is-the-new-administrator-of-the-pen-hemingway-award-for-debut-novel',
                'link': 'https://www.penfaulkner.org/2025/05/16/the-pen-faulkner-foundation-is-the-new-administrator-of-the-pen-hemingway-award-for-debut-novel/',
            },
            {
                'title': {'rendered': 'Free books in DC schools'},
                'slug': 'free-books-in-dc-schools',
                'link': 'https://www.penfaulkner.org/2027/06/01/free-books-in-dc-schools/',
            },
        ]
        discovered = ph._discover_year_urls(2027, payload)
        self.assertEqual(
            discovered,
            {
                'finalists': payload[2]['link'],
            },
        )

    def test_hemingway_winner_is_accepted_after_finalists(self):
        payload = [
            {
                'title': {
                    'rendered': 'Announcing the Finalists for the 2027 PEN/Hemingway Award for Debut Novel'
                },
                'slug': 'announcing-the-finalists-for-the-2027-pen-hemingway-award-for-debut-novel',
                'link': 'https://www.penfaulkner.org/2027/02/17/announcing-the-finalists-for-the-2027-pen-hemingway-award-for-debut-novel/',
            },
            {
                'title': {
                    'rendered': 'Announcing the Winner of the 2027 PEN/Hemingway Award for Debut Novel'
                },
                'slug': 'announcing-the-winner-of-the-2027-pen-hemingway-award-for-debut-novel',
                'link': 'https://www.penfaulkner.org/2027/03/16/announcing-the-winner-of-the-2027-pen-hemingway-award-for-debut-novel/',
            },
        ]
        discovered = ph._discover_year_urls(2027, payload)
        self.assertEqual(
            discovered,
            {
                'finalists': payload[0]['link'],
                'winner': payload[1]['link'],
            },
        )

    def test_ambiguous_finalists_fail_closed(self):
        payload = [
            {
                'title': {
                    'rendered': 'Announcing the Finalists for the 2027 PEN/Hemingway Award for Debut Novel'
                },
                'slug': 'announcing-the-finalists-for-the-2027-pen-hemingway-award-for-debut-novel',
                'link': 'https://www.penfaulkner.org/2027/02/17/announcing-the-finalists-for-the-2027-pen-hemingway-award-for-debut-novel/',
            },
            {
                'title': {
                    'rendered': 'Announcing the Finalists for the 2027 PEN/Hemingway Award for Debut Novel'
                },
                'slug': 'announcing-the-finalists-for-the-2027-pen-hemingway-award-for-debut-novel-2',
                'link': 'https://www.penfaulkner.org/2027/02/18/announcing-the-finalists-for-the-2027-pen-hemingway-award-for-debut-novel-2/',
            },
        ]
        with self.assertRaises(ph.PenHemingwaySourceError):
            ph._discover_year_urls(2027, payload)

    def test_rest_content_is_not_used_as_facts(self):
        payload = [
            {
                'title': {
                    'rendered': 'Announcing the Winner of the 2027 PEN/Hemingway Award for Debut Novel'
                },
                'slug': 'announcing-the-winner-of-the-2027-pen-hemingway-award-for-debut-novel',
                'link': 'https://www.penfaulkner.org/2027/03/16/announcing-the-winner-of-the-2027-pen-hemingway-award-for-debut-novel/',
                'content': {
                    'rendered': '<p>Trip by Amie Barrodale has been selected as the winner of the 2027 PEN/Hemingway Award for Debut Novel.</p>'
                },
            }
        ]
        discovered = ph._discover_year_urls(2027, payload)
        self.assertEqual(discovered['winner'], payload[0]['link'])
        self.assertNotIn('Trip', json.dumps(discovered))
        self.assertNotIn('Amie Barrodale', json.dumps(discovered))

    def test_url_body_year_disagreement_fails_closed(self):
        html = _winner_article(2026, 'The Correspondent', 'Virginia Evans')
        with self.assertRaises(ph.PenHemingwaySourceError):
            ph._require_official_html(
                html,
                'https://www.penfaulkner.org/2027/03/16/announcing-the-winner-of-the-pen-hemingway-award-for-debut-novel/',
                award_year=2027,
            )


if __name__ == '__main__':
    unittest.main()
