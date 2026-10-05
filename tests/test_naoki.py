"""Offline official records, matching, qualification and cache regressions."""
import unittest
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from awards import cache, cache_control
from awards.sources import naoki as n
from awards.qualifier import qualify_award_result, QualificationDecision
from awards.presentation import default_award_row_checked
F = Path(__file__).parent / 'fixtures' / 'naoki'
HTML = (F/'winners.html').read_text(encoding='utf-8')
NHTML = (F/'nominees-175.html').read_text(encoding='utf-8')
W = n._parse_winners(HTML)
N = n._parse_nominees(NHTML,n.NOMINATION_PAGES[0])
ROWS=W+N
RECORDS=n._merge(W,N)

def fetch(url):
    return HTML if url==n.WINNERS_URL else NHTML

class NaokiTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory(); cache.set_cache_directory(self.temp.name); n._reset_runtime_state()
    def tearDown(self):
        n._reset_runtime_state(); cache._reset_runtime_state(); self.temp.cleanup()
    def save(self,stale=False):
        cache.save_source_cache(n.SOURCE_KEY,n.CACHE_VERSION,records=[asdict(r) for r in ROWS],source_urls=n.SOURCE_URLS,
            coverage={'last_round':175,'nomination_rounds':[175]},ttl_seconds=n.CACHE_TTL_SECONDS,
            generated_at=datetime(2000,1,1,tzinfo=timezone.utc) if stale else None)
    def test_history_joint_winners_and_interruptions(self):
        self.assertEqual(len([r for r in W if r.status=='Winner']),208)
        self.assertEqual(len([r for r in W if r.status=='No award']),30)
        self.assertEqual({r.round_number for r in W},set(range(1,176)))
        self.assertEqual(len([r for r in W if r.round_number==170]),2)
        self.assertEqual(next(r.year for r in W if r.round_number==21),1949)
        self.assertFalse(any(r.round_number==173 for r in RECORDS))
    def test_mapping_identity_dates_and_qualification(self):
        with patch.object(n,'_get_records',return_value=RECORDS):
            for title,author,year in [('The Devotion of Suspect X','Keigo Higashino',2005),('Honeybees and Distant Thunder','Riku Onda',2016)]:
                result=n.lookup(title,author)[0]
                self.assertEqual(result.award_year,year); self.assertEqual(result.status,'Winner')
                self.assertEqual(result.source_url,n.WINNERS_URL); self.assertIn('second half',' '.join(result.source_details))
                self.assertEqual(qualify_award_result(result).decision,QualificationDecision.QUALIFIES)
                self.assertIsNone(result.rank); self.assertIsNone(result.category)
            for m in n._mappings():
                self.assertEqual(n.lookup(m['titles'][0],m['authors'][0])[0].work_title,m['title_ja'])
                self.assertEqual(n.lookup(m['title_ja'],m['author_ja'])[0].work_author,m['author_ja'])
    def test_nominees_unchecked_and_winner_deduplicated(self):
        self.assertEqual(len(N),5); self.assertEqual(len(RECORDS),212)
        with patch.object(n,'_get_records',return_value=RECORDS):
            result=n.lookup('＃台所のあるところ','原田ひ香')[0]
            q=qualify_award_result(result)
            self.assertEqual(result.status,'Nominated'); self.assertEqual(result.award_year,2026)
            self.assertEqual(result.source_url,n.NOMINATION_PAGES[0][3])
            self.assertEqual(q.decision,QualificationDecision.REVIEW)
            self.assertFalse(default_award_row_checked(qualifies=q.decision is QualificationDecision.QUALIFIES,identity_confirmation_required=False))
            self.assertEqual(len(n.lookup('けんぐゎい','朝倉かすみ')),1)
            self.assertEqual(n.lookup('けんぐゎい','朝倉かすみ')[0].status,'Winner')
    def test_no_author_wide_translator_or_other_prize_matches(self):
        with patch.object(n,'_get_records',return_value=RECORDS):
            for t,a in [('Salvation of a Saint','Keigo Higashino'),('The Devotion of Suspect X','Alexander O. Smith'),('Honeybees and Distant Thunder','Philip Gabriel'),('The Devotion of Suspect X','Riku Onda')]:
                self.assertEqual(n.lookup(t,a),[])
    def test_multi_story_citations_preserved_unsplit(self):
        row=next(r for r in W if r.author=='野坂昭如')
        self.assertIn('・',row.title)
        with patch.object(n,'_get_records',return_value=RECORDS):
            self.assertEqual(n.lookup('火垂るの墓','野坂昭如'),[])
            self.assertEqual(n.lookup(row.title,row.author)[0].work_title,row.title)
    def test_missing_history_joint_winner_and_wrong_year_rejected(self):
        for bad in [W[1:],tuple(r for r in W if r.round_number!=170),tuple(replace(r,year=2006) if r.round_number==134 else r for r in W),W+(W[0],)]:
            with self.assertRaises(n.NaokiSourceError): n._validate_winners(bad)
    def test_wrong_round_award_page_and_partial_nominees_rejected(self):
        for bad in [NHTML.replace('第175回直木','第175回芥川'),NHTML.replace('原田ひ香',''),NHTML.replace('/11013','/11012')]:
            with self.assertRaises(n.NaokiSourceError): n._parse_nominees(bad,n.NOMINATION_PAGES[0])
    def test_cold_ram_and_disk_cache(self):
        with patch.object(n,'_fetch_html',side_effect=fetch) as f:
            self.assertEqual(len(n._get_records()),212); self.assertEqual(f.call_count,2)
            n._get_records(); self.assertEqual(f.call_count,2)
        n._reset_runtime_state()
        with patch.object(n,'_fetch_html',side_effect=AssertionError('network')):
            self.assertEqual(len(n._get_records()),212)
    def test_failed_refresh_retains_disk_and_pending_request(self):
        self.save(); path=Path(self.temp.name)/'naoki.json'; before=path.read_bytes()
        cache_control.refresh_award_source_cache('naoki')
        with patch.object(n,'_fetch_html',side_effect=n.NaokiSourceError('unavailable')):
            self.assertEqual(len(n._get_records()),212)
        self.assertEqual(path.read_bytes(),before); self.assertTrue(cache.source_refresh_pending('naoki'))
        n._reset_runtime_state()
        with patch.object(n,'_fetch_html',side_effect=fetch): n._get_records()
        self.assertFalse(cache.source_refresh_pending('naoki'))
    def test_incomplete_cold_fetch_never_publishes_cache(self):
        with patch.object(n,'_fetch_html',side_effect=[HTML,'broken']):
            with self.assertRaises(n.NaokiSourceError): n._get_records()
        self.assertIsNone(n._load_disk())
    def test_corrupt_cache_rejected(self):
        self.save(); p=Path(self.temp.name)/'naoki.json'
        import json
        d=json.loads(p.read_text(encoding='utf-8')); d['records'][0]['year']=1900
        p.write_text(json.dumps(d)); self.assertIsNone(n._load_disk())
    def test_zip_resource_api_and_isolated_cache_registration(self):
        n._reset_runtime_state()
        raw=(Path(n.__file__).parents[1]/'data/naoki_mappings.json').read_bytes()
        with patch.object(n,'get_resources',create=True,return_value=raw) as resource:
            self.assertEqual(len(n._mappings()),2); resource.assert_called_once_with('awards/data/naoki_mappings.json')
        self.assertIn('naoki',cache_control.runtime_reset_source_keys())
        self.assertNotIn('naoki',cache_control.BUNDLED_SOURCE_KEYS)
