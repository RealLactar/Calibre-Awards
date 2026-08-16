"""Offline unittest coverage for the Locus Awards winner parser and harvest."""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from awards.sources import locus

ABOUT_URL = locus.ABOUT_URL
URL_2018 = 'https://locusmag.com/2018/06/2018-locus-awards-winners/'
URL_2020 = 'https://locusmag.com/2020/06/locus-awards-winners-2020/'
URL_2024 = 'https://locusmag.com/2024/06/2024-locus-awards-winners/'
URL_2026 = 'https://locusmag.com/2026/05/2026-locus-awards-winners/'
URL_2017 = 'https://locusmag.com/2017/06/2017-locus-awards-winners/'
URL_REPORT = 'https://locusmag.com/feature/2024-locus-awards-online-report/'
URL_INTRO_2026 = 'https://locusmag.com/2026/05/2026-locus-awards-winners/'

HTML_ABOUT = f"""
<html><body>
<p>Recent winners. <a href="{URL_INTRO_2026}">You can read all about the 2026 winners here</a>.</p>
<p>For a full list visit the <a href="https://www.sfadb.com/Locus_Awards">Science Fiction Awards Database</a>.</p>
<h2 style="text-align: left;">Previous Winners</h2>
<p>Here are the winners and reports from across the years.</p>
<p><center>2026: <a href="{URL_2026}">Winners</a> • <em>Report forthcoming</em><br />
2026: <a href="{URL_2026}">Winners</a> • <em>duplicate should not repeat</em><br />
2024: <a href="{URL_2024}">Winners</a> • <a href="{URL_REPORT}">Report</a><br />
2020: <a href="{URL_2020}">Winners</a> • <a href="">Report</a><br />
2023: <a href="https://example.com/fake">Winners</a> • <em>external should be ignored</em><br />
2018: <a href="{URL_2018}">Winners</a> • <a href="https://locusmag.com/2018/08/locus-awards-weekend/">Report</a><br />
2017: <a href="{URL_2017}">Winners</a> • <a href="https://example.invalid/2017-report">Report</a></center></p>
<h2>Frequently Asked Questions</h2>
<p>2016: <a href="https://locusmag.com/2016/06/2016-locus-awards-winners/">Winners</a></p>
<p><a href="https://locusmag.com/about-the-locus-awards/">About</a></p>
</body></html>
"""

HTML_2026 = """
<div class="entry-content">
<p>The Locus Science Fiction Foundation announced the 2026 Locus Awards.</p>
<p><span style="color: #008080;"><strong>SCIENCE FICTION NOVEL</strong></span></p>
<ul>
<li>WINNER:&nbsp;<strong>Death of the Author</strong>, Nnedi Okorafor (Morrow; Gollancz)&nbsp;<span class="purchase_links"><a href="https://www.amazon.com/s?k=9780063445789&amp;tag=locusmag06-20">amazon</a> / <a href="https://bookshop.org/a/18487/9780063445789">bookshop</a></span></li>
</ul>
<ul>
<li><strong>The Folded Sky</strong>, Elizabeth Bear (Saga; Gollancz)</li>
<li><strong>Shroud</strong>, Adrian Tchaikovsky (Tor UK; Orbit US)</li>
</ul>
<p><span style="color: #008080;"><strong>FANTASY NOVEL</strong></span></p>
<ul>
<li>WINNER: <strong>The Everlasting</strong>, Alix E. Harrow (Tor; Tor UK)</li>
</ul>
<ul>
<li><strong>The Devils</strong>, Joe Abercrombie (Tor; Gollancz)</li>
</ul>
<p><span style="color: #008080;"><strong>HORROR NOVEL</strong></span></p>
<ul>
<li>WINNER: <strong>The Buffalo Hunter Hunter</strong>, Stephen Graham Jones (Saga; Titan UK)</li>
</ul>
<p><span style="color: #008080;"><strong>YOUNG ADULT NOVEL</strong></span></p>
<ul>
<li>WINNER: <strong>Starstrike</strong>, Yoon Ha Lee (Delacorte; Solaris UK) [SF]</li>
</ul>
<p><span style="color: #008080;"><strong>FIRST NOVEL</strong></span></p>
<ul>
<li>WINNER: <strong>Sour Cherry</strong>, Natalia Theodoridou (Tin House; Wildfire UK) [F]</li>
</ul>
<p><span style="color: #008080;"><strong>TRANSLATED NOVEL</strong></span></p>
<ul>
<li>WINNER:&nbsp;<strong>On the Calculation of Volume III</strong>, Solvej Balle, tr. Sophia Hersi Smith &amp; Jennifer Russell (New Directions; Faber &amp; Faber) [SF]</li>
</ul>
<p><span style="color: #008080;"><strong>NOVELLA</strong></span></p>
<ul>
<li>WINNER: <strong>The River Has Roots</strong>, Amal El-Mohtar (Tordotcom)</li>
</ul>
<p><span style="color: #008080;"><strong>MAGAZINE</strong></span></p>
<ul>
<li>WINNER: <em>Clarkesworld</em></li>
</ul>
</div>
"""

HTML_2018 = """
<div class="entry-content">
<p><span style="color: #008080;"><strong>SCIENCE FICTION NOVEL</strong></span></p>
<ul>
<li><span style="color: #ff0000;">WINNER: <b><a style="color: #ff0000;" href="https://www.amazon.com/dp/076538888X/?tag=locusmag06-20">The Collapsing Empire</a></b>, John Scalzi (Tor US; Tor UK)</span></li>
</ul>
<ul>
<li><b><a href="https://www.amazon.com/dp/0316332836/?tag=locusmag06-20">Persepolis Rising</a></b>, James S.A. Corey (Orbit US; Orbit UK)</li>
</ul>
<p><span style="color: #008080;"><strong>FANTASY NOVEL</strong></span></p>
<ul>
<li><span style="color: #ff0000;">WINNER: <b><a href="https://www.amazon.com/dp/0316229245/?tag=locusmag06-20">The Stone Sky</a></b>, N.K. Jemisin (Orbit US; Orbit UK)</span></li>
</ul>
<p><span style="color: #008080;"><strong>YOUNG ADULT BOOK</strong></span></p>
<ul>
<li><span style="color: #ff0000;">WINNER: <b><a href="https://www.amazon.com/dp/067078561X/?tag=locusmag06-20">Akata Warrior</a></b>, Nnedi Okorafor (Viking)</span></li>
</ul>
<p><span style="color: #008080;"><strong>FIRST NOVEL</strong></span></p>
<ul>
<li><span style="color: #ff0000;">WINNER: <b><a href="https://www.amazon.com/dp/148146650X/?tag=locusmag06-20">The Strange Case of the Alchemist’s Daughter</a></b>, Theodora Goss (Saga)</span></li>
</ul>
</div>
"""

HTML_2024 = """
<div class="nobullets">
<p><strong>SCIENCE FICTION NOVEL</strong></p>
<ul>
<li>WINNER: <a href="https://www.amazon.com/s?k=978-1250826978&amp;tag=locusmag06-20"><b>System Collapse</b></a>, Martha Wells (Tordotcom)</li>
</ul>
<ul>
<li><a href="https://www.amazon.com/s?k=978-1250827517&amp;tag=locusmag06-20"><b>The Jinn-Bot of Shantiport</b></a>, Samit Basu (Tordotcom)</li>
</ul>
<p><strong>HORROR NOVEL</strong></p>
<ul>
<li>WINNER: <a href="https://www.amazon.com/s?k=9781250829795&amp;tag=locusmag06-20"><b>A House with Good Bones</b></a>, T. Kingfisher (Nightfire; Titan UK)</li>
</ul>
</div>
"""

HTML_2025_BOLD_WINNER = """
<p><b>SCIENCE FICTION NOVEL</b></p>
<div class="mynomorebulletlist">
<ul>
<li style="font-weight: 400;"><b>WINNER: The Man Who Saw Seconds</b><span style="font-weight: 400;">, Alexander Boldizar (Clash) </span><a href="https://www.amazon.com/s?k=9781960988072&amp;tag=locusmag06-20"><span>amazon</span></a><span> / </span><a href="https://bookshop.org/a/18487/9781960988072"><span>bookshop</span></a></li>
</ul>
<ul>
<li><b>Rakesfall</b>, Vajra Chandrasekera (Tordotcom; Solaris)</li>
</ul>
</div>
"""

HTML_RED_WITHOUT_WINNER = """
<p><strong>SCIENCE FICTION NOVEL</strong></p>
<ul>
<li><span style="color: #ff0000;"><b>Ancillary Justice</b>, Ann Leckie (Orbit)</span></li>
</ul>
<ul>
<li><b>Neptune's Brood</b>, Charles Stross (Ace)</li>
</ul>
"""

HTML_UNLABELED_FIRST = """
<p><strong>SCIENCE FICTION NOVEL</strong></p>
<ul>
<li><strong>Death of the Author</strong>, Nnedi Okorafor (Morrow)</li>
</ul>
"""

HTML_TOP_TEN = """
<p>The top ten finalists in each category are:</p>
<p><strong>SCIENCE FICTION NOVEL</strong></p>
<ul>
<li><b>The Jinn-Bot of Shantiport</b>, Samit Basu (Tordotcom)</li>
<li><b>A Fire Born of Exile</b>, Aliette de Bodard (Gollancz)</li>
<li><b>Red Team Blues</b>, Cory Doctorow (Tor)</li>
<li><b>Furious Heaven</b>, Kate Elliott (Ad Astra)</li>
<li><b>Translation State</b>, Ann Leckie (Orbit)</li>
<li><b>The Terraformers</b>, Annalee Newitz (Tor)</li>
<li><b>Starter Villain</b>, John Scalzi (Tor)</li>
<li><b>Lords of Uncreation</b>, Adrian Tchaikovsky (Orbit)</li>
<li><b>System Collapse</b>, Martha Wells (Tordotcom)</li>
<li><b>The Road to Roswell</b>, Connie Willis (Del Rey)</li>
</ul>
"""

HTML_MAGAZINE_ONLY = """
<p><strong>MAGAZINE</strong></p>
<ul>
<li>WINNER: <em>Clarkesworld</em></li>
</ul>
<p><strong>PUBLISHER</strong></p>
<ul>
<li>WINNER: Orbit</li>
</ul>
"""

HTML_CONTEST = """
<p>Contest</p>
<ul>
<li>WINNER: Free Subscription Drawing</li>
</ul>
"""

HTML_EMPTY = '<html><body><p>No awards here.</p></body></html>'

HTML_FUZZY_CATEGORY = """
<p><strong>Best Science Fiction Novel</strong></p>
<ul>
<li>WINNER: <strong>Should Not Match Category</strong>, A. Author (Press)</li>
</ul>
<p><strong>Science Fiction</strong></p>
<ul>
<li>WINNER: <strong>Also Should Not Match</strong>, B. Author (Press)</li>
</ul>
<p><strong>SCIENCE FICTION NOVEL</strong></p>
<ul>
<li>WINNER: <strong>Death of the Author</strong>, Nnedi Okorafor (Morrow)</li>
</ul>
"""


def _find_records(records, *, title: str, author: str | None = None):
    matches = [record for record in records if record.work_title == title]
    if author is not None:
        matches = [record for record in matches if record.work_author == author]
    return matches


class LocusDiscoveryTests(unittest.TestCase):
    def test_discovers_2018_forward_official_winner_links(self):
        pages = locus._discover_winner_pages(HTML_ABOUT, ABOUT_URL)
        self.assertEqual(
            pages,
            [
                (2026, URL_2026),
                (2024, URL_2024),
                (2020, URL_2020),
                (2018, URL_2018),
            ],
        )

    def test_ignores_unrelated_and_pre_2018_links(self):
        pages = locus._discover_winner_pages(HTML_ABOUT, ABOUT_URL)
        urls = [url for _year, url in pages]
        self.assertNotIn(URL_2017, urls)
        self.assertNotIn(URL_REPORT, urls)
        self.assertNotIn('https://www.sfadb.com/Locus_Awards', urls)
        self.assertNotIn(
            'https://locusmag.com/2016/06/2016-locus-awards-winners/',
            urls,
        )

    def test_uses_discovered_urls_not_synthesized_slugs(self):
        pages = dict(locus._discover_winner_pages(HTML_ABOUT, ABOUT_URL))
        self.assertEqual(pages[2020], URL_2020)
        self.assertNotEqual(
            pages[2020],
            'https://locusmag.com/2020/06/2020-locus-awards-winners/',
        )

    def test_does_not_duplicate_repeated_links(self):
        pages = locus._discover_winner_pages(HTML_ABOUT, ABOUT_URL)
        urls = [url for _year, url in pages]
        self.assertEqual(urls.count(URL_2026), 1)

    def test_external_winners_url_is_not_accepted(self):
        pages = locus._discover_winner_pages(HTML_ABOUT, ABOUT_URL)
        urls = [url for _year, url in pages]
        self.assertNotIn('https://example.com/fake', urls)
        years = [year for year, _url in pages]
        self.assertNotIn(2023, years)

    def test_www_official_host_is_accepted(self):
        html = """
        <h2>Previous Winners</h2>
        <p>2018: <a href="https://www.locusmag.com/2018/06/2018-locus-awards-winners/">Winners</a></p>
        <h2>FAQ</h2>
        """
        pages = locus._discover_winner_pages(html, ABOUT_URL)
        self.assertEqual(
            pages,
            [
                (
                    2018,
                    'https://www.locusmag.com/2018/06/2018-locus-awards-winners/',
                )
            ],
        )


class LocusWinnerParseTests(unittest.TestCase):
    def test_parses_supported_2026_categories(self):
        parsed = locus._parse_winner_page(HTML_2026, 2026, URL_2026)
        self.assertTrue(parsed.recognized_winner_structure)
        records = parsed.records
        self.assertEqual(
            _find_records(
                records, title='Death of the Author', author='Nnedi Okorafor'
            )[0].category,
            'Science Fiction Novel',
        )
        self.assertEqual(
            _find_records(
                records, title='The Everlasting', author='Alix E. Harrow'
            )[0].category,
            'Fantasy Novel',
        )
        self.assertEqual(
            _find_records(
                records,
                title='The Buffalo Hunter Hunter',
                author='Stephen Graham Jones',
            )[0].category,
            'Horror Novel',
        )
        self.assertEqual(
            _find_records(
                records, title='Sour Cherry', author='Natalia Theodoridou'
            )[0].category,
            'First Novel',
        )
        self.assertEqual(
            _find_records(
                records, title='Starstrike', author='Yoon Ha Lee'
            )[0].category,
            'Young Adult Novel',
        )
        translated = _find_records(
            records,
            title='On the Calculation of Volume III',
            author='Solvej Balle',
        )
        self.assertEqual(len(translated), 1)
        self.assertEqual(translated[0].category, 'Translated Novel')
        self.assertNotIn('Sophia Hersi Smith', translated[0].work_author)

    def test_parses_2018_young_adult_book_distinct_from_novel(self):
        parsed = locus._parse_winner_page(HTML_2018, 2018, URL_2018)
        akata = _find_records(
            parsed.records, title='Akata Warrior', author='Nnedi Okorafor'
        )
        self.assertEqual(len(akata), 1)
        self.assertEqual(akata[0].category, 'Young Adult Book')
        self.assertNotEqual(akata[0].category, 'Young Adult Novel')

    def test_parses_2024_and_2025_winner_markup(self):
        parsed_2024 = locus._parse_winner_page(HTML_2024, 2024, URL_2024)
        wells = _find_records(
            parsed_2024.records, title='System Collapse', author='Martha Wells'
        )
        self.assertEqual(len(wells), 1)
        self.assertEqual(wells[0].category, 'Science Fiction Novel')
        kingfisher = _find_records(
            parsed_2024.records,
            title='A House with Good Bones',
            author='T. Kingfisher',
        )
        self.assertEqual(len(kingfisher), 1)

        parsed_2025 = locus._parse_winner_page(
            HTML_2025_BOLD_WINNER,
            2025,
            'https://locusmag.com/2025/06/2025-locus-awards-winners/',
        )
        boldizar = _find_records(
            parsed_2025.records,
            title='The Man Who Saw Seconds',
            author='Alexander Boldizar',
        )
        self.assertEqual(len(boldizar), 1)
        self.assertNotIn('amazon', boldizar[0].work_author.casefold())
        self.assertNotIn('Clash', boldizar[0].work_author)

    def test_emits_only_explicit_winner_entries(self):
        parsed = locus._parse_winner_page(HTML_2026, 2026, URL_2026)
        titles = [record.work_title for record in parsed.records]
        self.assertIn('Death of the Author', titles)
        self.assertNotIn('The Folded Sky', titles)
        self.assertNotIn('Shroud', titles)
        self.assertNotIn('The Devils', titles)
        self.assertNotIn('The River Has Roots', titles)

    def test_unlabeled_first_item_is_not_winner(self):
        parsed = locus._parse_winner_page(HTML_UNLABELED_FIRST, 2026, URL_2026)
        self.assertFalse(parsed.recognized_winner_structure)
        self.assertEqual(parsed.records, ())

    def test_red_styling_without_winner_text_is_not_winner(self):
        parsed = locus._parse_winner_page(HTML_RED_WITHOUT_WINNER, 2016, URL_2018)
        self.assertFalse(parsed.recognized_winner_structure)
        self.assertEqual(parsed.records, ())

    def test_every_parsed_winner_has_rank_none(self):
        for html, year, url in (
            (HTML_2018, 2018, URL_2018),
            (HTML_2024, 2024, URL_2024),
            (HTML_2026, 2026, URL_2026),
        ):
            parsed = locus._parse_winner_page(html, year, url)
            results = [locus._to_award_result(record) for record in parsed.records]
            self.assertTrue(results)
            for result in results:
                self.assertIsNone(result.rank)
                self.assertEqual(result.status, 'Winner')
                self.assertEqual(result.award_name, 'Locus Award')
                self.assertEqual(result.source_name, 'Locus Awards')
                self.assertEqual(result.source_url, url)

    def test_top_ten_list_creates_neither_ranks_nor_winners(self):
        parsed = locus._parse_winner_page(HTML_TOP_TEN, 2024, URL_2024)
        self.assertFalse(parsed.recognized_winner_structure)
        self.assertEqual(parsed.records, ())

    def test_unsupported_categories_do_not_leak(self):
        parsed = locus._parse_winner_page(HTML_2026, 2026, URL_2026)
        categories = {record.category for record in parsed.records}
        self.assertNotIn('Novella', categories)
        self.assertNotIn('Magazine', categories)
        titles = [record.work_title for record in parsed.records]
        self.assertNotIn('Clarkesworld', titles)

    def test_science_fiction_and_fantasy_remain_distinct(self):
        parsed = locus._parse_winner_page(HTML_2026, 2026, URL_2026)
        sf = _find_records(parsed.records, title='Death of the Author')[0]
        fantasy = _find_records(parsed.records, title='The Everlasting')[0]
        self.assertEqual(sf.category, 'Science Fiction Novel')
        self.assertEqual(fantasy.category, 'Fantasy Novel')
        self.assertNotEqual(sf.category, fantasy.category)

    def test_partial_category_names_do_not_match(self):
        parsed = locus._parse_winner_page(HTML_FUZZY_CATEGORY, 2026, URL_2026)
        titles = [record.work_title for record in parsed.records]
        self.assertEqual(titles, ['Death of the Author'])
        self.assertNotIn('Should Not Match Category', titles)
        self.assertNotIn('Also Should Not Match', titles)

    def test_valid_page_with_no_supported_category_is_recognized(self):
        parsed = locus._parse_winner_page(HTML_MAGAZINE_ONLY, 2026, URL_2026)
        self.assertTrue(
            parsed.recognized_winner_structure,
            'WINNER: list items in recognized unsupported categories still '
            'prove the page is a recognizable Locus winners listing',
        )
        self.assertEqual(parsed.records, ())

    def test_winner_outside_recognized_category_does_not_validate_page(self):
        parsed = locus._parse_winner_page(HTML_CONTEST, 2026, URL_2026)
        self.assertFalse(parsed.recognized_winner_structure)
        self.assertEqual(parsed.records, ())

    def test_unrecognized_page_has_no_winner_structure(self):
        parsed = locus._parse_winner_page(HTML_EMPTY, 2026, URL_2026)
        self.assertFalse(parsed.recognized_winner_structure)
        self.assertEqual(parsed.records, ())
        top_ten = locus._parse_winner_page(HTML_TOP_TEN, 2024, URL_2024)
        self.assertFalse(top_ten.recognized_winner_structure)


class LocusMatchingTests(unittest.TestCase):
    def setUp(self):
        locus._archive_records_cache = None

    def tearDown(self):
        locus._archive_records_cache = None

    def _prime_cache(self, records):
        locus._archive_records_cache = tuple(records)

    def test_exact_normalized_match_succeeds(self):
        parsed = locus._parse_winner_page(HTML_2018, 2018, URL_2018)
        self._prime_cache(parsed.records)
        results = locus.lookup('The Collapsing Empire', 'John Scalzi')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, 'Winner')
        self.assertIsNone(results[0].rank)
        self.assertEqual(results[0].award_year, 2018)

    def test_initials_spacing_normalization(self):
        parsed = locus._parse_winner_page(HTML_2018, 2018, URL_2018)
        self._prime_cache(parsed.records)
        results = locus.lookup('The Stone Sky', 'N. K. Jemisin')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].work_author, 'N.K. Jemisin')

    def test_curly_apostrophe_normalization(self):
        parsed = locus._parse_winner_page(HTML_2018, 2018, URL_2018)
        self._prime_cache(parsed.records)
        results = locus.lookup(
            "The Strange Case of the Alchemist's Daughter",
            'Theodora Goss',
        )
        self.assertEqual(len(results), 1)

    def test_title_prefix_collision_does_not_match(self):
        parsed = locus._parse_winner_page(HTML_2018, 2018, URL_2018)
        self._prime_cache(parsed.records)
        self.assertEqual(locus.lookup('The Collapsing', 'John Scalzi'), [])

    def test_same_title_wrong_author_does_not_match(self):
        parsed = locus._parse_winner_page(HTML_2018, 2018, URL_2018)
        self._prime_cache(parsed.records)
        self.assertEqual(
            locus.lookup('The Collapsing Empire', 'James S.A. Corey'),
            [],
        )


class LocusHarvestCacheTests(unittest.TestCase):
    def setUp(self):
        locus._archive_records_cache = None

    def tearDown(self):
        locus._archive_records_cache = None

    def _rest_item(self, slug: str, link: str, title: str, content: str):
        return {
            'slug': slug,
            'link': link,
            'title': {'rendered': title},
            'content': {'rendered': content},
        }

    def _posts_payload(self, items, *, total=None):
        headers = {
            'X-WP-Total': str(len(items) if total is None else total),
            'X-WP-TotalPages': '1',
        }
        return (200, headers, json.dumps(items))

    def test_empty_index_raises_and_is_not_cached(self):
        with patch.object(locus, '_fetch_html', return_value=HTML_EMPTY):
            with self.assertRaises(locus.LocusSourceError) as ctx:
                locus._get_archive_records()
        self.assertIsNone(locus._archive_records_cache)
        self.assertIn('did not yield any 2018+', str(ctx.exception))

    def test_failed_rest_retrieval_raises_and_is_not_cached(self):
        def fake_fetch_html(opener, url):
            return HTML_ABOUT

        def fake_posts(opener, slugs):
            raise locus.LocusSourceError(
                'Locus request failed with HTTP 500 for posts'
            )

        with (
            patch.object(locus, '_fetch_html', side_effect=fake_fetch_html),
            patch.object(locus, '_fetch_posts_response', side_effect=fake_posts),
        ):
            with self.assertRaises(locus.LocusSourceError) as ctx:
                locus._get_archive_records()
        self.assertIsNone(locus._archive_records_cache)
        self.assertIn('HTTP 500', str(ctx.exception))

    def test_malformed_rest_json_raises_and_is_not_cached(self):
        with (
            patch.object(locus, '_fetch_html', return_value=HTML_ABOUT),
            patch.object(
                locus,
                '_fetch_posts_response',
                return_value=(200, {'X-WP-Total': '1', 'X-WP-TotalPages': '1'}, '{'),
            ),
        ):
            with self.assertRaises(locus.LocusSourceError) as ctx:
                locus._get_archive_records()
        self.assertIsNone(locus._archive_records_cache)
        self.assertIn('not valid JSON', str(ctx.exception))

    def test_non_list_rest_payload_raises_and_is_not_cached(self):
        with (
            patch.object(locus, '_fetch_html', return_value=HTML_ABOUT),
            patch.object(
                locus,
                '_fetch_posts_response',
                return_value=(
                    200,
                    {'X-WP-Total': '1', 'X-WP-TotalPages': '1'},
                    json.dumps({'slug': 'nope'}),
                ),
            ),
        ):
            with self.assertRaises(locus.LocusSourceError) as ctx:
                locus._get_archive_records()
        self.assertIsNone(locus._archive_records_cache)
        self.assertIn('was not a list', str(ctx.exception))

    def test_missing_discovered_post_raises_and_is_not_cached(self):
        items = [
            self._rest_item(
                '2026-locus-awards-winners',
                URL_2026,
                '2026 Locus Awards Winners',
                HTML_2026,
            )
        ]
        with (
            patch.object(locus, '_fetch_html', return_value=HTML_ABOUT),
            patch.object(
                locus, '_fetch_posts_response', return_value=self._posts_payload(items)
            ),
        ):
            with self.assertRaises(locus.LocusSourceError) as ctx:
                locus._get_archive_records()
        self.assertIsNone(locus._archive_records_cache)
        self.assertIn('missing discovered winner slugs', str(ctx.exception))

    def test_duplicate_rest_mapping_raises_and_is_not_cached(self):
        item = self._rest_item(
            '2026-locus-awards-winners',
            URL_2026,
            '2026 Locus Awards Winners',
            HTML_2026,
        )
        with (
            patch.object(locus, '_fetch_html', return_value=HTML_ABOUT),
            patch.object(
                locus,
                '_fetch_posts_response',
                return_value=self._posts_payload([item, item], total=2),
            ),
        ):
            with self.assertRaises(locus.LocusSourceError) as ctx:
                locus._get_archive_records()
        self.assertIsNone(locus._archive_records_cache)
        self.assertIn('duplicate slug', str(ctx.exception))

    def test_about_year_post_title_mismatch_raises_and_is_not_cached(self):
        about = """
        <h2>Previous Winners</h2>
        <p>2024: <a href="https://locusmag.com/2024/06/2024-locus-awards-winners/">Winners</a></p>
        <h2>FAQ</h2>
        """
        items = [
            self._rest_item(
                '2024-locus-awards-winners',
                URL_2024,
                '2025 Locus Awards Winners',
                HTML_2024,
            )
        ]
        with (
            patch.object(locus, '_fetch_html', return_value=about),
            patch.object(
                locus, '_fetch_posts_response', return_value=self._posts_payload(items)
            ),
        ):
            with self.assertRaises(locus.LocusSourceError) as ctx:
                locus._get_archive_records()
        self.assertIsNone(locus._archive_records_cache)
        self.assertIn('did not match official post title', str(ctx.exception))

    def test_unrecognized_indexed_page_raises_and_is_not_cached(self):
        about = """
        <h2>Previous Winners</h2>
        <p>2024: <a href="https://locusmag.com/2024/06/2024-locus-awards-winners/">Winners</a></p>
        <h2>FAQ</h2>
        """
        items = [
            self._rest_item(
                '2024-locus-awards-winners',
                URL_2024,
                '2024 Locus Awards Winners',
                HTML_TOP_TEN,
            )
        ]
        with (
            patch.object(locus, '_fetch_html', return_value=about),
            patch.object(
                locus, '_fetch_posts_response', return_value=self._posts_payload(items)
            ),
        ):
            with self.assertRaises(locus.LocusSourceError) as ctx:
                locus._get_archive_records()
        self.assertIsNone(locus._archive_records_cache)
        self.assertIn('recognizable WINNER:', str(ctx.exception))

    def test_catastrophic_zero_record_harvest_raises_and_is_not_cached(self):
        magazine_about = """
        <h2>Previous Winners</h2>
        <p>2026: <a href="https://locusmag.com/2026/05/2026-locus-awards-winners/">Winners</a></p>
        <h2>FAQ</h2>
        """
        items = [
            self._rest_item(
                '2026-locus-awards-winners',
                URL_2026,
                '2026 Locus Awards Winners',
                HTML_MAGAZINE_ONLY,
            )
        ]
        with (
            patch.object(locus, '_fetch_html', return_value=magazine_about),
            patch.object(
                locus, '_fetch_posts_response', return_value=self._posts_payload(items)
            ),
        ):
            with self.assertRaises(locus.LocusSourceError) as ctx:
                locus._get_archive_records()
        self.assertIsNone(locus._archive_records_cache)
        self.assertIn('no explicit supported-category WINNER records', str(ctx.exception))

    def test_successful_complete_batch_harvest_is_cached(self):
        about = """
        <h2>Previous Winners</h2>
        <p>2026: <a href="https://locusmag.com/2026/05/2026-locus-awards-winners/">Winners</a></p>
        <h2>FAQ</h2>
        """
        items = [
            self._rest_item(
                '2026-locus-awards-winners',
                URL_2026,
                '2026 Locus Awards Winners',
                HTML_2026,
            )
        ]
        html_calls = {'count': 0}
        rest_calls = {'count': 0}

        def fake_html(opener, url):
            html_calls['count'] += 1
            return about

        def fake_posts(opener, slugs):
            rest_calls['count'] += 1
            self.assertEqual(slugs, ['2026-locus-awards-winners'])
            return self._posts_payload(items)

        with (
            patch.object(locus, '_fetch_html', side_effect=fake_html),
            patch.object(locus, '_fetch_posts_response', side_effect=fake_posts),
        ):
            first = locus.lookup('Death of the Author', 'Nnedi Okorafor')
            second = locus.lookup('Death of the Author', 'Nnedi Okorafor')
        self.assertEqual(len(first), 1)
        self.assertEqual(first[0].source_url, URL_2026)
        self.assertEqual(first, second)
        self.assertEqual(html_calls['count'], 1)
        self.assertEqual(rest_calls['count'], 1)
        self.assertIsNotNone(locus._archive_records_cache)

    def test_successful_harvest_is_reused_from_cache(self):
        parsed = locus._parse_winner_page(HTML_2026, 2026, URL_2026)
        locus._archive_records_cache = parsed.records
        with patch.object(locus, '_harvest_records') as harvest:
            results = locus.lookup('Death of the Author', 'Nnedi Okorafor')
        harvest.assert_not_called()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].source_url, URL_2026)

    def test_partial_harvest_is_never_cached(self):
        def fake_html(opener, url):
            return HTML_ABOUT

        def fake_posts(opener, slugs):
            raise locus.LocusSourceError('Locus request failed for posts')

        with (
            patch.object(locus, '_fetch_html', side_effect=fake_html),
            patch.object(locus, '_fetch_posts_response', side_effect=fake_posts),
        ):
            with self.assertRaises(locus.LocusSourceError):
                locus._get_archive_records()
        self.assertIsNone(locus._archive_records_cache)


if __name__ == '__main__':
    unittest.main()
