"""Offline unittest coverage for the Hugo Best Novel parser and archive helpers."""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from awards.sources import hugo

URL_1966 = 'https://www.thehugoawards.org/hugo-history/1966-hugo-awards/'
URL_1985 = 'https://www.thehugoawards.org/hugo-history/1995-hugo-awards-2/'
URL_2015 = 'https://www.thehugoawards.org/hugo-history/2015-hugo-awards/'
URL_2025 = 'https://www.thehugoawards.org/hugo-history/2025-hugo-awards/'
URL_2026 = 'https://www.thehugoawards.org/hugo-history/2026-hugo-awards/'
URL_2016 = 'https://www.thehugoawards.org/hugo-history/2016-hugo-awards/'

HTML_1966 = """
<p><strong>Best Novel</strong></p>
<ul>
<li class="winner"><em>Dune</em> by Frank Herbert [Chilton, 1965] (tie)</li>
<li class="winner"><em>&#8230;And Call Me Conrad (alt: This Immortal)</em> by Roger Zelazny [<em>F&amp;SF</em> Oct,Nov 1965; Ace, 1965] (tie)</li>
<li><em>The Squares of the City</em> by John Brunner [Ballantine, 1965]</li>
<li><em>The Moon is a Harsh Mistress</em> by Robert A. Heinlein [<em>If</em> Dec 1965,Jan,Feb,Mar,Apr 1966; Putnam, 1966]</li>
<li><em>Skylark DuQuesne</em> by Edward E. Smith [<em>If</em> Jun,Jul,Aug,Oct 1965]</li>
</ul>
<p><strong>Short Fiction</strong></p>
<ul>
<li class="winner">&#8220;&#8216;Repent, Harlequin!&#8217; Said the Ticktockman&#8221; by Harlan Ellison [<em>Galaxy</em> Dec 1965]</li>
</ul>
"""

HTML_2025 = """
<p><strong>Best Novel</strong></p>
<ul>
<li class="winner"><em>The Tainted Cup</em> by Robert Jackson Bennett (Del Rey, Hodderscape UK)</li>
<li><em>A Sorceress Comes to Call</em> by T. Kingfisher (Tor)</li>
<li><em>Alien Clay</em> by Adrian Tchaikovsky (Orbit US, Tor UK)</li>
<li><em>Someone You Can Build a Nest In</em> by John Wiswell (DAW)</li>
<li><em>The Ministry of Time</em> by Kaliane Bradley (Avid Reader Press, Sceptre)</li>
<li><em>Service Model</em> by Adrian Tchaikovsky (Tordotcom)</li>
</ul>
<p>1078 ballots cast for 554 nominees, finalists range 90 to 157.</p>
<p><strong>Best Novella</strong></p>
<ul>
<li class="winner"><em>The Tusks of Extinction</em> by Ray Nayler (Tordotcom)</li>
</ul>
<p><strong>Best Novelette</strong></p>
<ul>
<li class="winner">“The Four Sisters Overlooking the Sea” by Naomi Kritzer</li>
</ul>
"""

HTML_2026 = """
<p><strong>Best Novel</strong></p>
<ul>
<li><em>A Drop of Corruption</em> by Robert Jackson Bennett (Del Rey; Hodderscape)</li>
<li><em>Death of the Author</em> by Nnedi Okorafor (William Morrow; Gollancz)</li>
<li><em>Shroud</em> by Adrian Tchaikovsky (Tor UK; Orbit US)</li>
<li><em>The Everlasting</em> by Alix E. Harrow (Tor US; Tor UK)</li>
<li><em>The Incandescent</em> by Emily Tesh (Tor US; Orbit UK)</li>
<li><em>The Raven Scholar</em> by Antonia Hodgson (Orbit US; Hodderscape)</li>
</ul>
<p>1,153 ballots cast for 555 nominees. Finalists range 126-210.</p>
<p><strong>Best Novella</strong></p>
<ul>
<li><em>Automatic Noodle</em> by Annalee Newitz (Tordotcom)</li>
</ul>
"""

HTML_1958 = """
<p><strong>Best Novel or Novelette</strong></p>
<ul>
<li class="winner"><em>The Big Time</em> by Fritz Leiber [<em>Galaxy</em> Mar,Apr 1958]</li>
</ul>
<p><strong>Best Short Story</strong></p>
<ul>
<li class="winner">&#8220;Or All the Seas with Oysters&#8221; by Avram Davidson</li>
</ul>
"""

HTML_DIALECTS = """
<p><strong>Best Novel</strong></p>
<ul>
<li class="winner"><em>Double Star</em> by Robert A. Heinlein [<em>Astounding</em> Feb,Mar,Apr 1956]</li>
<li><em>Call Him Dead</em>, by Eric Frank Russell</li>
<li class="winner"><strong>Ancillary Justice</strong>, Ann Leckie (Orbit US/Orbit UK)</li>
<li><strong>No Award</strong></li>
<li>No winner chosen</li>
<li>Insufficient Nominations &#8211; Not on ballot</li>
</ul>
<p><strong>Best Novella</strong></p>
<ul>
<li class="winner"><em>Should Not Leak</em> by A. Leak</li>
</ul>
"""

HTML_DUNE_WORLD = """
<p><strong>Best Novel</strong></p>
<ul>
<li><em>Dune World</em> by Frank Herbert [Analog, 1963]</li>
<li><em>Way Station</em> by Clifford D. Simak [Galaxy, 1963]</li>
</ul>
"""

HTML_1985 = """
<p><strong>Best Novel</strong></p>
<ul>
<li class="winner"><em>Neuromancer</em> by William Gibson [Ace, 1984]</li>
</ul>
"""

HTML_RETRO = """
<p><strong>Best Novel</strong></p>
<ul>
<li class="winner"><em>Should Not Appear</em> by Retro Author (Press)</li>
</ul>
"""

HTML_INTERVENING_LIST = """
<p><strong>Best Novel</strong></p>
<p>Presented at: intervening commentary that is not the novel list.</p>
<ul>
<li class="winner"><em>Should Not Associate</em> by Intervening Author (Press)</li>
</ul>
<p><strong>Best Novella</strong></p>
<ul>
<li><em>Also Should Not Leak</em> by Other Author (Tor)</li>
</ul>
"""

HTML_MALFORMED_STRONG_TITLE = """
<p><strong>Best Novel</strong></p>
<ul>
<li class="winner"><strong>Ancillary Justice</strong>, Ann Leckie (Orbit US/Orbit UK)</li>
<li><strong>Warbound, Book III of the Grimnoir Chronicle</strong>s, Larry Correia (Baen Books)</li>
<li><strong>Parasite</strong>, Mira Grant (Orbit US/Orbit UK)</li>
</ul>
"""

HTML_2016 = """
<p><strong>Best Novel</strong> (2903 final ballots, 3695 nominating ballots)</p>
<ul>
<li class="winner"><em>The Fifth Season</em> by N.K. Jemisin (Orbit)</li>
<li><em>Uprooted</em> by Naomi Novik (Del Rey)</li>
<li><em>Ancillary Mercy</em> by Ann Leckie (Orbit)</li>
<li><em>Seveneves: A Novel</em> by Neal Stephenson (William Morrow)</li>
<li><em>The Cinder Spires: The Aeronaut’s Windlass</em> by Jim Butcher (Roc)</li>
</ul>
<p><strong>Best Novella</strong></p>
<ul>
<li class="winner"><em>Binti</em> by Nnedi Okorafor (Tor.com)</li>
</ul>
"""

HTML_ARBITRARY_PARENTHETICAL = """
<p><strong>Best Novel</strong> (see Worldcon program notes)</p>
<ul>
<li class="winner"><em>Should Not Associate</em> by Intervening Author (Press)</li>
</ul>
"""


def _find_records(records, *, title: str, author: str | None = None):
    matches = [record for record in records if record.work_title == title]
    if author is not None:
        matches = [record for record in matches if record.work_author == author]
    return matches


def _archive_item(title: str, link: str, content: str, slug: str = 'unused'):
    return {
        'title': {'rendered': title},
        'link': link,
        'slug': slug,
        'content': {'rendered': content},
    }


class HugoParserTests(unittest.TestCase):
    def test_1966_tied_winners_and_finalists(self):
        records = hugo._parse_best_novel_html(HTML_1966, 1966, URL_1966)
        dune = _find_records(records, title='Dune', author='Frank Herbert')
        self.assertEqual(len(dune), 1)
        self.assertEqual(dune[0].status, 'Winner')
        self.assertEqual(dune[0].award_year, 1966)
        self.assertEqual(dune[0].source_url, URL_1966)

        conrad = [
            record
            for record in records
            if 'Call Me Conrad' in record.work_title
        ]
        self.assertEqual(len(conrad), 1)
        self.assertEqual(conrad[0].status, 'Winner')
        self.assertEqual(conrad[0].work_author, 'Roger Zelazny')
        self.assertNotIn('alt:', conrad[0].work_title.casefold())

        squares = _find_records(
            records,
            title='The Squares of the City',
            author='John Brunner',
        )
        self.assertEqual(len(squares), 1)
        self.assertEqual(squares[0].status, 'Finalist')

        self.assertEqual(sum(1 for record in records if record.status == 'Winner'), 2)
        self.assertEqual(sum(1 for record in records if record.status == 'Finalist'), 3)
        self.assertTrue(
            all(record.status != 'Winner' or 'winner' in HTML_1966 for record in records)
        )
        self.assertNotIn('Repent, Harlequin', ' '.join(r.work_title for r in records))

    def test_this_immortal_alternate_title_matches_tied_winner(self):
        records = hugo._parse_best_novel_html(HTML_1966, 1966, URL_1966)
        conrad = [
            record
            for record in records
            if record.work_author == 'Roger Zelazny'
        ][0]
        self.assertTrue(
            hugo._record_matches(conrad, 'This Immortal', 'Roger Zelazny')
        )
        self.assertTrue(
            hugo._record_matches(conrad, '...And Call Me Conrad', 'Roger Zelazny')
        )
        self.assertFalse(hugo._record_matches(conrad, 'Dune', 'Frank Herbert'))

    def test_2025_winner_and_finalist(self):
        records = hugo._parse_best_novel_html(HTML_2025, 2025, URL_2025)
        tainted = _find_records(
            records,
            title='The Tainted Cup',
            author='Robert Jackson Bennett',
        )
        self.assertEqual(len(tainted), 1)
        self.assertEqual(tainted[0].status, 'Winner')

        sorceress = _find_records(
            records,
            title='A Sorceress Comes to Call',
            author='T. Kingfisher',
        )
        self.assertEqual(len(sorceress), 1)
        self.assertEqual(sorceress[0].status, 'Finalist')
        self.assertEqual(len(records), 6)
        self.assertNotIn('The Tusks of Extinction', [r.work_title for r in records])
        self.assertNotIn(
            'The Four Sisters Overlooking the Sea',
            [r.work_title for r in records],
        )

    def test_2026_finalists_do_not_invent_a_winner(self):
        records = hugo._parse_best_novel_html(HTML_2026, 2026, URL_2026)
        self.assertEqual(len(records), 6)
        self.assertTrue(all(record.status == 'Finalist' for record in records))
        self.assertNotIn('Winner', [record.status for record in records])
        drop = _find_records(
            records,
            title='A Drop of Corruption',
            author='Robert Jackson Bennett',
        )
        self.assertEqual(len(drop), 1)
        self.assertEqual(drop[0].status, 'Finalist')
        self.assertNotIn('Automatic Noodle', [r.work_title for r in records])

    def test_best_novel_or_novelette_is_not_best_novel(self):
        records = hugo._parse_best_novel_html(HTML_1958, 1958, 'https://example.test/1958')
        self.assertEqual(records, [])

    def test_citation_dialects_and_non_work_rows(self):
        records = hugo._parse_best_novel_html(
            HTML_DIALECTS, 2014, 'https://example.test/dialects'
        )
        titles = [record.work_title for record in records]
        self.assertEqual(
            _find_records(records, title='Double Star', author='Robert A. Heinlein')[0].status,
            'Winner',
        )
        self.assertEqual(
            _find_records(records, title='Call Him Dead', author='Eric Frank Russell')[0].status,
            'Finalist',
        )
        ancillary = _find_records(
            records, title='Ancillary Justice', author='Ann Leckie'
        )
        self.assertEqual(len(ancillary), 1)
        self.assertEqual(ancillary[0].status, 'Winner')
        self.assertNotIn('No Award', titles)
        self.assertNotIn('Should Not Leak', titles)
        self.assertEqual(len(records), 3)

    def test_dune_does_not_match_dune_world(self):
        dune = hugo._parse_best_novel_html(HTML_1966, 1966, URL_1966)[0]
        world = hugo._parse_best_novel_html(HTML_DUNE_WORLD, 1964, 'https://example.test/1964')[0]
        self.assertEqual(dune.work_title, 'Dune')
        self.assertEqual(world.work_title, 'Dune World')
        self.assertTrue(hugo._record_matches(dune, 'Dune', 'Frank Herbert'))
        self.assertFalse(hugo._record_matches(world, 'Dune', 'Frank Herbert'))
        self.assertFalse(hugo._record_matches(dune, 'Dune World', 'Frank Herbert'))

    def test_to_award_result_fields(self):
        dune = _find_records(
            hugo._parse_best_novel_html(HTML_1966, 1966, URL_1966),
            title='Dune',
            author='Frank Herbert',
        )[0]
        result = hugo._to_award_result(dune)
        self.assertEqual(result.award_name, 'Hugo Award')
        self.assertEqual(result.category, 'Best Novel')
        self.assertEqual(result.status, 'Winner')
        self.assertIsNone(result.rank)
        self.assertEqual(result.source_name, 'Hugo Awards')
        self.assertEqual(result.source_url, URL_1966)
        self.assertIsNone(result.notes)

    def test_2016_ballot_count_note_does_not_drop_best_novel(self):
        records = hugo._parse_best_novel_html(HTML_2016, 2016, URL_2016)
        fifth = _find_records(
            records,
            title='The Fifth Season',
            author='N.K. Jemisin',
        )
        self.assertEqual(len(fifth), 1)
        self.assertEqual(fifth[0].status, 'Winner')
        self.assertEqual(fifth[0].award_year, 2016)
        uprooted = _find_records(
            records,
            title='Uprooted',
            author='Naomi Novik',
        )
        self.assertEqual(len(uprooted), 1)
        self.assertEqual(uprooted[0].status, 'Finalist')
        self.assertEqual(len(records), 5)
        self.assertNotIn('Binti', [record.work_title for record in records])

    def test_2016_ballot_count_note_accepts_comma_grouped_numbers(self):
        html = HTML_2016.replace(
            '(2903 final ballots, 3695 nominating ballots)',
            '(2,903 final ballots, 2,416 nominating ballots)',
        )
        records = hugo._parse_best_novel_html(html, 2016, URL_2016)
        self.assertEqual(
            _find_records(
                records, title='The Fifth Season', author='N.K. Jemisin'
            )[0].status,
            'Winner',
        )

    def test_arbitrary_parenthetical_commentary_does_not_keep_pending_list(self):
        records = hugo._parse_best_novel_html(
            HTML_ARBITRARY_PARENTHETICAL,
            2016,
            'https://example.test/parenthetical',
        )
        titles = [record.work_title for record in records]
        self.assertEqual(records, [])
        self.assertNotIn('Should Not Associate', titles)

    def test_intervening_markup_does_not_claim_a_later_list(self):
        records = hugo._parse_best_novel_html(
            HTML_INTERVENING_LIST,
            2014,
            'https://example.test/intervening',
        )
        titles = [record.work_title for record in records]
        self.assertEqual(records, [])
        self.assertNotIn('Should Not Associate', titles)
        self.assertNotIn('Also Should Not Leak', titles)

    def test_malformed_strong_title_row_is_skipped_not_repaired(self):
        records = hugo._parse_best_novel_html(
            HTML_MALFORMED_STRONG_TITLE,
            2014,
            'https://example.test/warbound',
        )
        titles = [record.work_title for record in records]
        authors = [record.work_author for record in records]
        self.assertEqual(len(records), 2)
        self.assertEqual(
            _find_records(
                records, title='Ancillary Justice', author='Ann Leckie'
            )[0].status,
            'Winner',
        )
        self.assertEqual(
            _find_records(records, title='Parasite', author='Mira Grant')[0].status,
            'Finalist',
        )
        self.assertNotIn('Warbound, Book III of the Grimnoir Chronicle', titles)
        self.assertNotIn('Warbound, Book III of the Grimnoir Chronicles', titles)
        self.assertNotIn('Larry Correia', authors)
        self.assertFalse(any('Warbound' in title for title in titles))
        self.assertFalse(any(author.casefold().startswith('s,') for author in authors))


class HugoArchiveHelperTests(unittest.TestCase):
    def setUp(self):
        hugo._archive_records_cache = None

    def tearDown(self):
        hugo._archive_records_cache = None

    def test_regular_year_pages_are_kept_and_others_filtered(self):
        items = [
            _archive_item('1966 Hugo Awards', URL_1966, HTML_1966, '1966-hugo-awards'),
            _archive_item(
                '1954 Retro-Hugo Awards',
                'https://www.thehugoawards.org/hugo-history/1954-retro-hugo-awards/',
                HTML_RETRO,
                '1954-retro-hugo-awards',
            ),
            _archive_item(
                'A Short History of the Hugo Awards Process',
                'https://www.thehugoawards.org/hugo-history/a-short-history-of-the-hugo-awards-process/',
                HTML_RETRO,
                'a-short-history-of-the-hugo-awards-process',
            ),
            _archive_item(
                '1985 Hugo Awards',
                URL_1985,
                HTML_1985,
                '1995-hugo-awards-2',
            ),
        ]
        records = hugo._records_from_archive_items(items)
        years = {record.award_year for record in records}
        self.assertEqual(years, {1966, 1985})
        neuromancer = _find_records(
            records, title='Neuromancer', author='William Gibson'
        )
        self.assertEqual(len(neuromancer), 1)
        self.assertEqual(neuromancer[0].award_year, 1985)
        self.assertEqual(neuromancer[0].source_url, URL_1985)
        self.assertNotIn(
            'Should Not Appear',
            [record.work_title for record in records],
        )

    def test_invalid_payload_raises_and_does_not_cache(self):
        cases = [
            (500, {'X-WP-Total': '1', 'X-WP-TotalPages': '1'}, '[]'),
            (200, {'X-WP-Total': '1', 'X-WP-TotalPages': '1'}, '{'),
            (200, {'X-WP-Total': '1', 'X-WP-TotalPages': '1'}, '{}'),
            (200, {'X-WP-Total': '1', 'X-WP-TotalPages': '1'}, '[]'),
            (
                200,
                {'X-WP-Total': '2', 'X-WP-TotalPages': '1'},
                json.dumps([_archive_item('1966 Hugo Awards', URL_1966, HTML_1966)]),
            ),
            (
                200,
                {'X-WP-Total': '1', 'X-WP-TotalPages': '2'},
                json.dumps([_archive_item('1966 Hugo Awards', URL_1966, HTML_1966)]),
            ),
            (
                200,
                {'X-WP-Total': '1', 'X-WP-TotalPages': '1'},
                json.dumps([{'title': {'rendered': '1966 Hugo Awards'}, 'link': URL_1966}]),
            ),
        ]
        for status, headers, body in cases:
            with self.subTest(status=status, body=body[:40]):
                hugo._archive_records_cache = None
                with patch.object(
                    hugo, '_fetch_archive_response', return_value=(status, headers, body)
                ):
                    with self.assertRaises(hugo.HugoSourceError):
                        hugo._get_archive_records()
                self.assertIsNone(hugo._archive_records_cache)

    def test_empty_parsed_archive_raises_and_does_not_cache(self):
        body = json.dumps(
            [
                _archive_item(
                    '1958 Hugo Awards',
                    'https://www.thehugoawards.org/hugo-history/1958-hugo-awards/',
                    HTML_1958,
                    '1958-hugo-awards',
                )
            ]
        )
        headers = {'X-WP-Total': '1', 'X-WP-TotalPages': '1'}
        with patch.object(
            hugo,
            '_fetch_archive_response',
            return_value=(200, headers, body),
        ):
            with self.assertRaises(hugo.HugoSourceError) as ctx:
                hugo._get_archive_records()
        self.assertIsNone(hugo._archive_records_cache)
        self.assertIn(
            'no Best Novel records could be parsed',
            str(ctx.exception),
        )

    def test_lookup_uses_cached_parsed_records(self):
        records = hugo._parse_best_novel_html(HTML_1966, 1966, URL_1966)
        hugo._archive_records_cache = tuple(records)
        results = hugo.lookup('This Immortal', 'Roger Zelazny')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, 'Winner')
        self.assertEqual(results[0].award_year, 1966)
        self.assertTrue('Call Me Conrad' in results[0].work_title)


if __name__ == '__main__':
    unittest.main()
