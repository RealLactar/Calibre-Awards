"""Offline regressions against cropped official live Médicis HTML."""
import json
import unittest
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from awards import cache, cache_control
from awards.sources import medicis as m
from awards.qualifier import qualify_award_result, QualificationDecision
from awards.presentation import default_award_row_checked
F = Path(__file__).parent / 'fixtures' / 'medicis'
HTML = (F / 'winners.html').read_text(encoding='utf-8')
SHTML = (F / 'selection-2026.html').read_text(encoding='utf-8')
W = m._parse_winners(HTML)
S = m._parse_selection(SHTML)
ROWS = W + S

class MedicisTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        cache.set_cache_directory(self.temp.name)
        m._reset_runtime_state()
    def tearDown(self):
        m._reset_runtime_state()
        cache._reset_runtime_state()
        self.temp.cleanup()
    def save(self, stale=False):
        cache.save_source_cache(m.SOURCE_KEY, m.CACHE_VERSION, records=[asdict(r) for r in ROWS], source_urls=m.SOURCE_URLS,
            coverage={'selection_rounds': ['2026-first']}, ttl_seconds=m.CACHE_TTL_SECONDS,
            generated_at=datetime(2000, 1, 1, tzinfo=timezone.utc) if stale else None)
    def fetch(self, url):
        return HTML if url == m.WINNERS_URL else SHTML
    def lookup(self, title, author):
        with patch.object(m, '_get_records', return_value=ROWS):
            return m.lookup(title, author)
    def test_full_history_and_categories(self):
        self.assertEqual(len(W), 168)
        self.assertEqual({r.year for r in W if r.category == m.CATEGORIES[0]}, set(range(1958, 2026)))
        self.assertEqual(min(r.year for r in W if r.category == 'Essai'), 1985)
        self.assertEqual(len(S), 35)
        self.assertEqual(sum(r.category == m.CATEGORIES[0] for r in S), 18)
        self.assertTrue(all(r.status == 'Selected' and r.year == 2026 for r in S))
    def test_verified_english_winner_and_provenance(self):
        r = self.lookup('The Mars Room', 'Rachel Kushner')[0]
        self.assertEqual((r.work_title, r.work_author, r.award_year, r.category, r.status), ('Le Mars Club', 'Rachel Kushner', 2018, 'Littérature étrangère', 'Winner'))
        self.assertEqual(r.source_url, m.WINNERS_URL)
        self.assertIsNone(r.rank)
        self.assertEqual(qualify_award_result(r).decision, QualificationDecision.QUALIFIES)
        self.assertTrue(default_award_row_checked(qualifies=True, identity_confirmation_required=r.identity_confirmation_required))
        self.assertIn('Verified English title:', ' '.join(r.source_details))
    def test_french_winner(self):
        self.assertEqual(self.lookup('La Mise en scène', 'Claude Ollier')[0].award_year, 1958)
    def test_candidates_review_unchecked(self):
        r = self.lookup('Décolorer sa fille', 'Lucie Bérard')[0]
        self.assertEqual(r.status, 'Selected')
        self.assertEqual(r.source_url, m.SELECTION_URL)
        self.assertEqual(qualify_award_result(r).decision, QualificationDecision.REVIEW)
        self.assertEqual(qualify_award_result(r).reason, 'Status meaning depends on the structure of the specific award.')
        self.assertFalse(default_award_row_checked(qualifies=False, identity_confirmation_required=False))
        self.assertIn('Première sélection', ' '.join(r.source_details))
    def test_split_author_markup_and_commas_in_titles(self):
        self.assertEqual(self.lookup('Tuer le vieux', 'Daria Marx')[0].work_author, 'Daria Marx')
        self.assertEqual(self.lookup('C’était ça, ou mourir', 'Thélyson Orélien')[0].work_title, 'C’était ça, ou mourir')
        self.assertEqual(self.lookup('Déclin et fascination', 'Eva Baltasar')[0].work_title, 'Déclin et fascination')
    def test_translators_and_wrong_author_do_not_match(self):
        for title, author in [('The Mars Room', 'Sylvie Schneiter'), ('The Mars Room', 'Other Author'), ('Creation Lake', 'Rachel Kushner'), ('Déclin et fascination', 'Annie Bats')]:
            self.assertEqual(self.lookup(title, author), [])
    def test_normalization_without_guessed_translations(self):
        self.assertEqual(len(self.lookup("C'était ça, ou mourir", 'THÉLYSON ORÉLIEN')), 1)
        self.assertEqual(self.lookup('Discolor Her Daughter', 'Lucie Bérard'), [])
    def test_joint_winners_preserved(self):
        self.assertEqual(sum(r.year == 2025 and r.category == m.CATEGORIES[1] for r in W), 2)
        rows = [r for r in W if not (r.year == 2025 and r.author == 'Nina Allan')]
        with self.assertRaises(m.MedicisSourceError):
            m._validate_winners(rows)
    def test_specific_volume_requires_confirmation(self):
        row = next(r for r in W if r.year == 2024 and r.category == 'Essai')
        r = self.lookup(row.title, row.author)[0]
        self.assertTrue(r.identity_confirmation_required)
        self.assertFalse(default_award_row_checked(qualifies=True, identity_confirmation_required=True))
        self.assertEqual(self.lookup('Kafka', row.author), [])
    def test_incomplete_and_wrong_pages_rejected(self):
        for html in [HTML.replace('graduates-table', 'other-table'), HTML.replace('1958', '1957'), HTML.replace('graduate-link__title', 'unknown-title')]:
            with self.assertRaises(m.MedicisSourceError):
                m._parse_winners(html)
        for html in [SHTML.replace('Première sélection du Prix Médicis 2026', 'Other award'), SHTML.replace('<strong>Lucie Bérard</strong>', ''), SHTML.replace('<em>Décolorer sa fille</em>', '')]:
            with self.assertRaises(m.MedicisSourceError):
                m._parse_selection(html)
    def test_coauthors_not_split_into_individual_awards(self):
        r = self.lookup('La Vie sauve', 'Marie Desplechin et Lydie Violet')[0]
        self.assertEqual(r.award_year, 2005)
        self.assertEqual(self.lookup('La Vie sauve', 'Marie Desplechin'), [])
    def test_winner_supersedes_selected_same_work_year_category(self):
        r = S[0]
        rows = m._merge((r, replace(r, status='Winner', source_url=m.WINNERS_URL)))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].status, 'Winner')
    def test_fresh_disk_avoids_network(self):
        self.save()
        with patch.object(m, '_fetch_html', side_effect=AssertionError('network')):
            self.assertEqual(len(m.lookup('The Mars Room', 'Rachel Kushner')), 1)
    def test_initial_fetch_persists_validated_records(self):
        with patch.object(m, '_fetch_html', side_effect=self.fetch) as fetch:
            self.assertEqual(len(m.lookup('The Mars Room', 'Rachel Kushner')), 1)
            self.assertEqual(fetch.call_count, 2)
        self.assertIsNotNone(m._load_disk())
    def test_refresh_failure_keeps_fallback_and_pending_then_recovers(self):
        self.save()
        path = Path(self.temp.name) / 'medicis.json'
        before = path.read_bytes()
        self.assertTrue(cache_control.refresh_award_source_cache('medicis'))
        with patch.object(m, '_fetch_html', side_effect=m.MedicisSourceError('outage')):
            self.assertEqual(len(m.lookup('The Mars Room', 'Rachel Kushner')), 1)
        self.assertEqual(path.read_bytes(), before)
        self.assertTrue(cache.source_refresh_pending('medicis'))
        cache_control.prepare_source_lookup('medicis')
        with patch.object(m, '_fetch_html', side_effect=self.fetch):
            self.assertEqual(len(m.lookup('The Mars Room', 'Rachel Kushner')), 1)
        self.assertFalse(cache.source_refresh_pending('medicis'))
    def test_stale_failure_keeps_validated_disk(self):
        self.save(stale=True)
        with patch.object(m, '_fetch_html', side_effect=m.MedicisSourceError('outage')):
            self.assertEqual(len(m.lookup('The Mars Room', 'Rachel Kushner')), 1)
    def test_no_disk_failure_surfaces_source_problem(self):
        with patch.object(m, '_fetch_html', side_effect=m.MedicisSourceError('outage')):
            with self.assertRaises(m.MedicisSourceError):
                m.lookup('The Mars Room', 'Rachel Kushner')
    def test_tampered_cache_is_rejected(self):
        for field, value in [('status', 'Nominated'), ('source_url', 'https://other.example/'), ('year', 1900), ('title', ''), ('author', '')]:
            self.save()
            path = Path(self.temp.name) / 'medicis.json'
            payload = json.loads(path.read_text(encoding='utf-8'))
            payload['records'][0][field] = value
            path.write_text(json.dumps(payload), encoding='utf-8')
            self.assertIsNone(m._load_disk())
    def test_zip_resource_loader_and_registry(self):
        raw = (Path(m.__file__).parents[1] / 'data/medicis_mappings.json').read_bytes()
        with patch.object(m, 'get_resources', return_value=raw, create=True) as resource:
            self.assertEqual(len(m._mappings()), 1)
            resource.assert_called_once_with('awards/data/medicis_mappings.json')
        from awards.source_registry import AWARD_SOURCES
        self.assertIn('medicis', {s.key for s in AWARD_SOURCES})
        self.assertNotIn('medicis', cache_control.BUNDLED_SOURCE_KEYS)
