"""Offline regressions using structural extracts of the official Dublin archive."""

import json
import unittest
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from awards import cache
from awards.sources import dublin as d
from awards.qualifier import qualify_award_result, QualificationDecision

FIXTURES = Path(__file__).parent / 'fixtures' / 'dublin'
PAGES = {y: (FIXTURES / f'{y}.html').read_text(encoding='utf-8') for y in range(1996, 2027)}
SITEMAP = (FIXTURES / 'years.xml').read_text(encoding='utf-8')
YEARS = d._parse_years(SITEMAP)
RECORDS = tuple(r for year, url in YEARS.items() for r in d._parse_year(PAGES[year], year, url))


def fetch_fixture(url):
    if url == d.SITEMAP_URL:
        return SITEMAP
    return PAGES[d._url_year(url)]


class DublinTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        cache.set_cache_directory(self.directory.name)
        d._reset_runtime_state()

    def tearDown(self):
        d._reset_runtime_state()
        cache.set_cache_directory(None)
        cache._reset_runtime_state()
        self.directory.cleanup()

    def save(self, stale=False):
        cache.save_source_cache(
            d.SOURCE_KEY, d.CACHE_VERSION, records=[asdict(r) for r in RECORDS],
            source_urls=[d.SITEMAP_URL] + list(YEARS.values()), coverage={'years': list(YEARS)},
            ttl_seconds=1 if stale else d.CACHE_TTL_SECONDS,
            generated_at=datetime(2000, 1, 1, tzinfo=timezone.utc) if stale else None,
        )

    def test_archive_coverage_and_rank_semantics(self):
        self.assertEqual(len(RECORDS), 3608)
        self.assertEqual(sum(r.status == 'Winner' for r in RECORDS), 31)
        self.assertEqual({r.award_year for r in RECORDS}, set(range(1996, 2027)))
        self.assertTrue(all(r.rank is None and r.category is None for r in RECORDS))
        d._validate(RECORDS, tuple(YEARS))

    def test_winner_lookup_and_provenance(self):
        with patch.object(d, '_get_records', return_value=RECORDS):
            r = d.lookup('The Known World', 'Edward P. Jones')[0]
            self.assertEqual(d.lookup('The Known World', 'Wrong Author'), [])
        self.assertEqual(r.award_year, 2005)
        self.assertEqual(r.source_url, YEARS[2005])
        self.assertEqual(r.source_name, d.SOURCE_NAME)
        self.assertEqual(r.status, 'Winner')
        self.assertEqual(qualify_award_result(r).decision, QualificationDecision.QUALIFIES)

    def test_shortlist_remains_review(self):
        r = next(r for r in RECORDS if r.award_year == 2026 and r.work_title == 'Live Fast')
        self.assertEqual(r.work_author, 'Brigitte Giraud')
        self.assertEqual(r.status, 'Shortlisted')
        self.assertEqual(qualify_award_result(r).decision, QualificationDecision.REVIEW)

    def test_latest_and_translated_winners_keep_author(self):
        with patch.object(d, '_get_records', return_value=RECORDS):
            self.assertEqual(d.lookup('Gliff', 'Ali Smith')[0].award_year, 2026)
            self.assertEqual(d.lookup('Solenoid', 'Mircea Cărtărescu')[0].award_year, 2024)
            self.assertEqual(d.lookup('Solenoid', 'Sean Cotter'), [])
            self.assertEqual(d.lookup('De Niro\'s Game', 'Rawi Hage')[0].award_year, 2008)

    def test_longlist_and_nominations_are_review_and_unchecked(self):
        from awards.presentation import default_award_row_checked
        with patch.object(d, '_get_records', return_value=RECORDS):
            for title, author, status in [('Creation Lake', 'Rachel Kushner', 'Longlisted'),
                                          ('1985: A Novel', 'Dominic Hoey', 'Nominated'),
                                          ('What I Know About You', 'Éric Chacour', 'Shortlisted')]:
                results = [r for r in d.lookup(title, author) if r.award_year == 2026]
                self.assertEqual(len(results), 1)
                r = results[0]
                self.assertEqual(r.status, status)
                self.assertEqual(r.source_url, YEARS[2026])
                self.assertIsNone(r.rank)
                q = qualify_award_result(r)
                self.assertEqual(q.decision, QualificationDecision.REVIEW)
                self.assertFalse(default_award_row_checked(qualifies=q.decision is QualificationDecision.QUALIFIES, identity_confirmation_required=False))
            self.assertEqual(d.lookup('1985: A Novel', 'Wrong Author'), [])

    def test_complete_lists_replace_previews_and_keep_strongest_status(self):
        from urllib.parse import parse_qs, urlparse
        requested = []
        def full_list(url):
            params = parse_qs(urlparse(url).query)
            requested.append(params)
            self.assertEqual(params['display_limit'], ['-1'])
            self.assertEqual(params['action'], ['fz0_ajax_load_books_list_item_block'])
            heading = 'longlist' if params['book_cats_ids'] == ['654,125'] else 'nominated'
            return ((FIXTURES / f'2026-{heading}-all.html').read_text(encoding='utf-8')
                    + '<div class="pagination-mod"></div>')
        preview = (FIXTURES / '2026-preview.html').read_text(encoding='utf-8')
        records = d._parse_year(preview, 2026, fetch_list=full_list)
        self.assertEqual(len(records), 69)
        self.assertEqual(len(requested), 2)
        for title, status in [('Gliff', 'Winner'), ('Live Fast', 'Shortlisted'),
                              ('Creation Lake', 'Longlisted'), ('Vanishing World', 'Nominated')]:
            results = [r for r in records if r.work_title == title]
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].status, status)
        with self.assertRaises(d.DublinSourceError):
            d._parse_year(preview, 2026, fetch_list=lambda url: '<html>Access denied</html>')

    def test_complete_list_rejects_wrong_year_truncation_and_pagination(self):
        preview = (FIXTURES / '2026-preview.html').read_text(encoding='utf-8')
        longlist = (FIXTURES / '2026-longlist-all.html').read_text(encoding='utf-8')
        nominees = (FIXTURES / '2026-nominated-all.html').read_text(encoding='utf-8')
        for bad in [nominees.replace('>2026<', '>2025<', 1),
                    nominees[:nominees.index('<article', 100)],
                    nominees + '<div class="pagination-mod"><a href="/page/2/">2</a></div>']:
            with self.subTest(bad=bad[-50:]), self.assertRaises(d.DublinSourceError):
                d._parse_year(preview, 2026, fetch_list=lambda url: longlist if '654%2C125' in url else bad)

    def test_current_year_can_have_only_nominations_before_winner(self):
        root = d._tree(PAGES[2026])
        block = next(n for n in root.walk() if n.has('fxb-books-list-block')
                     and any(a.has('block-heading') and a.text() == 'NOMINATED' for a in n.walk()))
        with patch.object(d, 'datetime') as clock, patch.object(d, '_tree', return_value=d._Node('root', children=[
                d._Node('link', {'rel': 'canonical', 'href': YEARS[2026]}), block])):
            clock.now.return_value = datetime(2026, 1, 1, tzinfo=timezone.utc)
            records = d._parse_year('unused', 2026)
        self.assertEqual(len(records), 69)
        self.assertTrue(all(r.status == 'Nominated' for r in records))

    def test_explicitly_empty_2013_longlist_is_a_documented_source_gap(self):
        records = d._parse_year(PAGES[2013], 2013)
        self.assertEqual(len(records), 10)
        self.assertFalse(any(r.status in ('Nominated', 'Longlisted') for r in records))
        with self.assertRaises(d.DublinSourceError):
            d._parse_year(PAGES[2013].replace('class="not-found"', 'class="error"'), 2013)

    def test_public_wordpress_author_link_preserves_named_author(self):
        with patch.object(d, '_get_records', return_value=RECORDS):
            self.assertEqual(d.lookup('Schmutz', 'Felicia Berliner')[0].status, 'Nominated')
        self.assertFalse(d._author_url('https://dublinliteraryaward.ie/?post_type=books_type&p=15448'))
        self.assertFalse(d._author_url('https://example.test/?post_type=authors_type&p=15448'))

    def test_old_winner_only_cache_cannot_hide_new_nominations(self):
        old_records = tuple(r for r in RECORDS if r.status in ('Winner', 'Shortlisted'))
        cache.save_source_cache('dublin', 1, records=[asdict(r) for r in old_records],
                                source_urls=[d.SITEMAP_URL] + list(YEARS.values()),
                                coverage={'years': list(YEARS)}, ttl_seconds=d.CACHE_TTL_SECONDS)
        self.assertIsNone(d._load_disk())
        with patch.object(d, '_fetch_html', side_effect=fetch_fixture) as fetch:
            self.assertEqual(d.lookup('1985: A Novel', 'Dominic Hoey')[0].status, 'Nominated')
            self.assertEqual(fetch.call_count, 32)
        self.assertIsNotNone(d._load_disk())
        self.save()
        path = Path(self.directory.name) / 'dublin.json'
        payload = json.loads(path.read_text(encoding='utf-8'))
        payload['records'] = [asdict(r) for r in old_records]
        path.write_text(json.dumps(payload), encoding='utf-8')
        self.assertIsNone(d._load_disk())

    def test_separate_winners_and_duplicate_shortlist_winners(self):
        for year in (2017, 2018, 2024, 2026):
            records = d._parse_year(PAGES[year], year)
            self.assertEqual(sum(r.status == 'Winner' for r in records), 1)
            self.assertEqual(len(records), d._MIN_YEAR_CANDIDATES[year])

    def test_wrong_page_missing_identity_and_truncation_fail_closed(self):
        bad = [PAGES[2025], '<html>Access denied</html>',
               PAGES[2026].replace('data-display-limit="-1"', 'data-display-limit="4"', 1),
               PAGES[2026].replace('>Gliff</a>', '></a>'),
               PAGES[2026].replace('books-list-item-author-link', 'translator-link')]
        for html in bad:
            with self.subTest(html=html[:50]), self.assertRaises(d.DublinSourceError):
                d._parse_year(html, 2026)

    def test_sitemap_rejects_missing_year_foreign_host_and_conflict(self):
        import xml.etree.ElementTree as ET
        ns = '{http://www.sitemaps.org/schemas/sitemap/0.9}'
        root = ET.fromstring(SITEMAP)
        root.remove(root.find(ns + 'url'))
        with self.assertRaises(d.DublinSourceError):
            d._parse_years(ET.tostring(root, encoding='unicode'))
        with self.assertRaises(d.DublinSourceError):
            d._parse_years(SITEMAP.replace('dublinliteraryaward.ie', 'example.test'))
        conflict = f'<url><loc>{d.SOURCE_HOME_URL}1996-conflict/</loc></url>'
        with self.assertRaises(d.DublinSourceError):
            d._parse_years(SITEMAP.replace('</urlset>', conflict + '</urlset>'))

    def test_cold_fetch_then_memory_and_disk_without_network(self):
        with patch.object(d, '_fetch_html', side_effect=fetch_fixture) as fetch:
            first = d.lookup('Gliff', 'Ali Smith')
            self.assertEqual(d.lookup('Gliff', 'Ali Smith'), first)
            self.assertEqual(fetch.call_count, 32)
        d._reset_runtime_state()
        with patch.object(d, '_fetch_html', side_effect=AssertionError('network')):
            self.assertEqual(d.lookup('Gliff', 'Ali Smith'), first)

    def test_stale_failure_keeps_fallback_unchanged(self):
        self.save(stale=True)
        path = Path(self.directory.name) / 'dublin.json'
        before = path.read_bytes()
        with patch.object(cache, 'try_claim_stale_refresh', return_value=True), patch.object(d, '_fetch_html', side_effect=d.DublinSourceError('down')):
            self.assertEqual(d.lookup('Gliff', 'Ali Smith')[0].status, 'Winner')
        self.assertEqual(path.read_bytes(), before)

    def test_partial_failure_does_not_publish_archive(self):
        def failed(url):
            if d._url_year(url) == 2017:
                raise d.DublinSourceError('failed year')
            return fetch_fixture(url)
        with patch.object(d, '_fetch_html', side_effect=failed), self.assertRaises(d.DublinSourceError):
            d.lookup('Gliff', 'Ali Smith')
        self.assertFalse((Path(self.directory.name) / 'dublin.json').exists())

    def test_corrupt_disk_and_inferred_rank_are_rejected(self):
        for field, value in [('rank', 1), ('work_author', 123), ('status', 'Unknown'),
                             ('source_url', 'https://example.test/1996/')]:
            self.save()
            path = Path(self.directory.name) / 'dublin.json'
            payload = json.loads(path.read_text(encoding='utf-8'))
            payload['records'][0][field] = value
            path.write_text(json.dumps(payload), encoding='utf-8')
            self.assertIsNone(d._load_disk(), field)

    def test_refresh_failure_retains_pending_request_then_success_clears_it(self):
        from awards.cache_control import refresh_award_source_cache
        self.save()
        d.lookup('Gliff', 'Ali Smith')
        path = Path(self.directory.name) / 'dublin.json'
        before = path.read_bytes()
        refresh_award_source_cache('dublin')
        with patch.object(d, '_fetch_html', side_effect=d.DublinSourceError('down')):
            self.assertEqual(d.lookup('Gliff', 'Ali Smith')[0].status, 'Winner')
        self.assertEqual(path.read_bytes(), before)
        self.assertTrue(cache.payload_refresh_requested(d._load_disk()[1]))
        d._reset_runtime_state()
        with patch.object(d, '_fetch_html', side_effect=fetch_fixture):
            self.assertEqual(d.lookup('Gliff', 'Ali Smith')[0].status, 'Winner')
        self.assertFalse(cache.payload_refresh_requested(d._load_disk()[1]))

    def test_new_source_defaults_enabled_and_has_refresh_help(self):
        from awards.source_registry import AWARD_SOURCES
        from awards.source_info import SOURCE_INFOS
        from awards.source_settings import compute_enabled_source_keys
        from awards.cache_control import runtime_reset_source_keys, BUNDLED_SOURCE_KEYS
        keys = tuple(s.key for s in AWARD_SOURCES)
        self.assertIn('dublin', compute_enabled_source_keys(keys, ['pulitzer']))
        self.assertIn('dublin', runtime_reset_source_keys())
        self.assertNotIn('dublin', BUNDLED_SOURCE_KEYS)
        self.assertEqual(next(i for i in SOURCE_INFOS if i.key == 'dublin').identity_scopes, ('work',))
