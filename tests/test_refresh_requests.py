"""Manual refresh preservation, persistence, and real background source paths."""
import ast
import unittest
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from awards import cache, cache_control, engine
from awards.sources import balrog, locus, diagram
from awards.source_registry import AWARD_SOURCES
from test_balrog import PAGES, RECORDS
from test_locus_cache import (
    _FX, _AUTHOR_SIMMONS, _CANONICAL_1990, _save_author_disk,
    _save_annual_disk, _author_path, _annual_path, _HttpTracker,
)


class RefreshRequestsTests(unittest.TestCase):
    def setUp(self):
        cache._reset_runtime_state()
        self.temp = TemporaryDirectory()
        self.directory = Path(self.temp.name)
        cache.set_cache_directory(self.directory)
        balrog._reset_runtime_state()
        locus._reset_runtime_state()

    def tearDown(self):
        cache._reset_runtime_state()
        balrog._reset_runtime_state()
        locus._reset_runtime_state()
        self.temp.cleanup()

    def save_balrog(self):
        cache.save_source_cache(
            balrog.SOURCE_KEY, balrog.CACHE_VERSION,
            records=[asdict(r) for r in RECORDS], source_urls=balrog.SOURCE_PAGE_URLS,
            coverage={'min_year': 1979, 'max_year': 1985},
            ttl_seconds=balrog.CACHE_TTL_SECONDS,
        )
        return self.directory / 'balrog.json'

    def request(self, key='balrog'):
        with patch('urllib.request.urlopen', side_effect=AssertionError('Refresh opened network')):
            self.assertTrue(cache_control.refresh_award_source_cache(key))
        self.assertTrue(cache.source_refresh_pending(key))

    def test_request_survives_restart_and_preserves_bytes_timestamp(self):
        path = self.save_balrog()
        before = (path.read_bytes(), path.stat().st_mtime_ns)
        self.request()
        cache._reset_runtime_state()
        cache.set_cache_directory(self.directory)
        self.assertTrue(cache.source_refresh_pending('balrog'))
        self.assertFalse(cache.cache_is_fresh(cache.load_source_cache('balrog', 1)))
        self.assertEqual(before, (path.read_bytes(), path.stat().st_mtime_ns))

    def test_manual_success_bypasses_exhausted_budget_and_completes(self):
        path = self.save_balrog()
        self.request()
        with cache.lookup_refresh_budget():
            self.assertTrue(cache.try_claim_stale_refresh())
            self.assertFalse(cache.try_claim_stale_refresh())
            with patch.object(balrog, '_fetch_html', side_effect=lambda url: PAGES[int(url.rsplit('+', 1)[1])]) as fetch:
                self.assertEqual(balrog.lookup('Blind Voices', 'Tom Reamy')[0].award_year, 1979)
        self.assertEqual(fetch.call_count, 7)
        self.assertFalse(cache.source_refresh_pending('balrog'))
        self.assertTrue(cache.cache_is_fresh(cache.load_source_cache('balrog', 1)))
        self.assertTrue(path.is_file())

    def test_failed_and_invalid_downloads_preserve_fallback_and_pending_request(self):
        path = self.save_balrog()
        before = (path.read_bytes(), path.stat().st_mtime_ns)
        for response in (OSError('offline'), '<h2>Account Suspended</h2>'):
            with self.subTest(response=response):
                self.request()
                kwargs = {'side_effect': response} if isinstance(response, Exception) else {'return_value': response}
                with patch.object(balrog, '_fetch_html', **kwargs) as fetch:
                    self.assertEqual(balrog.lookup('Blind Voices', 'Tom Reamy')[0].status, 'Winner')
                self.assertTrue(fetch.called)
                self.assertTrue(cache.source_refresh_pending('balrog'))
                self.assertEqual(before, (path.read_bytes(), path.stat().st_mtime_ns))

    def test_no_fallback_failure_remains_visible_in_engine(self):
        self.request()
        source = next(s for s in AWARD_SOURCES if s.key == 'balrog')
        with patch.object(balrog, '_fetch_html', return_value='<h2>Account Suspended</h2>'):
            result = engine._lookup_one_source(source, 'Blind Voices', 'Tom Reamy', None)
        self.assertIsInstance(result, engine.SourceFailure)
        self.assertTrue(cache.source_refresh_pending('balrog'))

    def test_engine_reports_pending_and_retries_ram_fallback_next_lookup(self):
        self.save_balrog()
        self.request()
        source = next(s for s in AWARD_SOURCES if s.key == 'balrog')
        with patch.object(balrog, '_fetch_html', side_effect=OSError('offline')) as fetch:
            for _ in range(2):
                results = engine._lookup_one_source(source, 'Blind Voices', 'Tom Reamy', None)
                self.assertTrue(any('Refresh pending' in d for d in results[0].source_details))
        self.assertEqual(fetch.call_count, 2)

    def test_publication_failure_does_not_complete_or_overwrite(self):
        path = self.save_balrog()
        before = (path.read_bytes(), path.stat().st_mtime_ns)
        self.request()
        with patch.object(cache.os, 'replace', side_effect=OSError('locked')):
            self.save_balrog()
        self.assertTrue(cache.source_refresh_pending('balrog'))
        self.assertEqual(before, (path.read_bytes(), path.stat().st_mtime_ns))

    def test_request_failure_retains_cache_and_resets_ram(self):
        path = self.save_balrog()
        before = path.read_bytes()
        balrog._records = RECORDS
        with patch.object(cache.os, 'replace', side_effect=OSError('locked')):
            self.assertFalse(cache_control.refresh_award_source_cache('balrog'))
        self.assertIsNone(balrog._records)
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse(cache.source_refresh_pending('balrog'))

    def test_source_isolation(self):
        self.save_balrog()
        cache.save_source_cache('hugo', 1, records=[], source_urls=[], coverage={}, ttl_seconds=60)
        sibling = self.directory / 'hugo.json'
        before = (sibling.read_bytes(), sibling.stat().st_mtime_ns)
        self.request()
        self.assertFalse(cache.source_refresh_pending('hugo'))
        self.assertEqual(before, (sibling.read_bytes(), sibling.stat().st_mtime_ns))

    def test_memory_only_request_completes_on_success(self):
        cache.set_cache_directory(None)
        self.request()
        self.save_balrog()
        self.assertFalse(cache.source_refresh_pending('balrog'))

    def test_corrupt_request_marker_is_not_accepted(self):
        path = self.directory / 'balrog.refresh-request'
        for value in ('[]', 'null', '{"version":1,"source_key":"hugo","targets":["*"]}'):
            path.write_text(value, encoding='utf-8')
            self.assertFalse(cache.source_refresh_pending('balrog'))

    def seed_locus(self):
        page = locus._parse_author_page(_FX.PAGES[_AUTHOR_SIMMONS], _AUTHOR_SIMMONS)
        records = locus._parse_annual_page(_FX.HTML_1990, 1990, _CANONICAL_1990)
        _save_author_disk(page, _AUTHOR_SIMMONS)
        _save_annual_disk(records, _CANONICAL_1990)
        return (_author_path(self.directory, _AUTHOR_SIMMONS),
                _annual_path(self.directory, _CANONICAL_1990))

    def test_locus_suspended_author_and_annual_preserve_both_entries(self):
        paths = self.seed_locus()
        before = [(p.read_bytes(), p.stat().st_mtime_ns) for p in paths]
        self.request('locus')
        tracker = lambda _opener, _url: (200, '<html><title>Account Suspended</title></html>')
        with patch.object(locus, '_request_html', side_effect=tracker) as http:
            result = locus.lookup('Hyperion', 'Dan Simmons')
        self.assertTrue(result)
        self.assertGreaterEqual(http.call_count, 2)
        self.assertTrue(cache.source_refresh_pending('locus'))
        self.assertEqual(before, [(p.read_bytes(), p.stat().st_mtime_ns) for p in paths])

    def test_locus_success_refreshes_historical_entry_despite_exhausted_budget(self):
        self.seed_locus()
        self.request('locus')
        tracker = _HttpTracker(_FX.PAGES)
        with cache.lookup_refresh_budget():
            self.assertTrue(cache.try_claim_stale_refresh())
            with patch.object(locus, '_request_html', side_effect=tracker):
                self.assertTrue(locus.lookup('Hyperion', 'Dan Simmons'))
        self.assertIn(_AUTHOR_SIMMONS, tracker.author)
        self.assertIn(_CANONICAL_1990, tracker.annual)
        self.assertFalse(cache.source_refresh_pending('locus'))

    def test_keyed_completion_and_retry_do_not_requeue_successful_entries(self):
        self.seed_locus()
        self.request('locus')
        payload = cache.load_cache_entry('locus', 'authors', _AUTHOR_SIMMONS, 1)
        cache.save_cache_entry('locus', 'authors', _AUTHOR_SIMMONS, 1,
            records=payload['records'], source_urls=payload['source_urls'],
            coverage=payload['coverage'], ttl_seconds=payload['ttl_seconds'])
        self.request('locus')
        self.assertFalse(cache.payload_refresh_requested(cache.load_cache_entry('locus', 'authors', _AUTHOR_SIMMONS, 1)))
        self.assertTrue(cache.payload_refresh_requested(cache.load_cache_entry('locus', 'annuals', _CANONICAL_1990, 1)))


class DiagramAliasTests(unittest.TestCase):
    def test_exact_verified_alias_and_conservative_identity(self):
        alias = "The Pornographic Delicatessen: Mid-century Montreal's Erotic Art, Media, and Spaces"
        canonical = "The Pornographic Delicatessen: Midcentury Montréal's Erotic Art, Media, and Spaces"
        expected = diagram.lookup(canonical, 'Matthew Purvis')
        self.assertEqual(diagram.lookup(alias, 'Matthew Purvis'), expected)
        self.assertEqual(len(expected), 1)
        self.assertEqual((expected[0].award_year, expected[0].status), (2025, 'Winner'))
        self.assertEqual(diagram.lookup(alias, 'Wrong Author'), [])
        self.assertEqual(diagram.lookup('The Pornographic Delicatessen', 'Matthew Purvis'), [])
        self.assertEqual(diagram.lookup(canonical.replace('Montréal', 'Montreal'), 'Matthew Purvis'), [])


class TextDouble:
    def __init__(self, text='Refresh', checked=True):
        self.value, self.checked, self.tooltip = text, checked, ''
    def text(self): return self.value
    def setText(self, value): self.value = value
    def isChecked(self): return self.checked
    def setToolTip(self, value): self.tooltip = value


def actual_config_methods():
    """Compile the production methods, not a reimplementation of their logic."""
    source = Path(__file__).resolve().parents[1] / 'config.py'
    tree = ast.parse(source.read_text(encoding='utf-8'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'ConfigWidget')
    names = {'_on_refresh_all_sources', '_mark_refresh_queued', '_on_refresh_cached_source',
             '_sync_bulk_refresh_state'}
    methods = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in names]
    namespace = {name: getattr(cache_control, name) for name in (
        'bulk_refresh_description', 'source_refresh_description',
        'run_source_cache_refresh_if_confirmed', 'source_cache_refresh_confirm_title',
        'source_cache_refresh_confirm_body', 'source_cache_refresh_status_text',
        'source_cache_refresh_failure_text')}
    namespace.update(question_dialog=lambda *a, **kw: True, error_dialog=lambda *a, **kw: None)
    exec(compile(ast.Module(body=methods, type_ignores=[]), str(source), 'exec'), namespace)
    return type('ActualConfigMethods', (), {name: namespace[name] for name in names}), namespace


class ActualBulkHandlerTests(unittest.TestCase):
    def setUp(self):
        cls, self.globals = actual_config_methods()
        self.panel = cls()
        p = self.panel
        p.source_checkboxes = {key: TextDouble(name) for key, name in cache_control.cache_refresh_source_rows()}
        p.source_refresh_buttons = {key: TextDouble() for key in p.source_checkboxes}
        p.refresh_all_button, p.cache_status = TextDouble('Refresh all'), TextDouble('')
        self.book_metadata = {'#awards': ['Existing award']}
        self.preferences = {'disabled_source_keys': [], 'writeback_enabled': True}
        p.book_metadata, p.preferences = self.book_metadata, self.preferences

    def select(self, *keys):
        for key, cb in self.panel.source_checkboxes.items(): cb.checked = key in keys
        if hasattr(self.panel, '_sync_bulk_refresh_state'):
            self.panel._sync_bulk_refresh_state()

    def fail_nebula(self, *selected):
        self.select(*(selected or ('nebula',)))
        with patch.dict(self.globals, run_source_cache_refresh_if_confirmed=lambda key, name, **kw: key != 'nebula'):
            self.panel._on_refresh_all_sources()
        self.assertEqual(self.panel._bulk_refresh_retry_keys, {'nebula'})

    def test_failed_nebula_changed_selection_queues_hugo(self):
        self.fail_nebula()
        self.select('hugo')
        calls = []
        with patch.dict(self.globals, run_source_cache_refresh_if_confirmed=lambda key, name, **kw: calls.append(key) or True):
            self.panel._on_refresh_all_sources()
        self.assertEqual(calls, ['hugo'])
        self.assertEqual(self.panel.refresh_all_button.text(), 'Refresh all queued')

    def test_unchanged_partial_selection_retries_only_failed(self):
        self.fail_nebula('nebula', 'hugo')
        calls = []
        with patch.dict(self.globals, run_source_cache_refresh_if_confirmed=lambda key, name, **kw: calls.append(key) or True):
            self.panel._on_refresh_all_sources()
        self.assertEqual(calls, ['nebula'])
        self.assertIsNone(self.panel._bulk_refresh_retry_keys)

    def test_changed_partial_selection_updates_label_and_skips_already_queued(self):
        self.fail_nebula('nebula', 'hugo')
        self.select('hugo', 'diagram')
        self.assertEqual(self.panel.refresh_all_button.text(), 'Refresh all')
        calls = []
        with patch.dict(self.globals, run_source_cache_refresh_if_confirmed=lambda key, name, **kw: calls.append(key) or True):
            self.panel._on_refresh_all_sources()
        self.assertEqual(calls, ['diagram'])
        self.assertEqual(self.panel.refresh_all_button.text(), 'Refresh all queued')

    def test_new_source_alongside_failed_source_is_included(self):
        self.fail_nebula('nebula', 'hugo')
        self.select('nebula', 'hugo', 'diagram')
        calls = []
        with patch.dict(self.globals, run_source_cache_refresh_if_confirmed=lambda key, name, **kw: calls.append(key) or True):
            self.panel._on_refresh_all_sources()
        self.assertEqual(calls, ['nebula', 'diagram'])

    def test_no_selection_after_failure_keeps_appropriate_message(self):
        self.fail_nebula()
        self.select()
        with patch.dict(self.globals, question_dialog=lambda *a, **kw: self.fail('confirmation')):
            self.panel._on_refresh_all_sources()
        self.assertIn('Select at least one', self.panel.cache_status.text())
        self.assertEqual(self.panel.refresh_all_button.text(), 'Refresh all')

    def test_cancel_retry_preserves_failure_state_and_queues_nothing(self):
        self.fail_nebula('nebula', 'hugo')
        before = set(self.panel._bulk_refresh_retry_keys)
        with patch.dict(self.globals, question_dialog=lambda *a, **kw: False,
                        run_source_cache_refresh_if_confirmed=lambda *a, **kw: self.fail('refresh')):
            self.panel._on_refresh_all_sources()
        self.assertEqual(self.panel._bulk_refresh_retry_keys, before)
        self.assertEqual(self.panel.refresh_all_button.text(), 'Retry Refresh all')
        self.assertEqual(self.panel.source_refresh_buttons['hugo'].text(), 'Refresh queued')

    def test_individual_success_removes_failed_source_and_completes_bulk_state(self):
        self.fail_nebula('nebula', 'hugo')
        with patch.dict(self.globals, run_source_cache_refresh_if_confirmed=lambda *a, **kw: True):
            self.panel._on_refresh_cached_source('nebula', 'Nebula Awards')
        self.assertIsNone(self.panel._bulk_refresh_retry_keys)
        self.assertEqual(self.panel.refresh_all_button.text(), 'Refresh all queued')
        with patch.dict(self.globals, run_source_cache_refresh_if_confirmed=lambda *a, **kw: self.fail('requeue')):
            self.panel._on_refresh_all_sources()
        self.assertIn('already queued', self.panel.cache_status.text())

    def test_individual_success_leaves_other_failed_source_retryable(self):
        self.select('nebula', 'hugo')
        with patch.dict(self.globals, run_source_cache_refresh_if_confirmed=lambda *a, **kw: False):
            self.panel._on_refresh_all_sources()
        with patch.dict(self.globals, run_source_cache_refresh_if_confirmed=lambda *a, **kw: True):
            self.panel._on_refresh_cached_source('nebula', 'Nebula Awards')
        self.assertEqual(self.panel._bulk_refresh_retry_keys, {'hugo'})
        self.assertEqual(self.panel.refresh_all_button.text(), 'Retry Refresh all')

    def test_changed_selection_preserves_saved_fallback_and_pending_requests(self):
        self.fail_nebula()
        with TemporaryDirectory() as directory:
            cache.set_cache_directory(directory)
            try:
                for key in ('nebula', 'hugo'):
                    cache.save_source_cache(key, 1, records=[], source_urls=[], coverage={}, ttl_seconds=60)
                cache.request_source_refresh('nebula')
                paths = [Path(directory) / (key + '.json') for key in ('nebula', 'hugo')]
                before = [(p.read_bytes(), p.stat().st_mtime_ns) for p in paths]
                self.select('hugo')
                with patch('urllib.request.urlopen', side_effect=AssertionError('network')):
                    self.panel._on_refresh_all_sources()
                self.assertTrue(cache.source_refresh_pending('nebula'))
                self.assertTrue(cache.source_refresh_pending('hugo'))
                self.assertEqual(before, [(p.read_bytes(), p.stat().st_mtime_ns) for p in paths])
            finally: cache._reset_runtime_state()

    def test_none_selected_does_not_prompt_or_refresh(self):
        self.select()
        with patch.dict(self.globals, question_dialog=lambda *a, **kw: self.fail('confirmation'),
                        run_source_cache_refresh_if_confirmed=lambda *a, **kw: self.fail('refresh')):
            self.panel._on_refresh_all_sources()
        self.assertIn('Select at least one', self.panel.cache_status.text())

    def test_cancel_preserves_cache_buttons_metadata_and_preferences(self):
        with TemporaryDirectory() as directory:
            cache.set_cache_directory(directory)
            try:
                cache.save_source_cache('hugo', 1, records=[], source_urls=[], coverage={}, ttl_seconds=60)
                path = Path(directory) / 'hugo.json'
                before = (path.read_bytes(), path.stat().st_mtime_ns)
                self.select('hugo')
                with patch.dict(self.globals, question_dialog=lambda *a, **kw: False):
                    self.panel._on_refresh_all_sources()
                self.assertEqual(before, (path.read_bytes(), path.stat().st_mtime_ns))
                self.assertFalse(cache.source_refresh_pending('hugo'))
                self.assertEqual(self.panel.source_refresh_buttons['hugo'].text(), 'Refresh')
            finally: cache._reset_runtime_state()
        self.assertEqual(self.book_metadata, {'#awards': ['Existing award']})
        self.assertEqual(self.preferences, {'disabled_source_keys': [], 'writeback_enabled': True})

    def test_only_checked_executable_sources_once_and_success_messages(self):
        self.select('hugo', 'diagram')
        self.panel.source_checkboxes['national_book_awards'] = TextDouble('Unavailable')
        calls = []
        def refresh(key, name, *, confirmed):
            self.assertTrue(confirmed)
            calls.append(key)
            return True
        with patch.dict(self.globals, run_source_cache_refresh_if_confirmed=refresh):
            self.panel._on_refresh_all_sources()
        self.assertEqual(calls, ['hugo', 'diagram'])
        self.assertEqual(self.panel.refresh_all_button.text(), 'Refresh all queued')
        self.assertEqual(self.panel.source_refresh_buttons['hugo'].text(), 'Refresh queued')
        self.assertEqual(self.panel.source_refresh_buttons['locus'].text(), 'Refresh')
        self.assertIn('retained', self.panel.cache_status.text())
        self.assertIn('plugin update', self.panel.cache_status.text())
        self.assertIn('download', self.panel.source_refresh_buttons['hugo'].tooltip.lower())
        self.assertNotIn('download', self.panel.source_refresh_buttons['diagram'].tooltip.lower())
        self.assertEqual(self.book_metadata, {'#awards': ['Existing award']})

    def test_partial_failure_exception_continue_and_retry_only_failed_checked(self):
        self.select('diagram', 'hugo', 'locus', 'nebula')
        calls = []
        def refresh(key, name, *, confirmed):
            calls.append(key)
            if key == 'hugo': raise OSError('locked')
            return key != 'locus'
        with patch.dict(self.globals, run_source_cache_refresh_if_confirmed=refresh):
            self.panel._on_refresh_all_sources()
        self.assertEqual(calls, ['nebula', 'hugo', 'locus', 'diagram'])
        self.assertEqual(self.panel.refresh_all_button.text(), 'Retry Refresh all')
        self.assertEqual(self.panel.source_refresh_buttons['hugo'].text(), 'Retry Refresh')
        self.assertIn('Hugo Awards', self.panel.cache_status.text())
        self.assertIn('Locus Awards', self.panel.cache_status.text())
        self.panel.source_checkboxes['locus'].checked = False
        calls.clear()
        with patch.dict(self.globals, run_source_cache_refresh_if_confirmed=lambda key, name, **kw: calls.append(key) or True):
            self.panel._on_refresh_all_sources()
        self.assertEqual(calls, ['hugo'])
        self.assertEqual(self.panel.refresh_all_button.text(), 'Refresh all queued')
        self.assertEqual(self.book_metadata, {'#awards': ['Existing award']})

    def test_real_bulk_preserves_fallback_without_http_or_metadata_changes(self):
        with TemporaryDirectory() as directory:
            cache.set_cache_directory(directory)
            try:
                cache.save_source_cache('hugo', 1, records=[], source_urls=[], coverage={}, ttl_seconds=60)
                path = Path(directory) / 'hugo.json'
                before = (path.read_bytes(), path.stat().st_mtime_ns)
                self.select('hugo', 'diagram', 'bad_sex_fiction')
                with patch('urllib.request.urlopen', side_effect=AssertionError('network')):
                    self.panel._on_refresh_all_sources()
                self.assertEqual(before, (path.read_bytes(), path.stat().st_mtime_ns))
                self.assertTrue(cache.source_refresh_pending('hugo'))
                self.assertFalse(cache.source_refresh_pending('diagram'))
                self.assertFalse(cache.source_refresh_pending('bad_sex_fiction'))
            finally: cache._reset_runtime_state()
        self.assertEqual(self.book_metadata, {'#awards': ['Existing award']})
