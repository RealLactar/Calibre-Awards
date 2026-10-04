"""Representative historical HTML, not a live-response fixture."""
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from awards import cache
from awards.cache_control import refresh_award_source_cache
from awards.formatter import format_award_result
from awards.qualifier import QualificationDecision, qualify_award_result
from awards.sources import nebula
from test_nebula_cache import _complete_archive, _save_disk

TITLE='24 Views of Mt. Fuji, by Hokusai'
AUTHOR='Roger Zelazny'
URL='https://nebulas.sfwa.org/nominated-work/24-views-mt-fuji-hokusai/'
HTML=(Path(__file__).parent/'fixtures/nebula/best_novella_1985_title_by.html').read_text(encoding='utf-8')


def injected_archive():
    archive=_complete_archive()
    # Cache validation requires a winner for each displayed year from 1965.
    seed=archive['best-novella'][0]
    archive['best-novella'] += tuple(replace(seed,award_year=year) for year in range(1966,1986))
    archive['best-novella'] += tuple(nebula._parse_category_html(HTML,nebula._BEST_NOVELLA_CONFIG))
    return archive


class NebulaTitleBylineTests(unittest.TestCase):
    def setUp(self):
        nebula._reset_runtime_state()
        cache._reset_runtime_state()
        self.temp=TemporaryDirectory()
        self.directory=Path(self.temp.name)
        cache.set_cache_directory(self.directory)

    def tearDown(self):
        nebula._reset_runtime_state()
        cache._reset_runtime_state()
        self.temp.cleanup()

    def test_representative_separate_links_preserve_title_author_and_provenance(self):
        records=nebula._parse_category_html(HTML,nebula._BEST_NOVELLA_CONFIG)
        self.assertEqual(len(records),1)
        record=records[0]
        self.assertEqual((record.work_title,record.work_author),(TITLE,AUTHOR))
        self.assertEqual((record.category,record.award_year,record.status),('Best Novella',1985,'Nominated'))
        self.assertEqual(record.source_url,URL)

    def test_public_lookup_with_injected_archive_zero_http_and_review(self):
        nebula._install_ram_records(injected_archive())
        with patch.object(nebula,'_fetch_html',side_effect=AssertionError('HTTP')):
            results=nebula.lookup(TITLE,AUTHOR)
            self.assertEqual(nebula.lookup(TITLE,'Unrelated Author'),[])
            self.assertEqual(nebula.lookup(TITLE,'Hokusai'),[])
        self.assertEqual(len(results),1)
        result=results[0]
        self.assertEqual((result.work_title,result.work_author,result.source_url),(TITLE,AUTHOR,URL))
        self.assertEqual(format_award_result(result),'Nominated - 1985 Nebula Award - Best Novella')
        self.assertEqual(qualify_award_result(result).decision,QualificationDecision.REVIEW)
        self.assertIsNone(result.rank)

    def test_linked_authors_override_by_wording_with_quotes_and_multiple_authors(self):
        for title in (TITLE,'“'+TITLE+'”','"'+TITLE+'"'):
            self.assertEqual(nebula._extract_title_author('',title,['Roger Zelazny','Pat Author']),
                             (TITLE,'Roger Zelazny and Pat Author'))
        self.assertEqual(nebula._extract_title_author('“'+TITLE+'”','ignored link',['Roger Zelazny']),
                         (TITLE,AUTHOR))

    def test_modern_compact_citations_still_parse_without_linked_authors(self):
        for citation in ('“Modern Title”, by First Author and Second Author (Publisher)',
                         'Modern Title, by First Author and Second Author (Publisher)'):
            with self.subTest(citation=citation):
                self.assertEqual(nebula._extract_title_author('',citation,[]),
                                 ('Modern Title','First Author and Second Author'))

    def test_missing_author_remains_explicitly_unknown(self):
        self.assertEqual(nebula._extract_title_author('“Unknown Work”','',[]),('Unknown Work',''))
        self.assertIsNone(nebula._extract_title_author('','',[]))

    def test_old_malformed_disk_cache_is_rejected_then_rebuilt_source_specifically(self):
        good=injected_archive()
        bad=dict(good)
        bad['best-novella']=tuple(replace(r,work_title='24 Views of Mt. Fuji',work_author='Hokusai')
                                 if r.award_year==1985 else r for r in good['best-novella'])
        _save_disk(bad,version=1)
        self.assertIsNotNone(cache.load_source_cache('nebula',1))
        # Record-shape validation alone cannot identify the old parsing bug.
        self.assertIsNotNone(nebula._records_from_cache_payload(cache.load_source_cache('nebula',1)))
        self.assertIsNone(nebula._load_persistent_archive())
        cache.save_source_cache('hugo',1,records=[],source_urls=[],coverage={},ttl_seconds=60)
        sibling=self.directory/'hugo.json'
        before=(sibling.read_bytes(),sibling.stat().st_mtime_ns)
        with patch.object(nebula,'_load_live_archive',return_value=good) as acquire:
            self.assertEqual(nebula.lookup(TITLE,AUTHOR)[0].status,'Nominated')
            self.assertTrue(nebula.lookup(TITLE,AUTHOR))
        acquire.assert_called_once()
        self.assertIsNotNone(cache.load_source_cache('nebula',nebula.CACHE_VERSION))
        self.assertIsNone(cache.load_source_cache('nebula',1))
        self.assertEqual(before,(sibling.read_bytes(),sibling.stat().st_mtime_ns))

    def test_old_cache_cannot_be_used_as_fallback_when_retrieval_fails(self):
        _save_disk(_complete_archive(),version=1)
        with patch.object(nebula,'_load_live_archive',side_effect=nebula.NebulaSourceError('HTTP 403')):
            with self.assertRaises(nebula.NebulaSourceError): nebula.lookup(TITLE,AUTHOR)

    def test_normal_refresh_resets_ram_preserves_current_valid_disk_and_retries(self):
        good=injected_archive()
        _save_disk(good)
        nebula._install_ram_records(good)
        path=self.directory/'nebula.json'
        before=(path.read_bytes(),path.stat().st_mtime_ns)
        with patch.object(nebula,'_fetch_html',side_effect=AssertionError('Refresh HTTP')):
            self.assertTrue(refresh_award_source_cache('nebula'))
        self.assertEqual(nebula._records_cache,{})
        self.assertEqual(nebula._pages_cache,{})
        with patch.object(nebula,'_load_live_archive',side_effect=nebula.NebulaSourceError('HTTP 403')):
            self.assertTrue(nebula.lookup(TITLE,AUTHOR))
        self.assertEqual(before,(path.read_bytes(),path.stat().st_mtime_ns))
        self.assertTrue(cache.source_refresh_pending('nebula'))
        refresh_award_source_cache('nebula')
        with patch.object(nebula,'_load_live_archive',return_value=good):
            self.assertTrue(nebula.lookup(TITLE,AUTHOR))
        self.assertFalse(cache.source_refresh_pending('nebula'))
