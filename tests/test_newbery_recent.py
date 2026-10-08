"""ALA announcement excerpts, independently cross-checked with March 2026 PDF."""
import json
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from awards import cache, cache_control, engine
from awards.sources import newbery as n
from awards.qualifier import QualificationDecision
from awards.presentation import default_award_row_checked
from test_newbery_cache import _complete_archive, _detail_pages

F = Path(__file__).parent / 'fixtures' / 'newbery'
HTML = {y: (F / f'annual-{y}.html').read_text(encoding='utf-8') for y in n.ANNUAL_URLS}
# Independent expected identities/statuses from the official PDF, not parser output.
EXPECTED = {
    2024: [('The Eyes and the Impossible', 'Dave Eggers'),
           ('Eagle Drums', 'Nasuġraq Rainey Hopson'), ('Elf Dog and Owl Head', 'M.T. Anderson'),
           ('Mexikid: A Graphic Memoir', 'Pedro Martín'), ('Simon Sort of Says', 'Erin Bow'),
           ('The Many Assassinations of Samir, the Seller of Dreams', 'Daniel Nayeri')],
    2025: [('The First State of Being', 'Erin Entrada Kelly'), ('Across So Many Seas', 'Ruth Behar'),
           ('Magnolia Wu Unfolds It All', 'Chanel Miller'), ('One Big Open Sky', 'Lesa Cline-Ransome'),
           ('The Wrong Way Home', 'Kate O’Shaughnessy')],
    2026: [('All the Blues in the Sky', 'Renée Watson'), ('The Nine Moons of Han Yu and Luli', 'Karina Yan Glaser'),
           ('A Sea of Lemon Trees: The Corrido of Roberto Alvarez', 'María Dolores Águila'),
           ('The Teacher of Nomad Land: A World War II Story', 'Daniel Nayeri'),
           ('The Undead Fox of Deadwood Forest', 'Aubrey Hartman')],
}

class RecentNewberyTests(unittest.TestCase):
    def setUp(self):
        cache._reset_runtime_state()
        n._reset_runtime_state()
        self.temp = TemporaryDirectory()
        cache.set_cache_directory(self.temp.name)
        self.archive = _complete_archive()

    def tearDown(self):
        n._reset_runtime_state()
        cache._reset_runtime_state()
        self.temp.cleanup()

    def legacy(self):
        rows = tuple(r for r in self.archive if r.award_year <= 2023)
        cache.save_source_cache('newbery', 1,
            records=[{k: v for k, v in n._record_to_cache_dict(r).items() if k != 'work_author'} for r in rows],
            source_urls=[s[0] for s in n._HISTORICAL_PAGE_SPECS],
            coverage=n._coverage_from_records(rows, specs=n._HISTORICAL_PAGE_SPECS, max_year=2023),
            ttl_seconds=n.CACHE_TTL_SECONDS)
        return Path(self.temp.name) / 'newbery.json'

    def test_every_2024_2026_medal_and_honor_matches_pdf_and_policy(self):
        n._save_persistent_archive(self.archive)
        with patch.object(n, '_fetch_html', side_effect=AssertionError('announcement identity must not fetch detail')):
            for year, expected in EXPECTED.items():
                parsed = n._parse_annual_html(HTML[year], year, n.ANNUAL_URLS[year])
                self.assertEqual([(r.work_title, r.work_author) for r in parsed], expected)
                for index, (title, author) in enumerate(expected):
                    result, = n.lookup(title, author)
                    self.assertEqual((result.award_year, result.work_title, result.work_author, result.status, result.source_url),
                        (year, title, author, 'Winner' if index == 0 else 'Honor', n.ANNUAL_URLS[year]))
                    self.assertIsNone(result.rank)
                    assessment = engine.assess_award_result(result)
                    self.assertIs(assessment.qualification.decision, QualificationDecision.QUALIFIES)
                    self.assertTrue(default_award_row_checked(qualifies=True, identity_confirmation_required=False))
                    self.assertEqual(n.lookup(title, 'Unrelated Author'), [])

    def test_illustrators_do_not_match_writing_credit(self):
        n._save_persistent_archive(self.archive)
        for title, illustrator in [('The Eyes and the Impossible', 'Shawn Harris'),
            ('Elf Dog and Owl Head', 'Junyi Wu'),
            ('The Many Assassinations of Samir, the Seller of Dreams', 'Daniel Miyares'),
            ('The Undead Fox of Deadwood Forest', 'Marcin Minor')]:
            self.assertEqual(n.lookup(title, illustrator), [])

    def test_missing_newest_year_or_any_annual_honor_is_rejected(self):
        for year in (2024, 2025, 2026):
            with self.subTest(year=year), self.assertRaises(n.NewberySourceError):
                n._validate_cached_archive(tuple(r for r in self.archive if r.award_year != year))
            rows = n._parse_annual_html(HTML[year], year, n.ANNUAL_URLS[year])
            with self.assertRaises(n.NewberySourceError):
                n._validate_page_records(rows[:-1], n.ANNUAL_URLS[year], year, year)
            with self.assertRaises(n.NewberySourceError):
                n._parse_annual_html(HTML[year].replace('written by', 'illustrated by'), year, n.ANNUAL_URLS[year])
        with self.assertRaises(n.NewberySourceError):
            n._parse_annual_html(HTML[2025], 2026, n.ANNUAL_URLS[2026])

    def test_legacy_cache_failure_retains_bytes_history_and_empty_diagnostic(self):
        path = self.legacy()
        before = path.read_bytes()
        cache_control.refresh_award_source_cache('newbery')
        with patch.object(n, '_load_live_archive', side_effect=n.NewberySourceError('offline')), patch.object(n, '_fetch_html', side_effect=lambda opener, url: _detail_pages()[url]):
            history = engine.lookup_awards('Crispin: The Cross of Lead', 'Avi', enabled_source_keys=['newbery'])
            self.assertEqual(len(history.assessments), 1)
            empty = engine.lookup_awards('All the Blues in the Sky', 'Renée Watson', enabled_source_keys=['newbery'])
        self.assertFalse(empty.assessments)
        self.assertFalse(empty.failures)
        self.assertEqual(len(empty.diagnostics), 1)
        self.assertIn('1930–2023', empty.diagnostics[0].message)
        self.assertIn('2024–2026', empty.diagnostics[0].message)
        self.assertTrue(cache.source_refresh_pending('newbery'))
        self.assertEqual(path.read_bytes(), before)
        self.assertIsNone(cache.load_source_cache('newbery', n.CACHE_VERSION))

    def test_legacy_budget_deferral_is_incomplete_then_success_migrates_and_warms(self):
        self.legacy()
        with cache.lookup_refresh_budget():
            cache.try_claim_stale_refresh()
            with patch.object(n, '_load_live_archive', side_effect=AssertionError('budget exhausted')):
                self.assertEqual(n.lookup('All the Blues in the Sky', 'Renée Watson'), [])
        self.assertIsNotNone(n._coverage_diagnostic())
        with patch.object(n, '_load_live_archive', return_value=self.archive) as live:
            report = engine.lookup_awards('All the Blues in the Sky', 'Renée Watson', enabled_source_keys=['newbery'])
            self.assertEqual(live.call_count, 1)
        self.assertTrue(report.assessments)
        self.assertFalse(report.diagnostics)
        self.assertEqual(cache.load_source_cache('newbery', 2)['coverage']['max_year'], 2026)
        with patch.object(n, '_fetch_html', side_effect=AssertionError('fresh warm HTTP')):
            self.assertTrue(n.lookup('All the Blues in the Sky', 'Renée Watson'))

    def test_explicit_success_completes_pending_and_failure_keeps_fuller_cache(self):
        n._save_persistent_archive(self.archive)
        path = Path(self.temp.name) / 'newbery.json'
        before = path.read_bytes()
        cache_control.refresh_award_source_cache('newbery')
        with patch.object(n, '_load_live_archive', return_value=tuple(r for r in self.archive if r.award_year < 2026)):
            self.assertTrue(n.lookup('All the Blues in the Sky', 'Renée Watson'))
        self.assertTrue(cache.source_refresh_pending('newbery'))
        self.assertEqual(path.read_bytes(), before)
        with patch.object(n, '_load_live_archive', return_value=self.archive):
            self.assertTrue(n.lookup('All the Blues in the Sky', 'Renée Watson'))
        self.assertFalse(cache.source_refresh_pending('newbery'))

    def test_truncated_current_cache_never_counts_as_complete(self):
        n._save_persistent_archive(self.archive)
        path = Path(self.temp.name) / 'newbery.json'
        payload = json.loads(path.read_text(encoding='utf-8'))
        payload['records'] = [r for r in payload['records'] if r['award_year'] < 2026]
        payload['record_count'] = len(payload['records'])
        path.write_text(json.dumps(payload), encoding='utf-8')
        self.assertIsNone(n._load_persistent_archive())

    def test_legacy_optional_failure_cools_down_then_retries_with_diagnostic(self):
        path = self.legacy()
        before = path.read_bytes()
        with patch.object(cache.time, 'monotonic', return_value=100), patch.object(n, '_load_live_archive', side_effect=n.NewberySourceError('offline')) as live:
            for _ in range(2):
                report = engine.lookup_awards('All the Blues in the Sky', 'Renée Watson', enabled_source_keys=['newbery'])
                self.assertEqual(len(report.diagnostics), 1)
                self.assertIn('Incomplete Newbery coverage', report.diagnostics[0].message)
            self.assertEqual(live.call_count, 1)
        self.assertFalse(cache.source_refresh_pending('newbery'))
        self.assertEqual(path.read_bytes(), before)
        with patch.object(cache.time, 'monotonic', return_value=161), patch.object(n, '_load_live_archive', return_value=self.archive):
            self.assertTrue(n.lookup('All the Blues in the Sky', 'Renée Watson'))
        self.assertIsNone(n._coverage_diagnostic())

    def test_superseded_newbery_migration_preserves_new_request_and_old_bytes(self):
        path = self.legacy()
        before = path.read_bytes()
        entered, release = threading.Event(), threading.Event()
        def retrieve():
            entered.set()
            self.assertTrue(release.wait(3))
            return self.archive
        pool = ThreadPoolExecutor(1)
        try:
            with patch.object(n, '_load_live_archive', side_effect=retrieve):
                future = pool.submit(n.lookup, 'All the Blues in the Sky', 'Renée Watson')
                self.assertTrue(entered.wait(2))
                self.assertTrue(cache_control.refresh_award_source_cache('newbery'))
                release.set()
                future.result(timeout=4)
            self.assertTrue(cache.source_refresh_pending('newbery'))
            self.assertEqual(path.read_bytes(), before)
            with patch.object(n, '_load_live_archive', return_value=self.archive):
                self.assertTrue(n.lookup('All the Blues in the Sky', 'Renée Watson'))
            self.assertFalse(cache.source_refresh_pending('newbery'))
        finally:
            release.set()
            pool.shutdown(wait=True)
