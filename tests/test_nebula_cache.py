"""Offline coverage for Nebula persistent archive cache."""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from awards import cache
from awards.sources import nebula

_UTC = timezone.utc


def _winner(config, year, title, author, slug):
    return nebula._ParsedRecord(
        award_year=year,
        award_name=config.award_name,
        category=config.category,
        status='Winner',
        work_title=title,
        work_author=author,
        source_url=f'https://nebulas.sfwa.org/nominated-work/{slug}/',
    )


def _complete_archive(*, dune=True):
    by_category = {}
    for config in nebula._AWARD_CONFIGS:
        if config is nebula._BEST_NOVEL_CONFIG and dune:
            record = _winner(
                config, config.first_year, 'Dune', 'Frank Herbert', 'dune'
            )
        else:
            record = _winner(
                config,
                config.first_year,
                f'{config.category} Book',
                'Pat Author',
                config.key,
            )
        by_category[config.key] = (record,)
    return by_category


def _save_disk(by_category, *, generated_at=None, ttl_seconds=None, version=None):
    records = []
    for config in nebula._AWARD_CONFIGS:
        records.extend(
            nebula._record_to_cache_dict(record)
            for record in by_category[config.key]
        )
    cache.save_source_cache(
        nebula.SOURCE_KEY,
        nebula.CACHE_VERSION if version is None else version,
        records=records,
        source_urls=nebula._archive_source_urls(),
        coverage=nebula._coverage_from_records(by_category),
        ttl_seconds=(
            nebula.CACHE_TTL_SECONDS if ttl_seconds is None else ttl_seconds
        ),
        generated_at=generated_at,
    )


class NebulaPersistentCacheTests(unittest.TestCase):
    def setUp(self):
        nebula._clear_caches_for_tests()
        cache._reset_runtime_state()
        self._temp = TemporaryDirectory()
        self.cache_dir = Path(self._temp.name)
        cache.set_cache_directory(self.cache_dir)

    def tearDown(self):
        nebula._clear_caches_for_tests()
        cache._reset_runtime_state()
        self._temp.cleanup()

    def _disk_path(self):
        return self.cache_dir / 'nebula.json'

    def test_cache_identity_constants(self):
        self.assertEqual(nebula.SOURCE_KEY, 'nebula')
        self.assertEqual(nebula.CACHE_VERSION, 1)
        self.assertEqual(nebula.CACHE_BASE_TTL_SECONDS, 7 * 24 * 60 * 60)
        self.assertEqual(nebula.CACHE_REFRESH_OFFSET_SECONDS, 0)
        self.assertEqual(
            nebula.CACHE_TTL_SECONDS,
            nebula.CACHE_BASE_TTL_SECONDS + nebula.CACHE_REFRESH_OFFSET_SECONDS,
        )
        self.assertEqual(nebula.CACHE_TTL_SECONDS, 7 * 24 * 60 * 60)

    def test_parsed_record_round_trips_all_fields(self):
        original = nebula._ParsedRecord(
            award_year=1990,
            award_name=nebula.AWARD_NAME_NEBULA,
            category=nebula.CATEGORY_BEST_NOVELLA,
            status='Nominated',
            work_title='The Hemingway Hoax',
            work_author='',
            source_url=None,
        )
        restored = nebula._record_from_cache_dict(
            nebula._record_to_cache_dict(original)
        )
        self.assertEqual(restored, original)
        self.assertIsInstance(restored.source_url, type(None))

    def test_fresh_cache_lookup_makes_zero_network_calls(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        nebula._clear_caches_for_tests()
        with patch.object(
            nebula, '_fetch_html', side_effect=AssertionError('network')
        ), patch.object(
            nebula,
            '_fetch_category_pages',
            side_effect=AssertionError('network'),
        ), patch.object(
            nebula,
            '_load_live_archive',
            side_effect=AssertionError('live'),
        ):
            results = nebula.lookup('Dune', 'Frank Herbert')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].work_title, 'Dune')
        self.assertEqual(results[0].work_author, 'Frank Herbert')
        self.assertEqual(results[0].category, 'Best Novel')
        self.assertEqual(results[0].status, 'Winner')
        self.assertIsNone(results[0].rank)
        self.assertEqual(
            nebula._records_cache[nebula._BEST_NOVEL_CONFIG.key][0].work_title,
            'Dune',
        )
        self.assertEqual(nebula._pages_cache, {})

    def test_fresh_cache_does_not_consume_refresh_budget(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        nebula._clear_caches_for_tests()
        with cache.lookup_refresh_budget():
            with patch.object(
                nebula, '_load_live_archive', side_effect=AssertionError('live')
            ):
                results = nebula.lookup('Dune', 'Frank Herbert')
            self.assertEqual(results[0].work_title, 'Dune')
            self.assertTrue(cache.try_claim_stale_refresh())

    def test_stale_cache_claims_refresh_slot_inside_lookup_budget(self):
        stale = _complete_archive()
        _save_disk(
            stale,
            generated_at=datetime(2020, 1, 1, tzinfo=_UTC),
            ttl_seconds=60,
        )
        nebula._clear_caches_for_tests()
        refreshed = _complete_archive(dune=False)
        novel = nebula._BEST_NOVEL_CONFIG
        refreshed[novel.key] = (
            _winner(novel, novel.first_year, 'New Dune', 'Frank Herbert', 'new-dune'),
        )
        with cache.lookup_refresh_budget():
            with patch.object(nebula, '_load_live_archive', return_value=refreshed):
                results = nebula.lookup('New Dune', 'Frank Herbert')
            self.assertEqual(results[0].work_title, 'New Dune')
            self.assertFalse(cache.try_claim_stale_refresh())

    def test_stale_cache_without_refresh_slot_uses_stale_and_skips_network(self):
        stale = _complete_archive()
        _save_disk(
            stale,
            generated_at=datetime(2020, 1, 1, tzinfo=_UTC),
            ttl_seconds=60,
        )
        nebula._clear_caches_for_tests()
        with cache.lookup_refresh_budget():
            self.assertTrue(cache.try_claim_stale_refresh())
            with patch.object(
                nebula, '_load_live_archive', side_effect=AssertionError('live')
            ) as mocked:
                results = nebula.lookup('Dune', 'Frank Herbert')
            mocked.assert_not_called()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].work_title, 'Dune')

    def test_missing_cache_live_fetches_after_stale_refresh_budget_consumed(self):
        self.assertFalse(self._disk_path().is_file())
        live = _complete_archive()
        with cache.lookup_refresh_budget():
            self.assertTrue(cache.try_claim_stale_refresh())
            with patch.object(
                nebula, '_load_live_archive', return_value=live
            ) as mocked:
                results = nebula.lookup('Dune', 'Frank Herbert')
            self.assertEqual(mocked.call_count, 1)
        self.assertEqual(results[0].work_title, 'Dune')

    def test_restart_simulation_reloads_disk_after_ram_clear(self):
        archive = _complete_archive()
        with patch.object(nebula, '_load_live_archive', return_value=archive) as live:
            first = nebula.lookup('Dune', 'Frank Herbert')
        self.assertEqual(len(first), 1)
        self.assertEqual(live.call_count, 1)
        self.assertTrue(self._disk_path().is_file())
        nebula._clear_caches_for_tests()
        self.assertTrue(self._disk_path().is_file())
        with patch.object(
            nebula, '_fetch_html', side_effect=AssertionError('network')
        ), patch.object(
            nebula, '_load_live_archive', side_effect=AssertionError('live')
        ):
            second = nebula.lookup('Dune', 'Frank Herbert')
        self.assertEqual(len(second), 1)
        self.assertEqual(second[0].work_title, 'Dune')

    def test_stale_cache_successful_refresh_replaces_disk(self):
        stale = _complete_archive()
        _save_disk(
            stale,
            generated_at=datetime(2020, 1, 1, tzinfo=_UTC),
            ttl_seconds=60,
        )
        original = self._disk_path().read_text(encoding='utf-8')
        refreshed = _complete_archive(dune=False)
        novel = nebula._BEST_NOVEL_CONFIG
        refreshed[novel.key] = (
            _winner(novel, novel.first_year, 'New Dune', 'Frank Herbert', 'new-dune'),
        )
        with patch.object(nebula, '_load_live_archive', return_value=refreshed):
            results = nebula.lookup('New Dune', 'Frank Herbert')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].work_title, 'New Dune')
        updated = self._disk_path().read_text(encoding='utf-8')
        self.assertNotEqual(updated, original)
        payload = json.loads(updated)
        titles = [item['work_title'] for item in payload['records']]
        self.assertIn('New Dune', titles)
        self.assertNotIn('Dune', titles)

    def test_stale_cache_failed_refresh_uses_stale_and_keeps_file(self):
        stale = _complete_archive()
        _save_disk(
            stale,
            generated_at=datetime(2020, 1, 1, tzinfo=_UTC),
            ttl_seconds=60,
        )
        original = self._disk_path().read_text(encoding='utf-8')
        with patch.object(
            nebula,
            '_load_live_archive',
            side_effect=nebula.NebulaSourceError('sfwa down'),
        ):
            results = nebula.lookup('Dune', 'Frank Herbert')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].work_title, 'Dune')
        self.assertEqual(self._disk_path().read_text(encoding='utf-8'), original)

    def test_incomplete_cached_archive_is_rejected(self):
        novel = nebula._BEST_NOVEL_CONFIG
        cache.save_source_cache(
            nebula.SOURCE_KEY,
            nebula.CACHE_VERSION,
            records=[
                nebula._record_to_cache_dict(
                    _winner(novel, 1965, 'Dune', 'Frank Herbert', 'dune')
                )
            ],
            source_urls=nebula._archive_source_urls(),
            coverage={'categories': []},
            ttl_seconds=nebula.CACHE_TTL_SECONDS,
            generated_at=datetime.now(_UTC),
        )
        live = _complete_archive()
        with patch.object(nebula, '_load_live_archive', return_value=live) as mocked:
            results = nebula.lookup('Dune', 'Frank Herbert')
        self.assertEqual(mocked.call_count, 1)
        self.assertEqual(results[0].work_title, 'Dune')

    def test_malformed_source_specific_record_is_rejected(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        payload = json.loads(self._disk_path().read_text(encoding='utf-8'))
        payload['records'][0]['status'] = 'Finalist'
        payload['record_count'] = len(payload['records'])
        self._disk_path().write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + '\n',
            encoding='utf-8',
        )
        live = _complete_archive()
        with patch.object(nebula, '_load_live_archive', return_value=live) as mocked:
            nebula.lookup('Dune', 'Frank Herbert')
        self.assertEqual(mocked.call_count, 1)

    def test_version_mismatch_uses_live_path(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC), version=2)
        live = _complete_archive()
        with patch.object(nebula, '_load_live_archive', return_value=live) as mocked:
            results = nebula.lookup('Dune', 'Frank Herbert')
        self.assertEqual(mocked.call_count, 1)
        self.assertEqual(results[0].work_title, 'Dune')

    def test_missing_cache_and_network_failure_raises(self):
        with patch.object(
            nebula,
            '_load_live_archive',
            side_effect=nebula.NebulaSourceError('blocked'),
        ):
            with self.assertRaises(nebula.NebulaSourceError) as caught:
                nebula.lookup('Dune', 'Frank Herbert')
        self.assertEqual(str(caught.exception), 'blocked')

    def test_save_failure_does_not_fail_lookup(self):
        archive = _complete_archive()
        with patch.object(nebula, '_load_live_archive', return_value=archive):
            with patch.object(
                nebula.cache,
                'save_source_cache',
                side_effect=OSError('disk full'),
            ):
                results = nebula.lookup('Dune', 'Frank Herbert')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].work_title, 'Dune')

    def test_ram_reset_does_not_delete_disk_cache(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        nebula._install_ram_records(archive)
        self.assertTrue(self._disk_path().is_file())
        nebula._clear_caches_for_tests()
        self.assertTrue(self._disk_path().is_file())
        self.assertEqual(nebula._records_cache, {})
        with patch.object(
            nebula, '_load_live_archive', side_effect=AssertionError('live')
        ):
            results = nebula.lookup('Dune', 'Frank Herbert')
        self.assertEqual(results[0].work_title, 'Dune')


if __name__ == '__main__':
    unittest.main()
