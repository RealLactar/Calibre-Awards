"""Offline official-fixture, matching, qualification and cache regressions."""
import json
import unittest
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from awards import cache
from awards.sources import akutagawa as a
from awards.qualifier import qualify_award_result, QualificationDecision
from awards.presentation import default_award_row_checked

FIXTURES = Path(__file__).parent / 'fixtures' / 'akutagawa'
WINNERS_HTML = (FIXTURES / 'winners.html').read_text(encoding='utf-8')
NOMINEES_HTML = {p[0]: (FIXTURES / f'nominees-{p[0]}.html').read_text(encoding='utf-8') for p in a.NOMINATION_PAGES}
WINNERS = a._parse_winners(WINNERS_HTML)
NOMINEES = tuple(r for p in a.NOMINATION_PAGES for r in a._parse_nominees(NOMINEES_HTML[p[0]], p))
ROWS = WINNERS + NOMINEES
RECORDS = a._merge(WINNERS, NOMINEES)


def fetch_fixture(url):
    if url == a.WINNERS_URL:
        return WINNERS_HTML
    p = next(p for p in a.NOMINATION_PAGES if p[3] == url)
    return NOMINEES_HTML[p[0]]


class AkutagawaTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        cache.set_cache_directory(self.temp.name)
        a._reset_runtime_state()

    def tearDown(self):
        a._reset_runtime_state()
        cache._reset_runtime_state()
        self.temp.cleanup()

    def save(self, stale=False):
        cache.save_source_cache(a.SOURCE_KEY, a.CACHE_VERSION,
                                records=[asdict(r) for r in ROWS], source_urls=a.SOURCE_URLS,
                                coverage={'last_round': 175, 'nomination_rounds': [162, 175]},
                                ttl_seconds=a.CACHE_TTL_SECONDS,
                                generated_at=datetime(2000, 1, 1, tzinfo=timezone.utc) if stale else None)

    def test_complete_history_shared_wins_and_no_award(self):
        self.assertEqual({r.round_number for r in WINNERS}, set(range(1, 176)))
        self.assertEqual(sum(r.status == 'Winner' for r in WINNERS), 189)
        self.assertEqual(sum(r.status == 'No award' for r in WINNERS), 33)
        self.assertEqual(len(RECORDS), 197)
        self.assertEqual(sum(r.status == 'Nominated' for r in RECORDS), 8)
        self.assertFalse(any(r.round_number == 173 for r in RECORDS))
        self.assertEqual(len([r for r in RECORDS if r.round_number == 130]), 2)

    def test_english_mapping_set_is_grounded_in_source_identity(self):
        self.assertEqual(len(a._mappings()), 9)
        for mapping in a._mappings():
            row = next(r for r in RECORDS if r.round_number == mapping['round']
                       and r.title == mapping['title_ja'] and r.author == mapping['author_ja'])
            self.assertTrue(mapping['evidence'][0].startswith('https://'))
            with patch.object(a, '_get_records', return_value=RECORDS):
                result = a.lookup(mapping['titles'][0], mapping['authors'][0])[0]
                self.assertEqual(result.work_title, row.title)
                self.assertEqual(result.work_author, row.author)
                self.assertEqual(result.status, row.status)
                self.assertEqual(result.source_url, row.source_url)
                self.assertIsNone(result.rank)
                self.assertIsNone(result.category)
                expected = QualificationDecision.REVIEW if row.status == 'Nominated' else QualificationDecision.QUALIFIES
                self.assertEqual(qualify_award_result(result).decision, expected)

    def test_known_work_qualifies_and_preserves_original_identity(self):
        with patch.object(a, '_get_records', return_value=RECORDS):
            result = a.lookup('Convenience Store Woman', 'Sayaka Murata')[0]
            self.assertEqual(result.award_year, 2016)
            self.assertEqual(result.work_title, 'コンビニ人間')
            self.assertEqual(result.source_url, a.WINNERS_URL)
            self.assertIn('Round 155: 2016, first half.', result.source_details)
            self.assertTrue(any('Grove' in d or 'groveatlantic.com' in d for d in result.source_details))
            self.assertEqual(a.lookup('コンビニ人間', '村田沙耶香'), [result])
            self.assertEqual(a.lookup('Convenience Store Woman', '村田沙耶香'), [result])

    def test_nominee_lookup_review_and_unchecked(self):
        with patch.object(a, '_get_records', return_value=RECORDS):
            result = a.lookup('Deadline', 'Masaya Chiba')[0]
            self.assertEqual(result.award_year, 2019)
            self.assertEqual(result.status, 'Nominated')
            self.assertEqual(result.source_url, a.NOMINATION_PAGES[0][3])
            q = qualify_award_result(result)
            self.assertEqual(q.decision, QualificationDecision.REVIEW)
            self.assertFalse(default_award_row_checked(qualifies=q.decision is QualificationDecision.QUALIFIES,
                                                       identity_confirmation_required=False))
            self.assertEqual(a.lookup('悪い血', '鈴木涼美')[0].status, 'Nominated')

    def test_no_author_wide_awards_translator_match_or_unverified_expansion(self):
        with patch.object(a, '_get_records', return_value=RECORDS):
            for title, author in [('Earthlings', 'Sayaka Murata'), ('The Factory', 'Hiroko Oyamada'),
                                  ('Breasts and Eggs', 'Mieko Kawakami'), ('The Pregnancy Diary', 'Yoko Ogawa'),
                                  ('Convenience Store Woman', 'Ginny Tapley Takemori'),
                                  ('The Hole', 'David Boyd'), ('Norwegian Wood', 'Haruki Murakami'),
                                  ('Convenience Store Woman', 'Unknown')]:
                self.assertEqual(a.lookup(title, author), [], (title, author))

    def test_award_period_not_announcement_or_translation_year(self):
        with patch.object(a, '_get_records', return_value=RECORDS):
            self.assertEqual(a.lookup('The Hole', 'Hiroko Oyamada')[0].award_year, 2013)
            self.assertEqual(a.lookup('Snakes and Earrings', 'Hitomi Kanehara')[0].award_year, 2003)
            self.assertEqual(a.lookup('Idol, Burning', 'Rin Usami')[0].award_year, 2020)
            self.assertIn('Round 150: 2013, second half.', a.lookup('The Hole', 'Hiroko Oyamada')[0].source_details)

    def test_winners_are_not_duplicated_as_nominations(self):
        for number in (162, 175):
            group = [r for r in RECORDS if r.round_number == number]
            self.assertEqual(len(group), 5)
            self.assertEqual(sum(r.status == 'Winner' for r in group), 1)

    def test_marked_readings_are_preserved_without_becoming_title_text(self):
        r = next(r for r in WINNERS if r.round_number == 171 and r.author == '松永K三蔵')
        self.assertEqual(r.title, 'バリ山行')
        self.assertIn('さんこう', r.source_title)
        with patch.object(a, '_get_records', return_value=RECORDS):
            self.assertEqual(len(a.lookup(r.title, r.author)), 1)
            self.assertEqual(len(a.lookup(r.source_title, r.author)), 1)

    def test_original_historical_japanese_lookup(self):
        with patch.object(a, '_get_records', return_value=RECORDS):
            result = a.lookup('飼育', '大江健三郎')[0]
            self.assertEqual(result.award_year, 1958)
            self.assertEqual(result.status, 'Winner')

    def test_blank_identity_rejected(self):
        for title, author in [('', 'Sayaka Murata'), ('The Hole', ' ')]:
            with self.assertRaises(ValueError):
                a.lookup(title, author)

    def test_missing_joint_winner_period_and_duplicate_cache_rows_rejected(self):
        for rows in [tuple(r for r in WINNERS if not (r.round_number == 130 and r.author == '金原ひとみ')),
                     (replace(WINNERS[0], year=2025),) + WINNERS[1:], WINNERS + WINNERS[:1]]:
            with self.assertRaises(a.AkutagawaSourceError):
                a._validate_winners(rows)
        with self.assertRaises(a.AkutagawaSourceError):
            a._parse_winners('<html>Access denied</html>')

    def test_nomination_round_scope_wrong_page_and_partial_list(self):
        spec = a.NOMINATION_PAGES[0]
        self.assertEqual(len(a._parse_nominees(NOMINEES_HTML[162], spec)), 5)
        self.assertFalse(any(r.author == '小川哲' for r in a._parse_nominees(NOMINEES_HTML[162], spec)))
        for html in [NOMINEES_HTML[175], NOMINEES_HTML[162].replace('デッドライン', ''),
                     NOMINEES_HTML[162].replace('https://books.bunshun.jp', 'https://example.test')]:
            with self.assertRaises(a.AkutagawaSourceError):
                a._parse_nominees(html, spec)

    def test_cold_memory_and_persistent_cache_lookup(self):
        with patch.object(a, '_fetch_html', side_effect=fetch_fixture) as fetch:
            first = a.lookup('The Hole', 'Hiroko Oyamada')
            self.assertEqual(a.lookup('The Hole', 'Hiroko Oyamada'), first)
            self.assertEqual(fetch.call_count, 3)
        a._reset_runtime_state()
        with patch.object(a, '_fetch_html', side_effect=AssertionError('network')):
            self.assertEqual(a.lookup('The Hole', 'Hiroko Oyamada'), first)

    def test_stale_failure_keeps_validated_fallback_bytes(self):
        self.save(stale=True)
        path = Path(self.temp.name) / 'akutagawa.json'
        before = path.read_bytes()
        with patch.object(cache, 'try_claim_stale_refresh', return_value=True), patch.object(a, '_fetch_html', side_effect=a.AkutagawaSourceError('down')):
            self.assertEqual(a.lookup('The Hole', 'Hiroko Oyamada')[0].status, 'Winner')
        self.assertEqual(path.read_bytes(), before)

    def test_incomplete_nomination_download_does_not_publish_cache(self):
        def fetch(url):
            return '<html>blocked</html>' if url == a.NOMINATION_PAGES[1][3] else fetch_fixture(url)
        with patch.object(a, '_fetch_html', side_effect=fetch), self.assertRaises(a.AkutagawaSourceError):
            a.lookup('The Hole', 'Hiroko Oyamada')
        self.assertFalse((Path(self.temp.name) / 'akutagawa.json').exists())

    def test_corrupt_cache_rejected(self):
        for field, value in [('year', 2000), ('status', 'Finalist'), ('source_url', 'https://example.test'),
                             ('title', ''), ('author', 3)]:
            self.save()
            path = Path(self.temp.name) / 'akutagawa.json'
            payload = json.loads(path.read_text(encoding='utf-8'))
            payload['records'][0][field] = value
            path.write_text(json.dumps(payload), encoding='utf-8')
            self.assertIsNone(a._load_disk())

    def test_refresh_failure_preserves_request_then_success_clears(self):
        from awards.cache_control import refresh_award_source_cache
        self.save()
        a.lookup('The Hole', 'Hiroko Oyamada')
        path = Path(self.temp.name) / 'akutagawa.json'
        before = path.read_bytes()
        self.assertTrue(refresh_award_source_cache('akutagawa'))
        with patch.object(a, '_fetch_html', side_effect=a.AkutagawaSourceError('down')):
            self.assertEqual(a.lookup('The Hole', 'Hiroko Oyamada')[0].status, 'Winner')
        self.assertEqual(path.read_bytes(), before)
        self.assertTrue(cache.source_refresh_pending('akutagawa'))
        a._reset_runtime_state()
        with patch.object(a, '_fetch_html', side_effect=fetch_fixture):
            self.assertEqual(a.lookup('Deadline', 'Masaya Chiba')[0].status, 'Nominated')
        self.assertFalse(cache.source_refresh_pending('akutagawa'))

    def test_zip_resource_loader_uses_one_positional_argument(self):
        raw = (Path(__file__).parents[1] / 'awards/data/akutagawa_mappings.json').read_bytes()
        with patch.dict(a.__dict__, {'get_resources': lambda path: raw}):
            self.assertEqual(len(a._mappings()), 9)

    def test_registration_default_enabled_refresh_and_scope(self):
        from awards.source_registry import AWARD_SOURCES
        from awards.source_info import SOURCE_INFOS
        from awards.source_settings import compute_enabled_source_keys
        from awards.cache_control import runtime_reset_source_keys, BUNDLED_SOURCE_KEYS
        source = next(s for s in AWARD_SOURCES if s.key == 'akutagawa')
        self.assertIs(source.lookup, a.lookup)
        self.assertEqual(AWARD_SOURCES[-1], source)
        self.assertIn('akutagawa', compute_enabled_source_keys(tuple(s.key for s in AWARD_SOURCES), ['pulitzer']))
        self.assertIn('akutagawa', runtime_reset_source_keys())
        self.assertNotIn('akutagawa', BUNDLED_SOURCE_KEYS)
        info = next(i for i in SOURCE_INFOS if i.key == 'akutagawa')
        self.assertEqual(info.identity_scopes, ('work',))
        self.assertIn('162', info.limitation)
        self.assertIn('175', info.limitation)
