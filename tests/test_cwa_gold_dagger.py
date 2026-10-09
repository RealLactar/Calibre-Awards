"""Offline official HTML and production cache/engine regressions for Gold Dagger."""
import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from unittest.mock import patch

from awards import cache, cache_control, engine
from awards.presentation import default_award_row_checked
from awards.qualifier import QualificationDecision, qualify_award_result
from awards.registry import find_award_policy
from awards.sources import cwa_gold_dagger as c

F = Path(__file__).parent / 'fixtures/cwa_gold_dagger'
PAGES = {i: (F / f'page-{i}.html').read_text(encoding='utf-8') for i in range(1, 17)}
HOME = (F / 'home.html').read_text(encoding='utf-8')
PRE = (F / 'predecessor.html').read_text(encoding='utf-8')
SUP = (F / 'supplement-2021.html').read_text(encoding='utf-8')


def fetch(url):
    if url == c.SOURCE_HOME_URL:
        return HOME
    if url == c.PREDECESSOR_URL:
        return PRE
    if url == c.SUPPLEMENT_URL:
        return SUP
    return PAGES[next(i for i in PAGES if c._page_url(i) == url)]


with patch.object(c, '_fetch_html', side_effect=fetch):
    ROWS = c._load_live_archive()


class CWAGoldDaggerTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        cache.set_cache_directory(self.temp.name)
        c._reset_runtime_state()

    def tearDown(self):
        c._reset_runtime_state()
        cache._reset_runtime_state()
        self.temp.cleanup()

    def save(self, rows=ROWS, stale=False):
        cache.save_source_cache(c.SOURCE_KEY, c.CACHE_VERSION, records=[asdict(r) for r in rows],
                                source_urls=c.SOURCE_URLS, coverage=c._coverage(rows), ttl_seconds=c.CACHE_TTL_SECONDS,
                                generated_at=datetime(2000, 1, 1, tzinfo=timezone.utc) if stale else None)

    def lookup(self, title, author):
        with patch.object(c, '_get_records', return_value=ROWS):
            return c.lookup(title, author)

    def test_minified_live_pagination_counter_does_not_absorb_page_links(self):
        html = PAGES[1]
        rows, total = c._parse_listing(html.replace('>\n<', '><'))
        self.assertEqual(total, 16)
        self.assertEqual(len(rows), 12)

    def test_live_shifted_pagination_recovers_reviewed_individual_results(self):
        def shifted(url):
            for i in PAGES:
                if url == c._page_url(i) and (F / f'shifting-page-{i}.html').exists():
                    return (F / f'shifting-page-{i}.html').read_text(encoding='utf-8')
            detail = F / ('recover-' + url.rstrip('/').split('/')[-1] + '.html')
            if detail.exists():
                return detail.read_text(encoding='utf-8')
            return fetch(url)
        with patch.object(c, '_fetch_html', side_effect=shifted) as requests:
            rows = c._load_live_archive()
        self.assertEqual(len(rows), 199)
        self.assertEqual(sum(r.status == 'Winner' for r in rows), 72)
        self.assertEqual(requests.call_count, 27)
        self.assertTrue({_identity_test(r) for r in ROWS}.issubset({_identity_test(r) for r in rows}))

    def test_missing_detail_failure_preserves_prior_cache_and_pending_request(self):
        self.save()
        cache_control.refresh_award_source_cache(c.SOURCE_KEY)
        original_cards=c._cards
        def incomplete_cards(root):
            return tuple(r for r in original_cards(root) if r.title != 'The Little Walls')
        def unavailable(url):
            if url == 'https://thecwa.co.uk/past-winners/the-little-walls/':
                raise c.CWAGoldDaggerSourceError('individual page unavailable')
            return fetch(url)
        with patch.object(c, '_fetch_html', side_effect=unavailable), patch.object(c, '_cards', side_effect=incomplete_cards):
            report=engine.lookup_awards('The Invited','Jennifer McMahon',enabled_source_keys=[c.SOURCE_KEY])
        self.assertFalse(report.failures)
        self.assertEqual(len(report.diagnostics),1)
        self.assertTrue(cache.source_refresh_pending(c.SOURCE_KEY))
        self.assertEqual(c._load_disk()[0],ROWS)

    def test_changed_recovery_detail_is_rejected(self):
        partial=tuple(r for r in ROWS if r.year!=1955)
        html=(F/'detail-1955.html').read_text(encoding='utf-8').replace('Winston Graham','Different Author')
        with patch.object(c,'_fetch_html',return_value=html), self.assertRaises(c.CWAGoldDaggerSourceError):
            c._recover_missing(partial)

    def test_previous_additional_record_recovered_from_live_detail(self):
        extra=c._Row(2015,'The Silkworm','Robert Galbraith','Shortlisted','https://thecwa.co.uk/past-winners/the-silkworm/','Gold Dagger')
        with patch.object(c,'_fetch_html',return_value='unused') as request,patch.object(c,'_parse_detail',return_value=extra):
            rows=c._recover_missing(ROWS,ROWS+(extra,))
        self.assertIn(extra,rows)
        request.assert_called_once_with(extra.source_url)

    def test_verified_1963_author_alias_preserves_source_credit_and_provenance(self):
        result=self.lookup('The Spy Who Came in from the Cold','John le Carré')[0]
        self.assertEqual((result.award_year,result.status,result.work_author),(1963,'Winner','John le Carr'))
        self.assertEqual(result.source_url,c._ALIAS_SOURCE_URL)
        self.assertIn(c._ALIAS_EVIDENCE_URL,' '.join(result.source_details))
        self.assertEqual(qualify_award_result(result,find_award_policy(result)).decision,QualificationDecision.QUALIFIES)
        self.assertEqual(len(self.lookup(result.work_title,'John le Carr')),1)
        evidence=c._tree((F/'le-carre-bibliography.html').read_text(encoding='utf-8')).text()
        self.assertIn('John le Carré',evidence)
        self.assertIn('September 1963',evidence)

    def test_author_alias_is_restricted_to_the_exact_1963_winning_record(self):
        row=next(r for r in ROWS if r.year==1963)
        for field,value in [('year',1964),('status','Shortlisted'),('title','Another Book'),
                            ('author','John Carr'),('historical_name','Silver Dagger'),
                            ('source_url','https://thecwa.co.uk/past-winners/another-book/')]:
            altered=replace(row,**{field:value})
            self.assertFalse(c._author_matches(altered,'John le Carré'),field)
        self.assertEqual(self.lookup(row.title,'Different Author'),[])
        self.assertEqual(self.lookup('Tinker Tailor Soldier Spy','John le Carré'),[])
        self.assertNotEqual(c._author_key('John le Carré'),c._author_key('John le Carr'))

    def test_verified_counts_and_full_winner_years(self):
        self.assertEqual(len(ROWS), 194)
        self.assertEqual(sum(r.status == 'Winner' for r in ROWS), 72)
        self.assertEqual({r.year for r in ROWS if r.status == 'Winner'}, set(range(1955, 2027)))
        for status, count in [('Shortlisted', 90), ('Longlisted', 29), ('Highly Commended', 3)]:
            self.assertEqual(sum(r.status == status for r in ROWS), count)

    def test_predecessor_historical_name_year_and_provenance(self):
        r = self.lookup('The Little Walls', 'Winston Graham')[0]
        self.assertEqual((r.award_year, r.status, r.category, r.rank), (1955, 'Winner', None, None))
        self.assertEqual(r.source_url, 'https://thecwa.co.uk/past-winners/the-little-walls/')
        self.assertIn('Crossed Herrings Dagger', ' '.join(r.source_details))
        self.assertIn('Crossed Red Herrings', ' '.join(r.source_details))
        self.assertEqual(qualify_award_result(r, find_award_policy(r)).decision, QualificationDecision.QUALIFIES)

    def test_recent_winner_and_missing_2021_supplement(self):
        for title, author, year, url in [('The Death of Us', 'Abigail Dean', 2026, 'https://thecwa.co.uk/past-winners/the-death-of-us/'),
                                         ('We Begin at the End', 'Chris Whitaker', 2021, c.SUPPLEMENT_URL)]:
            r = self.lookup(title, author)[0]
            self.assertEqual((r.award_year, r.status, r.source_url), (year, 'Winner', url))
            self.assertTrue(default_award_row_checked(qualifies=True, identity_confirmation_required=False))

    def test_explicit_review_distinctions_preserved_unchecked(self):
        for title, author, status in [('Not Quite Dead Yet', 'Holly Jackson', 'Shortlisted'),
                                      ('A Case Of Life And Limb', 'Sally Smith', 'Longlisted'),
                                      ('Blacktop Wasteland', 'S A Cosby', 'Highly Commended')]:
            r = self.lookup(title, author)[0]
            self.assertEqual(r.status, status)
            self.assertIsNone(r.rank)
            self.assertEqual(qualify_award_result(r, find_award_policy(r)).decision, QualificationDecision.REVIEW)
            self.assertFalse(default_award_row_checked(qualifies=False, identity_confirmation_required=False))

    def test_longlist_announcement_is_official_provenance(self):
        r = self.lookup('A Case Of Life And Limb', 'Sally Smith')[0]
        self.assertEqual(r.source_url, c.SOURCE_HOME_URL)
        self.assertEqual(r.award_year, 2026)

    def test_wrong_author_and_authors_other_books_do_not_match(self):
        for title, author in [('The Death of Us', 'Other Author'), ('Girl A', 'Abigail Dean'),
                              ('Poldark', 'Winston Graham'), ('The Little Walls', 'Winston Churchill')]:
            self.assertEqual(self.lookup(title, author), [])

    def test_normalization_and_cwa_initial_variants(self):
        self.assertEqual(len(self.lookup(' the death of us ', 'ABIGAIL DEAN')), 1)
        self.assertEqual(len(self.lookup('King of Ashes', 'S. A. Cosby')), 1)
        self.assertEqual(self.lookup('The Death', 'Abigail Dean'), [])

    def test_duplicate_winner_and_shortlist_longlist_collapse_to_winner(self):
        winner = next(r for r in ROWS if r.title == 'The Death of Us')
        merged = c._merge((replace(winner, status='Shortlisted'), winner, winner, replace(winner, status='Longlisted')))
        self.assertEqual(merged, (winner,))
        self.assertEqual(sum(r.title == 'Raven Black' for r in ROWS), 1)
        self.assertEqual(sum(r.title == 'Troubled Blood' for r in ROWS), 1)

    def test_no_guess_for_undated_shortlist(self):
        self.assertEqual(self.lookup('Bluebird, Bluebird', 'Attica Locke'), [])
        with self.assertRaises(c.CWAGoldDaggerSourceError):
            c._parse_detail((F / 'undated.html').read_text(encoding='utf-8'), c._UNDATED_URL)

    def test_other_daggers_excluded_without_substring_matching(self):
        for name in ('Silver Dagger', 'Diamond Dagger', 'Ian Fleming Steel Dagger', 'New Blood Dagger',
                     'Historical Dagger', 'Crime Fiction in Translation Dagger', 'ALCS Gold Dagger for Non-fiction'):
            root = c._tree(PAGES[1].replace('<br>Gold Dagger<br>', f'<br>{name}<br>'))
            self.assertEqual(c._cards(root), ())
            detail = (F / 'detail.html').read_text(encoding='utf-8').replace('Gold Dagger 2026', name + ' 2026')
            with self.assertRaises(c.CWAGoldDaggerSourceError):
                c._parse_detail(detail, 'https://thecwa.co.uk/past-winners/the-death-of-us/')

    def test_pagination_fetches_all_pages_and_sources(self):
        with patch.object(c, '_fetch_html', side_effect=fetch) as network:
            self.assertEqual(c._load_live_archive(), ROWS)
            self.assertEqual(network.call_count, 19)
            self.assertEqual([x.args[0] for x in network.call_args_list[:16]], [c._page_url(i) for i in range(1, 17)])

    def test_missing_next_link_or_wrong_counter_rejected(self):
        for html in [PAGES[1].replace('nextpostslink', 'otherlink'), PAGES[1].replace('Page 1 of 16', 'Page 1 of 15')]:
            with self.assertRaises(c.CWAGoldDaggerSourceError):
                c._parse_listing(html)

    def test_unfiltered_or_foreign_pagination_rejected(self):
        html = PAGES[1].replace(c._page_url(2), 'https://example.org/page/2/')
        with self.assertRaises(c.CWAGoldDaggerSourceError):
            c._parse_listing(html)

    def test_missing_oldest_interior_or_newest_winner_rejected(self):
        for year in (1955, 1990, 2026):
            with self.assertRaises(c.CWAGoldDaggerSourceError):
                c._validate(tuple(r for r in ROWS if not (r.year == year and r.status == 'Winner')))

    def test_incomplete_annual_distinctions_rejected(self):
        for status in ('Shortlisted', 'Longlisted', 'Highly Commended'):
            removed = next(r for r in ROWS if r.status == status)
            with self.assertRaises(c.CWAGoldDaggerSourceError):
                c._validate(tuple(r for r in ROWS if r != removed))

    def test_later_partial_published_cycle_accepted_without_inventing_winner(self):
        later = _later_row()
        c._validate(ROWS + (later,))
        self.assertFalse(any(r.year == 2027 and r.status == 'Winner' for r in ROWS + (later,)))
        with self.assertRaises(c.CWAGoldDaggerSourceError):
            c._validate(ROWS, ROWS + (later,))

    def test_calendar_change_does_not_require_unpublished_year(self):
        self.save()
        with patch.object(cache, 'datetime', wraps=datetime) as clock:
            clock.now.return_value = datetime(2027, 1, 1, tzinfo=timezone.utc)
            c._validate(ROWS)
            self.assertIsNotNone(c._load_disk())

    def test_invalid_provenance_status_and_historical_label_rejected(self):
        r = ROWS[0]
        for field, value in [('source_url', 'https://example.org/result/'), ('historical_name', 'Gold Dagger for Non-fiction'),
                             ('status', 'Second place'), ('year', True), ('author', '')]:
            with self.assertRaises(c.CWAGoldDaggerSourceError):
                c._validate((replace(r, **{field: value}),) + ROWS[1:])

    def test_fresh_disk_and_warm_ram_avoid_network(self):
        self.save()
        with patch.object(c, '_fetch_html', side_effect=AssertionError('network')):
            self.assertEqual(len(c.lookup('The Little Walls', 'Winston Graham')), 1)
            self.assertEqual(len(c.lookup('The Death of Us', 'Abigail Dean')), 1)

    def test_initial_fetch_saves_complete_validated_cache(self):
        with patch.object(c, '_fetch_html', side_effect=fetch):
            self.assertEqual(len(c.lookup('The Death of Us', 'Abigail Dean')), 1)
        self.assertEqual(c._load_disk()[0], ROWS)

    def test_truncated_disk_cannot_masquerade_as_complete(self):
        self.save(tuple(r for r in ROWS if r.year != 2026))
        self.assertIsNone(c._load_disk())

    def test_failed_requested_refresh_retains_fallback_and_diagnostic_zero_matches(self):
        self.save()
        path = Path(self.temp.name) / 'cwa_gold_dagger.json'
        before = path.read_bytes()
        self.assertTrue(cache_control.refresh_award_source_cache(c.SOURCE_KEY))
        with patch.object(c, '_fetch_html', side_effect=c.CWAGoldDaggerSourceError('outage')):
            report = engine.lookup_awards('Unrelated Book', 'Unrelated Author', enabled_source_keys=[c.SOURCE_KEY])
            self.assertEqual(report.assessments, ())
            self.assertEqual(len(report.diagnostics), 1)
            self.assertEqual(report.failures, ())
        self.assertEqual(path.read_bytes(), before)
        self.assertTrue(cache.source_refresh_pending(c.SOURCE_KEY))

    def test_incomplete_requested_refresh_preserves_matching_fallback_then_recovers(self):
        self.save()
        cache_control.refresh_award_source_cache(c.SOURCE_KEY)
        with patch.object(c, '_load_live_archive', return_value=ROWS[:-1]):
            report = engine.lookup_awards('The Death of Us', 'Abigail Dean', enabled_source_keys=[c.SOURCE_KEY])
        self.assertEqual(len(report.assessments), 1)
        self.assertEqual(len(report.diagnostics), 1)
        self.assertTrue(cache.source_refresh_pending(c.SOURCE_KEY))
        with patch.object(c, '_fetch_html', side_effect=fetch):
            report = engine.lookup_awards('The Death of Us', 'Abigail Dean', enabled_source_keys=[c.SOURCE_KEY])
        self.assertFalse(cache.source_refresh_pending(c.SOURCE_KEY))
        self.assertEqual(report.diagnostics, ())

    def test_previously_accepted_later_year_not_lost_on_refresh(self):
        later = ROWS + (_later_row(),)
        self.save(later)
        cache_control.refresh_award_source_cache(c.SOURCE_KEY)
        with patch.object(c, '_load_live_archive', return_value=ROWS):
            self.assertEqual(len(c.lookup('Later Candidate', 'Later Author')), 1)
        self.assertEqual(c._load_disk()[0], later)
        self.assertTrue(cache.source_refresh_pending(c.SOURCE_KEY))

    def test_stale_budget_deferred_ram_retries_next_lookup(self):
        self.save(stale=True)
        with cache.lookup_refresh_budget():
            self.assertTrue(cache.try_claim_stale_refresh())
            with patch.object(c, '_fetch_html', side_effect=AssertionError('budget exhausted')):
                c.lookup('The Death of Us', 'Abigail Dean')
        with cache.lookup_refresh_budget(), patch.object(c, '_fetch_html', side_effect=fetch) as network:
            c.lookup('The Death of Us', 'Abigail Dean')
            self.assertEqual(network.call_count, 19)

    def test_fresh_ram_expires_and_is_reconsidered(self):
        self.save()
        c.lookup('The Death of Us', 'Abigail Dean')
        with patch.object(cache, 'cache_is_fresh', return_value=False), patch.object(c, '_fetch_html', side_effect=fetch) as network:
            c.lookup('The Death of Us', 'Abigail Dean')
        self.assertEqual(network.call_count, 19)

    def test_failed_optional_refresh_cooldown_and_controlled_retry(self):
        self.save(stale=True)
        with patch.object(cache.time, 'monotonic', return_value=100), patch.object(c, '_fetch_html', side_effect=OSError('outage')) as network:
            c.lookup('The Death of Us', 'Abigail Dean')
            c.lookup('The Death of Us', 'Abigail Dean')
            self.assertEqual(network.call_count, 1)
        with patch.object(cache.time, 'monotonic', return_value=161), patch.object(c, '_fetch_html', side_effect=fetch) as network:
            c.lookup('The Death of Us', 'Abigail Dean')
            self.assertEqual(network.call_count, 19)

    def test_explicit_refresh_bypasses_consumed_optional_budget(self):
        self.save(stale=True)
        cache_control.refresh_award_source_cache(c.SOURCE_KEY)
        with cache.lookup_refresh_budget():
            self.assertTrue(cache.try_claim_stale_refresh())
            with patch.object(c, '_fetch_html', side_effect=fetch) as network:
                c.lookup('The Death of Us', 'Abigail Dean')
                self.assertEqual(network.call_count, 19)
        self.assertFalse(cache.source_refresh_pending(c.SOURCE_KEY))

    def test_refresh_responsive_and_newer_request_survives_old_retrieval(self):
        self.save()
        cache_control.refresh_award_source_cache(c.SOURCE_KEY)
        entered, release = Event(), Event()
        def delayed(previous=()):
            entered.set()
            if not release.wait(5):
                raise AssertionError('bounded retrieval wait expired')
            return ROWS
        with patch.object(c, '_load_live_archive', side_effect=delayed), ThreadPoolExecutor(max_workers=2) as pool:
            worker = pool.submit(c.lookup, 'The Death of Us', 'Abigail Dean')
            try:
                self.assertTrue(entered.wait(3))
                refresh = pool.submit(cache_control.refresh_award_source_cache, c.SOURCE_KEY)
                self.assertTrue(refresh.result(timeout=2))
            finally:
                release.set()
            self.assertEqual(len(worker.result(timeout=3)), 1)
        self.assertTrue(cache.source_refresh_pending(c.SOURCE_KEY))
        with patch.object(c, '_fetch_html', side_effect=fetch):
            report = engine.lookup_awards('The Death of Us', 'Abigail Dean', enabled_source_keys=[c.SOURCE_KEY])
        self.assertFalse(cache.source_refresh_pending(c.SOURCE_KEY))
        self.assertFalse(report.diagnostics)

    def test_source_registration_default_policy_metadata_and_disabled_lookup(self):
        from awards.source_registry import AWARD_SOURCES
        from awards.source_info import SOURCE_INFOS
        from awards.source_settings import compute_enabled_source_keys
        self.assertIs(next(s.lookup for s in AWARD_SOURCES if s.key == c.SOURCE_KEY), c.lookup)
        self.assertIn(c.SOURCE_KEY, compute_enabled_source_keys([s.key for s in AWARD_SOURCES], None))
        self.assertIn(c.SOURCE_KEY, cache_control.runtime_reset_source_keys())
        self.assertNotIn(c.SOURCE_KEY, cache_control.BUNDLED_SOURCE_KEYS)
        self.assertIn('partial', next(s.limitation for s in SOURCE_INFOS if s.key == c.SOURCE_KEY))
        with patch.object(c, '_fetch_html', side_effect=AssertionError('disabled')):
            report = engine.lookup_awards('The Death of Us', 'Abigail Dean', enabled_source_keys=[])
        self.assertFalse(report.assessments or report.failures or report.diagnostics)


def _identity_test(r):
    return r.year,r.title,r.author


def _later_row():
    return c._Row(2027, 'Later Candidate', 'Later Author', 'Longlisted', c.SOURCE_HOME_URL, 'Gold Dagger')


if __name__ == '__main__':
    unittest.main()
