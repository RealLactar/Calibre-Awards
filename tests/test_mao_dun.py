"""Offline primary-HTML, edition identity, qualification and cache regressions."""
import json
import unittest
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from awards import cache, cache_control
from awards.sources import mao_dun as m
from awards.qualifier import qualify_award_result, QualificationDecision
from awards.presentation import default_award_row_checked
F=Path(__file__).parent/'fixtures'/'mao_dun'
HTML=(F/'winners.html').read_text(encoding='utf-8')
NHTML=(F/'nominees-11.html').read_text(encoding='utf-8')
W=m._parse_winners(HTML)
N=m._parse_nominees(NHTML)
ROWS=W+N
RECORDS=m._merge(W,N)

def fetch(url):
    return HTML if url==m.WINNERS_URL else NHTML

class MaoDunTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();cache.set_cache_directory(self.temp.name);m._reset_runtime_state()
    def tearDown(self):
        m._reset_runtime_state();cache._reset_runtime_state();self.temp.cleanup()
    def save(self,stale=False):
        cache.save_source_cache(m.SOURCE_KEY,m.CACHE_VERSION,records=[asdict(r) for r in ROWS],source_urls=m.SOURCE_URLS,
            coverage={'last_edition':11,'nomination_editions':[11]},ttl_seconds=m.CACHE_TTL_SECONDS,
            generated_at=datetime(2000,1,1,tzinfo=timezone.utc) if stale else None)
    def test_complete_history_categories_and_deduplication(self):
        self.assertEqual({r.edition for r in W},set(range(1,12)))
        self.assertEqual(sum(r.status=='Winner' for r in W),51)
        self.assertEqual(sum(r.status=='Honorary award' for r in W),2)
        self.assertEqual(len(N),10);self.assertEqual(len(RECORDS),58)
        self.assertEqual(sum(r.status=='Nominated' for r in RECORDS),5)
    def test_english_identities_provenance_and_award_year(self):
        with patch.object(m,'_get_records',return_value=RECORDS):
            for title,author,year,original in [('The Last Quarter of the Moon','Chi Zijian',2008,'额尔古纳河右岸'),('Frog','Mo Yan',2011,'蛙')]:
                r=m.lookup(title,author)[0]
                self.assertEqual(r.work_title,original);self.assertEqual(r.award_year,year)
                self.assertEqual(r.status,'Winner');self.assertEqual(r.source_url,m.WINNERS_URL)
                self.assertEqual(qualify_award_result(r).decision,QualificationDecision.QUALIFIES)
                self.assertIsNone(r.rank);self.assertIsNone(r.category)
                self.assertTrue(any('Verified title/name mapping' in d for d in r.source_details))
    def test_nominees_show_unchecked_review(self):
        with patch.object(m,'_get_records',return_value=RECORDS):
            r=m.lookup('燕食记','葛亮')[0];q=qualify_award_result(r)
            self.assertEqual(r.status,'Nominated');self.assertEqual(r.award_year,2023)
            self.assertEqual(r.source_url,m.NOMINEES_URL)
            self.assertEqual(q.decision,QualificationDecision.REVIEW)
            self.assertFalse(default_award_row_checked(qualifies=q.decision is QualificationDecision.QUALIFIES,identity_confirmation_required=r.identity_confirmation_required))
            self.assertEqual(len(m.lookup('雪山大地','杨志军')),1)
            self.assertEqual(m.lookup('雪山大地','杨志军')[0].status,'Winner')
    def test_honorary_awards_distinct_from_winners(self):
        with patch.object(m,'_get_records',return_value=RECORDS):
            for title,author in [('浴血罗霄','萧克'),('金瓯缺','徐兴业')]:
                r=m.lookup(title,author)[0]
                self.assertEqual(r.status,'Honorary award');self.assertEqual(r.award_year,1991)
                self.assertEqual(qualify_award_result(r).decision,QualificationDecision.REVIEW)
                self.assertIn('荣誉奖',' '.join(r.source_details))
    def test_award_years_are_not_periods_or_article_date(self):
        self.assertEqual({r.edition:r.year for r in W},{1:1982,2:1985,3:1991,4:1997,5:2000,6:2005,7:2008,8:2011,9:2015,10:2019,11:2023})
        with patch.object(m,'_get_records',return_value=RECORDS):
            r=m.lookup('芙蓉镇','古华')[0]
            self.assertEqual(r.award_year,1982);self.assertIn('1977–1981',' '.join(r.source_details))
    def test_volume_and_revised_scope_requires_confirmation(self):
        with patch.object(m,'_get_records',return_value=RECORDS):
            for title,author,bare in [('李自成（第二卷）','姚雪垠','李自成'),('白鹿原（修订本）','陈忠实','白鹿原'),('茶人三部曲(一、二)','王旭烽','茶人三部曲')]:
                r=m.lookup(title,author)[0]
                self.assertTrue(r.identity_confirmation_required);self.assertIn(r.work_title.replace('（','(').replace('）',')'),r.source_identity_note.replace('（','(').replace('）',')').replace('《','').replace('》',''))
                self.assertFalse(default_award_row_checked(qualifies=True,identity_confirmation_required=True))
                self.assertEqual(m.lookup(bare,author),[])
            self.assertEqual(m.lookup('人面桃花','格非'),[])
    def test_no_author_wide_translator_or_guessed_translation_matches(self):
        with patch.object(m,'_get_records',return_value=RECORDS):
            for t,a in [('Red Sorghum','Mo Yan'),('Frog','Howard Goldblatt'),('The Last Quarter of the Moon','Bruce Humes'),('Frog','Chi Zijian'),('Moon','Chi Zijian')]:
                self.assertEqual(m.lookup(t,a),[])
    def test_chinese_name_spacing_and_coauthors(self):
        with patch.object(m,'_get_records',return_value=RECORDS):
            self.assertEqual(m.lookup('蛙','莫 言')[0].work_title,'蛙')
            self.assertEqual(m.lookup('都市风流','孙力、余小惠')[0].award_year,1991)
            self.assertEqual(m.lookup('都市风流','孙力'),[])
            self.assertEqual(m.lookup('Frog','MoYan'),[])
    def test_wrong_archive_and_unknown_future_edition_rejected(self):
        for html in [HTML.replace('历届茅盾文学奖获奖作品一览','鲁迅文学奖'),HTML.replace('第十一届茅盾','第十二届茅盾')]:
            with self.assertRaises(m.MaoDunSourceError):m._parse_winners(html)
    def test_incomplete_or_misclassified_honorary_records_rejected(self):
        for rows in [W[:-1],tuple(r for r in W if r.status!='Honorary award'),tuple(replace(r,status='Winner') if r.status=='Honorary award' else r for r in W),W+(W[0],)]:
            with self.assertRaises(m.MaoDunSourceError):m._validate_winners(rows)
    def test_wrong_year_and_lost_volume_scope_rejected(self):
        for rows in [tuple(replace(r,year=2022) if r.edition==11 else r for r in W),tuple(replace(r,title='李自成') if r.title.startswith('李自成') else r for r in W)]:
            with self.assertRaises(m.MaoDunSourceError):m._validate_winners(rows)
    def test_wrong_nomination_edition_section_and_partial_records_rejected(self):
        for html in [NHTML.replace('第十一届茅盾文学奖--','第十届茅盾文学奖--'),NHTML.replace('提名作品</h1>','参评作品</h1>'),NHTML.replace('<b>作者：</b>葛亮','<b>作者：</b>')]:
            with self.assertRaises(m.MaoDunSourceError):m._parse_nominees(html)
    def test_cold_ram_and_disk_cache(self):
        with patch.object(m,'_fetch_html',side_effect=fetch) as f:
            self.assertEqual(len(m._get_records()),58);self.assertEqual(f.call_count,2)
            m._get_records();self.assertEqual(f.call_count,2)
        m._reset_runtime_state()
        with patch.object(m,'_fetch_html',side_effect=AssertionError('network')):self.assertEqual(len(m._get_records()),58)
    def test_failed_refresh_retains_disk_and_pending_then_success_clears(self):
        self.save();path=Path(self.temp.name)/'mao_dun.json';before=path.read_bytes()
        cache_control.refresh_award_source_cache('mao_dun')
        with patch.object(m,'_fetch_html',side_effect=m.MaoDunSourceError('unavailable')):self.assertEqual(len(m._get_records()),58)
        self.assertEqual(path.read_bytes(),before);self.assertTrue(cache.source_refresh_pending('mao_dun'))
        m._reset_runtime_state()
        with patch.object(m,'_fetch_html',side_effect=fetch):m._get_records()
        self.assertFalse(cache.source_refresh_pending('mao_dun'))
    def test_partial_cold_fetch_never_publishes(self):
        with patch.object(m,'_fetch_html',side_effect=[HTML,'broken']):
            with self.assertRaises(m.MaoDunSourceError):m._get_records()
        self.assertIsNone(m._load_disk())
    def test_corrupt_cache_and_wrong_source_url_rejected(self):
        for field,value in [('year',2019),('status','Nominated'),('source_url','https://example.com/')]:
            self.save();p=Path(self.temp.name)/'mao_dun.json';d=json.loads(p.read_text(encoding='utf-8'));d['records'][0][field]=value
            p.write_text(json.dumps(d),encoding='utf-8');self.assertIsNone(m._load_disk())
    def test_zip_reference_and_registration(self):
        raw=(Path(m.__file__).parents[1]/'data/mao_dun_mappings.json').read_bytes()
        with patch.object(m,'get_resources',create=True,return_value=raw) as resource:
            self.assertEqual(len(m._reference_data()['mappings']),2);resource.assert_called_once_with('awards/data/mao_dun_mappings.json')
        from awards.source_registry import AWARD_SOURCES
        from awards.source_settings import compute_enabled_source_keys
        self.assertIs(AWARD_SOURCES[-1].lookup,m.lookup)
        self.assertIn('mao_dun',compute_enabled_source_keys(tuple(s.key for s in AWARD_SOURCES),['pulitzer']))
        self.assertNotIn('mao_dun',cache_control.BUNDLED_SOURCE_KEYS)
    def test_blank_identity_rejected(self):
        for title,author in [('', 'Mo Yan'),('Frog',' ')]:
            with self.assertRaises(ValueError):m.lookup(title,author)
