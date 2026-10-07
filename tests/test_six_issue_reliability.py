"""Behavioral regressions for reliability review A1–A6; no live network."""
import json
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from datetime import datetime, timezone, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch, MagicMock
from awards import cache, cache_control, engine
from awards.source_registry import AwardSource
from awards.sources import balrog as b, dublin as d, medicis as m, mao_dun
from awards.presentation import format_possible_author_match_warning, default_award_row_checked
F = Path(__file__).parent / 'fixtures'
DX = (F/'dublin/years.xml').read_text(encoding='utf-8')
DY = d._parse_years(DX)
DR = tuple(r for y,u in DY.items() for r in d._parse_year((F/f'dublin/{y}.html').read_text(encoding='utf-8'),y,u))
MH = (F/'medicis/winners.html').read_text(encoding='utf-8')
MS = (F/'medicis/selection-2026.html').read_text(encoding='utf-8')
MR = m._parse_winners(MH)+m._parse_selection(MS)
BH = {url:(F/f'balrog/{year}.html').read_text(encoding='utf-8') for year,url in zip(range(1979,1986),b.SOURCE_PAGE_URLS)}
BR = tuple(r for year,url in zip(range(1979,1986),b.SOURCE_PAGE_URLS) for r in b._parse_year(BH[url],year))

def render_actual_dialog(report):
    """Execute the production dialog constructor with widget doubles."""
    import ast
    from types import SimpleNamespace
    from awards import presentation
    path = Path(__file__).resolve().parents[1] / 'award_selection_dialog.py'
    tree = ast.parse(path.read_text(encoding='utf-8'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'AwardSelectionDialog')
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '__init__')
    labels = []
    def label(text, parent):
        labels.append(text)
        return MagicMock()
    namespace = {name: getattr(presentation, name) for name in ('format_book_line', 'format_series_line', 'lookup_has_series_award')}
    namespace.update(QDialog=SimpleNamespace(__init__=lambda self, parent: None), QLabel=label,
                     Qt=SimpleNamespace(PlainText=0), QFrame=SimpleNamespace(Shape=SimpleNamespace(NoFrame=0)),
                     QDialogButtonBox=MagicMock(), _AwardMatchRow=MagicMock())
    namespace['QDialogButtonBox'].StandardButton = SimpleNamespace(Ok=1, Cancel=2, Close=4)
    for name in ('QVBoxLayout', 'QScrollArea', 'QWidget'):
        namespace[name] = MagicMock()
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(path), 'exec'), namespace)
    dialog = MagicMock()
    namespace['__init__'](dialog, None, report, '<placement> - <year> <award> - <category>', 'Review results', 'Book', 'Author', write_enabled=True)
    return labels, dialog

def render_actual_match_row(assessment, title, author):
    """Run actual row presentation/selection logic without Qt installation."""
    import ast
    from types import SimpleNamespace
    from awards import presentation, formatter
    from awards.qualifier import QualificationDecision
    path = Path(__file__).resolve().parents[1] / 'award_selection_dialog.py'
    tree = ast.parse(path.read_text(encoding='utf-8'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == '_AwardMatchRow')
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '__init__')
    labels = []
    def label(text, parent):
        labels.append(text)
        return MagicMock()
    checkbox = MagicMock()
    namespace = {name: getattr(presentation, name) for name in ('default_award_row_checked', 'format_possible_author_match_warning', 'match_row_scope_lines')}
    namespace.update(QWidget=SimpleNamespace(__init__=lambda self, parent: None),
                     QVBoxLayout=MagicMock(), QCheckBox=MagicMock(return_value=checkbox),
                     QLabel=label, Qt=SimpleNamespace(PlainText=0),
                     QualificationDecision=QualificationDecision,
                     format_award_result=formatter.format_award_result,
                     _apply_possible_author_match_style=MagicMock())
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(path), 'exec'), namespace)
    row = MagicMock()
    namespace['__init__'](row, assessment, formatter.DEFAULT_AWARD_OUTPUT_TEMPLATE, title, author)
    return labels, checkbox

class SixIssueTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();cache.set_cache_directory(self.temp.name)
        for mod in (b,d,m):mod._reset_runtime_state()
    def tearDown(self):
        for mod in (b,d,m):mod._reset_runtime_state()
        cache._reset_runtime_state();self.temp.cleanup()
    def save_dublin(self, stale=True, rows=DR, years=None):
        years=list(DY) if years is None else years
        cache.save_source_cache('dublin',d.CACHE_VERSION,records=[asdict(r) for r in rows],source_urls=[d.SITEMAP_URL]+[next(r.source_url for r in rows if r.award_year==y) for y in years],coverage={'years':years},ttl_seconds=d.CACHE_TTL_SECONDS,generated_at=datetime(2000,1,1,tzinfo=timezone.utc) if stale else None)
    def save_medicis(self, stale=True):
        cache.save_source_cache('medicis',m.CACHE_VERSION,records=[asdict(r) for r in MR],source_urls=m.SOURCE_URLS,coverage={'selection_rounds':['2026-first']},ttl_seconds=m.CACHE_TTL_SECONDS,generated_at=datetime(2000,1,1,tzinfo=timezone.utc) if stale else None)
    def save_balrog(self):
        cache.save_source_cache('balrog',b.CACHE_VERSION,records=[asdict(r) for r in BR],source_urls=b.SOURCE_PAGE_URLS,coverage={'min_year':1979,'max_year':1985},ttl_seconds=b.CACHE_TTL_SECONDS)
    def d_fetch(self,url):
        return DX if url==d.SITEMAP_URL else (F/f'dublin/{d._url_year(url)}.html').read_text(encoding='utf-8')
    def test_A1_refresh_returns_while_balrog_fetch_held_and_repeated_request_survives(self):
        self.save_balrog();cache_control.refresh_award_source_cache('balrog')
        entered=threading.Event();release=threading.Event()
        def fetch(url):
            entered.set();self.assertTrue(release.wait(3));return BH[url]
        pool=ThreadPoolExecutor(2)
        try:
            with patch.object(b,'_fetch_html',side_effect=fetch):
                old=pool.submit(b._get_records);self.assertTrue(entered.wait(2))
                before=(Path(self.temp.name)/'balrog.json').read_bytes()
                for _ in range(2):
                    self.assertTrue(pool.submit(cache_control.refresh_award_source_cache,'balrog').result(timeout=1))
                self.assertTrue(cache.source_refresh_pending('balrog'))
                release.set();old.result(timeout=3)
                self.assertTrue(cache.source_refresh_pending('balrog'))
                self.assertEqual((Path(self.temp.name)/'balrog.json').read_bytes(),before)
            with patch.object(b,'_fetch_html',side_effect=lambda url:BH[url]) as fetched:
                b._get_records();self.assertEqual(fetched.call_count,7)
            self.assertFalse(cache.source_refresh_pending('balrog'))
        finally:release.set();pool.shutdown(wait=True)
    def test_A1_bulk_queue_finishes_before_fetch_release(self):
        entered=threading.Event();release=threading.Event()
        def fetch(url):entered.set();self.assertTrue(release.wait(3));return BH[url]
        pool=ThreadPoolExecutor(2)
        try:
            with patch.object(b,'_fetch_html',side_effect=fetch):
                future=pool.submit(b._get_records);self.assertTrue(entered.wait(2))
                queued=pool.submit(lambda:[cache_control.refresh_award_source_cache(k) for k in ('balrog','dublin','medicis')])
                self.assertEqual(queued.result(timeout=1),[True]*3)
                self.assertTrue(cache.source_refresh_pending('balrog'));release.set();future.result(timeout=3)
                self.assertTrue(cache.source_refresh_pending('balrog'))
        finally:release.set();pool.shutdown(wait=True)
    def test_A2_latest_oldest_interior_missing_rejected(self):
        import xml.etree.ElementTree as ET
        for year in (1996,2010,2026):
            root=ET.fromstring(DX)
            for node in list(root):
                if str(year) in ''.join(node.itertext()):root.remove(node)
            with self.assertRaises(d.DublinSourceError):d._parse_years(ET.tostring(root,encoding='unicode'))
    def test_A2_truncated_disk_rejected(self):
        self.save_dublin(rows=tuple(r for r in DR if r.award_year<2026),years=list(range(1996,2026)))
        self.assertIsNone(d._load_disk())
    def test_A2_failed_truncated_refresh_keeps_gliff_and_full_disk(self):
        self.save_dublin();cache_control.refresh_award_source_cache('dublin');path=Path(self.temp.name)/'dublin.json';before=path.read_bytes()
        with patch.object(d,'_discover_years',return_value={y:u for y,u in DY.items() if y<2026}),patch.object(d,'_fetch_html',side_effect=self.d_fetch):
            self.assertEqual(d.lookup('Gliff','Ali Smith')[0].award_year,2026)
        self.assertEqual(path.read_bytes(),before);self.assertTrue(cache.source_refresh_pending('dublin'))
    def test_A2_valid_later_year_and_no_regression(self):
        future=datetime(2027,6,1,tzinfo=timezone.utc);url=DY[2026].replace('2026','2027')
        more=(replace(DR[0],award_year=2027,source_url=url,status='Nominated'),)
        with patch.object(d,'datetime') as clock:
            clock.now.return_value=future
            years={**DY,2027:url}
            import xml.etree.ElementTree as ET
            root=ET.fromstring(DX);ns='{http://www.sitemaps.org/schemas/sitemap/0.9}'
            node=ET.SubElement(root,ns+'url');ET.SubElement(node,ns+'loc').text=url
            self.assertEqual(d._parse_years(ET.tostring(root,encoding='unicode')),years)
            d._validate(DR+more,tuple(years))
            self.save_dublin(rows=DR+more,years=list(years));self.assertIsNotNone(d._load_disk())
            with patch.object(d,'_discover_years',return_value=DY),patch.object(d,'_fetch_html',side_effect=AssertionError('must reject before fetch')):
                self.assertEqual(len(d._get_records()),len(DR)+1)
            self.assertEqual(cache.load_source_cache('dublin',d.CACHE_VERSION)['coverage']['years'][-1],2027)
    def test_A3_two_overlapping_engine_searches_each_own_budget_both_completion_orders(self):
        for first in ('A','B'):
            barrier=threading.Barrier(4);gates={'A':threading.Event(),'B':threading.Event()};claims={'A':[],'B':[]};lock=threading.Lock()
            def lookup(title,author,series=None):
                barrier.wait(timeout=3);claim=cache.try_claim_stale_refresh()
                with lock:claims[title].append(claim)
                gates[title].wait(3);return []
            sources=tuple(AwardSource(k,k,lookup) for k in ('one','two'))
            pool=ThreadPoolExecutor(2)
            try:
                def run_lookup(title):
                    report = engine._lookup_awards_from_sources(title, 'Author', sources)
                    self.assertIsNone(cache._active_budget.get())
                    self.assertEqual([cache.try_claim_stale_refresh(), cache.try_claim_stale_refresh()], [True, True])
                    return report
                futures={t:pool.submit(run_lookup,t) for t in gates}
                gates[first].set();futures[first].result(timeout=4)
                other='B' if first=='A' else 'A';gates[other].set();futures[other].result(timeout=4)
                self.assertEqual([sum(claims[t]) for t in ('A','B')],[1,1])
                self.assertEqual([cache.try_claim_stale_refresh(),cache.try_claim_stale_refresh()],[True,True])
            finally:
                for gate in gates.values():gate.set()
                pool.shutdown(wait=True)
    def test_A3_nested_exception_and_explicit_bypass(self):
        with cache.lookup_refresh_budget():
            self.assertTrue(cache.try_claim_stale_refresh())
            with self.assertRaises(RuntimeError):
                with cache.lookup_refresh_budget():
                    self.assertTrue(cache.try_claim_stale_refresh());raise RuntimeError()
            self.assertFalse(cache.try_claim_stale_refresh())
            cache.request_source_refresh('dublin');self.assertTrue(cache.try_claim_stale_refresh('dublin'))
        self.assertTrue(cache.try_claim_stale_refresh())

    def test_A3_fresh_missing_invalid_archives_leave_worker_allowance_available(self):
        for state in ('fresh', 'missing', 'invalid'):
            with self.subTest(state=state):
                d._reset_runtime_state()
                path = Path(self.temp.name) / 'dublin.json'
                if state == 'fresh':
                    self.save_dublin(stale=False)
                elif state == 'missing':
                    path.unlink(missing_ok=True)
                else:
                    self.save_dublin(rows=tuple(r for r in DR if r.award_year < 2026), years=list(range(1996, 2026)))
                def lookup(title, author, series=None):
                    rows = d.lookup(title, author)
                    self.assertEqual([cache.try_claim_stale_refresh(), cache.try_claim_stale_refresh()], [True, False])
                    return rows
                with patch.object(d, '_fetch_html', side_effect=self.d_fetch) as fetch:
                    report = engine._lookup_awards_from_sources('Gliff', 'Ali Smith', (AwardSource('dublin', 'Dublin', lookup),))
                self.assertFalse(report.failures)
                self.assertEqual(len(report.assessments), 1)
                self.assertEqual(fetch.call_count == 0, state == 'fresh')

    def test_A3_worker_explicit_bypass_does_not_consume_optional_allowance(self):
        cache.request_source_refresh('dublin')
        def lookup(title, author, series=None):
            self.assertTrue(cache.try_claim_stale_refresh('dublin'))
            self.assertTrue(cache.try_claim_stale_refresh())
            self.assertTrue(cache.try_claim_stale_refresh('dublin'))
            self.assertFalse(cache.try_claim_stale_refresh())
            return []
        report = engine._lookup_awards_from_sources('Title', 'Author', (AwardSource('dublin', 'Dublin', lookup),))
        self.assertFalse(report.failures)
        self.assertTrue(cache.source_refresh_pending('dublin'))

    def test_A3_progress_exception_restores_outer_budget_and_standalone_state(self):
        def fail_progress(progress):
            raise RuntimeError('progress callback failed')
        with cache.lookup_refresh_budget() as outer:
            self.assertTrue(cache.try_claim_stale_refresh())
            with self.assertRaisesRegex(RuntimeError, 'progress callback failed'):
                engine._lookup_awards_from_sources('Title', 'Author', (), on_progress=fail_progress)
            self.assertIs(cache._active_budget.get(), outer)
            self.assertFalse(cache.try_claim_stale_refresh())
        self.assertIsNone(cache._active_budget.get())
        self.assertEqual([cache.try_claim_stale_refresh(), cache.try_claim_stale_refresh()], [True, True])
    def test_A4_deferred_dublin_refreshes_later_through_engine(self):
        self.save_dublin()
        def first(title,author,series=None):
            self.assertTrue(cache.try_claim_stale_refresh());return d.lookup(title,author)
        with patch.object(d,'_fetch_html',side_effect=AssertionError('deferred HTTP')):
            report=engine._lookup_awards_from_sources('Gliff','Ali Smith',(AwardSource('dublin','Dublin',first),));self.assertEqual(len(report.assessments),1)
        with patch.object(d,'_fetch_html',side_effect=self.d_fetch) as fetch:
            report=engine.lookup_awards('Gliff','Ali Smith',enabled_source_keys=['dublin']);self.assertFalse(report.failures);self.assertGreater(fetch.call_count,1)
    def test_A4_second_mutable_source_deferral_ttl_expiry_and_fresh_warm(self):
        self.save_medicis()
        with cache.lookup_refresh_budget():
            cache.try_claim_stale_refresh()
            with patch.object(m,'_fetch_html',side_effect=AssertionError('deferred')):m.lookup('The Mars Room','Rachel Kushner')
        with patch.object(m,'_fetch_html',side_effect=lambda u:MH if u==m.WINNERS_URL else MS) as fetch:
            engine.lookup_awards('The Mars Room','Rachel Kushner',enabled_source_keys=['medicis']);self.assertEqual(fetch.call_count,2)
        with patch.object(m,'_fetch_html',side_effect=AssertionError('fresh')):m.lookup('The Mars Room','Rachel Kushner')
        payload=cache.load_source_cache('medicis',m.CACHE_VERSION)
        future=datetime.now(timezone.utc)+timedelta(days=10)
        original=cache.cache_is_fresh
        with patch.object(cache,'cache_is_fresh',side_effect=lambda p:original(p,now=future)),patch.object(m,'_fetch_html',side_effect=lambda u:MH if u==m.WINNERS_URL else MS) as fetch:
            m.lookup('The Mars Room','Rachel Kushner');self.assertEqual(fetch.call_count,2)
    def test_A4_failed_optional_retry_cooldown_and_explicit_bypass(self):
        self.save_medicis()
        with patch.object(cache.time,'monotonic',return_value=100),patch.object(m,'_fetch_html',side_effect=m.MedicisSourceError('offline')) as fetch:
            m.lookup('The Mars Room','Rachel Kushner');m.lookup('The Mars Room','Rachel Kushner');self.assertEqual(fetch.call_count,1)
        with patch.object(cache.time,'monotonic',return_value=161),patch.object(m,'_fetch_html',side_effect=m.MedicisSourceError('offline')) as fetch:
            m.lookup('The Mars Room','Rachel Kushner');self.assertEqual(fetch.call_count,1)
            cache_control.refresh_award_source_cache('medicis');m.lookup('The Mars Room','Rachel Kushner');self.assertEqual(fetch.call_count,2)
    def test_A5_zero_matching_mixed_and_disabled_refresh_diagnostics(self):
        self.save_balrog();cache_control.refresh_award_source_cache('balrog')
        with patch.object(b,'_fetch_html',side_effect=b.BalrogSourceError('offline')):
            empty=engine.lookup_awards('Not a book','Nobody',enabled_source_keys=['balrog'])
            self.assertFalse(empty.assessments);self.assertFalse(empty.failures);self.assertEqual(len(empty.diagnostics),1)
            row=BR[0];matching=engine.lookup_awards(row.work_title,row.work_author,enabled_source_keys=['balrog'])
            self.assertTrue(matching.assessments);self.assertEqual(len(matching.diagnostics),1)
            mixed=engine._lookup_awards_from_sources(row.work_title,row.work_author,(AwardSource('balrog','Balrog',b.lookup),AwardSource('stub','Stub',lambda *a,**k:[])))
            self.assertEqual(len(mixed.diagnostics),1)
        self.assertFalse(engine.lookup_awards('Nothing','Nobody',enabled_source_keys=[]).diagnostics)
        with patch.object(b,'_fetch_html',side_effect=lambda u:BH[u]):
            self.assertFalse(engine.lookup_awards('Nothing','Nobody',enabled_source_keys=['balrog']).diagnostics)

    def test_A5_actual_dialog_shows_failed_refresh_with_empty_and_matching_fallback(self):
        self.save_balrog()
        cache_control.refresh_award_source_cache('balrog')
        with patch.object(b, '_fetch_html', side_effect=b.BalrogSourceError('offline')):
            for title, author in (('Not a book', 'Nobody'), (BR[0].work_title, BR[0].work_author)):
                report = engine.lookup_awards(title, author, enabled_source_keys=['balrog'])
                self.assertEqual(bool(report.assessments), title != 'Not a book')
                self.assertFalse(report.failures)
                self.assertEqual(len(report.diagnostics), 1)
                labels, dialog = render_actual_dialog(report)
                text = '\n'.join(labels)
                self.assertEqual(text.count('Requested refresh did not complete'), 1)
                self.assertIn('Balrog Award', text)
                self.assertIn('retained data was used', text)
                self.assertEqual(len(dialog._rows), len(report.assessments))
                self.assertTrue(all('Requested refresh' not in detail for a in report.assessments for detail in a.result.source_details))
        with patch.object(b, '_fetch_html', side_effect=lambda url: BH[url]):
            report = engine.lookup_awards('Not a book', 'Nobody', enabled_source_keys=['balrog'])
        self.assertFalse(report.diagnostics)
        labels, _ = render_actual_dialog(report)
        self.assertIn('No matching award records were found. Nothing will be changed.', labels)
        self.assertFalse(any('Source update status:' in text for text in labels))

    def test_A5_mixed_results_failures_and_multiple_diagnostics_keep_source_order(self):
        self.save_balrog()
        self.save_medicis(stale=False)
        for key in ('balrog', 'medicis'):
            cache_control.refresh_award_source_cache(key)
        cache.request_source_refresh('failed')
        def failed(*args, **kwargs):
            raise RuntimeError('actual source failure')
        sources = (AwardSource('medicis', 'Medicis', m.lookup),
                   AwardSource('successful', 'Successful', lambda *a, **k: [DR[0]]),
                   AwardSource('balrog', 'Balrog', b.lookup),
                   AwardSource('failed', 'Failed', failed))
        with patch.object(b, '_fetch_html', side_effect=b.BalrogSourceError('offline')), patch.object(m, '_fetch_html', side_effect=m.MedicisSourceError('offline')):
            report = engine._lookup_awards_from_sources('Not a book', 'Nobody', sources)
        self.assertEqual([a.result for a in report.assessments], [DR[0]])
        self.assertEqual([d.source_name for d in report.diagnostics], ['Medicis', 'Balrog'])
        self.assertEqual([f.source_name for f in report.failures], ['Failed'])
        labels, _ = render_actual_dialog(report)
        updates = next(text for text in labels if text.startswith('Source update status:'))
        self.assertEqual(updates.count('Medicis —'), 1)
        self.assertEqual(updates.count('Balrog —'), 1)
        self.assertEqual(updates.count('Requested refresh did not complete'), 2)
        self.assertNotIn('actual source failure', updates)
        self.assertTrue(any('Source problems:' in text and 'actual source failure' in text for text in labels))
        self.assertFalse(engine.lookup_awards('Not a book', 'Nobody', enabled_source_keys=[]).diagnostics)

    def test_A5_new_request_during_engine_retrieval_remains_visible_after_old_completion(self):
        self.save_balrog()
        cache_control.refresh_award_source_cache('balrog')
        entered, release = threading.Event(), threading.Event()
        def fetch(url):
            entered.set()
            self.assertTrue(release.wait(3))
            return BH[url]
        pool = ThreadPoolExecutor(1)
        try:
            with patch.object(b, '_fetch_html', side_effect=fetch):
                future = pool.submit(engine.lookup_awards, 'Not a book', 'Nobody', enabled_source_keys=['balrog'])
                self.assertTrue(entered.wait(2))
                cache_control.refresh_award_source_cache('balrog')
                release.set()
                report = future.result(timeout=4)
            self.assertTrue(cache.source_refresh_pending('balrog'))
            self.assertFalse(report.failures)
            self.assertEqual(len(report.diagnostics), 1)
            labels, _ = render_actual_dialog(report)
            self.assertTrue(any('remains pending' in text for text in labels))
            with patch.object(b, '_fetch_html', side_effect=lambda url: BH[url]):
                self.assertFalse(engine.lookup_awards('Not a book', 'Nobody', enabled_source_keys=['balrog']).diagnostics)
        finally:
            release.set()
            pool.shutdown(wait=True)
    def test_A6_scope_notes_and_author_evidence(self):
        note='Confirm the awarded revised edition: 白鹿原（修订本）'
        row=replace(DR[0],work_author='陈忠实',identity_confirmation_required=True,source_identity_note=note)
        text=format_possible_author_match_warning(row,'陈忠实');self.assertIn(note,text);self.assertNotIn('POSSIBLE AUTHOR MATCH',text)
        med=next(r for r in MR if r.year==2024 and r.category=='Essai')
        with patch.object(m,'_get_records',return_value=MR):r=m.lookup(med.title,med.author)[0]
        self.assertIn(r.source_identity_note,format_possible_author_match_warning(r,med.author))
        author=replace(row,work_author='John A. Smith',source_identity_note='Confirm author identity.')
        text=format_possible_author_match_warning(author,'John Smith');self.assertIn('John A. Smith',text);self.assertIn('John Smith',text)
        self.assertFalse(default_award_row_checked(qualifies=True,identity_confirmation_required=True))
        self.assertIsNone(format_possible_author_match_warning(DR[0],DR[0].work_author))
    def test_A1_child_executor_publication_cannot_consume_new_request(self):
        from types import SimpleNamespace
        entered=threading.Event();release=threading.Event()
        mod=SimpleNamespace(SOURCE_KEY='child_source',_reset_runtime_state=lambda:None)
        def retrieve():
            def child():
                entered.set();self.assertTrue(release.wait(3))
                cache.save_cache_entry('child_source','years','2026',1,records=[],source_urls=[],coverage={},ttl_seconds=60)
            with ThreadPoolExecutor(1) as pool:pool.submit(child).result(timeout=4)
        retrieve=cache.source_runtime_guard(mod,retrieve)
        pool=ThreadPoolExecutor(1)
        try:
            future=pool.submit(retrieve);self.assertTrue(entered.wait(2))
            cache.request_source_refresh('child_source');release.set();future.result(timeout=4)
            self.assertTrue(cache.source_refresh_pending('child_source'))
            self.assertIsNone(cache.load_cache_entry('child_source','years','2026',1))
        finally:release.set();pool.shutdown(wait=True)
    def test_A4_all_network_sources_use_shared_guard(self):
        from awards.source_registry import AWARD_SOURCES
        import inspect
        for source in AWARD_SOURCES:
            if source.key in cache_control.BUNDLED_SOURCE_KEYS:continue
            self.assertTrue(hasattr(source.lookup,'__wrapped__'),source.key)
            module = inspect.getmodule(source.lookup)
            self.assertEqual(module.SOURCE_KEY, source.key)
            self.assertIs(inspect.getclosurevars(source.lookup).nonlocals['module'], module)
            self.assertIs(source.lookup.__code__, d.lookup.__code__)

    def test_A4_dublin_ttl_expiry_refreshes_ram_without_resetting_fresh_sources(self):
        self.save_dublin(stale=False)
        self.save_medicis(stale=False)
        with patch.object(d, '_fetch_html', side_effect=AssertionError('fresh Dublin HTTP')), patch.object(m, '_fetch_html', side_effect=AssertionError('fresh Medicis HTTP')):
            self.assertTrue(d.lookup('Gliff', 'Ali Smith'))
            self.assertTrue(m.lookup('The Mars Room', 'Rachel Kushner'))
        with patch.object(d, '_reset_runtime_state', wraps=d._reset_runtime_state) as reset_d, patch.object(m, '_reset_runtime_state', wraps=m._reset_runtime_state) as reset_m:
            with patch.object(d, '_fetch_html', side_effect=AssertionError('warm HTTP')):
                self.assertTrue(d.lookup('Gliff', 'Ali Smith'))
            self.assertEqual((reset_d.call_count, reset_m.call_count), (0, 0))
            original = cache.cache_is_fresh
            future = datetime.now(timezone.utc) + timedelta(days=10)
            with patch.object(cache, 'cache_is_fresh', side_effect=lambda payload: original(payload, now=future)), patch.object(d, '_fetch_html', side_effect=self.d_fetch) as fetch:
                report = engine.lookup_awards('Gliff', 'Ali Smith', enabled_source_keys=['dublin'])
            self.assertFalse(report.failures)
            self.assertTrue(report.assessments)
            self.assertGreater(fetch.call_count, 1)
            self.assertEqual(reset_d.call_count, 1)
            self.assertEqual(reset_m.call_count, 0)

    def test_A4_failed_automatic_medicis_refresh_keeps_disk_then_retry_succeeds(self):
        self.save_medicis()
        path = Path(self.temp.name) / 'medicis.json'
        before = path.read_bytes()
        with patch.object(cache.time, 'monotonic', return_value=100), patch.object(m, '_fetch_html', side_effect=m.MedicisSourceError('offline')) as fetch:
            for _ in range(3):
                report = engine.lookup_awards('The Mars Room', 'Rachel Kushner', enabled_source_keys=['medicis'])
                self.assertTrue(report.assessments)
                self.assertFalse(report.failures)
            self.assertEqual(fetch.call_count, 1)
        self.assertEqual(path.read_bytes(), before)
        with patch.object(cache.time, 'monotonic', return_value=161), patch.object(m, '_fetch_html', side_effect=lambda url: MH if url == m.WINNERS_URL else MS) as fetch:
            report = engine.lookup_awards('The Mars Room', 'Rachel Kushner', enabled_source_keys=['medicis'])
            self.assertEqual(fetch.call_count, 2)
            self.assertTrue(report.assessments)
        self.assertTrue(cache.cache_is_fresh(cache.load_source_cache('medicis', m.CACHE_VERSION)))
        with patch.object(m, '_fetch_html', side_effect=AssertionError('successful RAM must stay fresh')):
            self.assertTrue(m.lookup('The Mars Room', 'Rachel Kushner'))

    def test_A4_explicit_medicis_failure_retries_despite_cooldown_and_consumed_budget(self):
        self.save_medicis(stale=False)
        self.assertTrue(m.lookup('The Mars Room', 'Rachel Kushner'))
        cache_control.refresh_award_source_cache('medicis')
        path = Path(self.temp.name) / 'medicis.json'
        before = path.read_bytes()
        with cache.lookup_refresh_budget(), patch.object(cache.time, 'monotonic', return_value=100):
            self.assertTrue(cache.try_claim_stale_refresh())
            with patch.object(m, '_fetch_html', side_effect=m.MedicisSourceError('offline')):
                self.assertTrue(m.lookup('The Mars Room', 'Rachel Kushner'))
            self.assertTrue(cache.source_refresh_pending('medicis'))
            self.assertEqual(path.read_bytes(), before)
            with patch.object(m, '_fetch_html', side_effect=lambda url: MH if url == m.WINNERS_URL else MS) as fetch:
                self.assertTrue(m.lookup('The Mars Room', 'Rachel Kushner'))
                self.assertEqual(fetch.call_count, 2)
            self.assertFalse(cache.source_refresh_pending('medicis'))
            self.assertFalse(cache.try_claim_stale_refresh())
    def test_A6_real_mao_dun_revised_edition_note(self):
        html=(F/'mao_dun/winners.html').read_text(encoding='utf-8')
        rows=mao_dun._parse_winners(html)
        with patch.object(mao_dun,'_get_records',return_value=rows):
            row=mao_dun.lookup('白鹿原（修订本）','陈忠实')[0]
        warning=format_possible_author_match_warning(row,'陈忠实')
        self.assertTrue(row.identity_confirmation_required)
        self.assertIn(row.source_identity_note,warning)
        self.assertIn('IDENTITY CONFIRMATION REQUIRED',warning)
        self.assertFalse(default_award_row_checked(qualifies=True,identity_confirmation_required=row.identity_confirmation_required))

    def test_A6_actual_rows_display_scope_reason_in_label_and_tooltip_unchecked(self):
        rows = mao_dun._parse_winners((F/'mao_dun/winners.html').read_text(encoding='utf-8'))
        with patch.object(mao_dun, '_get_records', return_value=rows):
            mao = mao_dun.lookup('白鹿原（修订本）', '陈忠实')[0]
        volume = next(r for r in MR if r.year == 2024 and r.category == 'Essai')
        with patch.object(m, '_get_records', return_value=MR):
            medicis = m.lookup(volume.title, volume.author)[0]
        for result in (mao, medicis):
            with self.subTest(award=result.award_name):
                assessment = engine.assess_award_result(result)
                labels, checkbox = render_actual_match_row(assessment, result.work_title, result.work_author)
                warning = format_possible_author_match_warning(result, result.work_author)
                self.assertEqual(labels.count(warning), 1)
                self.assertIn(result.source_identity_note, warning)
                self.assertNotIn('POSSIBLE AUTHOR MATCH', warning)
                self.assertNotIn('Source lists', warning)
                tooltip = checkbox.setToolTip.call_args.args[0]
                self.assertIn(warning, tooltip)
                self.assertIn(result.source_url, tooltip)
                checkbox.setChecked.assert_called_once_with(False)
                self.assertIs(assessment.result, result)

    def test_A6_actual_author_warning_and_exact_defaults_are_structured(self):
        base = next(r for r in DR if r.status == 'Winner')
        for note in ('Confirm author identity.', 'Confirm the edition instead.'):
            result = replace(base, work_author='John A. Smith', identity_confirmation_required=True, source_identity_note=note)
            labels, checkbox = render_actual_match_row(engine.assess_award_result(result), result.work_title, 'John Smith')
            warning = format_possible_author_match_warning(result, 'John Smith')
            self.assertEqual(labels.count(warning), 1)
            self.assertIn('John A. Smith', warning)
            self.assertIn('John Smith', warning)
            self.assertIn(warning, checkbox.setToolTip.call_args.args[0])
            checkbox.setChecked.assert_called_once_with(False)
        exact = replace(base, identity_confirmation_required=False, source_identity_note=None)
        assessment = engine.assess_award_result(exact)
        labels, checkbox = render_actual_match_row(assessment, exact.work_title, exact.work_author)
        self.assertFalse(any('IDENTITY CONFIRMATION REQUIRED' in text for text in labels))
        self.assertNotIn('Confirm author identity.', checkbox.setToolTip.call_args.args[0])
        checkbox.setChecked.assert_called_once_with(True)

    def test_A3_internal_source_executor_inherits_own_engine_budget(self):
        from types import SimpleNamespace
        mod=SimpleNamespace(SOURCE_KEY='child_budget',_reset_runtime_state=lambda:None)
        def lookup(title,author,series=None):
            with ThreadPoolExecutor(3) as pool:
                claims=list(pool.map(lambda _:cache.try_claim_stale_refresh('child_budget'),range(3)))
            self.assertEqual(sum(claims),1)
            return []
        lookup=cache.source_runtime_guard(mod,lookup)
        report=engine._lookup_awards_from_sources('Title','Author',(AwardSource('child_budget','Child budget',lookup),))
        self.assertFalse(report.failures)
