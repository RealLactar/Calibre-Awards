"""Offline unittest coverage for the Pulitzer HTML parser and match/convert helpers."""

from __future__ import annotations

import io
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from awards.sources import pulitzer
from awards.sources.pulitzer import (
    PulitzerSourceError,
    _parse_category_html,
    _record_matches,
    _safe_detail_url,
    _titles_match,
    _to_award_result,
)

FIXTURES = Path(__file__).resolve().parent / 'fixtures' / 'pulitzer'
FICTION_URL = 'https://www.pulitzer.org/prize-winners-by-category/219'
NOVEL_URL = 'https://www.pulitzer.org/prize-winners-by-category/261'
HOME_URL = 'https://www.pulitzer.org/'
CHALLENGE_HTML = (
    '<html><head><title>Just a moment...</title></head>'
    '<body>Just a moment... Enable JavaScript and cookies to continue'
    '<div id="cf-browser-verification"></div></body></html>'
)
INVALID_HTML = '<html><title>Fiction | The Pulitzer Prizes</title><p>No prizes.</p></html>'


def _load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding='utf-8')


def _find_records(records, *, title: str, author: str):
    return [
        record
        for record in records
        if record.work_title == title and record.work_author == author
    ]


class PulitzerParserFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fiction_html = _load_fixture('fiction_excerpt.html')
        cls.novel_html = _load_fixture('novel_excerpt.html')
        cls.modern_html = _load_fixture('fiction_modern_excerpt.html')
        cls.no_award_html = _load_fixture('fiction_no_award_2012.html')
        cls.fiction_records = _parse_category_html(
            cls.fiction_html,
            'Fiction',
            FICTION_URL,
        )
        cls.novel_records = _parse_category_html(
            cls.novel_html,
            'Novel',
            NOVEL_URL,
        )
        cls.modern_records = _parse_category_html(
            cls.modern_html,
            'Fiction',
            FICTION_URL,
        )
        cls.no_award_records = _parse_category_html(
            cls.no_award_html,
            'Fiction',
            FICTION_URL,
        )

    def test_beloved_winner_parses_once(self):
        matches = _find_records(
            self.fiction_records,
            title='Beloved',
            author='Toni Morrison',
        )
        self.assertEqual(len(matches), 1)
        record = matches[0]
        self.assertEqual(record.award_year, 1988)
        self.assertEqual(record.category, 'Fiction')
        self.assertEqual(record.status, 'Winner')
        self.assertEqual(record.work_title, 'Beloved')
        self.assertEqual(record.work_author, 'Toni Morrison')

    def test_things_they_carried_finalist_deduped_to_once(self):
        matches = _find_records(
            self.fiction_records,
            title='The Things They Carried',
            author="Tim O'Brien",
        )
        self.assertEqual(len(matches), 1)
        record = matches[0]
        self.assertEqual(record.award_year, 1991)
        self.assertEqual(record.category, 'Fiction')
        self.assertEqual(record.status, 'Finalist')
        self.assertEqual(record.work_title, 'The Things They Carried')
        self.assertEqual(record.work_author, "Tim O'Brien")

    def test_grapes_of_wrath_winner_parses_once(self):
        matches = _find_records(
            self.novel_records,
            title='The Grapes of Wrath',
            author='John Steinbeck',
        )
        self.assertEqual(len(matches), 1)
        record = matches[0]
        self.assertEqual(record.award_year, 1940)
        self.assertEqual(record.category, 'Novel')
        self.assertEqual(record.status, 'Winner')
        self.assertEqual(record.work_title, 'The Grapes of Wrath')
        self.assertEqual(record.work_author, 'John Steinbeck')

    def test_fiction_record_keys_are_unique(self):
        keys = [
            (
                record.award_year,
                record.status,
                record.work_title.casefold(),
                record.work_author.casefold(),
            )
            for record in self.fiction_records
        ]
        self.assertEqual(len(keys), len(set(keys)))

    def test_record_matches_for_expected_pairs(self):
        beloved = _find_records(
            self.fiction_records,
            title='Beloved',
            author='Toni Morrison',
        )[0]
        things = _find_records(
            self.fiction_records,
            title='The Things They Carried',
            author="Tim O'Brien",
        )[0]
        grapes = _find_records(
            self.novel_records,
            title='The Grapes of Wrath',
            author='John Steinbeck',
        )[0]

        self.assertTrue(_record_matches(beloved, 'Beloved', 'Toni Morrison'))
        self.assertTrue(
            _record_matches(things, 'The Things They Carried', "Tim O'Brien")
        )
        self.assertTrue(
            _record_matches(grapes, 'The Grapes of Wrath', 'John Steinbeck')
        )

    def test_to_award_result_conversion(self):
        beloved = _find_records(
            self.fiction_records,
            title='Beloved',
            author='Toni Morrison',
        )[0]
        things = _find_records(
            self.fiction_records,
            title='The Things They Carried',
            author="Tim O'Brien",
        )[0]
        grapes = _find_records(
            self.novel_records,
            title='The Grapes of Wrath',
            author='John Steinbeck',
        )[0]

        beloved_result = _to_award_result(beloved)
        self.assertEqual(beloved_result.award_name, 'Pulitzer Prize')
        self.assertEqual(beloved_result.source_name, 'Pulitzer Prizes')
        self.assertEqual(beloved_result.category, 'Fiction')
        self.assertEqual(beloved_result.award_year, 1988)
        self.assertEqual(beloved_result.status, 'Winner')
        self.assertIsNone(beloved_result.rank)
        self.assertEqual(
            beloved_result.source_url,
            'https://www.pulitzer.org/winners/toni-morrison',
        )
        self.assertEqual(beloved_result.work_title, 'Beloved')
        self.assertEqual(beloved_result.work_author, 'Toni Morrison')

        things_result = _to_award_result(things)
        self.assertEqual(things_result.award_name, 'Pulitzer Prize')
        self.assertEqual(things_result.source_name, 'Pulitzer Prizes')
        self.assertEqual(things_result.category, 'Fiction')
        self.assertEqual(things_result.award_year, 1991)
        self.assertEqual(things_result.status, 'Finalist')
        self.assertEqual(
            things_result.source_url,
            'https://www.pulitzer.org/finalists/tim-obrien',
        )

        grapes_result = _to_award_result(grapes)
        self.assertEqual(grapes_result.award_name, 'Pulitzer Prize')
        self.assertEqual(grapes_result.source_name, 'Pulitzer Prizes')
        self.assertEqual(grapes_result.category, 'Novel')
        self.assertEqual(grapes_result.award_year, 1940)
        self.assertEqual(grapes_result.status, 'Winner')
        self.assertEqual(
            grapes_result.source_url,
            'https://www.pulitzer.org/winners/john-steinbeck',
        )

    def test_standalone_ampersand_matches_and(self):
        self.assertTrue(
            _titles_match(
                'Jonathan Strange and Mr Norrell',
                'Jonathan Strange & Mr Norrell',
            )
        )
        self.assertTrue(
            _titles_match(
                'Jonathan Strange & Mr Norrell',
                'Jonathan Strange and Mr Norrell',
            )
        )
        self.assertTrue(_titles_match('Smith & Jones', 'Smith and Jones'))
        self.assertFalse(_titles_match('The City', 'The City & The City'))


class PulitzerModernMarkupTests(unittest.TestCase):
    def setUp(self):
        self.modern = _parse_category_html(
            _load_fixture('fiction_modern_excerpt.html'),
            'Fiction',
            FICTION_URL,
        )
        self.no_award = _parse_category_html(
            _load_fixture('fiction_no_award_2012.html'),
            'Fiction',
            FICTION_URL,
        )

    def test_angel_down_winner_uses_winners_href(self):
        matches = _find_records(
            self.modern,
            title='Angel Down',
            author='Daniel Kraus',
        )
        self.assertEqual(len(matches), 1)
        record = matches[0]
        self.assertEqual(record.award_year, 2026)
        self.assertEqual(record.category, 'Fiction')
        self.assertEqual(record.status, 'Winner')
        self.assertEqual(
            record.source_url,
            'https://www.pulitzer.org/winners/daniel-kraus',
        )
        result = _to_award_result(record)
        self.assertEqual(result.identity_kind, 'work')
        self.assertIsNone(result.rank)
        self.assertEqual(result.source_url, record.source_url)

    def test_audition_finalist_uses_finalists_href_and_dedupes(self):
        matches = _find_records(
            self.modern,
            title='Audition',
            author='Katie Kitamura',
        )
        self.assertEqual(len(matches), 1)
        record = matches[0]
        self.assertEqual(record.award_year, 2026)
        self.assertEqual(record.status, 'Finalist')
        self.assertEqual(
            record.source_url,
            'https://www.pulitzer.org/finalists/katie-kitamura',
        )

    def test_navigation_h2_is_not_a_prize_record(self):
        self.assertFalse(
            any('navigation' in record.work_title.casefold() for record in self.modern)
        )
        self.assertFalse(
            any(record.work_author.casefold() == 'main navigation' for record in self.modern)
        )

    def test_prose_winner_citation_does_not_replace_the_work(self):
        matches = _find_records(
            self.modern,
            title='Angel Down',
            author='Daniel Kraus',
        )
        self.assertEqual(len(matches), 1)
        self.assertNotIn('tour-de-force', matches[0].work_title.casefold())

    def test_2012_no_award_does_not_emit_a_winner(self):
        self.assertEqual(self.no_award, [])
        self.assertFalse(any(record.status == 'Winner' for record in self.no_award))
        self.assertFalse(
            any(record.award_year == 2012 for record in self.no_award)
        )


class PulitzerSourceUrlSafetyTests(unittest.TestCase):
    def test_relative_winner_href_becomes_absolute(self):
        html = """
        <a href="https://www.pulitzer.org/prize-winners-by-year/1940">1940</a>
        <h2><a href="/winners/john-steinbeck"><em>The Grapes of Wrath</em>,
        by John Steinbeck (Viking)</a></h2>
        """
        records = _parse_category_html(html, 'Novel', NOVEL_URL)
        self.assertEqual(len(records), 1)
        self.assertEqual(
            records[0].source_url,
            'https://www.pulitzer.org/winners/john-steinbeck',
        )

    def test_relative_finalist_href_becomes_absolute(self):
        html = """
        <a href="https://www.pulitzer.org/prize-winners-by-year/2026">2026</a>
        <div class="finalist-title"><a href="/finalists/katie-kitamura">
        <em>Audition</em>, by Katie Kitamura (Riverhead Books)</a></div>
        """
        records = _parse_category_html(html, 'Fiction', FICTION_URL)
        self.assertEqual(len(records), 1)
        self.assertEqual(
            records[0].source_url,
            'https://www.pulitzer.org/finalists/katie-kitamura',
        )

    def test_foreign_href_falls_back_to_category_url(self):
        html = """
        <a href="https://www.pulitzer.org/prize-winners-by-year/1940">1940</a>
        <h2><a href="https://evil.example/winners/john-steinbeck">
        <em>The Grapes of Wrath</em>, by John Steinbeck (Viking)</a></h2>
        """
        records = _parse_category_html(html, 'Novel', NOVEL_URL)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].source_url, NOVEL_URL)

    def test_missing_href_falls_back_to_category_url(self):
        html = """
        <a href="https://www.pulitzer.org/prize-winners-by-year/1940">1940</a>
        <h2><em>The Grapes of Wrath</em>, by John Steinbeck (Viking)</h2>
        """
        records = _parse_category_html(html, 'Novel', NOVEL_URL)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].source_url, NOVEL_URL)

    def test_winner_with_finalists_path_is_rejected(self):
        html = """
        <a href="https://www.pulitzer.org/prize-winners-by-year/1940">1940</a>
        <h2><a href="https://www.pulitzer.org/finalists/john-steinbeck">
        <em>The Grapes of Wrath</em>, by John Steinbeck (Viking)</a></h2>
        """
        records = _parse_category_html(html, 'Novel', NOVEL_URL)
        self.assertEqual(records[0].source_url, NOVEL_URL)

    def test_javascript_href_is_rejected(self):
        self.assertEqual(
            _safe_detail_url(
                'javascript:alert(1)',
                status='Winner',
                fallback=NOVEL_URL,
            ),
            NOVEL_URL,
        )


class _FakeResponse:
    def __init__(self, url: str, status: int, body: str):
        self._url = url
        self.status = status
        self._body = body.encode('utf-8')

    def getcode(self):
        return self.status

    def read(self):
        return self._body

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class PulitzerNetworkTests(unittest.TestCase):
    def setUp(self):
        pulitzer._reset_runtime_state()
        self.fiction_html = _load_fixture('fiction_excerpt.html')
        self.novel_html = _load_fixture('novel_excerpt.html')
        self.requests: list = []

    def tearDown(self):
        pulitzer._reset_runtime_state()

    def _install_opener(self, handler):
        opener = Mock()
        opener.open.side_effect = handler
        return patch.object(pulitzer, '_build_opener', return_value=opener)

    def _open(self, mapping, request, timeout=None):
        self.requests.append(request)
        url = request.full_url
        spec = mapping.get(url)
        if spec is None:
            raise AssertionError(f'unexpected URL {url}')
        status, body = spec
        if status == 403:
            raise HTTPError(url, 403, 'Forbidden', hdrs=None, fp=io.BytesIO(body.encode('utf-8')))
        if status != 200:
            raise HTTPError(url, status, 'Error', hdrs=None, fp=io.BytesIO(body.encode('utf-8')))
        return _FakeResponse(url, status, body)

    def _lookup_with(self, mapping, title='Beloved', author='Toni Morrison'):
        def handler(request, timeout=None):
            return self._open(mapping, request, timeout)

        with self._install_opener(handler):
            return pulitzer.lookup(title, author)

    def test_successful_fetch_skips_homepage_and_referer(self):
        mapping = {
            FICTION_URL: (200, self.fiction_html),
            NOVEL_URL: (200, self.novel_html),
        }
        results = self._lookup_with(mapping)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].work_title, 'Beloved')
        self.assertEqual(
            results[0].source_url,
            'https://www.pulitzer.org/winners/toni-morrison',
        )
        urls = [request.full_url for request in self.requests]
        self.assertEqual(urls, [FICTION_URL, NOVEL_URL])
        self.assertNotIn(HOME_URL, urls)
        for request in self.requests:
            header_names = {name.casefold() for name, _ in request.header_items()}
            self.assertNotIn('referer', header_names)
            self.assertTrue(request.has_header('User-agent'))
            self.assertIn(
                'Mozilla/5.0',
                request.get_header('User-agent'),
            )

    def test_successful_pages_are_cached(self):
        mapping = {
            FICTION_URL: (200, self.fiction_html),
            NOVEL_URL: (200, self.novel_html),
        }
        self._lookup_with(mapping)
        self.assertIsNotNone(pulitzer._category_pages_cache)
        self.assertEqual(len(pulitzer._category_pages_cache), 2)

    def test_fiction_403_raises_and_caches_nothing(self):
        mapping = {
            FICTION_URL: (403, CHALLENGE_HTML),
            NOVEL_URL: (200, self.novel_html),
        }
        with self.assertRaises(PulitzerSourceError) as raised:
            self._lookup_with(mapping)
        self.assertIn('HTTP 403', str(raised.exception))
        self.assertIn(FICTION_URL, str(raised.exception))
        self.assertIsNone(pulitzer._category_pages_cache)
        self.assertEqual(
            [request.full_url for request in self.requests],
            [FICTION_URL],
        )

    def test_novel_403_after_fiction_success_caches_nothing(self):
        mapping = {
            FICTION_URL: (200, self.fiction_html),
            NOVEL_URL: (403, CHALLENGE_HTML),
        }
        with self.assertRaises(PulitzerSourceError) as raised:
            self._lookup_with(mapping)
        self.assertIn('HTTP 403', str(raised.exception))
        self.assertIn(NOVEL_URL, str(raised.exception))
        self.assertIsNone(pulitzer._category_pages_cache)
        self.assertEqual(
            [request.full_url for request in self.requests],
            [FICTION_URL, NOVEL_URL],
        )

    def test_cloudflare_challenge_http_200_is_not_cached(self):
        mapping = {
            FICTION_URL: (200, CHALLENGE_HTML),
            NOVEL_URL: (200, self.novel_html),
        }
        with self.assertRaises(PulitzerSourceError) as raised:
            self._lookup_with(mapping)
        self.assertIn('HTTP 200', str(raised.exception))
        self.assertIsNone(pulitzer._category_pages_cache)

    def test_invalid_fiction_page_is_not_cached(self):
        mapping = {
            FICTION_URL: (200, INVALID_HTML),
            NOVEL_URL: (200, self.novel_html),
        }
        with self.assertRaises(PulitzerSourceError):
            self._lookup_with(mapping)
        self.assertIsNone(pulitzer._category_pages_cache)

    def test_invalid_novel_page_is_not_cached(self):
        mapping = {
            FICTION_URL: (200, self.fiction_html),
            NOVEL_URL: (200, INVALID_HTML),
        }
        with self.assertRaises(PulitzerSourceError):
            self._lookup_with(mapping)
        self.assertIsNone(pulitzer._category_pages_cache)

    def test_failed_lookup_can_succeed_on_later_retry(self):
        mapping = {FICTION_URL: (403, CHALLENGE_HTML)}
        with self.assertRaises(PulitzerSourceError):
            self._lookup_with(mapping)
        self.assertIsNone(pulitzer._category_pages_cache)
        self.requests.clear()
        mapping = {
            FICTION_URL: (200, self.fiction_html),
            NOVEL_URL: (200, self.novel_html),
        }
        results = self._lookup_with(mapping)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].work_title, 'Beloved')
        self.assertIsNotNone(pulitzer._category_pages_cache)

    def test_cached_pages_prevent_subsequent_network_requests(self):
        mapping = {
            FICTION_URL: (200, self.fiction_html),
            NOVEL_URL: (200, self.novel_html),
        }
        self._lookup_with(mapping, title='Beloved', author='Toni Morrison')
        first_count = len(self.requests)
        self._lookup_with(
            mapping,
            title='The Grapes of Wrath',
            author='John Steinbeck',
        )
        self.assertEqual(len(self.requests), first_count)


if __name__ == '__main__':
    unittest.main()
