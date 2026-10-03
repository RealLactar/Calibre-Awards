"""Balrog archive regression coverage. Fixtures are ISFDB CC BY 4.0 data."""

import unittest
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from awards import cache
from awards.sources import balrog as b
from awards.qualifier import qualify_award_result, QualificationDecision

PAGES = {
    year: (Path(__file__).parent / 'fixtures' / 'balrog' / f'{year}.html').read_text(encoding='utf-8')
    for year in range(1979, 1986)
}
RECORDS = tuple(r for year, html in PAGES.items() for r in b._parse_year(html, year))


class BalrogTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        cache.set_cache_directory(self.directory.name)
        b._reset_runtime_state()

    def tearDown(self):
        b._reset_runtime_state()
        cache.set_cache_directory(None)
        self.directory.cleanup()

    def save(self, stale=False):
        cache.save_source_cache(
            b.SOURCE_KEY, b.CACHE_VERSION, records=[asdict(r) for r in RECORDS],
            source_urls=b.SOURCE_PAGE_URLS, coverage={'min_year': 1979, 'max_year': 1985},
            ttl_seconds=1 if stale else b.CACHE_TTL_SECONDS,
            generated_at=datetime(2000, 1, 1, tzinfo=timezone.utc) if stale else None,
        )

    def test_complete_archive_and_historical_categories(self):
        self.assertEqual(len(RECORDS), 133)
        self.assertEqual(sum(r.status == 'Winner' for r in RECORDS), 21)
        self.assertEqual({r.category for r in RECORDS}, set(b.CATEGORIES))
        self.assertTrue(all(r.rank is None for r in RECORDS))
        self.assertTrue(all(r.status == 'Winner' for r in RECORDS if r.award_year >= 1984))

    def test_live_load_fetches_all_years_once_then_uses_memory(self):
        with patch.object(b, '_fetch_html', side_effect=lambda url: PAGES[int(url.rsplit('+', 1)[1])]) as fetch:
            first = b.lookup('Blind Voices', 'Tom Reamy')
            second = b.lookup('Blind Voices', 'Tom Reamy')
        self.assertEqual(first, second)
        self.assertEqual(fetch.call_count, 7)
        self.assertEqual(first[0].award_year, 1979)
        self.assertEqual(qualify_award_result(first[0]).decision, QualificationDecision.QUALIFIES)

    def test_fresh_disk_no_network_and_author_identity(self):
        self.save()
        with patch.object(b, '_fetch_html', side_effect=AssertionError('network')):
            self.assertEqual(b.lookup('The Practice Effect', 'David Brin')[0].award_year, 1985)
            self.assertEqual(b.lookup('The Practice Effect', 'Wrong Author'), [])

    def test_nomination_remains_review_without_rank(self):
        self.save()
        result = b.lookup('The Stand', 'Stephen King')[0]
        self.assertEqual(result.status, 'Nomination')
        self.assertIsNone(result.rank)
        self.assertEqual(qualify_award_result(result).decision, QualificationDecision.REVIEW)

    def test_malformed_or_wrong_year_fails_closed(self):
        for html in ('<h2>Account Suspended</h2>', PAGES[1980], PAGES[1979].replace('Blind Voices', '')):
            with self.subTest(html=html[:30]):
                with self.assertRaises(b.BalrogSourceError):
                    b._parse_year(html, 1979)

    def test_duplicate_rows_collapse(self):
        duplicate = '<tr><td><a href="/cgi-bin/award_details.cgi?1">Win</a></td><td><a href="/cgi-bin/title.cgi?1">Blind Voices</a></td><td><a href="/cgi-bin/ea.cgi?1">Tom Reamy</a></td></tr>'
        boundary = '<td colspan=3><b><a href="/cgi-bin/award_category.cgi?114+0"'
        html = PAGES[1979].replace(boundary, '</tr>' + duplicate + '<tr>' + boundary, 1)
        self.assertEqual(len(b._parse_year(html, 1979)), 12)

    def test_failed_stale_refresh_preserves_snapshot(self):
        self.save(stale=True)
        path = Path(self.directory.name) / 'balrog.json'
        before = path.read_bytes()
        with patch.object(cache, 'try_claim_stale_refresh', return_value=True), patch.object(b, '_fetch_html', side_effect=b.BalrogSourceError('down')):
            self.assertEqual(b.lookup('Blind Voices', 'Tom Reamy')[0].status, 'Winner')
        self.assertEqual(path.read_bytes(), before)

    def test_invalid_disk_never_used(self):
        self.save()
        import json
        path = Path(self.directory.name) / 'balrog.json'
        payload = json.loads(path.read_text())
        payload['records'][0]['rank'] = 1
        path.write_text(json.dumps(payload))
        self.assertIsNone(b._load_disk())

    def test_refresh_is_source_specific(self):
        from awards.cache_control import refresh_award_source_cache
        self.save()
        b.lookup('Blind Voices', 'Tom Reamy')
        unrelated = Path(self.directory.name) / 'keep.txt'
        unrelated.write_text('keep')
        self.assertTrue(refresh_award_source_cache('balrog'))
        self.assertIsNone(b._records)
        self.assertFalse((Path(self.directory.name) / 'balrog.json').exists())
        self.assertEqual(unrelated.read_text(), 'keep')

    def test_empty_identity_rejected(self):
        for title, author in (('', 'Tom Reamy'), ('Blind Voices', ' ')):
            with self.assertRaises(ValueError):
                b.lookup(title, author)
