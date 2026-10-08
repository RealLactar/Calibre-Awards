"""Reviewed publisher/author edition evidence, exercised through production lookups."""
import json
import unittest
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from awards import cache, cache_control
from awards.presentation import default_award_row_checked
from awards.qualifier import QualificationDecision, qualify_award_result
from awards.sources import akutagawa, naoki, mao_dun, medicis

F = Path(__file__).parent / 'fixtures'
REVIEWED = json.loads((F / 'title_mappings/reviewed-2026-10-07.json').read_text(encoding='utf-8'))
MODULES = {m.SOURCE_KEY: m for m in (akutagawa, naoki, mao_dun, medicis)}


class VerifiedTitleMappingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        cache.set_cache_directory(self.temp.name)
        self.rows = {}
        for key, m in MODULES.items():
            m._reset_runtime_state()
            winners = m._parse_winners((F / key / 'winners.html').read_text(encoding='utf-8'))
            if key in ('akutagawa', 'naoki'):
                nominees = tuple(r for p in m.NOMINATION_PAGES for r in
                                 m._parse_nominees((F / key / f'nominees-{p[0]}.html').read_text(encoding='utf-8'), p))
                coverage = {'last_round': 175, 'nomination_rounds': [p[0] for p in m.NOMINATION_PAGES]}
            elif key == 'mao_dun':
                nominees = m._parse_nominees((F / key / 'nominees-11.html').read_text(encoding='utf-8'))
                coverage = {'last_edition': 11, 'nomination_editions': [11]}
            else:
                nominees = m._parse_selection((F / key / 'selection-2026.html').read_text(encoding='utf-8'))
                coverage = {'selection_rounds': ['2026-first']}
            self.rows[key] = winners + nominees
            cache.save_source_cache(key, m.CACHE_VERSION, records=[asdict(r) for r in self.rows[key]],
                                    source_urls=m.SOURCE_URLS, coverage=coverage, ttl_seconds=m.CACHE_TTL_SECONDS)
        self.network_patches = [patch.object(m, '_fetch_html', side_effect=AssertionError('offline regression attempted network'))
                                for m in MODULES.values()]
        for p in self.network_patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.network_patches):
            p.stop()
        for m in MODULES.values():
            m._reset_runtime_state()
        cache._reset_runtime_state()
        self.temp.cleanup()

    def test_each_reviewed_english_and_original_identity(self):
        self.assertEqual(len(REVIEWED), 11)
        for e in REVIEWED:
            with self.subTest(title=e['english_title']):
                m = MODULES[e['source']]
                english = m.lookup(e['english_title'], e['english_author'])
                original = m.lookup(e['original_title'], e['original_author'])
                self.assertEqual(len(english), 1)
                self.assertEqual(english, original)
                r = english[0]
                self.assertEqual((r.work_title, r.work_author, r.award_year, r.status, r.category),
                                 (e['original_title'], e['original_author'], e['year'], 'Winner', e['category']))
                self.assertEqual(r.source_url, m.WINNERS_URL)
                self.assertIsNone(r.rank)
                self.assertFalse(r.identity_confirmation_required)
                self.assertEqual(qualify_award_result(r).decision, QualificationDecision.QUALIFIES)
                self.assertTrue(default_award_row_checked(qualifies=True, identity_confirmation_required=False))
                self.assertIn(e['evidence'][0], ' '.join(r.source_details))

    def test_added_titles_were_not_already_matchable_without_mappings(self):
        added = {e['english_title'] for e in REVIEWED}
        for key, m in MODULES.items():
            old = [v for v in m._mappings() if not added.intersection(v['titles'])] if key != 'mao_dun' else [v for v in m._reference_data()['mappings'] if not added.intersection(v['titles'])]
            target = '_mappings' if key != 'mao_dun' else '_reference_data'
            value = old if key != 'mao_dun' else dict(m._reference_data(), mappings=old)
            with patch.object(m, target, return_value=value):
                for e in REVIEWED:
                    if e['source'] == key:
                        self.assertEqual(m.lookup(e['english_title'], e['english_author']), [])

    def test_wrong_authors_and_translators_are_not_authors(self):
        for e in REVIEWED:
            m = MODULES[e['source']]
            for author in ['Unrelated Author'] + e['translators']:
                with self.subTest(title=e['english_title'], author=author):
                    self.assertEqual(m.lookup(e['english_title'], author), [])
                    self.assertEqual(m.lookup(e['original_title'], author), [])

    def test_multiple_identical_aliases_do_not_duplicate_results(self):
        for key, m in MODULES.items():
            values = m._mappings() if key != 'mao_dun' else m._reference_data()['mappings']
            duplicate = [dict(v, titles=v['titles'] * 2) for v in values]
            target = '_mappings' if key != 'mao_dun' else '_reference_data'
            value = duplicate if key != 'mao_dun' else dict(m._reference_data(), mappings=duplicate)
            with patch.object(m, target, return_value=value):
                for e in REVIEWED:
                    if e['source'] == key:
                        self.assertEqual(len(m.lookup(e['english_title'], e['english_author'])), 1)

    def test_warm_cache_repeated_lookups_do_not_fetch(self):
        for e in REVIEWED:
            m = MODULES[e['source']]
            first = m.lookup(e['english_title'], e['english_author'])
            self.assertEqual(m.lookup(e['english_title'], e['english_author']), first)
            self.assertFalse(cache.source_refresh_pending(e['source']))

    def test_unverified_related_books_and_collection_titles_do_not_match(self):
        cases = [('akutagawa', 'The Hunting Gun', 'Yasushi Inoue'),
                 ('akutagawa', 'The Thief', 'Fuminori Nakamura'),
                 ('akutagawa', 'Breasts and Eggs', 'Mieko Kawakami'),
                 ('akutagawa', 'The Diving Pool', 'Yoko Ogawa'),
                 ('naoki', 'The Eighth Day', 'Mitsuyo Kakuta'),
                 ('naoki', 'The Great Passage', 'Shion Miura'),
                 ('mao_dun', 'White Deer Plain', 'Chen Zhongshi'),
                 ('mao_dun', 'Heavy Wings', 'Zhang Jie'),
                 ('mao_dun', 'Ordinary World', 'Lu Yao'),
                 ('mao_dun', 'Yellowbird Story', 'Su Tong'),
                 ('medicis', 'Legend of a Suicide', 'David Vann')]
        for key, title, author in cases:
            with self.subTest(source=key, title=title):
                self.assertEqual(MODULES[key].lookup(title, author), [])

    def test_existing_volume_and_revision_confirmation_remains_unchecked(self):
        for key in ('mao_dun', 'medicis'):
            m = MODULES[key]
            restricted = []
            for row in self.rows[key]:
                results = m.lookup(row.title, row.author)
                restricted.extend(r for r in results if r.identity_confirmation_required)
            self.assertTrue(restricted, key)
            for r in restricted:
                self.assertTrue(r.source_identity_note)
                self.assertFalse(default_award_row_checked(qualifies=True, identity_confirmation_required=True))


if __name__ == '__main__':
    unittest.main()
