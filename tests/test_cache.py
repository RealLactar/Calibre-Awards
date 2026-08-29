"""Offline coverage for the Calibre-free persistent source cache."""

from __future__ import annotations

import hashlib
import json
import os
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from awards import cache


def _utc(year=2026, month=1, day=1, hour=0, minute=0, second=0) -> datetime:
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


def _records():
    return [
        {'title': 'Dune', 'year': 1966},
        {'title': 'The Left Hand of Darkness', 'year': 1970},
    ]


def _save(source_key='nebula', version=1, **overrides):
    values = {
        'records': _records(),
        'source_urls': [
            'https://nebulas.sfwa.org/award/best-novel/',
            'https://nebulas.sfwa.org/award/best-novella/',
        ],
        'coverage': {'min_year': 1965, 'max_year': 2026},
        'ttl_seconds': 3600,
        'generated_at': _utc(),
    }
    values.update(overrides)
    cache.save_source_cache(source_key, version, **values)


class CacheTestCase(unittest.TestCase):
    def setUp(self):
        cache._reset_runtime_state()
        self._temp = TemporaryDirectory()
        self.cache_dir = Path(self._temp.name)

    def tearDown(self):
        cache._reset_runtime_state()
        self._temp.cleanup()

    def _configure(self):
        cache.set_cache_directory(self.cache_dir)


class CacheConfigurationTests(CacheTestCase):
    def test_unconfigured_load_is_none(self):
        self.assertIsNone(cache.load_source_cache('nebula', 1))

    def test_unconfigured_save_is_harmless(self):
        cache.save_source_cache(
            'nebula',
            1,
            records=_records(),
            source_urls=['https://example.test/archive'],
            coverage={},
            ttl_seconds=60,
            generated_at=_utc(),
        )
        self.assertEqual(os.listdir(self.cache_dir), [])

    def test_unconfigured_invalidation_is_harmless(self):
        cache.invalidate_source_cache('nebula')
        cache.invalidate_all_source_caches()
        cache.invalidate_cache_entry(
            'locus',
            'authors',
            'https://www.sfadb.com/Dan_Simmons',
        )

    def test_configured_directory_receives_files(self):
        self._configure()
        _save()
        path = self.cache_dir / 'nebula.json'
        self.assertTrue(path.is_file())
        self.assertTrue(path.read_text(encoding='utf-8'))

    def test_relative_directory_is_rejected(self):
        with self.assertRaises(ValueError):
            cache.set_cache_directory('relative-cache-dir')

    def test_source_cache_directory_joins_config_dir(self):
        path = cache.source_cache_directory(self.cache_dir)
        self.assertEqual(
            path,
            self.cache_dir / 'plugins' / 'calibre_awards' / 'source_cache',
        )
        self.assertTrue(path.is_absolute())

    def test_configure_from_config_dir_sets_injected_directory(self):
        cache.configure_from_config_dir(self.cache_dir)
        _save()
        expected = (
            self.cache_dir / 'plugins' / 'calibre_awards' / 'source_cache' / 'nebula.json'
        )
        self.assertTrue(expected.is_file())
        self.assertFalse((self.cache_dir / 'nebula.json').exists())


class CacheRoundTripTests(CacheTestCase):
    def test_save_then_load_preserves_envelope_and_order(self):
        self._configure()
        records = _records()
        urls = [
            'https://nebulas.sfwa.org/award/best-novel/',
            'https://nebulas.sfwa.org/award/best-novella/',
        ]
        coverage = {'min_year': 1965, 'categories': ['Best Novel', 'Best Novella']}
        _save(
            records=records,
            source_urls=urls,
            coverage=coverage,
            ttl_seconds=86400,
            generated_at=_utc(2026, 8, 28, 12, 0, 0),
        )
        payload = cache.load_source_cache('nebula', 1)
        self.assertIsNotNone(payload)
        self.assertEqual(payload['cache_format_version'], 1)
        self.assertEqual(payload['source_key'], 'nebula')
        self.assertEqual(payload['source_cache_version'], 1)
        self.assertEqual(payload['generated_at'], '2026-08-28T12:00:00Z')
        self.assertEqual(payload['ttl_seconds'], 86400)
        self.assertEqual(payload['source_urls'], urls)
        self.assertEqual(payload['records'], records)
        self.assertEqual(
            [item['title'] for item in payload['records']],
            ['Dune', 'The Left Hand of Darkness'],
        )
        self.assertEqual(payload['record_count'], 2)
        self.assertEqual(payload['coverage'], coverage)

    def test_tuple_records_and_urls_preserve_order(self):
        self._configure()
        _save(
            records=(
                {'title': 'First'},
                {'title': 'Second'},
                {'title': 'Third'},
            ),
            source_urls=(
                'https://example.test/a',
                'https://example.test/b',
            ),
        )
        payload = cache.load_source_cache('nebula', 1)
        self.assertEqual(
            [item['title'] for item in payload['records']],
            ['First', 'Second', 'Third'],
        )
        self.assertEqual(
            payload['source_urls'],
            ['https://example.test/a', 'https://example.test/b'],
        )

    def test_record_count_matches_records(self):
        self._configure()
        _save(records=[])
        payload = cache.load_source_cache('nebula', 1)
        self.assertEqual(payload['records'], [])
        self.assertEqual(payload['record_count'], 0)

    def test_json_is_deterministic(self):
        self._configure()
        _save()
        first = (self.cache_dir / 'nebula.json').read_bytes()
        (self.cache_dir / 'nebula.json').unlink()
        _save()
        second = (self.cache_dir / 'nebula.json').read_bytes()
        self.assertEqual(first, second)
        parsed = json.loads(first.decode('utf-8'))
        self.assertEqual(
            list(parsed),
            sorted(parsed),
        )


class CacheValidationTests(CacheTestCase):
    def _write(self, name, payload):
        path = self.cache_dir / name
        path.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + '\n',
            encoding='utf-8',
        )

    def _valid_payload(self, **overrides):
        values = {
            'cache_format_version': 1,
            'coverage': {'min_year': 1965},
            'generated_at': '2026-01-01T00:00:00Z',
            'record_count': 1,
            'records': [{'title': 'Dune'}],
            'source_cache_version': 1,
            'source_key': 'nebula',
            'source_urls': ['https://example.test/archive'],
            'ttl_seconds': 60,
        }
        values.update(overrides)
        return values

    def test_missing_file_is_none(self):
        self._configure()
        self.assertIsNone(cache.load_source_cache('nebula', 1))

    def test_malformed_json_is_none(self):
        self._configure()
        (self.cache_dir / 'nebula.json').write_text('{not json', encoding='utf-8')
        self.assertIsNone(cache.load_source_cache('nebula', 1))

    def test_top_level_array_is_none(self):
        self._configure()
        (self.cache_dir / 'nebula.json').write_text('[]\n', encoding='utf-8')
        self.assertIsNone(cache.load_source_cache('nebula', 1))

    def test_cache_format_mismatch_is_none(self):
        self._configure()
        self._write('nebula.json', self._valid_payload(cache_format_version=2))
        self.assertIsNone(cache.load_source_cache('nebula', 1))

    def test_source_key_mismatch_is_none(self):
        self._configure()
        self._write('nebula.json', self._valid_payload(source_key='hugo'))
        self.assertIsNone(cache.load_source_cache('nebula', 1))

    def test_source_cache_version_mismatch_is_none(self):
        self._configure()
        self._write('nebula.json', self._valid_payload(source_cache_version=2))
        self.assertIsNone(cache.load_source_cache('nebula', 1))

    def test_missing_required_field_is_none(self):
        self._configure()
        payload = self._valid_payload()
        del payload['coverage']
        self._write('nebula.json', payload)
        self.assertIsNone(cache.load_source_cache('nebula', 1))

    def test_bad_generated_at_is_none(self):
        self._configure()
        self._write('nebula.json', self._valid_payload(generated_at='last Tuesday'))
        self.assertIsNone(cache.load_source_cache('nebula', 1))
        self._write(
            'nebula.json',
            self._valid_payload(generated_at='2026-01-01T00:00:00'),
        )
        self.assertIsNone(cache.load_source_cache('nebula', 1))

    def test_record_count_mismatch_is_none(self):
        self._configure()
        self._write('nebula.json', self._valid_payload(record_count=99))
        self.assertIsNone(cache.load_source_cache('nebula', 1))

    def test_records_not_list_is_none(self):
        self._configure()
        self._write(
            'nebula.json',
            self._valid_payload(records={'title': 'Dune'}, record_count=1),
        )
        self.assertIsNone(cache.load_source_cache('nebula', 1))

    def test_invalid_ttl_is_none(self):
        self._configure()
        self._write('nebula.json', self._valid_payload(ttl_seconds=-1))
        self.assertIsNone(cache.load_source_cache('nebula', 1))
        self._write('nebula.json', self._valid_payload(ttl_seconds=True))
        self.assertIsNone(cache.load_source_cache('nebula', 1))


class CacheFreshnessTests(CacheTestCase):
    def test_fresh_payload_is_true(self):
        generated = _utc()
        payload = {
            'generated_at': '2026-01-01T00:00:00Z',
            'ttl_seconds': 60,
        }
        self.assertTrue(
            cache.cache_is_fresh(payload, now=generated + timedelta(seconds=59))
        )

    def test_stale_payload_is_false(self):
        generated = _utc()
        payload = {
            'generated_at': '2026-01-01T00:00:00Z',
            'ttl_seconds': 60,
        }
        self.assertFalse(
            cache.cache_is_fresh(payload, now=generated + timedelta(seconds=61))
        )

    def test_exact_expiry_boundary_is_stale(self):
        generated = _utc()
        payload = {
            'generated_at': '2026-01-01T00:00:00Z',
            'ttl_seconds': 60,
        }
        self.assertFalse(
            cache.cache_is_fresh(payload, now=generated + timedelta(seconds=60))
        )

    def test_stale_cache_still_loads(self):
        self._configure()
        _save(ttl_seconds=1, generated_at=_utc(2020, 1, 1))
        payload = cache.load_source_cache('nebula', 1)
        self.assertIsNotNone(payload)
        self.assertEqual(payload['source_key'], 'nebula')
        self.assertEqual(
            [item['title'] for item in payload['records']],
            ['Dune', 'The Left Hand of Darkness'],
        )
        self.assertFalse(cache.cache_is_fresh(payload, now=_utc(2026, 1, 1)))


class CacheInvalidationTests(CacheTestCase):
    def test_invalidate_one_source_leaves_another(self):
        self._configure()
        _save('nebula')
        _save('hugo', source_urls=['https://www.thehugoawards.org/'])
        cache.invalidate_source_cache('nebula')
        self.assertIsNone(cache.load_source_cache('nebula', 1))
        remaining = cache.load_source_cache('hugo', 1)
        self.assertIsNotNone(remaining)
        self.assertEqual(remaining['source_key'], 'hugo')
        self.assertTrue((self.cache_dir / 'hugo.json').is_file())
        self.assertFalse((self.cache_dir / 'nebula.json').exists())

    def test_invalidate_missing_source_is_harmless(self):
        self._configure()
        cache.invalidate_source_cache('nebula')

    def test_invalidate_all_removes_owned_json_only(self):
        self._configure()
        _save('nebula')
        _save('hugo', source_urls=['https://www.thehugoawards.org/'])
        unrelated = self.cache_dir / 'notes.txt'
        unrelated.write_text('keep me', encoding='utf-8')
        leftover_tmp = self.cache_dir / 'nebula.partial.json.tmp'
        leftover_tmp.write_text('tmp', encoding='utf-8')
        cache.invalidate_all_source_caches()
        self.assertFalse((self.cache_dir / 'nebula.json').exists())
        self.assertFalse((self.cache_dir / 'hugo.json').exists())
        self.assertTrue(unrelated.is_file())
        self.assertEqual(unrelated.read_text(encoding='utf-8'), 'keep me')
        self.assertTrue(leftover_tmp.is_file())


class SourceInvalidationResultTests(CacheTestCase):
    def test_archive_successful_delete_returns_true(self):
        self._configure()
        _save('nebula')
        self.assertTrue(cache.invalidate_source_cache('nebula'))
        self.assertFalse((self.cache_dir / 'nebula.json').exists())

    def test_archive_missing_file_returns_true(self):
        self._configure()
        self.assertTrue(cache.invalidate_source_cache('nebula'))

    def test_unconfigured_directory_returns_true(self):
        self.assertTrue(cache.invalidate_source_cache('nebula'))

    def test_archive_unlink_failure_returns_false(self):
        self._configure()
        _save('nebula')
        original = Path.unlink

        def _unlink(self, *args, **kwargs):
            if self.name == 'nebula.json':
                raise OSError('permission denied')
            return original(self, *args, **kwargs)

        with patch.object(Path, 'unlink', _unlink):
            self.assertFalse(cache.invalidate_source_cache('nebula'))
        self.assertTrue((self.cache_dir / 'nebula.json').is_file())

    def test_locus_keyed_removal_returns_true(self):
        self._configure()
        _save_entry()
        _save_entry(
            entry_kind='annuals',
            entry_key=ANNUAL_URL,
            records=_annual_records(),
            source_urls=[ANNUAL_URL],
            coverage={'award_year': 1990},
        )
        self.assertTrue(cache.invalidate_source_cache('locus'))
        self.assertFalse((self.cache_dir / 'locus').exists())

    def test_one_locked_locus_keyed_file_returns_false(self):
        self._configure()
        _save_entry()
        _save_entry(
            entry_kind='annuals',
            entry_key=ANNUAL_URL,
            records=_annual_records(),
            source_urls=[ANNUAL_URL],
            coverage={'award_year': 1990},
        )
        blocked = _entry_filename(AUTHOR_URL)
        original = Path.unlink

        def _unlink(self, *args, **kwargs):
            if self.name == blocked:
                raise OSError('permission denied')
            return original(self, *args, **kwargs)

        with patch.object(Path, 'unlink', _unlink):
            self.assertFalse(cache.invalidate_source_cache('locus'))
        self.assertTrue(
            (
                self.cache_dir / 'locus' / 'authors' / blocked
            ).is_file()
        )
        self.assertFalse(
            (
                self.cache_dir / 'locus' / 'annuals' / _entry_filename(ANNUAL_URL)
            ).exists()
        )

    def test_unrelated_files_do_not_cause_invalidation_failure(self):
        self._configure()
        _save('nebula')
        _save_entry()
        notes = self.cache_dir / 'notes.txt'
        notes.write_text('keep me', encoding='utf-8')
        stray = self.cache_dir / 'locus' / 'notes.txt'
        stray.write_text('keep', encoding='utf-8')
        kind_stray = self.cache_dir / 'locus' / 'authors' / 'readme.txt'
        kind_stray.write_text('keep', encoding='utf-8')
        self.assertTrue(cache.invalidate_source_cache('nebula'))
        self.assertTrue(cache.invalidate_source_cache('locus'))
        self.assertTrue(notes.is_file())
        self.assertTrue(stray.is_file())
        self.assertTrue(kind_stray.is_file())
        self.assertFalse((self.cache_dir / 'nebula.json').exists())
        self.assertFalse(
            (
                self.cache_dir / 'locus' / 'authors' / _entry_filename(AUTHOR_URL)
            ).exists()
        )

    def test_existing_callers_may_ignore_the_boolean_result(self):
        self._configure()
        _save('nebula')
        cache.invalidate_source_cache('nebula')
        cache.invalidate_source_cache('nebula')
        self.assertFalse((self.cache_dir / 'nebula.json').exists())


class CacheAtomicReplacementTests(CacheTestCase):
    def test_successful_save_replaces_previous_file(self):
        self._configure()
        _save(records=[{'title': 'Old'}])
        _save(records=[{'title': 'New'}])
        payload = cache.load_source_cache('nebula', 1)
        self.assertEqual(payload['records'], [{'title': 'New'}])
        self.assertEqual(payload['record_count'], 1)

    def test_failed_replace_leaves_previous_file(self):
        self._configure()
        _save(records=[{'title': 'Good'}])
        original = (self.cache_dir / 'nebula.json').read_text(encoding='utf-8')
        with patch('awards.cache.os.replace', side_effect=OSError('disk full')):
            _save(records=[{'title': 'Replacement'}])
        remaining = (self.cache_dir / 'nebula.json').read_text(encoding='utf-8')
        self.assertEqual(remaining, original)
        payload = cache.load_source_cache('nebula', 1)
        self.assertEqual(payload['records'], [{'title': 'Good'}])
        leftovers = [
            name for name in os.listdir(self.cache_dir) if name.endswith('.json.tmp')
        ]
        self.assertEqual(leftovers, [])


class CacheSourceKeySafetyTests(CacheTestCase):
    def test_load_rejects_traversal_and_separators(self):
        self._configure()
        _save('nebula')
        self.assertIsNone(cache.load_source_cache('../nebula', 1))
        self.assertIsNone(cache.load_source_cache('foo/bar', 1))
        self.assertIsNone(cache.load_source_cache('foo\\bar', 1))
        self.assertIsNone(cache.load_source_cache('nebula.json', 1))
        self.assertIsNotNone(cache.load_source_cache('nebula', 1))

    def test_save_rejects_traversal_and_separators(self):
        self._configure()
        for key in ('../nebula', 'foo/bar', 'foo\\bar', '', ' nebula', '.'):
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    _save(key)

    def test_save_does_not_create_files_outside_cache_directory(self):
        self._configure()
        with self.assertRaises(ValueError):
            _save('../outside')
        parent_entries = os.listdir(self.cache_dir.parent)
        self.assertNotIn('outside.json', parent_entries)


class CacheRuntimeResetTests(CacheTestCase):
    def test_reset_disables_configured_directory(self):
        self._configure()
        _save()
        cache._reset_runtime_state()
        self.assertIsNone(cache.load_source_cache('nebula', 1))
        _save()
        self.assertEqual(
            [name for name in os.listdir(self.cache_dir) if name.endswith('.json')],
            ['nebula.json'],
        )


class LookupRefreshBudgetTests(CacheTestCase):
    def test_standalone_always_allows_refresh(self):
        self.assertTrue(cache.try_claim_stale_refresh())
        self.assertTrue(cache.try_claim_stale_refresh())

    def test_first_claim_wins_second_loses_within_lookup(self):
        with cache.lookup_refresh_budget():
            self.assertTrue(cache.try_claim_stale_refresh())
            self.assertFalse(cache.try_claim_stale_refresh())

    def test_next_lookup_gets_a_fresh_budget(self):
        with cache.lookup_refresh_budget():
            self.assertTrue(cache.try_claim_stale_refresh())
            self.assertFalse(cache.try_claim_stale_refresh())
        with cache.lookup_refresh_budget():
            self.assertTrue(cache.try_claim_stale_refresh())

    def test_nested_budget_restores_outer_claim_state(self):
        with cache.lookup_refresh_budget():
            self.assertTrue(cache.try_claim_stale_refresh())
            with cache.lookup_refresh_budget():
                self.assertTrue(cache.try_claim_stale_refresh())
                self.assertFalse(cache.try_claim_stale_refresh())
            self.assertFalse(cache.try_claim_stale_refresh())

    def test_concurrent_workers_only_one_wins(self):
        worker_count = 8
        with cache.lookup_refresh_budget():
            barrier = threading.Barrier(worker_count)
            results: list[bool] = []
            lock = threading.Lock()

            def _worker():
                barrier.wait()
                won = cache.try_claim_stale_refresh()
                with lock:
                    results.append(won)

            threads = [
                threading.Thread(target=_worker) for _ in range(worker_count)
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertEqual(results.count(True), 1)
            self.assertEqual(results.count(False), worker_count - 1)

    def test_reset_clears_active_budget(self):
        with cache.lookup_refresh_budget():
            self.assertTrue(cache.try_claim_stale_refresh())
            cache._reset_runtime_state()
            self.assertTrue(cache.try_claim_stale_refresh())
            self.assertTrue(cache.try_claim_stale_refresh())


AUTHOR_URL = 'https://www.sfadb.com/Dan_Simmons'
SECOND_AUTHOR_URL = 'https://www.sfadb.com/C_J_Cherryh'
ANNUAL_URL = 'https://www.sfadb.com/Locus_Awards_1990'


def _entry_filename(entry_key: str) -> str:
    return hashlib.sha256(entry_key.encode('utf-8')).hexdigest() + '.json'


def _author_records():
    return [
        {'title': 'Hyperion', 'year': 1990, 'rank': 1},
        {'title': 'Muse of Fire', 'year': 2008, 'rank': 5},
    ]


def _annual_records():
    return [
        {'title': 'Hyperion', 'rank': 1},
        {'title': 'Rimrunners', 'rank': 2},
    ]


def _save_entry(
    source_key='locus',
    entry_kind='authors',
    entry_key=AUTHOR_URL,
    version=1,
    **overrides,
):
    values = {
        'records': _author_records(),
        'source_urls': [entry_key],
        'coverage': {'page_name': 'Dan Simmons'},
        'ttl_seconds': 3600,
        'generated_at': _utc(),
    }
    values.update(overrides)
    cache.save_cache_entry(
        source_key,
        entry_kind,
        entry_key,
        version,
        **values,
    )


class KeyedCacheRoundTripTests(CacheTestCase):
    def test_save_then_load_preserves_envelope_and_order(self):
        self._configure()
        records = _author_records()
        urls = [AUTHOR_URL]
        coverage = {'page_name': 'Dan Simmons', 'entry_count': 2}
        _save_entry(
            records=records,
            source_urls=urls,
            coverage=coverage,
            ttl_seconds=86400,
            generated_at=_utc(2026, 8, 28, 12, 0, 0),
        )
        payload = cache.load_cache_entry('locus', 'authors', AUTHOR_URL, 1)
        self.assertIsNotNone(payload)
        self.assertEqual(payload['cache_format_version'], 1)
        self.assertEqual(payload['source_key'], 'locus')
        self.assertEqual(payload['source_cache_version'], 1)
        self.assertEqual(payload['entry_kind'], 'authors')
        self.assertEqual(payload['entry_key'], AUTHOR_URL)
        self.assertEqual(payload['generated_at'], '2026-08-28T12:00:00Z')
        self.assertEqual(payload['ttl_seconds'], 86400)
        self.assertEqual(payload['source_urls'], urls)
        self.assertEqual(payload['records'], records)
        self.assertEqual(
            [item['title'] for item in payload['records']],
            ['Hyperion', 'Muse of Fire'],
        )
        self.assertEqual(payload['record_count'], 2)
        self.assertEqual(payload['coverage'], coverage)

    def test_tuple_records_and_urls_preserve_order(self):
        self._configure()
        _save_entry(
            records=(
                {'title': 'First'},
                {'title': 'Second'},
                {'title': 'Third'},
            ),
            source_urls=(AUTHOR_URL, 'https://www.sfadb.com/'),
        )
        payload = cache.load_cache_entry('locus', 'authors', AUTHOR_URL, 1)
        self.assertEqual(
            [item['title'] for item in payload['records']],
            ['First', 'Second', 'Third'],
        )
        self.assertEqual(
            payload['source_urls'],
            [AUTHOR_URL, 'https://www.sfadb.com/'],
        )

    def test_json_is_deterministic(self):
        self._configure()
        _save_entry()
        path = (
            self.cache_dir / 'locus' / 'authors' / _entry_filename(AUTHOR_URL)
        )
        first = path.read_bytes()
        path.unlink()
        _save_entry()
        second = path.read_bytes()
        self.assertEqual(first, second)
        parsed = json.loads(first.decode('utf-8'))
        self.assertEqual(list(parsed), sorted(parsed))


class KeyedCacheFilenameTests(CacheTestCase):
    def test_hashed_filename_is_deterministic_and_not_a_url(self):
        self._configure()
        _save_entry()
        expected = _entry_filename(AUTHOR_URL)
        path = self.cache_dir / 'locus' / 'authors' / expected
        self.assertTrue(path.is_file())
        self.assertEqual(len(expected), 64 + 5)
        self.assertTrue(all(char in '0123456789abcdef' for char in expected[:-5]))
        self.assertNotIn('http', expected)
        self.assertNotIn('sfadb', expected)
        self.assertNotIn('Dan_Simmons', expected)
        self.assertNotIn('/', expected)
        names = os.listdir(self.cache_dir / 'locus' / 'authors')
        self.assertEqual(names, [expected])
        again = hashlib.sha256(AUTHOR_URL.encode('utf-8')).hexdigest() + '.json'
        self.assertEqual(again, expected)
        self.assertNotEqual(again, str(hash(AUTHOR_URL)))

    def test_different_entry_keys_use_different_filenames(self):
        self._configure()
        _save_entry(entry_key=AUTHOR_URL, source_urls=[AUTHOR_URL])
        _save_entry(
            entry_key=SECOND_AUTHOR_URL,
            source_urls=[SECOND_AUTHOR_URL],
            coverage={'page_name': 'C. J. Cherryh'},
        )
        first = _entry_filename(AUTHOR_URL)
        second = _entry_filename(SECOND_AUTHOR_URL)
        self.assertNotEqual(first, second)
        author_dir = self.cache_dir / 'locus' / 'authors'
        self.assertTrue((author_dir / first).is_file())
        self.assertTrue((author_dir / second).is_file())


class KeyedCacheLayoutTests(CacheTestCase):
    def test_locus_author_and_annual_layout(self):
        self._configure()
        _save_entry(
            source_key='locus',
            entry_kind='authors',
            entry_key=AUTHOR_URL,
            source_urls=[AUTHOR_URL],
        )
        _save_entry(
            source_key='locus',
            entry_kind='annuals',
            entry_key=ANNUAL_URL,
            records=_annual_records(),
            source_urls=[ANNUAL_URL],
            coverage={'award_year': 1990},
        )
        author_path = (
            self.cache_dir / 'locus' / 'authors' / _entry_filename(AUTHOR_URL)
        )
        annual_path = (
            self.cache_dir / 'locus' / 'annuals' / _entry_filename(ANNUAL_URL)
        )
        self.assertTrue(author_path.is_file())
        self.assertTrue(annual_path.is_file())
        self.assertFalse((self.cache_dir / 'locus.json').exists())
        self.assertNotEqual(author_path, annual_path)

    def test_archive_source_files_stay_at_top_level(self):
        self._configure()
        _save('nebula')
        _save_entry()
        self.assertTrue((self.cache_dir / 'nebula.json').is_file())
        self.assertFalse((self.cache_dir / 'nebula').exists())
        self.assertTrue(
            (
                self.cache_dir / 'locus' / 'authors' / _entry_filename(AUTHOR_URL)
            ).is_file()
        )
        payload = cache.load_source_cache('nebula', 1)
        self.assertEqual(payload['source_key'], 'nebula')
        self.assertNotIn('entry_key', payload)


class KeyedCacheIdentityTests(CacheTestCase):
    def _rewrite(self, **overrides):
        path = (
            self.cache_dir / 'locus' / 'authors' / _entry_filename(AUTHOR_URL)
        )
        payload = json.loads(path.read_text(encoding='utf-8'))
        payload.update(overrides)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
            + '\n',
            encoding='utf-8',
        )

    def test_stored_entry_key_mismatch_is_none(self):
        self._configure()
        _save_entry()
        self._rewrite(entry_key=SECOND_AUTHOR_URL)
        self.assertIsNone(
            cache.load_cache_entry('locus', 'authors', AUTHOR_URL, 1)
        )

    def test_wrong_entry_kind_is_none(self):
        self._configure()
        _save_entry()
        self.assertIsNone(
            cache.load_cache_entry('locus', 'annuals', AUTHOR_URL, 1)
        )

    def test_wrong_source_key_is_none(self):
        self._configure()
        _save_entry()
        self.assertIsNone(
            cache.load_cache_entry('hugo', 'authors', AUTHOR_URL, 1)
        )

    def test_wrong_source_cache_version_is_none(self):
        self._configure()
        _save_entry()
        self.assertIsNone(
            cache.load_cache_entry('locus', 'authors', AUTHOR_URL, 2)
        )


class KeyedCacheCorruptionTests(CacheTestCase):
    def _path(self):
        return self.cache_dir / 'locus' / 'authors' / _entry_filename(AUTHOR_URL)

    def test_malformed_json_is_none(self):
        self._configure()
        _save_entry()
        self._path().write_text('{not json', encoding='utf-8')
        self.assertIsNone(
            cache.load_cache_entry('locus', 'authors', AUTHOR_URL, 1)
        )

    def test_bad_record_count_is_none(self):
        self._configure()
        _save_entry()
        payload = json.loads(self._path().read_text(encoding='utf-8'))
        payload['record_count'] = 99
        self._path().write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
            + '\n',
            encoding='utf-8',
        )
        self.assertIsNone(
            cache.load_cache_entry('locus', 'authors', AUTHOR_URL, 1)
        )

    def test_missing_required_field_is_none(self):
        self._configure()
        _save_entry()
        payload = json.loads(self._path().read_text(encoding='utf-8'))
        del payload['entry_key']
        self._path().write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
            + '\n',
            encoding='utf-8',
        )
        self.assertIsNone(
            cache.load_cache_entry('locus', 'authors', AUTHOR_URL, 1)
        )

    def test_records_not_list_is_none(self):
        self._configure()
        _save_entry()
        payload = json.loads(self._path().read_text(encoding='utf-8'))
        payload['records'] = {'title': 'Hyperion'}
        payload['record_count'] = 1
        self._path().write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
            + '\n',
            encoding='utf-8',
        )
        self.assertIsNone(
            cache.load_cache_entry('locus', 'authors', AUTHOR_URL, 1)
        )


class KeyedCacheSafetyTests(CacheTestCase):
    def test_save_rejects_empty_and_unsafe_source_key(self):
        self._configure()
        for key in ('', ' ', '../locus', 'foo/bar', 'foo\\bar'):
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    _save_entry(source_key=key)

    def test_save_rejects_empty_and_unsafe_entry_kind(self):
        self._configure()
        for kind in (
            '',
            ' ',
            '../',
            '..',
            'authors/evil',
            'authors\\evil',
            '/authors',
            '\\authors',
            'C:authors',
            'C:/authors',
        ):
            with self.subTest(kind=kind):
                with self.assertRaises(ValueError):
                    _save_entry(entry_kind=kind)
        self.assertFalse((self.cache_dir / 'authors').exists())
        parent_names = os.listdir(self.cache_dir.parent)
        self.assertNotIn('authors', parent_names)

    def test_save_rejects_empty_entry_key(self):
        self._configure()
        for entry_key in ('', '   ', ' https://example.test/x'):
            with self.subTest(entry_key=repr(entry_key)):
                with self.assertRaises(ValueError):
                    _save_entry(entry_key=entry_key)

    def test_load_rejects_unsafe_identifiers_without_raising(self):
        self._configure()
        _save_entry()
        self.assertIsNone(cache.load_cache_entry('', 'authors', AUTHOR_URL, 1))
        self.assertIsNone(
            cache.load_cache_entry('../locus', 'authors', AUTHOR_URL, 1)
        )
        self.assertIsNone(
            cache.load_cache_entry('locus', '../authors', AUTHOR_URL, 1)
        )
        self.assertIsNone(
            cache.load_cache_entry('locus', 'authors/evil', AUTHOR_URL, 1)
        )
        self.assertIsNone(cache.load_cache_entry('locus', 'authors', '', 1))
        self.assertIsNone(cache.load_cache_entry('locus', 'authors', '  x', 1))
        self.assertIsNotNone(
            cache.load_cache_entry('locus', 'authors', AUTHOR_URL, 1)
        )

    def test_url_entry_key_is_hashed_not_used_as_path(self):
        self._configure()
        _save_entry(entry_key=AUTHOR_URL, source_urls=[AUTHOR_URL])
        walked = [str(path) for path in self.cache_dir.rglob('*')]
        self.assertTrue(any(path.endswith('.json') for path in walked))
        self.assertFalse(any('http:' in path or 'https:' in path for path in walked))
        self.assertFalse(any('Dan_Simmons' in path for path in walked))


class KeyedCacheAtomicReplacementTests(CacheTestCase):
    def test_successful_save_replaces_previous_entry(self):
        self._configure()
        _save_entry(records=[{'title': 'Old'}])
        _save_entry(records=[{'title': 'New'}])
        payload = cache.load_cache_entry('locus', 'authors', AUTHOR_URL, 1)
        self.assertEqual(payload['records'], [{'title': 'New'}])
        self.assertEqual(payload['record_count'], 1)

    def test_failed_replace_leaves_previous_entry(self):
        self._configure()
        _save_entry(records=[{'title': 'Good'}])
        path = (
            self.cache_dir / 'locus' / 'authors' / _entry_filename(AUTHOR_URL)
        )
        original = path.read_text(encoding='utf-8')
        with patch('awards.cache.os.replace', side_effect=OSError('disk full')):
            _save_entry(records=[{'title': 'Replacement'}])
        self.assertEqual(path.read_text(encoding='utf-8'), original)
        payload = cache.load_cache_entry('locus', 'authors', AUTHOR_URL, 1)
        self.assertEqual(payload['records'], [{'title': 'Good'}])
        leftovers = [
            name
            for name in os.listdir(self.cache_dir / 'locus' / 'authors')
            if name.endswith('.json.tmp')
        ]
        self.assertEqual(leftovers, [])


class KeyedCacheIndependenceTests(CacheTestCase):
    def test_corrupt_or_deleted_entry_does_not_affect_siblings(self):
        self._configure()
        _save_entry(entry_key=AUTHOR_URL, source_urls=[AUTHOR_URL])
        _save_entry(
            entry_key=SECOND_AUTHOR_URL,
            source_urls=[SECOND_AUTHOR_URL],
            coverage={'page_name': 'C. J. Cherryh'},
        )
        _save_entry(
            entry_kind='annuals',
            entry_key=ANNUAL_URL,
            records=_annual_records(),
            source_urls=[ANNUAL_URL],
            coverage={'award_year': 1990},
        )
        first_path = (
            self.cache_dir / 'locus' / 'authors' / _entry_filename(AUTHOR_URL)
        )
        first_path.write_text('{broken', encoding='utf-8')
        self.assertIsNone(
            cache.load_cache_entry('locus', 'authors', AUTHOR_URL, 1)
        )
        second = cache.load_cache_entry(
            'locus', 'authors', SECOND_AUTHOR_URL, 1
        )
        annual = cache.load_cache_entry('locus', 'annuals', ANNUAL_URL, 1)
        self.assertEqual(second['entry_key'], SECOND_AUTHOR_URL)
        self.assertEqual(annual['entry_key'], ANNUAL_URL)
        self.assertEqual(
            [item['title'] for item in annual['records']],
            ['Hyperion', 'Rimrunners'],
        )


class KeyedCacheInvalidationTests(CacheTestCase):
    def test_invalidate_entry_removes_only_that_file(self):
        self._configure()
        _save_entry(entry_key=AUTHOR_URL, source_urls=[AUTHOR_URL])
        _save_entry(
            entry_key=SECOND_AUTHOR_URL,
            source_urls=[SECOND_AUTHOR_URL],
            coverage={'page_name': 'C. J. Cherryh'},
        )
        _save_entry(
            entry_kind='annuals',
            entry_key=ANNUAL_URL,
            records=_annual_records(),
            source_urls=[ANNUAL_URL],
            coverage={'award_year': 1990},
        )
        cache.invalidate_cache_entry('locus', 'authors', AUTHOR_URL)
        self.assertIsNone(
            cache.load_cache_entry('locus', 'authors', AUTHOR_URL, 1)
        )
        self.assertIsNotNone(
            cache.load_cache_entry('locus', 'authors', SECOND_AUTHOR_URL, 1)
        )
        self.assertIsNotNone(
            cache.load_cache_entry('locus', 'annuals', ANNUAL_URL, 1)
        )
        cache.invalidate_cache_entry('locus', 'authors', AUTHOR_URL)

    def test_invalidate_source_removes_keyed_subtree_only(self):
        self._configure()
        _save('nebula')
        _save_entry()
        _save_entry(
            entry_kind='annuals',
            entry_key=ANNUAL_URL,
            records=_annual_records(),
            source_urls=[ANNUAL_URL],
            coverage={'award_year': 1990},
        )
        cache.invalidate_source_cache('locus')
        self.assertFalse((self.cache_dir / 'locus').exists())
        self.assertTrue((self.cache_dir / 'nebula.json').is_file())
        self.assertIsNotNone(cache.load_source_cache('nebula', 1))
        self.assertIsNone(
            cache.load_cache_entry('locus', 'authors', AUTHOR_URL, 1)
        )

    def test_invalidate_all_removes_managed_caches_and_keeps_unrelated(self):
        self._configure()
        _save('nebula')
        _save('hugo', source_urls=['https://www.thehugoawards.org/'])
        _save_entry()
        _save_entry(
            entry_kind='annuals',
            entry_key=ANNUAL_URL,
            records=_annual_records(),
            source_urls=[ANNUAL_URL],
            coverage={'award_year': 1990},
        )
        notes = self.cache_dir / 'notes.txt'
        notes.write_text('keep me', encoding='utf-8')
        leftover_tmp = self.cache_dir / 'nebula.partial.json.tmp'
        leftover_tmp.write_text('tmp', encoding='utf-8')
        unrelated_dir = self.cache_dir / 'diagnostics'
        unrelated_dir.mkdir()
        unrelated_file = unrelated_dir / 'trace.log'
        unrelated_file.write_text('log', encoding='utf-8')
        cache.invalidate_all_source_caches()
        self.assertFalse((self.cache_dir / 'nebula.json').exists())
        self.assertFalse((self.cache_dir / 'hugo.json').exists())
        self.assertFalse((self.cache_dir / 'locus').exists())
        self.assertTrue(notes.is_file())
        self.assertEqual(notes.read_text(encoding='utf-8'), 'keep me')
        self.assertTrue(leftover_tmp.is_file())
        self.assertTrue(unrelated_dir.is_dir())
        self.assertTrue(unrelated_file.is_file())

    def test_invalidate_all_leaves_unrelated_files_inside_source_dir(self):
        self._configure()
        _save_entry()
        stray = self.cache_dir / 'locus' / 'notes.txt'
        stray.write_text('keep', encoding='utf-8')
        cache.invalidate_all_source_caches()
        self.assertTrue(stray.is_file())
        self.assertEqual(stray.read_text(encoding='utf-8'), 'keep')
        self.assertFalse(
            (
                self.cache_dir / 'locus' / 'authors' / _entry_filename(AUTHOR_URL)
            ).exists()
        )


class KeyedCacheUnconfiguredTests(CacheTestCase):
    def test_unconfigured_keyed_load_is_none(self):
        self.assertIsNone(
            cache.load_cache_entry('locus', 'authors', AUTHOR_URL, 1)
        )

    def test_unconfigured_keyed_save_and_invalidate_are_harmless(self):
        _save_entry()
        cache.invalidate_cache_entry('locus', 'authors', AUTHOR_URL)
        self.assertEqual(os.listdir(self.cache_dir), [])


class KeyedCacheFreshnessTests(CacheTestCase):
    def test_stale_keyed_payload_still_loads(self):
        self._configure()
        _save_entry(ttl_seconds=1, generated_at=_utc(2020, 1, 1))
        payload = cache.load_cache_entry('locus', 'authors', AUTHOR_URL, 1)
        self.assertIsNotNone(payload)
        self.assertEqual(payload['entry_key'], AUTHOR_URL)
        self.assertEqual(
            [item['title'] for item in payload['records']],
            ['Hyperion', 'Muse of Fire'],
        )
        self.assertFalse(cache.cache_is_fresh(payload, now=_utc(2026, 1, 1)))

    def test_fresh_keyed_payload_is_true(self):
        self._configure()
        _save_entry(ttl_seconds=60, generated_at=_utc())
        payload = cache.load_cache_entry('locus', 'authors', AUTHOR_URL, 1)
        self.assertTrue(
            cache.cache_is_fresh(payload, now=_utc(2026, 1, 1, 0, 0, 59))
        )


if __name__ == '__main__':
    unittest.main()
