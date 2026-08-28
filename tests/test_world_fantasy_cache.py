"""Offline coverage for World Fantasy persistent archive cache."""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from awards import cache
from awards.engine import lookup_awards
from awards.sources import nebula, world_fantasy

_UTC = timezone.utc


def _wfa_record(
    year,
    category,
    status,
    title,
    author,
    source_url,
):
    authors = (author,) if isinstance(author, str) else author
    return world_fantasy._make_record(
        year, category, status, title, authors, source_url
    )


def _complete_archive(
    *,
    novel_title='The Forgotten Beasts of Eld',
    novel_author='Patricia A. McKillip',
):
    records: list[world_fantasy._ParsedRecord] = []

    def _add(year, category, status, title, author, url):
        records.append(_wfa_record(year, category, status, title, author, url))

    for year in sorted(world_fantasy.NOVEL_MASTER_WINNER_YEARS):
        if year == 1975:
            _add(
                year,
                world_fantasy.CATEGORY_NOVEL,
                'Winner',
                novel_title,
                novel_author,
                world_fantasy.WINNERS_URL,
            )
        else:
            _add(
                year,
                world_fantasy.CATEGORY_NOVEL,
                'Winner',
                f'Novel Winner {year}',
                'Pat Author',
                world_fantasy.WINNERS_URL,
            )
    for year in sorted(world_fantasy.NOVELLA_MASTER_WINNER_YEARS):
        _add(
            year,
            world_fantasy.CATEGORY_NOVELLA,
            'Winner',
            f'Novella Winner {year}',
            'Pat Author',
            world_fantasy.WINNERS_URL,
        )
    for year in sorted(world_fantasy.SHORT_FICTION_MASTER_WINNER_YEARS):
        _add(
            year,
            world_fantasy.CATEGORY_SHORT_FICTION,
            'Winner',
            f'Short Winner {year}',
            'Pat Author',
            world_fantasy.WINNERS_URL,
        )
    for year in sorted(world_fantasy.COLLECTION_MASTER_WINNER_YEARS):
        _add(
            year,
            world_fantasy.CATEGORY_COLLECTION,
            'Winner',
            f'Collection Winner {year}',
            'Pat Author',
            world_fantasy.WINNERS_URL,
        )

    nominee_pages = {
        1982: world_fantasy.CONVENTION_1982_URL,
        1993: world_fantasy.CONVENTION_1993_URL,
        2005: world_fantasy.CONVENTION_2005_URL,
    }
    for year, url in nominee_pages.items():
        for category in world_fantasy._CANONICAL_CATEGORIES:
            if year < world_fantasy._CATEGORY_FIRST_YEAR[category]:
                continue
            _add(
                year,
                category,
                'Nominee',
                f'{category} Nominee {year}',
                'Nom Author',
                url,
            )

    for category in world_fantasy._CANONICAL_CATEGORIES:
        _add(
            2013,
            category,
            'Nominee',
            f'{category} Nominee 2013',
            'Nom Author',
            world_fantasy.ANNUAL_2013_URL,
        )
    for year, url in (
        (2024, world_fantasy.ANNUAL_2024_URL),
        (2025, world_fantasy.ANNUAL_2025_URL),
    ):
        for category in world_fantasy._CANONICAL_CATEGORIES:
            _add(
                year,
                category,
                'Winner',
                f'{category} Winner {year}',
                'Pat Author',
                url,
            )
            _add(
                year,
                category,
                'Nominee',
                f'{category} Nominee {year}',
                'Nom Author',
                url,
            )
    return tuple(records)


def _save_disk(records, *, generated_at=None, ttl_seconds=None, version=None):
    cache.save_source_cache(
        world_fantasy.SOURCE_KEY,
        world_fantasy.CACHE_VERSION if version is None else version,
        records=[world_fantasy._record_to_cache_dict(record) for record in records],
        source_urls=world_fantasy._archive_source_urls(),
        coverage=world_fantasy._coverage_from_records(records),
        ttl_seconds=(
            world_fantasy.CACHE_TTL_SECONDS if ttl_seconds is None else ttl_seconds
        ),
        generated_at=generated_at,
    )


def _nebula_winner(config, year, title, author, slug):
    return nebula._ParsedRecord(
        award_year=year,
        award_name=config.award_name,
        category=config.category,
        status='Winner',
        work_title=title,
        work_author=author,
        source_url=f'https://nebulas.sfwa.org/nominated-work/{slug}/',
    )


def _nebula_complete_archive(*, dune=True):
    by_category = {}
    for config in nebula._AWARD_CONFIGS:
        if config is nebula._BEST_NOVEL_CONFIG and dune:
            record = _nebula_winner(
                config, config.first_year, 'Dune', 'Frank Herbert', 'dune'
            )
        else:
            record = _nebula_winner(
                config,
                config.first_year,
                f'{config.category} Book',
                'Pat Author',
                config.key,
            )
        by_category[config.key] = (record,)
    return by_category


def _save_nebula_disk(by_category, *, generated_at=None, ttl_seconds=None):
    records = []
    for config in nebula._AWARD_CONFIGS:
        records.extend(
            nebula._record_to_cache_dict(record)
            for record in by_category[config.key]
        )
    cache.save_source_cache(
        nebula.SOURCE_KEY,
        nebula.CACHE_VERSION,
        records=records,
        source_urls=nebula._archive_source_urls(),
        coverage=nebula._coverage_from_records(by_category),
        ttl_seconds=(
            nebula.CACHE_TTL_SECONDS if ttl_seconds is None else ttl_seconds
        ),
        generated_at=generated_at,
    )


class WorldFantasyPersistentCacheTests(unittest.TestCase):
    def setUp(self):
        world_fantasy._reset_runtime_state()
        cache._reset_runtime_state()
        self._temp = TemporaryDirectory()
        self.cache_dir = Path(self._temp.name)
        cache.set_cache_directory(self.cache_dir)

    def tearDown(self):
        world_fantasy._reset_runtime_state()
        cache._reset_runtime_state()
        self._temp.cleanup()

    def _disk_path(self):
        return self.cache_dir / 'world_fantasy.json'

    def test_cache_identity_constants(self):
        self.assertEqual(world_fantasy.SOURCE_KEY, 'world_fantasy')
        self.assertEqual(world_fantasy.CACHE_VERSION, 1)
        self.assertEqual(world_fantasy.CACHE_BASE_TTL_SECONDS, 7 * 24 * 60 * 60)
        self.assertEqual(world_fantasy.CACHE_REFRESH_OFFSET_SECONDS, 1 * 60 * 60)
        self.assertEqual(
            world_fantasy.CACHE_TTL_SECONDS,
            world_fantasy.CACHE_BASE_TTL_SECONDS
            + world_fantasy.CACHE_REFRESH_OFFSET_SECONDS,
        )
        self.assertEqual(
            world_fantasy.CACHE_TTL_SECONDS,
            7 * 24 * 60 * 60 + 60 * 60,
        )

    def test_complete_archive_helper_passes_source_validation(self):
        world_fantasy._validate_cached_archive(_complete_archive())

    def test_parsed_record_round_trips_all_fields(self):
        original = world_fantasy._ParsedRecord(
            award_year=1991,
            category=world_fantasy.CATEGORY_NOVEL,
            status='Nominee',
            work_title='Good Omens',
            work_author='Neil Gaiman and Terry Pratchett',
            source_url=world_fantasy.NOMINEES_URL,
            match_authors=('Neil Gaiman', 'Terry Pratchett'),
        )
        restored = world_fantasy._record_from_cache_dict(
            world_fantasy._record_to_cache_dict(original)
        )
        self.assertEqual(restored, original)
        self.assertIsInstance(restored.match_authors, tuple)
        self.assertEqual(
            restored.match_authors,
            ('Neil Gaiman', 'Terry Pratchett'),
        )

    def test_record_order_is_preserved(self):
        archive = _complete_archive()
        restored = world_fantasy._records_from_cache_payload(
            {
                'records': [
                    world_fantasy._record_to_cache_dict(record)
                    for record in archive
                ],
                'source_urls': list(world_fantasy._archive_source_urls()),
            }
        )
        self.assertEqual(restored, archive)
        self.assertEqual(
            [record.work_title for record in restored[:3]],
            [record.work_title for record in archive[:3]],
        )

    def test_fresh_cache_lookup_makes_zero_network_calls(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        world_fantasy._reset_runtime_state()
        with patch.object(
            world_fantasy, '_fetch_html', side_effect=AssertionError('network')
        ), patch.object(
            world_fantasy,
            '_fetch_source_pages',
            side_effect=AssertionError('network'),
        ), patch.object(
            world_fantasy,
            '_load_live_archive',
            side_effect=AssertionError('live'),
        ):
            results = world_fantasy.lookup(
                'The Forgotten Beasts of Eld', 'Patricia A. McKillip'
            )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].work_title, 'The Forgotten Beasts of Eld')
        self.assertEqual(results[0].work_author, 'Patricia A. McKillip')
        self.assertEqual(results[0].category, 'Novel')
        self.assertEqual(results[0].status, 'Winner')
        self.assertEqual(results[0].award_year, 1975)
        self.assertIsNone(results[0].rank)
        self.assertEqual(results[0].award_name, 'World Fantasy Award')
        self.assertEqual(results[0].source_name, 'World Fantasy Awards')
        self.assertEqual(results[0].source_url, world_fantasy.WINNERS_URL)
        self.assertEqual(
            world_fantasy._records_cache[0].work_title,
            'The Forgotten Beasts of Eld',
        )

    def test_fresh_cache_does_not_consume_refresh_budget(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        world_fantasy._reset_runtime_state()
        with cache.lookup_refresh_budget():
            with patch.object(
                world_fantasy,
                '_load_live_archive',
                side_effect=AssertionError('live'),
            ):
                results = world_fantasy.lookup(
                    'The Forgotten Beasts of Eld', 'Patricia A. McKillip'
                )
            self.assertEqual(results[0].work_title, 'The Forgotten Beasts of Eld')
            self.assertTrue(cache.try_claim_stale_refresh())

    def test_restart_simulation_reloads_disk_after_ram_clear(self):
        archive = _complete_archive()
        with patch.object(
            world_fantasy, '_load_live_archive', return_value=archive
        ) as live:
            first = world_fantasy.lookup(
                'The Forgotten Beasts of Eld', 'Patricia A. McKillip'
            )
        self.assertEqual(len(first), 1)
        self.assertEqual(live.call_count, 1)
        self.assertTrue(self._disk_path().is_file())
        world_fantasy._reset_runtime_state()
        self.assertTrue(self._disk_path().is_file())
        with patch.object(
            world_fantasy, '_fetch_html', side_effect=AssertionError('network')
        ), patch.object(
            world_fantasy, '_load_live_archive', side_effect=AssertionError('live')
        ):
            second = world_fantasy.lookup(
                'The Forgotten Beasts of Eld', 'Patricia A. McKillip'
            )
        self.assertEqual(len(second), 1)
        self.assertEqual(second[0].work_title, 'The Forgotten Beasts of Eld')

    def test_stale_cache_successful_refresh_replaces_disk(self):
        stale = _complete_archive()
        _save_disk(
            stale,
            generated_at=datetime(2020, 1, 1, tzinfo=_UTC),
            ttl_seconds=60,
        )
        original = self._disk_path().read_text(encoding='utf-8')
        refreshed = _complete_archive(novel_title='The New Beasts of Eld')
        with patch.object(
            world_fantasy, '_load_live_archive', return_value=refreshed
        ):
            results = world_fantasy.lookup(
                'The New Beasts of Eld', 'Patricia A. McKillip'
            )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].work_title, 'The New Beasts of Eld')
        updated = self._disk_path().read_text(encoding='utf-8')
        self.assertNotEqual(updated, original)
        payload = json.loads(updated)
        titles = [item['work_title'] for item in payload['records']]
        self.assertIn('The New Beasts of Eld', titles)
        self.assertNotIn('The Forgotten Beasts of Eld', titles)

    def test_stale_cache_claims_refresh_slot_inside_lookup_budget(self):
        stale = _complete_archive()
        _save_disk(
            stale,
            generated_at=datetime(2020, 1, 1, tzinfo=_UTC),
            ttl_seconds=60,
        )
        world_fantasy._reset_runtime_state()
        refreshed = _complete_archive(novel_title='The New Beasts of Eld')
        with cache.lookup_refresh_budget():
            with patch.object(
                world_fantasy, '_load_live_archive', return_value=refreshed
            ):
                results = world_fantasy.lookup(
                    'The New Beasts of Eld', 'Patricia A. McKillip'
                )
            self.assertEqual(results[0].work_title, 'The New Beasts of Eld')
            self.assertFalse(cache.try_claim_stale_refresh())

    def test_stale_cache_failed_refresh_uses_stale_and_keeps_file(self):
        stale = _complete_archive()
        _save_disk(
            stale,
            generated_at=datetime(2020, 1, 1, tzinfo=_UTC),
            ttl_seconds=60,
        )
        original = self._disk_path().read_text(encoding='utf-8')
        with patch.object(
            world_fantasy,
            '_load_live_archive',
            side_effect=world_fantasy.WorldFantasySourceError('site down'),
        ):
            results = world_fantasy.lookup(
                'The Forgotten Beasts of Eld', 'Patricia A. McKillip'
            )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].work_title, 'The Forgotten Beasts of Eld')
        self.assertEqual(self._disk_path().read_text(encoding='utf-8'), original)

    def test_stale_cache_without_refresh_slot_uses_stale_and_skips_network(self):
        stale = _complete_archive()
        _save_disk(
            stale,
            generated_at=datetime(2020, 1, 1, tzinfo=_UTC),
            ttl_seconds=60,
        )
        world_fantasy._reset_runtime_state()
        with cache.lookup_refresh_budget():
            self.assertTrue(cache.try_claim_stale_refresh())
            with patch.object(
                world_fantasy,
                '_load_live_archive',
                side_effect=AssertionError('live'),
            ) as mocked:
                results = world_fantasy.lookup(
                    'The Forgotten Beasts of Eld', 'Patricia A. McKillip'
                )
            mocked.assert_not_called()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].work_title, 'The Forgotten Beasts of Eld')

    def test_missing_cache_live_fetches_after_stale_refresh_budget_consumed(self):
        self.assertFalse(self._disk_path().is_file())
        live = _complete_archive()
        with cache.lookup_refresh_budget():
            self.assertTrue(cache.try_claim_stale_refresh())
            with patch.object(
                world_fantasy, '_load_live_archive', return_value=live
            ) as mocked:
                results = world_fantasy.lookup(
                    'The Forgotten Beasts of Eld', 'Patricia A. McKillip'
                )
            self.assertEqual(mocked.call_count, 1)
        self.assertEqual(results[0].work_title, 'The Forgotten Beasts of Eld')

    def test_unsupported_category_is_rejected(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        payload = json.loads(self._disk_path().read_text(encoding='utf-8'))
        payload['records'][0]['category'] = 'Anthology'
        payload['record_count'] = len(payload['records'])
        self._disk_path().write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + '\n',
            encoding='utf-8',
        )
        live = _complete_archive()
        with patch.object(
            world_fantasy, '_load_live_archive', return_value=live
        ) as mocked:
            world_fantasy.lookup(
                'The Forgotten Beasts of Eld', 'Patricia A. McKillip'
            )
        self.assertEqual(mocked.call_count, 1)

    def test_missing_historical_coverage_is_rejected(self):
        cache.save_source_cache(
            world_fantasy.SOURCE_KEY,
            world_fantasy.CACHE_VERSION,
            records=[
                world_fantasy._record_to_cache_dict(
                    _wfa_record(
                        1975,
                        world_fantasy.CATEGORY_NOVEL,
                        'Winner',
                        'The Forgotten Beasts of Eld',
                        'Patricia A. McKillip',
                        world_fantasy.WINNERS_URL,
                    )
                )
            ],
            source_urls=world_fantasy._archive_source_urls(),
            coverage={'categories': []},
            ttl_seconds=world_fantasy.CACHE_TTL_SECONDS,
            generated_at=datetime.now(_UTC),
        )
        live = _complete_archive()
        with patch.object(
            world_fantasy, '_load_live_archive', return_value=live
        ) as mocked:
            results = world_fantasy.lookup(
                'The Forgotten Beasts of Eld', 'Patricia A. McKillip'
            )
        self.assertEqual(mocked.call_count, 1)
        self.assertEqual(results[0].work_title, 'The Forgotten Beasts of Eld')

    def test_invalid_year_is_rejected(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        payload = json.loads(self._disk_path().read_text(encoding='utf-8'))
        payload['records'][0]['award_year'] = 12
        self._disk_path().write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + '\n',
            encoding='utf-8',
        )
        live = _complete_archive()
        with patch.object(
            world_fantasy, '_load_live_archive', return_value=live
        ) as mocked:
            world_fantasy.lookup(
                'The Forgotten Beasts of Eld', 'Patricia A. McKillip'
            )
        self.assertEqual(mocked.call_count, 1)

    def test_invalid_status_is_rejected(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        payload = json.loads(self._disk_path().read_text(encoding='utf-8'))
        payload['records'][0]['status'] = 'Finalist'
        self._disk_path().write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + '\n',
            encoding='utf-8',
        )
        live = _complete_archive()
        with patch.object(
            world_fantasy, '_load_live_archive', return_value=live
        ) as mocked:
            world_fantasy.lookup(
                'The Forgotten Beasts of Eld', 'Patricia A. McKillip'
            )
        self.assertEqual(mocked.call_count, 1)

    def test_malformed_match_authors_is_rejected(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        payload = json.loads(self._disk_path().read_text(encoding='utf-8'))
        payload['records'][0]['match_authors'] = 'Patricia A. McKillip'
        self._disk_path().write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + '\n',
            encoding='utf-8',
        )
        live = _complete_archive()
        with patch.object(
            world_fantasy, '_load_live_archive', return_value=live
        ) as mocked:
            world_fantasy.lookup(
                'The Forgotten Beasts of Eld', 'Patricia A. McKillip'
            )
        self.assertEqual(mocked.call_count, 1)

    def test_record_missing_required_field_is_rejected(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        payload = json.loads(self._disk_path().read_text(encoding='utf-8'))
        del payload['records'][0]['work_title']
        self._disk_path().write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + '\n',
            encoding='utf-8',
        )
        live = _complete_archive()
        with patch.object(
            world_fantasy, '_load_live_archive', return_value=live
        ) as mocked:
            world_fantasy.lookup(
                'The Forgotten Beasts of Eld', 'Patricia A. McKillip'
            )
        self.assertEqual(mocked.call_count, 1)

    def test_version_mismatch_uses_live_path(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC), version=2)
        live = _complete_archive()
        with patch.object(
            world_fantasy, '_load_live_archive', return_value=live
        ) as mocked:
            results = world_fantasy.lookup(
                'The Forgotten Beasts of Eld', 'Patricia A. McKillip'
            )
        self.assertEqual(mocked.call_count, 1)
        self.assertEqual(results[0].work_title, 'The Forgotten Beasts of Eld')

    def test_save_failure_does_not_fail_lookup(self):
        archive = _complete_archive()
        with patch.object(
            world_fantasy, '_load_live_archive', return_value=archive
        ):
            with patch.object(
                world_fantasy.cache,
                'save_source_cache',
                side_effect=OSError('disk full'),
            ):
                results = world_fantasy.lookup(
                    'The Forgotten Beasts of Eld', 'Patricia A. McKillip'
                )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].work_title, 'The Forgotten Beasts of Eld')

    def test_ram_reset_does_not_delete_disk_cache(self):
        archive = _complete_archive()
        _save_disk(archive, generated_at=datetime.now(_UTC))
        world_fantasy._records_cache = archive
        self.assertTrue(self._disk_path().is_file())
        world_fantasy._reset_runtime_state()
        self.assertTrue(self._disk_path().is_file())
        self.assertIsNone(world_fantasy._records_cache)
        with patch.object(
            world_fantasy, '_load_live_archive', side_effect=AssertionError('live')
        ):
            results = world_fantasy.lookup(
                'The Forgotten Beasts of Eld', 'Patricia A. McKillip'
            )
        self.assertEqual(results[0].work_title, 'The Forgotten Beasts of Eld')


class WorldFantasyNebulaRefreshBudgetTests(unittest.TestCase):
    def setUp(self):
        world_fantasy._reset_runtime_state()
        nebula._clear_caches_for_tests()
        cache._reset_runtime_state()
        self._temp = TemporaryDirectory()
        self.cache_dir = Path(self._temp.name)
        cache.set_cache_directory(self.cache_dir)

    def tearDown(self):
        world_fantasy._reset_runtime_state()
        nebula._clear_caches_for_tests()
        cache._reset_runtime_state()
        self._temp.cleanup()

    def test_one_optional_refresh_per_engine_lookup_then_fresh_budget(self):
        wfa_stale = _complete_archive()
        nebula_stale = _nebula_complete_archive()
        _save_disk(
            wfa_stale,
            generated_at=datetime(2020, 1, 1, tzinfo=_UTC),
            ttl_seconds=60,
        )
        _save_nebula_disk(
            nebula_stale,
            generated_at=datetime(2020, 1, 1, tzinfo=_UTC),
            ttl_seconds=60,
        )
        world_fantasy._reset_runtime_state()
        nebula._clear_caches_for_tests()

        with patch.object(
            nebula, '_load_live_archive', return_value=nebula_stale
        ) as nebula_live, patch.object(
            world_fantasy, '_load_live_archive', return_value=wfa_stale
        ) as wfa_live:
            first = lookup_awards(
                'Dune',
                'Frank Herbert',
                enabled_source_keys=('nebula', 'world_fantasy'),
            )
            self.assertEqual(len(first.failures), 0)
            self.assertTrue(
                any(
                    item.result.work_title == 'Dune'
                    for item in first.assessments
                )
            )
            first_nebula = nebula_live.call_count
            first_wfa = wfa_live.call_count
            self.assertEqual(first_nebula + first_wfa, 1)

            world_fantasy._reset_runtime_state()
            nebula._clear_caches_for_tests()
            second = lookup_awards(
                'Dune',
                'Frank Herbert',
                enabled_source_keys=('nebula', 'world_fantasy'),
            )
            self.assertEqual(len(second.failures), 0)
            second_nebula = nebula_live.call_count - first_nebula
            second_wfa = wfa_live.call_count - first_wfa
            self.assertEqual(second_nebula + second_wfa, 1)
            if first_nebula:
                self.assertEqual((second_nebula, second_wfa), (0, 1))
            else:
                self.assertEqual((second_nebula, second_wfa), (1, 0))


if __name__ == '__main__':
    unittest.main()
